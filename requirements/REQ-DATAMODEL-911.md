---
id: REQ-DATAMODEL-911
status: confirmed
level: code
layer: feature
owner: Alex
satisfies: [ARCH-DATAMODEL-036]
---

# A data-model diagram a stranger can read

## Description
> A student, or anyone who has never met a star schema or this repository, should not have
> to look anything up. Every colour has an icon and a plain sentence, every term on the
> picture is defined in everyday words, and every table says why it has its role.

Every bullet below is binding.
- The legend gives each role in use a colour, an icon and a plain meaning, and the review note gets the same.
- The subtitle says how to read the picture: a box is a table, an arrow from A to B means A holds a key that points at B.
- The glossary defines the terms the diagram uses in everyday words, and defines no term the diagram does not use.
- The glossary ends with one "Why" row per table, giving the evidence for its role.
- A key column in a node starts with an icon and the word `PK` or `FK`.
- A review note starts with the icon of its rule.
- An arrow carries its key column's name only when no two labels can meet: one fact table, and columns not listed.
- Without those labels the subtitle says to add `--columns`, unless the columns are already listed.
- The glossary starts to the right of the legend, whatever the legend's width.

## Cases
CASE-1 — legend with icon and meaning
  Given  a schema with facts, dimensions, unknown tables and review notes
  When   `graph_from_tables()` is called
  Then   each role in use has a legend entry starting with its icon and holding its plain meaning

CASE-2 — how to read it
  Given  any schema
  When   `graph_from_tables()` is called
  Then   the subtitle says what a box is and what an arrow from A to B means

CASE-3 — only the terms in use
  Given  a schema with notes, a clean one, one with columns listed and one with a role set by hand
  When   the glossary terms of each are read
  Then   each defines what it shows, and none defines SCD, PK or the like where the diagram has no use for them

CASE-4 — why each table has its role
  Given  the demo schema of six tables
  When   the glossary is read
  Then   it ends with one "Why" row per table, each holding the evidence in words

CASE-5 — icons on keys and notes
  Given  a primary key, a foreign key, a plain column and a review note
  When   their text is built
  Then   the keys start with an icon, then `PK` or `FK`
  And    the plain column is bare
  And    the note starts with its rule's icon

CASE-6 — labels only where they cannot collide
  Given  a one-fact schema, a two-fact schema, and the two-fact schema with columns listed
  When   `graph_from_tables()` is called
  Then   only the first labels its arrows, and the second says to add `--columns` in its subtitle

CASE-7 — a wide legend
  Given  schemas whose legend holds long entries
  When   `scene_from_ddl()` draws them through every gate
  Then   the files are written because the glossary does not overlap the legend

## Context
**Notes**
- The icons are Unicode emoji, so their look depends on the viewer's emoji font. The words
  carry the meaning on their own: an icon is a visual cue, never the only one.
- The "Why" rows repeat the classifier's evidence text, which is plain but still names
  things like "descriptive columns"; the glossary defines the roles those words lead to.

**Current implementation**
- Text and icons in `plugin/skills/excalidraw-diagram/scripts/excalidraw_engine/explain.py`;
  label policy in `data_model.py`; the glossary position in `spec.py`.
- `TestExplain` in `plugin/skills/excalidraw-diagram/scripts/test_data_model.py`.
