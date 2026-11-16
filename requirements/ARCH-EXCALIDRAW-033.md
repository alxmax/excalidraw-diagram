---
id: ARCH-EXCALIDRAW-033
status: confirmed
level: architecture
layer: feature
owner: Alex
milestone: v1.0.1
depends_on: [ARCH-EXCALIDRAW-030]
satisfies: [SYS-DIAGRAM-001]
---

# Explanatory output — a diagram a reader with no context can decode

## Description
> The skill is reached for most often by someone who does not understand the
> thing being drawn: they ask "how does X work?" and want the picture to teach
> them. A diagram that is correct but implicit — colours with no key, project
> jargon with no definition, no stated reading direction — fails that reader
> even though every gate passes. So the output carries its own decoding: the
> canvas explains its colours, its terms and its order, in everyday words.

Every bullet below is binding.
- `Scene` exposes two decoding helpers, `legend()` for colour → meaning and
  `glossary()` for term → meaning, so every colour and every project-specific
  term used on the canvas is explained on that same canvas. [[REQ-EXCALIDRAW-849]]
  details the behaviour.
- A diagram produced for a reader who does not know the system opens with a
  `title()` and a one-line `label()` subtitle that states what the picture shows
  and its reading direction. Node text uses everyday words; jargon goes to the
  glossary rather than into a box.
- A teaching diagram numbers its main path ①②③, states one takeaway under its
  subtitle, and explains at most two *why*s in margin notes on dashed leaders. The node
  text has two tiers: an everyday name, and the real file or call beneath it.
  [[REQ-EXCALIDRAW-862]] details the calls.
- `examples/make_explainer.py` is the maintained reference for this shape (a
  teaching diagram read top to bottom, with a legend and a glossary) and builds
  clean on every gate.

## Cases
CASE-1 — a reader with no context can decode every colour and term
  Given  a scene that uses role colours and at least one project-specific term
  When   it is saved with `Gates(legend="error")`
  Then   a `legend()` decodes every fill colour used and a `glossary()` lists the
         term with its meaning, both on the same canvas

CASE-2 — the explainer example stays a clean teaching diagram
  Given  `examples/make_explainer.py`
  When   `test_excalidraw.py` runs it
  Then   the built scene contains a legend and a glossary, opens with a title,
         and produces zero violations on every gate

CASE-3 — the asker who does not know the system gets a picture that teaches it  <!-- verifiable by: inspection -->
  Given  a request phrased as "explain how X works" or "I don't understand X",
         with no mention of a diagram
  When   the skill runs
  Then   the delivered diagram opens with a title plus a one-line subtitle
         naming the reading direction. Its boxes use everyday words rather than
         file names alone. A legend decodes every colour; a glossary decodes
         every term. Checked by inspection; the reference shape is
         `make_explainer.py`

## Context
**Notes**
- The obligation on plain words and a stated reading direction is checked by
  reading the diagram, not by a gate: no check can tell "Auth service" from
  "Service A". Its prose form is the `SKILL.md` quality rule named
  **Real identifiers as node names, jargon in a glossary** — kept on one line
  here so `grep` can confirm the rule still exists. Cite it by name, never by
  number: renumbering the list would break this link silently, and neither the
  gate, the tests nor a line count would notice.
- The `legend` gate ([[REQ-EXCALIDRAW-846]]) is the mechanical half: once a legend
  is rendered, a fill it does not decode fails the build.

**Current implementation**
- `Scene.legend()` and `Scene.glossary()` in
  `plugin-full/skills/excalidraw-diagram/scripts/excalidraw_engine/annotate.py`.
- `plugin-full/skills/excalidraw-diagram/examples/make_explainer.py` (the reference
  teaching diagram); `TestExampleDiagrams` in
  `plugin-full/skills/excalidraw-diagram/scripts/test_excalidraw.py` runs it.
