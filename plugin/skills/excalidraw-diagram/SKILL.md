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

**You never hand-write Excalidraw JSON.** `scripts/excalidraw_builder.py` owns
the format's invariants (seeds, version nonces, two-way arrow bindings,
bound-text back-references) and emits both files in one `.save()`. Two companion
files carry the detail this contract only states:
[`references/builder_api.md`](references/builder_api.md) — every call, how to
import it, the `graph.json` schema — and
[`references/worked_examples.md`](references/worked_examples.md) — the repo-poster
recipe and ❌ → ✅ variants.

## The goal (read this first)

**Produce a schematic an outsider can understand with no prior context** — one
that shows *how the system actually works*: its real components, the flow between
them, how it is invoked, how it ships. For a repo that means *that repo's* files
and flow, never a generic template. Pretty-but-shallow fails. Three things pass:

1. **Substance** — real identifiers (`excalidraw_builder.py`, `pack()`), the actual
   workflow, and all three layers (internal flow → integration → distribution).
2. **Readability** — title + one-line subtitle, a legend when colour means a
   role, a glossary for jargon, one reading direction, zero overlaps/crossings.
3. **Enforcement** — the builder's gates turn those rules into hard failures, so
   a sloppy diagram cannot ship.

## When to use

- "Make an Excalidraw / whiteboard / hand-drawn diagram of …"
- "Diagram this repo's architecture" / "schemă excalidraw pentru …"
- Flowcharts, pipelines, multi-agent layouts, module maps, state flows.
- "Put the diagram in an HTML I can open / share."
- **"Explain how X works" / "I don't understand X"** — the most common case. The
  asker wants to *learn* the system, not just see it. Build a teaching diagram:
  everyday words in the boxes, a stated reading direction, a legend and a
  glossary that decode every colour and term on the canvas. The template is
  [`examples/make_explainer.py`](examples/make_explainer.py); worked example 6 in
  `references/worked_examples.md` shows the shape.
- Not this, if they want a static image with no sketch aesthetic — but if they
  said Excalidraw, use this.

## Two ways in

| Path | Use it when | How |
|---|---|---|
| **`scene --from-json`** | the subject is a graph you can describe — parts and connections — and you do not care where each box lands | write `graph.json` (schema in `references/builder_api.md`), then `python scripts/excalidraw_builder.py scene --from-json graph.json -o out/` |
| **A generator script** | the layout itself carries meaning: stacked layers, a lane per tool, a poster | write Python against the `Scene` API and run it |

Two more verbs: `render <scene.excalidraw> [out_dir]` rebuilds the `.html` for a
scene edited elsewhere; `discover <repo> [out.py]` scaffolds a poster stub from a
repo. **No arguments is the smoke test CI depends on — never shadow it.**

## Workflow

1. **Understand the thing to draw.** For a repo, read its README and file layout
   first, so the diagram shows the *actual* components and flow. Identify the
   nodes, the directed connections, the grouping, the reading direction. For an
   architecture diagram audit **all three layers** before planning: *internal
   flow* (steps, modes, decision gates), *integration* (entry points, external
   systems, feedback loops, state) and *distribution* (install, package, deploy).
   One that shows only the internal flow is incomplete.

   **Large repo? Fan out (optional).** Count source files with a `Glob`
   (excluding `node_modules/`, `.git/`, `__pycache__/`). At **≤ 80, or with no
   `Agent` tool**, explore sequentially — the subagent overhead is not worth it.
   Past that, dispatch read-only `Explore` subagents **in parallel**: 3 by
   default, one per lens, never more than 5. **sonnet** for *data-flow +
   integration*, the lens that must reason about flow; **haiku** for *structure +
   entry-points* and *distribution + packaging*. Each returns **≤ 60 lines** of
   JSON — `components` (real file names, never "ServiceA"), directed `edges`
   (`{src, dst, label}` with a verb), its `group`. Merge, **dedup by id**, lay
   out, and never re-read a file a subagent covered.

2. **Choose the path.** Describable as nodes and edges → `graph.json`. Layout
   carries meaning → a generator script.
3. **Plan the layout before writing code** (see Layout rules): every column, its
   x, every arrow. Check no arrow crosses an unrelated box.
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
- **Arrow crossing check.** Before coding each arrow, trace the straight line
  between the two centres. If it passes through a box that is neither end,
  restructure or use `route_under()`.
- **Backward / feedback arrows.** A right-to-left arrow crosses the whole
  forward flow. Always `route_under()` (below the row and back), or drop it and
  note the feedback in a `label()`.
- **Reference columns.** A column that only lists possible values is a legend,
  not a stage; do not draw a long arrow to it across the diagram.
