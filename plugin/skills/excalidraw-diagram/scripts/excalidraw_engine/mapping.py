"""A dbt project -> a source-to-target mapping in Markdown.

For every model, one row per target column: where it comes from, what is done to it, and
which rules (the schema.yml tests) it must meet.

The source of a column is only as good as the SQL reader behind it, and that reader is a
small one: it follows a plain `select`, aliases, joins and CTEs, tracing each column through
every CTE's own SELECT to the models and source tables underneath, so a CTE is never named as
a source. A model's columns are the ones its SQL produces, followed through `*`, because
schema.yml usually lists only the columns it tests.

Anything else is NOT guessed. A union, Jinja control flow (a `{% for %}` loop), a subquery in
`from`, a CTE it cannot read, or an unqualified column no single relation is known to hold
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


_STAR = re.compile(r"^(?:(\w+)\.)?\*$")


def _star_relation(match, sel):
    """The one relation a `*` or `alias.*` stands for, or None when it is ambiguous."""
    alias = (match.group(1) or "").lower()
    if alias:
        return sel.aliases.get(alias)
    return next(iter(sel.aliases.values())) if len(sel.aliases) == 1 else None


def _split_item(item):
    """(expression, target column name or None, plain-column match) for one select item."""
    alias_m = _AS.match(item)
    expr, target = (alias_m.group(1), alias_m.group(2)) if alias_m else (item, None)
    plain = _PLAIN.match(expr.strip())
    return expr, target or (plain.group(2) if plain else None), plain


def _query(text):
    """(ctes, Select) for a model's SQL, or None when it cannot be read to the end."""
    prepared = _prepare(text)
    parsed = _ctes(prepared) if prepared is not None else None
    if parsed is None:
        return None
    ctes, rest = parsed
    sel = _select(rest)
    return None if sel.why else (ctes, sel)


class _Project(object):
    """The models of a dbt project and the columns each one produces.

    A model's columns come from its own SQL, followed through `*` and through CTEs, because
    schema.yml usually names only the columns it tests. A model whose SQL cannot be followed
    to the end yields None. A source table (a seed or a raw table) is no model, so its columns
    are never known."""

    def __init__(self, tables, sql):
        self.declared = {t.name: [c.name for c in t.columns] for t in tables}
        self.sql, self._cache = sql, {}

    def produced(self, model, seen=()):
        """The ordered column names `model` produces, or None when they cannot be known."""
        if model in self._cache:
            return self._cache[model]
        if model in seen or model not in self.declared:
            return None
        text = self.sql.get(model)
        if text is None:
            cols = self.declared[model] or None          # no SQL: only what schema.yml says
        else:
            query = _query(text)
            cols = self._select_columns(query[1], query[0], seen + (model,)) if query else None
        self._cache[model] = cols
        return cols

    def relation_columns(self, rel, ctes, seen=()):
        """The column names of relation `rel` as a query sees it: a CTE, a model, or None."""
        if rel in ctes:
            sel = _select(ctes[rel])
            if rel in seen or sel.why:
                return None
            return self._select_columns(sel, ctes, seen + (rel,))
        return self.produced(rel, seen)

    def _select_columns(self, sel, ctes, seen):
        names = []
        for item in sel.items:
            star = _STAR.match(item)
            if star:
                rel = _star_relation(star, sel)
                cols = self.relation_columns(rel, ctes, seen) if rel else None
                if cols is None:
                    return None
                names += cols
                continue
            target = _split_item(item)[1]
            if target:
                names.append(target)
        return list(dict.fromkeys(names))


def _trace(rel, col, ctes, project, seen=()):
    """([sources], transform, review) for column `col` of relation `rel`.

    A relation that is no CTE is a model or a source table, so the column is just `rel.col`.
    A CTE is followed into its own SELECT: the sources named are the models and source tables
    underneath, never the CTE itself. `transform` is the expression a CTE applied to the
    column when it did more than rename it; `review` says why a CTE could not be followed."""
    if rel not in ctes:
        return ["%s.%s" % (rel, col)], None, None
    if rel in seen:
        return [], None, "CTE %s reads itself" % rel
    sel = _select(ctes[rel])
    if sel.why:
        return [], None, "CTE %s is not traced: %s" % (rel, sel.why)
    seen, star_rel = seen + (rel,), None
    for item in sel.items:
        star = _STAR.match(item)
        if star:
            star_rel = _star_relation(star, sel) or star_rel
            continue
        expr, target, plain = _split_item(item)
        if target and target.lower() == col.lower():
            sources, review, inner = _expr_sources(expr, sel, ctes, project, seen)
            copy = bool(plain) and len(sources) == 1
            how = (inner[0] if inner else None) if copy else " ".join(expr.split())
            return sources, how, review
    if star_rel:
        return _trace(star_rel, col, ctes, project, seen)
    return [], None, "CTE %s has no column %s" % (rel, col)


