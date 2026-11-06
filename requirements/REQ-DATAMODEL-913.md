---
id: REQ-DATAMODEL-913
status: confirmed
level: code
layer: feature
owner: Alex
satisfies: [ARCH-DATAMODEL-036]
---

# Facts sharing dimensions on opposite sides of them

## Description
> Two facts that share dimensions drew their arrows across each other, and a bridge or
> factless table pushed its arrows into long loops round the diagram. Putting every second
> fact on the other side of the dimensions lets each arrow run straight into the dimension
> next to it, which is how a star schema is drawn when there is more than one star.

Every bullet below is binding.
- With two or more fact-like tables, a fact or a bridge, every second one in schema order is laid out on the far side of the dimensions.
- The first fact-like table, and the only one when there is one, is laid out as before.
- The foreign-key arrow of a laid-out table still runs from that table to the dimension.

## Cases
CASE-1 — two facts, no crossing
  Given  two fact tables that share two dimensions
  When   the graph is built and drawn
  Then   the second fact is flipped, and the drawing has no crossing pair of arrows and no routed edge

CASE-2 — one fact, nothing flipped
  Given  a schema with one fact table
  When   the graph is built
  Then   no edge carries `flip`

CASE-3 — many facts, measured
  Given  an order process of five fact-like tables and eight dimensions, one dimension reached only by a flipped bridge
  When   it is drawn
  Then   at most one edge is routed and at most ten pairs of arrows cross, and that dimension shares its column with the others

## Context
**Notes**
- Measured on the order process before and after: routed edges 3 to 1, crossing pairs 11 to 10.
  With many facts crossings are a property of the graph, so the layout reduces them and does not
  remove them. The two-fact case goes from one crossing pair to none.
- The rule alternates in schema order and does not search for the assignment with the fewest
  crossings.

**Current implementation**
- `_right_side()` and `graph_from_tables()` in
  `plugin/skills/excalidraw-diagram/scripts/excalidraw_engine/data_model.py`; the layout in `pack.py`.
- `TestStarLayout` in `plugin/skills/excalidraw-diagram/scripts/test_data_model.py`.