- **Box sizing.** Start from `h ≥ lines × font_size × 1.6 + 16` and
  `w ≥ longest_line_chars × font_size × 0.65 + 20`; `overflow_check` confirms.
  Keep labels to 2–3 words, push detail into a `label()` caption.
- **One file, many diagrams.** ONE `.excalidraw` + ONE `.html` per request, from
  a single `.save()`. Several views stack as labelled regions in the *same* scene
  (`section()`, or `bounds()` + ~80px). Calling `save()` twice raises
  `RuntimeError`, so splitting into several files fails at once.
- **Expand, don't cram.** The canvas is unlimited. Spread out rather than
  shrinking fonts or overlapping shapes.
- **Centered captions anchor at the point.** `label(text, x, y)` and
  `title(..., align="center")` treat `x` as the text's centre (`align="right"` as
  its right edge) — pass the coordinate you want it centred on.
- **Frame and group captions** sit ≥24px ABOVE the frame's top edge
  (`y = frame_y - 24`), never on the border; keep free `label()` text ≥16px clear
  of every shape and arrowhead.
- **Committing the diagram?** Pass `Scene(seed=<int>)` for byte-identical re-runs.

## Quality rules — make it understandable with no context (required)

Not optional polish. Rules 1 and 3 are enforced by `scripts/test_excalidraw.py`:
every example must build with zero overlaps, zero crossings and zero unlegended
fills. That is the operational definition of "clean", not a matter of taste.

1. **Zero overlaps, zero crossings.** `save()` raises on overlap already; for
   crossings use `route_under()`/`path()` and `crossing_check="error"`.
2. **Title + one-line subtitle.** Open with `s.title(...)` and one `s.label(...)`
   sentence saying what the diagram shows and its reading direction.
3. **Legend whenever colour means something.** If any `fill=` encodes a role,
   call `s.legend(...)` (or `Scene(roles=…)` then `s.legend()`). Colour is the
   single source of truth for role and the legend lists every colour used; give
   each *distinct meaning* its own colour. **Enforced:** once a legend is
   rendered, `save()` flags any fill missing from the key, and
   `legend_check="error"` makes that fatal. Build the key with `legend()` — a
   hand-rolled row of swatches is invisible to the gate.
4. **Label cross-role edges.** Any arrow whose ends are different roles, or is
   otherwise non-obvious, carries a short verb phrase (`label="validates"`).
5. **Real identifiers as node names, jargon in a glossary.** Name the actual file
   / function / component (`save()`, `check_overlaps()`), never "Service A".
   When a label must use a term a newcomer cannot decode (`back edge`, `@v1`), add
   `s.glossary([(term, meaning), …])` beside the legend, so every term is
   explained on the canvas.
6. **Readable type sizes.** Two tiers suffice — a title size (~28–32) and a body
   size (~14–16). Never below font_size 12.
7. **Complexity ceiling: ≤20 nodes per region.** Past that, split into an
   overview region and a detail one below; never cram 30 boxes into one.

**The seven gates.** Two always raise unless allowed: overlapping shapes
(`allow_overlap=True`) and an arrow too short to draw (`allow_short_arrows=True`).
Five take `"warn"` (default) or `"error"` (raises): `crossing_check` (an arrow
through an unrelated box), `legend_check` (a fill missing from the key),
`overflow_check` (bound text bigger than its shape), `text_overlap_check` (two
captions on each other), `label_fit_check` (an arrow's label wider than its
connector — bound labels are excluded from the other two, so this is their only
gate). Ship with all five at `"error"`.

## Output

**Pre-delivery checklist.**

*The builder enforces these:*
- [ ] `save(..., crossing_check="error", legend_check="error", overflow_check="error", text_overlap_check="error", label_fit_check="error")`
- [ ] `Scene(seed=<int>)` if the diagram is committed

*You must check these — the builder cannot:*
- [ ] Title + one-line subtitle stating what it shows and the reading direction
- [ ] Legend present if colour encodes a role, listing every colour used
- [ ] Glossary present if any acronym / project term needs decoding
- [ ] Every cross-role / non-obvious arrow is labelled
- [ ] Node names are real identifiers, not placeholders
- [ ] All three layers covered (internal flow / integration / distribution)
- [ ] No region exceeds ~20 nodes

Then deliver **both** files and say three things: **what it shows** (one
sentence), **how to read it** (the direction, how regions stack), and the
**colour legend** if colour is used. `<name>.excalidraw` drags onto
excalidraw.com to edit; `<name>.html` opens by double-click, loading Excalidraw
from a CDN on first open — the `.excalidraw` works fully offline.
