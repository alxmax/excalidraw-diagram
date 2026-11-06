---
id: REQ-DATAMODEL-905
status: confirmed
level: code
layer: feature
owner: Alex
satisfies: [ARCH-DATAMODEL-036]
---

# Columns inside the table nodes, on request

## Description
> A table drawn as a name hides what a modeller most wants to check: which column is the
> key, which ones point elsewhere, which ones are measures. Listing the columns answers
> that, but it makes every node taller, so it is off until asked for.

Every bullet below is binding.
- `graph_from_tables(tables, columns=True)` lists every column of a table under its name and role badge, in the order the DDL declares them.
- A primary-key column starts with `PK`.
- A foreign-key column starts with `FK`.
- A column that is both a primary key and a foreign key carries both marks.
- Without `columns`, a node holds only the table name and its role badge.
- The `data-model` command takes `--columns` and passes it through to the same graph builder.

## Cases
CASE-1 — off by default
  Given  the demo schema
  When   `graph_from_tables()` is called without `columns`
  Then   each node label is the table name and its role badge, and nothing else

CASE-2 — columns in order with key marks
  Given  a fact table with a primary key, three foreign keys and three measures
  When   `graph_from_tables(columns=True)` is called
  Then   its label lists all seven columns in declared order, with `PK` or `FK` where they apply

CASE-3 — the flag reaches the drawing
  Given  the demo schema
  When   `data-model --from-ddl` is run with `--columns`
  Then   the scene passes every gate and holds a text element listing `PK order_line_key`

## Context
**Notes**
- A column line is the name only, not its type: types would widen every node for a fact the
  modeller can read in the DDL.
- Node text keeps the line breaks it is given; `fit_text()` wraps each line on its own.

**Current implementation**
- `graph_from_tables()` and `_label()` in
  `plugin/skills/excalidraw-diagram/scripts/excalidraw_engine/data_model.py`; the flag in `cli.py`.
- `TestColumns` in `plugin/skills/excalidraw-diagram/scripts/test_data_model.py`.
