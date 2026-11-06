#!/usr/bin/env python3
# tested-by: REQ-DATAMODEL-900  # tested-by: REQ-DATAMODEL-901  # tested-by: REQ-DATAMODEL-902  # tested-by: REQ-DATAMODEL-903  # tested-by: REQ-DATAMODEL-904  # tested-by: ARCH-DATAMODEL-036  # tested-by: REQ-DATAMODEL-905  # tested-by: REQ-DATAMODEL-906  # tested-by: REQ-DATAMODEL-907  # tested-by: REQ-DATAMODEL-908  # tested-by: REQ-DATAMODEL-909  # tested-by: REQ-DATAMODEL-910  # tested-by: REQ-DATAMODEL-911  # tested-by: REQ-DATAMODEL-912  # tested-by: REQ-DATAMODEL-913
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
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "examples", "data_model")
sys.path.insert(0, HERE)

from excalidraw_engine import cli  # noqa: E402
from excalidraw_engine import explain  # noqa: E402
from excalidraw_engine.classify import classify_tables  # noqa: E402
from excalidraw_engine.data_model import (  # noqa: E402
    NOTE, graph_from_tables, scene_from_dbt, scene_from_ddl, unresolved_fks)
from excalidraw_engine.dbt import read_dbt  # noqa: E402
from excalidraw_engine.ddl import Column, ForeignKey, Table, parse_ddl  # noqa: E402
from excalidraw_engine.mapping import mapping_markdown  # noqa: E402
from excalidraw_engine.miniyaml import parse_yaml  # noqa: E402
from excalidraw_engine.review import review_tables  # noqa: E402
from excalidraw_engine.roles import parse_roles  # noqa: E402


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
    "order_process.sql": {
        "calendar": "dimension", "customer": "dimension", "department": "dimension",
        "product_category": "dimension", "product": "dimension", "warehouse": "dimension",
        "promotion": "dimension", "segment": "dimension", "order_line": "fact",
        "order_fulfilment": "fact", "inventory_snapshot": "fact",
        "customer_segment": "bridge", "promotion_coverage": "fact"},
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

    def test_a_tie_between_two_roles_is_unknown_with_zero_confidence(self):  # verifies: REQ-DATAMODEL-902#CASE-4
        # `rates` is referenced by another table (dimension +2, no keys out +1) and holds
        # three numbers (fact +3): fact 3, dimension 3
        sql = ("CREATE TABLE rates (rate_key serial PRIMARY KEY, buy numeric, sell numeric, "
               "mid numeric);"
               "CREATE TABLE trades (trade_key serial PRIMARY KEY, "
               "rate_key int REFERENCES rates (rate_key));")
        got = classify_tables(parse_ddl(sql))["rates"]
        self.assertEqual((got.role, got.confidence), ("unknown", 0.0))
        self.assertIn("fact and dimension tie", got.reason)

    @staticmethod
    def _orders_table(types):
        """A dbt-style `orders` that points at `customers`; `types` maps column -> type."""
        orders = Table("orders")
        orders.columns = [Column(n, types.get(n, "")) for n in
                          ("order_id", "customer_id", "status", "amount", "coupon_amount")]
        orders.primary_key = ["order_id"]
        orders.foreign_keys = [ForeignKey(["customer_id"], "customers", ["customer_id"])]
        customers = Table("customers")
        customers.columns = [Column("customer_id", "")]
        customers.primary_key = ["customer_id"]
        return [customers, orders]

    def test_an_untyped_table_is_judged_from_its_column_names_and_says_so(self):  # verifies: REQ-DATAMODEL-902#CASE-7
        got = classify_tables(self._orders_table({}))["orders"]
        self.assertEqual(got.role, "fact")
        self.assertIn("amount, coupon_amount (guessed from the names", got.reason)

    def test_a_declared_type_is_never_overridden_by_a_name(self):  # verifies: REQ-DATAMODEL-902#CASE-7
        typed = {"status": "varchar", "amount": "text", "coupon_amount": "text"}
        got = classify_tables(self._orders_table(typed))["orders"]
        self.assertNotIn("guessed", got.reason)
        self.assertNotEqual(got.role, "fact")

    def test_keys_only_joining_three_tables_is_a_factless_fact_and_two_is_a_bridge(self):  # verifies: REQ-DATAMODEL-902#CASE-1
        dims = "".join("CREATE TABLE d%d (k int PRIMARY KEY, name varchar(10));" % i for i in (1, 2, 3))
        two = classify_tables(parse_ddl(dims + "CREATE TABLE link (a int REFERENCES d1 (k), "
                                        "b int REFERENCES d2 (k), PRIMARY KEY (a, b));"))
        three = classify_tables(parse_ddl(dims + "CREATE TABLE cover (a int REFERENCES d1 (k), "
                                          "b int REFERENCES d2 (k), c int REFERENCES d3 (k), "
                                          "PRIMARY KEY (a, b, c));"))
        self.assertEqual(two["link"].role, "bridge")
        self.assertEqual(three["cover"].role, "fact")
        self.assertIn("factless fact", three["cover"].reason)

    def test_node_is_coloured_by_role_and_legend_lists_only_roles_in_use(self):  # verifies: REQ-DATAMODEL-902#CASE-5
        spec = graph_from_tables(parse_ddl(_read("shop_clean.sql")))
        keys = {explain.role_key("fact"), explain.role_key("dimension")}
        self.assertEqual({n["fill"] for n in spec["nodes"]}, keys)
        self.assertEqual(set(spec["roles"]), keys)
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


_FACT_ON_P = ("CREATE TABLE fact_s (s_key serial PRIMARY KEY, d1 int REFERENCES dim_p, "
              "d2 int REFERENCES dim_p, amount numeric);")


