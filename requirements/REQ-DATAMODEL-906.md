---
id: REQ-DATAMODEL-906
status: confirmed
level: code
layer: feature
owner: Alex
satisfies: [ARCH-DATAMODEL-036]
---

# A roles file that corrects the classifier

## Description
> The classifier is a heuristic, and on a real schema it will be wrong somewhere. A
> modeller who knows better needs to say so without editing rules, and the diagram must
> show that the role was chosen by a person, not found by the rules.

Every bullet below is binding.
- `parse_roles(text)` reads flat `table: role` lines, with `#` comments, blank lines and optional quotes, into a `{table: role}` map.
- `parse_roles()` raises `ValueError` naming the line for anything richer, a role other than fact, dimension, bridge or unknown, or a table listed twice.
- `classify_tables(tables, overrides)` gives each named table the role from the map, confidence 1 and an `overridden` flag, and keeps what the rules had said in the reason.
- `classify_tables()` raises `ValueError` for an override naming a table the schema does not define.
- The review rules and the node badge use the overridden role, and the badge reads `set by you`.
- The `data-model` command takes `--roles <file>`, and an error in that file names the file.

## Cases
CASE-1 — flat lines are read
  Given  a roles file with comments, a quoted table name, a trailing comment and mixed-case roles
  When   `parse_roles()` reads it
  Then   it returns each table with its lower-case role

CASE-2 — anything else is refused
  Given  a nested mapping, a list item, an unknown role and a table listed twice
  When   `parse_roles()` reads each
  Then   `ValueError` is raised naming the line that is wrong

CASE-3 — the override wins and the history stays
  Given  a schema and an override setting `stg_payments` to fact
  When   `classify_tables()` is called with it
  Then   that table is a fact at confidence 1, flagged overridden, and its reason says the rules had said unknown

CASE-4 — a typo is not ignored
  Given  an override naming a table the schema does not define
  When   `classify_tables()` is called with it
  Then   `ValueError` is raised naming that table

CASE-5 — the override reaches the review and the label
  Given  `dim_product` overridden to unknown
  When   `graph_from_tables()` is called
  Then   its surrogate-key note is gone and its label reads `unknown · set by you`

CASE-6 — the flag works end to end
  Given  a roles file, and one with a bad role or a missing table
  When   `data-model --from-ddl` is run with `--roles`
  Then   the first renders with the override marked, and the others fail naming the roles file

## Context
**Notes**
- The file is a YAML subset on purpose: the plugin is stdlib only and carries no YAML parser.
  Richer YAML is an error, never a guess, because a half-understood config changes a
  diagram without saying so.

**Current implementation**
- `parse_roles()` in `plugin/skills/excalidraw-diagram/scripts/excalidraw_engine/roles.py`;
  `classify_tables()` in `classify.py`; the flag in `cli.py`.
- `TestRoles` in `plugin/skills/excalidraw-diagram/scripts/test_data_model.py`.
