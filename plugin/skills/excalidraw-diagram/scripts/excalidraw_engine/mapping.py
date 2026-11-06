"""A dbt project -> a source-to-target mapping in Markdown.

For every model, one row per target column: where it comes from, what is done to it, and
which rules (the schema.yml tests) it must meet.

The source of a column is only as good as the SQL reader behind it, and that reader is a
small one: it follows a plain `select`, aliases, joins and CTEs that merely pass a table
through. Anything else is NOT guessed. A union, Jinja control flow, a subquery in `from`,
a CTE that reshapes its input, or an unqualified column with several relations in scope
gives a row marked "needs review" with the reason, because a mapping that looks complete
and is wrong is worse than one that says where to read the SQL.
"""

import re

from .ddl import _split
from .dbt import _NOISE, read_dbt_project

_JINJA_CONFIG = re.compile(r"\{\{\s*config\s*\(.*?\)\s*\}\}", re.S)
_JINJA_REF = re.compile(r"""\{\{\s*ref\s*\(\s*(?:['"][^'"]+['"]\s*,\s*)?['"]([\w.-]+)['"]\s*\)\s*\}\}""")
_JINJA_SOURCE = re.compile(r"""\{\{\s*source\s*\(\s*['"]([\w.-]+)['"]\s*,\s*['"]([\w.-]+)['"]\s*\)\s*\}\}""")
_JINJA_LEFT = re.compile(r"\{\{|\{%")
_NOT_ALIAS = frozenset("on using left right inner outer full cross natural join where group "
                       "order having limit union intersect except window qualify lateral "
                       "offset fetch".split())
_NOT_COLUMN = frozenset("""as case when then else end and or not null is in distinct cast over
    partition by order asc desc between like ilike true false current_date current_timestamp
    interval int integer bigint smallint numeric decimal float double precision real varchar
    char text date timestamp timestamptz boolean bool exists all any some filter rows range
    unbounded preceding following current row""".split())
_PLAIN = re.compile(r"^(?:(\w+)\.)?(\w+)$")
_AS = re.compile(r"^(.*\S)\s+as\s+\"?(\w+)\"?$", re.I | re.S)
_FROM_ITEM = re.compile(r"(?:\bfrom\b|\bjoin\b|,)\s+(?P<rel>\(|[\w.]+)(?:\s+(?:as\s+)?(?P<alias>\w+))?", re.I)
_QUALIFIED = re.compile(r"\b(\w+)\.(\w+)\b(?!\s*\()")
_WORD = re.compile(r"\b[A-Za-z_]\w*\b(?!\s*\()")


class Row(object):
    """One target column: its `sources`, the `transform` text, the `rule` text and, when
    the reader could not be sure, the `review` reason (else None)."""

    __slots__ = ("target", "sources", "transform", "rule", "review")

    def __init__(self, target, sources, transform, rule, review=None):
        self.target, self.sources, self.transform = target, sources, transform
        self.rule, self.review = rule, review


# ---------------------------------------------------------------------------
# reading one query
# ---------------------------------------------------------------------------
def _prepare(sql):
    """`sql` as plain SQL: comments gone, ref() and source() as names. None when Jinja is
    left over that this reader does not evaluate."""
    text = _JINJA_CONFIG.sub(" ", _NOISE.sub(" ", sql))
    text = _JINJA_REF.sub(lambda m: m.group(1), text)
    text = _JINJA_SOURCE.sub(lambda m: "%s.%s" % m.groups(), text)
    return None if _JINJA_LEFT.search(text) else text.strip().rstrip(";").strip()


def _mask(text):
    """(masked, depth): `text` with string contents blanked, and the paren depth at each
    character, so a keyword is found only where it sits at the top level."""
    masked, depth, level, quote = [], [], 0, None
    for ch in text:
        if quote:
            masked.append("_" if ch != quote else ch)
            quote = None if ch == quote else quote
        elif ch in "'\"":
            quote = ch
            masked.append(ch)
        else:
            level += ch == "("
            level -= ch == ")"
            masked.append(ch)
        depth.append(level)
    return "".join(masked), depth


def _top(word, masked, depth, start=0):
    """Positions of the keyword `word` outside every parenthesis, from `start`."""
    return [start + m.start() for m in re.finditer(r"\b%s\b" % word, masked[start:], re.I)
            if depth[start + m.start()] == 0]


def _balanced(text, open_at):
    """The index of the parenthesis closing the one at `open_at`, or -1."""
    level = 0
    for i in range(open_at, len(text)):
        level += text[i] == "("
        level -= text[i] == ")"
        if level == 0:
            return i
    return -1


