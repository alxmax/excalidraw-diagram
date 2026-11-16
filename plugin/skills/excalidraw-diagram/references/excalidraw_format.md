# The Excalidraw format, for writing a scene by hand

Read this when you need detail beyond SKILL.md: the on-disk format, every field, and
the mistakes that make a scene import badly.
[`example_scene.json`](example_scene.json) is a correct scene with every construct
below. It has a title, a subtitle, two boxes with bound labels, a bound arrow with a
label, and a legend. When in doubt, copy its shape.

## 1. The file

A scene is a single JSON object:

```json
{
  "type": "excalidraw",
  "version": 2,
  "source": "excalidraw-diagram-skill",
  "elements": [],
  "appState": { "gridSize": null, "viewBackgroundColor": "#ffffff" },
  "files": {}
}
```

- `elements` is **flat**: there is no nesting. A box "inside" a frame is a separate
  element whose coordinates fall within the frame's, listed later so it paints on top.
- Array order is paint order. Write frames first.
- Importing into excalidraw.com runs a `restore` pass that fills in missing cosmetic
  fields (fractional z-index strings and the like). Leave those out.

## 2. Element types and fields

Every element carries this base:

```
id, type, x, y, width, height, angle,
strokeColor, backgroundColor, fillStyle, strokeWidth, strokeStyle,
roughness, opacity, groupIds, frameId, roundness,
seed, version, versionNonce, isDeleted, boundElements, updated, link, locked
```

| Field | Value |
|---|---|
| `angle` | `0` |
| `fillStyle` | `"solid"` |
| `strokeWidth` | `2` |
| `strokeStyle` | `"solid"`, or `"dashed"` for feedback, optional and skip paths |
| `roughness` | `0` clean, `1` sketch: one value for the whole scene |
| `opacity` | `100` |
| `groupIds` | `[]` |
| `frameId` | `null` |
| `seed`, `versionNonce` | distinct random integers, 1..2147483647 |
| `version` | `1` |
| `isDeleted` | `false` |
| `updated` | a millisecond timestamp, the same for every element is fine |
| `link` | `null` |
| `locked` | `false` |

Type-specific:

- **rectangle / ellipse / diamond**: `roundness: {"type": 3}` rounds rectangle corners;
  ellipses and diamonds use `null`. `backgroundColor` is the role fill, or
  `"transparent"`.
- **text** adds `text, fontSize, fontFamily, textAlign, verticalAlign, containerId,
  originalText, lineHeight, autoResize`. `fontFamily` is `1` for hand-drawn
  (Excalifont/Virgil), `2` for normal (Helvetica) and `3` for code (Cascadia).
  `originalText` equals `text`, `lineHeight` is `1.25`, `autoResize` is `true`, and
  `backgroundColor` is `"transparent"`. A free caption has `containerId: null`,
  `verticalAlign: "top"` and usually `textAlign: "left"`.
- **arrow** adds `points` (relative to the element's `x,y`; the first is `[0, 0]`),
  `startBinding, endBinding, startArrowhead, endArrowhead, lastCommittedPoint, elbowed`.
  `roundness: {"type": 2}` with a third, raised midpoint makes a curve; a straight arrow
  has `roundness: null`. `endArrowhead: "arrow"` and `startArrowhead: null` for a normal
  arrow; set both to `null` for a plain connector.

## 3. Bindings

Two relationships need **two-way** references, or Excalidraw renders them wrong.

**Text inside a shape.** The text gets `containerId` = the shape's id,
`textAlign: "center"` and `verticalAlign: "middle"`. The shape gets
`{"type": "text", "id": <textId>}` in `boundElements`. Size the text with the extent
rule (characters × size × 0.58 wide, lines × size × 1.25 tall) and centre it in the shape.

**Arrow between two shapes.** The arrow gets `startBinding: {elementId, focus, gap}` and
`endBinding: {…}`. **Each** connected shape gets `{"type": "arrow", "id": <arrowId>}`
in `boundElements`. `focus` (−1..1) shifts where the arrow meets the shape; use `0`.
`gap` is the pixel gap between the arrowhead and the border; use `14`, or less when the
shapes are close.

On load Excalidraw re-routes a bound arrow from its bindings, so `points` only need to
be a good initial straight line. Compute it border to border.
1. Take the line between the two shapes' centres.
2. Find where it leaves each shape. For a rectangle, scale the centre-to-centre vector
   by `0.5 / max(|dx|/w, |dy|/h)`.
3. Move each end 14px further along the line, away from its border.
4. The arrow's `x,y` is the start point and `points` is `[[0,0],[end-start]]`.
   `width` and `height` are the span of the points.

**Right-angle (elbow) arrow.** When the two shapes do not share a row or a column, a
straight line between them is a diagonal, and diagonals fail the self-check. Draw the
same bound arrow through four points instead: out of the side facing the target, along
to the middle of the gap, across, and into the facing side. A Z from a box on the left
to a box lower right, with the turn at `xm` (the middle of the horizontal gap):

```json
"x": 214, "y": 95,
"points": [[0, 0], [xm - 214, 0], [xm - 214, 180], [412 - 214, 180]],
"elbowed": false
```

Every leg is horizontal or vertical. The bindings are the same as a straight arrow's,
both shapes list it, and Excalidraw 0.17.6 keeps the inner points on load and re-fits
only the ends. Leave `elbowed: false`: `true` is a later version's auto-router and
discards your points. A label sits at the midpoint of the middle leg (for an even count
of points) or on the middle point (for an odd count): that is where the editor draws it.
**Attach points:** when two or more connectors meet the same side of a shape, give each
its own point on that side, at least 12px apart (24px keeps the arrowheads apart),
leaning toward the shape at the other end. Never let two connectors share one point.

**Arrow label.** Text with `containerId` = the arrow's id, `fontSize` 14, stroke
`#343a40`, centred on the arrow's midpoint (on an elbow arrow, its middle leg). The arrow
lists it in its own `boundElements`.

**Sublabel (the second text tier).** A node's technical detail (a file, a port, a
command) is a separate free text under the name: `fontFamily: 3`, `fontSize` 12–13,
`containerId: null`, inside the shape below the bound name with 4px between them. Give
the shape, its name and the sublabel one shared `groupIds` entry so they move together,
set the name's `verticalAlign` to `"top"` so a re-layout keeps it above, and size the
shape for both tiers: `h ≥ name height + 4 + sublabel height + 16`.

**Unbound connectors** (a feedback edge routed under a row, a lifeline, a timing trace)
have `startBinding: null` and `endBinding: null`, and appear in no shape's
`boundElements`. Three of the seven checks cannot see them, so assert their geometry
yourself: every point lies where you meant it to.

## 4. Common mistakes

- **Cramming text.** Boxes do not grow to fit. Size the box from its text, or move the
  detail into a caption beneath.
- **A container drawn after its members** hides them. Frames come first in `elements`.
- **One-way bindings.** An arrow with `startBinding` whose shape does not list it, or a
  text with `containerId` whose shape does not list it, is the usual cause of "arrow not
  attached" or "label floats" on import.
- **Reused ids, seeds or nonces.** Every id is unique, and every seed and nonce is fresh.
- **Coordinates by eye.** Compute every `x` from the column rule and every size from the
  text. Keep ~90–120px between boxes and ~24–40px of frame padding.
- **Mixed reading directions** in one region. Pick left-to-right or top-down, and
  separate other regions with a section title.
