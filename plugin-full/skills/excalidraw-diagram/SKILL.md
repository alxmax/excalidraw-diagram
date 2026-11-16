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

# Excalidraw diagram

Turn a description of a system into a real **Excalidraw scene** (`.excalidraw`)
plus a **self-contained HTML viewer** (`.html`) — genuine Excalidraw, editable,
not a screenshot. The scene drag-and-drops into
[excalidraw.com](https://excalidraw.com); the viewer opens by double-click.

**You never hand-write Excalidraw JSON.** `scripts/excalidraw_builder.py` owns the
format's invariants (seeds, nonces, two-way bindings) and emits both files in one
`.save()`. [`references/builder_api.md`](references/builder_api.md): every call, how to
import it, the `graph.json` schema.
[`references/worked_examples.md`](references/worked_examples.md): the repo-poster recipe,
the ❌ → ✅ variants and the anti-patterns.

## The goal (read this first)

**Produce a schematic an outsider can understand with no prior context** — one
that shows *how the system actually works*: its real components, the flow between
them, how it is invoked, how it ships. For a repo that means *that repo's* files
and flow, never a generic template. Pretty-but-shallow fails. Three things pass:

1. **Substance** — real identifiers (`excalidraw_builder.py`, `pack()`), the actual
   workflow, and every layer (internal flow → integration → distribution) that
   carries information for *this* reader; a layer that tells them nothing stays out.
2. **Readability** — title + one-line subtitle, one focus, a legend when colour
   means a role, a glossary for jargon, one reading direction, zero overlaps/crossings.
3. **Enforcement** — the builder's gates turn those rules into hard failures, so
   a sloppy diagram cannot ship.

## When to use

- "Make an Excalidraw / whiteboard / hand-drawn diagram of …"
- "Diagram this repo's architecture" / "schemă excalidraw pentru …"
- Flowcharts, pipelines, multi-agent layouts, module maps, state flows.
- "Put the diagram in an HTML I can open / share."
- **"Explain how X works" / "I don't understand X"** — the most common case. The
  asker wants to *learn* the system. Build a teaching diagram: everyday words in the
  boxes, a stated reading direction, a legend and a glossary that decode every colour
  and term on the canvas, the main path numbered ①②③ (`pipeline(numbered=True)`),
  ONE `takeaway()` line under the subtitle, and at most two margin `note()`s saying
  *why*, each on a dashed leader to its element. Template: [`examples/make_explainer.py`](examples/make_explainer.py);
  worked example 6 in `references/worked_examples.md` shows the shape.
- Not this, if they want a static image with no sketch aesthetic — but if they
  said Excalidraw, use this.

## Two ways in

| Path | Use it when | How |
|---|---|---|
| **`scene --from-json`** | the subject is a graph you can describe — parts and connections — and you do not care where each box lands; a Mermaid flowchart already is one, so translate it with `references/mermaid_to_graph.md` rather than pasting an image | write `graph.json` (schema in `references/builder_api.md`) with `"edge_style": "orthogonal"`, then `python scripts/excalidraw_builder.py scene --from-json graph.json -o out/` (`python3` where there is no `python`); add `--svg` for a clean-line `.svg` too |
| **A generator script** | the layout itself carries meaning: stacked layers, a lane per tool, a poster | write Python against the `Scene` API — position as `at=(x, y)`, colour as `paint=`, type as `font=` — and run it |

Three more verbs: `render <scene.excalidraw> [out_dir]` rebuilds the `.html` for a scene edited elsewhere; `discover <repo> [out.py]` scaffolds a poster stub; `data-model --from-ddl <schema.sql> | --from-dbt <project> [--mapping map.md] [--lineage] [-o out/] [--name Title] [--columns] [--roles roles.yml]` draws SQL tables or dbt models with roles and amber review notes, and a dbt project can also write a source-to-target mapping (`references/builder_api.md`).
**No arguments is the smoke test CI depends on — never shadow it.** An MCP client gets every verb but `data-model` as a tool (`build_scene`, `render_html`, `discover_repo`, `graph_schema`).

## Workflow

1. **Understand the thing to draw.** For a repo, read its README and file layout
   first, so the diagram shows the *actual* components and flow. Identify the
   nodes, the directed connections, the grouping, the reading direction. For an
   architecture diagram audit the three layers — *internal flow* (steps, modes,
   decision gates), *integration* (entry points, external systems, state) and
   *distribution* (install, package, deploy) — and keep each one only when it
   carries information for this reader.

   **Large repo? Fan out (optional).** Count source files with a `Glob` (excluding
   `node_modules/`, `.git/`, `__pycache__/`). At **≤ 80, or with no `Agent` tool**,
   explore sequentially. Past that, dispatch read-only `Explore` subagents **in
   parallel**, 3 by default (never more than 5), one per lens: **sonnet** for
   *data-flow + integration*, **haiku** for *structure + entry-points* and
   *distribution + packaging*. Each returns **≤ 60 lines** of JSON — `components` (real
   file names, never "ServiceA"), directed `edges` (`{src, dst, label}` with a verb),
   its `group`. Merge, **dedup by id**, and never re-read a file a subagent covered.

2. **Choose the path.** Describable as nodes and edges → `graph.json`. Layout
   carries meaning → a generator script.
3. **State the plan before drawing.** Before any JSON or code, write down the
   regions, the node count per region, the focal path and its focal nodes, and
   what you cut to stay in budget. Then plan the layout (see Layout rules):
   every column, its x, every arrow, none crossing an unrelated box.
4. **Write it.** Name a generator `make_diagram.py` — **never
   `make_<projectname>.py`**: the project is implicit from the directory and the
   `basename` you pass to `.save()`, and a subject-specific name blocks reuse.
5. **Run it.** `save()` raises on overlap — fix and re-run until it passes, then
   **present both files**, `.excalidraw` first.

## Layout rules (they hold on both paths; `pack()` already obeys them)

- **Parallel groups.** When N nodes do the same thing at once, place them with
  `grid()`/`row()`, wrap with `enclose()`, and draw **one arrow in and one out**
  of the frame. Arrows between members are the biggest source of spaghetti.
- **Column gaps.** Every column needs ≥80px clearance each side:
  `col_x[i+1] ≥ col_x[i] + col_width[i] + 80`.
- **Right angles, never diagonals.** Draw `arrow(..., elbow=True)` and pack with
  `PackOptions(edge_style="orthogonal")` — the recommended style, opt-in only so
  existing layouts keep their shape. Connectors sharing a side each get their own
  attach point. Trace every leg first: one that cuts a box that is neither end
  means restructure or `route_under()`.
- **Backward / feedback arrows.** A right-to-left arrow crosses the whole
  forward flow. Always `route_under()` (below the row and back), or drop it and
  note the feedback in a `label()`.
- **Box sizing.** `h ≥ lines × size × 1.6 + 16`, `w ≥ longest_line_chars × size × 0.65 + 20`
  (the `overflow` gate confirms). Labels of 2–3 words; detail in a `label()` caption.
- **One file, many diagrams.** ONE `.excalidraw` + ONE `.html` per request, from
  a single `.save()`. Several views stack as labelled regions in the *same* scene
  (`section()`, or `bounds()` + ~80px). Calling `save()` twice raises
  `RuntimeError`, so splitting into several files fails at once.
- **Frame and group captions** sit ≥24px ABOVE the frame's top edge
  (`y = frame_y - 24`), never on the border; keep free `label()` text ≥16px clear
  of every shape and arrowhead.
- **Committing the diagram?** Pass `Scene(seed=<int>)` for byte-identical re-runs.

## Quality rules — make it understandable with no context (required)

Not optional polish. `scripts/test_excalidraw.py` builds every example with zero
overlaps, zero crossings, zero unlegended fills and every design gate clean. That
is the operational definition of "clean", not a matter of taste.

1. **Zero overlaps, zero crossings.** `save()` raises on overlap already; for
   crossings use `route_under()`/`path()` and `Gates(crossing="error")`.
2. **Title + one-line subtitle.** Open with `s.title(...)` and one `s.label(...)`
   sentence saying what the diagram shows and its reading direction.
3. **One focus.** Fills default to neutral grey. One accent colour
   (`paint="accent"`) marks the headline path and at most 2 focal nodes. Role
   colours, at most 4, appear only where colour carries a meaning the legend
   explains. If you want to accent four things, you have not decided what matters yet.
4. **Legend whenever colour means something.** If any `paint=` encodes a role, call
   `s.legend(...)` (or `Scene(roles=…)` then `s.legend()`), listing every colour
   used, one colour per *distinct meaning*. Once a legend is rendered, `save()` flags
   any fill missing from it (`Gates(legend="error")` makes that fatal); a
   hand-rolled row of swatches is invisible to the gate.
5. **Label cross-role edges.** Any arrow whose ends are different roles, or is
   otherwise non-obvious, carries a short verb phrase (`label="validates"`).
6. **Real identifiers as node names, jargon in a glossary.** Name the actual file
   / function / component (`save()`, `check_overlaps()`), never "Service A". A term
   a newcomer cannot decode (`back edge`, `@v1`) goes in `s.glossary([(term, meaning), …])`
   beside the legend, so every term is explained on the canvas.
7. **Two-tier node text.** The name in the body font; the technical detail (file,
   port, command) beneath it with `box(..., sublabel=...)` — code typeface, ~12px,
   separate text the overflow and text-overlap checks judge.
8. **Readable type sizes.** A title size (~28–32) and a body size (~14–16), plus
   that sublabel tier. Never below 12px.
9. **Node budget: 9–12 nodes per region.** Past 12, split into an overview region
   and a detail region below. The canvas is unlimited: expand, never cram or shrink.

**The seven gates**, each set in one `Gates` value to `"error"` (raises), `"warn"`
(prints) or `"off"`. `overlap` and `short_arrows` (an arrow too short to draw) default
to `"error"`; `crossing`, `legend`, `overflow` (bound text bigger than its shape),
`text_overlap` (captions on each other) and `label_fit` (an arrow label wider than its
connector) to `"warn"`. Ship with `Gates.strict()`. Three **design gates** judge
hierarchy and only warn, under `strict()` too: `focus` (rule 3), `node_budget`
(rule 9, per region or frame) and `orthogonal` (a bound arrow with a diagonal leg).

## Output

**Pre-delivery checklist.**

*The builder enforces these:*
- [ ] `save(..., gates=Gates.strict())`
- [ ] `Scene(seed=<int>)` if the diagram is committed

*You must check these — the builder cannot:*
- [ ] Title + one-line subtitle stating what it shows and the reading direction
- [ ] Legend present if colour encodes a role, listing every colour used
- [ ] Glossary present if any acronym / project term needs decoding
- [ ] Every cross-role / non-obvious arrow is labelled
- [ ] Node names are real identifiers, not placeholders
- [ ] One focus: grey by default, ≤2 accent nodes, ≤4 role colours
- [ ] No region past 12 nodes; every layer drawn tells this reader something
- [ ] **Remove test:** no node can go, no two can merge, no arrow repeats what the
  layout says, no label repeats what colour or shape says
- [ ] A 3-column table would not say the same thing — if it would, make a table
- [ ] None of the anti-patterns in `references/worked_examples.md`

Then deliver **both** files and say three things: **what it shows** (one sentence),
**how to read it** (the direction, how regions stack), and the **colour legend** if
colour is used. `<name>.excalidraw` drags onto excalidraw.com; `<name>.html` opens by
double-click. **Both work offline and upload nothing** (`--cdn` links unpkg instead).
