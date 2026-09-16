---
id: ARCH-EXCALIDRAW-031
status: confirmed
level: architecture
layer: feature
owner: Alex
milestone: v1.0.0
depends_on: [ARCH-EXCALIDRAW-030]
satisfies: [SYS-DIAGRAM-001]
---

# Excalidraw quality gates

## Description
> A diagram that ships with overlapping shapes, arrows that cut through
> unrelated boxes, unlegended colours, text that spills outside its box, an
> arrow too short to draw a visible line, or a label wider than the arrow it
> sits on is unreadable to an outsider. Hard-fail gates at `.save()` time make
> these defects impossible to ship silently.

Every bullet below is binding.
- `.save(gates=Gates(...))` runs five advisory gates (`crossing`, `legend`, `overflow`, `text_overlap`, `label_fit`), each set to `"warn"` (the default, prints to stderr), `"error"` (raises `ValueError`) or `"off"`. [[REQ-EXCALIDRAW-846]]
- `.save()` additionally enforces two hard gates that raise `ValueError` by default — overlapping shapes and arrows clamped too short to render — each switchable through the same `Gates` object for a deliberate exception. [[REQ-EXCALIDRAW-847]]

## Cases
CASE-1
  Given  a scene where a bound arrow's path passes through an unrelated box
  When   `save(gates=Gates(crossing="error"))` is called
  Then   a `ValueError` is raised; with the default `Gates()` a warning is
         printed and the files are written

CASE-2
  Given  a scene with `paint="blue"` on a box and a `legend()` that omits blue
  When   `save(gates=Gates(legend="error"))` is called
  Then   a `ValueError` is raised naming the unlegended colour

CASE-3
  Given  a box whose bound text is wider than the box width
  When   `save(gates=Gates(overflow="error"))` is called
  Then   a `ValueError` is raised; `check_text_overflow()` returns the
         offending shape

CASE-4
  Given  two `label()` elements placed at overlapping coordinates
  When   `save(gates=Gates(text_overlap="error"))` is called
  Then   a `ValueError` is raised naming the overlapping pair

CASE-5
  Given  each maintained example generator in `examples/`
  When   `test_excalidraw.py` runs it
  Then   the generator produces zero violations on every gate (the five
         advisory gates and both hard gates)

CASE-6
  Given  two boxes placed close but not overlapping, joined by a bound arrow
  When   `save()` is called with defaults
  Then   a `ValueError` is raised (the connector is too short to render);
         `save(gates=Gates(short_arrows="off"))` writes the files, and
         `check_short_arrows()` returns the offending pair

CASE-7
  Given  a bound arrow whose label is wider than the arrow's visible line
  When   `save(gates=Gates(label_fit="error"))` is called
  Then   a `ValueError` is raised; `check_arrow_label_fit()` returns the
         offending label

## Context
**Notes**
- The canonical pattern for a ship-quality diagram is every gate at `"error"`:
  `save(..., gates=Gates.strict())`.
- Until 2.0.0 the gates were five `*_check=` keyword arguments plus
  `allow_overlap=` / `allow_short_arrows=`. One `Gates` value replaced the seven.

**Current implementation**
- The seven `check_*` methods in
  `plugin/skills/excalidraw-diagram/scripts/excalidraw_engine/checks.py`, and
  `Gates` with the `save()` gate dispatch in `excalidraw_engine/gates.py`.
- `plugin/skills/excalidraw-diagram/scripts/test_excalidraw.py` (gate regression suite).


--------------------


---
id: REQ-EXCALIDRAW-846
status: confirmed
level: code
layer: feature
owner: Alex
satisfies: [ARCH-EXCALIDRAW-031]
---

# Named gates: crossing, legend, and overflow checks

## Description
> `.save()` runs five advisory checks before it writes a scene. Each is set through a
> `Gates` value to `"warn"` (print to stderr and continue, the default), `"error"` (raise
> `ValueError`) or `"off"`, so a generator can ship diagrams where readability defects — an
> arrow cutting through an unrelated box, an unlegended colour, text spilling out of its
> shape — fail the build instead of shipping silently.

Every bullet below is binding.
- `Gates(...)` sets each of five advisory gates to `"warn"` (default,
  prints to stderr), `"error"` (raises `ValueError`) or `"off"`: `crossing`,
  `legend`, `overflow`, `text_overlap`, `label_fit`. An unknown gate name or
  mode raises `ValueError`.
