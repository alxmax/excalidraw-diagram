# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

One Claude Code plugin, `excalidraw-diagram`, shipping one skill of the same name. The
skill turns a description of a system, flow or architecture into an `.excalidraw` scene
plus a self-contained HTML viewer.

**Stdlib only, no dependencies.** `plugin/skills/excalidraw-diagram/scripts/excalidraw_builder.py`
is the whole builder. Nothing here installs from PyPI or npm; if a change would need a
dependency, that is a design question, not an implementation detail.

## Commands

```bash
# the builder's own smoke run — renders every shape, runs the auto-layout, and asserts
# nothing overlaps and no connector crosses another. Exits non-zero on a layout
# regression, which is the failure a unit test does NOT catch: the JSON stays perfectly
# valid while the diagram becomes unreadable.
cd plugin/skills/excalidraw-diagram/scripts && python -X utf8 excalidraw_builder.py

cd plugin/skills/excalidraw-diagram/scripts && python -X utf8 -m unittest test_excalidraw -v
cd plugin/skills/excalidraw-diagram/scripts && python -X utf8 -m unittest test_excalidraw.ClassName.test_name -v

# every worked example must still run; each takes an output directory
python -X utf8 plugin/skills/excalidraw-diagram/examples/make_iso5807_flowchart.py out/

python scripts/check_versions.py          # plugin.json == marketplace.json (x2); --fix syncs
```

**On Windows always pass `-X utf8`** — the suites print non-ASCII and fail on cp1252.

## Versioning

`plugin/.claude-plugin/plugin.json` is the source of truth. `.claude-plugin/marketplace.json`
repeats the version **twice** — top level and inside `plugins[]` — and an installed copy
reads the marketplace entry, so a bump that misses either place ships a release nobody
receives. Nothing errors; the plugin simply never updates. `scripts/check_versions.py`
enforces the three-way match and CI runs it.

**Any shipped change bumps the semver**, a skill edit included: an edit with no bump is
invisible to consumers running `/plugin update`. A bump needs a matching `` `vX.Y.Z` ``
heading in `CHANGELOG.md` — CI fails the PR without one (the backticked form is what the
grep matches).

## Requirements

This repo keeps its own requirement corpus and vendors the engine that checks it, so the
skill's contracts travelled with the skill rather than being left behind.

```bash
cd plugin && python -X utf8 scripts/reqmap.py gate --code ..    # THE verdict
cd plugin && python -X utf8 scripts/reqmap.py sync --code ..    # rebuild lock + map
cd plugin && python -X utf8 scripts/reqmap.py gate --audit --code ..
```

**`--code ..` is not optional for those two.** The committed `_reqlock.json` and `_map.*`
are generated from the widened scan; a run without it reports every member's path one
level off and fails the freshness check against the real committed files.

`plugin/scripts/reqmap.py` is **vendored, not owned**. It carries the `implements:`
self-tags of the repository it was written in, and those requirements do not live here —
`.reqmapignore` excludes it for exactly that reason, which is the posture the engine seeds
for any consumer. Do not edit it here; update it from upstream.

Nine requirements: `SYS-DIAGRAM-001` (the need), three `ARCH-EXCALIDRAW-*` capabilities and
their five `REQ-*` children. `SYS-DIAGRAM-001` was **authored by a human** on the split —
the ARCH nodes previously satisfied `SYS-VISUAL-106` in requirement-manager, whose scope
was seeing the requirement graph, which is a different need from this one.

## Layout

```
plugin/.claude-plugin/plugin.json          the manifest
plugin/skills/excalidraw-diagram/
  SKILL.md                                 the authoritative contract (Claude Code)
  SKILL.universal.md                       the same for any assistant — keep the two in step
  scripts/excalidraw_builder.py            the builder
  scripts/test_excalidraw.py               65 unit tests
  references/excalidraw_format.md          the format notes the builder encodes
  examples/make_*.py                       worked generators, each runnable standalone
.claude-plugin/marketplace.json            the marketplace manifest
scripts/check_versions.py                  version coherence
```

**`SKILL.md` and `SKILL.universal.md` are two hand-maintained copies of one contract.**
Nothing generates either from the other, so a change to one that misses the other is a
silent divergence. Edit both.

**Generated diagrams are never committed.** `.gitignore` blocks `*.excalidraw`, `out/` and
`diagrams/`. Run a generator with an output directory you choose; the outputs are
regenerable by definition and reviewing them in a diff is not useful.

## Why the builder rather than model-authored JSON

Excalidraw's format has invariants that are easy to break and hard to see: bound arrows
need reciprocal ids on both shapes, `seed`/`versionNonce` drive the hand-drawn look, and
overlapping boxes render as a mess rather than an error. The builder owns those invariants
and checks its own output, so the model describes a diagram instead of emitting JSON.

## Python floor

**3.9**, and it is the oldest version CI runs rather than the oldest the code happens to
work on — a floor nothing tests is a claim, not a guarantee. Raising it means moving the
CI matrix and this line together.

## Provenance

Developed inside [requirement-manager](https://github.com/alxmax/requirement-manager) and
split out at plugin `v6.0.0` once it was clear the two shared a repository and nothing
else — no imports in either direction. History came across via `git subtree split`, so
`git log` and `git blame` still reach the original commits.
