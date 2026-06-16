# Excalidraw format & builder reference

Read this when you need detail beyond the SKILL.md cheat-sheet: the on-disk
format, every builder argument, and the gotchas that make a scene import cleanly.

## Contents
1. The `.excalidraw` file format
2. Element types and required fields
3. Bindings (text-in-shape, arrows-between-shapes)
4. Full builder API
5. Common mistakes

---

## 1. The `.excalidraw` file format

A scene is a single JSON object:

```json
{
  "type": "excalidraw",
  "version": 2,
  "source": "excalidraw-diagram-skill",
  "elements": [ /* flat, ordered list — array order = z-order */ ],
  "appState": { "gridSize": null, "viewBackgroundColor": "#ffffff" },
  "files": {}
}
```

- `elements` is **flat** — there is no nesting. A box "inside" a frame is just a
  separate element whose coordinates happen to fall within the frame's, drawn
  later in the array so it paints on top.
- Array order is paint order. The builder inserts `frame()` elements at the
  front so children drawn afterwards sit on top.
- Importing into excalidraw.com runs a `restore` pass that fills in any missing
  cosmetic fields (e.g. fractional z-index strings), so the builder deliberately
  omits those — do not add them by hand.

## 2. Element types and required fields

Every element shares this base (the builder's `_base`):

```
id, type, x, y, width, height, angle,
strokeColor, backgroundColor, fillStyle, strokeWidth, strokeStyle,
roughness, opacity, groupIds, frameId, roundness,
seed, version, versionNonce, isDeleted, boundElements, updated, link, locked
```

Type-specific:

- **rectangle / ellipse / diamond** — `roundness: {type: 3}` rounds rectangle
  corners; ellipses/diamonds use `null`.
- **text** — adds `text, fontSize, fontFamily, textAlign, verticalAlign,
  containerId, originalText, lineHeight, autoResize`.
  `fontFamily`: `1` = hand-drawn (Excalifont/Virgil), `2` = normal (Helvetica),
  `3` = code (Cascadia).
- **arrow / line** — adds `points` (relative to the element's x,y),
  `startBinding, endBinding, startArrowhead, endArrowhead, lastCommittedPoint,
  elbowed`. `roundness: {type: 2}` makes a multi-point arrow curve.

`roughness`: `1` = hand-drawn sketch, `0` = clean/architect. Set once via
`Scene(sketch=True)` (or the back-compat `Scene(hand_drawn=True)`, which also
switches the font to Excalifont).

## 3. Bindings

Two relationships need **two-way** references or Excalidraw renders them wrong.

**Text inside a shape.** The text element gets `containerId` = the shape's id,
`textAlign:"center"`, `verticalAlign:"middle"`; the shape gets
`boundElements: [{type:"text", id:<textId>}]`. The builder's `box/ellipse/
diamond` do this automatically.

**Arrow between two shapes.** The arrow gets
`startBinding:{elementId, focus, gap}` and `endBinding:{…}`; **each** connected
shape gets `boundElements: [{type:"arrow", id:<arrowId>}]`. On load Excalidraw
re-routes the arrow from the bindings, so the arrow's own `points` only need to
be a reasonable initial straight line — the builder computes border-to-border
points so it already looks right before any interaction.

`focus` (−1..1) shifts where the arrow meets the shape; `gap` is the pixel gap.
The builder uses `focus:0` and an auto-clamped `gap` (≤14px, shrunk when the two
shapes are close so the endpoints never cross).

## 4. Full builder API

```python
Scene(font="normal", sketch=False, hand_drawn=None,
      background="#ffffff", seed=None, roles=None)
```
`font`: `"normal"` (Helvetica), `"hand"` (Excalifont), or `"code"`. `sketch=True`
gives rough/hand-drawn outlines. `hand_drawn=True` is a back-compat alias that
sets `font="hand", sketch=True`. `seed=<int>` makes every id, seed, nonce and
timestamp deterministic, so the same scene re-saves to a byte-identical file (use
it when the diagram is committed). `roles={"agent": "violet", …}` declares
semantic fill aliases (see *Legend, swimlane & semantic roles* below).

### Shapes with a centered label — return a node id
```python
s.box(text, x, y, w=160, h=70, *,
      fill=None, stroke=None, shape="rectangle",
      font_size=16, font_color=None, group=None, container=False)
s.ellipse(text, x, y, w=170, h=110, **kw)   # shape="ellipse"
s.diamond(text, x, y, w=160, h=90,  **kw)   # shape="diamond"
```
- `fill` / `stroke` / `font_color`: hex (`"#a5d8ff"`) or palette name.
- `text` may contain `\n`; the box does not auto-grow, so size `w/h` for it.
- `container=True` exempts the shape from the overlap check — use it for an
  ellipse/box that wraps other shapes (e.g. an "agent" ellipse around inner
  boxes).
- Returns the **node id** — pass it to `arrow()`.

### Container frame — return a node id
```python
s.frame(x, y, w, h, *, fill=None, stroke=None, dashed=False, group=None)
```
Drawn behind everything added so far; always exempt from the overlap check.
Place child boxes on top at coordinates inside it.

### ISO 5807 flowchart shapes — return a node id
Thin `box()` aliases pre-sized for flowcharts; each accepts the same kwargs as
`box()` (`fill`, `font_size`, `w`, `h`, …):
```python
s.process(text, x, y)              # rectangle           — a step
s.terminator(text, x, y)           # stadium             — start / end
s.decision(text, x, y)             # diamond             — a branch
s.data(text, x, y)                 # parallelogram       — input / output
s.predefined_process(text, x, y)   # framed rectangle    — a sub-routine
s.preparation(text, x, y)          # hexagon             — setup / init
s.connector(text, x, y)            # small circle        — on-page connector
```

### Poster helpers — stacked sections + a workflow band
```python
s.section(title, *, x=40, gap=70, size=18) -> y    # heading below ALL content
s.pipeline(steps, x, y, *, gap=44, row_h=None,
           font_size=14, connect=True) -> [ids]    # horizontal flowchart band
```
- **`section`** places a left-aligned heading below everything drawn so far and
  returns the `y` to start this region's shapes — removes manual `bounds()` math
  when stacking regions top→bottom.
- **`pipeline`** lays out steps left→right on a shared midline and (default)
  chains bound arrows. Each `step` is `"text"`, `(text, kind)`,
  `(text, kind, fill)`, or a dict `{text, kind, fill, w, h, label, font_size}`.
  `kind` is any ISO shape verb (`process` default, `decision`, `terminator`,
  `data`, `predefined_process`, `preparation`, `connector`, `box`). A step's
  `label` becomes the label on its outgoing arrow. Returns node ids — index them
  for `route_under()` feedback loops.

### Auto-layout — place groups without coordinate math
```python
s.row(items, x, y, *, w=160, h=70, gap=40, fill=None,
      font_size=16, shape="rectangle", connect=False)   # -> [ids] left→right
s.column(items, x, y, *, w=160, h=70, gap=30, ...)       # -> [ids] top→down
s.grid(items, x, y, cols, *, w=160, h=70,
       gap_x=40, gap_y=30, ...)                          # -> [ids] cols-wide grid
s.enclose(ids, *, pad=24, dashed=True, fill=None,
          stroke=None, label=None)                       # -> frame id around ids
```
- `items`: each entry is `"text"`, `(text, fill)`, or a dict of `box()` options
  (`text`, `fill`, `stroke`, `shape`, `font_size`, `w`, `h`, `container`).
- `connect=True` (row/column) chains consecutive nodes with arrows.
- `grid` uses a uniform cell size so rows/columns align (per-item `w/h` ignored).
- `enclose` measures the bounding box of `ids`, pads it, and draws a `frame()`
  behind them; call it *after* placing the nodes. Optional centered caption.

### Legend, swimlane & semantic roles
```python
s.role(name, colour)                       # declare one semantic fill alias
Scene(roles={"agent": "violet", ...})      # or declare them up-front
s.legend(entries=None, x=0, y=0, *, title="Legend",
         swatch=18, gap=10, font_size=13, pad=14)    # -> frame id
s.glossary(entries, x, y, *, title="Glossary",
           font_size=13, pad=14)                     # -> frame id
s.lane(ids, label, *, pad=24, fill=None, stroke=None,
       font_size=14, label_color="black")            # -> frame id
```
- A **role** maps a name to a palette colour, so `box(fill="agent")` resolves via
  `roles` then the palette. Unknown names fall through to the palette unchanged,
  so existing colour names keep working.
- **`legend`** renders a colour key. Pass `entries=[(label, colour), …]`, or omit
  it to use the Scene's `roles`. Required whenever colour encodes meaning, so a
  reader with no context can decode the diagram.
- **`glossary`** renders a term→meaning key (`entries=[(term, meaning), …]`) to
  decode acronyms / project jargon; its content is overlap-checked like any box.
- **`lane`** is a thin `enclose()` wrapper drawing a solid frame with a top-left
  header — a swimlane for one stage/actor.

### Post-placement adjustment
```python
s.align(ids, axis="center_x")              # left|right|center_x|top|bottom|center_y
s.distribute(ids, axis="x", *, gap=40)     # even spacing along "x" or "y"
```
Both mutate already-placed nodes in place (moving each shape *and* its bound
label) and keep the overlap bookkeeping in sync, so a later `save()` still
validates the adjusted layout. Use them to tidy a hand-placed cluster instead of
recomputing coordinates.

### Layout sanity
```python
s.check_overlaps(min_px=1.0)            # -> [(label_a, label_b), ...] overlapping nodes
s.check_arrow_crossings(threshold=12)   # -> [(src, dst, crossed), ...] arrows over a box
s.check_legend_coverage()               # -> [fill, ...] colours used but not in the legend
s.check_text_overflow()                 # -> [...] boxes whose text spills outside the shape
s.check_text_overlaps()                 # -> [(a, b), ...] captions/labels overlapping
s.bounds()                              # -> (min_x, min_y, max_x, max_y) over all shapes
```
All checks ignore containers. `save()` runs every one of them (see *Save* below):
overlaps always raise; the other four print a warning by default and raise at
`"error"`. `bounds` is handy for stacking several diagrams in one scene (start the
next region below `max_y`).

### Free-standing text
```python
s.title(text, x, y, *, size=28, color=None, align="left")  # heading
s.label(text, x, y, *, size=12, color="grey", align="center")  # caption
```

### Arrows & connectors
```python
s.arrow(src, dst, *, label=None, dashed=False, color=None,
        start=None, end="arrow", curve=False)        # bound, node→node
s.free_arrow(p0, p1, *, label=None, dashed=False,
             color=None, start=None, end="arrow")     # unbound, point→point
s.path(points_abs, *, label=None, dashed=False, color=None,
       start=None, end="arrow")                       # unbound polyline (waypoints)
s.route_under(src, dst, *, drop=70, label=None,
              color="grey", dashed=True)               # feedback: drop below the row
```
Arrowheads: `None, "arrow", "dot", "triangle", "bar"`. `curve=True` bends a
bound arrow (useful for a loop-back). `p0/p1` and each `points_abs` entry are
`(x, y)` tuples.
- **`path`** draws an unbound connector through explicit waypoints — use it for a
  routed line that must avoid boxes (a feedback loop that goes down, across, and
  back up). Its `label` gets a white knock-out panel so it reads cleanly over the
  line. That panel is **overlap-checked**: if the label lands on a box its white
  fill would hide it, so `save()` raises just as for any overlapping shape —
  shorten the label or move the waypoints until it sits in clear space.
- **`route_under`** is the common feedback case prebuilt: it leaves the bottom of
  `src`, runs `drop` px below the row, and returns into the bottom of `dst`.

### Save
```python
s.save(basename, out_dir=".", allow_overlap=False,
       crossing_check="warn", legend_check="warn",
       overflow_check="warn", text_overlap_check="warn")
# -> (path.excalidraw, path.html)
```
Always re-runs `check_overlaps()` first (so a post-placement `align()`/
`distribute()` can't ship a hidden overlap), then raises `ValueError` if two
non-container nodes overlap (lists the labels). The four `*_check` gates each take
`"warn"` (default, prints) or `"error"` (raises):
- `crossing_check` — a bound arrow runs through an unrelated box.
- `legend_check` — a fill colour is used but missing from the `legend()` (fires
  only once a legend is rendered).
- `overflow_check` — bound text is bigger than its box (spills outside).
- `text_overlap_check` — two captions / labels overlap each other.

For a ship-quality diagram pass all four at `"error"`. Fix the layout, mark a
wrapper `container=True`, or pass `allow_overlap=True` to bypass the overlap raise.

### Palette
`grey, red, orange, yellow, green, teal, blue, indigo, violet, pink`
(+ `black`, `transparent`). Each maps to Excalidraw's stroke + light-fill pair.

## 5. Common mistakes

- **Cramming text** — boxes don't auto-resize; long text overflows. Keep labels
  to a few words, size the box, or push detail into a `label()` beneath.
- **Forgetting frames go behind** — use `frame()` (auto z-order), not a plain
  `box()`, for containers, or children get hidden.
- **Hand-editing the JSON** — let the builder own seeds/nonces/bindings.
  Editing them by hand is the usual cause of "arrow not attached" on import.
- **Overlapping coordinates** — there's no collision detection. Lay out on a
  mental grid; ~90–120px between boxes, ~40px frame padding.
- **Mixed reading directions** in one region — pick one (L→R or top-down) and
  separate other regions with a `title()`.

## HTML viewer notes

`save()` also writes a `<basename>.html` that renders the scene via the official
Excalidraw UMD build pinned to `@excalidraw/excalidraw@0.17.6` + React 18.2 from
unpkg. It needs a network connection on first load (to fetch the CDN bundle and
fonts); if the CDN is unreachable it shows a fallback with a download button.
The embedded scene and the standalone `.excalidraw` file are always offline-safe.
To change the pinned version, edit `_html_page()` in `excalidraw_builder.py`
(note: 0.18+ is ESM-only and won't work with the UMD `<script>` approach).
