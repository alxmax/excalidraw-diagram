#!/usr/bin/env python3
"""Diagram: the requirement-manager plugin — whole-plugin architecture poster.

Four stacked regions (top -> bottom), the three-layer architecture audit:
  1. the plugin & its three shipped skills
  2. the reqmap.py engine internals (SSOT <-> code, reconciled)
  3. integration (invoked in Claude Code, seeded into a repo, gated in CI)
  4. distribution (semver lockstep, marketplace, action tag, sync)

Names real files/paths so it is useful to someone reading the repo.

Run from the repo root:
    python plugin/skills/excalidraw-diagram/examples/make_architecture.py docs
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from excalidraw_builder import Scene

ROLES = {
    "skill":    "blue",     # a Claude Code skill (entry point)
    "engine":   "teal",     # reqmap.py engine + builder code
    "ssot":     "indigo",   # requirement files / code tags (source of truth)
    "gate":     "orange",   # the check gate + CI checks + hooks
    "output":   "green",    # generated artifacts
    "dist":     "violet",   # packaging & distribution
    "external": "grey",     # external systems (Claude Code, git, repos)
}

s = Scene(seed=7, roles=ROLES)
GAP = 110   # vertical clearance between stacked regions

# ── Title & subtitle ──────────────────────────────────────────────────────
s.title("requirement-manager plugin — architecture", 40, -96, size=30)
s.label(
    "Four stacked regions, top -> bottom:  (1) plugin & its 3 skills   "
    "(2) reqmap.py engine   (3) integration   (4) distribution.  "
    "Colour = role (legend, right).",
    40, -54, size=14, color="grey", align="left",
)

# ═══════════════════════════════════════════════════════════════════════════
#  REGION 1 — the plugin & its three skills
# ═══════════════════════════════════════════════════════════════════════════
manifest = s.box("plugin/.claude-plugin/plugin.json\nv1.35.0",
                 360, 30, 320, 64, fill="dist", font_size=14)

sk_rm  = s.box("requirement-manager\n(SKILL.md)",          40, 190, 300, 84,
               fill="skill", font_size=14)
sk_qr  = s.box("requirement-quality-review\n(SKILL.md)",  370, 190, 300, 84,
               fill="skill", font_size=14)
sk_ex  = s.box("excalidraw-diagram\n(SKILL.md + scripts/)", 700, 190, 300, 84,
               fill="skill", font_size=14)

skills_frame = s.enclose([sk_rm, sk_qr, sk_ex], pad=26, label=None)
fx, fy, fw, fh, _ = s._geom[skills_frame]
s.label("plugin/skills/  —  three skills shipped", fx + 170, fy - 20,
        size=13, color="grey", align="center")
s.arrow(manifest, skills_frame, label="ships")

s.label("core · drives SSOT + drift (Region 2)", 190, 282, size=12, color="grey")
s.label("AI advisory · never in gate",          520, 282, size=12, color="grey")
s.label("own builder · independent",            850, 282, size=12, color="grey")

# ═══════════════════════════════════════════════════════════════════════════
#  REGION 2 — reqmap.py engine internals
# ═══════════════════════════════════════════════════════════════════════════
_, _, _, b1 = s.bounds()
R2 = b1 + GAP
s.title("Region 2 — reqmap.py engine:  requirement ⇄ code, reconciled",
        40, R2, size=22)
R2c = R2 + 56

req_md = s.box("requirements/*.md\nsingle source of truth\nbus · feature · need",
               40, R2c + 30, 270, 92, fill="ssot", font_size=13)
code   = s.box("source code\nimplements: · tested-by:\ngenerated-from: tags",
               40, R2c + 180, 270, 92, fill="ssot", font_size=13)

reqmap = s.box("reqmap.py\nengine\n~3100 lines\nstdlib only",
               400, R2c + 95, 250, 122, fill="engine", font_size=14)

s.arrow(req_md, reqmap, label="parsed")
s.arrow(code,   reqmap, label="scanned")

check = s.box("check — the gate\nlink-sync → ERROR\ndrift · test-link → WARN",
              740, R2c + 8, 300, 96, fill="gate", font_size=13)
mapc  = s.box("map — build the registry graph",
              740, R2c + 134, 300, 56, fill="engine", font_size=13)
cli   = s.box("CLI surface\ninit · scan · extract\nnext · findings · promote",
              740, R2c + 224, 300, 92, fill="engine", font_size=13)

s.arrow(reqmap, check, label="commit / CI")
s.arrow(reqmap, mapc,  label="generates")
s.arrow(reqmap, cli)

o1 = s.box("_map.md (4 Mermaid)",            1140, R2c + 6,   240, 52,
           fill="output", font_size=13)
o2 = s.box("_map.json (graph)",             1140, R2c + 80,  240, 52,
           fill="output", font_size=13)
o3 = s.box("_map.html (viewer)",            1140, R2c + 154, 240, 52,
           fill="output", font_size=13)
o4 = s.box("_reqlock.json\n_findings.md",   1140, R2c + 228, 240, 64,
           fill="output", font_size=13)
out_frame = s.enclose([o1, o2, o3, o4], pad=20,
                      label="generated artifacts (committed)")
s.arrow(mapc, out_frame, label="writes _map.*")
s.label("_reqlock ← check · _findings ← findings",
        1260, R2c + 312, size=11, color="grey", align="center")

# ═══════════════════════════════════════════════════════════════════════════
#  REGION 3 — integration
# ═══════════════════════════════════════════════════════════════════════════
_, _, _, b2 = s.bounds()
R3 = b2 + GAP
s.title("Region 3 — integration:  invoked in Claude Code, seeded into a repo, "
        "gated in CI", 40, R3, size=22)
R3c = R3 + 56

cc   = s.box("Claude Code\nskill system\n/requirement-manager:…",
             40, R3c + 36, 220, 88, fill="external", font_size=13)
repo = s.box("target repo\nscripts/reqmap.py +\n.reqmapignore (committed)",
             320, R3c + 36, 260, 88, fill="external", font_size=13)
hook = s.box("plugin/hooks/pre-commit\n→ reqmap.py check",
             650, R3c - 6, 270, 66, fill="gate", font_size=13)
ci   = s.box("GitHub Actions CI\ncheck_versions → check →\n"
             "map --check → test_reqmap",
             650, R3c + 96, 270, 92, fill="gate", font_size=13)
act  = s.box("check/action.yml\npublished as\nalxmax/…/check@v1",
             1000, R3c + 96, 250, 92, fill="dist", font_size=13)

s.arrow(cc,   repo, label="seeds engine")
s.arrow(repo, hook, label="wires")
s.arrow(repo, ci,   label="wires")
s.arrow(ci,   act,  label="uses:")

# viewer build chain (second left->right band, below)
R3v = R3c + 250
s.label("Viewer build chain  (app/  ->  vendored template  ->  per-repo HTML)",
        40, R3v - 26, size=12, color="grey", align="left")
app  = s.box("app/  —  Vite + React\nviewer (src/App.jsx)",
             40, R3v, 240, 80, fill="engine", font_size=13)
vtpl = s.box("_map_viewer.html\nvendored single-file\ntemplate",
             360, R3v, 260, 80, fill="output", font_size=13)
vhtml = s.box("_map.html\nrepo data inlined\n(double-click)",
              720, R3v, 240, 80, fill="output", font_size=13)
s.arrow(app,  vtpl,  label="npm run build:viewer")
s.arrow(vtpl, vhtml, label="engine injects _map.json")

# ═══════════════════════════════════════════════════════════════════════════
#  REGION 4 — distribution
# ═══════════════════════════════════════════════════════════════════════════
_, _, _, b3 = s.bounds()
R4 = b3 + GAP
s.title("Region 4 — distribution:  semver lockstep, marketplace, action tag, "
        "sync", 40, R4, size=22)
R4c = R4 + 56

pj  = s.box("plugin.json\nversion 1.35.0",
            40, R4c + 30, 240, 70, fill="dist", font_size=13)
mp  = s.box(".claude-plugin/\nmarketplace.json\n(version ×2)",
            40, R4c + 140, 240, 84, fill="dist", font_size=13)
cv  = s.box("scripts/check_versions.py\nsemver lockstep gate\n(3 places must match)",
            360, R4c + 78, 280, 92, fill="gate", font_size=13)
upd = s.box("/plugin update\nconsumers pull",
            720, R4c + 30, 240, 70, fill="external", font_size=13)
syn = s.box("sync_reqmap.sh\npropagate engine to\nconsumer repos",
            720, R4c + 145, 260, 84, fill="dist", font_size=13)

s.arrow(pj, cv, label="validated by")
s.arrow(mp, cv, label="validated by")
s.arrow(cv, upd, label="release")
s.arrow(cv, syn, label="propagate")

# ═══════════════════════════════════════════════════════════════════════════
#  LEGEND + GLOSSARY  (right margin, outside the regions)
# ═══════════════════════════════════════════════════════════════════════════
s.legend(
    [("Claude Code skill",            "skill"),
     ("reqmap.py / builder engine",   "engine"),
     ("source of truth (req + tags)", "ssot"),
     ("gate / CI check",              "gate"),
     ("generated artifact",           "output"),
     ("packaging / distribution",     "dist"),
     ("external system",              "external")],
    1480, R2, title="What the colours mean",
)
s.glossary(
    [("SSOT",        "single source of truth — one .md per capability"),
     ("drift",       "confirmed contract changed; code not re-touched"),
     ("bus/feature", "requirement layers: base · composed · need"),
     ("the gate",    "reqmap.py check — link errors block a commit"),
     ("semver lock", "plugin.json + marketplace (×2) must match"),
     ("@v1",         "the GitHub Action's own release tag"),
     ("dogfood",     "the repo manages its own requirements")],
    1480, R2 + 320, title="Terms",
)

# ── Save ──────────────────────────────────────────────────────────────────
out_dir = sys.argv[1] if len(sys.argv) > 1 else "docs"
pj_path, ph_path = s.save(
    "plugin_architecture", out_dir=out_dir,
    crossing_check="error", legend_check="error",
)
print("elements:", len(s.elements))
print("overlaps:", s.check_overlaps())
print("crossings:", s.check_arrow_crossings())
print("legend coverage gaps:", s.check_legend_coverage())
print("wrote:", pj_path, ph_path)