class TestReview(unittest.TestCase):
    """REQ-DATAMODEL-903: each rule fires on its problem and stays silent without it."""

    def test_the_order_process_gets_exactly_its_three_findings(self):  # verifies: REQ-DATAMODEL-903#CASE-1  # verifies: REQ-DATAMODEL-903#CASE-2
        # modelled by hand from a business description before the tool was run on it
        self.assertEqual(sorted(_review(_read("order_process.sql"))),
                         [("department", "snowflake"), ("product_category", "snowflake"),
                          ("warehouse", "surrogate-key")])

    def test_scd2_ignores_key_columns_and_the_entitys_own_label(self):  # verifies: REQ-DATAMODEL-903#CASE-5
        # department_key is a key, and department_name is the department's own name: neither
        # is an attribute that changes, though both contain a word the rule listens for
        sql = ("CREATE TABLE department (department_key serial PRIMARY KEY, "
               "department_name varchar(40));"
               "CREATE TABLE dim_p (p_key serial PRIMARY KEY, name varchar(20), "
               "department_key int REFERENCES department (department_key));") + _FACT_ON_P
        self.assertNotIn("scd2", [rule for _, rule in _review(sql)])

    def test_scd2_needs_two_places_but_only_one_strong_name(self):  # verifies: REQ-DATAMODEL-903#CASE-5
        def fires(cols):
            sql = ("CREATE TABLE dim_a (a_key serial PRIMARY KEY, %s);" % cols) + _FACT_ON_A
            return ("dim_a", "scd2") in _review(sql)
        self.assertFalse(fires("country varchar(20)"))              # a warehouse does not move
        self.assertTrue(fires("city varchar(20), country varchar(20)"))
        self.assertTrue(fires("email varchar(40)"))

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
        ddl = "CREATE TABLE dim_a (a_key serial PRIMARY KEY, address varchar(20));"
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
        notes = [n for n in spec["nodes"] if n["fill"] == NOTE]
        self.assertEqual(len(notes), 4)
        joined = {(e["src"], e["dst"]) for e in spec["edges"] if e.get("dashed")}
        self.assertIn(("stg_payments", notes[-1]["id"]), joined)
        self.assertEqual(spec["roles"][NOTE], "yellow")

    def test_clean_schema_draws_no_notes_and_no_note_legend(self):  # verifies: REQ-DATAMODEL-904#CASE-3
        spec = graph_from_tables(parse_ddl(_read("shop_clean.sql")))
        self.assertNotIn(NOTE, spec["roles"])
        self.assertEqual([n for n in spec["nodes"] if n["fill"] == NOTE], [])


class TestGraph(unittest.TestCase):
    """REQ-DATAMODEL-901: one node per table, one edge per foreign-key relationship."""

    def test_one_node_per_table_one_edge_per_fk(self):  # verifies: REQ-DATAMODEL-901#CASE-1
        spec = graph_from_tables(parse_ddl(_read("shop_demo.sql")))
        self.assertEqual(len([n for n in spec["nodes"] if n["fill"] != NOTE]), 6)
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

    def test_a_ddl_drawing_takes_only_its_own_options(self):
        with tempfile.TemporaryDirectory() as out:
            path = os.path.join(DATA, "shop_demo.sql")
            for bad in ({"mapping_path": os.path.join(out, "m.md")}, {"draw_lineage": True},
                        {"no_such_option": 1}):
                with self.assertRaises(TypeError):
                    scene_from_ddl(path, out, **bad)
            self.assertEqual(os.listdir(out), [])       # a refused call wrote nothing

    def test_a_dbt_drawing_also_takes_lineage_and_a_mapping_path(self):
        with tempfile.TemporaryDirectory() as out:
            target = os.path.join(out, "m.md")
            paths = scene_from_dbt(DBT, out, draw_lineage=True, mapping_path=target, columns=True)
            self.assertEqual(paths[-1], target)
            self.assertTrue(all(os.path.getsize(p) > 0 for p in paths))

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


ROLES_FILE = os.path.join(DATA, "shop_demo.roles.yml")


PK, FK = explain.ICON["pk"], explain.ICON["fk"]


def _node(spec, table):
    return next(n for n in spec["nodes"] if n["id"] == table)


class TestColumns(unittest.TestCase):
    """REQ-DATAMODEL-905: --columns lists each table's columns, off by default."""

    def test_columns_are_off_by_default(self):  # verifies: REQ-DATAMODEL-905#CASE-1
        spec = graph_from_tables(parse_ddl(_read("shop_demo.sql")))
        self.assertEqual(_node(spec, "dim_date")["label"].split("\n"),
                         ["dim_date", explain.ICON["dimension"] + " dimension · 100%"])

    def test_columns_listed_in_order_with_key_marks(self):  # verifies: REQ-DATAMODEL-905#CASE-2
        spec = graph_from_tables(parse_ddl(_read("shop_demo.sql")), columns=True)
        self.assertEqual(_node(spec, "fact_order_line")["label"].split("\n")[2:],
                         [PK + " PK order_line_key", FK + " FK date_key",
                          FK + " FK customer_key", FK + " FK product_id",
                          "quantity", "unit_price", "line_amount"])

    def test_a_key_that_is_both_primary_and_foreign_carries_both_marks(self):  # verifies: REQ-DATAMODEL-905#CASE-2
        spec = graph_from_tables(parse_ddl(
            "CREATE TABLE p (k int PRIMARY KEY);"
            "CREATE TABLE c (k int PRIMARY KEY REFERENCES p (k), v text);"), columns=True)
        self.assertIn(PK + " PK " + FK + " FK k", _node(spec, "c")["label"].split("\n"))

    def test_columns_flag_renders_through_every_gate(self):  # verifies: REQ-DATAMODEL-905#CASE-3
        with tempfile.TemporaryDirectory() as out, contextlib.redirect_stdout(io.StringIO()):
            code = cli.main(["data-model", "--from-ddl", os.path.join(DATA, "shop_demo.sql"),
                             "--columns", "-o", out])
            self.assertEqual(code, 0)
            with open(os.path.join(out, "shop_demo.excalidraw"), encoding="utf-8") as fh:
                texts = [e["text"] for e in json.load(fh)["elements"] if e["type"] == "text"]
        self.assertTrue(any(PK + " PK order_line_key" in t.split("\n") for t in texts))


