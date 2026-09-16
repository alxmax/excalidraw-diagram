---
id: ARCH-EXCALIDRAW-032
status: confirmed
level: architecture
layer: feature
owner: Alex
milestone: v1.1.0
depends_on: [ARCH-EXCALIDRAW-030]
satisfies: [SYS-DIAGRAM-001]
---

# Excalidraw builder entry points: CLI verbs and MCP tools

## Description
> A diagram gets rebuilt from four different starting points: a description of
> a graph that has no coordinates yet, a generator script, a hand-edited
> `.excalidraw` file, or a repo that needs a scaffold. Each is a different
> question, so each gets its own verb rather than one verb guessing which was
> meant. The no-arg form is CI's own health check and is never shadowed.

Every bullet below is binding.
- The CLI exposes four verbs, each a single unambiguous entry point: no-arg runs the CI smoke test, `render` rebuilds a viewer HTML from an existing `.excalidraw` file, and `discover` scaffolds a generator stub from a repo. Any other verb exits 2 with usage. [[REQ-EXCALIDRAW-848]]
- `scene --from-json <graph.json>` lays out a coordinate-free graph description and writes both output files, so a caller gets a diagram without writing Python. [[REQ-EXCALIDRAW-850]]
- An MCP server offers the same entry points as tools to an assistant, so no client has to shell out to the CLI. [[REQ-EXCALIDRAW-852]]

## Cases
CASE-1
  Given  no arguments
  When   `python excalidraw_builder.py` is run
  Then   it exits 0 and stdout contains a success/summary line (not an error)

CASE-2
  Given  a valid `.excalidraw` file at `<path>`
  When   `render <path>` is run
  Then   a `<basename>.html` is written; the source `.excalidraw` is unchanged

CASE-3
  Given  a directory containing at least one `.py` source file
  When   `discover <dir>` is run
  Then   a runnable Python stub is emitted that imports `excalidraw_builder`
         and calls `.save()`

CASE-4
  Given  an unknown verb such as `frobnicate`
  When   `python excalidraw_builder.py frobnicate`
  Then   the process exits with code 2 and prints usage

CASE-5
  Given  a `graph.json` describing nodes and edges with no coordinates
  When   `scene --from-json graph.json -o <dir>` is run
  Then   both `<name>.excalidraw` and `<name>.html` are written into `<dir>`

CASE-6
  Given  an MCP client connected to `mcp_server.py`
  When   it calls `build_scene` with a graph description
  Then   both files are written, as they would be by `scene --from-json`

## Context
**Notes**
- `discover` only scaffolds the *components* it can see; inferring real data
  flow and grouping remains the author's responsibility.
- The smoke test (no-arg invocation) is what CI depends on — do not change the
  no-arg behaviour.
- `scene` is deliberately not a second authoring language. Every key it accepts
  maps to one `Scene` call, so the JSON cannot drift away from the Python API.
  A caller who wants control over the layout writes a generator instead.

**Current implementation**
- `main(argv)` in `plugin/skills/excalidraw-diagram/scripts/excalidraw_engine/cli.py`, dispatching to `render_html`
  (`viewer.py`), `discover_stub` (`discover.py`) and `scene_from_json` (`spec.py`).
- `plugin/skills/excalidraw-diagram/scripts/mcp_server.py` for the MCP tools.
- `plugin/skills/excalidraw-diagram/scripts/test_excalidraw.py` (CLI test class,
  and `CasesExcalidrawSceneVerb` for the `scene` verb).


--------------------


---
id: REQ-EXCALIDRAW-848
status: confirmed
level: code
layer: feature
owner: Alex
satisfies: [ARCH-EXCALIDRAW-032]
---

# Smoke test, render and discover verbs

## Description
> A diagram can need rebuilding from several different starting points — a generator script,
> a hand-edited `.excalidraw` scene, or an existing repo with no diagram yet — and each needs
> its own unambiguous command rather than one verb guessing the intent. The no-arg form is
> also CI's health check for the builder itself, so it must never be shadowed by a new
> default.

Every bullet below is binding.
- Invoking `python excalidraw_builder.py` with **no arguments** runs the
  builder smoke test, prints a human-readable summary, and exits 0 on success.
  This is the CI health-check entry point and is never shadowed by a new
  default verb.
