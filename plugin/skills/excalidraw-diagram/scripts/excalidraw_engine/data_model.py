# implements: ARCH-DATAMODEL-036
"""Tables -> the graph description scene_from_spec() already draws.

This module adds no layout and no renderer: it turns the tables ddl.py parsed into the
coordinate-free graph (one node per table, one edge per foreign-key relationship) that
`scene --from-json` takes, so pack() places it and the gates judge it unchanged.

An edge runs from the table holding the foreign key to the table it references, so a
fact points at its dimensions and the arrow reads "belongs to".
"""

import os

from . import explain
from .classify import classify_tables
from .dbt import read_dbt
from .mapping import mapping_markdown
from .ddl import parse_ddl
from .review import review_tables
from .roles import parse_roles
from .spec import scene_from_spec


NOTE = explain.NOTE_KEY          # a note's fill, and its legend text
NOTE_WIDTH = 40                  # a review note wraps wide, not as a 12-line tower
ROLE_COLOURS = {"fact": "blue", "dimension": "green", "bridge": "violet", "unknown": "grey"}
NOTE_COLOUR = "yellow"


def graph_from_tables(tables, title=None, seed=1, columns=False, overrides=None,
                      lineage=()):
    """A graph description (a dict for scene_from_spec) for `tables`.

    Several foreign keys from one table to the same target become one edge labelled
    with all their columns; a foreign key to a table the script never defines is left
    out of the graph (it has no node to point at) and is listed by `unresolved_fks`.
    `seed` fixes the hand-drawn look, so one schema always gives the same bytes.

    Each node is coloured by the role classify_tables() gives its table, labelled with
    that role and its confidence, and the glossary holds the reason for every role.
    Every finding of review_tables() becomes an amber note joined to its table.

    `columns=True` lists each table's columns under its name, marking the PK and FK ones;
    `overrides` is a {table: role} map that replaces the classifier's answer.

    `lineage` is a list of (model, upstream) pairs (dbt's ref()); each is drawn as a dashed
    line labelled "ref" from the model to what it is built from, unless a foreign key
    already joins that pair the same way."""
    # implements: REQ-DATAMODEL-901
    # implements: REQ-DATAMODEL-904
    # implements: REQ-DATAMODEL-905
    # implements: REQ-DATAMODEL-907
    # implements: REQ-DATAMODEL-911
    known = {t.name for t in tables}
    roles = classify_tables(tables, overrides)
    # An arrow carries its key column's name only where two labels cannot meet: with several
    # facts sharing dimensions the arrows cross and their labels pile up, and with columns
    # listed in the boxes the FK lines already name the key.
    named = not columns and sum(c.role == "fact" for c in roles.values()) <= 1
    right = _right_side(tables, roles)
    edges, seen = [], {}
    for table in tables:
        for fk in table.foreign_keys:
            if fk.ref_table not in known:
                continue
            label = ", ".join(fk.columns)
            key = (table.name, fk.ref_table)
            if key in seen:
                if named:
                    seen[key]["label"] += ", " + label
            else:
                seen[key] = {"src": table.name, "dst": fk.ref_table}
                if table.name in right:
                    seen[key]["flip"] = True
                if named:
                    seen[key]["label"] = label
                edges.append(seen[key])
    drawn = [(a, b) for a, b in lineage if (a, b) not in seen]
    edges += [{"src": a, "dst": b, "dashed": True, "label": "ref"} for a, b in drawn]
    nodes = [{"id": t.name, "label": _label(t, roles[t.name], columns),
              "fill": explain.role_key(roles[t.name].role)} for t in tables]
    used = {c.role for c in roles.values()}
    issues = review_tables(tables, roles)
    for n, issue in enumerate(issues, 1):
        note = _free_id("review-note-%d" % n, known)
        nodes.append({"id": note, "label": explain.note_text(issue.rule, issue.message),
                      "fill": NOTE, "max_chars": NOTE_WIDTH})
        edges.append({"src": issue.table, "dst": note, "dashed": True})
    legend = {explain.role_key(r): col for r, col in ROLE_COLOURS.items() if r in used}
    if issues:
        legend[NOTE] = NOTE_COLOUR
    subtitle = (explain.SUBTITLE + ("" if named or columns else explain.SUBTITLE_NO_COLUMNS)
                + (explain.SUBTITLE_LINEAGE if drawn else "")
                + (explain.SUBTITLE_NOTES if issues else ""))
    spec = {"nodes": nodes, "edges": edges, "seed": seed, "subtitle": subtitle,
            "roles": legend,
            "glossary": explain.glossary(tables, roles, issues, columns, bool(drawn))}
    if title:
        spec["title"] = title
    return spec


def _right_side(tables, roles):
    """The names of every second fact-like table (a fact or a bridge), which pack() lays out on
    the far side of the dimensions they share. Alternating puts two facts one on each side of
    their dimensions, so their arrows do not cross; fewer than two fact-like tables change
    nothing."""
    # implements: REQ-DATAMODEL-913
    fact_like = [t.name for t in tables if roles[t.name].role in ("fact", "bridge")]
    return set(fact_like[1::2]) if len(fact_like) >= 2 else set()


def _free_id(wanted, taken):
    """`wanted`, lengthened until no table is already called that."""
    while wanted in taken:
        wanted += "_"
    return wanted