class TestRoles(unittest.TestCase):
    """REQ-DATAMODEL-906: a roles file overrides the classifier, and says so."""

    def test_flat_lines_comments_and_quotes_are_read(self):  # verifies: REQ-DATAMODEL-906#CASE-1
        got = parse_roles('# note\na: fact\n"b c": Dimension   # trailing\n\n\'d\': bridge\n')
        self.assertEqual(got, {"a": "fact", "b c": "dimension", "d": "bridge"})

    def test_anything_richer_or_wrong_names_the_line(self):  # verifies: REQ-DATAMODEL-906#CASE-2
        for text, msg in (("a: fact\nb:\n  c: dimension\n", "line 2"),
                          ("a: fact\n- b\n", "line 2"),
                          ("a: hub\n", "line 1.*not a role"),
                          ("a: fact\na: dimension\n", "line 2.*twice")):
            with self.assertRaisesRegex(ValueError, msg):
                parse_roles(text)

    def test_override_replaces_the_role_and_keeps_what_the_rules_said(self):  # verifies: REQ-DATAMODEL-906#CASE-3
        got = classify_tables(parse_ddl(_read("shop_demo.sql")),
                              {"stg_payments": "fact"})["stg_payments"]
        self.assertEqual((got.role, got.confidence, got.overridden), ("fact", 1.0, True))
        self.assertIn("rules had said unknown", got.reason)

    def test_tables_not_named_keep_the_rules_answer(self):  # verifies: REQ-DATAMODEL-906#CASE-3
        got = classify_tables(parse_ddl(_read("shop_demo.sql")), {"stg_payments": "fact"})
        self.assertFalse(got["dim_date"].overridden)
        self.assertEqual(got["dim_date"].role, "dimension")

    def test_a_table_the_schema_lacks_is_an_error(self):  # verifies: REQ-DATAMODEL-906#CASE-4
        with self.assertRaisesRegex(ValueError, "ghost.*does not define"):
            classify_tables(parse_ddl(_read("shop_demo.sql")), {"ghost": "fact"})

    def test_the_override_feeds_the_review_and_the_label(self):  # verifies: REQ-DATAMODEL-906#CASE-5
        tables = parse_ddl(_read("shop_demo.sql"))
        before = [(i.table, i.rule) for i in review_tables(tables, classify_tables(tables))]
        self.assertIn(("dim_product", "surrogate-key"), before)
        spec = graph_from_tables(tables, overrides={"dim_product": "unknown"})
        self.assertNotIn("surrogate-key", " ".join(n["label"] for n in spec["nodes"]))
        self.assertIn("unknown · set by you", _node(spec, "dim_product")["label"])

    def test_roles_file_errors_name_the_roles_file(self):  # verifies: REQ-DATAMODEL-906#CASE-6
        with tempfile.TemporaryDirectory() as d:
            for text, msg in (("a: hub\n", "line 1"), ("ghost: fact\n", "ghost")):
                path = os.path.join(d, "r.yml")
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(text)
                with self.assertRaisesRegex(ValueError, "r.yml.*" + msg):
                    scene_from_ddl(os.path.join(DATA, "shop_demo.sql"), d, roles_path=path)

    def test_roles_flag_renders_and_marks_the_override(self):  # verifies: REQ-DATAMODEL-906#CASE-6
        with tempfile.TemporaryDirectory() as out, contextlib.redirect_stdout(io.StringIO()):
            code = cli.main(["data-model", "--from-ddl", os.path.join(DATA, "shop_demo.sql"),
                             "--roles", ROLES_FILE, "-o", out])
            self.assertEqual(code, 0)
            with open(os.path.join(out, "shop_demo.excalidraw"), encoding="utf-8") as fh:
                texts = [e["text"] for e in json.load(fh)["elements"] if e["type"] == "text"]
        self.assertTrue(any("fact · set by you" in t for t in texts))


class TestConfidence(unittest.TestCase):
    """REQ-DATAMODEL-902: confidence rests on the lead AND on how much evidence there is."""

    def _conf(self, fixture, table):
        return classify_tables(parse_ddl(_read(fixture)))[table].confidence

    def test_strong_evidence_and_no_rival_reads_one(self):  # verifies: REQ-DATAMODEL-902#CASE-6
        self.assertEqual(self._conf("shop_demo.sql", "fact_order_line"), 1.0)
        self.assertEqual(self._conf("shop_demo.sql", "dim_date"), 1.0)

    def test_thin_evidence_or_a_close_rival_reads_lower(self):  # verifies: REQ-DATAMODEL-902#CASE-6
        strong = self._conf("shop_demo.sql", "dim_date")
        self.assertLess(self._conf("shop_noprefix.sql", "calendar"), strong)    # few points
        self.assertLess(self._conf("shop_noprefix.sql", "products"), strong)    # a rival role
        self.assertLess(self._conf("shop_noprefix.sql", "product_promotion"), 0.5)  # lead of 1


