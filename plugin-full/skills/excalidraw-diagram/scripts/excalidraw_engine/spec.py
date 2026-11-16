"""The graph description: a coordinate-free JSON object becomes both files.

This is the short path to a diagram, and deliberately not a second authoring
language: every key maps to one Scene call, so the JSON cannot drift away from the
Python API. A caller who wants control over the layout writes a generator instead.

    {
      "name": "auth_flow",              // output basename (else the file's)
      "title": "Auth flow",             // title() + label() subtitle
      "subtitle": "Left to right: ...",
      "direction": "LR",                // or "TB"
      "edge_style": "orthogonal",       // or "straight" (the default)
      "seed": 7,                        // byte-stable re-runs
      "accent": "orange",               // the focal colour; fill "accent" uses it
      "takeaway": "...",                // the one line to remember, under the subtitle
      "roles": {"service": "blue"},     // colour = meaning, decoded by legend()
      "nodes": [{"id": "api", "label": "API gateway", "fill": "service",
                 "kind": "process", "sublabel": "api.py", "step": 1}],
      "notes": [{"target": "api", "text": "why it is there"}],   // at most 2
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


def _heading(scene, spec):
    """The title, the subtitle and the takeaway, stacked above whatever pack() drew
    highest: a group on the first row puts its frame label above y=0, where a
    fixed-height subtitle would sit on it."""
    top = min(0.0, scene.bounds()[1])
    title, subtitle, takeaway = spec.get("title"), spec.get("subtitle"), spec.get("takeaway")
    lines = [line for line in (subtitle, takeaway) if line]
    y = top - 54 - 34 * (len(lines) - 1)
    if title:
        scene.title(str(title), (40, y - 42 if lines else top - 60), font=30)
    if subtitle:
        scene.label(str(subtitle), (40, y), font=Font(14, align="left"))
        y += 34
    if takeaway:
        scene.takeaway(str(takeaway), (40, y))


def scene_from_spec(spec, out_dir, name=None, offline=None, svg=False, gates=None):
    """Build and save a scene from a graph description held in memory.

    `name` overrides the description's own "name", `offline` the viewer's
    renderer (see `html_page`), and `svg=True` also writes the .svg. Saves with
    `gates`, by default `Gates.strict()` (every defect gate at "error", the design
    gates warning), and returns the (.excalidraw, .html) paths, plus the .svg's.
    Raises ValueError on a malformed description or a failed gate."""
    # implements: REQ-EXCALIDRAW-850
    nodes, edges, groups = _checked(spec, "the graph description")
    scene = Scene(seed=spec.get("seed"), roles=spec.get("roles") or {},
                  accent=spec.get("accent", "orange"))
    placed = scene.pack(nodes, edges, groups=groups, at=(40, 0.0),
                        options=PackOptions(direction=str(spec.get("direction", "LR")),
                                            edge_style=str(spec.get("edge_style",
                                                                    "straight"))))
    for note in spec.get("notes") or []:
        target = str(note.get("target", "")) if isinstance(note, dict) else ""
        if target not in placed:
            raise ValueError("the graph description: a note's target %r is not a node"
                             % target)
        scene.note(str(note.get("text", "")), placed[target])
    _heading(scene, spec)
    # the two decoders sit below the diagram, side by side, clear of every lane
    key_y = scene.bounds()[3] + 70
    glossary_x = 460
    if spec.get("legend", bool(spec.get("roles"))) and scene.roles:
        key = scene.rect(scene.legend(at=(40, key_y), title="What the colours mean"))
        glossary_x = max(glossary_x, int(key.x + key.w) + 40)   # clear of a wide legend
    entries = [(str(t[0]), str(t[1])) for t in spec.get("glossary") or [] if len(t) >= 2]
    if entries:
        scene.glossary(entries, (glossary_x, key_y))
    return scene.save(str(name or spec.get("name") or "diagram"), out_dir,
                      gates=gates or Gates.strict(), offline=offline, svg=svg)


def scene_from_json(spec_path, out_dir=None, offline=None, svg=False):
    """Build and save a scene from a graph description file. The output name is
    the description's "name", else the file's stem; the output directory defaults
    to the file's own. Returns the (.excalidraw, .html) paths, plus the .svg's when
    `svg=True`."""
    # implements: REQ-EXCALIDRAW-850
    with open(spec_path, encoding="utf-8") as fh:
        try:
            spec = json.load(fh)
        except ValueError as exc:      # json.JSONDecodeError is a ValueError
            raise ValueError("%s is not valid JSON: %s" % (spec_path, exc))
    _checked(spec, spec_path)
    stem = os.path.splitext(os.path.basename(spec_path))[0]
    return scene_from_spec(spec, out_dir or os.path.dirname(spec_path) or ".",
                           name=spec.get("name") or stem, offline=offline, svg=svg)
