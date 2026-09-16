#!/usr/bin/env python3
"""excalidraw-diagram — Complete Architecture poster (single .excalidraw + .html).

The canonical self-diagram of this repo, and the reference for the skill's
ADAPTIVE recipe: include only the layers a repo actually needs. This one needs
FOUR of the six layer-types — it has no execution modes and no per-part model
assignment, so MODES and MODEL are deliberately omitted:

  1. STRUCTURE     the plugin's containers
  2. WORKFLOWS     one lane per authoring path (the two-lane rule, for two flows)
  3. INTEGRATION   how it is invoked, checked, and shipped
  6. DATA SCHEMA   the graph description it accepts

Colour = role (one legend decodes all layers); a glossary decodes the jargon.
Every save() gate runs at "error". Run from the repo root, writing into the
regenerable diagrams/ dir:
    python plugin/skills/excalidraw-diagram/examples/make_full_architecture.py diagrams
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from excalidraw_builder import Font, Gates, Scene

s = Scene(seed=31, roles={
    "engine":   "blue",     # excalidraw_builder.py
    "skill":    "violet",   # the skill / the plugin
    "words":    "indigo",   # what you write: a description or a generator
    "artifact": "green",    # generated outputs (.excalidraw, .html)
    "spec":     "pink",     # the requirement corpus
    "external": "grey",     # systems outside the plugin
    "gate":     "orange",   # a check / a decision
    "enum":     "teal",     # schema enum / annotation
})

s.title("excalidraw-diagram — Architecture", (40, -92), font=32)
s.label("A Claude Code plugin: describe a system, get an editable Excalidraw scene "
        "and a viewer, with checks that refuse an unreadable one. Left -> right = order.",
        (40, -52), font=Font(14, align="left"))

# ═══════════════════════ 1 · STRUCTURE ═══════════════════════
y = s.section("1 - STRUCTURE   the plugin's containers")
parts = s.row([
    ("SKILL.md\nthe contract", "skill"),
    ("excalidraw_builder.py\nstdlib only", "engine"),
    ("references/\napi + examples", "words"),
    ("examples/make_*.py\nfour generators", "artifact"),
    ("requirements/\n14 promises", "spec"),
], (80, y + 44), gap=28, cell={"size": (200, 64), "font": 13})
s.enclose(parts, label="excalidraw-diagram plugin")

# ═══════════════════════ 2 · WORKFLOWS (per path) ════════════
# Two distinct authoring flows in one tool -> one labelled lane() each, rather
# than a single pipeline that would show one and hide the other.
y = s.section("2 - WORKFLOWS   one pipeline per authoring path (left -> right = run order)")

# Lane 1 — the short path: a description, and the builder places everything
row1 = y + 60
js = s.pipeline([
    ("graph.json", "data", "words"),
    ("pack():\nlayer", "process", "engine"),
    ("order", "process", "engine"),
    {"text": "line\nclear?", "kind": "decision", "paint": "gate", "label": "yes"},
    ("route it", "process", "engine"),
    {"text": "scene + viewer", "kind": "terminator", "paint": "artifact", "size": (190, 54)},
], (120, row1), gap=110)
s.lane(js, "scene --from-json  -  you describe it, pack() places it")
s.route_under(js[3], js[4], label="no", drop=55)

# Lane 2 — the control path: you place the shapes yourself
row2 = row1 + 230
gen = s.pipeline([
    ("make_diagram.py", "data", "words"),
    {"text": "Scene API:\nbox, arrow, section", "kind": "process", "paint": "engine",
     "size": (210, 64)},
    ("your coordinates", "process", "words"),
    {"text": "scene + viewer", "kind": "terminator", "paint": "artifact", "size": (190, 54)},
], (120, row2), gap=90)
s.lane(gen, "a generator script  -  when the layout itself carries meaning")

s.label("both paths end at the same save(): seven checks, and only a clean diagram is written",
        (120, row2 + 130), font=Font(12, align="left"))

# ═══════════════════════ 3 · INTEGRATION ═════════════════════
y = s.section("3 - INTEGRATION   how it is invoked, checked, and shipped")
yi = y + 30
dev = s.box("Developer / AI", (80, yi, 170, 70), paint="external", font=13)
cc = s.box("Claude Code", (450, yi, 180, 70), paint="external", font=13)
plug = s.box("excalidraw-diagram\n(skill + builder)", (840, yi, 210, 70),
             paint="skill", font=13)
site = s.box("excalidraw.com\nstill editable", (1270, yi, 190, 70),
             paint="external", font=13)
s.arrow(dev, cc, label="asks")
s.arrow(cc, plug, label="invokes [skill]")
s.arrow(plug, site, label="opens in")
yb = yi + 150
mkt = s.box(".claude-plugin\nmarketplace.json", (80, yb, 190, 64),
            paint="external", font=13)
inst = s.box("/plugin install", (470, yb, 170, 64), paint="external", font=13)
ci = s.box("git + CI\n80 tests, every example", (840, yb, 220, 64),
           paint="external", font=13)
s.arrow(mkt, inst, label="lists")
s.arrow(inst, ci, label="then every push")
s.label("distribution (left) + CI (right): every push runs the suite and rebuilds every example.",
        (80, yb + 84), font=Font(12, align="left"))
ym = yb + 150
gen2 = s.box("SKILL.universal.md\nreferences/*.md", (80, ym, 230, 80),
             paint="artifact", font=12)
others = s.box("other AI assistants\nCopilot / Gemini / Codex", (560, ym, 230, 80),
               paint="external", font=12)
s.arrow(gen2, others, label="run the same builder")
s.label("multi-platform: the builder is stdlib and tool-agnostic, so the universal "
        "contract is the only thing another assistant needs.",
        (80, ym + 100), font=Font(12, align="left"))

# ═══════════════════════ 6 · DATA SCHEMA ═════════════════════
y = s.section("6 - DATA SCHEMA   the graph description it accepts")
ys = y + 20
record = s.box(
    "graph.json\n\n"
    "direction: LR | TB\n"
    "nodes: [{id, label, fill, kind}]\n"
    "edges: [{src, dst, label, dashed}]\n"
    "groups: [{label, members}]\n"
    "roles: {name: colour}\n"
    "seed, title, subtitle\n\n"
    "legend, glossary",
    (560, ys, 350, 250), paint="words", font=12)
kinds = s.box("kind: process | decision\nterminator | data | ...", (80, ys + 30, 230, 64),
              paint="enum", font=12)
checks = s.box("the seven gates\noverlap, crossing, fit", (80, ys + 170, 230, 64),
               paint="gate", font=13)
s.arrow(kinds, record, label="shape per node")
s.arrow(checks, record, label="judge the result")
scene = s.box("scene.excalidraw\nevery element editable", (1090, ys + 20, 240, 84),
              paint="artifact", font=12)
html = s.box("viewer.html\nopens by double-click", (1140, ys + 180, 240, 64),
             paint="artifact", font=12)
s.arrow(record, scene, label="pack()")
s.arrow(record, html, label="save() writes")

# ═══════════════════════ legend + glossary ═══════════════════
_, _, max_x, max_y = s.bounds()
ly = max_y + 60
s.legend([
    ("engine - excalidraw_builder.py", "blue"),
    ("the skill / the plugin", "violet"),
    ("what you write", "indigo"),
    ("generated output", "green"),
    ("requirement corpus", "pink"),
    ("external system", "grey"),
    ("gate / decision", "orange"),
    ("schema enum / annotation", "teal"),
], (80, ly), title="Legend - colour = role")
s.glossary([
    ("scene", "the .excalidraw file — the picture, editable box by box"),
    ("viewer", "the .html file — the same scene, opens in a browser"),
    ("pack()", "the layout pass: layer by depth, order, then route"),
    ("gate", "a check at save() time; a failed one refuses to write"),
    ("routed edge", "drawn around the diagram, because a straight line would cut a box"),
    ("lane", "one labelled band per flow, so a second flow is not hidden"),
    ("dogfood", "this poster is drawn by the builder it documents"),
], (760, ly), title="Glossary")

out_dir = sys.argv[1] if len(sys.argv) > 1 else "diagrams"
s.save("full_architecture", out_dir=out_dir, gates=Gates.strict())
print("wrote full_architecture.excalidraw + .html")
