---
id: ARCH-EXCALIDRAW-030
status: confirmed
level: architecture
layer: feature
owner: Alex
milestone: v1.0.0
satisfies: [SYS-DIAGRAM-001]
---

# Excalidraw scene builder — core API

## Description
> The excalidraw-diagram skill needs a stdlib-only Python library that turns
> declarative shape and arrow declarations into a valid Excalidraw scene file
> and a self-contained HTML viewer, with no external dependencies, so the skill
> can be vendored into any environment without install friction.

Every bullet below is binding.
- `Scene` exposes shape primitives, ISO 5807 flowchart aliases, layout helpers, and annotation helpers for building a diagram declaratively. [[REQ-EXCALIDRAW-844]] details the behaviour.
- `Scene` exposes connector helpers and a `.save(basename, out_dir)` that writes both a `.excalidraw` scene and a self-contained `.html` viewer once, deterministically when seeded. [[REQ-EXCALIDRAW-845]] details the behaviour.

## Cases
CASE-1
  Given  a `Scene` with at least one `box` and one `arrow`
  When   `.save()` is called
  Then   both `<basename>.excalidraw` and `<basename>.html` are written and the
         `.excalidraw` file parses as valid JSON with `type: "excalidraw"`

CASE-2
  Given  two `box` shapes placed at overlapping coordinates
  When   `.save()` is called without `allow_overlap=True`
  Then   a `ValueError` is raised naming the overlapping shapes

CASE-3
  Given  `Scene(seed=42)` with identical shape declarations run twice
  When   both outputs are compared byte-for-byte
  Then   they are identical

CASE-4
  Given  `.save()` has already been called once on a `Scene`
  When   `.save()` is called again
  Then   a `RuntimeError` is raised

CASE-5
  Given  a `pipeline([...])` call with step dicts
  When   `.save()` is called
  Then   the resulting scene contains connected flowchart nodes with no
         overlapping shapes

## Context
**Notes**
- The authoritative usage reference is `plugin/skills/excalidraw-diagram/SKILL.md`.
- `save()` overlap detection raises on any two non-container shapes that
  overlap (co-ordinates checked after all shapes are added).

**Current implementation**
- `class Scene` and all shape/layout/arrow methods in
  `plugin/skills/excalidraw-diagram/scripts/excalidraw_builder.py`.

**Links**
- Used by: ARCH-EXCALIDRAW-031, ARCH-EXCALIDRAW-032


--------------------


---
id: REQ-EXCALIDRAW-844
status: confirmed
level: code
layer: feature
owner: Alex
satisfies: [ARCH-EXCALIDRAW-030]
---

# Shape, layout, and annotation vocabulary

## Description
> A diagram is built by declaring shapes and arranging them, not by computing pixel
> coordinates by hand. `Scene` gives a caller shape primitives, ISO 5807 flowchart
> aliases (so a flowchart reads like a flowchart, not a pile of boxes), layout helpers
> that place shapes without overlap, and annotation helpers for titles and labels.

Every bullet below is binding.
- `Scene()` produces a valid Excalidraw JSON scene (schema version 2) with
  a `type: "excalidraw"` root and a `elements` list compatible with
  excalidraw.com import.
- `Scene` exposes shape primitives: `box`, `ellipse`, `diamond`, `frame`.
- `Scene` exposes ISO 5807 flowchart aliases: `process`, `terminator`,
  `decision`, `data`, `predefined_process`, `preparation`, `connector`.
- `Scene` exposes layout helpers: `row`, `column`, `grid`, `enclose`,
  `lane`, `pipeline`, `section`, `align`, `distribute`.
- `Scene` exposes annotation helpers: `title`, `label`, `legend`,
  `glossary`, `role`.

## Cases
CASE-1 — Scene() produces an excalidraw.com-importable JSON scene
  Given  a `Scene` with at least one shape added
  When   `.save()` writes the `.excalidraw` file
  Then   it parses as JSON with `type: "excalidraw"` and an `elements` list

CASE-2 — each shape primitive adds one element of its kind
  Given  a `Scene`
  When   `box`, `ellipse`, `diamond` and `frame` are each called once
  Then   the scene gains one element of each corresponding Excalidraw type

CASE-3 — ISO 5807 aliases produce their underlying shapes
  Given  a `Scene`
  When   `process`, `terminator`, `decision`, `data`, `predefined_process`, `preparation` and `connector` are each called
  Then   each adds an element without raising, using its mapped primitive shape

CASE-4 — layout helpers place shapes without overlap
  Given  three boxes
  When   `row([...])` arranges them
  Then   the resulting coordinates place them side by side with no overlapping pair

CASE-5 — annotation helpers attach text without raising
  Given  a `Scene` with one shape
  When   `title`, `label`, `legend`, `glossary` and `role` are each called
  Then   each adds its text element and `.save()` still succeeds


--------------------


---
id: REQ-EXCALIDRAW-845
status: confirmed
level: code
layer: feature
owner: Alex
satisfies: [ARCH-EXCALIDRAW-030]
---

# Connectors and the save() contract

## Description
> Shapes alone are not a diagram until they are linked, and a caller needs one
> predictable moment where the scene becomes files on disk. Connector helpers bind
> arrows to shape ids; `.save()` writes the `.excalidraw` scene and its HTML viewer
> together, exactly once, and — when the scene was seeded — byte-identically on every
> run, so a regenerated diagram never shows as a spurious diff.

Every bullet below is binding.
- `Scene` exposes connector helpers: `arrow`, `free_arrow`, `path`,
  `route_under`.
- `.save(basename, out_dir)` writes both `<basename>.excalidraw` (the
  scene JSON) and `<basename>.html` (a self-contained viewer) in one call and
  raises `RuntimeError` if called more than once on the same `Scene`.
- `Scene(seed=<int>)` produces byte-identical output across re-runs.
- The builder has no external dependencies — stdlib only.

## Cases
CASE-1 — connector helpers link two shapes
  Given  two boxes already placed in a `Scene`
  When   `arrow(a, b)` is called
  Then   the scene gains an arrow element bound to both shapes' ids

CASE-2 — one .save() call writes both output files
  Given  a `Scene` with at least one shape
  When   `.save("demo", out_dir)` is called
  Then   both `demo.excalidraw` and `demo.html` exist in `out_dir` after the single call

CASE-3 — a fixed seed reproduces byte-identical output
  Given  the same shape declarations built twice with `Scene(seed=42)`
  When   each is saved to its own file
  Then   the two `.excalidraw` files are byte-for-byte identical

CASE-4 — the builder imports only the standard library
  Given  `excalidraw_builder.py`
  When   its top-level imports are inspected
  Then   every imported module belongs to the Python standard library