class TestNodeWidth(unittest.TestCase):
    """A node's `max_chars` sets its label's wrap width; the default is unchanged."""

    def _lines(self, **extra):
        from excalidraw_engine.scene import Scene
        s = Scene(seed=1)
        s.pack([dict(id="a", label="one two three four five six seven eight nine ten eleven", **extra)])
        return max(len(ln) for e in s.elements if e["type"] == "text"
                   for ln in e["text"].split("\n"))

    def test_default_wraps_at_22_and_max_chars_widens_it(self):
        self.assertLessEqual(self._lines(), 22)
        wide = self._lines(max_chars=40)
        self.assertGreater(wide, 22)
        self.assertLessEqual(wide, 40)

    def test_review_notes_ask_for_the_wide_wrap(self):  # verifies: REQ-DATAMODEL-904#CASE-2
        spec = graph_from_tables(parse_ddl(_read("shop_demo.sql")))
        notes = [n for n in spec["nodes"] if n["fill"] == NOTE]
        self.assertTrue(notes and all(n["max_chars"] == 40 for n in notes))


class TestFitTextKeepsLines(unittest.TestCase):
    """A newline in a label is a line break the author chose, not a space."""

    def test_each_line_is_wrapped_on_its_own(self):
        from excalidraw_engine.geometry import fit_text
        text, _, _ = fit_text("name\nrole · 100%\nPK key\nFK other_key", max_chars=40)
        self.assertEqual(text.split("\n"), ["name", "role · 100%", "PK key", "FK other_key"])

    def test_text_without_newlines_wraps_as_before(self):
        from excalidraw_engine.geometry import fit_text
        text, _, _ = fit_text("one two three four five six", max_chars=10)
        self.assertEqual(text.split("\n"), ["one two", "three four", "five six"])


DBT = os.path.join(DATA, "dbt_shop")


class TestMiniYaml(unittest.TestCase):
    """REQ-DATAMODEL-908: the YAML subset a dbt schema.yml uses, and a refusal for the rest."""

    def test_nested_maps_and_lists_of_maps(self):  # verifies: REQ-DATAMODEL-908#CASE-1
        got = parse_yaml("a:\n  b: 1\n  c:\n    - x\n    - y\nmodels:\n  - name: m\n"
                         "    columns:\n      - name: c1\n      - name: c2\n  - name: n\n")
        self.assertEqual(got["a"], {"b": 1, "c": ["x", "y"]})
        self.assertEqual(got["models"][0]["columns"], [{"name": "c1"}, {"name": "c2"}])
        self.assertEqual(got["models"][1], {"name": "n"})

    def test_a_list_at_the_same_indent_as_its_key(self):  # verifies: REQ-DATAMODEL-908#CASE-1
        self.assertEqual(parse_yaml("tests:\n- unique\n- not_null\nnext: 1\n"),
                         {"tests": ["unique", "not_null"], "next": 1})

    def test_scalars_and_flow_collections(self):  # verifies: REQ-DATAMODEL-908#CASE-2
        got = parse_yaml("""a: true\nb: ~\nc: 3\nd: 2.5\ne: 'it''s'\nf: "x\\ty"\ng: ref('m')\n"""
                         "h: [1, 'a, b', {k: v}]\ni: {x: 1, y: [2]}\nj: {{ doc('d') }}\n")
        self.assertEqual((got["a"], got["b"], got["c"], got["d"]), (True, None, 3, 2.5))
        self.assertEqual((got["e"], got["f"], got["g"]), ("it's", "x\ty", "ref('m')"))
        self.assertEqual(got["h"], [1, "a, b", {"k": "v"}])
        self.assertEqual(got["i"], {"x": 1, "y": [2]})
        self.assertEqual(got["j"], "{{ doc('d') }}")

    def test_block_scalars_comments_and_leading_marker(self):  # verifies: REQ-DATAMODEL-908#CASE-3
        got = parse_yaml("---\n# top\nd: >\n  one\n  two\ne: |\n  l1\n  l2\nf: 1  # trailing\n")
        self.assertEqual(got, {"d": "one two", "e": "l1\nl2", "f": 1})

    def test_anything_outside_the_subset_names_the_line(self):  # verifies: REQ-DATAMODEL-908#CASE-4
        for text, msg in (("a: &x 1\n", "line 1.*anchors"),
                          ("a:\n\t- 1\n", "line 2.*tab"),
                          ("a: 1\na: 2\n", "line 2.*twice"),
                          ("a: 1\nb\n", "line 2"),
                          ("a: 1\n---\nb: 2\n", "line 2.*several documents"),
                          ("a: 'open\n", "line 1.*unterminated")):
            with self.assertRaisesRegex(ValueError, msg):
                parse_yaml(text)


