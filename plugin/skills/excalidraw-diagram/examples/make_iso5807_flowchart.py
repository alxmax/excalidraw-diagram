#!/usr/bin/env python3
"""ISO 5807 flowchart — how the builder turns a description into two files.

Doubles as the demonstration/regression example for the builder's ISO 5807 shape
set: terminator (start/end), preparation (init), data (I/O parallelogram),
process, predefined process (subroutine), decision, and the on-page connector.

Deliberately *not* 100% ISO: the standard says shape carries meaning and colour
is undefined — here colour reinforces the shape category (redundant encoding),
purely so the diagram reads with some life. The coloured shape key decodes both
axes.

Top -> bottom is the flow. The first decision is the one that matters: an edge
becomes a straight arrow only if its line clears every box, and the "no" branch
routes it instead, resuming at the gates via on-page connector A rather than a
long back-edge.

Run from the repo root, writing into the regenerable diagrams/ dir:
    python plugin/skills/excalidraw-diagram/examples/make_iso5807_flowchart.py diagrams
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from excalidraw_builder import Scene

# colour by ISO category (the 20% we add on top of the standard shapes)
ROLES = {
    "startend": "green",    # terminator
    "init":     "teal",     # preparation
    "io":       "blue",     # data (input/output)
    "step":     "violet",   # process
    "sub":      "indigo",   # predefined process
    "branch":   "orange",   # decision
    "conn":     "yellow",   # connector
}

s = Scene(seed=23, roles=ROLES)
cx = 360  # centre line of the main flow column


def at(w, y):  # x so a width-w box is centred on cx
    return cx - w / 2, y


s.title("From a description to two files — ISO 5807 flowchart", 40, -78, size=28)
s.label("Top -> bottom. ~80% ISO 5807 (shape = meaning) + colour by category for "
        "readability. A crossing edge is routed, then resumes at on-page connector A.",
        cx, -44, size=14)

# ── main flow (top -> bottom) ─────────────────────────────────────────────
# Stack with >=70px of clear space between consecutive boxes so every vertical
# connector renders as a visible line (the builder's short-arrow gate rejects a
# tighter stack — a clamped near-zero arrow shows only its label).
GAP_V = 96            # clear enough that even a labelled step ('yes') keeps line
yc = 0


def below(h):            # return the top y for a height-h box, then advance
    global yc
    top = yc
    yc += h + GAP_V
    return top


start = s.terminator("Start", *at(150, below(52)), w=150, h=52, fill="startend")
init = s.preparation("Scene(seed=…)\n(canvas + roles)", *at(240, below(78)), w=240, h=78, fill="init")
inp = s.data("nodes, edges, groups\n(no coordinates)", *at(250, below(64)), w=250, h=64, fill="io")
layer = s.process("layer by depth", *at(220, below(60)), w=220, h=60, fill="step")
order = s.process("order each layer\n(barycenter)", *at(220, below(60)), w=220, h=60, fill="step")
clear = s.decision("edge's line\nclears every\nbox?", *at(230, below(120)), w=230, h=120, fill="branch")
gates = s.process("run the\nseven gates", *at(220, below(60)), w=220, h=60, fill="step")
outp = s.data("scene.excalidraw\n+ viewer.html", *at(250, below(66)), w=250, h=66, fill="io")
done = s.terminator("Open it", *at(150, below(52)), w=150, h=52, fill="startend")

# ── the "no" branch: route the edge instead of drawing it straight ────────
cy = s._geom[clear][1]                    # decision's top y (layout-driven)
route = s.predefined_process("route_around()\n(out, along, back)", 620, cy, w=210, h=70, fill="sub")
connA1 = s.connector("A", 702, cy + 140, w=46, h=46, fill="conn")
connA2 = s.connector("A", 36, s._geom[gates][1] + 7, w=46, h=46, fill="conn")

# ── connectors ────────────────────────────────────────────────────────────
s.arrow(start, init)
s.arrow(init, inp)
s.arrow(inp, layer)
s.arrow(layer, order)
s.arrow(order, clear)
s.arrow(clear, gates, label="yes: draw it straight")
s.arrow(gates, outp)
s.arrow(outp, done)
s.arrow(clear, route, label="no")
s.arrow(route, connA1)
s.arrow(connA2, gates, label="resume (A)")
s.label("on-page connector A: once routed, the edge rejoins at the gates",
        740, cy + 200, size=12)

# ── shape key (ISO 5807 symbol + colour → meaning) ────────────────────────
kx, ky = 920, 40
s.label("ISO 5807 shape key", kx + 30, ky - 26, size=13, align="left")
key = [
    (s.terminator,         "startend", "terminator — start / end"),
    (s.preparation,        "init",     "preparation — initialise"),
    (s.process,            "step",     "process — a step"),
    (s.predefined_process, "sub",      "predefined process — subroutine"),
    (s.data,               "io",       "data — input / output"),
    (s.decision,           "branch",   "decision — branch"),
    (s.connector,          "conn",     "on-page connector"),
]
row_y = ky
for fn, role, meaning in key:
    fn("", kx, row_y, w=64, h=34, fill=role)
    s.label(meaning, kx + 76, row_y + 9, size=12, align="left")
    row_y += 58

# ── glossary (the builder's own terms) ────────────────────────────────────
s.glossary([
    ("layer", "how deep a node sits in the flow; one column, or one row"),
    ("barycenter", "put a node near the average position of its neighbours"),
    ("routed edge", "one drawn around the diagram because a straight line would cut a box"),
    ("gate", "a check run before writing; a failed one refuses the file"),
], 235, s.bounds()[3] + 60, title="Glossary")

out_dir = sys.argv[1] if len(sys.argv) > 1 else "docs"
s.save("builder_flow_iso5807", out_dir=out_dir, crossing_check="error")
print("wrote builder_flow_iso5807.excalidraw + .html")