def _expr_sources(expr, sel, ctes, project, seen=()):
    """([source strings], review reason or None, [inner transforms]) for the columns an
    expression reads. Each column is traced through any CTE it comes from, and a bare name
    over several relations is placed with the one relation known to hold it."""
    found, reason, inner = [], None, []

    def follow(rel, col):
        nonlocal reason
        sources, how, note = _trace(rel, col, ctes, project, seen)
        found.extend(sources)
        reason = reason or note
        if how:
            inner.append(how)

    scrubbed = re.sub(r"'[^']*'", "''", expr)
    for alias, col in _QUALIFIED.findall(scrubbed):
        rel = sel.aliases.get(alias.lower())
        if rel is None:
            reason = reason or "%s. is not a relation in this query" % alias
        else:
            follow(rel, col)
    bare = re.sub(r"\b\w+\.\w+\b", " ", scrubbed)
    names = [w for w in _WORD.findall(bare) if w.lower() not in _NOT_COLUMN]
    rels = sorted(set(sel.aliases.values()))
    cols = {r: project.relation_columns(r, ctes, seen) for r in rels} if names else {}
    for n in names:
        if len(sel.aliases) == 1:
            rel = rels[0]
            if cols[rel] is not None and n not in cols[rel]:
                continue                                # a keyword or function, not a column
            if cols[rel] is None and rel not in ctes and len(names) > 1 \
                    and not _PLAIN.match(expr.strip()):
                reason = reason or "several bare names (%s) and no schema for %s" % (
                    ", ".join(names), rel)
                break
            follow(rel, n)
            continue
        owners = [r for r in rels if cols[r] is not None and n in cols[r]]
        if len(owners) == 1 and all(cols[r] is not None for r in rels):
            follow(owners[0], n)
        else:
            reason = reason or "unqualified column %s with %d relations in scope" % (
                n, len(sel.aliases))
    return list(dict.fromkeys(found)), reason, inner


def _star_row(rel, col, ctes, project, rule):
    """The Row for column `col` that a `*` over relation `rel` brings in."""
    sources, how, note = _trace(rel, col, ctes, project)
    renamed = bool(sources) and sources[0].rsplit(".", 1)[1] != col
    return Row(col, sources, how or ("rename (via *)" if renamed else "copy (via *)"),
               rule(col), note)


def _why_unreadable(sql):
    """Why a model's SQL cannot be read at all, in a sentence."""
    if sql is None:
        return "no SQL file"
    prepared = _prepare(sql)
    if prepared is None:
        return "the SQL uses Jinja this reader does not evaluate"
    parsed = _ctes(prepared)
    return "the WITH clause could not be read" if parsed is None else _select(parsed[1]).why


def _model_rows(name, sql, table, tests, project):
    """The Rows for model `name`: every column its SELECT produces, in order, then any column
    schema.yml declares that the SQL does not produce."""
    declared = [c.name for c in table.columns]
    rule = lambda col: _rule_text(tests.get(col, {}))
    query = _query(sql) if sql is not None else None
    if query is None:
        why = _why_unreadable(sql)
        return [Row(c, [], "—", rule(c), why) for c in declared]
    ctes, sel = query
    rows, named, unknown_star = [], set(), None

    def add(row):
        rows.append(row)
        named.add(row.target.lower())

    for item in sel.items:
        star = _STAR.match(item)
        if star:
            rel = _star_relation(star, sel)
            if rel is None:
                rows.append(Row("*", [], "—", "—", "SELECT * with more than one relation in scope"))
                continue
            produced = project.relation_columns(rel, ctes)
            if produced is None:
                unknown_star = rel
            for col in produced or []:
                if col.lower() not in named:
                    add(_star_row(rel, col, ctes, project, rule))
            continue
        expr, target, plain = _split_item(item)
        sources, review, inner = _expr_sources(expr, sel, ctes, project)
        if target is None:
            rows.append(Row("(unnamed)", sources, " ".join(expr.split()), "—",
                            "an expression with no alias: its column name is up to the warehouse"))
            continue
        copy = bool(plain) and len(sources) == 1
        if copy and inner:
            transform = inner[0]
        elif copy:
            transform = "copy" if sources[0].split(".")[-1] == target else "rename"
        else:
            transform = " ".join(expr.split())
        add(Row(target, sources, transform, rule(target), review))
    for col in declared:
        if col.lower() in named:
            continue
        if unknown_star:                         # the star's columns are unknown: trust the schema
            add(_star_row(unknown_star, col, ctes, project, rule))
        else:
            add(Row(col, [], "—", rule(col),
                    "declared in schema.yml, but the SQL produces no column %s" % col))
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
    project = _Project(tables, sql)
    upstream = {}
    for model, up in lineage:
        upstream.setdefault(model, []).append(up)
    order = sorted(tables, key=lambda t: (_depth(t.name, upstream), t.name))
    out = ["# Source-to-target mapping" + (" — %s" % title if title else ""), "",
           "Built from each model's SQL and the tests in its schema.yml. A source marked "
           "**needs review** could not be traced by this reader: read that model's SQL.", ""]
    for table in order:
        rows = _model_rows(table.name, sql.get(table.name), table, tests.get(table.name, {}),
                           project)
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
