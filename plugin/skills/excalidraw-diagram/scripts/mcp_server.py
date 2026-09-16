#!/usr/bin/env python3
# implements: REQ-EXCALIDRAW-852
"""
mcp_server.py — expose the excalidraw builder as an MCP server over stdio.

Why this exists
---------------
The skill drives the builder through a shell: write a graph.json, run a command,
read what it printed. An MCP client can instead call a typed tool with the graph as
an argument and get the written paths back, with no temp file and no quoting. The
server is a thin adapter: every tool is one builder call, so the builder stays the
only place a diagram is decided.

Transport: newline-delimited JSON-RPC 2.0 on stdin/stdout. Stdout IS the protocol,
so nothing else may reach it. The builder prints gate warnings; each tool call runs
with stdout and stderr redirected into one buffer, and the captured text is returned
inside the tool result as warnings.
Stray writes outside a call (imports, anything unforeseen) go to stderr, because the
real stdout is held privately and sys.stdout is pointed at stderr for the lifetime
of the process.

Python standard library only.
"""
import contextlib
import io
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

# the builder must not write to stdout while it loads either
with contextlib.redirect_stdout(sys.stderr):
    import excalidraw_builder as eb

SUPPORTED_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
PLUGIN_JSON = os.path.join(SCRIPT_DIR, "..", "..", "..", ".claude-plugin", "plugin.json")
BUILDER_API_MD = os.path.join(SCRIPT_DIR, "..", "references", "builder_api.md")
SCHEMA_HEADING = "## The `scene --from-json` description"
INSTRUCTIONS = (
    "Draw Excalidraw diagrams without coordinates: call graph_schema once to learn the "
    "graph description, then build_scene with nodes and edges; the builder lays it out, "
    "runs its readability gates, and writes a .excalidraw scene plus an HTML viewer. "
    "A failed gate comes back as a tool error naming the fix."
)
_CWD_NOTE = " Relative paths resolve against the server process's working directory."


class RpcError(Exception):
    """A JSON-RPC error: code plus message, turned into an error response."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def server_version():
    """The plugin's version from plugin.json, or 0.0.0 when it cannot be read."""
    try:
        with open(PLUGIN_JSON, encoding="utf-8") as fh:
            return str(json.load(fh).get("version") or "0.0.0")
    except (OSError, ValueError, AttributeError):
        return "0.0.0"


# --- tools ------------------------------------------------------------------------------

def tool_build_scene(args):
    """Build a scene from a graph description; return both written paths."""
    scene_path, html_path = eb.scene_from_spec(
        args["graph"], os.path.abspath(args["out_dir"]), args.get("name"))
    return "wrote %s\nwrote %s" % (os.path.abspath(scene_path), os.path.abspath(html_path))


def tool_render_html(args):
    """Render an existing .excalidraw scene to an HTML viewer; return its path."""
    out_dir = args.get("out_dir")
    html = eb.render_html(os.path.abspath(args["scene_path"]),
                          os.path.abspath(out_dir) if out_dir else None)
    return "wrote %s" % os.path.abspath(html)


def tool_discover_repo(args):
    """Scan a repo into a runnable generator stub; return the stub path."""
    out_path = args.get("out_path")
    stub = eb.discover_stub(os.path.abspath(args["repo"]),
                            os.path.abspath(out_path) if out_path else None)
    return "wrote %s" % os.path.abspath(stub)


