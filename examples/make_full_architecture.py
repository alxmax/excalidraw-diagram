#!/usr/bin/env python3
"""requirement-manager — Complete Architecture poster (single .excalidraw + .html).

The canonical self-diagram of this repo, and the reference for the skill's
ADAPTIVE recipe: include only the layers a repo actually needs. requirement-
manager needs FOUR of the six layer-types — it has no execution modes and no
per-part model assignment, so MODES and MODEL are deliberately omitted:

  1. STRUCTURE     the plugin's containers
  2. WORKFLOWS     one pipeline per skill (3 skills, 3 lanes — the per-tool rule)
  3. INTEGRATION   how it is invoked, gated, and shipped
  6. DATA SCHEMA   the requirement record it maintains

Colour = role (one legend decodes all layers); a glossary decodes the jargon.
All four save() gates run at "error". Run from the repo root, writing into the
regenerable diagrams/ dir:
    python plugin/skills/excalidraw-diagram/examples/make_full_architecture.py diagrams
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from excalidraw_builder import Scene

s = Scene(seed=31, roles={
    "engine":   "blue",     # reqmap.py
    "skill":    "violet",   # a Claude Code skill / the plugin
    "ssot":     "indigo",   # requirement specs (single source of truth)
    "artifact": "green",    # generated outputs (_map.*, _reqlock)
    "viewer":   "pink",     # the React map viewer / app
    "external": "grey",     # systems outside the plugin
    "gate":     "orange",   # the drift gate / a decision
    "enum":     "teal",     # schema enum / annotation
})

s.title("requirement-manager — Architecture", 40, -92, size=32)
s.label("A Claude Code plugin: one markdown file per capability as the SSOT, a "
        "drift gate, and a navigable requirement map. Left -> right = order.",
        40, -52, size=14, align="left")

# ═══════════════════════ 1 · STRUCTURE ═══════════════════════
y = s.section("1 - STRUCTURE   the plugin's containers")
parts = s.row([
    ("reqmap.py\nparse-scan-gate-map", "engine"),
    ("3 skills\n(SKILL.md)", "skill"),
    ("requirements/*.md\n36 specs - SSOT", "ssot"),
    ("_map.* / _reqlock\ngenerated", "artifact"),
    ("app/ viewer\nReact", "viewer"),
], 80, y + 44, w=200, h=64, gap=28, font_size=13)
s.enclose(parts, label="requirement-manager plugin")

# ═══════════════════════ 2 · WORKFLOWS (per skill) ═══════════
# Multi-tool repo -> one labelled lane() per skill (the per-tool sub-workflow rule).
y = s.section("2 - WORKFLOWS   one pipeline per skill (left -> right = run order)")

# Lane 1 — requirement-manager (the core: SSOT + drift gate)
row1 = y + 60
rm = s.pipeline([
    ("init", "process", "skill"),
    ("draft", "process", "skill"),
    ("sync", "process", "skill"),
    {"text": "gate:\ndrift?", "kind": "decision", "fill": "gate", "label": "clean"},
    ("map", "process", "skill"),
    ("_map.html", "terminator", "artifact"),
], 120, row1, gap=120)
s.lane(rm, "requirement-manager  -  core: SSOT + drift gate")
s.route_under(rm[3], rm[2], label="no -> re-sync", drop=55)

# Lane 2 — requirement-quality-review (advisory, never gates)
row2 = row1 + 215
qr = s.pipeline([
    ("reqmap review\n(JSON)", "data", "external"),
    ("AI quality\ncheck", "process", "skill"),
    ("advisory\nfindings", "terminator", "artifact"),
], 120, row2, gap=70)
s.lane(qr, "requirement-quality-review  -  advisory, never edits / never gates")

# Lane 3 — excalidraw-diagram (one poster per repo)
row3 = row2 + 175
ex = s.pipeline([
    ("explore repo", "process", "skill"),
    ("discover /\nscaffold", "process", "skill"),
    ("fill layers", "process", "skill"),
    {"text": "save ->\n.excalidraw + .html", "kind": "terminator", "fill": "artifact", "w": 200, "h": 54},
], 120, row3, gap=64)
s.lane(ex, "excalidraw-diagram  -  one adaptive poster per repo")

s.label("dogfood: the requirement-manager skill runs its own gate on requirements/ (must be 0 errors)",
        120, row3 + 120, size=12, align="left")

# ═══════════════════════ 3 · INTEGRATION ═════════════════════
y = s.section("3 - INTEGRATION   how it is invoked, gated, and shipped")
yi = y + 30
dev = s.box("Developer / AI", 80, yi, w=170, h=70, fill="external", font_size=13)
cc  = s.box("Claude Code", 450, yi, w=180, h=70, fill="external", font_size=13)
plug = s.box("requirement-manager\n(skill + engine)", 840, yi, w=210, h=70,
             fill="skill", font_size=13)
tgt = s.box("target repo\nseeded reqmap.py", 1270, yi, w=190, h=70,
            fill="external", font_size=13)
s.arrow(dev, cc, label="uses")
s.arrow(cc, plug, label="invokes [skill]")
s.arrow(plug, tgt, label="seeds reqmap.py")
yb = yi + 150
mkt = s.box(".claude-plugin\nmarketplace.json", 80, yb, w=190, h=64,
            fill="external", font_size=13)
inst = s.box("/plugin install", 470, yb, w=170, h=64, fill="external", font_size=13)
ci = s.box("git + CI\ncheck@v1 runs the gate", 840, yb, w=220, h=64,
           fill="external", font_size=13)
s.arrow(mkt, inst, label="lists")
s.label("distribution (left) + CI gating (right): every push runs the drift gate.",
        80, yb + 84, size=12, align="left")
# multi-platform (v2.7): usable beyond Claude Code via generated artifacts
ym = yb + 150
gen = s.box("generated artifacts\ntool_definition.json\n+ SKILL.universal.md", 80, ym,
            w=230, h=80, fill="artifact", font_size=12)
others = s.box("other AI assistants\nCopilot / Gemini / Codex", 560, ym,
               w=230, h=80, fill="external", font_size=12)
s.arrow(gen, others, label="run reqmap CLI")
s.label("multi-platform: a command registry generates the schema + instructions other AIs "
        "consume; reqmap.py is stdlib + tool-agnostic, drift-guarded in the gate.",
        80, ym + 100, size=12, align="left")

# ═══════════════════════ 6 · DATA SCHEMA ═════════════════════
y = s.section("6 - DATA SCHEMA   the requirement record it maintains")
ys = y + 20
record = s.box(
    "requirement (*.md)\n\n"
    "id: REQ-...\n"
    "status: draft | confirmed\n"
    "layer: need | feature | bus\n"
    "depends_on: [ ... ]\n"
    "satisfies: [ NEED-... ]\n"
    "milestone\n\n"
    "WHY / WHAT / WHERE / HOW",
    560, ys, w=330, h=260, fill="ssot", font_size=12)
code = s.box("tagged source code\n# implements: / # tested-by:", 80, ys + 30,
             w=230, h=64, fill="enum", font_size=12)
gate = s.box("reqmap gate\nlink-sync + drift", 80, ys + 170, w=230, h=64,
             fill="gate", font_size=13)
s.arrow(code, record, label="tags link to")
s.arrow(gate, record, label="checks")
mapj = s.box("_map.json\n{engine_version,\nnodes, edges}", 1050, ys + 20,
             w=240, h=84, fill="artifact", font_size=12)
lock = s.box("_reqlock.json\ncontent-hash baseline", 1100, ys + 180, w=240, h=64,
             fill="artifact", font_size=12)
s.arrow(record, mapj, label="map builds")
s.arrow(record, lock, label="gate hashes")

# ═══════════════════════ legend + glossary ═══════════════════
_, _, max_x, max_y = s.bounds()
ly = max_y + 60
s.legend([
    ("engine - reqmap.py", "blue"),
    ("skill / the plugin", "violet"),
    ("requirement spec (SSOT)", "indigo"),
    ("generated artifact", "green"),
    ("map viewer / app", "pink"),
    ("external system", "grey"),
    ("gate / decision", "orange"),
    ("schema enum / annotation", "teal"),
], 80, ly, title="Legend - colour = role")
s.glossary([
    ("SSOT", "single source of truth - requirements/*.md"),
    ("drift", "content hash of a spec vs _reqlock.json baseline"),
    ("gate", "pre-commit link-sync + drift + test-link check"),
    ("dogfood", "the repo runs reqmap on its own requirements/"),
    ("layer", "bus (foundation) / feature (composes bus) / need (stakeholder)"),
    ("@v2", "major-alias git tag of the published GitHub Action"),
], 760, ly, title="Glossary")

# The capabilities this poster actually draws. Stamped into the generated page as a
# `generated-from:` tag so REQ-DOCBUNDLE-026 can do its job on the repo's own biggest
# bundle: a contract change in any of these lists the poster as needing a redraw,
# instead of the doc silently describing a version of the system that no longer exists.
# Kept to what the diagram DEPICTS - a longer list would trade real signal for noise.
LINEAGE = [
    "CORE-PARSE-001",   # the requirement record, drawn as the DATA SCHEMA layer
    "CORE-SCAN-002",    # member discovery, the scan arrow
    "CORE-DRIFT-003",   # the lock + drift comparison
    "REQ-CHECK-006",    # the gate box
    "REQ-MAP-007",      # the generated artifacts
    "REQ-VIEWER-007",   # the map viewer lane
]

out_dir = sys.argv[1] if len(sys.argv) > 1 else "diagrams"
pj, ph = s.save("full_architecture", out_dir=out_dir, crossing_check="error",
                legend_check="error", overflow_check="error", text_overlap_check="error",
                label_fit_check="error")

# newline="\n" so the page is byte-identical whoever regenerates it (Python's
# default translates "\n" to os.linesep, which made this file differ by platform).
page = open(ph, encoding="utf-8").read()
tag = "<!-- generated-from: " + ", ".join(LINEAGE) + " -->"
if tag not in page:
    page = page.replace("<head>", "<head>" + chr(10) + tag, 1)
    with open(ph, "w", encoding="utf-8", newline=chr(10)) as f:
        f.write(page)
print("wrote full_architecture.excalidraw + .html")
