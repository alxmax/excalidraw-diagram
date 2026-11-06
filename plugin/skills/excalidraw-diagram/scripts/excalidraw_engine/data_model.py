# implements: ARCH-DATAMODEL-036
"""Tables -> the graph description scene_from_spec() already draws.

This module adds no layout and no renderer: it turns the tables ddl.py parsed into the
coordinate-free graph (one node per table, one edge per foreign-key relationship) that
`scene --from-json` takes, so pack() places it and the gates judge it unchanged.

An edge runs from the table holding the foreign key to the table it references, so a
fact points at its dimensions and the arrow reads "belongs to".
"""

import os

from .classify import classify_tables
from .ddl import parse_ddl
from .review import review_tables
from .spec import scene_from_spec


NOTE = "review note"
ROLE_COLOURS = {"fact": "blue", "dimension": "green", "bridge": "violet", "unknown": "grey",
                NOTE: "yellow"}
SUBTITLE = ("Each arrow runs from a table to the table its foreign key references. "
            "Under each name: the role and how sure the classification is.")
NOTE_SUBTITLE = " Amber notes on dashed lines are review findings on the table they touch."


def graph_from_tables(tables, title=None, seed=1):
    """A graph description (a dict for scene_from_spec) for `tables`.

    Several foreign keys from one table to the same target become one edge labelled
    with all their columns; a foreign key to a table the script never defines is left
    out of the graph (it has no node to point at) and is listed by `unresolved_fks`.
    `seed` fixes the hand-drawn look, so one schema always gives the same bytes.

    Each node is coloured by the role classify_tables() gives its table, labelled with
    that role and its confidence, and the glossary holds the reason for every role.
    Every finding of review_tables() becomes an amber note joined to its table."""
    # implements: REQ-DATAMODEL-901
    # implements: REQ-DATAMODEL-904
    known = {t.name for t in tables}
    edges, seen = [], {}
    for table in tables:
        for fk in table.foreign_keys:
            if fk.ref_table not in known:
                continue
            label = ", ".join(fk.columns)
            key = (table.name, fk.ref_table)
            if key in seen:
                seen[key]["label"] += ", " + label
            else:
                seen[key] = {"src": table.name, "dst": fk.ref_table, "label": label}
                edges.append(seen[key])
    roles = classify_tables(tables)
    nodes = [{"id": t.name, "label": t.name + "\n" + _badge(roles[t.name]),
              "fill": roles[t.name].role} for t in tables]
    used = {c.role for c in roles.values()}
    issues = review_tables(tables, roles)
    for n, issue in enumerate(issues, 1):
        note = _free_id("review-note-%d" % n, known)
        nodes.append({"id": note, "label": issue.rule + ": " + issue.message, "fill": NOTE})
        edges.append({"src": issue.table, "dst": note, "dashed": True})
    if issues:
        used.add(NOTE)
    spec = {"nodes": nodes, "edges": edges, "seed": seed,
            "subtitle": SUBTITLE + (NOTE_SUBTITLE if issues else ""),
            "roles": {r: col for r, col in ROLE_COLOURS.items() if r in used},
            "glossary": [[t.name, "%s - %s" % (roles[t.name].role, roles[t.name].reason)]
                         for t in tables]}
    if title:
        spec["title"] = title
    return spec


def _free_id(wanted, taken):
    """`wanted`, lengthened until no table is already called that."""
    while wanted in taken:
        wanted += "_"
    return wanted


def _badge(classification):
    """'fact · 92%', or just 'unknown' when no role earned enough evidence."""
    if classification.role == "unknown":
        return "unknown"
    return "%s · %d%%" % (classification.role, round(classification.confidence * 100))


def unresolved_fks(tables):
    """[(table, ForeignKey)] for every foreign key whose target table is not defined."""
    known = {t.name for t in tables}
    return [(t, fk) for t in tables for fk in t.foreign_keys if fk.ref_table not in known]


def scene_from_ddl(ddl_path, out_dir=None, name=None, offline=None, svg=False):
    """Read a DDL file, draw its tables, and save the scene and viewer.

    The output name is `name`, else the file's stem; the directory defaults to the
    file's own. Returns what scene_from_spec() returns. Raises ValueError when the DDL
    cannot be read or a gate fails."""
    # implements: REQ-DATAMODEL-901
    with open(ddl_path, encoding="utf-8") as fh:
        try:
            tables = parse_ddl(fh.read())
        except ValueError as exc:
            raise ValueError("%s: %s" % (ddl_path, exc))
    stem = os.path.splitext(os.path.basename(ddl_path))[0]
    spec = graph_from_tables(tables, title=name or stem)
    return scene_from_spec(spec, out_dir or os.path.dirname(ddl_path) or ".",
                           name=name or stem, offline=offline, svg=svg)
