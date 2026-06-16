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

## The goal (read this first)

**Produce a schematic an outsider can understand with no prior context** — one
that shows *how the system actually works*: its real components, the data flow /
workflow between them, how it is invoked, and how it ships. When the subject is a
repo, the diagram must reflect *that repo's* real files and flow, not a generic
template. Pretty-but-shallow fails the goal; accurate-and-readable passes it.

Three things make a diagram pass:
1. **Substance** — real identifiers (`reqmap.py`, `check_overlaps()`), the actual
   workflow, and all three layers (internal flow → integration → distribution).
2. **Readability** — title + one-line subtitle, a legend when colour means a
   role, a glossary for jargon, one reading direction, zero overlaps/crossings.
3. **Enforcement** — the builder's gates (`save(..., crossing_check="error",
   legend_check="error", overflow_check="error", text_overlap_check="error")`)
   turn those rules into hard failures so a sloppy diagram can't ship.

The canonical worked example of all three is
[`examples/make_full_architecture.py`](examples/make_full_architecture.py) —
treat it as the template when asked to "diagram this repo." See **Worked
examples** at the bottom for ❌ → ✅ variants of the common cases.

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

## Commands (CLI)

The authoring path is **always Python** — you write (or scaffold) a generator
script against the `Scene` API and run it. There is intentionally **no
declarative `build <spec>` verb**: a second authoring format would diverge from
the builder API. The CLI has two helper verbs plus the self-test:

| Command | What it does | When to pick it |
|---|---|---|
| `python scripts/excalidraw_builder.py` | run the builder self-test (smoke test) | verifying the builder still works |
| `python scripts/excalidraw_builder.py render <scene.excalidraw> [out_dir]` | rebuild the self-contained `.html` viewer from an **existing** scene file | you edited a `.excalidraw` on excalidraw.com and want a fresh viewer (no generator script to re-run) |
| `python scripts/excalidraw_builder.py discover <repo> [out.py]` | scan a repo → emit a **runnable multi-layer poster stub** (live STRUCTURE layer + commented scaffolds for WORKFLOW / INTEGRATION / MODES / MODEL / DATA to keep or delete) | starting a repo-architecture diagram — scaffold the layers, fill in the real content, run it |

**Menu (how to start a diagram):**
- **New diagram (from a description)** — write a Python generator against the `Scene` API (the Workflow below), then run it. *When you know the system and want full control over the layout.*
- **Scaffold from a repo** — `discover <repo>` to emit `make_diagram.py` pre-seeded as a multi-layer poster (live STRUCTURE + commented WORKFLOW/INTEGRATION/MODES/MODEL/DATA layers); keep the layers the repo needs, fill in the real content, then run it. *When the subject is an existing codebase.*
- **Re-run / extend your generator** — re-execute (or edit, then re-execute) the existing `make_diagram.py`. *When you already have the generator and want to update or grow the diagram — the source of truth is the Python script, not the `.excalidraw`.*
- **Re-render the viewer only** — `render <scene.excalidraw>` to regenerate the `.html` for a scene edited elsewhere (e.g. on excalidraw.com), with no generator script to re-run. *When you hand-edited the `.excalidraw` directly.*
- **Self-test** — `python scripts/excalidraw_builder.py` with no args runs the builder smoke test. *When verifying the builder is healthy or before reporting a bug — this is the no-arg invocation CI depends on, so don't shadow it with a new default verb.*

`discover` only scaffolds the *components* it can see; inferring the real data flow
and grouping stays your job (the same judgement the Workflow below describes).

### Workflow

1. **Understand the thing to draw.** If it's a repo, read its README / file
   layout first so the diagram reflects the *actual* components and data flow,
   not a generic template. Identify: the nodes, the directed connections between
   them, any grouping (frames / "agents"), and the natural reading direction.

   **For architecture diagrams, audit all three layers before planning layout —
   a diagram that only shows the internal flow is incomplete:**
   - *Internal flow* — pipeline steps, algorithm, modes/variants, decision gates
   - *Integration* — how the system is invoked (entry points, CLI, skill, API),
     what external systems it touches (git, CI, databases, plugins, parent
     orchestrators), feedback loops, and persistent state (files, logs, caches)
   - *Distribution* — how the system reaches users (install, package, deploy,
     marketplace)

   Use `s.bounds()` to stack each layer as a separate labelled region below the
   previous one rather than cramming all three into a single dense region.

   **Large repo? Fan out the exploration (optional).** Sequential reading is
   slow on a big codebase. After the README pass, count source files with a
   `Glob` over the scan extensions (excluding `node_modules/`, `.git/`,
   `__pycache__/`):
   - **≤ 80 source files, or the `Agent` tool is unavailable** → explore
     sequentially yourself; do not spawn subagents (the overhead isn't worth it).
   - **> 80 source files** → dispatch read-only `Explore` subagents **in
     parallel** (3 by default — one per lens; split a lens for a very large repo,
     never more than 5), then synthesise their results and draw. Assign the model
     per lens — **Sonnet only for the analytical lens, Haiku for the mechanical
     ones** (the reasoning gap is real only where flow must be inferred):

     | Lens (subagent) | Model | Gathers |
     |---|---|---|
     | structure + entry-points | **haiku** | source dirs; entry points (`main`/`run`/`app`/`index`/`cli`); package manifests (`setup.py`, `package.json`, `go.mod`, `Cargo.toml`) |
     | data-flow + integration | **sonnet** | imports/calls between modules, real vs test deps, external touch-points (APIs, DBs, queues, CI) — the lens that must *reason* about flow |
     | distribution + packaging | **haiku** | CI/deploy/packaging files (`.github/*.yml`, `Dockerfile`, `*.tf`, manifests) and what the repo publishes to / depends on at deploy |

     Each subagent returns a compact JSON (**≤ 60 lines**): `components`
     (real file/module names — never placeholders like "ServiceA"), directed
     `edges` (`{src, dst, label}` with a verb like calls/imports/reads/deploys),
     and its `group`. The main agent merges the outputs, **dedups by id**, then
     proceeds to layout. Cost guards: never exceed 5 subagents, ≤ 60 lines each,
     and don't re-read files a subagent already covered.
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
   `examples/make_full_architecture.py` for a complete, non-trivial example
   (role-coloured stacked sections + a `legend()` key + glossary, shipped with
   `crossing_check="error"`/`legend_check="error"` so the layout gates stay enforced).

   **Name the script by what it generates, not by the project it depicts.**
   Use `make_diagram.py` or `make_full_architecture.py` — never
   `make_<projectname>.py`. The project is already implicit from the directory
   and from the `basename` you pass to `.save()`. A subject-specific filename
   prevents reuse and is wrong when the script is moved or repurposed.
5. **Run it.** `save()` raises if any shapes overlap — if it does, fix the
   coordinates and re-run until it passes. Then **present both files**
   (`.excalidraw` first, then `.html`).
6. If you want to sanity-check the layout before presenting, you can render a
   quick preview — but the `.excalidraw` itself is the source of truth.

### Diagramming a repo's architecture (the canonical recipe)

When the task is "diagram this repo / how this system works," do **not** invent a
layout from scratch and do **not** emit several files. Produce **ONE** scene of
**stacked layers**, each opened with `s.section(title)` (which auto-stacks below
everything drawn so far — no `bounds()` math). The template is
[`examples/make_full_architecture.py`](examples/make_full_architecture.py).

**You decide which layers this repo needs — and how many.** Not every repo has
modes or a schema; a CLI tool may be three layers, a multi-agent system six.
After exploring the repo (Workflow step 1), include a layer **only when its
condition holds**, in this order, all in the one scene:

| Layer | Include when… | Build it with |
|---|---|---|
| **1. STRUCTURE** | always | role-coloured `box()`es + one `enclose()` |
| **2. WORKFLOW** | the repo has a pipeline / run-order / algorithm | `s.pipeline([...])` (ISO shapes) + `route_under()` for feedback — **one `s.lane()` per tool** if the repo bundles several (see *Per-tool sub-workflows*) |
| **3. INTEGRATION** | it is invoked by / connects to external systems, CI, or has a loop | `box()`es + labelled `arrow()`s; entry points, external systems, state |
| **4. MODES / VARIANTS** | it has modes / strategies / variants of the same flow | one self-contained `column()`+`enclose()` per mode |
| **5. MODEL / RUNNERS** | parts run on different models / workers / runtimes | group → `arrow()` → a runtime/model box |
| **6. DATA / SCHEMA** | it produces a core record / output shape | a record `box()` + enum/annotation satellites |

Then **one** `s.legend(...)` (colour = role) and **one** `s.glossary(...)` decode
the *whole* poster, and `s.save(..., crossing_check="error", legend_check="error",
overflow_check="error", text_overlap_check="error")`.

**Colour discipline across layers:** the single legend must decode every layer, so
give each *distinct* meaning its own colour — do not let two layers reuse one
colour for different roles (e.g. an "engine" script and a "model" must differ).
With ≤10 palette colours, merge only genuinely-equivalent roles.

**Per-tool sub-workflows (multi-tool repos only).** A repo that bundles **two or
more distinct tools / skills / services with distinct flows** (e.g. a plugin with
3 skills, a monorepo of services) must NOT collapse them into one pipeline — that
hides all but one. Give each its own labelled `s.lane(ids, "<tool> — <one-line>")`
sub-workflow, stacked within the WORKFLOW layer. A **single-tool** repo keeps a
single `pipeline()` — do not invent lanes it doesn't have.

**Depth comes from structure, never from cramming.** Make each layer show the
*true* flow — its real steps, decision gates (`diamond`), and feedback edges
(`route_under`) with real identifiers — using the **fewest nodes that tell the
real story**. When a layer would need more, add *another lane / sub-region /
layer*, never more nodes in one region or smaller text. The readability rules
below (≤20 nodes per region, keep labels short, simplicity first, expand-don't-
cram) **always win**: on any tension, split or drop — do not cram. "Elaborate"
means *structurally complete*, not *busy*.

**Fast start:** `discover <repo>` emits exactly this skeleton — a live STRUCTURE
layer plus commented scaffolds for layers 2-6 (the WORKFLOW scaffold shows both a
single pipeline and the per-tool `lane()` pattern). Delete the layers the repo
doesn't need, fill in the rest from the real code, and run it.

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

Size boxes to fit their text; do not let text overflow. The builder *catches*
overflow for you — `save(..., overflow_check="error")` raises when bound text
spills outside its shape, and `check_text_overflow()` lists the offenders — so
you don't have to eyeball it. Use these starting estimates, then let the gate
confirm:
- Height: `h ≥ num_lines × font_size × 1.6 + 16`
- Width:  `w ≥ max_line_length_chars × font_size × 0.65 + 20`

A 2-line label at font_size 14 needs at least h=60; at font_size 13 with a
16-char line needs at least w=135. Keep labels short (2–3 words) and push detail
into a `label()` caption to stay well clear of the gate.

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
warning by default — reroute with `route_under()` or move the box until it's
gone. Pass `save(..., crossing_check="error")` to make a crossing a hard failure
(opt-in gate, mirroring the overlap check).

**Four `save()` gates — turn them all to `"error"` for a ship-quality diagram.**
Each defaults to `"warn"` (prints) and becomes a hard failure at `"error"`:
- `crossing_check` — a bound arrow runs through an unrelated box.
- `legend_check` — a fill colour is used but missing from the `legend()` (fires
  only once a legend is rendered; the colour-SSOT guarantee).
- `overflow_check` — bound text is bigger than its box (spills outside). Shapes
  don't overlap, so the overlap check misses this — it's a separate gate.
- `text_overlap_check` — two captions / labels overlap each other.

The canonical examples ship with all four at `"error"`:
`s.save("name", out_dir, crossing_check="error", legend_check="error",
overflow_check="error", text_overlap_check="error")`. Do the same — it is the
operational definition of "an outsider can read this."

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

### Importing the builder

**Inside the plugin** (e.g. an `examples/` script): use a relative path.

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from excalidraw_builder import Scene
```

**In an external repo** (a generator script that lives in your own project,
not inside the plugin directory): use the dynamic resolver below. It scans
the plugin cache, picks the **highest installed semver**, and imports from
there. This survives any plugin update without ever needing to edit the script.

```python
import sys, os, glob, re

def _builder_path():
    cache = os.path.join(os.path.expanduser("~"), ".claude", "plugins",
                         "cache", "requirement-manager", "requirement-manager")
    hits = glob.glob(os.path.join(cache, "*", "skills",
                                  "excalidraw-diagram", "scripts"))
    if not hits:
        raise RuntimeError(
            "excalidraw-diagram skill not found — run: /plugin install requirement-manager"
        )
    def _ver(p):
        m = re.search(r"(\d+)\.(\d+)\.(\d+)", p)
        return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)
    return max(hits, key=_ver)

sys.path.insert(0, _builder_path())
from excalidraw_builder import Scene
```

**Never hardcode a version number** (e.g. `1.32.0`) in the path — the plugin
cache keeps every version ever installed and the script will silently keep
using the old, limited API after any update.

### Minimal example

```python
import sys, os, glob, re

def _builder_path():
    cache = os.path.join(os.path.expanduser("~"), ".claude", "plugins",
                         "cache", "requirement-manager", "requirement-manager")
    hits = glob.glob(os.path.join(cache, "*", "skills",
                                  "excalidraw-diagram", "scripts"))
    if not hits:
        raise RuntimeError("excalidraw-diagram skill not found")
    def _ver(p):
        m = re.search(r"(\d+)\.(\d+)\.(\d+)", p)
        return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)
    return max(hits, key=_ver)

sys.path.insert(0, _builder_path())
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
| `Scene(font="normal", sketch=False, background="#ffffff", seed=None, roles=None)` | the canvas (`seed=<int>` → byte-stable file for git; `roles={name:colour}` → semantic fills). `font="hand", sketch=True` for the whiteboard look |
| `s.box(text, x, y, w=160, h=70, fill=…, shape=…, font_size=…, container=…)` | a labelled rectangle (→ node id) |
| `s.ellipse(text, x, y, w, h, …, container=…)` | a labelled ellipse |
| `s.diamond(text, x, y, w, h, …)` | a labelled decision diamond |
| `s.frame(x, y, w, h, dashed=False)` | a container drawn *behind* children (overlap-exempt) |
| **ISO 5807 flowchart shapes** (thin `box` aliases, sized for flowcharts) | |
| `s.process(text, x, y)` / `s.terminator(...)` / `s.decision(...)` | rectangle / stadium (start-end) / diamond |
| `s.data(...)` / `s.predefined_process(...)` / `s.preparation(...)` / `s.connector(...)` | parallelogram / framed box / hexagon / small circle |
| **Auto-layout & grouping** | |
| `s.row(items, x, y, gap=…, connect=…)` | place items left→right → list of ids (`connect=True` chains arrows) |
| `s.column(items, x, y, gap=…, connect=…)` | place items top→down → list of ids |
| `s.grid(items, x, y, cols, …)` | place items in a `cols`-wide grid → list of ids |
| `s.enclose(ids, label=…, pad=…)` | auto-sized frame *behind* those nodes → frame id |
| `s.lane(ids, label)` | a swimlane: solid frame around `ids` with a top-left header |
| `s.align(ids, axis)` / `s.distribute(ids, axis, gap=…)` | tidy already-placed nodes (`axis`: left/right/center_x/top/bottom/center_y; distribute `"x"`/`"y"`) |
| **Poster helpers** (for "how a repo works" diagrams) | |
| `s.section(title) → y` | stack a left-aligned heading *below all existing content*; returns the y to place this region's shapes (no manual `bounds()` math) |
| `s.pipeline(steps, x, y, gap=44, connect=True) → [ids]` | lay out a horizontal flowchart band and chain arrows. Each step is `"text"`, `(text, kind)`, `(text, kind, fill)`, or a dict; `kind` is any ISO shape verb; a step's `label` becomes its outgoing arrow label |
| **Roles, captions, arrows** | |
| `s.role(name, colour)` / `Scene(roles={…})` | declare a semantic fill so `box(fill="agent")` works and `legend()` renders the key |
| `s.legend(entries=None, x, y, title=…)` | colour→meaning key (`entries=[(label, colour),…]`, or omit to use `roles`) — **required when colour encodes a role** |
| `s.glossary(entries, x, y, title=…)` | term→meaning key (`entries=[(term, meaning),…]`) — decode jargon/acronyms; overlap-checked |
| `s.title(text, x, y, size=28, align="left")` | a large free-standing heading |
| `s.label(text, x, y, size=12)` | a small grey caption (e.g. "ONE AGENT") |
| `s.arrow(src, dst, label=…, dashed=…, curve=…, start=…, end="arrow", gap=14)` | a bound arrow node→node |
| `s.free_arrow(p0, p1, …)` | an unbound arrow between two points |
| `s.path(points, label=…, dashed=…, end="arrow")` | an unbound multi-point connector through absolute `(x,y)` points (crossing-free routing) |
| `s.route_under(src, dst, drop=70, label=…, color="grey", dashed=True)` | a connector routed below the row (feedback / backward) |
| **Inspection & save** | |
| `s.bounds()` | `(min_x, min_y, max_x, max_y)` of all shapes — for stacking regions |
| `s.check_arrow_crossings()` | `[(src, dst, crossed), …]` arrows running through an unrelated box |
| `s.check_legend_coverage()` | `[fill, …]` colours used but absent from the `legend()` key (colour-SSOT); `[]` when clean |
| `s.check_text_overflow()` | `[(id, …), …]` boxes whose bound text spills outside the shape |
| `s.check_text_overlaps()` | `[(a, b), …]` captions/labels that overlap each other |
| `s.save(basename, out_dir=".", crossing_check=…, legend_check=…, overflow_check=…, text_overlap_check=…)` | writes both files; **raises if shapes overlap**; each `*_check` is `"warn"` (default, prints) or `"error"` (raises). Use all four at `"error"` for a ship-quality diagram |

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
wrapper-vs-child. Or let `enclose(ids, label=...)` auto-size a frame around
boxes you have already placed (see the `excalidraw_builder.py` smoke test).

## Quality rules — make it understandable with no context (required)

A diagram an outsider can read is not optional polish. Apply these to every
diagram. Rules 1 and 3 are enforced mechanically by
`scripts/test_excalidraw.py`: every example must build with **zero overlapping
shapes, zero arrow crossings, and zero unlegended fills** — that is the
operational definition of a "clean" diagram, not a matter of taste.

1. **Zero overlaps, zero crossings.** `save()` already raises on overlap; for a
   crossing-free guarantee use `route_under()`/`path()` and, when you want it
   enforced, `save(..., crossing_check="error")`.
2. **Title + one-line subtitle.** Open with `s.title(...)` and a one-sentence
   `s.label(...)` stating what the diagram shows and the reading direction
   (e.g. "Left → right: a request enters at Client and exits at Auth").
3. **Legend whenever colour means something.** If any `fill=` encodes a role,
   call `s.legend(...)` (or declare `Scene(roles=…)` then `s.legend()`). Colour
   is the single source of truth for role; the legend lists every colour used.
   An undecodable palette turns the diagram into guesswork. **Enforced:** once a
   `legend()` is rendered, `save()` warns on any fill used but missing from the
   key (`check_legend_coverage()`), so an unlegended colour can't ship silently;
   `save(..., legend_check="error")` makes it a hard failure. Build the key with
   `legend()` — a hand-rolled row of `box()` swatches is invisible to this gate.
   Give each *distinct meaning* its own colour: don't reuse a voice/role colour
   for an unrelated box (e.g. a storage tier), or the legend decodes it wrong.
4. **Label cross-role edges.** Any arrow whose endpoints are different roles (or
   is otherwise non-obvious) carries a short verb phrase (`label="validates"`,
   `"returns token"`). Self-evident same-role edges may stay unlabelled.
5. **Real identifiers as node names, jargon in a glossary.** Name the actual
   file / function / component (`reqmap.py`, `check_overlaps()`), never
   "Service A" / "Module". When a label must use an acronym or project term a
   newcomer can't decode (`SSOT`, `dogfood`, `CI action`, `@v1`), add a
   `s.glossary([(term, meaning), …])` box next to the legend (bottom, outside the
   main region) so every term is explained on the canvas.
6. **Readable type sizes.** Two tiers suffice — a title size (~28–32) and a body
   size (~14–16). Never go below font_size 12.
7. **Complexity ceiling: ≤20 nodes per region.** Past that, split into a
   high-level overview region and a detail region below (stack with
   `s.bounds()`); never cram 30 boxes into one region.

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

## Worked examples — ❌ → ✅ variants

For each common case, the ❌ shows the mistake that makes a diagram unreadable;
the ✅ is what to do instead. The ✅ is always the smaller amount of code *and*
the clearer picture.

### 1 · Repo architecture ("diagram how this repo works")

❌ One dense region: 30 boxes of every file, arrows everywhere, no legend, no
subtitle. An outsider can't tell entry points from internals, and it trips the
overlap/crossing gates.

```python
# ❌ everything jammed into one region
for f in all_files: s.box(f, rand_x(), rand_y())   # spaghetti, no story
```

✅ Stacked **sections** (one per layer), role colours, one legend + glossary, all
gates on. This is `make_full_architecture.py`.

```python
# ✅ a layered poster — structure / workflow / integration
y = s.section("1 - STRUCTURE   the components")
parts = [s.box("reqmap.py\nparse-scan-gate", 80, y, fill="engine"), ...]
s.enclose(parts, label="requirement-manager plugin")
y = s.section("2 - WORKFLOW   run order (left -> right)")
s.pipeline([("init","process"),("gate","decision"),("map","process")], 80, y)
y = s.section("3 - INTEGRATION   invoked, gated, shipped")
# ... external systems + arrows ...
s.legend(...); s.glossary(...)
s.save("full_architecture", out_dir, crossing_check="error",
       legend_check="error", overflow_check="error", text_overlap_check="error")
```

### 2 · Pipeline / data flow

❌ Hand-placed boxes with guessed x-coordinates that drift into overlaps, arrows
added one by one.

```python
a = s.box("ingest", 0, 0); b = s.box("process", 150, 0)   # gaps by eye -> overlap
s.arrow(a, b); s.arrow(b, c)                               # tedious + error-prone
```

✅ `row(..., connect=True)` (or `pipeline()` for a flowchart band) — even spacing,
arrows auto-chained, returns the ids.

```python
ids = s.row(["ingest", "process", "store"], 0, 0, connect=True, fill="source")
# many steps / a poster band? use the ISO pipeline instead:
ids = s.pipeline([("Start","terminator"),("parse","process"),("Done","terminator")], 80, y)
```

### 2b · Multi-tool repo workflow (one lane per tool)

❌ A repo that bundles several tools/skills drawn as **one** pipeline — it shows
one tool's flow and silently hides the rest.

```python
# repo has 3 skills, but only the engine's flow is drawn:
s.pipeline([("init","process"),("gate","decision"),("map","process")], 80, y)
```

✅ One labelled `lane()` per tool — every tool's real flow is visible, stacked.
*(Only for repos that bundle 2+ distinct tools; a single-tool repo keeps one pipeline.)*

```python
y = s.section("2 - WORKFLOWS   one pipeline per skill")
a = s.pipeline([("init","process"),("gate","decision"),("map","process")], 120, y + 40)
s.lane(a, "requirement-manager - SSOT + drift gate")
b = s.pipeline([("review","data"),("check","process"),("findings","terminator")], 120, y + 210)
s.lane(b, "requirement-quality-review - advisory")
```

### 3 · Parallel agents / sub-agents (the #1 spaghetti source)

❌ N nodes with arrows between each → N×N crossing lines, unreadable.

```python
for w in workers:            # ❌ every dispatch drawn individually
    s.arrow(dispatch, w); s.arrow(w, merge)
```

✅ `grid()` + `enclose()`, then **one arrow in, one arrow out** of the frame.

```python
workers = s.grid([f"agent {i}" for i in range(9)], 900, 120, 3, fill="worker")
group   = s.enclose(workers, label="9 parallel sub-agents")
s.arrow(dispatch, group); s.arrow(group, merge)   # 2 arrows, not 18
```

### 4 · Decision / branch flow

❌ A plain rectangle for the choice and unlabelled branches — the reader can't
tell which arrow is "yes" vs "no".

```python
q = s.box("valid?", x, y)                 # ❌ looks like a step, not a decision
s.arrow(q, ok); s.arrow(q, err)           # which branch is which?
```

✅ A `diamond()` (or `decision` in a pipeline) with **labelled** branches; dashed
for the failure path.

```python
q = s.diamond("token\nvalid?", x, y, fill="gate")
s.arrow(q, ok,  label="yes")
s.arrow(q, err, label="no", dashed=True)
```

### 5 · Feedback loop / backward edge

❌ A right-to-left arrow drawn straight back across the whole flow — it overlaps
every box in between.

```python
s.arrow(gate, resync)        # ❌ gate is downstream of resync -> crosses everything
```

✅ `route_under()` drops below the row and returns, clear of the forward flow;
label it with the trigger.

```python
s.route_under(gate, resync, label="no - fix & re-sync", drop=70)
```

## Output

**Pre-delivery checklist:**

*The builder enforces these — turn the gates to `"error"`:*
- [ ] `save(..., crossing_check="error", legend_check="error", overflow_check="error", text_overlap_check="error")` — no overlaps, crossings, unlegended fills, text overflow, or overlapping captions
- [ ] `Scene(seed=<int>)` if the diagram is committed (byte-stable output)

*You must check these (the builder can't):*
- [ ] Title + one-line subtitle stating what it shows and the reading direction
- [ ] Legend present if colour encodes a role, and it lists every colour used
- [ ] Glossary present if any acronym / project term needs decoding
- [ ] Every cross-role / non-obvious arrow is labelled
- [ ] Node names are real identifiers, not placeholders
- [ ] All three layers covered (internal flow / integration / distribution)
- [ ] No region exceeds ~20 nodes

Then deliver **both** files and tell the user in three short points:
1. **What it shows** — one sentence.
2. **How to read it** — the flow direction / how the regions stack.
3. **Colour legend** — if colour is used.

- `<name>.excalidraw` — drag onto excalidraw.com (or File → Open) to edit.
- `<name>.html` — double-click to open in a browser; "Download .excalidraw"
  button is built in. The HTML loads Excalidraw from a CDN, so viewing it needs
  a network connection the first time; the `.excalidraw` file works fully
  offline.
