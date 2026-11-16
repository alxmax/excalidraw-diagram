# Worked examples — the shapes a diagram takes

Each case below is a mistake that makes a diagram unreadable, and the smaller,
clearer thing to do instead. Read the one that matches your subject before you
start. `SKILL.md` carries the rules these examples illustrate.

## Diagramming a repo's architecture (the canonical recipe)

When the task is "diagram this repo / how this system works," do **not** invent a
layout from scratch and do **not** emit several files. Produce **ONE** scene of
**stacked layers**, each opened with `s.section(title)` (which auto-stacks below
everything drawn so far — no `bounds()` math). The template is
[`examples/make_full_architecture.py`](../examples/make_full_architecture.py).

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
the *whole* poster, and `s.save(..., gates=Gates.strict())`.

**Colour discipline across layers:** the single legend must decode every layer, so
give each *distinct* meaning its own colour — do not let two layers reuse one
colour for different roles (e.g. an "engine" script and a "model" must differ).
But the budget is small: neutral grey for everything ordinary, the accent for the
headline path and at most two focal nodes, and at most four role colours. Six roles
means two of them are the same role, or not worth a colour; merge them, and let the
shape or the region carry the difference.

**State the plan first.** Before any code, write four lines: the regions in order,
the node count per region (each 12 or fewer), the focal path and its one or two
focal nodes, and what was cut to fit. For example: *regions: structure (6),
workflow (9), integration (7); focus: description → pack() → gates → files, focal
node the gates; cut: the per-file boxes of `references/`, merged into one.*

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
below (9–12 nodes per region, keep labels short, simplicity first, expand-don't-
cram) **always win**: on any tension, split or drop — do not cram. "Elaborate"
means *structurally complete*, not *busy*.

**Fast start:** `discover <repo>` emits exactly this skeleton — a live STRUCTURE
layer plus commented scaffolds for layers 2-6 (the WORKFLOW scaffold shows both a
single pipeline and the per-tool `lane()` pattern). Delete the layers the repo
doesn't need, fill in the rest from the real code, and run it.

## Tips

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
  Put the everyday name first and the file under it: `box("the layout",
  at, sublabel="pack.py")`.
- **Reference columns.** A column that only lists possible values is a legend,
  not a stage; do not draw a long arrow to it across the diagram.
- **The remove test, before delivery.** Can a node be removed? Can two nodes
  merge? Can an arrow go because the layout already says it (the next box in a
  row needs no arrow to say "next")? Can a label go because colour or shape
  already says it? And would a three-column table say the same thing? Then make
  a table, not a diagram.
- **Font & style.** `Scene()` defaults to a normal font with clean outlines —
  the most readable choice for "anyone should understand this". Pass
  `Scene(typeface="hand", sketch=True)` only when the sketchy whiteboard aesthetic
  is wanted. Arrows already start and end a few pixels *outside* each box, so
  heads and tails never touch the shapes.

## ❌ → ✅ variants

For each common case, the ❌ shows the mistake that makes a diagram unreadable;
the ✅ is what to do instead. The ✅ is always the smaller amount of code *and*
the clearer picture.

### 1 · Repo architecture ("diagram how this repo works")

❌ One dense region: 30 boxes of every file, arrows everywhere, no legend, no
subtitle. An outsider can't tell entry points from internals, and it trips the
overlap/crossing gates.

```python
# ❌ everything jammed into one region
for f in all_files: s.box(f, (rand_x(), rand_y()))   # spaghetti, no story
```

✅ Stacked **sections** (one per layer), role colours, one legend + glossary, all
gates on. This is `make_full_architecture.py`.

```python
# ✅ a layered poster — structure / workflow / integration
y = s.section("1 - STRUCTURE   the components")
parts = s.row([("excalidraw_builder.py\nstdlib only", "engine"), ...], (80, y))
s.enclose(parts, label="excalidraw-diagram plugin")
y = s.section("2 - WORKFLOW   run order (left -> right)")
s.pipeline([("layer","process"),("clear?","decision"),("route","process")], (80, y))
y = s.section("3 - INTEGRATION   invoked, checked, shipped")
# ... external systems + arrows ...
s.legend(...); s.glossary(...)
s.save("full_architecture", out_dir, gates=Gates.strict())
```

### 2 · Pipeline / data flow

❌ Hand-placed boxes with guessed x-coordinates that drift into overlaps, arrows
added one by one.

```python
a = s.box("ingest", (0, 0)); b = s.box("process", (150, 0))   # gaps by eye -> overlap
s.arrow(a, b); s.arrow(b, c)                               # tedious + error-prone
```

✅ `row(..., connect=True)` (or `pipeline()` for a flowchart band) — even spacing,
arrows auto-chained, returns the ids.

