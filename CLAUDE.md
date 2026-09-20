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
is the builder's import name and CLI; the code is the `excalidraw_engine/` package beside it,
one module per responsibility (its `__init__` has the map). `mcp_server.py` beside both
offers the same entry points as MCP tools. Nothing here installs from PyPI or npm; if a
change would need a dependency, that is a design question, not an implementation detail.

## Out of scope: animated timing, log timelines, log parsers

An animated timing view (time cursor, per-signal value, event narration), a log timeline
and log parsers (CSV, VCD, CANoe `.asc` + DBC, AUTOSAR DLT) are **deferred, and none of
them belongs in this plugin**. Senate `2026-09-20_225217-senate-excalidraw-timing-scope`
landed 9-0 on keeping the prototype local and building nothing; it overturned the
proposal's own recommendation. Two measurements decided it: demand is n=0 (no filed
request has ever existed for any of the three), and the narration those items sell is
already shipped — `examples/make_timing_diagrams.py` narrates its diagram with `s.label(...)`
captions under `ARCH-EXCALIDRAW-033`. The earlier
`2026-09-18_222241-excalidraw-wavedrom-waveform-scope` reached the same place and is
discharged by `9882c9c`, which drew timing diagrams with the existing `Scene` API.

**The reopening gate.** Reopen only when all three hold: at least two filed requests from
non-author accounts naming the animated timing view or the log timeline, the vendored
offline viewer runtime landed, and the open v2.2 research item closed.

**If it ever reopens, the home is a standalone repo** — not a second `plugins[]` entry,
not a second directory under `plugin/skills/`. The viewer here emits one `.excalidraw`
plus one `.html` from a single `save()`; an animated player is a second renderer that
emits no scene, and that is the contract it would break.

**What is worth keeping from the prototype**, which lives untracked at
`out/previews/animated_timing.html` and has no generator: the *narration* idea, and its
data shape — a `DIAGRAMS` array of rows (`kind` `"d"`/`"a"`, per-signal `min`/`max`/`fmt`)
plus `events[{t, text}]` captions keyed to a time index. That is the reconstructable part;
the 116 lines of hand-written HTML are output, not implementation.

**Preconditions on any future parser**, recorded now so they are not rediscovered later:
truncated, unmapped or DBC-mismatched input must raise an error naming the file, the byte
offset and the signal, and write no HTML — the seven gates judge layout, not semantics, so
a mis-decoded trace renders as a confident, well-formed, wrong diagram. An unbound trace
(`path(heads="none")`) is invisible to three of the seven gates, which is why the timing
generators assert their own geometry. Signal names derived from a DBC must never be
embedded in a page meant to be forwarded.

## Commands

```bash
# a diagram from a coordinate-free description: pack() places it, the gates judge it
python -X utf8 plugin/skills/excalidraw-diagram/scripts/excalidraw_builder.py scene --from-json graph.json -o out/

# the builder's own smoke run — renders every shape, runs the auto-layout, and asserts
# nothing overlaps and no connector crosses another. Exits non-zero on a layout
# regression, which is the failure a unit test does NOT catch: the JSON stays perfectly
# valid while the diagram becomes unreadable.
cd plugin/skills/excalidraw-diagram/scripts && python -X utf8 excalidraw_builder.py

cd plugin/skills/excalidraw-diagram/scripts && python -X utf8 -m unittest test_excalidraw test_mcp_server -v
cd plugin/skills/excalidraw-diagram/scripts && python -X utf8 -m unittest test_excalidraw.ClassName.test_name -v

# every worked example must still run; each takes an output directory
python -X utf8 plugin/skills/excalidraw-diagram/examples/make_iso5807_flowchart.py out/

python scripts/check_versions.py          # plugin.json == marketplace.json (x2); --fix syncs
cd scripts && python -X utf8 -m unittest test_check_versions -v   # and that the check itself catches a stale copy
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

This repo keeps its own requirement corpus in `requirements/` and vendors the engine
that checks it. Both sit at the repo root, so every command runs from there with no
path arguments — the scan already covers every member.

```bash
python -X utf8 scripts/reqmap.py gate                        # THE verdict
python -X utf8 scripts/reqmap.py sync                        # rebuild lock + map
python -X utf8 scripts/reqmap.py sync --accept-drift "why"   # after editing a confirmed contract
python -X utf8 scripts/reqmap.py gate --audit
```

The corpus lived under `plugin/` until it moved out: it was being shipped to everyone
who installed the plugin, and it forced every command to carry `--code ..` to widen the
scan back to the repo it was describing. Neither is true now.

`scripts/reqmap.py` is **vendored, not owned**. It carries the `implements:`
self-tags of the repository it was written in, and those requirements do not live here —
`.reqmapignore` excludes it for exactly that reason. Do not edit it here; update it from
the installed plugin (the `update-engine` action does the copy). `.reqmapignore` also excludes `examples/`: a generator demonstrates the builder
rather than implementing a capability, so tagging one claims a requirement it does not carry.

**Eighteen requirements:** `SYS-DIAGRAM-001` (the need), five `ARCH-EXCALIDRAW-*`
capabilities with their eleven `REQ-*` children, and `ARCH-RELEASE-035` (the version
match). The count is what `reqmap.py gate` prints, not a number to carry by hand. All are `confirmed`, so the gate enforces them as truth. Editing a confirmed
contract demotes it to `draft` — set `status: confirmed` back and
`sync --accept-drift "<why>"`.

**`init` over-drafts in this repo, and that is expected.** It proposes a requirement
per untagged file, so it invents nodes from directory names (`ARCH-DOCS-001`) and
drafts the reference prose that `ARCH-EXCALIDRAW-030/031/034` already own. It says so
itself in the files it writes. `.reqmapignore` now covers the recurring cases —
`docs/make_*.py`, `SKILL.universal.md`, `references/**`, `.github/**` — so a re-run
stays quiet; a new draft it does propose is worth reading before deleting.

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
plugin/.mcp.json                           registers the MCP server on install
plugin/skills/excalidraw-diagram/
  SKILL.md                                 the authoritative contract (Claude Code)
  SKILL.universal.md                       the same for any assistant — keep the two in step
  references/builder_api.md                every call, imports, the graph.json schema
  references/worked_examples.md            the repo-poster recipe and the ❌ → ✅ variants
  references/excalidraw_format.md          the format notes the builder encodes
  scripts/excalidraw_builder.py            the import name + CLI (a facade)
  scripts/excalidraw_engine/               the builder: style, geometry, canvas, shapes,
                                           connectors, arrange, annotate, pack, checks,
                                           gates, scene, viewer, discover, spec, cli
  scripts/mcp_server.py                    the MCP server (stdio JSON-RPC)
  scripts/test_excalidraw.py               the builder's tests, every example included
  scripts/test_mcp_server.py               the MCP server's tests
  examples/make_*.py                       worked generators, each runnable standalone
.claude-plugin/marketplace.json            the marketplace manifest
requirements/                              the corpus, its lock files and the generated map
scripts/reqmap.py                          the vendored requirement engine
scripts/check_versions.py + its test       version coherence
```

**Only `plugin/` ships.** `/plugin install` hands a consumer the manifest and the skill;
the corpus, the engine and the release check are this repo's own scaffolding and stay
outside it.

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
