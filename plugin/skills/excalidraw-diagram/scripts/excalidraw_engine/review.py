"""Tables -> modelling problems: the review half of the data-model module.

Ten rules, one function each, run over the tables and the roles classify.py gave them:

    grain                  a fact with no primary key states no grain
    surrogate-key          a dimension whose key is not an artificial one
    scd2                   a dimension with changing attributes and no valid_from / valid_to
    orphan-fk              a foreign key to a table or column that does not exist
    snowflake              a dimension normalised into sub-dimensions
    fk-type                a foreign key whose type is not the type of the key it points at
    degenerate-dimension   a dimension that holds nothing but its key
    junk-dimension         a dimension that holds nothing but flags
    conformed-dimension    a fact that shares no dimension with any other fact
    many-to-many           several keys in one column, with no bridge table

Every Issue carries the sentence that says WHY, not just a label. A rule fires only on
evidence it can name, so a clean schema stays silent: the rules lean towards missing a
problem over inventing one.
"""

import re

_SURROGATE = re.compile(r"(_key|_sk|_skey)$|^(key|sk)$", re.I)
# Names that suggest an attribute which changes over time. One strong name is enough; the
# weak ones are places, which move for a person and almost never for a warehouse, so two
# of them are needed.
_STRONG = re.compile(r"(^|_)(address|email|phone|status|tier|plan|manager|department|"
                     r"job_title|salary|segment)(_|$)", re.I)
_WEAK = re.compile(r"(^|_)(city|country|region)(_|$)", re.I)
_KEYISH = re.compile(r"(^id$|_id$|_key$|_sk$|_fk$|_code$)", re.I)
_LABEL = ("name", "label", "title", "description")
_VALID_FROM = re.compile(r"^(valid_from|effective_from|effective_date|row_start|start_date)$", re.I)
_VALID_TO = re.compile(r"^(valid_to|effective_to|row_end|end_date)$", re.I)
_FLAG_NAME = re.compile(r"^(is|has|can)_|_(flag|ind)$", re.I)
_FLAG_TYPE = re.compile(r"^(bool|boolean|bit)\b", re.I)
_KEY_LIST = re.compile(r"_(ids|keys|codes)$", re.I)
_ARRAY = re.compile(r"\[\s*\d*\s*\]|\barray\b", re.I)
# the same type under its other names, so `int` and `integer` are not a mismatch and a serial
# primary key can be pointed at by a plain integer
_SAME_TYPE = {"integer": "int", "int4": "int", "serial": "int", "serial4": "int",
              "int8": "bigint", "bigserial": "bigint", "serial8": "bigint",
              "int2": "smallint", "smallserial": "smallint", "decimal": "numeric",
              "character varying": "varchar", "character": "char", "bool": "boolean"}


class Issue(object):
    """A problem on `table`: which `rule` found it and the `message` saying why."""

    __slots__ = ("table", "rule", "message")

    def __init__(self, table, rule, message):
        self.table, self.rule, self.message = table, rule, message


class _Schema(object):
    """What every review rule reads: the tables, the roles classify_tables() gave them, and
    the tables by name. One value instead of three arguments every rule takes together."""

    def __init__(self, tables, roles):
        self.tables, self.roles = tables, roles
        self.by_name = {t.name: t for t in tables}

    def of_role(self, role):
        """The tables classified as `role`, in schema order."""
        return [t for t in self.tables if self.roles[t.name].role == role]


def _grain(schema):
    return [Issue(t.name, "grain",
                  "fact has no primary key, so one row's meaning (its grain) is not stated; "
                  "declare the key that makes a row unique")
            for t in schema.of_role("fact") if not t.primary_key]


def _surrogate_key(schema):
    out = []
    for t in schema.of_role("dimension"):
        pk = t.primary_key
        if len(pk) == 1 and _SURROGATE.search(pk[0]):
            continue
        if not pk:
            why = "has no primary key"
        elif len(pk) > 1:
            why = "is keyed by the composite (%s)" % ", ".join(pk)
        else:
            why = ("is keyed by %s, which looks like a source-system id rather than a "
                   "surrogate key (a *_key or *_sk column)" % pk[0])
        out.append(Issue(t.name, "surrogate-key",
                         "dimension %s; add a surrogate key so source ids can change" % why))
    return out


