#!/usr/bin/env python3
"""requirement-manager — entire-repo file map (every top-level area + real files).

The filesystem lens (complements make_full_architecture.py, which is the
conceptual/architecture lens). One stacked section per top-level area, using the
builder's s.section() auto-stacking; boxes are the real files/dirs, coloured by
role. Cross-subsystem flows are summarised in the "Key data flows" panel rather
than drawn as long cross-region arrows.

Run from the repo root, writing into the regenerable diagrams/ dir:
    python plugin/skills/excalidraw-diagram/examples/make_repo_map.py diagrams
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from excalidraw_builder import Scene

s = Scene(seed=11, roles={
    "doc":       "grey",     # prose / markdown / html docs
    "packaging": "orange",   # manifests, version gate, CI, hooks
    "engine":    "violet",   # reqmap.py — the single stdlib engine
    "test":      "red",      # test files
    "ssot":      "indigo",   # requirements/*.md — single source of truth
    "artifact":  "green",    # generated outputs
    "skill":     "blue",     # SKILL.md skill contracts
    "app":       "teal",     # app/ React viewer source + build
    "tool":      "pink",     # excalidraw builder + generators
})

s.title("requirement-manager — entire-repo file map", 40, -78, size=30)
s.label("Filesystem lens: one section per top-level area, boxes are the real "
        "files. Cross-subsystem flows are in the panel at the bottom.",
        40, -40, size=14, align="left")

# ============================================================= (1) repo root
y = s.section("(1) repo root — docs - packaging - CI")
root_docs = s.grid([
    ("README.md", "doc"), ("CHANGELOG.md", "doc"),
    ("TODO.md", "doc"),   ("CLAUDE.md", "doc"),
    ("LICENSE", "doc"),   ("sync_reqmap.sh", "doc"),
], 40, y, 2, w=160, h=46, gap_x=30, gap_y=24)
s.enclose(root_docs, label="root docs")
pkg = s.grid([
    (".claude-plugin/\nmarketplace.json", "packaging"),
    ("scripts/check_versions.py", "packaging"),
    (".github/workflows/ci.yml", "packaging"),
    (".githooks/pre-commit", "packaging"),
], 480, y, 2, w=220, h=46, gap_x=30, gap_y=24)
s.enclose(pkg, label="packaging & CI")

# ============================================================= (2) engine
y = s.section("(2) plugin/scripts - engine, tests, vendored viewer")
b_manifest = s.box("plugin/.claude-plugin/\nplugin.json", 40, y, w=190, h=60, fill="packaging")
b_test_eng = s.box("test_reqmap.py", 270, y, w=180, h=60, fill="test")
b_engine   = s.box("reqmap.py\n~3200 lines\nstdlib only", 500, y, w=190, h=84, fill="engine")
b_viewer   = s.box("_map_viewer.html\n(vendored React build)", 750, y, w=210, h=60, fill="artifact")
s.arrow(b_test_eng, b_engine, label="tests")
s.arrow(b_engine, b_viewer, label="inject _map.json")
s.enclose([b_manifest, b_test_eng, b_engine, b_viewer])

# ============================================================= (3) requirements
y = s.section("(3) plugin/requirements - SSOT specs + generated artifacts")
b_req = s.box("requirements/*.md\n29 specs:\nCORE-* / REQ-* / NEED-*", 40, y, w=250, h=80, fill="ssot")
arts = s.grid([
    ("_map.json", "artifact"), ("_map.md", "artifact"), ("_map.html", "artifact"),
    ("_reqlock.json", "artifact"), ("_findings.md", "artifact"),
], 420, y, 3, w=160, h=54, gap_x=30, gap_y=24)
s.enclose(arts, label="generated (committed; _map.html regenerable)")

# ============================================================= (4) skills
y = s.section("(4) plugin/skills - three shipped skills")
sk_core = s.box("requirement-manager/\nSKILL.md", 40, y, w=240, h=56, fill="skill")
sk_adv  = s.box("requirement-quality-review/\nSKILL.md", 40, y + 86, w=280, h=56, fill="skill")
s.enclose([sk_core, sk_adv], label="core + advisory")
exc = s.grid([
    ("excalidraw-diagram/\nSKILL.md", "skill"),
    ("scripts/\nexcalidraw_builder.py", "tool"),
    ("scripts/\ntest_excalidraw.py", "test"),
    ("examples/\n(3 generators)", "tool"),
    ("references/\nexcalidraw_format.md", "doc"),
], 400, y, 3, w=190, h=56, gap_x=30, gap_y=26)
s.enclose(exc, label="skills/excalidraw-diagram/ (independent — own builder)")

# ============================================================= (5) app
y = s.section("(5) app/ - Vite + React viewer (built into the vendored viewer)")
src = s.grid([
    ("src/App.jsx", "app"), ("src/main.jsx", "app"),
    ("src/lib/\n(data, layout,\nloadData, ui, icons)", "app"),
    ("src/views/\n(Map, Problems,\nRoadmap, Spec)", "app"),
    ("src/styles/", "app"),
], 40, y, 3, w=180, h=66, gap_x=30, gap_y=24)
s.enclose(src, label="app/src/")
build = s.grid([
    ("vite.config.js", "app"), ("vite.viewer.config.js", "app"),
    ("package.json", "app"), ("dist-viewer/", "artifact"),
    ("public/data.json", "artifact"),
], 760, y, 2, w=210, h=66, gap_x=30, gap_y=24)
s.enclose(build, label="build config + output")

# ============================================================= (6) action + site
y = s.section("(6) check/ - GitHub Action   +   docs/ & diagrams/ - output")
s.row([
    ("check/action.yml", "packaging"),
    ("docs/architecture.html", "doc"),
    ("docs/index.html", "doc"),
    ("docs/map.html", "doc"),
    ("diagrams/\n(excalidraw out)", "artifact"),
], 40, y, gap=40, w=180, h=58)

# ============================================================= legend / glossary / flows
_, _, max_x, max_y = s.bounds()
ly = max_y + 50
s.legend([
    ("doc — markdown / html prose", "grey"),
    ("packaging — manifest / version gate / CI / hooks", "orange"),
    ("engine — reqmap.py", "violet"),
    ("test", "red"),
    ("ssot — requirements/*.md", "indigo"),
    ("generated artifact", "green"),
    ("skill — SKILL.md contract", "blue"),
    ("app — React viewer source", "teal"),
    ("tool — excalidraw builder / generators", "pink"),
], 40, ly, title="Legend — colour = role")

s.glossary([
    ("SSOT", "single source of truth — requirements/*.md"),
    ("drift", "content hash of a spec vs _reqlock.json baseline"),
    ("gate", "pre-commit link-sync + drift + test-link check"),
    ("vendored", "prebuilt viewer shipped in-repo, no Node at runtime"),
    ("@v1", "git tag of the published GitHub Action"),
    ("dogfood", "the repo describes its own engine in requirements/"),
], 560, ly, title="Glossary")

s.glossary([
    ("engine I/O", "reqmap.py reads requirements/*.md + scans tagged code -> writes _map.* / _reqlock / _findings"),
    ("viewer", "app/ -> npm build:viewer -> vendored _map_viewer.html; engine injects _map.json -> _map.html"),
    ("seeding", "the requirement-manager skill copies reqmap.py into a target repo"),
    ("CI", "ci.yml runs check_versions -> reqmap gate -> map --check -> test_reqmap.py"),
    ("versioning", "check_versions.py keeps plugin.json == marketplace.json semver"),
], 1130, ly, title="Key data flows")

out_dir = sys.argv[1] if len(sys.argv) > 1 else "docs"
s.save("repo_map", out_dir=out_dir, crossing_check="warn", legend_check="error")
print("wrote repo_map.excalidraw + .html")
