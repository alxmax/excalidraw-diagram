"""`discover`: scan a repository and scaffold a runnable diagram generator for it.

The scan is a heuristic — it sees top-level components, never real data flow — so
what it writes is a starting point the author edits, not a finished diagram."""

import os

_DISCOVER_EXTS = (".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs",
                  ".c", ".cpp", ".h", ".java", ".rb", ".php")
_DISCOVER_PRUNE = {".git", "node_modules", "__pycache__", ".venv", "venv",
                   "env", "dist", "build", "target", ".idea", ".vscode",
                   ".pytest_cache", ".mypy_cache"}


def _dir_has_source(d):
    """True if directory d (recursively, minus pruned dirs) holds any source file."""
    for dirpath, dirs, files in os.walk(d):
        dirs[:] = [x for x in dirs if x not in _DISCOVER_PRUNE and not x.startswith(".")]
        if any(f.endswith(_DISCOVER_EXTS) for f in files):
            return True
    return False


def discover_components(repo):
    """Scan a repo and return its top-level 'components', sorted: each immediate
    child directory that (recursively) contains source, plus each top-level
    source file. Deterministic and cross-platform (sorted, pruned). A heuristic
    scaffold only — the human/LLM refines the real edges + grouping in the stub."""
    repo = os.path.abspath(repo)
    comps = []
    for entry in sorted(os.listdir(repo)):
        if entry in _DISCOVER_PRUNE or entry.startswith("."):
            continue
        full = os.path.join(repo, entry)
        if os.path.isdir(full):
            if _dir_has_source(full):
                comps.append(entry)
        elif entry.endswith(_DISCOVER_EXTS):
            comps.append(entry)
    return comps


# Import preamble baked into every generated stub: try the builder next to the
# stub (or on PYTHONPATH — how CI runs it), else fall back to the newest builder
# in the plugin cache, so a stub generated into ANY repo still runs. Plain raw
# string (not an f-string) so the regex backslashes survive verbatim.
_STUB_IMPORT = r'''import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from excalidraw_builder import Font, Gates, Scene
except ModuleNotFoundError:                      # not alongside the stub — find the plugin
    # Falls back to the newest INSTALLED plugin build; if you run this stub outside
    # the plugin, that cached build may lag an unreleased local edit to the builder.
    import glob, re
    _cache = os.path.join(os.path.expanduser("~"), ".claude", "plugins",
                          "cache", "excalidraw-diagram", "excalidraw-diagram")
    _hits = glob.glob(os.path.join(_cache, "*", "skills",
                                   "excalidraw-diagram", "scripts"))
    if not _hits:
        raise
    def _ver(p):
        m = re.search(r"(\d+)\.(\d+)\.(\d+)", p)
        return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)
    sys.path.insert(0, max(_hits, key=_ver))     # newest installed version
    from excalidraw_builder import Font, Gates, Scene'''


