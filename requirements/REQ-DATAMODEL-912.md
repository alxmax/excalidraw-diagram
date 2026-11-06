---
id: REQ-DATAMODEL-912
status: confirmed
level: code
layer: feature
owner: Alex
satisfies: [ARCH-DATAMODEL-036]
---

# The mapping file is written only for a diagram that was drawn

## Description
> A mapping file beside a diagram that failed its checks would look like a finished pair
> when half of it never existed. So the file is written last, after the scene has passed
> every gate, and a run that fails anywhere leaves no mapping behind.

Every bullet below is binding.
- `data-model --from-dbt <project> --mapping <file.md>` writes the mapping as UTF-8 Markdown, the same text `mapping_markdown()` returns.
- The file is written only after the scene has passed every gate.
- `--mapping` without `--from-dbt` is a usage error.
- A project that cannot be read leaves no mapping file.

## Cases
CASE-1 — the file is written beside the scene
  Given  the fixture dbt project and a mapping path
  When   `data-model --from-dbt --mapping` runs
  Then   the file holds exactly the text `mapping_markdown()` returns

CASE-2 — a failed gate leaves no file
  Given  a project whose scene fails a gate
  When   `scene_from_dbt()` is called with a mapping path
  Then   it raises `ValueError`, and no mapping file exists

CASE-3 — the mapping needs a dbt project
  Given  a DDL file and a mapping path
  When   `data-model --from-ddl --mapping` runs
  Then   the command fails with a usage error

CASE-4 — an unreadable project leaves nothing
  Given  an empty project directory and a mapping path
  When   `data-model --from-dbt --mapping` runs
  Then   the command fails, and no mapping file exists

## Context
**Notes**
- The report is built before the scene is drawn, so a project that cannot be read fails early;
  the file itself is written after the gates, so a drawing that fails them never gets one.

**Current implementation**
- `scene_from_dbt()` in `plugin/skills/excalidraw-diagram/scripts/excalidraw_engine/data_model.py`;
  the `--mapping` flag in `cli.py`.
- `TestMapping` in `plugin/skills/excalidraw-diagram/scripts/test_data_model.py`.
