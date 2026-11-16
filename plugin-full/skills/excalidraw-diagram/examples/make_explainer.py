#!/usr/bin/env python3
"""excalidraw-diagram — plain-English explainer (understandable with no context).

A teaching diagram: read top -> bottom and you learn what the skill is for, how
you use it, what's inside, and where it runs — in everyday words, with every term
decoded in the glossary. It is the reference for the teaching shape:

  - a title, a one-line subtitle that says how to read it, and ONE takeaway line;
  - the main path numbered ①②③ and drawn in the accent colour, with the accent
    on at most two focal nodes; everything else neutral grey or one of four roles;
  - node names in everyday words, the real file or call beneath in code type;
  - at most two margin notes saying WHY, joined to their element by a dashed
    leader and kept outside the diagram;
  - connectors at right angles only.

Run from the repo root, writing into the regenerable diagrams/ dir:
    python plugin-full/skills/excalidraw-diagram/examples/make_explainer.py diagrams
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from excalidraw_builder import Font, Gates, Paint, Scene

s = Scene(seed=91, accent="orange", roles={
    "words":   "indigo",   # the description you write
    "engine":  "violet",   # the builder
    "output":  "green",    # things it produces
    "tool":    "blue",     # the skill itself
    "outside": "grey",     # people / external systems: neutral
})

s.title("excalidraw-diagram — how it works", (40, -140), font=32)
s.label("A tool that turns a DESCRIPTION of a system into a PICTURE of it. Read top "
        "to bottom; follow the orange path ① to ⑤. Every special word is explained "
        "in the Glossary at the bottom.",
        (40, -96), font=Font(15, align="left"))
s.takeaway("you say what the parts are; the tool places them and refuses to hand "
           "you a picture nobody can read.", (40, -62))

# ════════════════════ 1 · THE PROBLEM IT SOLVES ═══════════════════════════
y = s.section("1 - THE PROBLEM IT SOLVES")
know = s.box("What someone\nUNDERSTANDS\nabout a system", (120, y, 230, 84), paint="words")
draw = s.box("What a diagram\nof it would show", (880, y, 230, 84), paint="outside")
s.arrow(know, draw, paint=Paint(stroke="red", dashed=True), heads="both",
        label="the picture nobody has the afternoon to draw")
fix = s.box("excalidraw-diagram", (460, y + 250, 330, 70), paint="tool")
s.arrow(fix, know, label="you describe it in words", elbow=True)
s.arrow(fix, draw, label="it draws and checks it", elbow=True)
s.label("The fix: you say what the parts are and what connects to what; the tool "
        "works out where every box goes and refuses to write an unreadable one.",
        (120, y + 350), font=Font(14, align="left"))

# ════════════════════ 2 · HOW YOU USE IT ══════════════════════════════════
y = s.section("2 - HOW YOU USE IT   (left -> right; the orange path is what happens)")
ids = s.pipeline([
    {"text": "you ask\nfor a diagram", "kind": "terminator", "paint": "outside",
     "size": (150, 58)},
    ("describe the\nparts and links", "process", "words"),
    ("the builder\nplaces them", "process", "engine"),
    {"text": "readable?", "kind": "decision", "paint": "accent", "label": "yes"},
    {"text": "two files\nyou can open", "kind": "terminator", "paint": "output",
     "size": (150, 58)},
], (120, y + 30), gap=150, numbered=True, line="accent")
s.route_under(ids[3], ids[1], label="no -> say it better, run again", drop=76)
s.label("In words:  you name the parts  -  the builder chooses the positions  -  "
        "the checks look at the result  -  and only a clean one is written.",
        (120, y + 250), font=Font(14, align="left"))

# ════════════════════ 3 · WHAT'S INSIDE ═══════════════════════════════════
y = s.section("3 - WHAT'S INSIDE   (everyday name on top, the real file or call below)")
parts = [
    ("the instructions", "SKILL.md", "tool", "what the assistant follows"),
    ("the builder", "excalidraw_builder.py", "engine", "stdlib Python, no dependencies"),
    ("where boxes go", "pack()", "engine", "works out every position"),
    ("the checks", "gates.py", "accent", "refuse a diagram that cannot be read"),
]
inside = []
for i, (name, code, role, desc) in enumerate(parts):
    px = 80 + i * 330
    inside.append(s.box(name, (px, y, 250, 70), paint=role, sublabel=code))
    s.label(desc, (px + 125, y + 82))

# ════════════════════ 4 · WHERE IT RUNS ═══════════════════════════════════
y = s.section("4 - WHERE IT RUNS")
you = s.box("You / an AI assistant", (60, y, 220, 64), paint="outside")
plug = s.box("excalidraw-diagram\n(a Claude Code plugin)", (620, y, 260, 64),
             paint="tool")
draw2 = s.box("excalidraw.com", (1320, y, 200, 64), paint="outside")
mkt = s.box("plugin marketplace", (620, y + 170, 260, 60), paint="outside")
s.arrow(you, plug, label="describe the system")
s.arrow(plug, draw2, label="the scene opens there, still editable")
s.arrow(mkt, plug, label="installs / updates it")
s.label("Nothing to install beyond Python: no npm, no service, no API key.",
        (60, y + 260), font=Font(14, align="left"))

# ════════════════════ margin notes: the two WHYs ══════════════════════════
# placed right of everything, level with what they explain: outside the diagram
s.note("Why two files? The .excalidraw stays editable box by box; the .html "
       "opens anywhere, with no network.", ids[4])
s.note("Why refuse instead of warn? A picture nobody can read costs more than "
       "no picture at all.", inside[3])

# ════════════════════ legend + glossary ═══════════════════════════════════
_, _, _, bottom = s.bounds()
ly = bottom + 80
s.legend([
    ("The focus: the path, and where it decides", "accent"),
    ("What you write", "words"),
    ("The builder", "engine"),
    ("The skill itself", "tool"),
    ("What you get", "output"),
    ("People and other systems", "outside"),
], (60, ly), title="What the colours mean")
s.glossary([
    ("scene", "the .excalidraw file — the picture, still editable box by box"),
    ("viewer", "the .html file — opens in a browser by double-click"),
    ("pack()", "the part that works out where each box goes, so you need not"),
    ("gate", "a check run before writing; a failed one refuses the file"),
    ("back edge", "an arrow returning to an earlier step, like 'try again'"),
], (560, ly))

out_dir = sys.argv[1] if len(sys.argv) > 1 else "diagrams"
s.save("explainer", out_dir=out_dir, gates=Gates.strict())
print("wrote explainer.excalidraw + .html")
