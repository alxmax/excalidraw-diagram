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
2. **Pick a layout.** Left-to-right for pipelines and data flow; top-down for
   hierarchies; grouped frames for "one box contains several things" (e.g. an
   agent that runs several sub-agents). Choose explicit coordinates — the
   builder does not auto-layout. Keep ~90–120px gaps between boxes and put
   frames *behind* their children (the builder handles z-order for `frame()`).
3. **Write a short generator script** that imports the builder, declares the
   shapes and arrows, and calls `.save(basename, out_dir)`. See
   `examples/make_consilium.py` for a complete, non-trivial example
   (pipeline + grouped agent frames + feedback loop + a modes section).
4. **Run it**, then **present both files** (`.excalidraw` first, then `.html`).
5. If you want to sanity-check the layout before presenting, you can render a
   quick preview — but the `.excalidraw` itself is the source of truth.

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
| `Scene(font="normal", sketch=False, background="#ffffff")` | the canvas |
| `s.box(text, x, y, w=160, h=70, fill=…, shape=…, font_size=…)` | a labelled rectangle (→ node id) |
| `s.ellipse(text, x, y, w, h, …)` | a labelled ellipse |
| `s.diamond(text, x, y, w, h, …)` | a labelled decision diamond |
| `s.frame(x, y, w, h, dashed=False)` | a container drawn *behind* children |
| `s.title(text, x, y, size=28)` | a large free-standing heading |
| `s.label(text, x, y, size=12)` | a small grey caption (e.g. "ONE AGENT") |
| `s.arrow(src, dst, label=…, dashed=…, curve=…, start=…, end=…)` | a bound arrow node→node |
| `s.free_arrow(p0, p1, …)` | an unbound arrow between two points |
| `s.save(basename, out_dir=".")` | writes `<basename>.excalidraw` + `.html` |

**Colours** accept a hex string or a palette name: `grey, red, orange, yellow,
green, teal, blue, indigo, violet, pink`. Each name maps to Excalidraw's own
stroke + light-fill pair, so diagrams look native.

**Grouping pattern** (an "agent" that holds several voices/boxes): draw a
`frame()` or `ellipse()` first, place the inner `box()`es on top at coordinates
inside it, and add a `label()` caption above. `examples/make_consilium.py`
factors this into an `agent(...)` helper you can copy.

## Tips for good diagrams

- **Keep labels short.** Two or three words per box; push detail into a caption
  `label()` underneath rather than cramming the box.
- **One reading direction.** Don't mix left-to-right and top-down in the same
  region; separate regions (like "pipeline" vs "modes") with a `title()`.
- **Use colour by role**, consistently (e.g. always violet = creative voice),
  not decoratively.
- **Dashed arrows** for feedback / optional / skip paths; solid for the main
  flow.
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
