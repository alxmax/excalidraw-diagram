"""The graph description: a coordinate-free JSON object becomes both files.

This is the short path to a diagram, and deliberately not a second authoring
language: every key maps to one Scene call, so the JSON cannot drift away from the
Python API. A caller who wants control over the layout writes a generator instead.

    {
      "name": "auth_flow",              // output basename (else the file's)
      "title": "Auth flow",             // title() + label() subtitle
      "subtitle": "Left to right: ...",
      "direction": "LR",                // or "TB"
      "seed": 7,                        // byte-stable re-runs
      "roles": {"service": "blue"},     // colour = meaning, decoded by legend()
      "nodes": [{"id": "api", "label": "API gateway", "fill": "service",
                 "kind": "process"}],
      "edges": [{"src": "api", "dst": "auth", "label": "verify",
                 "dashed": false}],
      "groups": [{"label": "the service", "members": ["api", "auth"]}],
      "legend": true,                   // render the roles key
      "glossary": [["back edge", "an arrow returning to an earlier step"]]
    }
"""

import json
import os

from .gates import Gates
from .pack import PackOptions
from .scene import Scene
from .style import Font


def _checked(spec, where):
    """`spec`'s nodes, edges and groups, or ValueError naming `where`."""
    if not isinstance(spec, dict):
        raise ValueError("%s must hold a JSON object, not a %s"
                         % (where, type(spec).__name__))
    nodes = spec.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        raise ValueError("%s needs a non-empty 'nodes' list" % where)
    edges, groups = spec.get("edges") or [], spec.get("groups") or []
    for name, value in (("edges", edges), ("groups", groups)):
        if not isinstance(value, list):
            raise ValueError("%s: '%s' must be a list" % (where, name))
    return nodes, edges, groups


def scene_from_spec(spec, out_dir, name=None, offline=None):
    """Build and save a scene from a graph description held in memory.

    `name` overrides the description's own "name", `offline` the viewer's
    renderer (see `html_page`). Saves with every gate at "error" and returns the
    (.excalidraw, .html) paths. Raises ValueError on a malformed description or a
    failed gate."""
    # implements: REQ-EXCALIDRAW-850
    nodes, edges, groups = _checked(spec, "the graph description")
    scene = Scene(seed=spec.get("seed"), roles=spec.get("roles") or {})
    title, subtitle = spec.get("title"), spec.get("subtitle")
    if title:
        scene.title(str(title), (40, -96 if subtitle else -60), font=30)
    if subtitle:
        scene.label(str(subtitle), (40, -54), font=Font(14, align="left"))
    scene.pack(nodes, edges, groups=groups, at=(40, 0.0),
               options=PackOptions(direction=str(spec.get("direction", "LR"))))
    # the two decoders sit below the diagram, side by side, clear of every lane
    key_y = scene.bounds()[3] + 70
    if spec.get("legend", bool(spec.get("roles"))) and scene.roles:
        scene.legend(at=(40, key_y), title="What the colours mean")
    entries = [(str(t[0]), str(t[1])) for t in spec.get("glossary") or [] if len(t) >= 2]
    if entries:
        scene.glossary(entries, (460, key_y))
    return scene.save(str(name or spec.get("name") or "diagram"), out_dir,
                      gates=Gates.strict(), offline=offline)


def scene_from_json(spec_path, out_dir=None, offline=None):
    """Build and save a scene from a graph description file. The output name is
    the description's "name", else the file's stem; the output directory defaults
    to the file's own. Returns the (.excalidraw, .html) paths."""
    # implements: REQ-EXCALIDRAW-850
    with open(spec_path, encoding="utf-8") as fh:
        try:
            spec = json.load(fh)
        except ValueError as exc:      # json.JSONDecodeError is a ValueError
            raise ValueError("%s is not valid JSON: %s" % (spec_path, exc))
    _checked(spec, spec_path)
    stem = os.path.splitext(os.path.basename(spec_path))[0]
    return scene_from_spec(spec, out_dir or os.path.dirname(spec_path) or ".",
                           name=spec.get("name") or stem, offline=offline)
