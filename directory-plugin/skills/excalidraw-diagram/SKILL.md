---
name: excalidraw-diagram
description: >-
  Generate Excalidraw diagrams (.excalidraw scene files) AND an HTML viewer
  from a description of a system, flow, or architecture. Use this whenever the
  user asks for an Excalidraw diagram, a hand-drawn / whiteboard style
  schematic, an architecture poster, a flowchart, a sub-agent or pipeline
  diagram, or says things like "draw the architecture", "make a schema",
  "diagram this repo", "schemă excalidraw", or "put the diagram in an HTML".
  Also trigger when someone does not understand a system and a picture would
  teach it: "explain how X works", "I don't understand X", "nu înțeleg cum
  merge X", "walk me through this". Produces a valid .excalidraw file that
  imports into excalidraw.com plus a browser-openable .html.
---

# Excalidraw diagram (instructions-only edition)

Turn a description of a system into a real **Excalidraw scene** (`.excalidraw`)
plus an **HTML viewer** (`.html`): genuine Excalidraw, editable, not a screenshot.
This edition ships no code. **You write the scene JSON yourself**, so you carry the
invariants and the seven readability checks that the full edition's builder enforces.
[`references/excalidraw_format.md`](references/excalidraw_format.md) has every field;
[`references/example_scene.json`](references/example_scene.json) is a correct scene to copy from;
[`references/worked_examples.md`](references/worked_examples.md) has the layouts;
[`references/viewer_template.md`](references/viewer_template.md) has the HTML page.

**Builder available? Use it.** If the session already has the full edition's MCP tools
(`build_scene`, `render_html`, `graph_schema`, from `/plugin marketplace add
alxmax/excalidraw-diagram`), use those instead of this file. Never download or run code
to get them; if they are absent, write the JSON as below.

## The goal

**A schematic an outsider can understand with no prior context**: real components,
the flow between them, how it is invoked, how it ships. Three things pass:
1. **Substance**: real identifiers (`viewer.py`, `save()`), the actual workflow, and all
   three layers (internal flow, then integration, then distribution).
2. **Readability**: a title, a one-line subtitle, a legend when colour means a role,
   a glossary for jargon, one reading direction, zero overlaps or crossings.
3. **Self-check**: you run the seven checks below on your coordinates before saving.

## Workflow

1. **Understand the subject.** For a repo, read its README and layout first. List the
   nodes, the directed edges (each with a verb), the groups and the reading direction.
2. **Plan on a grid, in a table, before any JSON.** One row per node: id, label,
   shape, role colour, `x`, `y`, `w`, `h`. Compute sizes and positions with the rules
   below; never guess a coordinate by eye.
3. **Write the elements** in paint order: frames and containers first, then shapes, each
   followed by its bound text, then arrows, each followed by its label, then free text.
4. **Run the self-check** on the table. Fix the coordinates and re-check until all seven
   checks are clean.
5. **Write both files**: `<name>.excalidraw`, then `<name>.html` from the viewer template.
   ONE scene per request; several views stack as labelled regions in it.

## Element invariants (break one and the import misbehaves)

- **Envelope:** `{"type":"excalidraw","version":2,"source":"excalidraw-diagram-skill",
  "elements":[…],"appState":{"gridSize":null,"viewBackgroundColor":"#ffffff"},"files":{}}`.
- **Every element carries the full base**: `id, type, x, y, width, height, angle:0,
  strokeColor, backgroundColor, fillStyle:"solid", strokeWidth:2, strokeStyle,
  roughness, opacity:100, groupIds:[], frameId:null, roundness, seed, version:1,
  versionNonce, isDeleted:false, boundElements:[], updated, link:null, locked:false`.
- **Ids are unique** across the scene. Use `<type>-<n>-<8 hex>`, with `n` counting up.
- **`seed` and `versionNonce`** are distinct random integers in 1..2147483647, two per
  element. Never reuse one; the seed drives the hand-drawn wobble.
- **Text in a shape is two-way.** The text has `containerId` = shape id,
  `textAlign:"center"`, `verticalAlign:"middle"`. The shape lists
  `{"type":"text","id":<text id>}` in `boundElements`. Centre the text's box in the shape.
- **An arrow between shapes is two-way.** The arrow has `startBinding` and `endBinding`
  `{elementId, focus:0, gap:14}`. BOTH shapes list `{"type":"arrow","id":<arrow id>}`.
  An arrow label is text with `containerId` = arrow id, listed in the arrow's `boundElements`.
- **Arrow geometry:** `x,y` is the start point; `points` are relative to it, the first
  always `[0,0]`. Start and end 14px outside each border, on the line between the two
  centres. `width`/`height` span the points. Add `lastCommittedPoint:null`,
  `startArrowhead:null`, `endArrowhead:"arrow"`, `elbowed:false`.
- **Text fields:** `text`, `originalText` (identical), `fontSize`, `fontFamily`
  (1 hand-drawn, 2 normal, 3 code), `lineHeight:1.25`, `autoResize:true`.
