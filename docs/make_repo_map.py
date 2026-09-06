#!/usr/bin/env python3
"""How this repository works — the diagram embedded in README.md.

Three stacked sections, read top to bottom: what is in the repo, how a diagram
gets made, and what keeps the repo honest (tests, requirement gate, CI,
release). A legend decodes the colours and a glossary decodes the terms.

Regenerate from the repo root (the .excalidraw + .html land where you say):
    python -X utf8 docs/make_repo_map.py out/
Then open out/repo_map.html and use Excalidraw's menu > Export image to refresh
docs/repo_map.png.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "plugin",
                                "skills", "excalidraw-diagram", "scripts"))
from excalidraw_builder import Scene

s = Scene(seed=7, roles={
    "you":      "grey",     # the person asking, or Claude acting for them
    "contract": "violet",   # SKILL.md - the instructions the skill follows
    "engine":   "blue",     # excalidraw_builder.py
    "gate":     "orange",   # a check that can fail the build
    "output":   "green",    # files the skill produces
    "spec":     "indigo",   # requirements/ - what the skill promises
    "ship":     "teal",     # packaging: manifests, marketplace, CI
})

s.title("excalidraw-diagram — how this repository works", 40, -96, size=32)
s.label("A Claude Code plugin that turns a description of a system into an editable "
        "Excalidraw scene plus an HTML viewer. Read top to bottom; each section is "
        "one question. Every colour is in the legend, every term in the glossary.",
        40, -52, size=14, align="left")

# ═══════════════════════ 1 · WHAT IS IN THE REPO ═══════════════════════
y = s.section("1 - WHAT IS IN THE REPO   the six parts and what each is for")
row_y = y + 44
parts = s.row([
    ("SKILL.md\nthe contract Claude follows", "contract"),
    ("excalidraw_builder.py\nthe builder, stdlib only", "engine"),
    ("test_excalidraw.py\n65 tests + every example", "gate"),
    ("examples/make_*.py\nfour worked generators", "output"),
    ("requirements/\n11 promises, gate-checked", "spec"),
], 80, row_y, w=215, h=70, gap=26, font_size=12)
s.enclose(parts, label="plugin/  -  what gets installed")
_, _, fx2, _ = s.bounds()
s.box("marketplace.json + CI\nversion, checks, release", fx2 + 60, row_y, w=215, h=70,
      fill="ship", font_size=12)
s.label("One skill, one Python file, no dependencies. The examples are the documentation: "
        "CI runs each one, so a stale example is a failed build.",
        80, row_y + 110, size=12, align="left")

# ═══════════════════════ 2 · HOW A DIAGRAM GETS MADE ═══════════════════
y = s.section("2 - HOW A DIAGRAM GETS MADE   left -> right, from a sentence to two files")
flow_y = y + 60
steps = s.pipeline([
    {"text": "\"explain how\nX works\"", "kind": "terminator", "fill": "you", "w": 150, "h": 56},
    ("read SKILL.md,\nexplore X", "process", "contract"),
    ("write\nmake_diagram.py", "process", "contract"),
    ("run it against\nthe builder", "process", "engine"),
    {"text": "save():\n7 gates\npass?", "kind": "decision", "fill": "gate", "label": "yes"},
    {"text": ".excalidraw\n+ .html", "kind": "terminator", "fill": "output", "w": 150, "h": 56},
], 120, flow_y, gap=110)
s.route_under(steps[4], steps[2], label="no -> fix the layout, run again", drop=60)
s.label("The model never writes Excalidraw JSON. It writes a short Python script; the builder "
        "owns the format's invariants (arrow bindings, seeds, z-order) and refuses to save an "
        "unreadable scene: overlaps, crossings, unlegended colours, text overflow.",
        120, flow_y + 175, size=12, align="left")

# ═══════════════════════ 3 · WHAT KEEPS IT HONEST ═══════════════════════
y = s.section("3 - WHAT KEEPS IT HONEST   every push, every pull request")
ci_y = y + 40
checks = s.row([
    ("tests\n3.9 / 3.12 / 3.13\nubuntu + windows", "gate"),
    ("examples\neach generator\nmust run", "gate"),
    ("gate\nrequirements vs code:\n0 errors", "gate"),
    ("versions\nplugin.json ==\nmarketplace.json x2", "gate"),
    ("changelog\na bump needs\nits entry", "gate"),
], 80, ci_y, w=190, h=84, gap=24, font_size=12)
ci = s.enclose(checks, label="GitHub Actions  -  five jobs, all must pass")

rel_y = ci_y + 210
pr = s.box("pull request\n(main is push-protected)", 80, rel_y, w=230, h=70,
           fill="you", font_size=12)
mkt = s.box("marketplace.json\nlists the version", 560, rel_y, w=230, h=70,
            fill="ship", font_size=12)
inst = s.box("/plugin install\nexcalidraw-diagram", 1040, rel_y, w=230, h=70,
             fill="you", font_size=12)
s.arrow(pr, ci, label="triggers", dashed=True)
s.arrow(pr, mkt, label="merge + version bump")
s.arrow(mkt, inst, label="consumers receive it")
s.label("The requirement corpus is the promise, the tests are the proof, the version bump is "
        "how the promise reaches anyone. Miss the bump and nothing errors: the plugin simply "
        "never updates.",
        80, rel_y + 100, size=12, align="left")

# ═══════════════════════ legend + glossary ═══════════════════════════════
_, _, _, bottom = s.bounds()
ly = bottom + 70
s.legend([
    ("You, or Claude acting for you", "you"),
    ("The skill's contract (SKILL.md)", "contract"),
    ("The builder", "engine"),
    ("A check that can fail the build", "gate"),
    ("What the skill produces", "output"),
    ("Requirements: what is promised", "spec"),
    ("Packaging and release", "ship"),
], 80, ly, title="What the colours mean")
s.glossary([
    ("skill", "a markdown contract Claude Code loads when a request matches it"),
    ("builder", "excalidraw_builder.py - a Python API that writes valid Excalidraw scenes"),
    ("gate", "a check at save() time; 'error' mode refuses to write an unreadable diagram"),
    ("requirement", "one markdown file per promise; code points back at it with a tag"),
    ("marketplace", "the JSON index /plugin install reads; it repeats the version twice"),
], 520, ly)

out_dir = sys.argv[1] if len(sys.argv) > 1 else "out"
s.save("repo_map", out_dir=out_dir,
       crossing_check="error", legend_check="error", overflow_check="error",
       text_overlap_check="error", label_fit_check="error")
print("wrote repo_map.excalidraw + .html")
