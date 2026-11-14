"""A dbt project -> the same table records ddl.py produces, plus the ref() lineage.

dbt has no foreign keys; what it has instead is two different statements, and they are
kept apart because they mean different things:

    relationships test   `tests: - relationships: {to: ref('x'), field: id}` on a column
                         says "this column points at that one": a foreign key, so it
                         feeds the classifier and the review like any DDL key.
    ref()                a model's SQL reading from another model says "built from":
                         lineage, a build dependency, not a relation between facts.

A column that carries both a `unique` and a `not_null` test is the model's primary key.
Column types come from `data_type` when the schema gives one and are empty otherwise, so
without them a model is classified from its name and keys alone.
"""

import os
import re

from .ddl import Column, ForeignKey, Table
from .miniyaml import parse_yaml

_REF = re.compile(r"""\bref\s*\(\s*(?:['"][^'"]+['"]\s*,\s*)?['"]([\w.-]+)['"]""")
_REF_TEXT = re.compile(r"""^ref\(\s*(?:['"][^'"]+['"]\s*,\s*)?['"]([\w.-]+)['"]""")
_NOISE = re.compile(r"\{#.*?#\}|/\*.*?\*/|--[^\n]*", re.S)


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _walk(root, extensions):
    for folder, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in ("target", "dbt_packages", ".git"))
        for name in sorted(files):
            if name.lower().endswith(extensions):
                yield os.path.join(folder, name)


def _tests(column):
    """The tests on a column as {name: arguments}; a bare `unique` has no arguments."""
    out = {}
    for test in (column.get("data_tests") or []) + (column.get("tests") or []):
        if isinstance(test, str):
            out[test] = {}
        elif isinstance(test, dict):
            for name, args in test.items():
                args = args or {}
                out[name] = args.get("arguments") or args if isinstance(args, dict) else {}
    return out


def _model_table(entry, where):
    """(Table, {column: {test: arguments}}) for a schema.yml `models:` entry."""
    if not isinstance(entry, dict) or not entry.get("name"):
        raise ValueError("%s: a model entry needs a name" % where)
    table, all_tests = Table(str(entry["name"])), {}
    for col in entry.get("columns") or []:
        if not isinstance(col, dict) or not col.get("name"):
            raise ValueError("%s: model %s has a column without a name" % (where, table.name))
        name, tests = str(col["name"]), _tests(col)
        all_tests[name] = tests
        table.columns.append(Column(name, str(col.get("data_type") or ""),
                                    nullable="not_null" not in tests))
        if "unique" in tests and "not_null" in tests:
            table.primary_key.append(name)
        rel = tests.get("relationships")
        target = _REF_TEXT.match(str(rel.get("to", ""))) if rel else None
        if target:                              # a source(...) target is not a model: skipped
            table.foreign_keys.append(ForeignKey(
                [name], target.group(1), [str(rel["field"])] if rel.get("field") else []))
    return table, all_tests


def read_dbt(project_dir):
    """(tables, lineage) for the dbt project in `project_dir`.

    `tables` is a list of Table, one per model, sorted by name: a model that has SQL
    and/or a schema.yml entry. `lineage` is a sorted list of (model, upstream) pairs for
    every ref() whose target is another model of the project. Raises ValueError naming
    the file when a schema.yml cannot be read, or the directory when it holds no model."""
    # implements: REQ-DATAMODEL-907
    tables, lineage, _sql, _tests = read_dbt_project(project_dir)
    return tables, lineage


def read_dbt_project(project_dir):
    """(tables, lineage, sql, tests): what read_dbt() returns, plus the raw SQL of each
    model that has a .sql file ({model: text}) and the schema.yml tests on each column
    ({model: {column: {test: arguments}}}). The mapping report reads these."""
    root = os.path.join(project_dir, "models")
    root = root if os.path.isdir(root) else project_dir
    tables, refs, texts, tests = {}, {}, {}, {}
    for path in _walk(root, (".yml", ".yaml")):
        try:
            doc = parse_yaml(_read(path))
            entries = doc.get("models") if isinstance(doc, dict) else None
            for entry in entries or []:
                table, column_tests = _model_table(entry, path)
                if table.name in tables:
                    raise ValueError("model %s is described twice" % table.name)
                tables[table.name], tests[table.name] = table, column_tests
        except ValueError as exc:
            raise ValueError("%s: %s" % (path, exc) if path not in str(exc) else str(exc))
    for path in _walk(root, (".sql",)):
        name = os.path.splitext(os.path.basename(path))[0]
        tables.setdefault(name, Table(name))
        texts[name] = _read(path)
        refs[name] = set(_REF.findall(_NOISE.sub(" ", texts[name])))
    if not tables:
        raise ValueError("%s: no dbt model found (looked for .sql files and schema.yml "
                         "files under %s)" % (project_dir, root))
    lineage = sorted((m, up) for m, ups in refs.items() for up in ups
                     if up in tables and up != m)
    return [tables[n] for n in sorted(tables)], lineage, texts, tests
