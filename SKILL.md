---
name: excalidraw-diagram
description: >-
  Generate Excalidraw diagrams (.excalidraw scene files) AND a self-contained
  HTML viewer from a description of a system, flow, or architecture. Use this
  whenever the user asks for an Excalidraw diagram, a hand-drawn / whiteboard
  style schematic, an architecture poster, a flowchart, a sub-agent or pipeline
  diagram, or says things like "draw the architecture", "make a schema",
  "diagram this repo", "schemă excalidraw", or "put the diagram in an HTML".
  Also trigger when asked to visualise how components, agents, requirements, or
  modules connect — even if the word "Excalidraw" is not used but a sketchy /
  editable diagram is wanted. Produces a valid .excalidraw file that imports
  into excalidraw.com plus a browser-openable .html.
---

# Excalidraw diagram

Turn a description of a system into a real **Excalidraw scene** (`.excalidraw`)
and a **self-contained HTML viewer** (`.html`) that renders it in any browser.

The output is genuine Excalidraw — hand-drawn look, editable, exportable — not a
screenshot. The `.excalidraw` file drag-and-drops into
[excalidraw.com](https://excalidraw.com); the `.html` embeds the same scene and
renders it with the official Excalidraw component.

## When to use

- "Make an Excalidraw / whiteboard / hand-drawn diagram of …"
- "Diagram this repo's architecture" / "schemă excalidraw pentru …"
- Flowcharts, pipelines, multi-agent / sub-agent layouts, module maps,
  state flows, decision trees.
- "Put the diagram in an HTML I can open / share."

For polished vector diagrams the user wants as a *static image* (PNG/SVG) with no
sketch aesthetic, a plain SVG may fit better — but if they said Excalidraw,
use this.

## How it works

You **never hand-write Excalidraw JSON.** Use the bundled builder
`scripts/excalidraw_builder.py`. It hides all the boilerplate (seeds, version
nonces, two-way arrow bindings, bound-text back-references) behind a small API,
and emits both files in one `.save()` call.

### Workflow

1. **Understand the thing to draw.** If it's a repo, read its README / file
   layout first so the diagram reflects the *actual* components and data flow,
   not a generic template. Identify: the nodes, the directed connections between
   them, any grouping (frames / "agents"), and the natural reading direction.
2. **Plan the layout on paper first** (see Layout rules below). List every
   column, its x position, and all arrows. Verify no arrow crosses an unrelated
   box before writing a single line of code.
3. **Pick a layout.** Left-to-right for pipelines and data flow; top-down for
   hierarchies; grouped frames for "one box contains several things" (e.g. an
   agent that runs several sub-agents). Choose explicit coordinates — the
   builder does not auto-layout. Keep ≥80px gaps between columns and ≥30px
   between boxes in the same column. Put frames *behind* their children (the
   builder handles z-order for `frame()`).
4. **Write a short generator script** that imports the builder, declares the
   shapes and arrows, and calls `.save(basename, out_dir)`. See
   `examples/make_consilium.py` for a complete, non-trivial example
   (pipeline + grouped agent frames + feedback loop + a modes section).
5. **Run it.** `save()` raises if any shapes overlap — if it does, fix the
   coordinates and re-run until it passes. Then **present both files**
   (`.excalidraw` first, then `.html`).
6. If you want to sanity-check the layout before presenting, you can render a
   quick preview — but the `.excalidraw` itself is the source of truth.

### Layout rules (apply before writing code)

**Parallel groups — the most common source of spaghetti arrows**

When N nodes run simultaneously (e.g. 9 senators, 3 agents, parallel workers):
- Place them with `grid()`/`row()` and wrap with `enclose()` — even spacing, an
  auto-sized frame, zero coordinate math:
  ```python
  workers = s.grid([f"agent {i}" for i in range(9)], 900, 120, 3, fill="violet")
  group   = s.enclose(workers, label="9 parallel sub-agents")
  ```
- Draw **one arrow in** to the frame (`s.arrow(dispatch, group)`), **one arrow
  out** (`s.arrow(group, merge)`). Never draw arrows between individual nodes
  inside the group — that creates N×N crossing lines.

**Column gaps**

Every column must have ≥80px clearance on each side before the next column
starts. Formula: `col_x[i+1] ≥ col_x[i] + col_width[i] + 80`.

**Arrow crossing check** (do this before coding every arrow)

Draw an imaginary straight line from source centre to target centre. If it
passes through any box that is NOT the source or target, the layout is wrong —
either restructure the columns or use `route_under()` for the arrow.

**Backward / feedback arrows**

Any arrow that goes right-to-left crosses the entire forward flow and will
overlap everything. Always use `route_under()` (goes below the row, then back)
or omit it and add a text `label()` noting the feedback.

**Reference / legend columns**

A column that only shows possible values (e.g. "Verdicts: GO / STOP / MODIFY")
is a legend, not a pipeline stage. Do not draw a long arrow to it from across
the diagram — that arrow will cross other columns. Either connect it with a
short arrow from the nearest upstream node, or leave it unlabelled and add a
`s.label()` caption above it.

**Box sizing**

Size boxes to fit their text; do not let text overflow:
- Height: `h ≥ num_lines × font_size × 1.6 + 16`
- Width:  `w ≥ max_line_length_chars × font_size × 0.65 + 20`

Run the numbers before placing the box. A 2-line label at font_size 14 needs
at least h=60; at font_size 13 with a 16-char line needs at least w=135.

**One file, many diagrams**

Always produce ONE `.excalidraw` + ONE `.html` per request — a single `.save()`
call. If a system genuinely needs several views (e.g. architecture + data flow +
modes), do NOT emit separate files. Stack the views as labelled regions in the
*same* scene: open each with a `s.title(...)` and separate them vertically. Use
`s.bounds()` (returns `(min_x, min_y, max_x, max_y)`) to find where the previous
region ended, then start the next ~80px below `max_y`.

This rule is **enforced by the builder**: calling `save()` twice on the same
`Scene` raises a `RuntimeError` at runtime, so splitting into multiple scripts
or multiple `save()` calls will fail immediately.

**Expand, don't cram**

The canvas is unlimited. When a diagram gets dense, spread it out — bigger gaps,
larger boxes, a fresh region below. Never shrink fonts or overlap shapes to make
things fit. A large, airy diagram always reads better than a small, tight one.

**Overlap and crossings are caught for you**

`save()` raises a `ValueError` if any two normal shapes overlap, naming the
offending labels — fix the coordinates until it passes. A shape that is *meant*
to wrap others (an ellipse drawn around inner boxes, a backing panel behind a
group) must be created with `container=True` so it is exempt; `frame()` is always
exempt. As a last resort `save(..., allow_overlap=True)` skips the check, but
prefer fixing the layout.

`save()` also **prints a warning** when a bound arrow's straight path runs
through an unrelated box (the automated form of the crossing rule above). It's a
warning, not an error — reroute with `route_under()` or move the box until it's
gone.

**Centered captions anchor at the point.** `label(text, x, y)` and
`title(..., align="center")` treat `x` as the *center* of the text (and
`align="right"` as the right edge). Pass the coordinate you want the caption
centered on — e.g. a frame's mid-x — not its left edge.

**Committing the diagram?** Pass `Scene(seed=<int>)` so re-running produces a
byte-identical file (no git churn from random seeds/timestamps).

**Frame & group captions**

Put a group's caption ≥24px ABOVE the frame's top edge (`y = frame_y - 24`),
never on the border line. Keep free-floating explanatory `label()` text ≥16px
clear of every shape and arrowhead — text under an arrowhead or on a box edge is
the other common overlap.

### Minimal example

```python
import sys, os
sys.path.insert(0, "scripts")
from excalidraw_builder import Scene

s = Scene()                       # normal font, clean lines (the readable default)
# Scene(font="hand", sketch=True) # the classic hand-drawn whiteboard look instead
s.title("Auth flow", 40, -40, size=32)

a = s.box("Client",        40,  60, fill="grey")
b = s.box("API gateway",   40, 200, fill="blue")
c = s.box("Auth service",  40, 340, fill="violet")
d = s.diamond("Token\nvalid?", 320, 330, fill="orange")
ok  = s.box("200 OK",   560, 250, fill="green")
err = s.box("401",      560, 410, fill="red")

s.arrow(a, b, label="request")
s.arrow(b, c, label="verify")
s.arrow(c, d)
s.arrow(d, ok,  label="yes")
s.arrow(d, err, label="no", dashed=True)

s.save("auth_flow", out_dir="docs")   # -> docs/auth_flow.excalidraw + .html
```

## Builder API (cheat-sheet)

Full signatures and the file-format details are in
[`references/excalidraw_format.md`](references/excalidraw_format.md). The
essentials:

| Call | Draws |
| --- | --- |
| `Scene(font="normal", sketch=False, background="#ffffff", seed=None)` | the canvas (`seed=<int>` → byte-stable file for git) |
| `s.box(text, x, y, w=160, h=70, fill=…, shape=…, font_size=…, container=…)` | a labelled rectangle (→ node id) |
| `s.ellipse(text, x, y, w, h, …, container=…)` | a labelled ellipse |
| `s.diamond(text, x, y, w, h, …)` | a labelled decision diamond |
| `s.frame(x, y, w, h, dashed=False)` | a container drawn *behind* children (overlap-exempt) |
| `s.row(items, x, y, gap=…, connect=…)` | place items left→right → list of ids (`connect=True` chains arrows) |
| `s.column(items, x, y, gap=…, connect=…)` | place items top→down → list of ids |
| `s.grid(items, x, y, cols, …)` | place items in a `cols`-wide grid → list of ids |
| `s.enclose(ids, label=…, pad=…)` | auto-sized frame *behind* those nodes → frame id |
| `s.title(text, x, y, size=28)` | a large free-standing heading |
| `s.label(text, x, y, size=12)` | a small grey caption (e.g. "ONE AGENT") |
| `s.arrow(src, dst, label=…, dashed=…, curve=…, start=…, end=…)` | a bound arrow node→node |
| `s.free_arrow(p0, p1, …)` | an unbound arrow between two points |
| `s.route_under(src, dst, drop=…, label=…)` | a connector routed below the row (feedback / backward) |
| `s.bounds()` | `(min_x, min_y, max_x, max_y)` of all shapes — for stacking regions |
| `s.check_arrow_crossings()` | `[(src, dst, crossed), …]` arrows running through an unrelated box |
| `s.save(basename, out_dir=".")` | writes both files; **raises if shapes overlap**, warns on arrow crossings |

**Colours** accept a hex string or a palette name: `grey, red, orange, yellow,
green, teal, blue, indigo, violet, pink`. Each name maps to Excalidraw's own
stroke + light-fill pair, so diagrams look native.

**Auto-layout** — prefer `row`/`column`/`grid` over hand-computing coordinates;
they space evenly (so shapes never overlap) and return the ids in order. Each
`items` entry is a `"text"` string, a `(text, fill)` pair, or a full dict of
`box()` options. `enclose(ids, label=…)` then draws a correctly-sized frame
behind them — no manual frame math.

**Grouping pattern** (an "agent" that holds several voices/boxes): draw a
`frame()` or `ellipse(..., container=True)` first, place the inner `box()`es on
top at coordinates inside it, and add a `label()` caption above. Mark the wrapper
`container=True` (frames are automatic) so the overlap check ignores
wrapper-vs-child. `examples/make_consilium.py` factors this into an `agent(...)`
helper you can copy.

## Tips for good diagrams

- **Keep labels short.** Two or three words per box; push detail into a caption
  `label()` underneath rather than cramming the box.
- **One reading direction.** Don't mix left-to-right and top-down in the same
  region; separate regions (like "pipeline" vs "modes") with a `title()`.
- **Use colour by role**, consistently (e.g. always violet = creative voice),
  not decoratively.
- **Dashed arrows** for feedback / optional / skip paths; solid for the main
  flow.
- **Parallel nodes → one frame, two arrows.** If N nodes do the same thing in
  parallel, group them in a `frame()` and connect the frame — not each node.
  This is the single biggest source of spaghetti diagrams.
- **No arrow should cross an unrelated box.** If a straight line from A to B
  passes through C (which it is not connected to), restructure the layout or
  route around with `route_under()`.
- **Reflect reality.** When diagramming a codebase, name the real files /
  scripts / functions so the picture is useful to someone reading the code.
- **Font & style.** `Scene()` defaults to a normal font with clean outlines —
  the most readable choice for "anyone should understand this". Pass
  `Scene(font="hand", sketch=True)` only when the sketchy whiteboard aesthetic
  is wanted. Arrows already start and end a few pixels *outside* each box, so
  heads and tails never touch the shapes.

## Output

Always deliver **both** files and tell the user, briefly:
- `<name>.excalidraw` — drag onto excalidraw.com (or File → Open) to edit.
- `<name>.html` — double-click to open in a browser; "Download .excalidraw"
  button is built in. The HTML loads Excalidraw from a CDN, so viewing it needs
  a network connection the first time; the `.excalidraw` file works fully
  offline.
