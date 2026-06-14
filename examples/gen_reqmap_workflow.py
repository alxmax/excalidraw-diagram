#!/usr/bin/env python3
"""Build the requirement-manager whole-project poster.

A non-trivial, real-world example for the excalidraw-diagram skill. It shows how
the ENTIRE requirement-manager project works, as a modular poster, and doubles
as a showcase of the role-colour + legend pattern: fills are declared by meaning
(Scene(roles=…)) and a legend() renders the key, so a reader with no context can
decode every colour. save(crossing_check="error", legend_check="error") enforces a
crossing-free, fully-legended scene (every fill must appear in the legend key).

Left -> right journey:  the plugin repo (modules)  ->  marketplace  ->
Claude Code install  ->  a consumer repo where it runs.  Plus the dogfood loop
and the published CI action.

Run from the repo root so the output lands in ./docs:
    python plugin/skills/excalidraw-diagram/examples/gen_reqmap_workflow.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from excalidraw_builder import Scene

# Colour by ROLE, not decoratively — declared once, rendered as a legend below.
ROLES = {
    "disk":   "grey",    # files on disk (inputs, seeded copies, manifests)
    "skill":  "blue",    # the skill, Claude Code, and the SSOT model
    "engine": "teal",    # the reqmap.py engine + its commands
    "output": "indigo",  # the viewer and generated artifacts
    "gate":   "orange",  # the CI gate and the published action
    "dist":   "yellow",  # marketplace / packaging (distribution)
    "meta":   "green",   # self-coherence: dogfood requirements, tests
}

s = Scene(seed=11, roles=ROLES)


def module(title, x, y, w, h):
    """A dashed module-frame with a left-aligned title inside the top edge."""
    fid = s.frame(x, y, w, h, dashed=True)
    s.label(title, x + 14, y + 10, size=13, color="black", align="left")
    return fid


# ── Title + reading guide ────────────────────────────────────────────────────
s.title("Requirement Manager  —  how the whole project works", 40, -78, size=30)
s.label("A Claude Code plugin. Built & shipped from THIS repo (left)  →  "
        "published to a marketplace  →  installed in Claude Code  →  "
        "seeded into ANY repo, where it runs (right).",
        40, -38, size=15, color="grey", align="left")

# ════════════════════════════════════════════════════════════════════════════
# ZONE 1 — THE PLUGIN REPO  (six modules)
# ════════════════════════════════════════════════════════════════════════════
z1 = s.frame(40, 120, 800, 820)
s.label("THE PLUGIN REPO  (this project)", 54, 96, size=16, color="black", align="left")

# M-SKILL ---------------------------------------------------------------------
module("SKILL  (plugin/skills/)", 70, 160, 350, 210)
s.box("requirement-\nmanager", 84, 220, 150, 60, fill="skill", font_size=12)
s.box("quality-\nreview",      244, 220, 158, 60, fill="skill", font_size=12)
s.box("excalidraw-\ndiagram",   84, 295, 318, 56, fill="skill", font_size=12)

# M-ENGINE --------------------------------------------------------------------
module("ENGINE  reqmap.py  (stdlib, 1 file)", 450, 160, 350, 210)
e1 = s.box("parse /\nscan", 462, 225, 74, 58, fill="engine", font_size=12)
e2 = s.box("model",        548, 225, 64, 58, fill="engine", font_size=12)
e3 = s.box("commands",     624, 225, 86, 58, fill="engine", font_size=12)
e4 = s.box("outputs",      722, 225, 66, 58, fill="engine", font_size=12)
s.arrow(e1, e2); s.arrow(e2, e3); s.arrow(e3, e4)
s.box("test_reqmap.py", 462, 300, 200, 46, fill="meta", font_size=12)

# M-VIEWER --------------------------------------------------------------------
module("VIEWER APP  (app/  Vite + React)", 70, 430, 350, 210)
v1 = s.box("App.jsx ·\nviews · lib", 84, 490, 150, 60, fill="output", font_size=12)
v2 = s.box("npm run\nbuild:viewer",  244, 490, 158, 60, fill="output", font_size=12)
s.box("_map_viewer.html  (template)", 84, 565, 318, 50, fill="output", font_size=12)
s.arrow(v1, v2)

# M-ACTION --------------------------------------------------------------------
module("CI ACTION  (check/action.yml)", 450, 430, 350, 210)
a1 = s.box("check/action.yml", 462, 495, 210, 50, fill="gate", font_size=12)
a2 = s.box("published tag  @v1", 462, 570, 210, 50, fill="gate", font_size=12)
s.arrow(a1, a2)

# M-PACKAGING -----------------------------------------------------------------
module("PACKAGING", 70, 700, 350, 210)
s.box("plugin.json\n(manifest)",  84, 760, 150, 60, fill="dist", font_size=12)
s.box("marketplace.json",        244, 760, 158, 60, fill="dist", font_size=12)

# M-SELF ----------------------------------------------------------------------
module("SELF-COHERENCE  (dogfood)", 450, 700, 350, 210)
s.box("plugin/\nrequirements/*", 462, 760, 150, 60, fill="meta", font_size=12)
s.box("check_versions.py", 622, 760, 168, 44, fill="meta", font_size=12)
s.box("pre-commit · CI · tests", 462, 838, 328, 46, fill="meta", font_size=12)

# ════════════════════════════════════════════════════════════════════════════
# COLOUR LEGEND  (fills the empty pocket below ZONE 2, between the three zones)
# ════════════════════════════════════════════════════════════════════════════
s.legend(
    [("On disk", "disk"), ("Skill / SSOT", "skill"), ("Engine (reqmap)", "engine"),
     ("Outputs / viewer", "output"), ("CI gate / action", "gate"),
     ("Distribution", "dist"), ("Dogfood / tests", "meta")],
    920, 600, title="What the colours mean")

# ════════════════════════════════════════════════════════════════════════════
# ZONE 2 — SHIP & INSTALL  (the bridge)
# ════════════════════════════════════════════════════════════════════════════
s.label("SHIP & INSTALL", 900, 270, size=16, color="black", align="left")
mkt = s.box("Marketplace\nmarketplace.json", 900, 300, 260, 90, fill="dist", font_size=14)
cc  = s.box("Claude Code\ninstall plugin →\nskill available", 900, 440, 260, 120, fill="skill", font_size=14)
s.arrow(mkt, cc, label="install")

# ════════════════════════════════════════════════════════════════════════════
# ZONE 3 — A CONSUMER REPO  (where it runs)
# ════════════════════════════════════════════════════════════════════════════
z3 = s.frame(1240, 180, 820, 610)
s.label("A CONSUMER REPO  (any project)", 1254, 156, size=16, color="black", align="left")

seeded = s.box("Seeded by the skill\nscripts/reqmap.py · _map_viewer.html · .reqmapignore",
               1290, 220, 470, 90, fill="disk", font_size=12)
loop   = s.box("requirements/*.md   ⇄   source code\nSSOT   ↔   # implements: tags",
               1290, 360, 470, 90, fill="skill", font_size=13)
cmds   = s.box("reqmap commands\ninit · check · map · next · health · …",
               1290, 500, 470, 90, fill="engine", font_size=13)
outs   = s.box("_map.html viewer\n_findings.md", 1820, 500, 220, 90, fill="output", font_size=12)
gate   = s.box("GATE on every commit\npre-commit hook   +   GitHub Action @v1",
               1290, 650, 750, 100, fill="gate", font_size=13)

s.arrow(seeded, loop)
s.arrow(loop, cmds)
s.arrow(cmds, outs)
s.arrow(cmds, gate)

# ════════════════════════════════════════════════════════════════════════════
# INTER-MODULE FLOW
# ════════════════════════════════════════════════════════════════════════════
s.arrow(z1, mkt, label="published")
# install/seed — routed (right, up, in) so it clears the SSOT-loop box.
# Short label so its panel fits the gap between ZONE 2 and ZONE 3.
s.path([(1160, 500), (1220, 500), (1220, 265), (1290, 265)],
       color="blue", end="arrow", label="seeds + init")

# dogfood loop — engine runs on its own requirements (routed on the right edge).
# Short label so its white panel fits the narrow strip without hitting a box.
s.path([(800, 265), (822, 265), (822, 805), (800, 805)],
       color="green", dashed=True, end="arrow", label="dogfoods own reqs")

# the published action reaches the consumer's CI (routed below everything)
s.path([(760, 940), (760, 1010), (1655, 1010), (1655, 752)],
       color="orange", dashed=True, end="arrow",
       label="consumer CI runs Action @v1")

# ── Glossary — decode the jargon (a term→meaning key, below the diagram) ──────
s.glossary(
    [("SSOT", "single source of truth — one .md per capability"),
     ("dogfood", "the engine runs on its own requirements"),
     ("CI action", "GitHub Action running the gate on every push / PR"),
     ("seed / init", "copy reqmap.py into a repo and scaffold it"),
     ("drift gate", "fails if requirements no longer match the code"),
     ("@v1", "the published action's pinned version tag")],
    40, 1060, title="Glossary")

# ════════════════════════════════════════════════════════════════════════════
out_dir = sys.argv[1] if len(sys.argv) > 1 else "docs"
pj, ph = s.save("reqmap_workflow", out_dir=out_dir,
                crossing_check="error", legend_check="error")
print("elements:", len(s.elements))
print("overlaps:", s.check_overlaps())
print("crossings:", s.check_arrow_crossings())
print("legend coverage gaps:", s.check_legend_coverage())
print("wrote:", pj, ph)