```python
ids = s.row(["ingest", "process", "store"], (0, 0), connect=True, cell={"paint": "source"})
# many steps / a poster band? use the ISO pipeline instead:
ids = s.pipeline([("Start","terminator"),("parse","process"),("Done","terminator")], (80, y))
```

### 2b · Multi-tool repo workflow (one lane per tool)

❌ A repo that bundles several tools/skills drawn as **one** pipeline — it shows
one tool's flow and silently hides the rest.

```python
# repo has 3 skills, but only the engine's flow is drawn:
s.pipeline([("init","process"),("gate","decision"),("map","process")], (80, y))
```

✅ One labelled `lane()` per tool — every tool's real flow is visible, stacked.
*(Only for repos that bundle 2+ distinct tools; a single-tool repo keeps one pipeline.)*

```python
y = s.section("2 - WORKFLOWS   one pipeline per tool")
a = s.pipeline([("ingest","data"),("validate","decision"),("store","process")], (120, y + 40))
s.lane(a, "api  -  takes the request, writes the record")
b = s.pipeline([("poll","process"),("render","process"),("upload","terminator")], (120, y + 210))
s.lane(b, "worker  -  picks the job up later, renders it")
```

### 3 · Parallel agents / sub-agents (the #1 spaghetti source)

❌ N nodes with arrows between each → N×N crossing lines, unreadable.

```python
for w in workers:            # ❌ every dispatch drawn individually
    s.arrow(dispatch, w); s.arrow(w, merge)
```

✅ `grid()` + `enclose()`, then **one arrow in, one arrow out** of the frame.

```python
workers = s.grid([f"agent {i}" for i in range(9)], (900, 120), 3, cell={"paint": "worker"})
group   = s.enclose(workers, label="9 parallel sub-agents")
s.arrow(dispatch, group); s.arrow(group, merge)   # 2 arrows, not 18
```

### 4 · Decision / branch flow

❌ A plain rectangle for the choice and unlabelled branches — the reader can't
tell which arrow is "yes" vs "no".

```python
q = s.box("valid?", (x, y))               # ❌ looks like a step, not a decision
s.arrow(q, ok); s.arrow(q, err)           # which branch is which?
```

✅ A `diamond()` (or `decision` in a pipeline) with **labelled** branches; dashed
for the failure path, and both at right angles: `elbow=True` leaves the diamond on
the side facing each branch and turns once, so neither runs on a diagonal and each
gets its own attach point.

```python
q = s.diamond("token\nvalid?", (x, y), paint="accent")    # the focal decision
s.arrow(q, ok,  label="yes", elbow=True)
s.arrow(q, err, label="no", paint=DASHED, elbow=True)
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
s.box("pack()", (x, y), paint="violet")             # ❌ what is it? why violet?
s.box("barycenter ordering", (x2, y), paint="orange")   # ❌ jargon, undefined
```

✅ A teaching diagram, read top to bottom: a subtitle that says what it is and
how to read it, ONE takeaway line under it (what the reader should remember),
everyday words in the boxes with the real file beneath as a sublabel, one
`section()` per idea ("the problem", "how you use it", "what is inside"), the main
path numbered ①②③ and drawn in the accent, at most two margin notes that say
*why*, and a `legend()` + `glossary()` that decode every colour and term. This is
`make_explainer.py`.

```python
s.title("excalidraw-diagram — how it works", (40, -140), font=32)
s.label("A tool that turns a DESCRIPTION of a system into a PICTURE of it. Read top "
        "to bottom; follow the orange path ① to ⑤.", (40, -96), font=Font(15, align="left"))
s.takeaway("you say what the parts are; the tool places them and refuses to hand "
           "you a picture nobody can read.", (40, -62))
y = s.section("2 - HOW YOU USE IT")
ids = s.pipeline([("describe the\nparts", "process", "words"),
                  {"text": "readable?", "kind": "decision", "paint": "accent", "label": "yes"},
                  ("two files", "terminator", "output")],
                 (120, y + 30), gap=150, numbered=True, line="accent")
s.note("Why two files? The .excalidraw stays editable; the .html opens anywhere.",
       ids[-1])                        # in the margin, on a dashed leader
```

```python
y = s.section("3 - WHAT'S INSIDE   (everyday name on top, the real file below)")
s.box("where boxes go", (740, y, 250, 70), paint="engine", sublabel="pack()")
s.box("the checks", (1070, y, 250, 70), paint="accent", sublabel="gates.py")
s.legend([("The focus: the path, and where it decides", "accent"), ...], (60, ly))
s.glossary([("gate", "a check that refuses an unreadable diagram"), ...], (560, ly))
```

### 7 · Timing / waveform diagram (there is no waveform primitive)

❌ Reaching for a feature the builder does not have, or drawing each level change
as a bound `arrow()` between tiny boxes. The first does not exist; the second
produces hundreds of nodes and a layout the gates spend their time re-checking.

