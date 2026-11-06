---
id: REQ-DATAMODEL-900
status: confirmed
level: code
layer: feature
owner: Alex
satisfies: [ARCH-DATAMODEL-036]
---

# Reading tables, keys and foreign keys from DDL

## Description
> A table the parser drops without a word is drawn as if it never existed, and the
> diagram still looks complete. So the reader takes what it understands, ignores
> statements that are not about tables, and refuses what it cannot read.

Every bullet below is binding.
- `parse_ddl(sql)` returns one table record per `CREATE TABLE`, in order of appearance, with its columns, primary key and foreign keys.
- `parse_ddl()` reads `PRIMARY KEY` and `REFERENCES` written inline or as table constraints.
- `parse_ddl()` reads `ALTER TABLE ... ADD ... FOREIGN KEY` and attaches it to the named table.
- `parse_ddl()` folds unquoted names to lower case, keeps quoted names as written, drops a schema prefix and strips comments.
- `parse_ddl()` ignores statements that define no table, and treats MySQL `KEY name (col)` as an index but `key varchar(20)` as a column.
- `parse_ddl()` raises `ValueError` for an unreadable `CREATE TABLE`, a table defined twice, an `ALTER TABLE` on an unknown table, or a script without tables.

## Cases
CASE-1 — tables and primary keys
  Given  the six-table demo schema
  When   `parse_ddl()` reads it
  Then   six tables come back in order, each with the primary key it declares

CASE-2 — foreign keys in every form
  Given  foreign keys written inline, as table constraints and through `ALTER TABLE`
  When   `parse_ddl()` reads them
  Then   each table lists its foreign keys with the referenced table and columns

CASE-3 — names, comments and index keywords
  Given  a quoted schema-qualified name, comments holding semicolons and a MySQL `KEY` index
  When   `parse_ddl()` reads the script
  Then   the table is named without its schema and the index is not taken for a column

CASE-4 — an unreadable script is refused
  Given  `CREATE TABLE t AS SELECT 1`, a duplicate table or an `ALTER TABLE` on an unknown table
  When   `parse_ddl()` reads it
  Then   `ValueError` is raised naming the offending statement or table

## Context
**Notes**
- A `CREATE TABLE ... AS SELECT` is refused rather than skipped: skipping it would hide a table.

**Current implementation**
- `parse_ddl()` in `plugin/skills/excalidraw-diagram/scripts/excalidraw_engine/ddl.py`.
- `TestParseDdl` in `plugin/skills/excalidraw-diagram/scripts/test_data_model.py`.
