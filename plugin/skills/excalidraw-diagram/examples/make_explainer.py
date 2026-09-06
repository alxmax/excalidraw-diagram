#!/usr/bin/env python3
"""excalidraw-diagram — plain-English explainer (understandable with no context).

A teaching diagram: read top -> bottom and you learn what the skill is for, how
you use it, what's inside, and where it runs — in everyday words, with every term
decoded in the glossary. Built with the builder's s.section() + s.pipeline().

Run from the repo root, writing into the regenerable diagrams/ dir:
    python plugin/skills/excalidraw-diagram/examples/make_explainer.py diagrams
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from excalidraw_builder import Scene

s = Scene(seed=91, roles={
    "words":   "indigo",   # the description you write
    "engine":  "violet",   # the builder
    "output":  "green",    # things it produces
    "outside": "grey",     # people / external systems
    "tool":    "blue",     # the skill itself
    "stop":    "red",      # the problem / a failed check
    "gate":    "orange",   # a yes/no check
})

s.title("excalidraw-diagram — how it works", 40, -96, size=32)
s.label("A tool that turns a DESCRIPTION of a system into a PICTURE of it, and "
        "refuses to hand you one that cannot be read. Read top to bottom. Every "
        "special word is explained in the Glossary at the bottom.",
        40, -52, size=15, align="left")

# ════════════════════ 1 · THE PROBLEM IT SOLVES ═══════════════════════════
y = s.section("1 - THE PROBLEM IT SOLVES")
know = s.box("What someone\nUNDERSTANDS\nabout a system", 120, y, w=230, h=84, fill="words")
draw = s.box("What a diagram\nof it would show", 880, y, w=230, h=84, fill="outside")
s.arrow(know, draw, dashed=True, color="red", start="arrow", end="arrow",
        label="the picture nobody has the afternoon to draw")
fix = s.box("excalidraw-diagram", 460, y + 250, w=330, h=70, fill="tool")
s.arrow(fix, know, label="you describe it in words")
s.arrow(fix, draw, label="it draws and checks it")
s.label("The fix: you say what the parts are and what connects to what; the tool "
        "works out where every box goes and refuses to write an unreadable one.",
        120, y + 350, size=14, align="left")

# ════════════════════ 2 · HOW YOU USE IT ══════════════════════════════════
y = s.section("2 - HOW YOU USE IT   (left -> right; ask, and this happens)")
ids = s.pipeline([
    {"text": "you ask\nfor a diagram", "kind": "terminator", "fill": "outside"},
    ("describe the\nparts and links", "process", "words"),
    ("the builder\nplaces them", "process", "engine"),
    {"text": "readable?", "kind": "decision", "fill": "gate", "label": "yes"},
    {"text": "two files\nyou can open", "kind": "terminator", "fill": "output"},
], 120, y + 30, gap=150)
s.route_under(ids[3], ids[1], label="no -> say it better, run again", drop=76)
s.label("In words:  you name the parts  -  the builder chooses the positions  -  "
        "seven checks look at the result  -  and only a clean one is written.",
        120, y + 250, size=14, align="left")

# ════════════════════ 3 · WHAT'S INSIDE ═══════════════════════════════════
y = s.section("3 - WHAT'S INSIDE   (the main parts)")
parts = [
    ("SKILL.md", "tool", "the instructions the assistant follows"),
    ("excalidraw_builder.py", "engine", "one Python file, no dependencies"),
    ("pack()", "engine", "decides where every box goes"),
    ("the seven gates", "gate", "refuse a diagram that cannot be read"),
]
for i, (name, role, desc) in enumerate(parts):
    px = 80 + i * 330
    nid = s.box(name, px, y, w=250, h=58, fill=role)
    s.label(desc, px + 125, y + 70, size=12)

# ════════════════════ 4 · WHERE IT RUNS ═══════════════════════════════════
y = s.section("4 - WHERE IT RUNS")
you = s.box("You / an AI assistant", 60, y, w=220, h=64, fill="outside")
plug = s.box("excalidraw-diagram\n(a Claude Code plugin)", 620, y, w=260, h=64, fill="tool")
draw2 = s.box("excalidraw.com", 1320, y, w=200, h=64, fill="outside")
mkt = s.box("plugin marketplace", 620, y + 170, w=260, h=60, fill="outside")
s.arrow(you, plug, label="describe the system")
s.arrow(plug, draw2, label="the scene opens there, still editable")
s.arrow(mkt, plug, label="installs / updates it")
s.label("Nothing to install beyond Python: no npm, no service, no API key.",
        60, y + 260, size=14, align="left")

# ════════════════════ legend + glossary ═══════════════════════════════════
_, _, _, bottom = s.bounds()
ly = bottom + 80
s.legend([
    ("What you write", "words"),
    ("The builder", "engine"),
    ("The skill itself", "tool"),
    ("A check that can refuse", "gate"),
    ("What you get", "output"),
    ("People and other systems", "outside"),
], 60, ly, title="What the colours mean")
s.glossary([
    ("scene", "the .excalidraw file — the picture, still editable box by box"),
    ("viewer", "the .html file — opens in a browser by double-click"),
    ("pack()", "the part that works out where each box goes, so you need not"),
    ("gate", "a check run before writing; a failed one refuses the file"),
    ("back edge", "an arrow returning to an earlier step, like 'try again'"),
], 520, ly)

out_dir = sys.argv[1] if len(sys.argv) > 1 else "diagrams"
s.save("explainer", out_dir=out_dir, crossing_check="error",
       legend_check="error", overflow_check="error", text_overlap_check="error",
       label_fit_check="error")
print("wrote explainer.excalidraw + .html")
