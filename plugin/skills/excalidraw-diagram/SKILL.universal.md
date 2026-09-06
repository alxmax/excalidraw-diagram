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
  editable diagram is wanted — and when someone does not understand a system
  and a picture would teach it: "explain how X works", "I don't understand X",
  "nu înțeleg cum merge X", "walk me through this". Produces a valid .excalidraw
  file that imports into excalidraw.com plus a browser-openable .html.
---

<!-- Universal variant: Claude Code-specific tool invocations and plugin-cache
     path resolvers removed. Works with any AI assistant that can run shell
     commands and read files. -->

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
   legend_check="error", overflow_check="error", text_overlap_check="error",
   label_fit_check="error")`) turn those rules into hard failures so a sloppy
   diagram can't ship.

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
- **"Explain how X works" / "I don't understand X"** — the asker wants to
  *learn* the system, not just see it. Build a teaching diagram: everyday words
  in the boxes, a stated reading direction, a legend and a glossary that decode
  every colour and term on the canvas. The template is
  [`examples/make_explainer.py`](examples/make_explainer.py); worked example 6
  below shows the shape.

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
script against the `Scene` API and run it. The CLI has two helper verbs plus the self-test:

| Command | What it does | When to pick it |
|---|---|---|
| `python scripts/excalidraw_builder.py` | run the builder self-test (smoke test) | verifying the builder still works |
| `python scripts/excalidraw_builder.py render <scene.excalidraw> [out_dir]` | rebuild the self-contained `.html` viewer from an **existing** scene file | you edited a `.excalidraw` on excalidraw.com and want a fresh viewer (no generator script to re-run) |
| `python scripts/excalidraw_builder.py discover <repo> [out.py]` | scan a repo → emit a **runnable multi-layer poster stub** | starting a repo-architecture diagram — scaffold the layers, fill in the real content, run it |

**Menu (how to start a diagram):**
- **New diagram (from a description)** — write a Python generator against the `Scene` API (the Workflow below), then run it.
- **Scaffold from a repo** — `discover <repo>` to emit `make_diagram.py` pre-seeded as a multi-layer poster; keep the layers the repo needs, fill in the real content, then run it.
- **Re-run / extend your generator** — re-execute (or edit, then re-execute) the existing `make_diagram.py`.
- **Re-render the viewer only** — `render <scene.excalidraw>` to regenerate the `.html` for a scene edited elsewhere.
- **Self-test** — `python scripts/excalidraw_builder.py` with no args runs the builder smoke test.

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

   **Large repo? Fan out the exploration (optional).** After the README pass,
   count source files (excluding `node_modules/`, `.git/`, `__pycache__/`):
   - **≤ 80 source files** → explore sequentially; do not spawn sub-agents.
   - **> 80 source files** → if your tool supports parallel sub-agents, dispatch
     3 read-only agents in parallel (one per lens below), then synthesise their
     results. Otherwise explore sequentially, focusing on entry points first.

     | Lens | Gathers |
     |---|---|
     | structure + entry-points | source dirs; entry points (`main`/`run`/`app`/`index`/`cli`); package manifests |
     | data-flow + integration | imports/calls between modules, external touch-points (APIs, DBs, queues, CI) |
     | distribution + packaging | CI/deploy/packaging files (`.github/*.yml`, `Dockerfile`, manifests) |

     Each sub-agent returns a compact JSON (≤ 60 lines): `components`
     (real file/module names — never placeholders like "ServiceA"), directed
     `edges` (`{src, dst, label}` with a verb like calls/imports/reads/deploys),
     and its `group`. The main agent merges the outputs, dedups by id, then
     proceeds to layout.

2. **Plan the layout on paper first** (see Layout rules below). List every
   column, its x position, and all arrows. Verify no arrow crosses an unrelated
   box before writing a single line of code.
3. **Pick a layout.** Left-to-right for pipelines and data flow; top-down for
   hierarchies; grouped frames for "one box contains several things". Choose
   explicit coordinates — the builder does not auto-layout. Keep ≥80px gaps
   between columns and ≥30px between boxes in the same column.
4. **Write a short generator script** that imports the builder, declares the
   shapes and arrows, and calls `.save(basename, out_dir)`. See
   `examples/make_full_architecture.py` for a complete, non-trivial example.
5. **Run it.** `save()` raises if any shapes overlap — fix the coordinates and
   re-run until it passes. Then **present both files**.
6. If you want to sanity-check the layout before presenting, you can render a
   quick preview — but the `.excalidraw` itself is the source of truth.

### Importing the builder

**Inside the plugin** (e.g. an `examples/` script): use a relative path.

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from excalidraw_builder import Scene
```

**In an external repo** (a generator script that lives in your own project):
locate `excalidraw_builder.py` inside the plugin's installed directory and add
it to `sys.path`. The builder lives at:

```
<plugin-install-dir>/skills/excalidraw-diagram/scripts/excalidraw_builder.py
```

Where `<plugin-install-dir>` depends on your tool:
- **Claude Code**: `~/.claude/plugins/cache/excalidraw-diagram/excalidraw-diagram/<version>/`
- **Other tools**: wherever the plugin was installed; check your tool's plugin docs.

A portable resolver that picks the highest installed semver automatically:

```python
import sys, os, glob, re

def _builder_path():
    # Adapt the base path for your tool's plugin install directory
    cache = os.path.join(os.path.expanduser("~"), ".claude", "plugins",
                         "cache", "excalidraw-diagram", "excalidraw-diagram")
    hits = glob.glob(os.path.join(cache, "*", "skills",
                                  "excalidraw-diagram", "scripts"))
    if not hits:
        raise RuntimeError(
            "excalidraw_builder.py not found — install the excalidraw-diagram plugin"
        )
    def _ver(p):
        m = re.search(r"(\d+)\.(\d+)\.(\d+)", p)
        return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)
    return max(hits, key=_ver)

sys.path.insert(0, _builder_path())
from excalidraw_builder import Scene
```

**Never hardcode a version number** in the path — the cache may keep every
version ever installed and the script will silently use the old API after any update.

### Minimal example

```python
import sys, os, glob, re

def _builder_path():
    cache = os.path.join(os.path.expanduser("~"), ".claude", "plugins",
                         "cache", "excalidraw-diagram", "excalidraw-diagram")
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

### Diagramming a repo's architecture (the canonical recipe)

When the task is "diagram this repo / how this system works," produce **ONE** scene of
**stacked layers**, each opened with `s.section(title)`. The template is
[`examples/make_full_architecture.py`](examples/make_full_architecture.py).

**You decide which layers this repo needs.** Include a layer **only when its
condition holds**, in this order, all in the one scene:

| Layer | Include when… | Build it with |
|---|---|---|
| **1. STRUCTURE** | always | role-coloured `box()`es + one `enclose()` |
| **2. WORKFLOW** | the repo has a pipeline / run-order / algorithm | `s.pipeline([...])` (ISO shapes) + `route_under()` for feedback — **one `s.lane()` per tool** if the repo bundles several |
| **3. INTEGRATION** | it is invoked by / connects to external systems, CI, or has a loop | `box()`es + labelled `arrow()`s |
| **4. MODES / VARIANTS** | it has modes / strategies / variants of the same flow | one self-contained `column()`+`enclose()` per mode |
| **5. MODEL / RUNNERS** | parts run on different models / workers / runtimes | group → `arrow()` → a runtime/model box |
| **6. DATA / SCHEMA** | it produces a core record / output shape | a record `box()` + enum/annotation satellites |

Then **one** `s.legend(...)` and **one** `s.glossary(...)` decode the whole poster,
and `s.save(..., crossing_check="error", legend_check="error", overflow_check="error",
text_overlap_check="error", label_fit_check="error")`.

### Layout rules (apply before writing code)

**Parallel groups — the most common source of spaghetti arrows**

When N nodes run simultaneously: place them with `grid()`/`row()` and wrap with
`enclose()`, then draw **one arrow in** to the frame and **one arrow out**.

**Column gaps**: every column must have ≥80px clearance on each side.

**Arrow crossing check**: before coding every arrow, draw an imaginary straight
line from source centre to target centre. If it passes through any unrelated box,
the layout is wrong — restructure or use `route_under()`.

**Backward / feedback arrows**: always use `route_under()` (goes below the row,
then back) or omit and add a text `label()` noting the feedback.

**Box sizing**: size boxes to fit their text. Use these starting estimates:
- Height: `h ≥ num_lines × font_size × 1.6 + 16`
- Width:  `w ≥ max_line_length_chars × font_size × 0.65 + 20`

**One file, many diagrams**: always produce ONE `.excalidraw` + ONE `.html` per
request. If a system needs several views, stack them as labelled regions in the
*same* scene.

**Expand, don't cram**: the canvas is unlimited. Spread out rather than shrinking
fonts or overlapping shapes.

**Five `save()` gates — turn them all to `"error"` for a ship-quality diagram:**
- `crossing_check` — a bound arrow runs through an unrelated box.
- `legend_check` — a fill colour is used but missing from the `legend()`.
- `overflow_check` — bound text is bigger than its box.
- `text_overlap_check` — two captions / labels overlap each other.
- `label_fit_check` — a bound arrow's label is wider than its connector (crowds
  the arrowheads or spills onto the joined boxes); the dedicated gate for arrow
  labels, which the two checks above exclude.

## Builder API (cheat-sheet)

| Call | Draws |
| --- | --- |
| `Scene(font="normal", sketch=False, background="#ffffff", seed=None, roles=None)` | the canvas |
| `s.box(text, x, y, w=160, h=70, fill=…, shape=…, font_size=…, container=…)` | a labelled rectangle |
| `s.ellipse(text, x, y, w, h, …, container=…)` | a labelled ellipse |
| `s.diamond(text, x, y, w, h, …)` | a labelled decision diamond |
| `s.frame(x, y, w, h, dashed=False)` | a container drawn *behind* children |
| `s.process(text, x, y)` / `s.terminator(...)` / `s.decision(...)` | ISO 5807 shapes |
| `s.row(items, x, y, gap=…, connect=…)` | place items left→right |
| `s.column(items, x, y, gap=…, connect=…)` | place items top→down |
| `s.grid(items, x, y, cols, …)` | place items in a grid |
| `s.enclose(ids, label=…, pad=…)` | auto-sized frame *behind* those nodes |
| `s.lane(ids, label)` | a swimlane with a top-left header |
| `s.section(title) → y` | stack a heading below all existing content; returns the y to start this region |
| `s.pipeline(steps, x, y, gap=80, connect=True) → [ids]` | horizontal flowchart band with chained arrows. Recommended gap: ≥80px for labeled arrows, ≥100px for multi-word labels |
| `s.legend(entries=None, x, y, title=…)` | colour→meaning key |
| `s.glossary(entries, x, y, title=…)` | term→meaning key |
| `s.title(text, x, y, size=28, align="left")` | a large free-standing heading |
| `s.label(text, x, y, size=12)` | a small grey caption |
| `s.arrow(src, dst, label=…, dashed=…, curve=…, end="arrow", gap=14)` | a bound arrow node→node |
| `s.route_under(src, dst, drop=70, label=…)` | a connector routed below the row (feedback) |
| `s.bounds()` | `(min_x, min_y, max_x, max_y)` of all shapes |
| `s.save(basename, out_dir=".", crossing_check=…, legend_check=…, overflow_check=…, text_overlap_check=…)` | writes both files; raises if shapes overlap |

**Colours**: `grey, red, orange, yellow, green, teal, blue, indigo, violet, pink` — or any hex string.

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
       legend_check="error", overflow_check="error", text_overlap_check="error",
       label_fit_check="error")
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

### 6 · "Explain how X works" (the reader does not know the system)

❌ An accurate architecture poster for an insider: file names in every box,
project jargon unexplained, colours with no key. The asker still does not
understand it — the diagram is correct and teaches nothing.

```python
s.box("reqmap.py", x, y, fill="violet")          # ❌ what is it? why violet?
s.box("SSOT drift gate", x2, y, fill="orange")   # ❌ two undefined terms in one box
```

✅ A teaching diagram, read top to bottom: a subtitle that says what it is and
how to read it, everyday words in the boxes, one `section()` per idea
("the problem", "how you use it", "what is inside"), and a `legend()` +
`glossary()` that decode every colour and term. This is `make_explainer.py`.

```python
s.title("requirement-manager — how it works", 40, -96, size=32)
s.label("A tool that stops a project's PLAN and its CODE from quietly drifting "
        "apart. Read top to bottom. Every special word is explained in the "
        "Glossary at the bottom.", 40, -52, size=15, align="left")
y = s.section("1 - THE PROBLEM IT SOLVES")
plan = s.box("What the project
SHOULD do
(the plan)", 120, y, fill="plan")
code = s.box("What the code
ACTUALLY does", 880, y, fill="outside")
s.arrow(plan, code, dashed=True, color="red", label="over time they silently disagree = 'drift'")
# ... 2 - HOW YOU USE IT, 3 - WHAT IS INSIDE ...
s.legend([...]); s.glossary([("drift", "plan and code no longer say the same thing"), ...])
```

## Output

**Pre-delivery checklist:**

*Builder-enforced (turn gates to `"error"`):**
- [ ] `save(..., crossing_check="error", legend_check="error", overflow_check="error", text_overlap_check="error", label_fit_check="error")`
- [ ] `Scene(seed=<int>)` if the diagram is committed (byte-stable output)

*You must check these:*
- [ ] Title + one-line subtitle
- [ ] Legend present if colour encodes a role
- [ ] Glossary present if any acronym / project term needs decoding
- [ ] Every cross-role / non-obvious arrow is labelled
- [ ] Node names are real identifiers, not placeholders
- [ ] All three layers covered (internal flow / integration / distribution)
- [ ] No region exceeds ~20 nodes

Then deliver **both** files:
- `<name>.excalidraw` — drag onto excalidraw.com to edit.
- `<name>.html` — double-click to open in a browser. Loads Excalidraw from a CDN (needs network on first open); the `.excalidraw` works fully offline.