class TestReadDbt(unittest.TestCase):
    """REQ-DATAMODEL-907: a dbt project becomes tables, foreign keys and lineage."""

    def test_models_come_from_sql_and_schema_files_sorted(self):  # verifies: REQ-DATAMODEL-907#CASE-1
        tables, _ = read_dbt(DBT)
        self.assertEqual([t.name for t in tables],
                         ["customers", "orders", "stg_customers", "stg_orders", "stg_payments"])

    def test_unique_plus_not_null_is_the_primary_key(self):  # verifies: REQ-DATAMODEL-907#CASE-2
        t = {t.name: t for t in read_dbt(DBT)[0]}
        self.assertEqual(t["orders"].primary_key, ["order_id"])
        self.assertEqual(t["orders"].column("customer_id").nullable, False)
        self.assertEqual(t["orders"].column("amount").type, "numeric")

    def test_a_relationships_test_is_a_foreign_key(self):  # verifies: REQ-DATAMODEL-907#CASE-3
        t = {t.name: t for t in read_dbt(DBT)[0]}
        fk = t["orders"].foreign_keys
        self.assertEqual([(f.columns, f.ref_table, f.ref_columns) for f in fk],
                         [(["customer_id"], "customers", ["customer_id"])])

    def test_ref_gives_lineage_and_sources_comments_and_unknowns_do_not(self):  # verifies: REQ-DATAMODEL-907#CASE-4
        _, lineage = read_dbt(DBT)
        self.assertIn(("customers", "stg_orders"), lineage)
        self.assertIn(("orders", "stg_payments"), lineage)
        self.assertFalse([p for p in lineage if p[1] in ("raw", "customers") and p[0] == "orders"])
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "models"))
            with open(os.path.join(d, "models", "m.sql"), "w", encoding="utf-8") as fh:
                fh.write("{# ref('ghost') #}\n-- ref('ghost2')\nselect * from {{ ref('m') }} "
                         "join {{ ref('pkg', 'ghost3') }} on 1=1")
            self.assertEqual(read_dbt(d)[1], [])

    def test_lineage_is_drawn_dashed_unless_a_foreign_key_already_joins_the_pair(self):  # verifies: REQ-DATAMODEL-907#CASE-5
        tables, lineage = read_dbt(DBT)
        spec = graph_from_tables(tables, lineage=lineage)
        dashed = {(e["src"], e["dst"]) for e in spec["edges"] if e.get("dashed")}
        self.assertIn(("customers", "stg_orders"), dashed)
        both = graph_from_tables(tables, lineage=lineage + [("orders", "customers")])
        self.assertEqual(len([e for e in both["edges"]
                              if (e["src"], e["dst"]) == ("orders", "customers")]), 1)

    def test_a_broken_schema_file_and_an_empty_project_are_errors(self):  # verifies: REQ-DATAMODEL-907#CASE-6
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, "no dbt model"):
                read_dbt(d)
            os.makedirs(os.path.join(d, "models"))
            with open(os.path.join(d, "models", "schema.yml"), "w", encoding="utf-8") as fh:
                fh.write("models:\n  - name: a\n    columns: &x []\n")
            with self.assertRaisesRegex(ValueError, "schema.yml.*line 3"):
                read_dbt(d)

    def test_from_dbt_renders_through_every_gate_and_needs_exactly_one_input(self):  # verifies: REQ-DATAMODEL-907#CASE-7
        with tempfile.TemporaryDirectory() as out, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(["data-model", "--from-dbt", DBT, "-o", out]), 0)
            self.assertEqual(sorted(os.listdir(out)), ["dbt_shop.excalidraw", "dbt_shop.html"])
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(["data-model"]), 2)
            self.assertEqual(cli.main(["data-model", "--from-dbt", DBT, "--from-ddl", "x.sql"]), 2)


def _project(models, schema=""):
    """A throwaway dbt project in a temp dir: {model: sql} plus an optional schema.yml
    text. Returns (TemporaryDirectory, path); the caller keeps the first alive."""
    tmp = tempfile.TemporaryDirectory()
    root = os.path.join(tmp.name, "models")
    os.makedirs(root)
    for name, sql in models.items():
        with open(os.path.join(root, name + ".sql"), "w", encoding="utf-8") as fh:
            fh.write(sql)
    if schema:
        with open(os.path.join(root, "schema.yml"), "w", encoding="utf-8") as fh:
            fh.write(schema)
    return tmp, tmp.name


def _row(markdown, model, column):
    """The table row for `column` in the `model` section, or None."""
    section = markdown.split("## %s\n" % model)[1].split("\n## ")[0]
    return next((ln for ln in section.splitlines() if ln.startswith("| `%s` |" % column)), None)


