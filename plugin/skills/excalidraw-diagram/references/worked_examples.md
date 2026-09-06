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
the *whole* poster, and `s.save(..., crossing_check="error", legend_check="error",
overflow_check="error", text_overlap_check="error", label_fit_check="error")`.

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
- **Font & style.** `Scene()` defaults to a normal font with clean outlines —
  the most readable choice for "anyone should understand this". Pass
  `Scene(font="hand", sketch=True)` only when the sketchy whiteboard aesthetic
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
for f in all_files: s.box(f, rand_x(), rand_y())   # spaghetti, no story
```

✅ Stacked **sections** (one per layer), role colours, one legend + glossary, all
gates on. This is `make_full_architecture.py`.

```python
# ✅ a layered poster — structure / workflow / integration
y = s.section("1 - STRUCTURE   the components")
parts = s.row([("excalidraw_builder.py\nstdlib only", "engine"), ...], 80, y)
s.enclose(parts, label="excalidraw-diagram plugin")
y = s.section("2 - WORKFLOW   run order (left -> right)")
s.pipeline([("layer","process"),("clear?","decision"),("route","process")], 80, y)
y = s.section("3 - INTEGRATION   invoked, checked, shipped")
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
y = s.section("2 - WORKFLOWS   one pipeline per tool")
a = s.pipeline([("ingest","data"),("validate","decision"),("store","process")], 120, y + 40)
s.lane(a, "api  -  takes the request, writes the record")
b = s.pipeline([("poll","process"),("render","process"),("upload","terminator")], 120, y + 210)
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
s.box("pack()", x, y, fill="violet")             # ❌ what is it? why violet?
s.box("barycenter ordering", x2, y, fill="orange")   # ❌ jargon, undefined
```

✅ A teaching diagram, read top to bottom: a subtitle that says what it is and
how to read it, everyday words in the boxes, one `section()` per idea
("the problem", "how you use it", "what is inside"), and a `legend()` +
`glossary()` that decode every colour and term. This is `make_explainer.py`.

```python
s.title("excalidraw-diagram — how it works", 40, -96, size=32)
s.label("A tool that turns a DESCRIPTION of a system into a PICTURE of it, and "
        "refuses to hand you one that cannot be read. Read top to bottom. Every "
        "special word is explained in the Glossary at the bottom.",
        40, -52, size=15, align="left")
y = s.section("1 - THE PROBLEM IT SOLVES")
know = s.box("What someone\nUNDERSTANDS\nabout a system", 120, y, fill="words")
draw = s.box("What a diagram\nof it would show", 880, y, fill="outside")
s.arrow(know, draw, dashed=True, color="red",
        label="the picture nobody has the afternoon to draw")
# ... 2 - HOW YOU USE IT, 3 - WHAT'S INSIDE, 4 - WHERE IT RUNS ...
s.legend([...]); s.glossary([("gate", "a check that refuses an unreadable diagram"), ...])
```