- The trigger phrases ("explain how X works", "I don't understand X") and the
  explainer recipe live in `SKILL.md` / `SKILL.universal.md`.


--------------------


---
id: REQ-EXCALIDRAW-862
status: confirmed
level: code
layer: feature
owner: Alex
satisfies: [ARCH-EXCALIDRAW-033]
---

# Teaching additions: steps, takeaway, margin notes, two-tier text

## Description
> A reader who does not know the system needs to know where to start, what to keep,
> and why the odd part is odd. Numbered steps give the order, one takeaway line gives
> the point, and two margin notes give the reasons. A second, smaller tier of node
> text keeps the real file names on the canvas without making them the headline.

Every bullet below is binding.
- `box(..., sublabel=...)` sets a second text tier under the name, in the code typeface
  at 12px, grouped with the shape.
- `check_text_overflow()` reports a sublabel wider than its shape, below its bottom, or
  above the end of the name.
- `pipeline(..., numbered=True)` opens each step's text with ①, ②, ③ in order. Its
  `line=` paints the chaining arrows.
- `pack()` sizes a node for its `sublabel` and opens the label of a node with `step`.
- `takeaway(text, at)` draws one line opened by "Takeaway:".
- `note(text, target, at=None)` draws a margin note joined to `target` by a dashed
  right-angle leader. Without `at` it goes in the first margin whose leader cuts no shape.
- `note()` raises `ValueError` on a third note in one scene.
- `check_arrow_crossings()` judges a note's leader along its legs.
- A graph description carries `takeaway`, `notes`, and a node's `sublabel` and `step`.

## Cases
CASE-1 — a sublabel is a second code tier that must fit
  Given  a box named "Orders API" with the sublabel "orders/api.py"
  When   it is drawn, and separately a box too narrow for its sublabel is drawn
  Then   the sublabel is code type, smaller, under the name and grouped with the shape. The
         narrow box's sublabel is reported by `check_text_overflow()`

CASE-2 — steps are numbered on the path
  Given  a three-step `pipeline(numbered=True, line="accent")`, and a `pack()` of two nodes
         with `step` 1 and 2
  When   the scenes are built
  Then   the steps read "① ask", "② build", "③ check" with accent arrows, and the packed
         labels open with ① and ②

CASE-3 — the takeaway opens with its word
  Given  a scene, and a graph description with a `takeaway` key
  When   `takeaway("one writer, many readers", (0, 0))` is called, and the description is built
  Then   each scene holds a line that starts with "Takeaway:"

CASE-4 — a margin note is joined, limited and checked
  Given  a box with a margin note, a box with two notes, and a note whose leader runs
         through an unrelated box
  When   each note is drawn
  Then   the first note sits in the margin on a dashed leader with every check clean. The
         third note raises `ValueError`, and the leader through a box is a crossing

CASE-5 — the explainer carries the teaching shape
  Given  `examples/make_explainer.py`
  When   `test_excalidraw.py` runs it
  Then   its scene holds one takeaway, steps ① to ⑤, two margin notes and a sublabel

## Context
**Notes**
- `MAX_NOTES` in `annotate.py` is the limit of two. A third reason belongs in the text
  around the diagram, not on it.
- A sublabel is free text, not bound text, because a shape binds one label. Sharing the
  shape's group is what moves it with the shape in the editor.

**Current implementation**
- `numbered_text()`, `takeaway()` and `note()` in
  `plugin-full/skills/excalidraw-diagram/scripts/excalidraw_engine/annotate.py`;
  `box(..., sublabel=...)` in `excalidraw_engine/shapes.py`; the `step` and `sublabel`
  keys in `excalidraw_engine/pack.py`; `takeaway` and `notes` in `excalidraw_engine/spec.py`.
- `CasesExcalidrawTeaching` and the explainer case in `CasesExcalidraw033`, in
  `plugin-full/skills/excalidraw-diagram/scripts/test_excalidraw.py`.

