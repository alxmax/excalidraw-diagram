---
id: REQ-DATAMODEL-907
status: confirmed
level: code
layer: feature
owner: Alex
satisfies: [ARCH-DATAMODEL-036]
---

# A dbt project read as tables, foreign keys and lineage

## Description
> dbt has no foreign keys, so a diagram of a dbt project has to say which of its two
> statements it is drawing. A `relationships` test says one column points at another: a
> foreign key. A `ref()` says one model is built from another: lineage. Keeping them apart
> lets the classifier and the review work on the first and the picture show the second.

Every bullet below is binding.
- `read_dbt(dir)` returns one table per model, sorted by name, for every model that has a `.sql` file or a `schema.yml` entry under `models/`, or under the folder itself without one.
- A column carrying both a `unique` and a `not_null` test is the model's primary key; a `data_type` becomes the column type, and is empty otherwise.
- A `relationships` test with a `ref()` target becomes a foreign key from that column; a `source()` target is skipped.
- `read_dbt()` returns lineage as sorted `(model, upstream)` pairs for each `ref()` in a model's SQL whose target is another model, ignoring comments.
- `graph_from_tables(lineage=...)` draws each lineage pair as a dashed line, unless a foreign key already joins that pair in the same direction.
- `read_dbt()` raises `ValueError` naming the file for an unreadable `schema.yml`, and naming the folder when it holds no model.
- The `data-model` command takes `--from-dbt <project>` in place of `--from-ddl`, and exactly one of the two.

## Cases
CASE-1 — models from SQL and schema files
  Given  a project with five models, three staging and two marts, in `.sql` and `schema.yml` files
  When   `read_dbt()` reads it
  Then   five tables come back sorted by name

CASE-2 — keys and types from the schema
  Given  a model whose `order_id` has `unique` and `not_null` tests and whose `amount` has a `data_type`
  When   `read_dbt()` reads it
  Then   `order_id` is the primary key, the type is `numeric`, and a column with `not_null` is not nullable

CASE-3 — a relationships test is a foreign key
  Given  a column with a `relationships` test to `ref('customers')` on `customer_id`
  When   `read_dbt()` reads it
  Then   the model gains a foreign key from that column to `customers.customer_id`

CASE-4 — lineage from ref() only
  Given  SQL that calls `ref()` on models, on an unknown name, and inside comments
  When   `read_dbt()` reads it
  Then   lineage holds only the refs to real models, in sorted pairs, with none from comments or `source()`

CASE-5 — lineage is dashed and never doubles a foreign key
  Given  lineage pairs, one of which a foreign key already joins in the same direction
  When   `graph_from_tables()` is called with them
  Then   the others are dashed lines, and the joined pair keeps its single foreign-key edge

CASE-6 — unreadable input is refused
  Given  an empty folder, and a `schema.yml` using a YAML anchor
  When   `read_dbt()` reads each
  Then   `ValueError` names the folder for the first and the file and line for the second

CASE-7 — the command draws a dbt project
  Given  the fixture dbt project
  When   `data-model --from-dbt` runs, and again with no input or with both inputs
  Then   the first writes both files through every gate, and the others are usage errors

## Context
**Notes**
- Without `data_type` a model has no typed columns, so it is classified from its name and
  keys alone and may come out unknown. `--roles` corrects it.
- Only `models/` is read; seeds, snapshots and sources are not drawn.

**Current implementation**
- `read_dbt()` in `plugin/skills/excalidraw-diagram/scripts/excalidraw_engine/dbt.py`;
  `scene_from_dbt()` and `graph_from_tables()` in `data_model.py`; the flag in `cli.py`.
- `TestReadDbt` in `plugin/skills/excalidraw-diagram/scripts/test_data_model.py`.
