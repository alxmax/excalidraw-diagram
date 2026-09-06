# excalidraw-diagram

A Claude Code skill that turns a description of a system, flow or architecture into an
**editable Excalidraw scene** plus a **self-contained HTML viewer** — no npm, no service,
no API key. The builder is one stdlib-only Python file.

You describe the thing; the skill writes `<name>.excalidraw` (imports into excalidraw.com,
every element still hand-editable) and `<name>.html` (opens by double-click).

## Install

```
/plugin marketplace add alxmax/excalidraw-diagram
/plugin install excalidraw-diagram
```

Then just ask — "draw the architecture", "make a flowchart of this pipeline", "schemă
excalidraw" — and the skill triggers on its own.

## Why a builder rather than an LLM writing JSON

Excalidraw's format is picky in ways that are easy to get wrong and hard to see: bound
arrows need reciprocal ids on both shapes, `seed` and `versionNonce` drive the hand-drawn
look, and a scene with overlapping boxes renders as a mess rather than an error.

So the model does not author JSON. It calls a builder that owns those invariants, and the
builder **checks its own output**:

```
$ python plugin/skills/excalidraw-diagram/scripts/excalidraw_builder.py
wrote /tmp/excd/smoke.excalidraw /tmp/excd/smoke.html
overlaps: [] crossings: []
OK smoke test (legend/role/align/distribute/path-bg/crossing-gate)
```

That smoke run renders every shape, runs the auto-layout and asserts nothing overlaps and
no connector crosses another. It exits non-zero on a layout regression — which is the
failure a unit test does not catch, because the JSON is still perfectly valid when the
diagram is unreadable.

## What is in here

```
plugin/skills/excalidraw-diagram/
  SKILL.md                  the authoritative contract (Claude Code)
  SKILL.universal.md        the same, for any assistant
  scripts/excalidraw_builder.py   the builder — stdlib only, no dependencies
  scripts/test_excalidraw.py      60 unit tests
  references/excalidraw_format.md the file-format notes the builder encodes
  examples/make_*.py        four worked generators, each runnable on its own
scripts/check_versions.py   plugin.json and marketplace.json must agree
```

## The examples are the documentation

Each generator under `examples/` runs standalone and writes into a directory you name:

```
python plugin/skills/excalidraw-diagram/examples/make_iso5807_flowchart.py out/
```

They are exercised in CI, so a generator that stops working is a build failure rather than
a stale snippet. Read one before writing your own — they are shorter than the format notes.

## Requirements

Python **3.9+**, standard library only. That floor is the oldest version CI runs, not the
oldest the code happens to work on: a floor nothing tests is a claim, not a guarantee.

## Provenance

This skill was developed inside
[requirement-manager](https://github.com/alxmax/requirement-manager) and split out once it
was clear it shared no code with the engine there — only a repository. Its history came
across with it, so `git log` still reaches the original commits.

## Licence

MIT — see [LICENSE](LICENSE). Use it, change it, ship it.

Note this is looser than [requirement-manager](https://github.com/alxmax/requirement-manager),
where this code lived until the split: that repo is BUSL-1.1. The skill was relicensed on
the way out, deliberately — a diagram builder is more useful to more people unencumbered.
