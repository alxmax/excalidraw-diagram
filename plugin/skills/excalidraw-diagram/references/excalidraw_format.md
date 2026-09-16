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
`Scene(sketch=True)`; `Scene(typeface="hand")` switches the font to Excalifont.

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

## 4. The builder API

Every call, its signature, and the values they share (`at`, `paint`, `font`,
`Gates`) are in [`builder_api.md`](builder_api.md) — one home, so the two files
cannot disagree. This file stays about the format those calls produce.

## 5. Common mistakes

- **Cramming text** — boxes don't auto-resize; long text overflows. Keep labels
  to a few words, size the box, or push detail into a `label()` beneath.
- **Forgetting frames go behind** — use `frame()` (auto z-order), not a plain
  `box()`, for containers, or children get hidden.
- **Hand-editing the JSON** — let the builder own seeds/nonces/bindings.
  Editing them by hand is the usual cause of "arrow not attached" on import.
- **Overlapping coordinates** — `save()` refuses overlapping shapes, but only
  after you placed them. Prefer `arrange()`/`pipeline()`/`pack()`; by hand, keep
  ~90–120px between boxes and ~40px frame padding.
- **Mixed reading directions** in one region — pick one (L→R or top-down) and
  separate other regions with a `title()`.

## HTML viewer notes

`save()` also writes a `<basename>.html` that renders the scene via the official
Excalidraw UMD build pinned to `@excalidraw/excalidraw@0.17.6` + React 18.2 from
unpkg. It needs a network connection on first load (to fetch the CDN bundle and
fonts); if the CDN is unreachable it shows a fallback with a download button.
The embedded scene and the standalone `.excalidraw` file are always offline-safe.
To change the pinned version, edit `_EXCALIDRAW_CDN` in `excalidraw_engine/viewer.py`
(note: 0.18+ is ESM-only and won't work with the UMD `<script>` approach).
