---
id: REQ-DATAMODEL-908
status: confirmed
level: code
layer: feature
owner: Alex
satisfies: [ARCH-DATAMODEL-036]
---

# A YAML subset reader for dbt schema files

## Description
> The plugin installs nothing from PyPI, so it has no YAML library. It reads the part of
> YAML that a dbt project writes and refuses the rest with a line number, because a file
> that is half understood would change the diagram without saying so.

Every bullet below is binding.
- `parse_yaml(text)` reads block maps and block lists nested by indentation, including a list item that opens a map and a list at the same indent as its key.
- `parse_yaml()` reads quoted and plain scalars as strings, numbers, booleans or null.
- `parse_yaml()` reads flow lists and flow maps.
- `parse_yaml()` reads `|` and `>` block scalars.
- `parse_yaml()` ignores `#` comments and a leading `---`.
- `parse_yaml()` keeps `{{ ... }}` as text.
- `parse_yaml()` raises `ValueError` naming the line for anchors, aliases, tags, tab indentation, a repeated key, several documents or an unreadable line.

## Cases
CASE-1 — nested maps and lists
  Given  maps nested by indentation, a list of maps that open on the dash line, and a list at its key's indent
  When   `parse_yaml()` reads them
  Then   it returns the matching nested dictionaries and lists

CASE-2 — scalars and flow collections
  Given  booleans, null, numbers, quoted strings, a `ref('m')` string and flow collections
  When   `parse_yaml()` reads them
  Then   each value has its Python type, and `{{ doc('d') }}` stays a string

CASE-3 — block scalars and comments
  Given  a `>` and a `|` block scalar, comments and a leading `---`
  When   `parse_yaml()` reads the text
  Then   the folded scalar joins with spaces, the literal one keeps its newlines, and comments are dropped

CASE-4 — what is outside the subset
  Given  an anchor, a tab indent, a repeated key, a second document, an unreadable line and an open quote
  When   `parse_yaml()` reads each
  Then   `ValueError` is raised naming the line that is wrong

## Context
**Notes**
- A ` #` inside a block scalar is read as a comment, so a description holding one loses
  the rest of that line.

**Current implementation**
- `parse_yaml()` in `plugin/skills/excalidraw-diagram/scripts/excalidraw_engine/miniyaml.py`.
- `TestMiniYaml` in `plugin/skills/excalidraw-diagram/scripts/test_data_model.py`.
