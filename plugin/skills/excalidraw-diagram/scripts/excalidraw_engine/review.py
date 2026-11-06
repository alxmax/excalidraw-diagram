"""Tables -> modelling problems: the review half of the data-model module.

Five rules, one function each, run over the tables and the roles classify.py gave them:

    grain          a fact with no primary key states no grain
    surrogate-key  a dimension whose key is not an artificial one
    scd2           a dimension with changing attributes and no valid_from / valid_to
    orphan-fk      a foreign key to a table or column that does not exist
    snowflake      a dimension normalised into sub-dimensions

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


class Issue(object):
    """A problem on `table`: which `rule` found it and the `message` saying why."""

    __slots__ = ("table", "rule", "message")

    def __init__(self, table, rule, message):
        self.table, self.rule, self.message = table, rule, message


def _of_role(tables, roles, role):
    return [t for t in tables if roles[t.name].role == role]


def _grain(tables, roles, _by_name):
    return [Issue(t.name, "grain",
                  "fact has no primary key, so one row's meaning (its grain) is not stated; "
                  "declare the key that makes a row unique")
            for t in _of_role(tables, roles, "fact") if not t.primary_key]


def _surrogate_key(tables, roles, _by_name):
    out = []
    for t in _of_role(tables, roles, "dimension"):
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


def _scd2(tables, roles, _by_name):
    out = []
    for t in _of_role(tables, roles, "dimension"):
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


def _orphan_fk(tables, _roles, by_name):
    out = []
    for t in tables:
        for fk in t.foreign_keys:
            target = by_name.get(fk.ref_table)
            if target is None:
                out.append(Issue(t.name, "orphan-fk", "%s references %s, which the schema "
                                 "does not define" % (", ".join(fk.columns), fk.ref_table)))
                continue
            gone = [c for c in fk.ref_columns if target.column(c) is None]
            if gone:
                out.append(Issue(t.name, "orphan-fk", "%s references %s.%s, which does not exist"
                                 % (", ".join(fk.columns), fk.ref_table, ", ".join(gone))))
    return out


def _snowflake(tables, roles, by_name):
    dims = {t.name for t in _of_role(tables, roles, "dimension")}
    parents = {}                        # sub-dimension -> {dimension that references it}
    for t in tables:
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
    for t in tables:
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


RULES = (_grain, _surrogate_key, _scd2, _orphan_fk, _snowflake)


def review_tables(tables, roles):
    """[Issue] for `tables`, given classify_tables()'s `roles`; table order, then rule order."""
    # implements: REQ-DATAMODEL-903
    by_name = {t.name: t for t in tables}
    found = [i for rule in RULES for i in rule(tables, roles, by_name)]
    order = {t.name: n for n, t in enumerate(tables)}
    return sorted(found, key=lambda i: order[i.table])