- `python excalidraw_builder.py render <scene.excalidraw> [out_dir]` reads
  an existing `.excalidraw` file and writes a fresh self-contained
  `<basename>.html` viewer beside it (or into `out_dir` when given). The
  source `.excalidraw` file is never modified.
- `python excalidraw_builder.py discover <repo> [out.py]` scans `<repo>`
  for source files and emits a runnable multi-layer poster stub (STRUCTURE layer
  pre-populated, WORKFLOW / INTEGRATION / MODES / MODEL / DATA layers
  commented as scaffolds) to `out.py` (default: `make_diagram.py`).
- Any unrecognised verb exits with code 2 and prints a usage message. The
  message names every verb the CLI accepts, `scene` included.

## Cases
CASE-1 — no-arg invocation runs the smoke test and exits 0
  Given  no command-line arguments
  When   `python excalidraw_builder.py` runs
  Then   it prints a success summary line and exits 0

CASE-2 — render rebuilds the HTML viewer without touching the source
  Given  an existing `<scene>.excalidraw` file
  When   `render <scene>.excalidraw` runs
  Then   a fresh `<scene>.html` is written and the `.excalidraw` file's bytes are unchanged

CASE-3 — discover emits a runnable multi-layer stub
  Given  a repository containing at least one source file
  When   `discover <repo> out.py` runs
  Then   `out.py` is written, imports `excalidraw_builder`, and runs without error

CASE-4 — an unknown verb exits 2 with usage
  Given  the verb `frobnicate`
  When   `python excalidraw_builder.py frobnicate` runs
  Then   it exits with code 2 and prints a usage message

--------------------


---
id: REQ-EXCALIDRAW-850
status: confirmed
level: code
layer: feature
owner: Alex
satisfies: [ARCH-EXCALIDRAW-032]
---

# The scene verb: a described graph becomes both files

## Description
> `scene --from-json` is the short path to a diagram. A caller writes what the
> parts are and what connects to what — no coordinates anywhere — and gets back
> the same two files a generator script would have produced, judged by the same
> gates. It exists so that wanting a picture of a fifteen-node flow does not first
> require writing and debugging a Python script.

Every bullet below is binding.
- `scene_from_json(spec_path, out_dir)` reads a JSON object describing `nodes`,
  `edges`, `groups` and a `direction`, lays it out with `pack()`, and writes both
  `<name>.excalidraw` and `<name>.html`. The name comes from the description's
  `name`, else from the file's own stem.
- Every key the description accepts maps to one `Scene` call: `title` and
  `subtitle` to `title()` and `label()`, `roles` and `legend` to `legend()`,
  `glossary` to `glossary()`, `seed` to `Scene(seed=...)`.
- `scene_from_json` saves with every gate set to `"error"` (`Gates.strict()`),
  so a description that cannot be drawn readably fails instead of shipping.
  `scene_from_spec(spec, out_dir, name)` does the same for a description
  already in memory.
- A description the builder cannot use raises `ValueError`, and the CLI turns that
  into one line on stderr and exit code 1. Invoking `scene` with no description
  prints usage and exits 2.

## Cases
CASE-1 — a coordinate-free description writes both files
  Given  a `graph.json` naming four nodes, four edges and one group, with no
         coordinate anywhere in it
  When   `scene --from-json graph.json -o <dir>` runs
  Then   both files exist in `<dir>` and the scene parses as JSON with
         `type: "excalidraw"` and a non-empty `elements` list

CASE-2 — a seeded description is byte-identical on re-run
  Given  a description carrying a `seed`
  When   it is built twice into separate directories
  Then   the two `.excalidraw` files are byte-for-byte identical

CASE-3 — the title, legend and glossary reach the canvas
  Given  a description with a `title`, declared `roles` and a `glossary` entry
  When   it is built
  Then   the scene contains the title text, the legend's heading, and the
         glossary line for that entry

CASE-4 — a malformed description exits 1 with one readable line
  Given  five broken files. One is not JSON. One holds an array, not an object.
         One has no nodes. One names an unknown node in an edge. One has an
         `edges` value that is not a list
  When   the `scene` verb runs on each
  Then   the process exits 1 and stderr holds one line starting `error: `, with
         no traceback

