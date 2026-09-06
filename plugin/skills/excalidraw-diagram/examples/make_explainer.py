#!/usr/bin/env python3
"""requirement-manager — plain-English explainer (understandable with no context).

A teaching diagram: read top -> bottom and you learn what the plugin is for, how
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
    "plan":    "indigo",   # the requirement files / intent
    "engine":  "violet",   # reqmap.py
    "output":  "green",    # things it produces
    "outside": "grey",     # people / external systems
    "tool":    "blue",     # the plugin itself
    "stop":    "red",      # the problem / a failed check
    "gate":    "orange",   # a yes/no check
})

s.title("requirement-manager — how it works", 40, -96, size=32)
s.label("A tool that stops a project's PLAN and its CODE from quietly drifting "
        "apart. Read top to bottom. Every special word is explained in the "
        "Glossary at the bottom.", 40, -52, size=15, align="left")

# ════════════════════ 1 · THE PROBLEM IT SOLVES ═══════════════════════════
y = s.section("1 - THE PROBLEM IT SOLVES")
intent = s.box("What the project\nSHOULD do\n(the plan)", 120, y, w=230, h=84, fill="plan")
code   = s.box("What the code\nACTUALLY does", 880, y, w=230, h=84, fill="outside")
s.arrow(intent, code, dashed=True, color="red", start="arrow", end="arrow",
        label="over time they silently disagree  =  'drift'")
fix = s.box("requirement-manager", 460, y + 250, w=330, h=70, fill="tool")
s.arrow(fix, intent, label="keeps ONE agreed plan")
s.arrow(fix, code, label="checks code still matches")
s.label("The fix: one source of truth (the plan files) + an automatic check that "
        "the code still matches it.", 120, y + 234, size=13)

# ════════════════════ 2 · HOW YOU USE IT (the workflow) ═══════════════════
y = s.section("2 - HOW YOU USE IT   (left -> right; each box is a command you run)")
ids = s.pipeline([
    ("Start", "terminator", "outside"),
    {"text": "init\n(set up files)", "kind": "process", "fill": "engine"},
    {"text": "draft\n(from code)", "kind": "process", "fill": "engine"},
    {"text": "confirm\n(agree it)", "kind": "process", "fill": "engine"},
    {"text": "sync\n(rescan)", "kind": "process", "fill": "engine"},
    {"text": "gate\ncode = plan?", "kind": "decision", "fill": "gate", "label": "yes"},
    {"text": "map\n(the picture)", "kind": "process", "fill": "engine"},
    {"text": "next\n(what now?)", "kind": "process", "fill": "engine"},
    ("Commit", "terminator", "outside"),
], 60, y, gap=112)
s.route_under(ids[5], ids[4], label="no -> fix the code, then re-check", drop=72)
s.label("In words:  init = create the plan files  -  draft = auto-write a first "
        "version from existing code  -  confirm = mark a plan item as agreed  -  "
        "sync = rescan the code and update  -  gate = does the code still match? "
        " -  map = build a clickable picture  -  next = what should I work on.",
        60, y + 132, size=13)

# ════════════════════ 3 · WHAT'S INSIDE ═══════════════════════════════════
y = s.section("3 - WHAT'S INSIDE   (the main parts)")
parts = [
    ("reqmap.py", "engine", "the engine: one Python file that does it all"),
    ("requirement files", "plan", "the plan: one file per capability (the truth)"),
    ("the gate", "gate", "the automatic check, runs before every commit"),
    ("the map", "output", "a clickable picture of plan <-> code"),
    ("3 skills", "tool", "how Claude Code drives the tool"),
]
px = 60
for name, role, desc in parts:
    nid = s.box(name, px, y, w=220, h=58, fill=role)
    s.label(desc, px + 110, y + 70, size=12)
    px += 340          # pitch > widest caption (~313px) so captions never overlap

# ════════════════════ 4 · WHERE IT RUNS ═══════════════════════════════════
y = s.section("4 - WHERE IT RUNS")
you   = s.box("You / an AI agent", 60, y, w=200, h=64, fill="outside")
plug  = s.box("requirement-manager\n(a Claude Code plugin)", 600, y, w=240, h=64, fill="tool")
gitci = s.box("git + CI", 1300, y, w=180, h=64, fill="outside")
mkt   = s.box("plugin marketplace", 600, y + 170, w=240, h=60, fill="outside")
s.arrow(you, plug, label="edit plan & code, run commands")
s.arrow(plug, gitci, label="the gate runs before commit / on the server")
s.arrow(mkt, plug, label="installs / updates it")

# ════════════════════ legend + glossary ═══════════════════════════════════
_, _, max_x, max_y = s.bounds()
ly = max_y + 50
s.legend([
    ("the plan (requirement files)", "indigo"),
    ("the engine (reqmap.py)", "violet"),
    ("things it produces", "green"),
    ("people / outside systems", "grey"),
    ("the plugin itself", "blue"),
    ("a problem / failed check", "red"),
    ("a yes/no check (gate)", "orange"),
], 60, ly, title="Legend — colour = what kind of thing")

s.glossary([
    ("requirement", "a short file saying what one capability should do + why"),
    ("plan / SSOT", "all requirement files together = the single source of truth"),
    ("drift", "when the code and the plan quietly stop matching"),
    ("gate", "the automatic pass/fail check (links + drift + tests)"),
    ("sync", "rescan the code and update the saved baseline"),
    ("map", "an interactive HTML picture of requirements and their code"),
    ("CI", "a server that re-runs the same checks on every change"),
    ("plugin / skill", "an add-on that Claude Code loads to gain this ability"),
], 620, ly, title="Glossary — every special word, in plain English")

out_dir = sys.argv[1] if len(sys.argv) > 1 else "docs"
s.save("explainer", out_dir=out_dir, crossing_check="error",
       legend_check="error", overflow_check="error", text_overlap_check="error",
       label_fit_check="error")
print("wrote explainer.excalidraw + .html")
