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
`Scene(hand_drawn=…)`.

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
Scene(hand_drawn=True, background="#ffffff", seed=None)
```
`seed=<int>` makes every id, seed, nonce and timestamp deterministic, so the same
scene re-saves to a byte-identical file (use it when the diagram is committed).

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

### Layout sanity
```python
s.check_overlaps(min_px=1.0)            # -> [(label_a, label_b), ...] overlapping nodes
s.check_arrow_crossings(threshold=12)   # -> [(src, dst, crossed), ...] arrows over a box
s.bounds()                              # -> (min_x, min_y, max_x, max_y) over all shapes
```
`check_overlaps` and `check_arrow_crossings` both ignore containers. `save()`
calls both — overlaps raise, crossings print a warning. `bounds` is handy for
stacking several diagrams in one scene (start the next region below `max_y`).

### Free-standing text
```python
s.title(text, x, y, *, size=28, color=None, align="left")  # heading
s.label(text, x, y, *, size=12, color="grey", align="center")  # caption
```

### Arrows
```python
s.arrow(src, dst, *, label=None, dashed=False, color=None,
        start=None, end="arrow", curve=False)        # bound, node→node
s.free_arrow(p0, p1, *, label=None, dashed=False,
             color=None, start=None, end="arrow")     # unbound, point→point
```
Arrowheads: `None, "arrow", "dot", "triangle", "bar"`. `curve=True` bends a
bound arrow (useful for a loop-back). `p0/p1` are `(x, y)` tuples.

### Save
```python
s.save(basename, out_dir=".", allow_overlap=False)  # -> (path.excalidraw, path.html)
```
Raises `ValueError` if two non-container nodes overlap (lists the labels). Fix
the layout, mark a wrapper `container=True`, or pass `allow_overlap=True`.

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
