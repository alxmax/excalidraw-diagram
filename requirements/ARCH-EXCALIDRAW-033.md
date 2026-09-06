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
- `examples/make_explainer.py` is the maintained reference for this shape (a
  teaching diagram read top to bottom, with a legend and a glossary) and builds
  clean on every gate.

## Cases
CASE-1 — a reader with no context can decode every colour and term
  Given  a scene that uses role colours and at least one project-specific term
  When   it is saved with `legend_check="error"`
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
- `legend_check` ([[REQ-EXCALIDRAW-846]]) is the mechanical half: once a legend
  is rendered, a fill it does not decode fails the build.

**Current implementation**
- `Scene.legend()` and `Scene.glossary()` in
  `plugin/skills/excalidraw-diagram/scripts/excalidraw_builder.py`.
- `plugin/skills/excalidraw-diagram/examples/make_explainer.py` (the reference
  teaching diagram); `TestExampleDiagrams` in
  `plugin/skills/excalidraw-diagram/scripts/test_excalidraw.py` runs it.
- The trigger phrases ("explain how X works", "I don't understand X") and the
  explainer recipe live in `SKILL.md` / `SKILL.universal.md`.
