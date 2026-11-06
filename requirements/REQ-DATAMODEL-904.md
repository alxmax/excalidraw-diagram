---
id: REQ-DATAMODEL-904
status: confirmed
level: code
layer: feature
owner: Alex
satisfies: [ARCH-DATAMODEL-036]
---

# Review findings explained and drawn as amber notes

## Description
> A finding is only useful if the reader can check it and find the table it is about. So
> every issue carries a sentence saying why, and every issue is drawn on the page beside
> the table it concerns, where a reviewer would put a sticky note.

Every bullet below is binding.
- Each issue from `review_tables()` carries a message that states the cause in a sentence, not a bare label.
- `graph_from_tables()` draws each issue as an amber note joined to its table by a dashed line.
- `graph_from_tables()` adds the review-note colour to the legend only when at least one issue exists.

## Cases
CASE-1 — every issue is explained
  Given  the issues found in the demo schema
  When   their messages are read
  Then   each message is a sentence stating the cause, not a bare label

CASE-2 — issues become amber notes
  Given  the demo schema
  When   `graph_from_tables()` is called
  Then   it gains four review notes, each joined to its table by a dashed edge

CASE-3 — a clean schema draws no note
  Given  the demo schema with every problem fixed
  When   `graph_from_tables()` is called
  Then   no review note is drawn and the legend has no review-note entry

## Context
**Current implementation**
- `graph_from_tables()` in
  `plugin/skills/excalidraw-diagram/scripts/excalidraw_engine/data_model.py`.
- `TestReview` in `plugin/skills/excalidraw-diagram/scripts/test_data_model.py`.
