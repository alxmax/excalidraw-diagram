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
- **Claude Code**: `~/.claude/plugins/cache/requirement-manager/requirement-manager/<version>/`
- **Other tools**: wherever the plugin was installed; check your tool's plugin docs.

A portable resolver that picks the highest installed semver automatically:

```python
import sys, os, glob, re

def _builder_path():
    # Adapt the base path for your tool's plugin install directory
    cache = os.path.join(os.path.expanduser("~"), ".claude", "plugins",
                         "cache", "requirement-manager", "requirement-manager")
    hits = glob.glob(os.path.join(cache, "*", "skills",
                                  "excalidraw-diagram", "scripts"))
    if not hits:
        raise RuntimeError(
            "excalidraw_builder.py not found — install the requirement-manager plugin"
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
text_overlap_check="error")`.

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

**Four `save()` gates — turn them all to `"error"` for a ship-quality diagram:**
- `crossing_check` — a bound arrow runs through an unrelated box.
- `legend_check` — a fill colour is used but missing from the `legend()`.
- `overflow_check` — bound text is bigger than its box.
- `text_overlap_check` — two captions / labels overlap each other.

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
| `s.pipeline(steps, x, y, gap=44, connect=True) → [ids]` | horizontal flowchart band with chained arrows |
| `s.legend(entries=None, x, y, title=…)` | colour→meaning key |
| `s.glossary(entries, x, y, title=…)` | term→meaning key |
| `s.title(text, x, y, size=28, align="left")` | a large free-standing heading |
| `s.label(text, x, y, size=12)` | a small grey caption |
| `s.arrow(src, dst, label=…, dashed=…, curve=…, end="arrow", gap=14)` | a bound arrow node→node |
| `s.route_under(src, dst, drop=70, label=…)` | a connector routed below the row (feedback) |
| `s.bounds()` | `(min_x, min_y, max_x, max_y)` of all shapes |
| `s.save(basename, out_dir=".", crossing_check=…, legend_check=…, overflow_check=…, text_overlap_check=…)` | writes both files; raises if shapes overlap |

**Colours**: `grey, red, orange, yellow, green, teal, blue, indigo, violet, pink` — or any hex string.

## Quality rules (required)

1. **Zero overlaps, zero crossings.**
2. **Title + one-line subtitle.**
3. **Legend whenever colour means something.**
4. **Label cross-role edges.**
5. **Real identifiers as node names, jargon in a glossary.**
6. **Readable type sizes** — minimum font_size 12.
7. **Complexity ceiling: ≤20 nodes per region.** Past that, split into overview + detail.

## Output

**Pre-delivery checklist:**

*Builder-enforced (turn gates to `"error"`):**
- [ ] `save(..., crossing_check="error", legend_check="error", overflow_check="error", text_overlap_check="error")`
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
