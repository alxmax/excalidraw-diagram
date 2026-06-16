#!/usr/bin/env python3
"""requirement-manager — Complete Architecture poster (single .excalidraw + .html).

Four stacked sections, top -> bottom (modeled on a complete-architecture poster):
  1. STRUCTURE       — the plugin's containers (C4 container view)
  2. WORKFLOW        — the reqmap command pipeline, left->right run order
  3. INTEGRATION     — how it is invoked, gated and shipped
  4. REQUIREMENT MODEL — layers, code tags, and the drift lock

Uses the builder's poster helpers: s.section() auto-stacks each region, and
s.pipeline() lays out + chains the workflow band. Colour = role (single legend);
a glossary decodes the jargon. The workflow band uses the ISO 5807 shapes
(terminator / process / decision).

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
skills = s.box("Skills\n3x SKILL.md", 80, y, w=220, h=92,
               fill="skill", font_size=13)
engine = s.box("reqmap.py\nparse-scan-gate-map", 340, y, w=240, h=92,
               fill="engine", font_size=13)
specs  = s.box("Requirement specs\n29 specs - the SSOT", 620, y, w=230, h=92,
               fill="ssot", font_size=13)
arts   = s.box("Generated artifacts\n_map.*, _reqlock", 890, y, w=230, h=92,
               fill="artifact", font_size=13)
viewer = s.box("Map viewer\nReact - _map.html", 1160, y, w=210, h=92,
               fill="viewer", font_size=13)
s.enclose([skills, engine, specs, arts, viewer],
          label="requirement-manager plugin")
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
dev    = s.box("Developer / AI agent\nauthors specs, runs gate", 80, y,
               w=200, h=86, fill="person", font_size=13)
claude = s.box("Claude Code\nhosts the skill", 340, y,
               w=200, h=86, fill="external", font_size=13)
plugin = s.box("requirement-manager\nthe skill + engine", 600, y,
               w=210, h=86, fill="skill", font_size=13)
target = s.box("target repo\nseeded reqmap.py", 880, y,
               w=190, h=86, fill="external", font_size=13)
gitci  = s.box("git + CI\naction @v1 - runs the gate", 600, y + 140,
               w=236, h=80, fill="external", font_size=13)
market = s.box("Plugin marketplace\ndistributes it", 880, y + 140,
               w=190, h=80, fill="external", font_size=13)
s.arrow(dev, claude, label="uses")
s.arrow(claude, plugin, label="invokes [skill]")
s.arrow(plugin, target, label="seeds reqmap.py")
s.arrow(gitci, plugin, label="gates")
s.arrow(market, plugin, label="distributes")

# ═══════════════════════════ 4 · REQUIREMENT MODEL ════════════════════════
y = s.section("4 - REQUIREMENT MODEL   layers, code tags, drift lock")
need = s.box("need\nNEED-* stakeholder need", 80, y,
             fill="ssot", w=240, h=80, font_size=13)
feat = s.box("feature\ngate/sync/map/draft/...", 360, y,
             fill="skill", w=240, h=80, font_size=13)
bus  = s.box("bus\nconfig/parse/scan/drift", 640, y,
             fill="engine", w=240, h=80, font_size=13)
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
