"""The command line: one verb per starting point, dispatched from a table."""

import sys

from . import selftest
from .discover import discover_stub
from .spec import scene_from_json
from .viewer import render_html

USAGE = """usage: excalidraw_builder.py [<command>]

  (no command)                          run the builder self-test (smoke test)
  scene --from-json <graph.json> [-o <dir>]
                                        lay out a coordinate-free graph and write both files
  render <scene.excalidraw> [out_dir]   rebuild the .html viewer from an existing scene
  discover <repo> [out.py]              scan a repo -> a runnable Python generator stub

Two authoring paths. `scene` is the short one: describe nodes, edges and groups in
JSON with no coordinates, and pack() places everything and runs the gates. Writing a
generator against the Scene API is the other, for a diagram whose layout you want to
control yourself. `render` re-emits the viewer for a scene edited elsewhere (e.g.
excalidraw.com)."""


def _usage_error(line):
    print("usage: excalidraw_builder.py " + line, file=sys.stderr)
    return 2


def _render(args):
    if not args:
        return _usage_error("render <scene.excalidraw> [out_dir]")
    print("wrote", render_html(args[0], args[1] if len(args) > 1 else None))
    return 0


def _discover(args):
    if not args:
        return _usage_error("discover <repo> [out.py]")
    print("wrote", discover_stub(args[0], args[1] if len(args) > 1 else None))
    return 0


def _scene(args):
    flags = {"--from-json": "spec", "-o": "out", "--out": "out"}
    got = {}
    while args:
        key = flags.get(args[0])
        if key is None or len(args) < 2:
            got = {}
            break
        got[key], args = args[1], args[2:]
    if not got.get("spec"):
        return _usage_error("scene --from-json <graph.json> [-o <dir>]")
    print("wrote", *scene_from_json(got["spec"], got.get("out")))
    return 0


def _selftest(_args):
    selftest.run()
    return 0


def _help(_args):
    print(USAGE)
    return 0


VERBS = {"render": _render, "discover": _discover, "scene": _scene,
         "selftest": _selftest, "help": _help, "-h": _help, "--help": _help}


def main(argv):
    """CLI dispatch. No command runs the self-test, so `python
    excalidraw_builder.py` stays the smoke test CI relies on. Returns an exit code."""
    # implements: REQ-EXCALIDRAW-848
    if not argv:
        return _selftest(argv)
    verb = VERBS.get(argv[0])
    if verb is None:
        print(f"unknown command: {argv[0]!r} — use scene, render, discover, "
              f"or no command for the self-test", file=sys.stderr)
        return 2
    try:
        return verb(argv[1:])
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
