---
id: REQ-DATAMODEL-903
status: confirmed
level: code
layer: feature
owner: Alex
satisfies: [ARCH-DATAMODEL-036]
---

# Five review rules over the classified tables

## Description
> Drawing a model is what every other tool does. What this one adds is a second reader
> that says where the model is weak. A rule fires only on evidence it can quote, so a
> clean schema stays silent: an invented warning costs more trust than a missed one.

Every bullet below is binding.
- `review_tables(tables, roles)` returns issues ordered by table, each naming its table and its rule.
- The `grain` rule flags a fact table that has no primary key.
- The `surrogate-key` rule flags a dimension whose key is missing, composite or named like a source id instead of `*_key` or `*_sk`.
- The `scd2` rule flags a dimension with attributes that change over time but no `valid_from` and `valid_to`, or with only one of them.
- The `orphan-fk` rule flags a foreign key to a table, or to a column, that does not exist.
- The `snowflake` rule flags a dimension referenced by another dimension, and calls the chain deep from two levels down; an outrigger shared by two dimensions is not flagged.

## Cases
CASE-1 — every planted problem is found
  Given  the demo schema with a missing SCD2 history, a source-id key, a needless snowflake and an orphan key
  When   `review_tables()` is run
  Then   exactly those four issues are returned, each on its table

CASE-2 — a clean schema raises no alarm
  Given  the demo schema with every problem fixed
  When   `review_tables()` is run
  Then   no issue is returned

CASE-3 — grain
  Given  a fact with no primary key, and the same fact with one
  When   `review_tables()` is run on each
  Then   only the first raises a `grain` issue

CASE-4 — surrogate key
  Given  dimensions keyed by a source id, by a composite, by nothing, and by `*_key` or `*_sk`
  When   `review_tables()` is run
  Then   the first three raise `surrogate-key` and the last does not

CASE-5 — SCD type 2
  Given  a dimension with a `city` column, one with half a history, and ones with a full history or stable attributes
  When   `review_tables()` is run
  Then   the first two raise `scd2` and the others do not

CASE-6 — orphan foreign key
  Given  a foreign key to a missing table, one to a missing column, and one to an existing target
  When   `review_tables()` is run
  Then   the first two raise `orphan-fk` and the third does not

CASE-7 — snowflake
  Given  a sub-dimension, a three-level chain, and an outrigger shared by two dimensions
  When   `review_tables()` is run
  Then   the sub-dimension is flagged, the chain end is called deep, and the shared outrigger is not flagged

## Context
**Notes**
- The `scd2` rule reads column names, so it is a heuristic: it names the columns it suspects.
- `snowflake` flags the sub-dimension, not the dimension that points at it, because that
  is the table a modeller would fold away.

**Current implementation**
- `review_tables()` and its five rules in
  `plugin/skills/excalidraw-diagram/scripts/excalidraw_engine/review.py`.
- `TestReview` in `plugin/skills/excalidraw-diagram/scripts/test_data_model.py`.
