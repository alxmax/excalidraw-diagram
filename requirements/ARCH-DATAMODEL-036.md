---
id: ARCH-DATAMODEL-036
status: confirmed
level: architecture
layer: feature
owner: Alex
depends_on: [ARCH-EXCALIDRAW-030]
satisfies: [SYS-DIAGRAM-001]
---

# A data model drawn and reviewed from its SQL

## Description
> A data model with ten tables is slow to draw by hand and easy to get wrong, and the
> existing tools only draw it. This capability reads the SQL that defines the tables,
> draws them as a coordinate-free graph the builder already lays out, and says what is
> wrong with the model. Every role and every warning carries the reason it was given,
> because a label the reader cannot check is a label the reader will not trust.

Every bullet below is binding.
- The `data-model` command reads DDL with the standard library alone and turns each table, key and foreign key into a table record. [[REQ-DATAMODEL-900]]
- The graph builder turns those records into the graph description that `scene --from-json` takes, so layout and gates stay unchanged. [[REQ-DATAMODEL-901]]
- The classifier gives each table a role, a confidence and a written reason from names and structure alone. [[REQ-DATAMODEL-902]]
- The review runs five rules over the classified tables. [[REQ-DATAMODEL-903]]
- Each finding is explained in a sentence and drawn as an amber note joined to its table. [[REQ-DATAMODEL-904]]
- A table can list its columns on request. [[REQ-DATAMODEL-905]]
- A roles file overrides the classifier, and the diagram says which roles were set by hand. [[REQ-DATAMODEL-906]]
- The command also draws a dbt project: models, `relationships` tests as foreign keys and `ref()` as lineage. [[REQ-DATAMODEL-907]]
- dbt schema files are read by a YAML subset reader that refuses what it cannot read. [[REQ-DATAMODEL-908]]
- A dbt project can also produce a source-to-target mapping that marks what it cannot trace. [[REQ-DATAMODEL-909]]
- dbt lineage is drawn only on request and labelled, so it cannot bury the foreign keys. [[REQ-DATAMODEL-910]]
- The diagram explains itself in icons and plain words, so a stranger can read it. [[REQ-DATAMODEL-911]]

## Cases
CASE-1
  Given  the demo shop schema with six tables and four planted problems
  When   `data-model --from-ddl` is run on it
  Then   a `.excalidraw` scene and an `.html` viewer are written, with four amber notes

CASE-2
  Given  the same schema with every planted problem fixed
  When   `data-model --from-ddl` is run on it
  Then   the diagram shows no amber note and no review-note entry in its legend

CASE-3
  Given  a DDL script the parser cannot read
  When   `data-model --from-ddl` is run on it
  Then   the command exits non-zero and names the file and the statement, writing no output

## Context
**Notes**
- Stdlib only: the DDL reader is hand-written rather than built on a SQL library, because
  this plugin installs nothing from PyPI. A dialect it cannot read raises an error.
- This is a module of the existing plugin, not a second plugin: it emits the graph the
  builder already draws and adds no layout or renderer of its own.

**Current implementation**
- `plugin/skills/excalidraw-diagram/scripts/excalidraw_engine/data_model.py`, with
  `ddl.py`, `classify.py` and `review.py` beside it.
- `plugin/skills/excalidraw-diagram/scripts/test_data_model.py`.
