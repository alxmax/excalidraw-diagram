---
id: REQ-DATAMODEL-909
status: confirmed
level: code
layer: feature
owner: Alex
satisfies: [ARCH-DATAMODEL-036]
---

# A source-to-target mapping that says when it cannot tell

## Description
> A mapping that looks complete and is wrong is worse than none, because people build on
> it. The reader behind this one is small, so it follows only what it can follow with
> certainty and marks the rest "needs review" with the reason, leaving the guess to a person
> who reads the SQL.

Every bullet below is binding.
- `mapping_markdown(project_dir)` returns Markdown with one section per model, upstream models first, each holding a table of target column, source, transformation and rule.
- A model's rows are the columns its SELECT produces, in order, then any column schema.yml declares that the SQL does not produce.
- A column is traced through table aliases, joins and CTEs to `model.column` or `source.table.column`, never to the name of a CTE.
- A bare column name over several relations is placed with the one relation known to hold it, and left for review when that relation is not unique.
- A rename reads `rename`, a copy reads `copy`, and any other expression is shown as written with every column it reads listed as a source.
- The rule is the model's schema.yml tests on the column, including the target of a `relationships` test and the values of `accepted_values`.
- With `select *`, each column the starred relation produces is a copy via the star, whether or not schema.yml declares it.
- A column is marked "needs review" with its reason, never guessed, for a union, Jinja control flow, a subquery in FROM, a CTE it cannot read or an ambiguous bare name.
- A column marked "needs review" also covers an unaliased expression, a column missing from the SELECT, and a model with no SQL file.
- A pipe inside a cell is escaped, and one project always produces the same text.

## Cases
CASE-1 — plain columns are traced
  Given  models that read source tables through CTEs, rename a column there, and end in `select *`
  When   `mapping_markdown()` is called
  Then   each column names its `model.column` or `source.table.column`, never a CTE
  And    each reads `copy` or `rename`

CASE-2 — an expression keeps its text
  Given  `min(orders.order_date) as first_order` and `amount / 100 as amount`
  When   `mapping_markdown()` is called
  Then   each row shows the expression as written, and one inside a CTE is not hidden behind `copy`

CASE-3 — rules and order
  Given  schema tests `not_null`, `relationships` and `accepted_values`, and marts that depend on staging models
  When   `mapping_markdown()` is called
  Then   the rule cell lists those tests with their targets and values, and staging models come first

CASE-4 — select star
  Given  a model that selects `*` from a model producing a column its schema does not declare
  When   `mapping_markdown()` is called
  Then   every column the star brings in gets a row reading `copy (via *)`, declared or not

CASE-5 — what cannot be read is marked
  Given  a union, Jinja control flow, a subquery in FROM, a bare name over two relations, and a CTE built on a union
  When   `mapping_markdown()` is called
  Then   each affected row says "needs review" with the reason, and names no guessed source

CASE-6 — what is missing is marked
  Given  an unaliased expression, a model with no SQL file, and a column the schema declares but the SELECT lacks
  When   `mapping_markdown()` is called
  Then   each affected row says "needs review" with the reason

CASE-7 — safe and stable text
  Given  an expression containing `||`, and the same project read twice
  When   `mapping_markdown()` is called
  Then   the pipes are escaped inside the table, and both texts are identical

## Context
**Notes**
- Only a plain `select` is read: window functions, lateral joins, `pivot`, macros and Jinja loops are not.
  A name that looks like a column but is a SQL keyword is filtered by a fixed list, so an
  unusual keyword can appear as a source; the row is then marked only if the schema is known.
- Column types are not inferred, so a `cast(...)` shows as written.

**Current implementation**
- `mapping_markdown()` in `plugin/skills/excalidraw-diagram/scripts/excalidraw_engine/mapping.py`;
  `read_dbt_project()` in `dbt.py`. The file-writing flag is `REQ-DATAMODEL-912`'s.
- `TestMapping` in `plugin/skills/excalidraw-diagram/scripts/test_data_model.py`.