def _label(table, classification, columns):
    """The node text: the name, the role's icon and badge, then one line per column when
    asked."""
    badge = "%s %s" % (explain.ICON[classification.role], _badge(classification))
    lines = [table.name, badge]
    if columns:
        pk = set(table.primary_key)
        fk = {c for key in table.foreign_keys for c in key.columns}
        lines += [explain.column_line(c.name, c.name in pk, c.name in fk) for c in table.columns]
    return "\n".join(lines)


def _badge(classification):
    """'fact · 92%'; 'fact · set by you' when the roles file chose it; just
    'unknown' when no role earned enough evidence."""
    if classification.overridden:
        return "%s · set by you" % classification.role
    if classification.role == "unknown":
        return "unknown"
    return "%s · %d%%" % (classification.role, round(classification.confidence * 100))


def unresolved_fks(tables):
    """[(table, ForeignKey)] for every foreign key whose target table is not defined."""
    known = {t.name for t in tables}
    return [(t, fk) for t in tables for fk in t.foreign_keys if fk.ref_table not in known]


class DrawOptions(object):
    """How scene_from_ddl() draws and writes; the loose keyword arguments it takes, as one
    value in the manner of PackOptions.

    name: the output basename (default: the input's own name). offline: the viewer's renderer
    (see html_page). svg: also write the .svg. columns: list each table's columns in its node.
    roles_path: a roles file (see roles.parse_roles) that overrides the classification."""

    __slots__ = ("name", "offline", "svg", "columns", "roles_path")

    def __init__(self, name=None, offline=None, svg=False, columns=False, roles_path=None):
        self.name, self.offline, self.svg, self.columns = name, offline, svg, columns
        self.roles_path = roles_path


class DbtOptions(DrawOptions):
    """DrawOptions plus the two a dbt project adds. draw_lineage: draw each ref() as a dashed
    "ref" line. mapping_path: also write the source-to-target mapping to that path."""

    __slots__ = ("mapping_path", "draw_lineage")

    def __init__(self, mapping_path=None, draw_lineage=False, **drawing):
        DrawOptions.__init__(self, **drawing)
        self.mapping_path, self.draw_lineage = mapping_path, draw_lineage


def _draw(tables, lineage, source, stem, out_dir, opts):
    """Overrides, graph and scene for already-parsed `tables`; `source` names the input in
    an error."""
    overrides = None
    if opts.roles_path:
        with open(opts.roles_path, encoding="utf-8") as fh:
            try:
                overrides = parse_roles(fh.read())
            except ValueError as exc:
                raise ValueError("%s: %s" % (opts.roles_path, exc))
    try:
        spec = graph_from_tables(tables, title=opts.name or stem, columns=opts.columns,
                                 overrides=overrides, lineage=lineage)
    except ValueError as exc:
        raise ValueError("%s: %s" % (opts.roles_path or source, exc))
    return scene_from_spec(spec, out_dir, name=opts.name or stem, offline=opts.offline,
                           svg=opts.svg)


def scene_from_ddl(ddl_path, out_dir=None, **options):
    """Read a DDL file, draw its tables, and save the scene and viewer.

    The output name is `name`, else the file's stem; the directory defaults to the
    file's own. `options` are DrawOptions' fields (name, offline, svg, columns, roles_path);
    an unknown one, such as a dbt-only one, is a TypeError. Returns what scene_from_spec()
    returns. Raises ValueError, naming the file at fault, when the DDL or
    the roles file cannot be read or a gate fails."""
    # implements: REQ-DATAMODEL-901
    opts = DrawOptions(**options)
    with open(ddl_path, encoding="utf-8") as fh:
        try:
            tables = parse_ddl(fh.read())
        except ValueError as exc:
            raise ValueError("%s: %s" % (ddl_path, exc))
    stem = os.path.splitext(os.path.basename(ddl_path))[0]
    return _draw(tables, (), ddl_path, stem, out_dir or os.path.dirname(ddl_path) or ".", opts)


def scene_from_dbt(project_dir, out_dir=None, **options):
    """Read a dbt project (see dbt.read_dbt), draw its models, and save the scene.

    Takes the options scene_from_ddl() does, plus `draw_lineage` and `mapping_path` (see
    DbtOptions). The
    output name is `name`, else the project folder's; the directory defaults to the current
    one, never the project itself. `draw_lineage` also draws each ref() as a dashed "ref"
    line; it is off by default because on a real project those lines outnumber the foreign
    keys and bury them. `mapping_path` also writes the source-to-target mapping (see
    mapping.py) there, as UTF-8 Markdown, and only once the scene has passed every gate; its
    path is appended to the returned paths."""
    # implements: REQ-DATAMODEL-907
    # implements: REQ-DATAMODEL-910
    # implements: REQ-DATAMODEL-912
    opts = DbtOptions(**options)
    tables, lineage = read_dbt(project_dir)
    stem = os.path.basename(os.path.abspath(project_dir))
    report = (mapping_markdown(project_dir, title=opts.name or stem)
              if opts.mapping_path else None)
    paths = _draw(tables, lineage if opts.draw_lineage else (), project_dir, stem,
                  out_dir or ".", opts)
    if report is None:
        return paths
    with open(opts.mapping_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(report)
    return tuple(paths) + (opts.mapping_path,)
