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
- Every drawing call takes its position, colour and text setting as one `at`, one `paint` and one `font` value. [[REQ-EXCALIDRAW-853]] details the behaviour.
- `Scene` exposes connector helpers and a `.save(basename, out_dir)` that writes both a `.excalidraw` scene and a self-contained `.html` viewer once, deterministically when seeded. [[REQ-EXCALIDRAW-845]] details the behaviour.
- The `.html` viewer carries the Excalidraw runtime inside it, so it opens with no network; [[REQ-EXCALIDRAW-854]] states the two modes.

## Cases
CASE-1
  Given  a `Scene` with at least one `box` and one `arrow`
  When   `.save()` is called
  Then   both `<basename>.excalidraw` and `<basename>.html` are written and the
         `.excalidraw` file parses as valid JSON with `type: "excalidraw"`

CASE-2
  Given  two `box` shapes placed at overlapping coordinates
  When   `.save()` is called with the default `Gates()`
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
- `Scene` in `plugin/skills/excalidraw-diagram/scripts/excalidraw_engine/scene.py`,
  assembled from one mixin per call family (`shapes.py`, `connectors.py`,
  `arrange.py`, `annotate.py`, `pack.py`, `checks.py`, `gates.py`) over the shared
  state in `canvas.py`. `excalidraw_builder.py` beside the package is the stable
  import name and the command line.

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
- `Scene` exposes layout helpers: `arrange` and its three forms `row`,
  `column`, `grid`, plus `enclose`, `lane`, `pipeline`, `section`, `align`,
  `distribute`.
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
- `.save(basename, out_dir, gates)` writes both `<basename>.excalidraw` (the
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
  Given  `excalidraw_builder.py` and every module of `excalidraw_engine/`
  When   their imports are inspected
  Then   every imported module belongs to the Python standard library or to
         `excalidraw_engine` itself


--------------------


---
id: REQ-EXCALIDRAW-853
status: confirmed
level: code
layer: feature
owner: Alex
satisfies: [ARCH-EXCALIDRAW-030]
---

# The three call values: at, paint and font

## Description
> Every drawing call takes the same few values — where a thing goes, how it is
> painted, how its text is set — so learning one call teaches the rest. Each value
> travels as one object instead of four loose arguments, which keeps a width from
> landing where a height belongs and a 1.x keyword from being silently ignored.

Every bullet below is binding.
- A call takes its position as one `at` value: a `Rect`, an `(x, y, w, h)`
  tuple, or an `(x, y)` point. A point on a shape call takes the shape's own
  default size.
- A call takes its colour as one `paint` value and its text setting as one
  `font` value. A bare colour string stands for a `Paint` and a bare number for a
  `Font` size. A `Font` field left unset keeps the calling method's own default.
- An `arrange()` item or cell carrying an option name `box()` does not accept
  raises `ValueError` that lists the accepted names.

## Cases
CASE-1 — the three forms of `at` place a shape identically
  Given  a `Rect(10, 20, 170, 64)`, the tuple `(10, 20, 170, 64)`, and the point
         `(10, 20)` given to `process()`, whose default size is 170 x 64
  When   each places one shape in its own scene
  Then   the three shape elements carry the same x, y, width and height

CASE-2 — a shorthand value means what the full object would
  Given  a caller writing `paint="blue"` and `font=20` on `box()`, and `font=Font(20)`
         on `label()`
  When   the elements are built
  Then   the box has blue's fill and 20px text, and the label keeps its grey colour

CASE-3 — a mistyped option is refused, not ignored
  Given  a 1.x-style item `{"text": "a", "fill": "blue"}` passed to `row()`
  When   the row is placed
  Then   `ValueError` is raised naming `fill` and listing the accepted names

## Context
**Notes**
- A bare paint string is the element's natural colour: a shape's fill, a
  connector's stroke. That is why `paint="red"` on an arrow colours its line.

**Current implementation**
- `Paint` and `Font` in
  `plugin/skills/excalidraw-diagram/scripts/excalidraw_engine/style.py`, `Rect` and
  `as_rect()` in `excalidraw_engine/geometry.py`, and item validation in
  `excalidraw_engine/arrange.py`.
- `CasesExcalidrawValues` in
  `plugin/skills/excalidraw-diagram/scripts/test_excalidraw.py`.


--------------------


---
id: REQ-EXCALIDRAW-854
status: confirmed
level: code
layer: feature
owner: Alex
satisfies: [ARCH-EXCALIDRAW-030]
---

# The viewer carries its renderer

## Description
> A viewer that fetches its renderer when opened is not self-contained: it fails on a
> plane, in an air-gapped review, or the day the CDN moves the file. It also tells a
> third party who is reading the diagram. So the page ships the renderer inside it, and
> the small CDN page becomes the explicit exception rather than the default.

Every bullet below is binding.
- The viewer page inlines the vendored Excalidraw runtime, its React pair and its
  fonts, so opening it issues no network request.
- `offline=False`, the CLI's `--cdn`, writes the page that loads that runtime from the
  pinned CDN path instead.
- A vendored runtime that is incomplete makes the builder warn and emit the CDN page.
- The runtime is vendored, never downloaded: the builder still imports no HTTP client.

## Cases
CASE-1 — the default page loads nothing remote
  Given  a scene saved with no viewer options
  When   the written `.html` is inspected
  Then   no `script` or `link` tag in its markup carries an `http` source, and the
         fonts are present as `data:` URIs

CASE-2 — the CDN page stays available on request
  Given  the same scene
  When   it is saved with `offline=False` or rendered with `--cdn`
  Then   the page links the pinned unpkg build and is an order of magnitude smaller

CASE-3 — a missing runtime degrades loudly
  Given  a vendored runtime whose files are absent
  When   a viewer page is built with the default options
  Then   the CDN page is written and a `WARNING [viewer]` line names the fallback

CASE-4 — the asset path never falls back to the CDN
  Given  an offline page
  When   `window.EXCALIDRAW_ASSET_PATH` is read
  Then   it is a truthy local path, because the bundle reads it as
         `EXCALIDRAW_ASSET_PATH || <unpkg>` and an empty string would fetch

## Context
**Notes**
- The lazily imported `vendor-*.js` chunk (2.96 MB) is deliberately not vendored. A
  scene renders identically without it. The Mermaid dialog needs it, and `--cdn` serves
  that case.

**Current implementation**
- `plugin/skills/excalidraw-diagram/scripts/excalidraw_engine/assets.py` and the
  vendored files in `excalidraw_engine/runtime/`, inlined by `_runtime()` and
  `html_page()` in `excalidraw_engine/viewer.py`.
- `CasesOfflineViewer` in
  `plugin/skills/excalidraw-diagram/scripts/test_excalidraw.py`.
