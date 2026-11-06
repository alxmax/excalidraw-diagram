#!/usr/bin/env python3
# tested-by: REQ-DATAMODEL-900  # tested-by: REQ-DATAMODEL-901  # tested-by: REQ-DATAMODEL-902  # tested-by: REQ-DATAMODEL-903  # tested-by: REQ-DATAMODEL-904  # tested-by: ARCH-DATAMODEL-036
"""Tests for the data-model module: DDL parser, table graph, end-to-end scene.

Run:  python -X utf8 -m unittest test_data_model -v   (from this scripts/ dir)
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "examples", "data_model")
sys.path.insert(0, HERE)

from excalidraw_engine import cli  # noqa: E402
from excalidraw_engine.classify import classify_tables  # noqa: E402
from excalidraw_engine.data_model import (  # noqa: E402
    graph_from_tables, scene_from_ddl, unresolved_fks)
from excalidraw_engine.ddl import parse_ddl  # noqa: E402
from excalidraw_engine.review import review_tables  # noqa: E402


def _read(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as fh:
        return fh.read()


def _tables(sql):
    return {t.name: t for t in parse_ddl(sql)}


class TestParseDdl(unittest.TestCase):
    """REQ-DATAMODEL-900: DDL becomes tables, keys and foreign keys."""

    def test_demo_schema_has_six_tables_in_order(self):  # verifies: REQ-DATAMODEL-900#CASE-1
        names = [t.name for t in parse_ddl(_read("shop_demo.sql"))]
        self.assertEqual(names, ["dim_date", "dim_customer", "dim_category",
                                 "dim_product", "fact_order_line", "stg_payments"])

    def test_primary_keys_inline_and_table_level(self):  # verifies: REQ-DATAMODEL-900#CASE-1
        t = _tables(_read("shop_demo.sql"))
        self.assertEqual(t["dim_product"].primary_key, ["product_id"])
        t = _tables("CREATE TABLE a (x int, y int, PRIMARY KEY (x, y));")
        self.assertEqual(t["a"].primary_key, ["x", "y"])

    def test_inline_and_table_level_foreign_keys(self):  # verifies: REQ-DATAMODEL-900#CASE-2
        t = _tables(_read("shop_demo.sql"))
        fk = {f.ref_table: f for f in t["fact_order_line"].foreign_keys}
        self.assertEqual(sorted(fk), ["dim_customer", "dim_date", "dim_product"])
        self.assertEqual(fk["dim_product"].columns, ["product_id"])
        self.assertEqual(fk["dim_product"].ref_columns, ["product_id"])
        t = _tables("CREATE TABLE p (id int PRIMARY KEY);"
                    "CREATE TABLE c (p_id int, CONSTRAINT fk FOREIGN KEY (p_id) REFERENCES p (id));")
        self.assertEqual(t["c"].foreign_keys[0].ref_table, "p")

    def test_alter_table_adds_foreign_key(self):  # verifies: REQ-DATAMODEL-900#CASE-2
        t = _tables(_read("shop_clean.sql"))
        refs = sorted(f.ref_table for f in t["fact_payment"].foreign_keys)
        self.assertEqual(refs, ["dim_customer", "dim_date"])

    def test_column_types_and_nullability(self):  # verifies: REQ-DATAMODEL-900#CASE-1
        t = _tables("CREATE TABLE a (n numeric(10, 2) NOT NULL, "
                    "s character varying(20) DEFAULT 'x, y', k int PRIMARY KEY);")["a"]
        self.assertEqual([(c.name, c.type, c.nullable) for c in t.columns],
                         [("n", "numeric(10, 2)", False),
                          ("s", "character varying(20)", True),
                          ("k", "int", False)])

    def test_names_fold_quotes_comments_and_schema(self):  # verifies: REQ-DATAMODEL-900#CASE-3
        t = _tables('-- a comment; with a semicolon\n/* block ; */\n'
                    'CREATE TABLE IF NOT EXISTS public."Orders" (Id int PRIMARY KEY, '
                    '"Total" int); CREATE INDEX i ON public."Orders" (id);')
        self.assertEqual(list(t), ["Orders"])
        self.assertEqual([c.name for c in t["Orders"].columns], ["id", "Total"])

    def test_a_column_named_key_is_a_column_but_a_mysql_key_is_an_index(self):  # verifies: REQ-DATAMODEL-900#CASE-3
        t = _tables("CREATE TABLE a (key varchar(20) NOT NULL, n int, KEY idx_n (n), "
                    "UNIQUE KEY u (n), INDEX (n));")["a"]
        self.assertEqual([c.name for c in t.columns], ["key", "n"])
        self.assertEqual(t.columns[0].type, "varchar(20)")

    def test_unreadable_create_table_names_the_statement(self):  # verifies: REQ-DATAMODEL-900#CASE-4
        with self.assertRaisesRegex(ValueError, "CREATE TABLE.*AS SELECT"):
            parse_ddl("CREATE TABLE t AS SELECT 1;")

    def test_script_errors_are_explicit(self):  # verifies: REQ-DATAMODEL-900#CASE-4
        for sql, msg in (("SELECT 1;", "no CREATE TABLE"),
                         ("CREATE TABLE a (x int); CREATE TABLE a (y int);", "twice"),
                         ("ALTER TABLE ghost ADD FOREIGN KEY (x) REFERENCES a (x);", "ghost")):
            with self.assertRaisesRegex(ValueError, msg):
                parse_ddl(sql)


# the test set: every table of the three fixtures with the role a modeller expects
EXPECTED = {
    "shop_demo.sql": {
        "fact_order_line": "fact", "dim_customer": "dimension", "dim_product": "dimension",
        "dim_date": "dimension", "dim_category": "dimension", "stg_payments": "unknown"},
    "shop_clean.sql": {
        "fact_order_line": "fact", "fact_payment": "fact", "dim_customer": "dimension",
        "dim_product": "dimension", "dim_date": "dimension"},
    "shop_noprefix.sql": {
        "sales": "fact", "customers": "dimension", "products": "dimension",
        "calendar": "dimension", "promotions": "dimension", "product_promotion": "bridge"},
}


class TestClassify(unittest.TestCase):
    """REQ-DATAMODEL-902: each table gets a role, a confidence and a written reason."""

    def test_at_least_90_percent_of_the_test_set_is_classified_correctly(self):  # verifies: REQ-DATAMODEL-902#CASE-1
        right = total = 0
        for fixture, expected in EXPECTED.items():
            got = classify_tables(parse_ddl(_read(fixture)))
            self.assertEqual(sorted(got), sorted(expected), fixture)
            for name, role in expected.items():
                total += 1
                right += got[name].role == role
        self.assertGreaterEqual(right / float(total), 0.9, "%d of %d" % (right, total))

    def test_structure_alone_classifies_a_schema_with_no_prefixes(self):  # verifies: REQ-DATAMODEL-902#CASE-2
        got = classify_tables(parse_ddl(_read("shop_noprefix.sql")))
        self.assertEqual(got["sales"].role, "fact")
        self.assertEqual(got["customers"].role, "dimension")
        self.assertNotIn("name prefix", got["sales"].reason)

    def test_every_classification_carries_a_reason_and_a_confidence(self):  # verifies: REQ-DATAMODEL-902#CASE-3
        for fixture in EXPECTED:
            for name, c in classify_tables(parse_ddl(_read(fixture))).items():
                self.assertTrue(c.reason.strip(), name)
                self.assertTrue(0.0 <= c.confidence <= 1.0, name)

    def test_a_table_with_no_evidence_is_unknown_with_zero_confidence(self):  # verifies: REQ-DATAMODEL-902#CASE-4
        c = classify_tables(parse_ddl("CREATE TABLE notes (id int PRIMARY KEY, body text);"))["notes"]
        self.assertEqual((c.role, c.confidence), ("unknown", 0.0))
        self.assertIn("not enough evidence", c.reason)

    def test_staging_prefix_is_unknown_whatever_its_shape(self):  # verifies: REQ-DATAMODEL-902#CASE-4
        sql = ("CREATE TABLE a (k int PRIMARY KEY); CREATE TABLE b (k int PRIMARY KEY);"
               "CREATE TABLE stg_x (a int REFERENCES a (k), b int REFERENCES b (k), amount numeric);")
        c = classify_tables(parse_ddl(sql))["stg_x"]
        self.assertEqual(c.role, "unknown")
        self.assertIn("staging", c.reason)

    def test_node_is_coloured_by_role_and_legend_lists_only_roles_in_use(self):  # verifies: REQ-DATAMODEL-902#CASE-5
        spec = graph_from_tables(parse_ddl(_read("shop_clean.sql")))
        self.assertEqual({n["fill"] for n in spec["nodes"]}, {"fact", "dimension"})
        self.assertEqual(sorted(spec["roles"]), ["dimension", "fact"])
        self.assertIn("fact", spec["nodes"][3]["label"])


def _review(sql):
    """[(table, rule)] the review finds in a DDL script."""
    tables = parse_ddl(sql)
    return [(i.table, i.rule) for i in review_tables(tables, classify_tables(tables))]


_DIM = "CREATE TABLE dim_a (a_key serial PRIMARY KEY, name varchar(20));"
_DIMS = _DIM + "CREATE TABLE dim_b (b_key serial PRIMARY KEY, label varchar(20));"
_FACT_FKS = "d1 int REFERENCES dim_a (a_key), d2 int REFERENCES dim_b (b_key), amount numeric"
# a keyed fact over dim_a twice: enough structure to be a fact, so only dim_a is under test
_FACT_ON_A = ("CREATE TABLE fact_s (s_key serial PRIMARY KEY, d1 int REFERENCES dim_a, "
              "d2 int REFERENCES dim_a, amount numeric);")


class TestReview(unittest.TestCase):
    """REQ-DATAMODEL-903: each rule fires on its problem and stays silent without it."""

    def test_every_planted_problem_is_found(self):  # verifies: REQ-DATAMODEL-903#CASE-1
        self.assertEqual(sorted(_review(_read("shop_demo.sql"))),
                         [("dim_category", "snowflake"), ("dim_customer", "scd2"),
                          ("dim_product", "surrogate-key"), ("stg_payments", "orphan-fk")])

    def test_clean_schema_raises_no_alarm(self):  # verifies: REQ-DATAMODEL-903#CASE-2
        self.assertEqual(_review(_read("shop_clean.sql")), [])

    def test_grain_fires_on_a_fact_without_primary_key(self):  # verifies: REQ-DATAMODEL-903#CASE-3
        self.assertEqual(_review(_DIMS + "CREATE TABLE fact_s (%s);" % _FACT_FKS),
                         [("fact_s", "grain")])

    def test_grain_is_silent_when_the_fact_has_a_key(self):  # verifies: REQ-DATAMODEL-903#CASE-3
        sql = _DIMS + "CREATE TABLE fact_s (s_key serial PRIMARY KEY, %s);" % _FACT_FKS
        self.assertEqual(_review(sql), [])

    def test_surrogate_key_fires_on_source_id_composite_and_missing_key(self):  # verifies: REQ-DATAMODEL-903#CASE-4
        for ddl in ("CREATE TABLE dim_a (a_id int PRIMARY KEY, name varchar(20));",
                    "CREATE TABLE dim_a (x int, y int, name varchar(20), PRIMARY KEY (x, y));",
                    "CREATE TABLE dim_a (x int, name varchar(20));"):
            self.assertIn(("dim_a", "surrogate-key"), _review(ddl + _FACT_ON_A), ddl)

    def test_surrogate_key_is_silent_for_key_and_sk_columns(self):  # verifies: REQ-DATAMODEL-903#CASE-4
        for col in ("a_key", "a_sk", "key"):
            ddl = "CREATE TABLE dim_a (%s serial PRIMARY KEY, name varchar(20));" % col
            self.assertEqual(_review(ddl + _FACT_ON_A), [], col)

    def test_scd2_fires_on_changing_attributes_without_history_columns(self):  # verifies: REQ-DATAMODEL-903#CASE-5
        ddl = "CREATE TABLE dim_a (a_key serial PRIMARY KEY, city varchar(20));"
        self.assertIn(("dim_a", "scd2"), _review(ddl + _FACT_ON_A))

    def test_scd2_fires_on_half_a_history(self):  # verifies: REQ-DATAMODEL-903#CASE-5
        ddl = "CREATE TABLE dim_a (a_key serial PRIMARY KEY, name varchar(20), valid_from date);"
        self.assertIn(("dim_a", "scd2"), _review(ddl + _FACT_ON_A))

    def test_scd2_is_silent_with_history_or_stable_attributes(self):  # verifies: REQ-DATAMODEL-903#CASE-5
        for cols in ("city varchar(20), valid_from date, valid_to date", "name varchar(20)"):
            ddl = "CREATE TABLE dim_a (a_key serial PRIMARY KEY, %s);" % cols
            self.assertEqual(_review(ddl + _FACT_ON_A), [], cols)

    def test_orphan_fk_fires_on_missing_table_and_missing_column(self):  # verifies: REQ-DATAMODEL-903#CASE-6
        self.assertEqual(_review("CREATE TABLE t (x int REFERENCES ghost (id));"),
                         [("t", "orphan-fk")])
        sql = _DIM + "CREATE TABLE t (x int REFERENCES dim_a (nope));"
        self.assertIn(("t", "orphan-fk"), _review(sql))

    def test_orphan_fk_is_silent_when_the_target_exists(self):  # verifies: REQ-DATAMODEL-903#CASE-6
        self.assertNotIn("orphan-fk", [r for _, r in _review(_read("shop_clean.sql"))])

    def test_snowflake_fires_on_a_sub_dimension(self):  # verifies: REQ-DATAMODEL-903#CASE-7
        sql = ("CREATE TABLE dim_c (c_key serial PRIMARY KEY, c_name varchar(20));"
               "CREATE TABLE dim_a (a_key serial PRIMARY KEY, name varchar(20), "
               "c_key int REFERENCES dim_c (c_key));"
               "CREATE TABLE dim_b (b_key serial PRIMARY KEY, label varchar(20));"
               "CREATE TABLE fact_s (s_key serial PRIMARY KEY, d1 int REFERENCES dim_a, "
               "d2 int REFERENCES dim_b, amount numeric);")
        self.assertEqual(_review(sql), [("dim_c", "snowflake")])

    def test_snowflake_deep_chain_is_called_deep(self):  # verifies: REQ-DATAMODEL-903#CASE-7
        sql = ("CREATE TABLE dim_e (e_key serial PRIMARY KEY, e_name varchar(20));"
               "CREATE TABLE dim_c (c_key serial PRIMARY KEY, c_name varchar(20), "
               "e_key int REFERENCES dim_e (e_key));"
               "CREATE TABLE dim_a (a_key serial PRIMARY KEY, name varchar(20), "
               "c_key int REFERENCES dim_c (c_key));"
               "CREATE TABLE dim_b (b_key serial PRIMARY KEY, label varchar(20));"
               "CREATE TABLE fact_s (s_key serial PRIMARY KEY, d1 int REFERENCES dim_a, "
               "d2 int REFERENCES dim_b, amount numeric);")
        tables = parse_ddl(sql)
        issues = {i.table: i.message for i in review_tables(tables, classify_tables(tables))}
        self.assertIn("deep snowflake", issues["dim_e"])
        self.assertNotIn("deep", issues["dim_c"])

    def test_snowflake_is_silent_for_a_dimension_two_dimensions_share(self):  # verifies: REQ-DATAMODEL-903#CASE-7
        sql = ("CREATE TABLE dim_c (c_key serial PRIMARY KEY, c_name varchar(20));"
               "CREATE TABLE dim_a (a_key serial PRIMARY KEY, name varchar(20), "
               "c_key int REFERENCES dim_c (c_key));"
               "CREATE TABLE dim_b (b_key serial PRIMARY KEY, label varchar(20), "
               "c_key int REFERENCES dim_c (c_key));"
               "CREATE TABLE fact_s (s_key serial PRIMARY KEY, d1 int REFERENCES dim_a, "
               "d2 int REFERENCES dim_b, amount numeric);")
        self.assertEqual(_review(sql), [])

    def test_every_issue_has_a_written_reason(self):  # verifies: REQ-DATAMODEL-904#CASE-1
        tables = parse_ddl(_read("shop_demo.sql"))
        for issue in review_tables(tables, classify_tables(tables)):
            self.assertGreater(len(issue.message.split()), 4, issue.rule)

    def test_issues_become_amber_notes_joined_to_their_table(self):  # verifies: REQ-DATAMODEL-904#CASE-2
        spec = graph_from_tables(parse_ddl(_read("shop_demo.sql")))
        notes = [n for n in spec["nodes"] if n["fill"] == "review note"]
        self.assertEqual(len(notes), 4)
        joined = {(e["src"], e["dst"]) for e in spec["edges"] if e.get("dashed")}
        self.assertIn(("stg_payments", notes[-1]["id"]), joined)
        self.assertEqual(spec["roles"]["review note"], "yellow")

    def test_clean_schema_draws_no_notes_and_no_note_legend(self):  # verifies: REQ-DATAMODEL-904#CASE-3
        spec = graph_from_tables(parse_ddl(_read("shop_clean.sql")))
        self.assertNotIn("review note", spec["roles"])
        self.assertEqual([n for n in spec["nodes"] if n["fill"] == "review note"], [])


class TestGraph(unittest.TestCase):
    """REQ-DATAMODEL-901: one node per table, one edge per foreign-key relationship."""

    def test_one_node_per_table_one_edge_per_fk(self):  # verifies: REQ-DATAMODEL-901#CASE-1
        spec = graph_from_tables(parse_ddl(_read("shop_demo.sql")))
        self.assertEqual(len([n for n in spec["nodes"] if n["fill"] != "review note"]), 6)
        pairs = sorted((e["src"], e["dst"]) for e in spec["edges"] if not e.get("dashed"))
        self.assertEqual(pairs, [("dim_product", "dim_category"),
                                 ("fact_order_line", "dim_customer"),
                                 ("fact_order_line", "dim_date"),
                                 ("fact_order_line", "dim_product")])

    def test_two_fks_to_one_table_make_one_labelled_edge(self):  # verifies: REQ-DATAMODEL-901#CASE-1
        spec = graph_from_tables(parse_ddl(
            "CREATE TABLE d (k int PRIMARY KEY);"
            "CREATE TABLE f (a int REFERENCES d (k), b int REFERENCES d (k));"))
        fk_edges = [e for e in spec["edges"] if not e.get("dashed")]
        self.assertEqual([(e["src"], e["dst"], e["label"]) for e in fk_edges],
                         [("f", "d", "a, b")])

    def test_foreign_key_to_missing_table_is_listed_not_drawn(self):  # verifies: REQ-DATAMODEL-901#CASE-2
        tables = parse_ddl(_read("shop_demo.sql"))
        spec = graph_from_tables(tables)
        self.assertNotIn("stg_payments", [e["src"] for e in spec["edges"] if not e.get("dashed")])
        self.assertEqual([(t.name, fk.ref_table) for t, fk in unresolved_fks(tables)],
                         [("stg_payments", "orders")])

    def test_clean_schema_has_nothing_unresolved(self):  # verifies: REQ-DATAMODEL-901#CASE-2
        self.assertEqual(unresolved_fks(parse_ddl(_read("shop_clean.sql"))), [])


class TestScene(unittest.TestCase):
    """REQ-DATAMODEL-901: the graph renders through the existing gates, byte-stable."""

    def _render(self, name, out):
        return scene_from_ddl(os.path.join(DATA, name), out)

    def test_demo_and_clean_render_through_every_gate(self):  # verifies: REQ-DATAMODEL-901#CASE-3
        with tempfile.TemporaryDirectory() as out:
            for name in ("shop_demo.sql", "shop_clean.sql"):
                for path in self._render(name, out):
                    self.assertTrue(os.path.getsize(path) > 0, path)

    def test_same_schema_gives_identical_files(self):  # verifies: REQ-DATAMODEL-901#CASE-4
        blobs = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as out:
                path = self._render("shop_demo.sql", out)[0]
                with open(path, "rb") as fh:
                    blobs.append(fh.read())
        self.assertEqual(blobs[0], blobs[1])

    def test_bad_ddl_error_names_the_file(self):  # verifies: REQ-DATAMODEL-900#CASE-4
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "bad.sql")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("CREATE TABLE t AS SELECT 1;")
            with self.assertRaisesRegex(ValueError, "bad.sql"):
                scene_from_ddl(path, d)


class TestCli(unittest.TestCase):
    """REQ-DATAMODEL-901: the data-model verb draws a schema from the command line."""

    def test_data_model_verb_writes_both_files(self):  # verifies: REQ-DATAMODEL-901#CASE-3
        with tempfile.TemporaryDirectory() as out, contextlib.redirect_stdout(io.StringIO()):
            code = cli.main(["data-model", "--from-ddl",
                             os.path.join(DATA, "shop_demo.sql"), "-o", out])
            self.assertEqual(code, 0)
            self.assertEqual(sorted(os.listdir(out)), ["shop_demo.excalidraw", "shop_demo.html"])

    def test_data_model_without_input_is_a_usage_error(self):  # verifies: REQ-DATAMODEL-901#CASE-3
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(["data-model"]), 2)


class TestCapability(unittest.TestCase):
    """ARCH-DATAMODEL-036: the command draws, reviews and refuses end to end."""

    def _notes(self, name):
        with tempfile.TemporaryDirectory() as out, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(["data-model", "--from-ddl",
                                       os.path.join(DATA, name), "-o", out]), 0)
            with open(os.path.join(out, name.replace(".sql", ".excalidraw")), encoding="utf-8") as fh:
                scene = json.load(fh)
        # amber review-note boxes; the 18px legend swatch is the same colour but not a note
        return [e for e in scene["elements"]
                if e["type"] == "rectangle" and e.get("backgroundColor") == "#ffec99"
                and e["width"] > 40]

    def test_demo_schema_is_drawn_with_four_amber_notes(self):  # verifies: ARCH-DATAMODEL-036#CASE-1
        self.assertEqual(len(self._notes("shop_demo.sql")), 4)

    def test_clean_schema_is_drawn_with_no_note_and_no_note_legend(self):  # verifies: ARCH-DATAMODEL-036#CASE-2
        self.assertEqual(self._notes("shop_clean.sql"), [])

    def test_unreadable_ddl_exits_non_zero_names_the_file_and_writes_nothing(self):  # verifies: ARCH-DATAMODEL-036#CASE-3
        with tempfile.TemporaryDirectory() as d:
            src, out = os.path.join(d, "bad.sql"), os.path.join(d, "out")
            os.mkdir(out)
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("CREATE TABLE t AS SELECT 1;")
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                code = cli.main(["data-model", "--from-ddl", src, "-o", out])
            self.assertEqual(code, 1)
            self.assertIn("bad.sql", err.getvalue())
            self.assertEqual(os.listdir(out), [])


if __name__ == "__main__":
    unittest.main()
