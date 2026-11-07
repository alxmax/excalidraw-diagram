---
id: REQ-DATAMODEL-915
status: confirmed
level: code
layer: feature
owner: Alex
satisfies: [ARCH-DATAMODEL-036]
---

# Five more review rules: key types, dimensions, shared dimensions, lists of keys

## Description
> The first five rules look at one table's keys and history. These five look at what a
> relationship is made of and how the tables fit together. Each fires only on evidence it
> can quote, so a clean schema stays silent: an invented warning costs more trust than a
> missed one.

Every bullet below is binding.
- The `fk-type` rule flags a foreign key column whose declared type differs from the type of the key it points at.
- Two types are the same when they differ only in length, precision or an alias such as `int` and `integer`, or a `serial` key and an `int`.
- The `fk-type` rule is silent when either column has no declared type.
- The `degenerate-dimension` rule flags a dimension whose columns are all keys, so it holds nothing but its key.
- The `junk-dimension` rule flags a dimension with two or more non-key columns that are all flags.
- A flag is a boolean column, or one named `is_*`, `has_*`, `can_*`, `*_flag` or `*_ind`.
- The `conformed-dimension` rule flags a fact that has dimensions and shares none of them with any other fact.
- The `many-to-many` rule flags a column named `*_ids`, `*_keys` or `*_codes`, or an array column named like a key, that is not itself a key.
- Each new rule has a plain-words term in the glossary, shown when a note of that rule is drawn.

## Cases
CASE-1 — foreign key types
  Given  a foreign key declared `int` to a `bigint` key, one to a `varchar` key, and ones that differ only by alias, length or an undeclared type
  When   `review_tables()` is run
  Then   the first two raise `fk-type` and the others do not

CASE-2 — degenerate dimension
  Given  a dimension holding only its key, and one that also holds a name
  When   `review_tables()` is run
  Then   only the first raises `degenerate-dimension`

CASE-3 — junk dimension
  Given  a dimension of two flags, one of a flag and a name, and one of a single flag
  When   `review_tables()` is run
  Then   only the first raises `junk-dimension`

CASE-4 — shared dimensions
  Given  two facts with no dimension in common, two that share one, and a schema with one fact
  When   `review_tables()` is run
  Then   both facts of the first pair raise `conformed-dimension` and nothing else does

CASE-5 — several keys in one column
  Given  columns `tag_ids`, `tag_keys` and an `int[]` named `tag_id`, and columns `tags text[]`, `author_id` and `title`
  When   `review_tables()` is run
  Then   the first three raise `many-to-many` and the others do not

CASE-6 — no new alarm on the shipped examples
  Given  the demo, clean, no-prefix and order-process schemas and the dbt example
  When   `review_tables()` is run on each
  Then   none of the five new rules fires

CASE-7 — every new rule is explained
  Given  a note of any of the five rules
  When   the glossary is built
  Then   it defines that rule's term in plain words

## Context
**Notes**
- `degenerate-dimension` reports a table nobody needs: an order number kept in a table of its own.
  The correct shape, the key kept in the fact, raises nothing.
- `conformed-dimension` skips a fact with no dimensions at all, so an orphan key is reported once,
  by `orphan-fk`, and not twice. Two unrelated subject areas in one schema will be flagged; the
  note says what to add if they were meant to be compared.
- `many-to-many` reads names and array types only. A column holding a list of values that are not
  keys, such as `tags text[]`, is left alone.
- The rules were run over the shipped examples before they were written down: none raised anything,
  which is what CASE-6 pins.

**Current implementation**
- The five rules and `RULES` in
  `plugin/skills/excalidraw-diagram/scripts/excalidraw_engine/review.py`; the terms in `explain.py`.
- `TestMoreReviewRules` in `plugin/skills/excalidraw-diagram/scripts/test_data_model.py`.
