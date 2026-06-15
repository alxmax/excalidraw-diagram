#!/usr/bin/env python3
"""requirement-manager — Complete Architecture poster (single .excalidraw + .html).

Four stacked sections, top -> bottom (modeled on a complete-architecture poster):
  1. STRUCTURE       — the plugin's containers (C4 container view)
  2. WORKFLOW        — the reqmap command pipeline, left->right run order
  3. INTEGRATION     — how it is invoked, gated and shipped
  4. REQUIREMENT MODEL — layers, code tags, and the drift lock

Uses the builder's poster helpers: s.section() auto-stacks each region, and
s.pipeline() lays out + chains the workflow band. Colour = role (single legend);
a glossary decodes the jargon. Exercises c4()/person() and the ISO 5807 diamond.

Run from the repo root, writing into the regenerable diagrams/ dir:
    python plugin/skills/excalidraw-diagram/examples/make_full_architecture.py diagrams
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from excalidraw_builder import Scene

s = Scene(seed=73, roles={
    "engine":   "violet",   # reqmap.py
    "viewer":   "pink",     # the React map viewer / app
    "skill":    "blue",     # a Claude Code skill / the plugin
    "ssot":     "indigo",   # requirement specs (single source of truth)
    "artifact": "green",    # generated outputs
    "external": "grey",     # systems outside the plugin
    "person":   "teal",     # an actor
    "gate":     "orange",   # a decision / gate
})

s.title("requirement-manager — Complete Architecture", 40, -116, size=34)
s.label("A Claude Code plugin: a single source of truth between intent and code "
        "- a drift gate, a navigable requirement map, and a dogfood loop.",
        40, -72, size=15, align="left")

# ═══════════════════════════ 1 · STRUCTURE ════════════════════════════════
y = s.section("1 - STRUCTURE   the plugin's containers")
skills = s.c4("Skills", 80, y, kind="Container", tech="skill",
              desc="3x SKILL.md", fill="skill", w=220, h=92)
engine = s.c4("reqmap.py", 340, y, kind="Container", tech="Python",
              desc="parse-scan-gate-map", fill="engine", w=240, h=92)
specs  = s.c4("Requirement specs", 620, y, kind="Container", tech="Markdown",
              desc="29 specs - the SSOT", fill="ssot", w=230, h=92)
arts   = s.c4("Generated artifacts", 890, y, kind="Container", tech="JSON/MD",
              desc="_map.*, _reqlock", fill="artifact", w=230, h=92)
viewer = s.c4("Map viewer", 1160, y, kind="Container", tech="React/Vite",
              desc="_map.html", fill="viewer", w=210, h=92)
s.enclose([skills, engine, specs, arts, viewer],
          label="requirement-manager plugin   [Software System]")
s.arrow(skills, engine, label="runs [CLI]")
s.arrow(engine, specs, label="reads / writes")
s.arrow(viewer, arts, label="reads _map.json")

# ═══════════════════════════ 2 · WORKFLOW ═════════════════════════════════
y = s.section("2 - WORKFLOW   the reqmap pipeline (left -> right = run order)")
ids = s.pipeline([
    ("Start", "terminator", "external"),
    ("init", "process", "engine"),
    ("draft", "process", "engine"),
    ("confirm", "process", "engine"),
    ("sync", "process", "engine"),
    {"text": "gate:\ndrift & links\nclean?", "kind": "decision", "fill": "gate", "label": "yes"},
    ("map", "process", "engine"),
    ("next", "process", "engine"),
    ("Commit", "terminator", "external"),
], 80, y, gap=42)
s.route_under(ids[5], ids[4], label="no - fix & re-sync", drop=70)
s.label("dogfood: reqmap runs the gate on its own requirements/", 600, y + 128, size=12)

# ═══════════════════════════ 3 · INTEGRATION ══════════════════════════════
y = s.section("3 - INTEGRATION   how it is invoked, gated and shipped")
dev    = s.c4("Developer / AI agent", 80, y, kind="Person",
              desc="authors specs, runs gate", person=True, fill="person", w=200, h=86)
claude = s.c4("Claude Code", 340, y, kind="Software System",
              desc="hosts the skill", fill="external", w=200, h=86)
plugin = s.c4("requirement-manager", 600, y, kind="Software System",
              desc="the skill + engine", fill="skill", w=210, h=86)
target = s.c4("target repo", 880, y, kind="Software System",
              desc="seeded reqmap.py", fill="external", w=190, h=86)
gitci  = s.c4("git + CI", 600, y + 140, kind="Software System", tech="action @v1",
              desc="runs the gate", fill="external", w=236, h=80)
market = s.c4("Plugin marketplace", 880, y + 140, kind="Software System",
              desc="distributes it", fill="external", w=190, h=80)
s.arrow(dev, claude, label="uses")
s.arrow(claude, plugin, label="invokes [skill]")
s.arrow(plugin, target, label="seeds reqmap.py")
s.arrow(gitci, plugin, label="gates")
s.arrow(market, plugin, label="distributes")

# ═══════════════════════════ 4 · REQUIREMENT MODEL ════════════════════════
y = s.section("4 - REQUIREMENT MODEL   layers, code tags, drift lock")
need = s.c4("need", 80, y, kind="Layer", desc="NEED-* stakeholder need",
            fill="ssot", w=240, h=80)
feat = s.c4("feature", 360, y, kind="Layer", desc="gate/sync/map/draft/...",
            fill="skill", w=240, h=80)
bus  = s.c4("bus", 640, y, kind="Layer", desc="config/parse/scan/drift",
            fill="engine", w=240, h=80)
s.arrow(need, feat, label="satisfied-by")
s.arrow(feat, bus, label="depends-on")
code = s.box("tagged source code\n# implements: / # tested-by:",
             960, y - 20, w=240, h=72, fill="external", font_size=12)
spec = s.box("a requirement spec\n*.md", 960, y + 92, w=240, h=72, fill="ssot",
             font_size=12)
lock = s.box("_reqlock.json\ndrift baseline", 1250, y + 36, w=190, h=80,
             fill="artifact", font_size=12)
s.arrow(code, spec, label="tags link to")
s.arrow(spec, lock, label="content-hash")

# ═══════════════════════════ legend + glossary ════════════════════════════
_, _, max_x, max_y = s.bounds()
ly = max_y + 50
s.legend([
    ("engine — reqmap.py", "violet"),
    ("map viewer / app", "pink"),
    ("skill / the plugin", "blue"),
    ("requirement spec (SSOT)", "indigo"),
    ("generated artifact", "green"),
    ("external system", "grey"),
    ("person (actor)", "teal"),
    ("gate / decision", "orange"),
], 80, ly, title="Legend — colour = role")

s.glossary([
    ("SSOT", "single source of truth — requirements/*.md"),
    ("drift", "content hash of a spec vs _reqlock.json baseline"),
    ("gate", "pre-commit link-sync + drift + test-link check"),
    ("dogfood", "the repo runs reqmap on its own requirements/"),
    ("@v1", "git tag of the published GitHub Action"),
    ("layer", "bus (foundation) / feature (composes bus) / need (stakeholder)"),
    ("vendored", "prebuilt viewer shipped in-repo, no Node at runtime"),
], 620, ly, title="Glossary")

out_dir = sys.argv[1] if len(sys.argv) > 1 else "docs"
s.save("full_architecture", out_dir=out_dir, crossing_check="error",
       legend_check="error", overflow_check="error", text_overlap_check="error")
print("wrote full_architecture.excalidraw + .html")
