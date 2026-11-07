---
id: REQ-DATAMODEL-914
status: confirmed
level: code
layer: feature
owner: Alex
satisfies: [ARCH-DATAMODEL-036]
---

# Three kinds of line and one frame for what is outside the star

## Description
> A box with no arrow reads as a table someone forgot to join, and two lines that look alike
> read as one kind of relationship. The picture sets aside what the rules could not place,
> and keeps a detour round the diagram from looking like a review note's link.

Every bullet below is binding.
- A table classified unknown that no foreign key and no ref() line joins is drawn inside one frame labelled "outside the star".
- An unknown table that something joins is drawn in the star as before, and a schema with no such table has no frame.
- The glossary defines "Outside the star" when the frame is drawn and not otherwise.
- A connector that pack() routes round the diagram is grey, and dashed only when its own edge is dashed.

## Cases
CASE-1 — an unplaced table is framed
  Given  the demo schema, whose staging table no key joins
  When   the graph is built
  Then   one group labelled "outside the star" holds that table and no other, and the glossary defines the term

CASE-2 — nothing unplaced, no frame
  Given  the clean schema, which has no unknown table
  When   the graph is built
  Then   the graph has no groups and the glossary has no "Outside the star" row

CASE-3 — a joined unknown table stays in the star
  Given  a dbt project whose unknown models are joined to one another
  When   the graph is built
  Then   no group is drawn

CASE-4 — a detour does not look like a review link
  Given  a back edge that is not dashed and one that is, both routed round the diagram
  When   the graph is packed
  Then   both are grey, and only the second has a dashed stroke

## Context
**Notes**
- Seen on a real dbt project: three staging models drawn as isolated boxes, and a routed foreign
  key drawn the same grey dashed way as a review note's link.
- The routed line keeps its grey so a detour still differs from a straight arrow.

**Current implementation**
- `_outside_star()` in `plugin/skills/excalidraw-diagram/scripts/excalidraw_engine/data_model.py`,
  the term in `explain.py`, and `_route()` in `pack.py`.
- `TestOutsideTheStar` in `plugin/skills/excalidraw-diagram/scripts/test_data_model.py`.