class TestMapping(unittest.TestCase):
    """REQ-DATAMODEL-909: a source-to-target mapping that says when it cannot tell."""

    def setUp(self):
        self.md = mapping_markdown(DBT, title="dbt_shop")

    def test_plain_columns_are_traced_through_aliases_and_pass_through_ctes(self):  # verifies: REQ-DATAMODEL-909#CASE-1
        self.assertIn("| `customer_id` | `stg_customers.customer_id` | copy | unique, not_null |",
                      _row(self.md, "customers", "customer_id"))
        self.assertIn("`stg_orders.status` | copy", _row(self.md, "orders", "status"))

    def test_a_renamed_column_and_a_source_table_are_named(self):  # verifies: REQ-DATAMODEL-909#CASE-1
        self.assertIn("`raw.customers.id` | rename", _row(self.md, "stg_customers", "customer_id"))
        self.assertIn("`raw.orders.user_id` | rename", _row(self.md, "stg_orders", "customer_id"))

    def test_an_expression_keeps_its_text_and_lists_the_columns_it_reads(self):  # verifies: REQ-DATAMODEL-909#CASE-2
        self.assertIn("`stg_orders.order_date` | min(orders.order_date)",
                      _row(self.md, "customers", "first_order"))
        self.assertIn("`raw.payments.amount` | amount / 100",
                      _row(self.md, "stg_payments", "amount"))

    def test_rules_come_from_the_schema_tests(self):  # verifies: REQ-DATAMODEL-909#CASE-3
        self.assertIn("not_null, relationships to customers.customer_id",
                      _row(self.md, "orders", "customer_id"))
        self.assertIn("accepted_values: placed, shipped, completed, returned",
                      _row(self.md, "orders", "status"))

    def test_models_are_listed_upstream_first_with_what_they_are_built_from(self):  # verifies: REQ-DATAMODEL-909#CASE-3
        self.assertLess(self.md.index("## stg_customers"), self.md.index("## customers"))
        self.assertIn("Built from: `stg_orders`, `stg_payments`", self.md.split("## orders")[1])

    def test_select_star_copies_what_is_produced_and_flags_a_declared_column_that_is_not(self):  # verifies: REQ-DATAMODEL-909#CASE-4  # verifies: REQ-DATAMODEL-909#CASE-6
        tmp, path = _project(
            {"a": "select 1 as x", "b": "select * from {{ ref('a') }}"},
            "models:\n  - name: a\n    columns:\n      - name: x\n"
            "  - name: b\n    columns:\n      - name: x\n      - name: y\n")
        with tmp:
            md = mapping_markdown(path)
        self.assertIn("`a.x` | copy (via *)", _row(md, "b", "x"))
        self.assertIn("needs review", _row(md, "b", "y"))
        self.assertIn("SQL produces no column y", _row(md, "b", "y"))

    def test_what_it_cannot_read_is_marked_needs_review_with_the_reason(self):  # verifies: REQ-DATAMODEL-909#CASE-5  # verifies: REQ-DATAMODEL-909#CASE-6
        cases = {
            "u": ("select a from {{ ref('s') }} union select a from {{ ref('t') }}", "union"),
            "j": ("{% if true %}select a from {{ ref('s') }}{% endif %}", "Jinja"),
            "q": ("select a from (select a from {{ ref('s') }}) z", "subquery"),
            "m": ("select a from {{ ref('s') }} x join {{ ref('t') }} y on x.k = y.k", "2 relations"),
            "r": ("with c as (select a from {{ ref('s') }} union select a from {{ ref('t') }}) "
                  "select c.a from c", "not traced"),
            "n": ("select count(*) from {{ ref('s') }}", "no alias"),
        }
        schema = "models:\n" + "".join("  - name: %s\n    columns:\n      - name: a\n" % k
                                       for k in cases)
        models = dict({k: v[0] for k, v in cases.items()}, s="select 1 as a", t="select 1 as a")
        tmp, path = _project(models, schema)
        with tmp:
            md = mapping_markdown(path)
        for model, (_, why) in cases.items():
            row = _row(md, model, "a") if model != "n" else _row(md, model, "(unnamed)")
            self.assertIn("needs review", row, model)
            self.assertIn(why, row, model)
        # model n also declares column a, which its SELECT never produces
        self.assertIn("SQL produces no column a", _row(md, "n", "a"))

    def test_a_model_with_no_sql_file_is_marked_needs_review(self):  # verifies: REQ-DATAMODEL-909#CASE-6
        tmp, path = _project({"b": "select 1 as c"},
                             "models:\n  - name: ghost\n    columns:\n      - name: c\n")
        with tmp:
            self.assertIn("no SQL file", _row(mapping_markdown(path), "ghost", "c"))

    def test_a_column_is_traced_through_every_cte_to_the_source_table(self):  # verifies: REQ-DATAMODEL-909#CASE-1
        # the usual dbt shape: read the table, rename in a CTE, select * from the last CTE
        tmp, path = _project(
            {"stg": "with source as (select * from {{ ref('raw_c') }}),\n"
                    "renamed as (select id as customer_id, first_name from source)\n"
                    "select * from renamed"},
            "models:\n  - name: stg\n    columns:\n      - name: customer_id\n")
        with tmp:
            md = mapping_markdown(path)
        self.assertIn("`raw_c.id` | rename (via *)", _row(md, "stg", "customer_id"))
        self.assertIn("`raw_c.first_name` | copy (via *)", _row(md, "stg", "first_name"))
        self.assertNotIn("renamed", md.split("## stg")[1])      # a CTE is never named as a source
        self.assertNotIn("needs review", md.split("## stg")[1])

    def test_an_expression_inside_a_cte_is_shown_not_hidden_behind_a_copy(self):  # verifies: REQ-DATAMODEL-909#CASE-2
        tmp, path = _project(
            {"stg": "with source as (select * from {{ ref('raw_p') }}),\n"
                    "renamed as (select amount / 100 as amount from source)\n"
                    "select * from renamed"})
        with tmp:
            row = _row(mapping_markdown(path), "stg", "amount")
        self.assertIn("`raw_p.amount` | amount / 100", row)

    def test_a_bare_name_over_two_relations_goes_to_the_one_that_holds_it(self):  # verifies: REQ-DATAMODEL-909#CASE-1
        tmp, path = _project(
            {"orders": "select 1 as order_id, 2 as customer_id",
             "payments": "select 1 as order_id, 5 as amount",
             "m": "select sum(amount) as total from {{ ref('payments') }} p "
                  "left join {{ ref('orders') }} o on p.order_id = o.order_id"},
            "models:\n  - name: m\n    columns:\n      - name: total\n")
        with tmp:
            row = _row(mapping_markdown(path), "m", "total")
        self.assertIn("`payments.amount` | sum(amount)", row)
        self.assertNotIn("needs review", row)

    def test_a_column_the_sql_produces_is_listed_though_the_schema_omits_it(self):  # verifies: REQ-DATAMODEL-909#CASE-4
        tmp, path = _project(
            {"a": "select 1 as x, 2 as z", "b": "select * from {{ ref('a') }}"},
            "models:\n  - name: b\n    columns:\n      - name: x\n")
        with tmp:
            md = mapping_markdown(path)
        self.assertIn("`a.z` | copy (via *)", _row(md, "b", "z"))
        self.assertNotIn("needs review", _row(md, "b", "z"))

    def test_a_pipe_in_an_expression_does_not_break_the_table(self):  # verifies: REQ-DATAMODEL-909#CASE-7
        tmp, path = _project({"s": "select 1 as a", "m": "select a || 'x' as b from {{ ref('s') }}"},
                             "models:\n  - name: m\n    columns:\n      - name: b\n")
        with tmp:
            row = _row(mapping_markdown(path), "m", "b")
        self.assertIn("a \\|\\| 'x'", row)

    def test_the_same_project_gives_the_same_text(self):  # verifies: REQ-DATAMODEL-909#CASE-7
        self.assertEqual(self.md, mapping_markdown(DBT, title="dbt_shop"))

    def test_the_mapping_flag_writes_markdown_beside_the_scene(self):  # verifies: REQ-DATAMODEL-912#CASE-1
        with tempfile.TemporaryDirectory() as out, contextlib.redirect_stdout(io.StringIO()):
            target = os.path.join(out, "mapping.md")
            self.assertEqual(cli.main(["data-model", "--from-dbt", DBT, "-o", out,
                                       "--mapping", target]), 0)
            with open(target, encoding="utf-8") as fh:
                self.assertEqual(fh.read(), self.md)

    def test_a_scene_that_fails_a_gate_leaves_no_mapping_file(self):  # verifies: REQ-DATAMODEL-912#CASE-2
        with tempfile.TemporaryDirectory() as out:
            target = os.path.join(out, "m.md")
            with mock.patch("excalidraw_engine.data_model.scene_from_spec",
                            side_effect=ValueError("1 overlapping shape(s)")):
                with self.assertRaisesRegex(ValueError, "overlapping"):
                    scene_from_dbt(DBT, out, mapping_path=target)
            self.assertFalse(os.path.exists(target))

    def test_mapping_needs_dbt_and_writes_nothing_when_the_project_is_unreadable(self):  # verifies: REQ-DATAMODEL-912#CASE-3  # verifies: REQ-DATAMODEL-912#CASE-4
        with tempfile.TemporaryDirectory() as out, contextlib.redirect_stderr(io.StringIO()):
            target = os.path.join(out, "m.md")
            self.assertEqual(cli.main(["data-model", "--from-ddl",
                                       os.path.join(DATA, "shop_demo.sql"),
                                       "--mapping", target]), 2)
            self.assertEqual(cli.main(["data-model", "--from-dbt", out, "--mapping", target]), 1)
            self.assertFalse(os.path.exists(target))