- **Style:** `roughness` 0 (clean, the default) or 1 (sketch), the same for every element.
  Rectangles take `roundness:{"type":3}`; ellipses, diamonds and text take `null`.
- **Frames go behind.** A grouping rectangle is listed before its members so they paint on top.

## Sizing and layout (the grid)

- **Text extent:** width = longest line's characters × fontSize × 0.58; height =
  lines × fontSize × 1.25.
- **Box size:** `w ≥ chars × size × 0.65 + 20` and `h ≥ lines × size × 1.6 + 16`.
  Keep labels to 2–3 words per line; detail goes in a free caption under the box.
- **Columns:** `col_x[i+1] ≥ col_x[i] + col_w[i] + 80`. **Rows:** at least 60px apart
  vertically. Two shapes joined by a labelled arrow need a gap of at least the label's
  width plus 76px (14px off each border, then 24px of line each side of the label).
- **Frames:** 24px padding round their members. Their caption sits 24px above the top edge.
- **Free text** stays 16px clear of every shape and arrowhead.
- **Parallel nodes** go in one frame with ONE arrow in and ONE out, never N×N arrows.
- **Feedback edges** never run straight back across the flow. Route them below the row
  as an unbound arrow (`startBinding:null`, `endBinding:null`) through 4 points, dashed,
  in grey `#343a40`.
- **≤ 20 nodes per region.** Past that, split into an overview region and a detail region.
- **Expand, don't cram.** The canvas is unlimited; never shrink type below 12px.

## The seven self-checks (run all of them on your table before saving)

The full edition refuses a scene that fails any of these. You refuse it too.

1. **overlap**: no two non-frame shapes overlap by more than 1px on both axes, and no
   shape sits inside a frame that does not group it.
2. **short_arrows**: every bound arrow is at least 24px long.
3. **crossing**: the straight line between a bound arrow's two centres cuts no unrelated
   shape (inset 4px) and no frame caption. Move the box or route the arrow under.
4. **legend**: once a legend exists, every non-white `backgroundColor` on a shape appears
   in it.
5. **overflow**: every bound text's width and height fit inside its shape.
6. **text_overlap**: no two free texts (titles, captions, legend rows) overlap.
7. **label_fit**: an arrow's length minus its label's extent along it leaves at least
   24px of visible line at each end.

Also check that every `boundElements` entry points to an element that points back, and
that every `containerId`, `elementId` and `id` resolves.

## Quality rules (required, not polish)

1. **Title (28–32px) plus a one-line subtitle (14–16px)** saying what the diagram shows
   and its reading direction.
2. **Legend whenever colour means a role.** Use a frame titled "Legend" with an 18×18
   swatch and a label per colour. One colour per distinct meaning, and every colour used.
3. **Label cross-role edges** with a short verb phrase (`validates`, `POST /orders`).
4. **Real identifiers** as node names, never "Service A". Any term a newcomer cannot decode
   goes in a **Glossary** frame (term, then meaning) beside the legend.
5. **Two type tiers suffice:** title ~28–32, body ~14–16, never below 12.
6. **"Explain how X works"** means a teaching diagram. Use everyday words in the boxes,
   read top to bottom, and give one region per idea (the problem, how you use it, what
   is inside), each opened by a section title.

Palette (fill / stroke): grey `#e9ecef`/`#343a40`, blue `#a5d8ff`/`#1971c2`, green
`#b2f2bb`/`#2f9e44`, orange `#ffd8a8`/`#e8590c`, violet `#d0bfff`/`#6741d9`, red
`#ffc9c9`/`#e03131`, yellow `#ffec99`/`#f08c00`, teal `#99e9f2`/`#0c8599`, pink
`#fcc2d7`/`#c2255c`. Text and outlines use `#1e1e1e`.

## The HTML viewer

Copy the page in [`references/viewer_template.md`](references/viewer_template.md). It loads
`@excalidraw/excalidraw@0.17.6` and React/ReactDOM `18.2.0` (UMD builds) from unpkg, pinned
to those exact versions. Do not change them: 0.18+ is ESM-only and breaks the `<script>` page.
Substitute the title and the scene JSON. **Escape every `</` in the JSON as `<\/`** before
embedding it, or a label containing `</script>` ends the script early. The page needs a
network on first open and falls back to a download button when the CDN is unreachable.
The `.excalidraw` file itself always works offline.

## Pre-delivery checklist

- [ ] Ids unique; every binding two-way; seeds and nonces distinct
- [ ] The seven self-checks clean, with numbers you computed rather than eyeballed
- [ ] Title and subtitle, with the reading direction stated
- [ ] Legend lists every colour used; glossary covers every acronym or project term
- [ ] Every cross-role or non-obvious arrow labelled; real identifiers, no placeholders
- [ ] All three layers covered (internal flow, integration, distribution); ≤20 nodes per region
- [ ] `</` escaped in the HTML's embedded scene

Then deliver **both** files and say three things: **what it shows** (one sentence),
**how to read it** (the direction, how regions stack), and the **colour legend**.
`<name>.excalidraw` drags onto excalidraw.com to edit; `<name>.html` opens by double-click.
