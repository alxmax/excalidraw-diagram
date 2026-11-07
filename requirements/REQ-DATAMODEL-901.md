---
id: REQ-DATAMODEL-901
status: confirmed
level: code
layer: feature
owner: Alex
satisfies: [ARCH-DATAMODEL-036]
---

# Tables as the graph the builder already draws

## Description
> The module adds no layout and no renderer. It describes the tables as nodes and
> foreign keys as edges, and the existing `pack()` and gates do the rest, so a data
> model is judged by the same bar as every other diagram.

Every bullet below is binding.
- `graph_from_tables(tables)` returns a graph description with one node per table and one edge per foreign-key relationship.
- `graph_from_tables()` merges several foreign keys between the same two tables into one edge labelled with all their columns.
- `graph_from_tables()` leaves out a foreign key whose target table is not defined, and `unresolved_fks()` lists it.
- `scene_from_ddl(path)` and the `data-model --from-ddl` command save the scene through every gate.
- `graph_from_tables()` sets a fixed seed, so one schema always produces byte-identical files.
- The `data-model` command takes `--name`, which sets the diagram's title and its output file name instead of the input's own name.

## Cases
CASE-1 — one node per table, one edge per relationship
  Given  the demo schema and a table with two foreign keys to one dimension
  When   `graph_from_tables()` is called
  Then   there is one node per table, and the two keys share one edge labelled with both columns

CASE-2 — an unresolved foreign key is listed, not drawn
  Given  a table whose foreign key names a table the script never defines
  When   `graph_from_tables()` and `unresolved_fks()` are called
  Then   the graph holds no edge for it, and `unresolved_fks()` returns that key

CASE-3 — the scene passes every gate
  Given  the demo, clean and no-prefix schemas
  When   `scene_from_ddl()` or the `data-model` command is run
  Then   both files are written without a failed gate, and a call with no input is a usage error

CASE-4 — the output is byte-stable
  Given  one DDL file
  When   `scene_from_ddl()` is run twice
  Then   the two `.excalidraw` files are identical byte for byte

CASE-5 — the title is chosen, not inherited
  Given  a dbt project in a folder with an unhelpful name
  When   the `data-model` command is run with `--name Orders`
  Then   the files are called Orders and the title reads Orders

## Context
**Current implementation**
- `graph_from_tables()`, `unresolved_fks()` and `scene_from_ddl()` in
  `plugin/skills/excalidraw-diagram/scripts/excalidraw_engine/data_model.py`; the verb in `cli.py`.
- `TestGraph`, `TestScene` and `TestCli` in
  `plugin/skills/excalidraw-diagram/scripts/test_data_model.py`.
