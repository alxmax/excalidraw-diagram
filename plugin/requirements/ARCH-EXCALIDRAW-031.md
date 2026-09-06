---
id: ARCH-EXCALIDRAW-031
status: confirmed
level: architecture
layer: feature
owner: Alex
milestone: v2.4
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
- `.save()` supports five named gates (`crossing_check`, `legend_check`, `overflow_check`, `text_overlap_check`, `label_fit_check`), each accepting `"warn"` (default, prints) or `"error"` (raises `ValueError`). [[REQ-EXCALIDRAW-846]]
- `.save()` additionally enforces two hard gates that raise `ValueError` by default — overlapping shapes and arrows clamped too short to render — each with its own opt-out flag for a deliberate exception. [[REQ-EXCALIDRAW-847]]

## Cases
CASE-1
  Given  a scene where a bound arrow's path passes through an unrelated box
  When   `save(crossing_check="error")` is called
  Then   a `ValueError` is raised; `save(crossing_check="warn")` emits a
         warning and exits normally

CASE-2
  Given  a scene with `fill="blue"` on a box and no `legend()` rendered
  When   `save(legend_check="error")` is called
  Then   a `ValueError` is raised naming the unlegended colour

CASE-3
  Given  a box whose bound text is wider than the box width
  When   `save(overflow_check="error")` is called
  Then   a `ValueError` is raised; `check_text_overflow()` returns the
         offending shape id

CASE-4
  Given  two `label()` elements placed at overlapping coordinates
  When   `save(text_overlap_check="error")` is called
  Then   a `ValueError` is raised naming the overlapping pair

CASE-5
  Given  each maintained example generator in `examples/`
  When   `test_excalidraw.py` runs it
  Then   the generator produces zero violations on every gate (the five named
         gates and both hard gates)

CASE-6
  Given  two boxes placed close but not overlapping, joined by a bound arrow
  When   `save()` is called with defaults
  Then   a `ValueError` is raised (the connector is too short to render);
         `save(allow_short_arrows=True)` writes the files, and
         `check_short_arrows()` returns the offending pair

CASE-7
  Given  a bound arrow whose label is wider than the arrow's visible line
  When   `save(label_fit_check="error")` is called
  Then   a `ValueError` is raised; `check_arrow_label_fit()` returns the
         offending label

## Context
**Notes**
- The canonical pattern for a ship-quality diagram is all five named gates set
  to `"error"` (the two hard gates already raise by default): `save(...,
  crossing_check="error", legend_check="error", overflow_check="error",
  text_overlap_check="error", label_fit_check="error")`.

**Current implementation**
- `check_overlaps`, `check_arrow_crossings`, `check_legend_coverage`,
  `check_text_overflow`, `check_text_overlaps`, `check_short_arrows`,
  `check_arrow_label_fit` and the `save()` gate dispatch in
  `skills/excalidraw-diagram/scripts/excalidraw_builder.py`.
- `skills/excalidraw-diagram/scripts/test_excalidraw.py` (gate regression suite).


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
> `.save()` runs five named checks before it writes a scene. Each accepts `"warn"` (print and
> continue, the default) or `"error"` (raise `ValueError`), so a generator can ship diagrams
> where readability defects — an arrow cutting through an unrelated box, an unlegended
> colour, text spilling out of its shape — fail the build instead of shipping silently.

Every bullet below is binding.
- `.save()` supports five named gates, each accepting `"warn"` (default,
  prints) or `"error"` (raises `ValueError`): `crossing_check`, `legend_check`,
  `overflow_check`, `text_overlap_check`, `label_fit_check`.
- `crossing_check`: a bound arrow whose straight centre-to-centre path passes
  through an unrelated box triggers the gate.
- `legend_check`: a fill colour used on any shape but absent from the
  `legend()` key triggers the gate (fires only after `legend()` is
  rendered; a scene with no legend is exempt).
- `overflow_check`: a shape whose bound text is larger than the shape bounds
  (text spills outside) triggers the gate.

## Cases
CASE-1 — each named gate accepts warn or error mode
  Given  a scene with a crossing_check violation
  When   `save(crossing_check="warn")` and `save(crossing_check="error")` are each called
  Then   the warn call prints a warning and returns normally, the error call raises `ValueError`

CASE-2 — crossing_check fires when an arrow's path crosses an unrelated box
  Given  a bound arrow whose straight centre-to-centre path passes through a third, unrelated
         box
  When   `save(crossing_check="error")` is called
  Then   a `ValueError` naming the crossing is raised

CASE-3 — legend_check fires for an unlegended colour, exempt with no legend
  Given  a shape filled "blue" with `legend()` rendered but "blue" absent from its key
  When   `save(legend_check="error")` is called
  Then   a `ValueError` naming the unlegended colour is raised; the same scene with no
         `legend()` call raises nothing

CASE-4 — overflow_check fires when bound text exceeds the shape bounds
  Given  a box whose bound text is wider than the box
  When   `save(overflow_check="error")` is called
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
> Two more named checks (`text_overlap_check`, `label_fit_check`) catch overlapping captions
> and labels that crowd their arrow. Beyond those, `.save()` enforces two hard gates that
> always raise unless explicitly opted out — overlapping shapes and arrows too short to
> render — because those two defects have no legitimate "warn and ship" case.

Every bullet below is binding.
- `text_overlap_check`: two free captions or label elements that geometrically
  overlap each other trigger the gate.
- `label_fit_check`: a bound arrow whose text label is wider than the connector
  it sits on — leaving less than ~24px of visible line on each side, measuring
  the label box projected onto the arrow direction — triggers the gate
  (the label crowds the arrowheads or spills onto the joined boxes).
- `.save()` additionally enforces two hard gates that raise `ValueError`
  by default (no `"warn"`/`"error"` mode), each with an opt-out flag for a
  deliberate exception: overlapping non-container shapes (`allow_overlap=True`)
  and a bound arrow clamped too short to render a visible line — only its label
  would show — (`allow_short_arrows=True`).
- The inspection methods `check_overlaps()`, `check_arrow_crossings()`,
  `check_legend_coverage()`, `check_text_overflow()`, `check_text_overlaps()`,
  `check_short_arrows()`, `check_arrow_label_fit()` each return a list of
  offending items (empty list = clean) and are callable before `.save()`.
- `test_excalidraw.py` exercises the five named gates in both `"warn"` and
  `"error"` modes, and the two hard gates, for each maintained example
  generator.

## Cases
CASE-1 — text_overlap_check fires when two labels geometrically overlap
  Given  two `label()` elements placed at overlapping coordinates
  When   `save(text_overlap_check="error")` is called
  Then   a `ValueError` naming the overlapping pair is raised

CASE-2 — label_fit_check fires when a label crowds a short arrow
  Given  a bound arrow whose label leaves less than ~24px of visible line on one side
  When   `save(label_fit_check="error")` is called
  Then   a `ValueError` is raised

CASE-3 — the two hard gates raise by default and respect their opt-out flags
  Given  two overlapping non-container shapes, and separately a bound arrow clamped too short to
         render
  When   `save()` is called with defaults, then again with `allow_overlap=True` /
         `allow_short_arrows=True`
  Then   the default calls raise `ValueError`, and the opt-out calls write the files without
         raising

CASE-4 — an inspection method returns offending items without saving
  Given  a scene with one crossing-arrow violation and no other defects
  When   `check_arrow_crossings()` is called before `.save()`
  Then   it returns a list containing that one item, while an unaffected check like
         `check_text_overflow()` returns an empty list

