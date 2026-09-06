#!/usr/bin/env python3
"""ISO 5807 flowchart — the reqmap command workflow (~80% standard + colour).

Doubles as the demonstration/regression example for the builder's ISO 5807 shape
set: terminator (start/end), preparation (init), data (I/O parallelogram),
process, predefined process (subroutine), decision, and the on-page connector.

Deliberately *not* 100% ISO: the standard says shape carries meaning and colour
is undefined — here colour reinforces the shape category (redundant encoding),
purely so the diagram reads with some life. The coloured shape key decodes both
axes.

Top -> bottom is the flow; the gate's "no" branch loops back to `sync` via an
on-page connector (A) rather than a long back-edge.

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


s.title("reqmap workflow — ISO 5807 flowchart", 40, -78, size=28)
s.label("Top -> bottom. ~80% ISO 5807 (shape = meaning) + colour by category for "
        "readability. Gate 'no' loops back to sync via on-page connector A.",
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
init  = s.preparation("init\n(scaffold + lock)", *at(240, below(78)), w=240, h=78, fill="init")
inp   = s.data("requirements/*.md\n+ tagged code", *at(250, below(64)), w=250, h=64, fill="io")
drc   = s.process("draft -> confirm", *at(220, below(60)), w=220, h=60, fill="step")
sync  = s.process("sync\n(rescan + baseline)", *at(220, below(60)), w=220, h=60, fill="step")
gate  = s.decision("gate:\ndrift & links\nclean?", *at(230, below(120)), w=230, h=120, fill="branch")
mapc  = s.process("map\n(regen _map.*)", *at(220, below(60)), w=220, h=60, fill="step")
outp  = s.data("_map.json / _map.md\n_reqlock.json", *at(250, below(66)), w=250, h=66, fill="io")
nxt   = s.process("next\n(risk buckets)", *at(220, below(60)), w=220, h=60, fill="step")
done  = s.terminator("Commit", *at(150, below(52)), w=150, h=52, fill="startend")

# ── remediation branch (gate = no) ────────────────────────────────────────
# gate spans y 664..784; place the fix beside it and the connectors with the
# same >=70px clear so the branch arrows render too.
gy = s._geom[gate][1]                     # gate's top y (layout-driven, not hand-counted)
fix    = s.predefined_process("fix /\nsync --accept-drift", 620, gy, w=210, h=70, fill="sub")
connA1 = s.connector("A", 702, gy + 140, w=46, h=46, fill="conn")
connA2 = s.connector("A", 36, s._geom[sync][1] + 7, w=46, h=46, fill="conn")

# ── arrows ────────────────────────────────────────────────────────────────
s.arrow(start, init)
s.arrow(init, inp)
s.arrow(inp, drc)
s.arrow(drc, sync)
s.arrow(sync, gate)
s.arrow(gate, mapc, label="yes")
s.arrow(mapc, outp)
s.arrow(outp, nxt)
s.arrow(nxt, done)
s.arrow(gate, fix, label="no")
s.arrow(fix, connA1)
s.arrow(connA2, sync, label="resume (A)")
s.label("on-page connector A: after fixing, resume at sync", 740, gy + 200, size=12)

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

# ── glossary (reqmap jargon) ──────────────────────────────────────────────
s.glossary([
    ("SSOT", "single source of truth — requirements/*.md"),
    ("drift", "content hash of a spec vs _reqlock.json baseline"),
    ("gate", "pre-commit link-sync + drift + test-link check"),
    ("sync", "rescan + advance the drift baseline + regen the map"),
], 235, s.bounds()[3] + 60, title="Glossary")

out_dir = sys.argv[1] if len(sys.argv) > 1 else "docs"
s.save("reqmap_command_flow_iso5807", out_dir=out_dir, crossing_check="error")
print("wrote reqmap_command_flow_iso5807.excalidraw + .html")
