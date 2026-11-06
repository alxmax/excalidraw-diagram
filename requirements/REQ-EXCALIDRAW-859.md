---
id: REQ-EXCALIDRAW-859
status: confirmed
level: code
layer: feature
owner: Alex
satisfies: [ARCH-EXCALIDRAW-034]
---

# Flipped edges: a source laid out beyond its target

## Description
> Two sources that point at the same targets cannot both sit before them without their
> arrows crossing. An edge marked `flip` is laid out the other way round, so one source sits
> before the targets and the other after, while every arrow still runs from source to target
> and so still says what it said.

Every bullet below is binding.
- `pack()` lays out an edge with `"flip": true` as if it ran from its target to its source, so the source sits in a later layer than the target.
- The arrow of a flipped edge is still drawn from its source to its target.
- A node that only flipped edges reach is placed in the layer just before its nearest flipped source, not in the first layer.
- A graph with no flipped edge is laid out exactly as it was before the key existed.

## Cases
CASE-1 — a source beyond its targets
  Given  two sources pointing at the same two targets, one of them flipped
  When   `pack()` lays them out
  Then   the flipped source sits after the targets, the other before, and every arrow stays bound

CASE-2 — the arrow keeps its direction
  Given  an edge from B to C marked `flip`
  When   `pack()` draws it
  Then   the arrow starts at B and ends at C

CASE-3 — a target only flipped edges reach
  Given  a node that only a flipped edge points at
  When   `pack()` lays out the graph
  Then   it sits in the same layer as the other targets, with its arrow bound and straight

CASE-4 — nothing changes without the key
  Given  one graph with no `flip` key and the same graph with `flip` set to false
  When   `pack()` lays out each
  Then   the two scenes are identical

## Context
**Notes**
- `flip` is for the `"straight"` edge style. A bus draws a trunk beside its source, so a flipped
  edge is left out of it.

**Current implementation**
- `_laid()` and `_pull_flipped_targets()` in
  `plugin/skills/excalidraw-diagram/scripts/excalidraw_engine/pack.py`.
- `CasesExcalidrawFlip` in `plugin/skills/excalidraw-diagram/scripts/test_excalidraw.py`.
