---
id: REQ-EXCALIDRAW-849
status: confirmed
level: code
layer: feature
owner: Alex
satisfies: [ARCH-EXCALIDRAW-033]
---

# Colour and term keys: legend() and glossary()

## Description
> A colour on a diagram means something only to the person who chose it, and a
> project term means something only to someone already inside the project. The
> two keys put that meaning on the canvas: `legend()` maps each fill colour to a
> role, `glossary()` maps each term to a one-line meaning. Both are drawn as
> real content, so nothing can be placed on top of them unnoticed.

Every bullet below is binding.
- `legend(entries=None, x, y, title="Legend")` draws a colour key with one row
  per entry, each row a swatch of the colour beside its label. An entry is a
  `(label, colour)` pair; `colour` is a palette name, a hex string or a role
  name declared with `Scene(roles=...)` / `role()`.
- `legend()` with no `entries` uses the Scene's declared roles as the key.
  With no entries and no roles it raises `ValueError`, because an empty key
  explains nothing.
- `legend()` records the resolved colour of every entry it draws, so
  `check_legend_coverage()` can report a fill the key leaves undecoded.
- `glossary(entries, x, y, title="Glossary")` draws a term key with one
  left-aligned line per `(term, meaning)` pair, rendered as `TERM — meaning`.
  An empty `entries` list raises `ValueError`.
- The glossary box counts as content for `check_overlaps()`: a shape placed
  over it is reported as an overlap.

## Cases
CASE-1 — a legend built from declared roles
  Given  `Scene(roles={"agent": "violet"})` and no explicit entries
  When   `legend()` is called
  Then   the scene gains a key with one row labelled "agent", and the resolved
         colour of "violet" is recorded for legend coverage

CASE-2 — an empty legend is refused
  Given  a `Scene` with no declared roles
  When   `legend()` is called with no entries
  Then   `ValueError` is raised

CASE-3 — a glossary decodes a term on the canvas
  Given  a `Scene`
  When   `glossary([("SSOT", "single source of truth")], 0, 0)` is called
  Then   the scene contains a text element reading `SSOT — single source of truth`

CASE-4 — an empty glossary is refused
  Given  a `Scene`
  When   `glossary([], 0, 0)` is called
  Then   `ValueError` is raised

CASE-5 — the glossary box is overlap-checked
  Given  a `Scene` with a glossary drawn at (0, 0)
  When   a box is placed on top of it and `check_overlaps()` is called
  Then   the overlap is reported

## Context
**Notes**
- `glossary()` neither wraps nor colours its lines: keep each meaning to one
  short line, or the box grows past the region beside it.
- The legend frame is container-exempt; the glossary box is registered in the
  overlap set explicitly because `frame()` alone would not be.

**Current implementation**
- `Scene.legend()` and `Scene.glossary()` in
  `plugin/skills/excalidraw-diagram/scripts/excalidraw_builder.py`.
- `TestBuilderUnits` in
  `plugin/skills/excalidraw-diagram/scripts/test_excalidraw.py`.