def _ctes(text):
    """({name: body}, rest) for a leading WITH clause; the same text when there is none.
    None when the clause cannot be read."""
    m = re.match(r"\s*with\s+(?:recursive\s+)?", text, re.I)
    if not m:
        return {}, text
    out, pos = {}, m.end()
    while True:
        head = re.compile(r"\s*(\w+)\s*(?:\([^)]*\))?\s*as\s*(?:not\s+materialized\s+|materialized\s+)?\(",
                          re.I).match(text, pos)
        if not head:
            return None
        end = _balanced(text, head.end() - 1)
        if end < 0:
            return None
        out[head.group(1).lower()] = text[head.end():end]
        pos = end + 1
        comma = re.compile(r"\s*,").match(text, pos)
        if not comma:
            return out, text[pos:]
        pos = comma.end()


class Select(object):
    """A parsed `select`: its items (source text), and `aliases` {alias: relation}."""

    def __init__(self, items, aliases, why=None):
        self.items, self.aliases, self.why = items, aliases, why


def _select(text):
    """The Select in `text`, or one with `why` set when it is outside what is read."""
    masked, depth = _mask(text)
    selects = _top("select", masked, depth)
    if len(selects) != 1 or any(_top(w, masked, depth) for w in ("union", "intersect", "except")):
        return Select([], {}, "more than one SELECT (union or set operation)")
    start = selects[0] + len("select")
    froms = _top("from", masked, depth, start)
    end = froms[0] if froms else len(text)
    head = re.match(r"\s*distinct\b", text[start:end], re.I)
    items = [i.strip() for i in _split(text[start + (head.end() if head else 0):end], ",")
             if i.strip()]
    aliases = {}
    if froms:
        stop = [p for w in ("where", "group", "order", "having", "limit", "qualify", "window")
                for p in _top(w, masked, depth, froms[0])]
        clause = (text[froms[0]:min(stop)] if stop else text[froms[0]:])
        cmask, cdepth = _mask(clause)
        for m in _FROM_ITEM.finditer(cmask):
            if cdepth[m.start()] != 0:
                continue
            rel = m.group("rel")
            if rel == "(":
                return Select(items, {}, "a subquery in FROM")
            alias = m.group("alias")
            alias = alias if alias and alias.lower() not in _NOT_ALIAS else None
            aliases[(alias or rel.split(".")[-1]).lower()] = rel.lower()
    return Select(items, aliases)


def _passthrough(body):
    """The one relation a CTE body only passes through (`select * from x`, or plain
    unrenamed columns of x), else None."""
    sel = _select(body)
    if sel.why or len(set(sel.aliases.values())) != 1 or re.search(r"\b(join)\b", body, re.I):
        return None
    for item in sel.items:
        plain = _PLAIN.match(item) or re.match(r"^(?:\w+\.)?\*$", item)
        if not plain:
            return None
    return next(iter(sel.aliases.values()))


# ---------------------------------------------------------------------------
# one model -> rows
# ---------------------------------------------------------------------------
def _rule_text(tests):
    parts = []
    for name, args in tests.items():
        if name == "relationships":
            to = re.search(r"""ref\(\s*(?:['"][^'"]+['"]\s*,\s*)?['"]([\w.-]+)""", str(args.get("to", "")))
            parts.append("relationships to %s.%s" % (to.group(1) if to else args.get("to"),
                                                      args.get("field", "?")))
        elif name == "accepted_values":
            parts.append("accepted_values: %s" % ", ".join(str(v) for v in args.get("values") or []))
        else:
            parts.append(name)
    return ", ".join(parts) or "—"


def _resolve(rel, ctes, models, seen=()):
    """(name, note): the model or source `rel` stands for, following pass-through CTEs.
    `note` says why it is only the CTE's own name when it could not be followed."""
    if rel in ctes and rel not in seen:
        inner = _passthrough(ctes[rel])
        if inner is None:
            return rel, "CTE %s reshapes its input and is not traced" % rel
        return _resolve(inner, ctes, models, seen + (rel,))
    return rel, None


def _expr_sources(expr, sel, ctes, models, columns):
    """([source strings], review reason or None) for the columns an expression reads."""
    found, reason = [], None
    scrubbed = re.sub(r"'[^']*'", "''", expr)
    for alias, col in _QUALIFIED.findall(scrubbed):
        rel = sel.aliases.get(alias.lower())
        if rel is None:
            reason = reason or "%s. is not a relation in this query" % alias
            continue
        name, note = _resolve(rel, ctes, models)
        reason = reason or note
        found.append("%s.%s" % (name, col))
    bare = re.sub(r"\b\w+\.\w+\b", " ", scrubbed)
    names = [w for w in _WORD.findall(bare) if w.lower() not in _NOT_COLUMN]
    if names and len(sel.aliases) != 1:
        reason = reason or "unqualified column%s %s with %d relations in scope" % (
            "s" if len(names) > 1 else "", ", ".join(names), len(sel.aliases))
    elif names:
        rel, note = _resolve(next(iter(sel.aliases.values())), ctes, models)
        reason = reason or note
        known = columns.get(rel)
        if known:
            names = [n for n in names if n in known]
        elif len(names) > 1 and not _PLAIN.match(expr.strip()):
            reason = reason or "several bare names (%s) and no schema for %s" % (", ".join(names), rel)
            names = []
        found += ["%s.%s" % (rel, n) for n in names]
    return list(dict.fromkeys(found)), reason


