---
id: REQ-DATAMODEL-902
status: confirmed
level: code
layer: feature
owner: Alex
satisfies: [ARCH-DATAMODEL-036]
---

# A role, a confidence and a reason for every table

## Description
> A heuristic that is wrong without saying why costs the reader's trust in everything
> else on the page. Each table gets a role from weighed evidence, and the evidence is
> written next to the role so a wrong call can be seen and argued with.

Every bullet below is binding.
- `classify_tables(tables)` returns, for every table, a role of fact, dimension, bridge or unknown, a confidence from 0 to 1 and a reason.
- The reason lists the evidence behind the role: name prefix, foreign keys out, numeric measures, tables that reference it and descriptive columns.
- A table with several foreign keys out and numeric measures leans fact; a table that others reference and that holds descriptive columns leans dimension.
- The name prefix is one piece of evidence, so a schema without prefixes is classified from structure.
- Confidence grows with the winner's lead over the runner-up.
- Confidence grows with the amount of evidence, and reaches 1 only with eight points or more.
- A table whose best score is below three, or ties for first, is unknown with confidence 0; a staging prefix such as `stg_` is always unknown.
- `graph_from_tables()` fills each node by role, adds the role and confidence to its label, and lists in the legend only the roles in use.

## Cases
CASE-1 — accuracy on the test set
  Given  every table of the demo, clean and no-prefix schemas with the role a modeller expects
  When   `classify_tables()` is run on each schema
  Then   at least ninety percent of the tables get the expected role

CASE-2 — structure alone is enough
  Given  a shop schema whose tables carry no `fact_` or `dim_` prefix
  When   `classify_tables()` is run
  Then   the sales table is a fact, the customers table is a dimension, and no reason cites a prefix

CASE-3 — every role is explained
  Given  any classified table
  When   its classification is read
  Then   the reason is not empty and the confidence lies between 0 and 1

CASE-4 — no evidence means unknown
  Given  a table with one key and one text column, and a staging table shaped like a fact
  When   `classify_tables()` is run
  Then   both are unknown with confidence 0, and the reason says why

CASE-5 — colour and legend follow the role
  Given  a schema holding only facts and dimensions
  When   `graph_from_tables()` is called
  Then   nodes are filled fact or dimension, and the legend holds those two roles only

CASE-6 — confidence reflects lead and evidence
  Given  a table with strong evidence and no rival, and one with thin evidence
  When   `classify_tables()` is run
  Then   the first has confidence 1, and the second has a lower one

## Context
**Notes**
- Confidence is the winner's lead over the runner-up, as a share of the winner's score, times
  the winner's score over eight (at most 1). Two tables that both win clearly differ when one
  rests on three points and the other on eight.
- A table with only key columns is a bridge by structure but may be a factless fact; the
  reason says so.

**Current implementation**
- `classify_tables()` in
  `plugin/skills/excalidraw-diagram/scripts/excalidraw_engine/classify.py`.
- `TestClassify` in `plugin/skills/excalidraw-diagram/scripts/test_data_model.py`.
