# excalidraw-diagram

Describe a system, a flow or an architecture, and get back an **editable Excalidraw
scene** (`<name>.excalidraw`, imports into excalidraw.com) and a **self-contained HTML
viewer** (`<name>.html`, opens by double-click). You never write coordinates: you name
nodes, edges and groups, and the builder places them, routes the connectors and checks
the result for overlaps and crossings before it writes anything.

This plugin is an independent project and is not affiliated with or endorsed by
Excalidraw. It writes files in Excalidraw's open `.excalidraw` format and bundles the
MIT-licensed Excalidraw library to render them.

It is built for the case where someone does not understand a system and asks for a
picture. The output decodes itself: a title, a stated reading direction, a legend for
every colour and a glossary for every term.

## Use it

Install the plugin, then ask in plain words:

- "draw the architecture of this repo", "make a flowchart of this pipeline"
- "explain how X works", "I don't understand X"
- "put the diagram in an HTML I can share"

The `excalidraw-diagram` skill triggers on those requests. It also supports sequence,
state and entity-relationship diagrams, ISO 5807 flowcharts, timing diagrams and a
Mermaid flowchart translated into an editable scene. Each has a runnable generator under
`skills/excalidraw-diagram/examples/`.

## What it runs, writes and fetches

- **One local process.** `.mcp.json` registers an MCP server that Claude Code starts with
  `python -X utf8 ${CLAUDE_PLUGIN_ROOT}/skills/excalidraw-diagram/scripts/mcp_server.py`.
  It speaks JSON-RPC over stdio, a pipe between two local processes, and listens on no
  port. It exposes four tools: `build_scene`, `render_html`, `discover_repo` and
  `graph_schema`.
- **Files it writes.** `build_scene` and `render_html` write `<name>.excalidraw` and
  `<name>.html` into the `out_dir` the caller names. `discover_repo` lists the top-level
  directory and source-file *names* of the repository you point it at, never their
  contents, and always writes a starter generator script: to the `out_path` you give it,
  or else to `make_diagram.py` in the server's working directory. It overwrites a file
  of that name without asking.
- **Where the server runs.** The MCP server is a local process, so it runs in Claude Code
  and in Cowork sessions on your computer, not in claude.ai chat.
- **A starter script looks in the plugin cache.** A script written by `discover_repo`
  imports the builder from beside itself. If the builder is not there, it lists the
  directories under `~/.claude/plugins/cache/excalidraw-diagram/` and imports the builder
  from the newest installed copy of this plugin. It reads no credentials, no file
  contents and sends nothing.
- **Network: none.** The builder is Python standard library only. It imports no HTTP
  client, no socket module and no subprocess module, and nothing is installed from PyPI
  or npm. There is no account, no telemetry and no upload.
- **The HTML viewer works offline.** It inlines a pinned copy of the Excalidraw renderer
  (see below), so opening a generated page issues no network request. The optional
  `--cdn` flag writes a small page that loads the same renderer from unpkg instead, which
  tells unpkg the viewer's IP address and user agent. The diagram stays in the file
  either way.
- **No credentials, no hooks, no permission changes.**

## The vendored renderer

The viewer's offline promise rests on third-party files in
`skills/excalidraw-diagram/scripts/excalidraw_engine/runtime/`. They are minified because
that is how their authors publish them. All are MIT-licensed except the fonts, which are
Virgil (shipped with Excalidraw) and Cascadia Code and Assistant (SIL OFL 1.1).

| File | Upstream | Version |
|---|---|---|
| `excalidraw.production.min.js` | `unpkg.com/@excalidraw/excalidraw/dist/` | 0.17.6 |
| `react.production.min.js` | `unpkg.com/react/umd/` | 18.2.0 |
| `react-dom.production.min.js` | `unpkg.com/react-dom/umd/` | 18.2.0 |

The React files are byte-identical to upstream. The Excalidraw bundle has exactly one
edit: its published build embeds Excalidraw's own Firebase web config, which belongs to
their live-collaboration backend. This viewer never starts a collaboration session, so
the config is replaced with `'{}'`. To reproduce the file from upstream, apply this to
the published `excalidraw.production.min.js`, three replacements in all:

```
VITE_APP_FIREBASE_CONFIG:'{...}'  ->  VITE_APP_FIREBASE_CONFIG:'{}'
```

`runtime/README.md` has the full provenance and the upgrade procedure.

## Feedback

Found a diagram that came out wrong, or one you wish it could draw? Open an issue at
https://github.com/alxmax/excalidraw-diagram/issues, where there is a form for each. Issues are public, so describe the
shape of the diagram rather than pasting a system you cannot share.

## Requirements

Python 3.9 or newer, standard library only. The bundled MCP server starts with the
command `python`. On a system that has only `python3`, which is how macOS and many Linux
distributions ship, that server does not start and `/mcp` shows it as failed. The skill
still works there: it runs the same builder from the command line, with `python3`. To
get the MCP tools as well, put a `python` command that runs Python 3 on your `PATH`: a
symlink to `python3` in a directory already on it, or the `python-is-python3` package on
Debian and Ubuntu. A shell alias does not help, because the server is not started
through a shell.

## Licence

MIT. See `LICENSE` at the repository root, or the `license` field in
`.claude-plugin/plugin.json`.