# The generator this command scaffolds. It is emitted source, not logic, so it
# lives here as a template with __NAME__ placeholders — the same style as the
# viewer template, and brace-safe, which matters because the stub is Python and
# is full of { } that a .format() template would force us to double.
_STUB_TEMPLATE = '''#!/usr/bin/env python3
\"\"\"Diagram generator for __SAFE__ — scaffolded by `excalidraw_builder.py discover`.

A multi-LAYER architecture poster in ONE file. Layer 1 (STRUCTURE) is live and
runnable now; layers 2-6 are commented scaffolds. DECIDE PER REPO which layers
explain it, KEEP those, delete the rest, and fill in the real content:

  1. STRUCTURE       (always)   the components and how they group
  2. WORKFLOW        if it has a pipeline / run-order / algorithm
  3. INTEGRATION     if it is invoked by / connects to external systems, CI, a loop
  4. MODES/VARIANTS  if it has modes / strategies / variants of the same flow
  5. MODEL/RUNNERS   if parts run on different models / workers / runtimes
  6. DATA/SCHEMA     if it produces a core record / output shape

Colour = role: give each distinct meaning its own colour and add ONE legend()
when colour is used. Keep every save() gate at "error". Then run this file to
emit __SAFE__.excalidraw + __SAFE__.html.
\"\"\"
__IMPORT__

s = Scene(seed=7)
s.title(__SAFE_REPR__, (40, -70), font=30)
s.label("What it is, how it runs, how it integrates. Left -> right within a layer.",
        (40, -34), font=Font(14, align="left"))

# ---- 1 - STRUCTURE (live: one box per discovered component) ----------------
y = s.section("1 - STRUCTURE   the components")
__NOTES__nodes = s.grid([__ITEMS__], (40, y), __COLS__,
              cell={"size": (__GW__, 64), "font": 13})
# TODO: group related nodes -> s.enclose([nodes[0], nodes[1]], label="subsystem")

# ---- 2 - WORKFLOW (optional: uncomment if the repo has a pipeline) ----------
# y = s.section("2 - WORKFLOW   run order (left -> right)")
# s.pipeline([("Start", "terminator"), ("step", "process"),
#             ("ok?", "decision"), ("Done", "terminator")], (40, y))
# Multi-tool repo (bundles 2+ skills/services with distinct flows)? Do NOT hide
# them in one pipeline — give each its own labelled lane (single-tool: skip this):
# t1 = s.pipeline([("step1", "process"), ("step2", "process")], (120, y + 40))
# s.lane(t1, "tool-one - one-line role")
# t2 = s.pipeline([("step1", "process"), ("step2", "process")], (120, y + 210))
# s.lane(t2, "tool-two - one-line role")

# ---- 3 - INTEGRATION (optional: entry points, external systems, loops) ------
# y = s.section("3 - INTEGRATION   how it is invoked and what it touches")
# entry = s.box("entry point", (40, y), paint="blue")
# ext   = s.box("external system", (320, y), paint="grey")
# s.arrow(entry, ext, label="calls")

# ---- 4 - MODES / VARIANTS (optional: one column per mode, enclosed) ---------
# y = s.section("4 - MODES   variants of the same flow")
# m1 = s.column(["step A", "step B"], (40, y + 40), cell={"paint": "violet"}, connect=True)
# s.enclose(m1, label="mode one")

# ---- 5 - MODEL / RUNNERS (optional: group -> arrow -> runtime) --------------
# y = s.section("5 - MODEL ASSIGNMENT   what runs where")
# grp = s.enclose(s.column(["part a", "part b"], (40, y + 40)), label="components")
# s.arrow(grp, s.box("runtime / model", (420, y + 60), paint="yellow"), label="runs on")

# ---- 6 - DATA / SCHEMA (optional: the record it produces) -------------------
# y = s.section("6 - DATA SCHEMA   the record it produces")
# s.box("record / field_a / field_b / field_c", (40, y, 300, 140), paint="green")

# When colour encodes a role, add ONE legend() that decodes the whole poster:
# s.legend([("component", "blue"), ("external system", "grey")],
#          (40, s.bounds()[3] + 50), title="Legend - colour = role")

s.save(__SAFE_REPR__, gates=Gates.strict())
print("wrote __SAFE__.excalidraw + .html")
'''


def render_stub(repo_name, comps, truncated):
    """Render the text of a runnable, multi-LAYER poster stub from the components.

    The stub is a single-file architecture poster: layer 1 (STRUCTURE) is live and
    runs as-is; layers 2-6 are commented scaffolds the author keeps/deletes per what
    the repo actually needs. This encodes the skill's adaptive recipe — pick the
    layers that explain THIS repo, emit them all in one file."""
    items = comps or ["component-a", "component-b"]
    items_repr = ", ".join(repr(c) for c in items)
    cols = min(4, max(1, len(items)))
    # Size the grid cells to the longest component name so the live STRUCTURE layer
    # never trips the overflow gate (the stub ships with every gate at "error").
    longest = max((len(c) for c in items), default=12)
    gw = max(160, int(longest * 13 * 0.62) + 26)
    # Sanitize the repo name before it lands in the generated stub: a name with a
    # quote (or `"""`) would otherwise break the stub's docstring / string literals
    # on filesystems that allow such characters. Also keeps the saved filename sane.
    safe = "".join(c if (c.isalnum() or c in " _-.") else "_"
                   for c in repo_name) or "diagram"
    notes = []
    if not comps:
        notes.append("# NOTE: no source components auto-detected — placeholders "
                     "shown; replace them.")
    if truncated:
        notes.append("# NOTE: repo had more components than the cap; only the "
                     "first are shown.")
    note_block = ("\n".join(notes) + "\n") if notes else ""
    return (_STUB_TEMPLATE
            .replace("__IMPORT__", _STUB_IMPORT)
            .replace("__SAFE_REPR__", repr(safe))
            .replace("__SAFE__", safe)
            .replace("__NOTES__", note_block)
            .replace("__ITEMS__", items_repr)
            .replace("__COLS__", str(cols))
            .replace("__GW__", str(gw)))


def discover_stub(repo, out_path=None, max_components=20):
    # implements: REQ-EXCALIDRAW-848
    """Emit a runnable Python generator stub (default: ./make_diagram.py) seeded
    from a repo scan — one box per discovered component on a no-overlap grid, with
    TODO markers for the edges/grouping the author adds. Returns the stub path.
    Running the stub produces a valid (if skeletal) .excalidraw + .html."""
    comps = discover_components(repo)
    truncated = len(comps) > max_components
    if truncated:
        comps = comps[:max_components]
    repo_name = os.path.basename(os.path.abspath(repo)) or "repo"
    out_path = out_path or os.path.join(os.getcwd(), "make_diagram.py")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(render_stub(repo_name, comps, truncated))
    return out_path