def _model_rows(name, sql, table, tests, models, columns):
    """The Rows for model `name`; every column of `table` plus whatever the SELECT names."""
    declared = [c.name for c in table.columns]
    rule = lambda col: _rule_text(tests.get(col, {}))
    text = _prepare(sql) if sql is not None else None
    if text is None:
        why = "no SQL file" if sql is None else "the SQL uses Jinja this reader does not evaluate"
        return [Row(c, [], "—", rule(c), why) for c in declared]
    parsed = _ctes(text)
    if parsed is None:
        return [Row(c, [], "—", rule(c), "the WITH clause could not be read") for c in declared]
    ctes, rest = parsed
    sel = _select(rest)
    if sel.why:
        return [Row(c, [], "—", rule(c), sel.why) for c in declared]
    rows, named, star_rel = [], set(), None
    for item in sel.items:
        star = re.match(r"^(?:(\w+)\.)?\*$", item)
        if star:
            alias = (star.group(1) or "").lower()
            rel = sel.aliases.get(alias) if alias else (next(iter(sel.aliases.values()))
                                                         if len(sel.aliases) == 1 else None)
            star_rel = _resolve(rel, ctes, models)[0] if rel else None
            if star_rel is None:
                rows.append(Row("*", [], "—", "—", "SELECT * with more than one relation in scope"))
            continue
        alias_m = _AS.match(item)
        expr, target = (alias_m.group(1), alias_m.group(2)) if alias_m else (item, None)
        plain = _PLAIN.match(expr.strip())
        target = target or (plain.group(2) if plain else None)
        sources, review = _expr_sources(expr, sel, ctes, models, columns)
        if target is None:
            rows.append(Row("(unnamed)", sources, " ".join(expr.split()), "—",
                            "an expression with no alias: its column name is up to the warehouse"))
            continue
        named.add(target.lower())
        copy = bool(plain) and len(sources) == 1
        transform = ("copy" if copy and sources[0].split(".")[-1] == target
                     else "rename" if copy else " ".join(expr.split()))
        rows.append(Row(target, sources, transform, rule(target), review))
    for col in declared:
        if col.lower() in named:
            continue
        if star_rel:
            note = None
            if columns.get(star_rel) and col not in columns[star_rel]:
                note = "%s does not declare %s in its schema.yml" % (star_rel, col)
            rows.append(Row(col, ["%s.%s" % (star_rel, col)], "copy (via *)", rule(col), note))
        else:
            rows.append(Row(col, [], "—", rule(col), "declared in schema.yml but not in the SELECT"))
    return rows


# ---------------------------------------------------------------------------
# the report
# ---------------------------------------------------------------------------
def _cell(text):
    return " ".join(str(text).split()).replace("|", "\\|")


def _depth(model, upstream, seen=()):
    ups = [u for u in upstream.get(model, ()) if u not in seen]
    return 1 + max([_depth(u, upstream, seen + (model,)) for u in ups], default=-1)


def mapping_markdown(project_dir, title=None):
    """The source-to-target mapping of the dbt project in `project_dir`, as Markdown.

    One section per model, upstream models first. Deterministic: one project, one text."""
    # implements: REQ-DATAMODEL-909
    tables, lineage, sql, tests = read_dbt_project(project_dir)
    models = {t.name for t in tables}
    columns = {t.name: {c.name for c in t.columns} for t in tables if t.columns}
    upstream = {}
    for model, up in lineage:
        upstream.setdefault(model, []).append(up)
    order = sorted(tables, key=lambda t: (_depth(t.name, upstream), t.name))
    out = ["# Source-to-target mapping" + (" — %s" % title if title else ""), "",
           "Built from each model's SQL and the tests in its schema.yml. A source marked "
           "**needs review** could not be traced by this reader: read that model's SQL.", ""]
    for table in order:
        rows = _model_rows(table.name, sql.get(table.name), table, tests.get(table.name, {}),
                           models, columns)
        out += ["## %s" % table.name, ""]
        if upstream.get(table.name):
            out += ["Built from: " + ", ".join("`%s`" % u for u in sorted(upstream[table.name])), ""]
        if not rows:
            out += ["_No columns: this model has no schema.yml entry and no readable SELECT._", ""]
            continue
        out += ["| Target column | Source | Transformation | Rule |", "|---|---|---|---|"]
        for r in rows:
            src = ", ".join("`%s`" % s for s in r.sources) or "—"
            if r.review:
                src += " **needs review** — " + r.review
            out.append("| `%s` | %s | %s | %s |" % (_cell(r.target), _cell(src),
                                                   _cell(r.transform), _cell(r.rule)))
        out.append("")
    return "\n".join(out)