def _attributes(table):
    """The names of the columns that describe what `table` holds, as opposed to keys and to
    the entity's own label: `department_key` is a key and `department.department_name` is the
    department's name, and neither is an attribute that changes."""
    keys = set(table.primary_key) | {c for fk in table.foreign_keys for c in fk.columns}
    own = [table.name.lower() + "_" + w for w in _LABEL]
    return [c.name for c in table.columns
            if c.name not in keys and not _KEYISH.search(c.name) and c.name.lower() not in own]


def _scd2(schema):
    out = []
    for t in schema.of_role("dimension"):
        names = [c.name for c in t.columns]
        has_from = any(_VALID_FROM.match(n) for n in names)
        has_to = any(_VALID_TO.match(n) for n in names)
        attrs = _attributes(t)
        strong = [n for n in attrs if _STRONG.search(n)]
        weak = [n for n in attrs if _WEAK.search(n)]
        changing = strong + weak if strong or len(weak) >= 2 else []
        if has_from != has_to:
            out.append(Issue(t.name, "scd2", "only one of valid_from / valid_to is present; "
                                             "a type 2 history needs both"))
        elif changing and not has_from:
            out.append(Issue(t.name, "scd2",
                             "%s can change over time but there is no valid_from / valid_to "
                             "(SCD type 2): history is overwritten" % ", ".join(changing[:3])))
    return out


def _orphan_fk(schema):
    out = []
    for t in schema.tables:
        for fk in t.foreign_keys:
            target = schema.by_name.get(fk.ref_table)
            if target is None:
                out.append(Issue(t.name, "orphan-fk", "%s references %s, which the schema "
                                 "does not define" % (", ".join(fk.columns), fk.ref_table)))
                continue
            gone = [c for c in fk.ref_columns if target.column(c) is None]
            if gone:
                out.append(Issue(t.name, "orphan-fk", "%s references %s.%s, which does not exist"
                                 % (", ".join(fk.columns), fk.ref_table, ", ".join(gone))))
    return out


def _snowflake(schema):
    dims = {t.name for t in schema.of_role("dimension")}
    parents = {}                        # sub-dimension -> {dimension that references it}
    for t in schema.tables:
        if t.name in dims:
            for fk in t.foreign_keys:
                if fk.ref_table in dims and fk.ref_table != t.name:
                    parents.setdefault(fk.ref_table, {})[t.name] = fk
    level = {}

    def depth(name, path=()):
        if name not in level:
            ups = [p for p in parents.get(name, ()) if p not in path]
            level[name] = 1 + max([depth(p, path + (name,)) for p in ups], default=-1)
        return level[name]

    out = []
    for t in schema.tables:
        ups = parents.get(t.name)
        if not ups:
            continue
        lvl, first = depth(t.name), sorted(ups)[0]
        if lvl == 1 and len(ups) > 1:
            continue                    # one outrigger shared by several dimensions
        fk = ups[first]
        where = "%s.%s -> %s" % (first, ", ".join(fk.columns), t.name)
        if lvl >= 2:
            msg = "deep snowflake: %s sits %d levels below its fact-side dimension (%s)" % (
                t.name, lvl, where)
        else:
            msg = ("%s is a snowflake of %s (%s); denormalise its columns into %s unless "
                   "several dimensions share it" % (t.name, first, where, first))
        out.append(Issue(t.name, "snowflake", msg))
    return out


def _base_type(declared):
    """A declared type reduced to what a join compares: lower case, no length or precision,
    one name for the usual aliases. `varchar(20)` and `varchar(40)` are the same type."""
    name = " ".join(re.sub(r"\(.*?\)", "", declared.lower()).split())
    return _SAME_TYPE.get(name, name)