class TestLineageFlag(unittest.TestCase):
    """REQ-DATAMODEL-910: lineage is drawn only on request, and labelled `ref`."""

    def _ref_labels(self, *flags):
        with tempfile.TemporaryDirectory() as out, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(["data-model", "--from-dbt", DBT, "-o", out] + list(flags)), 0)
            with open(os.path.join(out, "dbt_shop.excalidraw"), encoding="utf-8") as fh:
                return [e for e in json.load(fh)["elements"]
                        if e["type"] == "text" and e["text"] == "ref"]

    def test_no_lineage_line_without_the_flag(self):  # verifies: REQ-DATAMODEL-910#CASE-1
        self.assertEqual(self._ref_labels(), [])

    def test_the_flag_draws_one_ref_label_per_lineage_line(self):  # verifies: REQ-DATAMODEL-910#CASE-2
        _, lineage = read_dbt(DBT)
        fk_pairs = {(f.columns and t.name, f.ref_table) for t in read_dbt(DBT)[0]
                    for f in t.foreign_keys}
        expected = len([p for p in lineage if p not in fk_pairs])
        self.assertGreater(expected, 0)
        self.assertEqual(len(self._ref_labels("--lineage")), expected)

    def test_lineage_without_dbt_is_a_usage_error(self):  # verifies: REQ-DATAMODEL-910#CASE-3
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(["data-model", "--from-ddl",
                                       os.path.join(DATA, "shop_demo.sql"), "--lineage"]), 2)

    def test_the_mapping_is_the_same_with_or_without_the_flag(self):  # verifies: REQ-DATAMODEL-910#CASE-4
        texts = []
        for flags in ([], ["--lineage"]):
            with tempfile.TemporaryDirectory() as out, contextlib.redirect_stdout(io.StringIO()):
                target = os.path.join(out, "m.md")
                self.assertEqual(cli.main(["data-model", "--from-dbt", DBT, "-o", out,
                                           "--mapping", target] + flags), 0)
                with open(target, encoding="utf-8") as fh:
                    texts.append(fh.read())
        self.assertEqual(texts[0], texts[1])