def tool_graph_schema(_args):
    """Return the graph description schema, read from builder_api.md at call time."""
    with open(BUILDER_API_MD, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    if SCHEMA_HEADING not in lines:
        raise ValueError("builder_api.md has no section %r" % SCHEMA_HEADING)
    block, inside = [], False
    for line in lines[lines.index(SCHEMA_HEADING) + 1:]:
        if inside and line.startswith("```"):
            return "\n".join(block)
        if inside:
            block.append(line)
        elif line.startswith("## "):
            break
        elif line.startswith("```jsonc"):
            inside = True
    raise ValueError("builder_api.md section %r holds no ```jsonc block" % SCHEMA_HEADING)


def _schema(properties, required):
    """A closed JSON Schema object with the given properties."""
    return {"type": "object", "properties": properties, "required": list(required),
            "additionalProperties": False}


def _str(description):
    """A string property."""
    return {"type": "string", "description": description}


TOOLS = {
    "build_scene": (
        "Build an Excalidraw diagram from a coordinate-free graph description (see "
        "graph_schema): auto-layout, readability gates at error level, then write "
        "<name>.excalidraw and <name>.html into out_dir. A failed gate is a tool error."
        + _CWD_NOTE,
        _schema({"graph": {"type": "object",
                           "description": "The graph description: nodes, edges, ..."},
                 "out_dir": _str("Directory to write the two files into."),
                 "name": _str("Output basename (default: graph.name).")},
                ("graph", "out_dir")),
        tool_build_scene),
    "render_html": (
        "Render an existing .excalidraw scene into a self-contained HTML viewer."
        + _CWD_NOTE,
        _schema({"scene_path": _str("Path to the .excalidraw file."),
                 "out_dir": _str("Directory for the .html (default: beside the scene).")},
                ("scene_path",)),
        tool_render_html),
    "discover_repo": (
        "Scan a repository and write a runnable Python generator stub with one box per "
        "discovered component, to be completed by hand." + _CWD_NOTE,
        _schema({"repo": _str("Repository root to scan."),
                 "out_path": _str("Stub path (default: make_diagram.py in the cwd).")},
                ("repo",)),
        tool_discover_repo),
    "graph_schema": (
        "Return the annotated schema of the graph description build_scene accepts.",
        _schema({}, ()),
        tool_graph_schema),
}

_JSON_TYPES = {"object": dict, "string": str}


def validate_arguments(schema, args):
    """Raise RpcError -32602 when args do not satisfy the tool's input schema."""
    if not isinstance(args, dict):
        raise RpcError(-32602, "arguments must be an object")
    props = schema["properties"]
    for key in schema["required"]:
        if key not in args:
            raise RpcError(-32602, "missing required argument %r" % key)
    for key, value in args.items():
        if key not in props:
            raise RpcError(-32602, "unknown argument %r" % key)
        if not isinstance(value, _JSON_TYPES[props[key]["type"]]):
            raise RpcError(-32602, "argument %r must be of type %s"
                           % (key, props[key]["type"]))


def call_tool(name, args):
    """Run one tool with stdout and stderr captured; return an MCP tool result."""
    captured = io.StringIO()           # the builder warns on either stream
    try:
        with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
            text = TOOLS[name][2](args)
    except (ValueError, OSError, KeyError) as exc:
        message = " ".join(str(exc).split()) or type(exc).__name__
        return {"content": [{"type": "text", "text": message}], "isError": True}
    extra = captured.getvalue().strip()
    if extra:
        text += "\nwarnings:\n" + extra
    return {"content": [{"type": "text", "text": text}], "isError": False}


# --- protocol methods -------------------------------------------------------------------

def on_initialize(params):
    """Negotiate the protocol version and describe the server."""
    requested = params.get("protocolVersion")
    version = requested if requested in SUPPORTED_VERSIONS else SUPPORTED_VERSIONS[0]
    return {"protocolVersion": version, "capabilities": {"tools": {}},
            "serverInfo": {"name": "excalidraw-diagram", "version": server_version()},
            "instructions": INSTRUCTIONS}


def on_ping(_params):
    """Answer a liveness check."""
    return {}


def on_tools_list(_params):
    """List every tool with its input schema."""
    return {"tools": [{"name": name, "description": desc, "inputSchema": schema}
                      for name, (desc, schema, _fn) in TOOLS.items()]}


def on_tools_call(params):
    """Validate a tool call, then run it."""
    name = params.get("name")
    if name not in TOOLS:
        raise RpcError(-32602, "unknown tool %r" % (name,))
    args = params.get("arguments")
    args = {} if args is None else args
    validate_arguments(TOOLS[name][1], args)
    return call_tool(name, args)


METHODS = {
    "initialize": on_initialize,
    "ping": on_ping,
    "tools/list": on_tools_list,
    "tools/call": on_tools_call,
}


def _error(msg_id, code, message):
    """A JSON-RPC error response."""
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def handle(message):
    """Answer one decoded JSON-RPC message; None for a notification."""
    if not isinstance(message, dict) or not isinstance(message.get("method"), str):
        msg_id = message.get("id") if isinstance(message, dict) else None
        return _error(msg_id, -32600, "invalid request")
    if "id" not in message:
        return None                    # notifications never get a response
    msg_id, method = message["id"], message["method"]
    if method not in METHODS:
        return _error(msg_id, -32601, "method not found: %s" % method)
    params = message.get("params")
    if not isinstance(params, dict):
        params = {}
    try:
        return {"jsonrpc": "2.0", "id": msg_id, "result": METHODS[method](params)}
    except RpcError as exc:
        return _error(msg_id, exc.code, exc.message)
    except Exception as exc:           # one bad message must never end the loop
        print("mcp_server: %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        return _error(msg_id, -32603, "internal error: %s" % exc)


def handle_line(line):
    """Decode one transport line and answer it; None when nothing is sent back."""
    if not line.strip():
        return None
    try:
        message = json.loads(line)
    except ValueError as exc:
        return _error(None, -32700, "parse error: %s" % exc)
    return handle(message)


def serve(stdin, stdout):
    """Read messages until EOF, writing one response line per request."""
    for line in stdin:
        response = handle_line(line)
        if response is not None:
            stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            stdout.flush()


def main():
    """Run the stdio server; the real stdout is reserved for the protocol."""
    for stream in (sys.stdin, sys.stdout):
        with contextlib.suppress(AttributeError, ValueError):
            stream.reconfigure(encoding="utf-8", newline="\n")
    protocol_out = sys.stdout
    sys.stdout = sys.stderr            # any stray print lands on stderr, not the wire
    try:
        serve(sys.stdin, protocol_out)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
