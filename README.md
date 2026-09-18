# excalidraw-diagram

A Claude Code plugin that turns a description of a system, flow or architecture into an
**editable Excalidraw scene** plus a **self-contained HTML viewer**. No npm, no service,
no API key: the builder is stdlib-only Python.

You describe the thing; the skill writes `<name>.excalidraw` (imports into excalidraw.com,
every element still hand-editable) and `<name>.html` (opens by double-click).

![How this repository works](docs/repo_map.png)

*Made with the skill, from `docs/make_repo_map.py`. Every picture below is a committed
PNG of a generator that CI runs on every push.*

## Install

```
/plugin marketplace add alxmax/excalidraw-diagram
/plugin install excalidraw-diagram
```

Then just ask. The skill triggers on its own for things like:

- "draw the architecture of this repo", "make a flowchart of this pipeline"
- "schemă excalidraw pentru …", "put the diagram in an HTML I can share"
- **"explain how X works", "I don't understand X"** — the most common case. The
  output is a teaching diagram: everyday words in the boxes, a stated reading
  direction, a legend for every colour and a glossary for every term, so someone
  who has never seen the system can read it.

## Two ways to a diagram

Describe the graph and let the builder place it:

```
cd plugin/skills/excalidraw-diagram/scripts
python excalidraw_builder.py scene --from-json graph.json -o out/
```

`graph.json` names nodes, edges, groups and a direction — **no coordinates**.
`pack()` layers the graph by depth, orders each layer to keep connected nodes
together, and routes any edge whose straight line would cut through a box.
Feedback edges are always routed, so a cycle never cuts back across the flow.

![A diagram built from a coordinate-free description](docs/scene_from_json.png)

*The description that produced it is [`docs/repo_graph.json`](docs/repo_graph.json),
51 lines with no x or y in them. CI builds it on every push.*

Or write a short Python generator against the `Scene` API, for a diagram whose
layout itself carries meaning — stacked layers, a lane per tool, a poster. Both
paths end at the same seven gates.

```python
s = Scene(seed=7)
a = s.box("Client", (40, 60), paint="grey")
b = s.box("API gateway", (320, 60), paint="blue")
s.arrow(a, b, label="request")
s.save("auth_flow", out_dir="out", gates=Gates.strict())
```

## MCP tools

Installing the plugin also registers an MCP server (`plugin/.mcp.json`), so an assistant
can call the builder as tools instead of shelling out: `build_scene` takes the same graph
description as `scene --from-json`, plus `render_html`, `discover_repo`, and `graph_schema`
for the description format. It speaks JSON-RPC over stdio and, like the builder, needs
nothing but Python.

## Why a builder rather than an LLM writing JSON

Excalidraw's format is picky in ways that are easy to get wrong and hard to see: bound
arrows need reciprocal ids on both shapes, `seed` and `versionNonce` drive the hand-drawn
look, and a scene with overlapping boxes renders as a mess rather than an error.

So the model does not author JSON. It writes a short Python script against a small
`Scene` API, and the builder owns the invariants and **checks its own output**:

```
$ python plugin/skills/excalidraw-diagram/scripts/excalidraw_builder.py
wrote /tmp/excd/smoke.excalidraw /tmp/excd/smoke.html
OK smoke test (legend/role/align/distribute/path-bg/crossing-gate)
```

That smoke run renders every shape, runs the auto-layout and asserts nothing overlaps and
no connector crosses another. It exits non-zero on a layout regression, which is the
failure a unit test does not catch: the JSON is still perfectly valid when the diagram is
unreadable.

At `save()` time the builder runs seven gates: overlapping shapes, arrows crossing an
unrelated box, a fill colour missing from the legend, text spilling out of its box, captions
overlapping, arrows too short to draw, and arrow labels wider than their connector. Two of
them raise by default; the other five warn until `Gates.strict()` turns them into hard
failures.

![What save() refuses, next to what it writes](docs/gate_demo.png)

The left half only exists because `docs/make_gate_demo.py` passes `Gates(overlap="warn")`.
Without it, this is what the run prints instead of writing a file:

```
ValueError: 1 overlapping shape(s): 'ingest' overlaps 'parse'. Move the coordinates apart, wrap a grouping shape with container=True, or pass Gates(overlap='off') if intentional.
```

## What is in here

```
plugin/skills/excalidraw-diagram/
  SKILL.md                  the authoritative contract (Claude Code), 196 lines
  SKILL.universal.md        the same, for any assistant
  scripts/excalidraw_builder.py   the import name and CLI — stdlib only, no dependencies
  scripts/excalidraw_engine/      the builder, one module per responsibility
  scripts/mcp_server.py           the MCP server over the same entry points
  scripts/test_excalidraw.py      the builder's tests, every example included
  references/builder_api.md       every call, the graph.json schema
  references/worked_examples.md   the repo-poster recipe and ❌ → ✅ variants
  references/excalidraw_format.md the file-format notes the builder encodes
  examples/make_*.py        four worked generators, each runnable on its own
plugin/.mcp.json            registers the MCP server on install
requirements/               the skill's requirement corpus, checked in CI
docs/make_*.py + *.png      the generators behind the pictures in this README
scripts/check_versions.py   plugin.json and marketplace.json must agree
```

## The examples are the documentation

Each generator under `examples/` runs standalone and writes into a directory you name:

```
python plugin/skills/excalidraw-diagram/examples/make_iso5807_flowchart.py out/
```

They are exercised in CI, so a generator that stops working is a build failure rather than
a stale snippet. Read one before writing your own; they are shorter than the format notes.
Every CI run also uploads a **gallery** artifact with each example's `.excalidraw` and
`.html`, built from that commit.

### `make_explainer.py` — a teaching diagram for a reader with no context

The shape the skill reaches for when someone says "explain how X works" — here turned on
the skill itself: read top to bottom, everyday words, a legend and a glossary that decode
everything on the canvas.

![Explainer](docs/explainer.png)

### `make_full_architecture.py` — a layered repo poster

This repo, drawn by the builder it documents. Structure, workflows, integration, data
schema: one stacked section per layer, a lane per authoring path, one legend for the
whole poster.

![Full architecture](docs/full_architecture.png)

### `make_iso5807_flowchart.py` — an ISO 5807 flowchart

How the builder turns a description into two files, in standard flowchart symbols:
terminator, preparation, data, process, predefined process, decision and the on-page
connector.

![ISO 5807 flowchart](docs/iso5807_flowchart.png)

### `make_excalidraw_skill_flow.py` — how the skill itself runs

![Skill flow](docs/skill_flow.png)

## Timing diagrams, with no timing code in the builder

The builder has no waveform primitive and needs none: a trace is an unbound
`path(points, heads="none")` polyline, a bus value is a `box()` placed at an exact
`(x, y, w, h)`. The gates never inspect an unbound trace, so each generator asserts its
own geometry: clock edges land on the bit grid, every trace stays in its row.

`docs/make_timing_diagrams.py`: how a byte travels on SPI, I2C and UART.

![SPI, I2C and UART timing diagrams](docs/timing_diagrams.png)

`docs/make_autosar_timing.py`: a button debounce, an AUTOSAR Dem counter-based
debounce with its fault detection counter, and an ECU turn-on / turn-off.

![Debounce and ECU power-state timing diagrams](docs/autosar_timing.png)

## Requirements

Python **3.9+**, standard library only. That floor is the oldest version CI runs, not the
oldest the code happens to work on: a floor nothing tests is a claim, not a guarantee.

## Licence

MIT — see [LICENSE](LICENSE). Use it, change it, ship it.