```python
s.waveform(["clk", "mosi"], ...)          # ❌ no such call, and none is planned
s.arrow(bit0, bit1)                       # ❌ a trace is one polyline, not N arrows
```

✅ One unbound polyline per signal and one `box()` per bus cell, both on a grid
you compute yourself. `path(points, heads="none")` draws the trace; the value
cells sit at exact `(x, y, w, h)` so they abut. Keep the explainer shape — title,
reading direction, `legend()` for what the colours mean, `glossary()` for
`t_deb`, `MOSI`, `Dem`. This is `make_timing_diagrams.py` and
`make_autosar_timing.py`.

```python
X0, W, ROW_H = 220, 64, 36                      # time origin, bit slot, band height

def trace(levels, top):                         # one 0/1 level per slot
    y = lambda v: top if v else top + ROW_H
    pts = [(X0, y(levels[0]))]
    for i in range(1, len(levels)):
        if levels[i] != levels[i - 1]:          # a vertical edge, then the new level
            pts += [(X0 + i * W, y(levels[i - 1])), (X0 + i * W, y(levels[i]))]
    pts.append((X0 + len(levels) * W, y(levels[-1])))
    s.path(pts, heads="none")
    assert all(top <= py <= top + ROW_H for _, py in pts), "trace left its band"
    return pts
```

**Assert your own geometry.** An unbound `path()` registers no node, so three of
the seven gates never see it: no overlap, no crossing and no legend check applies
to a trace. The generator carries the checks the gates cannot — every clock edge
lands on the bit grid, every trace stays inside its row — and a failed `assert`
stops the run exactly as a gate would. A timing diagram whose traces drift is
wrong in a way the file format cannot report.

### 8 · Sequence, state and entity-relationship diagrams (no new primitives)

❌ Treating each one as a flowchart: `pack()` a sequence diagram and time order
disappears; draw an entity as one box and its columns become a caption.

✅ Pick the primitive that carries the meaning.

- **Sequence** — `make_sequence_diagram.py`. A participant is a `box()`, its
  lifeline an unbound `path(heads="none")`, a message a horizontal `path()` between
  two lifelines (dashed for a reply), an `alt` fragment a `frame()` with `[guard]`
  labels. Assert that every message ends on a lifeline and that messages run strictly
  downwards: no gate sees an unbound path.
- **State machine** — `make_state_machine.py`. States and events are a graph, so
  `pack()` lays them out; a transition back to an earlier state is routed on its own.
  Assert that every state is reachable and every non-final state has a way out.
- **Entity-relationship** — `make_er_diagram.py`. An entity is a coloured header
  `box()` over a body `box()` listing its columns; a relationship is an `arrow(...,
  heads="none")` labelled `1 x : N y`. Join a table lower down at its header, or the
  line cuts through it. Assert that every foreign key has a relationship and back.

```python
x_of = {"browser": 145, "api": 395}             # one lifeline per participant
s.path([(x_of["browser"], y), (x_of["api"], y)])                 # a request
s.path([(x_of["api"], y + 58), (x_of["browser"], y + 58)],
       paint=Paint(dashed=True))                                  # its reply
```

## Anti-patterns — refuse these on sight

Each one makes a diagram harder to read while every gate can still pass. The design
gates catch some of them (`focus`, `orthogonal`, `node_budget`); the rest are yours
to catch in the pre-delivery checklist.

- **Identical boxes for every node.** Same size, same colour, same weight: nothing
  says where to look. Neutral grey for the ordinary, the accent for the one or two
  that matter, the sublabel tier for detail.
- **Rainbow colouring.** A colour per node, or per file type nobody asked about.
  At most four role colours, each in the legend; the `focus` gate counts them.
- **More than two accents.** If you want to accent four things, you have not decided
  what matters yet. The `focus` gate counts accent-coloured shapes.
- **Shadows, gradients, 3D.** Excalidraw draws none of them on purpose; a fake drop
  shadow (a second offset box) is two overlapping shapes and a reader sees two.
- **Labels sitting on the line.** A label belongs on its connector's middle leg with
  clear line both sides (`label_fit` measures it), never across a box or a junction.
- **A legend floating inside the diagram.** The legend and glossary sit below or
  beside the diagram, outside every region, never between two boxes.
- **Vertical text.** Nobody tilts their head. Widen the box, wrap the label, or move
  the detail into a caption.
- **Diagonal connectors.** They read as noise beside right angles and cross more:
  `arrow(..., elbow=True)`, `PackOptions(edge_style="orthogonal")`. The `orthogonal`
  gate names every bound arrow with a diagonal leg.
- **Placeholder names.** "Service A", "Module 1", "Component": the reader learns
  nothing. Name the real file, function or system, and decode jargon in the glossary.
