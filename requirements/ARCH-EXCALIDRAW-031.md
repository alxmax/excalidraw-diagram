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
- `.save()` also runs three design gates that judge hierarchy rather than defects: one focus and a node budget [[REQ-EXCALIDRAW-860]], and right-angle connectors [[REQ-EXCALIDRAW-861]]. They warn by default and under `Gates.strict()`, so they advise and never refuse a file unless a caller names one.

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
         advisory gates, both hard gates and the three design gates)

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
  `plugin-full/skills/excalidraw-diagram/scripts/excalidraw_engine/checks.py`, and
  `Gates` with the `save()` gate dispatch in `excalidraw_engine/gates.py`.
- `plugin-full/skills/excalidraw-diagram/scripts/test_excalidraw.py` (gate regression suite).


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
- `crossing` also fires when any drawn arrow or line runs through the caption of
  an `enclose()` frame.
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

CASE-5 — the crossing gate sees an arrow through a frame caption
  Given  an arrow drawn straight through the caption of an `enclose()` frame
  When   `check_arrow_crossings()` is called
  Then   it names the arrow's two ends and the caption


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
- `overlap` also fires on a node inside an `enclose()` frame, or on its caption, that
  is not one of the ids the frame was drawn around.
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

CASE-5 — the overlap gate sees a box that strayed into a frame
  Given  a frame drawn around two boxes, and a third box placed inside it
  When   `check_overlaps()` is called
  Then   it names the third box and the frame's caption, and not the two members


--------------------


---
id: REQ-EXCALIDRAW-860
status: confirmed
level: code
layer: feature
owner: Alex
satisfies: [ARCH-EXCALIDRAW-031]
---

# Design gates: one focus and a node budget

## Description
> A diagram can pass every defect gate and still not say where to look: a box per
> colour of the palette, five things in the accent, thirty nodes in one region. Two
> design gates name those cases, so the builder advises on hierarchy the way it
> refuses defects, without refusing a file for a judgement call.

Every bullet below is binding.
- `Scene(accent=...)` names the focal colour, orange by default. A paint of `"accent"`
  resolves to it, and so does a role declared as `"accent"`.
- `check_focus()` reports more than 2 shapes filled in the accent colour, with their labels.
- `check_focus()` also reports more than 4 distinct role fills, counting neither neutral grey,
  white, transparent nor the accent.
- `check_node_budget()` reports every `section()` region, or the whole scene without one,
  holding more than 12 nodes.
- `check_node_budget()` also reports every `enclose()` frame holding more than 12 nodes.
- `check_node_budget()` counts shapes sharing one `Paint(group=...)` as one node.
- `Gates` carries `focus` and `node_budget` as design gates. They default to `"warn"`, and
  `Gates.strict()` leaves them at `"warn"`; naming one as `"error"` makes it raise.

## Cases
CASE-1 — the focus gate names a rainbow and a crowd of accents
  Given  five boxes in five role colours, and separately three boxes painted "accent"
  When   `check_focus()` is called on each scene
  Then   the first reports 5 role fills, and the second reports 3 accent shapes by label

CASE-2 — grey, the accent and four roles is one clear focus
  Given  two grey boxes, two accent boxes, four boxes in four role colours, and a legend
  When   `check_focus()` is called
  Then   it returns an empty list, because legend swatches are not nodes

CASE-3 — the node budget counts per region and per frame
  Given  a section of 9 nodes, and a second section of 13 nodes framed by `enclose()`
  When   `check_node_budget()` is called
  Then   it names the second section and the frame, each with 13, and not the first

CASE-4 — a painted group counts once
  Given  twenty boxes that share one `Paint(group=...)`, like the cells of one waveform row
  When   `check_node_budget()` is called
  Then   it returns an empty list

CASE-5 — the design gates warn, even under strict
  Given  a scene with five role fills
  When   it is saved with the default `Gates()`, then with `Gates.strict()`, then with
         `Gates(focus="error")`
  Then   the first two print a `focus` warning and write the files, and the third raises
         `ValueError`