CASE-5 — the verb without a description prints usage and exits 2
  Given  `scene`, or `scene --from-json` with nothing after it
  When   the CLI runs
  Then   it exits 2 and prints a usage line

## Context
**Notes**
- The legend and glossary are placed from `bounds()` after `pack()` has run, so
  they sit below every routed lane rather than on one.
- `json.JSONDecodeError` is a subclass of `ValueError`, which is what lets a
  malformed file take the same exit path as a malformed description.

**Current implementation**
- `scene_from_spec()` and `scene_from_json()` in `plugin/skills/excalidraw-diagram/scripts/excalidraw_engine/spec.py`, and the
  `scene` verb in `plugin/skills/excalidraw-diagram/scripts/excalidraw_engine/cli.py`.
- `CasesExcalidrawSceneVerb` in
  `plugin/skills/excalidraw-diagram/scripts/test_excalidraw.py`.


--------------------


---
id: REQ-EXCALIDRAW-852
status: confirmed
level: code
layer: feature
owner: Alex
satisfies: [ARCH-EXCALIDRAW-032]
---

# The MCP server: the same entry points as tools

## Description
> An assistant that speaks the Model Context Protocol (MCP, the standard way an AI
> client calls external tools) should not have to shell out and parse text to draw a
> diagram. `mcp_server.py` offers the builder's entry points as MCP tools over stdio
> (JSON-RPC 2.0 messages, one per line, on stdin and stdout), with nothing to install.

Every bullet below is binding.
- `mcp_server.py` answers `initialize`, `ping`, `tools/list` and `tools/call`, and
  sends no reply to a notification. It negotiates a protocol version the client
  offers when it supports one, else answers with its latest.
- `tools/list` names exactly four tools: `build_scene` for a graph description,
  `render_html` for a scene path, `discover_repo` for a repository, and
  `graph_schema` for the description format.
- A tool whose input is valid but whose work fails returns `isError: true` with a
  one-line message. An unknown tool or an invalid argument is a JSON-RPC error
  instead.
- `graph_schema` reads the format from `references/builder_api.md` at call time.
  The documented schema is the single source, so the tool cannot drift from it.
- `mcp_server.py` writes only protocol messages to stdout. Text the builder prints
  during a call is captured and returned inside that call's result.
- `plugin/.mcp.json` registers the server, so installing the plugin makes the
  tools available with no further setup.

## Cases
CASE-1 — the handshake and the tool list
  Given  a client that sends `initialize`, the `initialized` notification and
         `tools/list`
  When   the server handles them
  Then   it answers the request with its capabilities, sends nothing for the
         notification, and lists exactly the four tools

CASE-2 — build_scene writes both files
  Given  a three-node graph description and an output directory
  When   `tools/call` runs `build_scene`
  Then   both files exist and the result is not an error

CASE-3 — a failing build is a tool error, not a crash
  Given  a description with an edge to a node that does not exist
  When   `build_scene` runs
  Then   the result carries `isError: true` and one line, and the server keeps
         serving

CASE-4 — render_html and discover_repo reach the builder
  Given  a scene the server just built, and a directory holding one `.py` file
  When   `render_html` and `discover_repo` run on them
  Then   the viewer page and the generator stub are written

CASE-5 — graph_schema comes from the documentation
  Given  the plugin as shipped
  When   `graph_schema` runs
  Then   the text names `nodes` and `edges`; with the reference file missing, the
         result is an error saying so

CASE-6 — stdout carries only protocol
  Given  the server started as a subprocess
  When   it receives an initialize, a notification, a tools/list and a malformed
         line, and then stdin closes
  Then   every stdout line parses as JSON-RPC and the process exits 0

## Context
**Notes**
- The server is stdlib only, like the builder. The official MCP SDK would need
  Python 3.10 and a dependency, and the protocol subset used here is small.
- Relative paths in tool arguments resolve against the server process's working
  directory.

**Current implementation**
- `plugin/skills/excalidraw-diagram/scripts/mcp_server.py` and `plugin/.mcp.json`.
- `plugin/skills/excalidraw-diagram/scripts/test_mcp_server.py`.