def _fk_type(schema):
    # implements: REQ-DATAMODEL-915
    out = []
    for t in schema.tables:
        for fk in t.foreign_keys:
            target = schema.by_name.get(fk.ref_table)
            if target is None:
                continue
            refs = fk.ref_columns or (target.primary_key
                                      if len(target.primary_key) == len(fk.columns) else [])
            for name, ref in zip(fk.columns, refs):
                col, key = t.column(name), target.column(ref)
                if col is None or key is None or not col.type or not key.type:
                    continue                    # a type nobody declared is not a mismatch
                if _base_type(col.type) != _base_type(key.type):
                    out.append(Issue(t.name, "fk-type",
                                     "%s is %s but it points at %s.%s, which is %s; a join "
                                     "across two types converts every value or skips the index"
                                     % (name, col.type, fk.ref_table, ref, key.type)))
    return out


def _non_key_columns(table):
    """The columns of `table` that are neither in a key nor named like one."""
    keys = set(table.primary_key) | {c for fk in table.foreign_keys for c in fk.columns}
    return [c for c in table.columns if c.name not in keys and not _KEYISH.search(c.name)]


def _degenerate_dimension(schema):
    # implements: REQ-DATAMODEL-915
    return [Issue(t.name, "degenerate-dimension",
                  "dimension holds nothing but its key (%s); a key with no attributes of its "
                  "own belongs in the fact, as a degenerate dimension, not in a table"
                  % ", ".join(c.name for c in t.columns))
            for t in schema.of_role("dimension") if t.columns and not _non_key_columns(t)]


def _junk_dimension(schema):
    # implements: REQ-DATAMODEL-915
    out = []
    for t in schema.of_role("dimension"):
        plain = _non_key_columns(t)
        if len(plain) >= 2 and all(_FLAG_NAME.search(c.name) or _FLAG_TYPE.match(c.type or "")
                                   for c in plain):
            out.append(Issue(t.name, "junk-dimension",
                             "dimension holds only flags (%s); as a junk dimension its rows must be "
                             "the combinations that occur, otherwise keep the flags in the fact"
                             % ", ".join(c.name for c in plain[:4])))
    return out


def _conformed_dimension(schema):
    # implements: REQ-DATAMODEL-915
    facts = schema.of_role("fact")
    if len(facts) < 2:
        return []

    def dimensions(table):
        return {fk.ref_table for fk in table.foreign_keys
                if fk.ref_table in schema.roles and schema.roles[fk.ref_table].role == "dimension"}

    out = []
    for fact in facts:
        own, others = dimensions(fact), [f for f in facts if f is not fact]
        if own and not any(own & dimensions(other) for other in others):
            out.append(Issue(fact.name, "conformed-dimension",
                             "shares no dimension with %s, so its numbers cannot be read beside "
                             "theirs; point both at a common dimension such as date or customer"
                             % ", ".join(f.name for f in others[:3])))
    return out


def _many_to_many(schema):
    # implements: REQ-DATAMODEL-915
    out = []
    for t in schema.tables:
        keys = set(t.primary_key) | {c for fk in t.foreign_keys for c in fk.columns}
        for c in t.columns:
            several = _KEY_LIST.search(c.name) or (
                _ARRAY.search(c.type or "") and _KEYISH.search(c.name))
            if several and c.name not in keys:
                out.append(Issue(t.name, "many-to-many",
                                 "%s holds several keys in one column, a many-to-many relation "
                                 "with no bridge table; add a table with one row for each pair"
                                 % c.name))
    return out


RULES = (_grain, _surrogate_key, _scd2, _orphan_fk, _snowflake, _fk_type, _degenerate_dimension,
         _junk_dimension, _conformed_dimension, _many_to_many)


def review_tables(tables, roles):
    """[Issue] for `tables`, given classify_tables()'s `roles`; table order, then rule order."""
    # implements: REQ-DATAMODEL-903
    schema = _Schema(tables, roles)
    found = [i for rule in RULES for i in rule(schema)]
    order = {t.name: n for n, t in enumerate(tables)}
    return sorted(found, key=lambda i: order[i.table])