- `crossing`: a bound arrow whose straight centre-to-centre path passes
  through an unrelated box triggers the gate.
- `legend`: a fill colour used on any shape but absent from the
  `legend()` key triggers the gate (fires only after `legend()` is
  rendered; a scene with no legend is exempt).
- `overflow`: a shape whose bound text is larger than the shape bounds
  (text spills outside) triggers the gate.

## Cases
CASE-1 — each named gate accepts warn or error mode
  Given  a scene with a crossing violation
  When   it is saved once with the default `Gates()` and once with `Gates(crossing="error")`
  Then   the warn call prints a warning and returns normally, the error call raises `ValueError`

CASE-2 — the crossing gate fires when an arrow's path crosses an unrelated box
  Given  a bound arrow whose straight centre-to-centre path passes through a third, unrelated
         box
  When   `save(gates=Gates(crossing="error"))` is called
  Then   a `ValueError` naming the crossing is raised

CASE-3 — the legend gate fires for an unlegended colour, exempt with no legend
  Given  a shape painted "blue" with `legend()` rendered but "blue" absent from its key
  When   `save(gates=Gates(legend="error"))` is called
  Then   a `ValueError` naming the unlegended colour is raised; the same scene with no
         `legend()` call raises nothing

CASE-4 — the overflow gate fires when bound text exceeds the shape bounds
  Given  a box whose bound text is wider than the box
  When   `save(gates=Gates(overflow="error"))` is called
  Then   a `ValueError` is raised


--------------------


---
id: REQ-EXCALIDRAW-847
status: confirmed
level: code
layer: feature
owner: Alex
satisfies: [ARCH-EXCALIDRAW-031]
---

# Text-overlap, label-fit gates, and the two hard gates

## Description
> Two more advisory checks (`text_overlap`, `label_fit`) catch overlapping captions and
> labels that crowd their arrow. Beyond those, `.save()` enforces two hard gates that raise
> unless explicitly switched — overlapping shapes and arrows too short to render — because
> those two defects have no legitimate "warn and ship" default.

Every bullet below is binding.
- `text_overlap`: two free captions or label elements that geometrically
  overlap each other trigger the gate.
- `label_fit`: a bound arrow whose text label is wider than the connector
  it sits on — leaving less than ~24px of visible line on each side, measuring
  the label box projected onto the arrow direction — triggers the gate
  (the label crowds the arrowheads or spills onto the joined boxes).
- `.save()` additionally enforces two hard gates that default to `"error"`:
  `overlap` (overlapping non-container shapes) and `short_arrows` (a bound arrow
  clamped too short to render a visible line, so only its label would show).
  `Gates(overlap="off")` or `Gates(short_arrows="off")` ships a deliberate exception.
- The inspection methods `check_overlaps()`, `check_arrow_crossings()`,
  `check_legend_coverage()`, `check_text_overflow()`, `check_text_overlaps()`,
  `check_short_arrows()`, `check_arrow_label_fit()` each return a list of
  offending items (empty list = clean) and are callable before `.save()`.
- `test_excalidraw.py` exercises the five advisory gates in both `"warn"` and
  `"error"` modes, and the two hard gates, for each maintained example
  generator.

## Cases
CASE-1 — the text_overlap gate fires when two labels geometrically overlap
  Given  two `label()` elements placed at overlapping coordinates
  When   `save(gates=Gates(text_overlap="error"))` is called
  Then   a `ValueError` naming the overlapping pair is raised

CASE-2 — the label_fit gate fires when a label crowds a short arrow
  Given  a bound arrow whose label leaves less than ~24px of visible line on one side
  When   `save(gates=Gates(label_fit="error"))` is called
  Then   a `ValueError` is raised

CASE-3 — the two hard gates raise by default and can be switched off
  Given  two overlapping non-container shapes, and separately a bound arrow clamped too short to
         render
  When   `save()` is called with defaults, then again with `Gates(overlap="off")` /
         `Gates(short_arrows="off")`
  Then   the default calls raise `ValueError`, and the switched calls write the files without
         raising

CASE-4 — an inspection method returns offending items without saving
  Given  a scene with one crossing-arrow violation and no other defects
  When   `check_arrow_crossings()` is called before `.save()`
  Then   it returns a list containing that one item, while an unaffected check like
         `check_text_overflow()` returns an empty list
