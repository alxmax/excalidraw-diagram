# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

One Claude Code plugin, `excalidraw-diagram`, shipping one skill of the same name. The
skill turns a description of a system, flow or architecture into an `.excalidraw` scene
plus a self-contained HTML viewer. Its most common use is explanatory: someone who does
not understand a system asks for a picture of it, so the output must decode itself
(title, reading direction, legend, glossary). `examples/make_explainer.py` is the
reference for that shape and `ARCH-EXCALIDRAW-033` is the requirement that holds it.

**Stdlib only, no dependencies.** `plugin/skills/excalidraw-diagram/scripts/excalidraw_builder.py`
is the whole builder. Nothing here installs from PyPI or npm; if a change would need a
dependency, that is a design question, not an implementation detail.

## Commands

```bash
# a diagram from a coordinate-free description: pack() places it, the gates judge it
python -X utf8 plugin/skills/excalidraw-diagram/scripts/excalidraw_builder.py scene --from-json graph.json -o out/

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

## How the tests are shaped

`test_excalidraw.py` has two kinds of test. `TestExampleDiagrams` is generated at import
time: it stubs `Scene.save`, runs every `examples/make_*.py` through `runpy`, and asserts
all seven inspection checks return empty. A new example is covered the moment it exists;
an example that breaks a gate fails the suite, not just CI's examples job. The other
classes are ordinary unit tests, grouped by the requirement they verify.

## Git workflow

Direct push to `main` is blocked by a global hook (`core.hooksPath` in the user's git
config). Branch (`feat/<slug>` or `fix/<slug>`), push, open a PR with `gh pr create`, let
the five CI jobs pass, merge with `gh pr merge --merge --delete-branch`. The `changelog`
job runs only on PRs, so a version bump pushed any other way is never checked.

## Versioning

`plugin/.claude-plugin/plugin.json` is the source of truth. `.claude-plugin/marketplace.json`
repeats the version **twice** — top level and inside `plugins[]` — and an installed copy
reads the marketplace entry, so a bump that misses either place ships a release nobody
receives. Nothing errors; the plugin simply never updates. `scripts/check_versions.py`
enforces the three-way match and CI runs it.

**Any shipped change bumps the semver**, a skill edit included: an edit with no bump is
invisible to consumers running `/plugin update`. A bump needs a matching `` `vX.Y.Z` ``
heading in `CHANGELOG.md` — CI fails the PR without one (the backticked form is what the
grep matches). Root-level files (`README.md`, this file, CI) are not shipped and need no bump.

## Requirements

This repo keeps its own requirement corpus under `plugin/requirements/` and vendors the
engine that checks it.

```bash
cd plugin && python -X utf8 scripts/reqmap.py gate --code ..    # THE verdict
cd plugin && python -X utf8 scripts/reqmap.py sync --code ..    # rebuild lock + map
cd plugin && python -X utf8 scripts/reqmap.py sync --accept-drift "why" --code ..   # after editing a confirmed contract
cd plugin && python -X utf8 scripts/reqmap.py gate --audit --code ..
```

**`--code ..` is not optional.** The committed `_reqlock.json` and `_map.*` are generated
from the widened scan; a run without it reports every member's path one level off and
fails the freshness check against the real committed files.

`plugin/scripts/reqmap.py` is **vendored, not owned**. It carries the `implements:`
self-tags of the repository it was written in, and those requirements do not live here —
`.reqmapignore` excludes it for exactly that reason. Do not edit it here; update it from
upstream. `.reqmapignore` also excludes `examples/`: a generator demonstrates the builder
rather than implementing a capability, so tagging one claims a requirement it does not carry.

**Fourteen requirements:** `SYS-DIAGRAM-001` (the need), five `ARCH-EXCALIDRAW-*`
capabilities and their eight `REQ-*` children. All are `confirmed`, so the gate
enforces them as truth. Editing a confirmed contract demotes it to `draft` — set
`status: confirmed` back and `sync --accept-drift "<why>"`.

**Tagging conventions the gate reads.** ARCH ids are `# implements:` lines at the top of
the builder and `# tested-by:` lines at the top of the test file. REQ ids sit on the
`def` / `class` that implements them and on the test class that covers them. Each test
method carries `# verifies: <ID>#CASE-n`; a confirmed requirement's automatable case with
no `verifies:` tag is a gate WARN. A case checked by reading rather than by a test is
marked `<!-- verifiable by: inspection -->` on its `CASE-n` line, which takes it out of
that count. Paths in a requirement's Context section are repo-relative
(`plugin/skills/...`), not plugin-relative.

**Lint rules that bite when writing a requirement:** a confirmed requirement needs at
least three cases; a `Then` with three or more `and`/`or` joins is flagged, so split it
into sentences; sentences stay under 25 words; a binding line names its subject.

## Layout

```
plugin/.claude-plugin/plugin.json          the manifest
plugin/skills/excalidraw-diagram/
  SKILL.md                                 the authoritative contract (Claude Code)
  SKILL.universal.md                       the same for any assistant — keep the two in step
  references/builder_api.md                every call, imports, the graph.json schema
  references/worked_examples.md            the repo-poster recipe and the ❌ → ✅ variants
  references/excalidraw_format.md          the format notes the builder encodes
  scripts/excalidraw_builder.py            the builder
  scripts/test_excalidraw.py               80 unit tests
  examples/make_*.py                       worked generators, each runnable standalone
plugin/requirements/                       the corpus, its lock files and the generated map
plugin/scripts/reqmap.py                   the vendored requirement engine
.claude-plugin/marketplace.json            the marketplace manifest
scripts/check_versions.py                  version coherence
```

**`SKILL.md` and `SKILL.universal.md` are two hand-maintained copies of one contract.**
Nothing generates either from the other, so a change to one that misses the other is a
silent divergence. Edit both. The universal file drops only the Claude Code-specific parts
(sub-agent fan-out, plugin-cache resolver); every rule, gate and checklist item must match.
The resolver's cache path is `excalidraw-diagram/excalidraw-diagram`, the marketplace name
then the plugin name.

**Both contracts stay in the 150-200 line band.** What earns a place in them is a
*rule*; what illustrates a rule goes to `references/`. A requirement that cites a
rule cites it **by name** — `ARCH-EXCALIDRAW-033` does — because renumbering a
list breaks a numeric citation and nothing in the gate would notice.

**Generated diagrams are never committed.** `.gitignore` blocks `*.excalidraw`, `out/` and
`diagrams/`. Run a generator with an output directory you choose; the outputs are
regenerable by definition and reviewing them in a diff is not useful. `_map.html` is
likewise generated by `sync` and gitignored.

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

The skill and its requirements were developed elsewhere and split into this repository
with their history, so `git log` and `git blame` reach commits older than the repo. That
is also why the requirement engine is vendored rather than owned.
