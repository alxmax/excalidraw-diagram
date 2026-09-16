---
id: ARCH-EXCALIDRAW-034
status: confirmed
level: architecture
layer: feature
owner: Alex
milestone: v1.1.0
depends_on: [ARCH-EXCALIDRAW-030, ARCH-EXCALIDRAW-031]
satisfies: [SYS-DIAGRAM-001]
---

# Graph auto-layout — a diagram from ids and edges alone

## Description
> Writing a generator gives a caller full control of the layout, and costs an
> afternoon of choosing coordinates. Someone who wants a picture of a fifteen-node
> flow in twenty seconds pays that price for control they did not ask for, and the
> quality gates make it worse: they are excellent at refusing a bad layout and no
> help at all in proposing a good one. So the builder computes the coordinates
> itself from a description of what connects to what, and the gates judge the
> result exactly as they judge a hand-placed one.

Every bullet below is binding.
- `Scene.pack(nodes, edges, groups, at, options)` places a directed graph whose description carries no
  coordinates, and returns the scene id of every node it placed.
  [[REQ-EXCALIDRAW-851]] details the behaviour.
- A layout `pack()` produces passes the same gates a hand-written generator's does.
  Passing is the definition of a finished layout: a run that places every node and
  leaves a shape sitting on another one has failed.
- The CLI reaches `pack()` through `scene --from-json`, so a caller never has to
  write Python to get a diagram. [[REQ-EXCALIDRAW-850]] details that verb.

## Cases
CASE-1 — a described graph with groups and a feedback edge lays out cleanly
  Given  a 13-node graph with two groups, one feedback edge and one edge that
         skips a layer, none of them carrying coordinates
  When   `pack()` runs over it, once with `PackOptions(direction="LR")` and once
         with `"TB"`
  Then   in both orientations all seven inspection checks return empty

CASE-2 — a second graph of a different shape lays out cleanly too
  Given  a differently shaped graph: two feedback edges at different spans, one
         forward edge that skips a layer, and no groups
  When   `pack()` runs over it in both orientations
  Then   all seven inspection checks return empty, because a layout that only
         works on the graph it was written against is not a layout

CASE-3 — the degenerate shapes are laid out, not crashed on
  Given  a 200-node chain, two disconnected components, an isolated node, and a
         12-way fan-out that rejoins
  When   `pack()` runs over each
  Then   each is placed with all seven checks empty and none of them exhausts
         the recursion limit

CASE-4 — a graph that cannot be laid out is refused, and says why
  Given  a description the builder cannot place: no nodes, a repeated id, an
         empty id, an edge naming a node that does not exist, a self-edge, or a
         direction it does not know
  When   `pack()` runs
  Then   it raises `ValueError` naming what is wrong

## Context
**Notes**
- Barycenter ordering, the classic second pass, minimises crossings between
  *edges*. `check_arrow_crossings()` measures something else: an edge cutting
  through a *box*. Ordering therefore reduces the problem without closing it, and
  the routing pass is what actually keeps the gate empty — an edge whose straight
  line would cut a third box is routed instead of drawn.
- A routed connector leaves through the gap between rows rather than the side of
  its box. A bound arrow carries its label at exactly the height of a box's side,
  and no gate would catch a line drawn through that text: `check_text_overlaps()`
  excludes bound labels by design.

**Current implementation**
- `pack()`, the `_PackRun` steps (`layers`, `measure`, `place`, `enclose`,
  `connect`, `_route`) and the pure graph functions `back_edges`, `layer_of`,
  `by_barycenter` in `plugin/skills/excalidraw-diagram/scripts/excalidraw_engine/pack.py`.
- `CasesExcalidraw034` in
  `plugin/skills/excalidraw-diagram/scripts/test_excalidraw.py`.

**Links**
- Depends on: ARCH-EXCALIDRAW-030 (the Scene API it places shapes with) and
  ARCH-EXCALIDRAW-031 (the gates that judge the result).


--------------------


