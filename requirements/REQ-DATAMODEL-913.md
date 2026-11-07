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
> factless table pushed its arrows into long loops round the diagram. Putting a fact on the
> other side of the dimensions lets each arrow run straight into the dimension next to it,
> which is how a star schema is drawn when there is more than one star. Which facts go
> across is measured on the drawn layout, not assumed to alternate.

Every bullet below is binding.
- With two or more fact-like tables, a fact or a bridge, the layout tries each choice of which sit on the far side of the dimensions and keeps the one with the fewest routed edges, then the fewest crossing pairs.
- The first fact-like table stays on the near side, because a mirrored layout costs the same.
- Every second fact-like table in schema order is the baseline: it wins any tie, and it is the answer when more than eight fact-like tables would have to be searched.
- The only fact-like table, when there is one, is laid out as before.
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
  Then   at most one edge is routed and at most nine pairs of arrows cross, and that dimension shares its column with the others

CASE-4 — the search beats alternating
  Given  two fact-like tables for which alternating sides routes an edge round the diagram
  When   the graph is built and drawn
  Then   neither table is flipped, and the drawing has no routed edge and one crossing pair

CASE-5 — too many to search
  Given  more than eight fact-like tables
  When   the sides are chosen
  Then   every second one is flipped, and no candidate layout is drawn to measure it

## Context
**Notes**
- Measured on the order process: routed edges 3 to 1 and crossing pairs 11 to 10 by alternating,
  then 10 to 9 by the search. With many facts crossings are a property of the graph, so the
  layout reduces them and does not remove them. The two-fact case goes from one crossing pair
  to none.
- On the no-prefix shop, two fact-like tables, alternating gave one routed edge and three
  crossing pairs, and the search gives none and one.
- Routed edges weigh more than crossings because a line looping round the diagram is the
  worse defect.

**Current implementation**
- `best_right()` in `plugin/skills/excalidraw-diagram/scripts/excalidraw_engine/sides.py`;
  `_flipped()` and `graph_from_tables()` in `data_model.py`; the layout in `pack.py`.
- `TestStarLayout` in `plugin/skills/excalidraw-diagram/scripts/test_data_model.py`.
