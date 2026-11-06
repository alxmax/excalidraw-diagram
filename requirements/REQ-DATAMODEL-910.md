---
id: REQ-DATAMODEL-910
status: confirmed
level: code
layer: feature
owner: Alex
satisfies: [ARCH-DATAMODEL-036]
---

# dbt lineage drawn only on request, and labelled

## Description
> On a real dbt project the `ref()` lines outnumber the foreign keys and run round the whole
> diagram, burying the model the picture is for. And a dashed lineage line looks exactly
> like the dashed line to a review note. So lineage is off until asked for, and when it is
> drawn each line says what it is.

Every bullet below is binding.
- `data-model --from-dbt` draws no lineage line unless `--lineage` is given.
- With `--lineage`, each `ref()` pair is a dashed line labelled `ref`, from the model to what it is built from.
- `--lineage` is a usage error without `--from-dbt`.
- The source-to-target mapping is unaffected by `--lineage`: it always states what each model is built from.

## Cases
CASE-1 — no lineage by default
  Given  the fixture dbt project
  When   `data-model --from-dbt` runs without `--lineage`
  Then   the scene holds no text element reading `ref`

CASE-2 — lineage on request
  Given  the same project
  When   `data-model --from-dbt` runs with `--lineage`
  Then   the scene passes every gate and holds one `ref` label for each lineage line

CASE-3 — lineage needs dbt
  Given  a DDL file
  When   `data-model --from-ddl` runs with `--lineage`
  Then   the command fails with a usage error

CASE-4 — the mapping does not depend on the flag
  Given  the fixture project and a mapping path
  When   `data-model --from-dbt --mapping` runs with and without `--lineage`
  Then   both write the same mapping text

## Context
**Notes**
- A label on a dashed line is the only thing that tells lineage from a review note, since
  edges carry no colour of their own.

**Current implementation**
- `scene_from_dbt(draw_lineage=...)` and `graph_from_tables()` in
  `plugin/skills/excalidraw-diagram/scripts/excalidraw_engine/data_model.py`; the flag in `cli.py`.
- `TestLineageFlag` in `plugin/skills/excalidraw-diagram/scripts/test_data_model.py`.