---
id: REQ-EXCALIDRAW-851
status: confirmed
level: code
layer: feature
owner: Alex
satisfies: [ARCH-EXCALIDRAW-034]
---

# pack(): layering, ordering, and routing what will not go straight

## Description
> `pack()` turns a list of nodes and a list of edges into placed shapes. It
> assigns every node to a layer by how deep it sits in the flow, orders the nodes
> inside each layer to keep connected ones near each other, places them, and then
> decides one edge at a time whether a straight arrow would be readable. The last
> decision is the one that matters: an edge that would cut through a box is routed
> around the diagram instead.

Every bullet below is binding.

**How it places things**
- `pack()` assigns each node a layer by longest path from the sources, over the
  graph with its cycle-closing edges removed. The computation is iterative, so a
  chain of any length is layered without touching the recursion limit.
- `pack()` orders the nodes within each layer by the mean position of their
  neighbours in the layer before and after, sweeping four times. A node with no
  neighbour there keeps the place it had.
- `pack()` keeps the members of a declared group adjacent in their layer, so the
  frame drawn around them holds them and nothing else.
- `pack()` sizes every box to its own label, and widens the gap between two layers
  to fit the widest label on an edge crossing it.

**How it connects things**
- `pack()` draws an edge as a bound arrow only when both its ends sit in
  neighbouring layers and its straight centre-to-centre line clears every other
  box. Every other edge is routed.
- A routed edge leaves its box through the gap between rows, crosses the diagram
  in the empty strip between two layers, runs past the diagram in a lane of its
  own, and returns the same way. Each routed edge gets its own lane.
- `pack()` raises `ValueError` for a description it cannot lay out: no nodes, a
  duplicate id, an empty id, an edge naming an unknown node, a self-edge, or a
  direction other than `"LR"` or `"TB"`.

## Cases
CASE-1 — a back edge becomes a routed connector, never a straight arrow
  Given  a three-node cycle
  When   `pack()` lays it out
  Then   the two forward edges are bound arrows and the cycle-closing edge is an
         unbound routed connector with more than two points

CASE-2 — layering a 200-node chain does not recurse
  Given  200 nodes chained one to the next
  When   `pack()` lays them out
  Then   every node is placed, no check reports an offender, and no
         `RecursionError` is raised

CASE-3 — a long edge label widens its gap instead of crowding its arrow
  Given  two nodes joined by an edge labelled with a phrase wider than the
         default gap
  When   `pack()` lays them out
  Then   `check_arrow_label_fit()` returns empty

CASE-4 — a node's declared role and shape reach the element
  Given  a node declaring `kind: "decision"` and a fill naming a declared role
  When   `pack()` places it
  Then   the scene contains a diamond element carrying that role's colour

CASE-5 — an unlayoutable description raises ValueError
  Given  six broken descriptions. One has no nodes. One repeats an id. One has an
         empty id. One names an unknown node in an edge. One carries a self-edge.
         One asks for a direction that is neither `"LR"` nor `"TB"`
  When   `pack()` runs on each
  Then   `ValueError` is raised every time

## Context
**Notes**
- The routing channel sits 34px from the column it hugs. That number clears three
  things at once: no box is ever placed in a layer gap, `enclose()` draws its
  frame 24px out so a line there would trace a frame border, and an arrow's label
  is centred in the gap with at least 48px free at each end.
- `_straight_hits()` is the id-level form of `check_arrow_crossings()`. The gate
  reports by label, which is not unique; `pack()` needs ids, and both read the
  same geometry so the layout cannot disagree with the check that judges it.

**Current implementation**
- `pack()`, `_PackRun` and the graph functions `back_edges`, `layer_of`,
  `by_barycenter` in `plugin/skills/excalidraw-diagram/scripts/excalidraw_engine/pack.py`; `_straight_hits()` in
  `plugin/skills/excalidraw-diagram/scripts/excalidraw_engine/checks.py`.
- `CasesExcalidraw034` in
  `plugin/skills/excalidraw-diagram/scripts/test_excalidraw.py`.
