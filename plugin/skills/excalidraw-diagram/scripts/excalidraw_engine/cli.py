"""The command line: one verb per starting point, dispatched from a table."""

import sys

from . import selftest
from .discover import discover_stub
from .spec import scene_from_json
from .viewer import render_html

USAGE = """usage: excalidraw_builder.py [<command>]

  (no command)                          run the builder self-test (smoke test)
  scene --from-json <graph.json> [-o <dir>] [--cdn]
                                        lay out a coordinate-free graph and write both files
  render <scene.excalidraw> [out_dir] [--cdn]
                                        rebuild the .html viewer from an existing scene
  discover <repo> [out.py]              scan a repo -> a runnable Python generator stub

Two authoring paths. `scene` is the short one: describe nodes, edges and groups in
JSON with no coordinates, and pack() places everything and runs the gates. Writing a
generator against the Scene API is the other, for a diagram whose layout you want to
control yourself. `render` re-emits the viewer for a scene edited elsewhere (e.g.
excalidraw.com).

The viewer carries the Excalidraw runtime, so it opens with no network — about 1.6 MB
of page. `--cdn` writes the ~100 KB page that loads the runtime from unpkg instead."""


def _cdn_flag(args):
    """(args without --cdn, offline). `offline` is False when the flag is present and
    None when it is not, so its absence leaves the default where it belongs — with
    `html_page` and the environment. The flag is positional-agnostic on purpose: it
    modifies the output, not the arguments, so it may sit anywhere."""
    kept = [a for a in args if a != "--cdn"]
    return kept, (None if len(kept) == len(args) else False)


def _usage_error(line):
    print("usage: excalidraw_builder.py " + line, file=sys.stderr)
    return 2


def _render(args):
    args, offline = _cdn_flag(args)
    if not args:
        return _usage_error("render <scene.excalidraw> [out_dir] [--cdn]")
    print("wrote", render_html(args[0], args[1] if len(args) > 1 else None,
                               offline=offline))
    return 0


def _discover(args):
    if not args:
        return _usage_error("discover <repo> [out.py]")
    print("wrote", discover_stub(args[0], args[1] if len(args) > 1 else None))
    return 0


def _scene(args):
    args, offline = _cdn_flag(args)
    flags = {"--from-json": "spec", "-o": "out", "--out": "out"}
    got = {}
    while args:
        key = flags.get(args[0])
        if key is None or len(args) < 2:
            got = {}
            break
        got[key], args = args[1], args[2:]
    if not got.get("spec"):
        return _usage_error("scene --from-json <graph.json> [-o <dir>] [--cdn]")
    print("wrote", *scene_from_json(got["spec"], got.get("out"), offline=offline))
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