class TestExplain(unittest.TestCase):
    """REQ-DATAMODEL-911: a diagram a stranger can read without looking anything up."""

    def _spec(self, fixture="shop_demo.sql", **kw):
        return graph_from_tables(parse_ddl(_read(fixture)), **kw)

    @staticmethod
    def _terms(spec):
        return [row[0] for row in spec["glossary"]]

    def test_legend_pairs_each_colour_with_an_icon_and_a_plain_meaning(self):  # verifies: REQ-DATAMODEL-911#CASE-1
        spec = self._spec()
        for role in ("fact", "dimension", "unknown"):
            key = explain.role_key(role)
            self.assertIn(key, spec["roles"])
            self.assertTrue(key.startswith(explain.ICON[role]), key)
            self.assertIn(explain.ROLE_MEANING[role], key)
        self.assertIn(explain.ICON["note"], NOTE)

    def test_the_subtitle_says_how_to_read_arrows_and_colours(self):  # verifies: REQ-DATAMODEL-911#CASE-2
        subtitle = self._spec()["subtitle"]
        self.assertIn("an arrow from A to B means A holds a key that points at B", subtitle)
        self.assertIn("Colour and icon show each table's role", subtitle)

    def test_the_glossary_defines_the_terms_the_diagram_uses_and_no_others(self):  # verifies: REQ-DATAMODEL-911#CASE-3
        demo = self._terms(self._spec())
        for term in ("Arrow", "Fact table", "Dimension", "Unknown", "NN%", "SCD type 2",
                     "Snowflake", "Surrogate key", "Orphan key"):
            self.assertIn(term, demo)
        for absent in ("PK (primary key)", "Grain", "Bridge table", "set by you"):
            self.assertNotIn(absent, demo)
        clean = self._terms(self._spec("shop_clean.sql"))
        for absent in ("SCD type 2", "Snowflake", "Unknown"):
            self.assertNotIn(absent, clean)
        self.assertIn("PK (primary key)", self._terms(self._spec(columns=True)))
        self.assertIn("set by you", self._terms(self._spec(overrides={"stg_payments": "fact"})))

    def test_every_table_says_why_it_has_its_role(self):  # verifies: REQ-DATAMODEL-911#CASE-4
        spec = self._spec()
        why = {row[0]: row[1] for row in spec["glossary"] if row[0].startswith("Why ")}
        self.assertEqual(len(why), 6)
        self.assertIn("Why fact_order_line is a fact table", why)
        self.assertIn("Why dim_product is a dimension", why)
        self.assertIn("Why stg_payments is unknown", why)
        self.assertTrue(all(len(text.split()) > 3 for text in why.values()))

    def test_key_columns_carry_an_icon_and_the_words_pk_and_fk(self):  # verifies: REQ-DATAMODEL-911#CASE-5
        self.assertEqual(explain.column_line("k", True, False), explain.ICON["pk"] + " PK k")
        self.assertEqual(explain.column_line("k", False, True), explain.ICON["fk"] + " FK k")
        self.assertEqual(explain.column_line("k", False, False), "k")
        self.assertTrue(explain.note_text("scd2", "x").startswith(explain.ICON["scd2"]))

    def test_arrows_are_labelled_only_where_labels_cannot_collide(self):  # verifies: REQ-DATAMODEL-911#CASE-6
        def labelled(spec):
            return [e for e in spec["edges"] if not e.get("dashed") and e.get("label")]
        one_fact = self._spec()
        self.assertTrue(labelled(one_fact))
        self.assertNotIn("--columns", one_fact["subtitle"])
        two_facts = self._spec("shop_clean.sql")
        self.assertEqual(labelled(two_facts), [])
        self.assertIn("Add --columns to see which column joins each pair", two_facts["subtitle"])
        with_columns = self._spec("shop_clean.sql", columns=True)
        self.assertEqual(labelled(with_columns), [])
        self.assertNotIn("--columns", with_columns["subtitle"])

    def test_a_wide_legend_never_overlaps_the_glossary(self):  # verifies: REQ-DATAMODEL-911#CASE-7
        with tempfile.TemporaryDirectory() as out:
            for fixture in ("shop_demo.sql", "shop_clean.sql", "shop_noprefix.sql",
                        "order_process.sql"):
                for path in scene_from_ddl(os.path.join(DATA, fixture), out, columns=True):
                    self.assertTrue(os.path.getsize(path) > 0, fixture)


def _scene_elements(fixture, columns=True):
    """The elements of the scene data-model draws for a fixture."""
    with tempfile.TemporaryDirectory() as out:
        path = scene_from_ddl(os.path.join(DATA, fixture), out, columns=columns)[0]
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)["elements"]


def _crossing_pairs(elements):
    """(unbound or routed lines, pairs of lines whose segments cross)."""
    def segments(el):
        pts = [(el["x"] + p[0], el["y"] + p[1]) for p in el["points"]]
        return list(zip(pts, pts[1:]))

    def cross(a, b):
        (p1, p2), (p3, p4) = a, b
        def turn(p, q, r):
            return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
        return (turn(p3, p4, p1) * turn(p3, p4, p2) < 0
                and turn(p1, p2, p3) * turn(p1, p2, p4) < 0)

    lines = [e for e in elements if e["type"] in ("arrow", "line") and len(e.get("points") or ()) >= 2]
    routed = [e for e in lines if e["type"] == "line" or not e.get("startBinding")]
    pairs = sum(1 for i in range(len(lines)) for j in range(i + 1, len(lines))
                if any(cross(a, b) for a in segments(lines[i]) for b in segments(lines[j])))
    return len(routed), pairs


class TestStarLayout(unittest.TestCase):
    """REQ-DATAMODEL-913: facts sharing dimensions sit on opposite sides of them."""

    def test_every_second_fact_like_table_is_flipped(self):  # verifies: REQ-DATAMODEL-913#CASE-1
        spec = graph_from_tables(parse_ddl(_read("shop_clean.sql")))
        flipped = {e["src"] for e in spec["edges"] if e.get("flip")}
        self.assertEqual(flipped, {"fact_payment"})
        self.assertFalse(any(e.get("flip") for e in spec["edges"] if e["src"] == "fact_order_line"))

    def test_two_facts_sharing_dimensions_draw_no_crossing_arrows(self):  # verifies: REQ-DATAMODEL-913#CASE-1
        routed, pairs = _crossing_pairs(_scene_elements("shop_clean.sql"))
        self.assertEqual((routed, pairs), (0, 0))

    def test_one_fact_changes_nothing(self):  # verifies: REQ-DATAMODEL-913#CASE-2
        # shop_demo has one fact table (stg_payments is unknown): nothing to put on the other side
        single = graph_from_tables(parse_ddl(_read("shop_demo.sql")))
        self.assertFalse(any(e.get("flip") for e in single["edges"]))

    def test_the_order_process_keeps_its_routed_edges_and_crossings_down(self):  # verifies: REQ-DATAMODEL-913#CASE-3
        # five facts and eight dimensions: measured at 1 routed edge and 10 crossing pairs
        # (3 and 11 before the flip). A ratchet: it may fall, it must not rise.
        routed, pairs = _crossing_pairs(_scene_elements("order_process.sql"))
        self.assertLessEqual(routed, 1)
        self.assertLessEqual(pairs, 10)

    def test_a_dimension_only_a_right_hand_table_reaches_sits_beside_it(self):  # verifies: REQ-DATAMODEL-913#CASE-3
        elements = _scene_elements("order_process.sql")
        x = {e["customData"]["id"]: e["x"] for e in elements if e.get("customData")}
        self.assertEqual(x["segment"], x["customer"])           # in the dimensions' column


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