## Context
**Notes**
- The limits are `MAX_ACCENTS`, `MAX_ROLE_FILLS` and `NODE_BUDGET` in `checks.py`. The
  contract states them as a rule in `SKILL.md` under the quality rules **One focus** and
  **Node budget: 9–12 nodes per region**, cited here by name.
- Every maintained example holds to both checks in full: `TestExampleDiagrams` asserts
  them empty, although `save()` only warns.

**Current implementation**
- `check_focus()` and `check_node_budget()` in
  `plugin-full/skills/excalidraw-diagram/scripts/excalidraw_engine/checks.py`; the
  `focus` and `node_budget` rows of `_GATES` and the `design` mode in
  `excalidraw_engine/gates.py`; `Scene(accent=...)` in `excalidraw_engine/canvas.py`.
- `CasesExcalidrawDesignGates` in
  `plugin-full/skills/excalidraw-diagram/scripts/test_excalidraw.py`.


--------------------


---
id: REQ-EXCALIDRAW-861
status: confirmed
level: code
layer: feature
owner: Alex
satisfies: [ARCH-EXCALIDRAW-031]
---

# Right-angle connectors and the orthogonal gate

## Description
> A diagonal connector reads as noise beside boxes that sit on a grid, and it cuts
> through more of the diagram than a connector that turns once. The builder can draw
> every bound arrow at right angles, and a design gate names each one that is not.

Every bullet below is binding.
- `arrow(src, dst, elbow=True)` draws a bound arrow whose every leg is horizontal or vertical.
- An elbow arrow between shapes that share a row or a column is one straight leg in the
  shared span.
- Any other elbow arrow has three legs. It leaves the side facing the target, turns in the
  gap between the shapes, and enters the facing side.
- An elbow arrow's label sits at the midpoint of its middle leg, where the editor draws it.
- Each elbow connector takes its own attach point on a side it shares, at least 12px from
  any other.
- `check_arrow_crossings()` judges an elbow arrow along its actual legs, not the line
  between centres.
- `check_orthogonal_arrows()` reports every bound arrow with a leg that is neither
  horizontal nor vertical. `Gates` carries it as the `orthogonal` design gate.

## Cases
CASE-1 — an elbow arrow turns only at right angles
  Given  two boxes that share neither a row nor a column
  When   `arrow(a, b, label="goes", elbow=True)` is called
  Then   the arrow has three axis-aligned legs and stays bound to both boxes. Its label
         sits on the middle leg, and two boxes sharing a row get one straight leg instead

CASE-2 — connectors sharing a side get their own points
  Given  three boxes that each send an elbow arrow to one wide box below them
  When   the end points on that box's top side are compared
  Then   every two of them are at least 12px apart

CASE-3 — the orthogonal gate names a diagonal
  Given  a straight bound arrow between two boxes on a diagonal
  When   `check_orthogonal_arrows()` is called, and the scene is saved with `Gates.strict()`
  Then   it names the pair, and the save prints an `orthogonal` warning and writes the files

CASE-4 — an elbow arrow through a box is a crossing
  Given  an elbow arrow whose turn runs through an unrelated box
  When   `check_arrow_crossings()` is called
  Then   it names that box

## Context
**Notes**
- `PackOptions(edge_style="orthogonal")` is the auto-layout's right-angle style and the
  one `SKILL.md` recommends. It stays opt-in: making it the default moved labels in the
  frozen layout corpus and the data-model star layout, which the ratchet refuses.
- The data-model command saves with `orthogonal="off"`: its star layout draws diagonals
  on purpose, and a warning the user cannot act on is noise.

**Current implementation**
- `arrow(..., elbow=True)`, `_elbow_route()` and `_port()` in
  `plugin-full/skills/excalidraw-diagram/scripts/excalidraw_engine/connectors.py`;
  `check_orthogonal_arrows()` and the leg-wise crossing test in
  `excalidraw_engine/checks.py`.
- `CasesExcalidrawElbow` in
  `plugin-full/skills/excalidraw-diagram/scripts/test_excalidraw.py`.

