#!/usr/bin/env python3
"""Regression gate for the excalidraw-diagram skill.

This is the operational definition of "professional / understandable" for a
generated diagram: every example scene must build with ZERO overlapping shapes
AND ZERO arrow crossings. If a future change (or a new example) introduces
either, this test fails — the quality bar is mechanical, not a matter of taste.

Run:  python -X utf8 -m unittest test_excalidraw -v   (from this scripts/ dir)
It executes each examples/*.py with a stubbed Scene.save (nothing is written to
disk) and asserts on the in-memory scene.
"""
import glob
import os
import runpy
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
EXAMPLES_DIR = os.path.join(HERE, "..", "examples")
sys.path.insert(0, HERE)

import excalidraw_builder as eb  # noqa: E402


def _example_files():
    return sorted(glob.glob(os.path.join(EXAMPLES_DIR, "*.py")))


class TestExampleDiagrams(unittest.TestCase):
    """One assertion per example: clean layout (no overlaps, no crossings)."""


def _make_case(path):
    def case(self):
        captured = {}
        original_save = eb.Scene.save

        def fake_save(self, *a, **k):
            captured["scene"] = self           # keep the built scene, write nothing
            return ("(stubbed).excalidraw", "(stubbed).html")

        eb.Scene.save = fake_save
        try:
            runpy.run_path(path, run_name="__main__")
        finally:
            eb.Scene.save = original_save

        scene = captured.get("scene")
        self.assertIsNotNone(scene, f"{os.path.basename(path)} never called save()")
        assert scene is not None               # narrow for type-checkers
        self.assertEqual(
            scene.check_overlaps(), [],
            f"{os.path.basename(path)} has overlapping shapes")
        self.assertEqual(
            scene.check_arrow_crossings(), [],
            f"{os.path.basename(path)} has arrow(s) crossing an unrelated box")
        self.assertEqual(
            scene.check_legend_coverage(), [],
            f"{os.path.basename(path)} uses fill colour(s) absent from its "
            f"legend (colour-SSOT)")

    return case


def _install_cases():
    files = _example_files()
    assert files, f"no example diagrams found under {EXAMPLES_DIR}"
    for path in files:
        name = "test_" + os.path.splitext(os.path.basename(path))[0]
        setattr(TestExampleDiagrams, name, _make_case(path))


_install_cases()


class TestBuilderUnits(unittest.TestCase):
    """Unit coverage for the Phase-1 builder helpers (gaps closed after the
    consilium pre-merge review: the example tests prove clean layouts but did
    not exercise these paths directly)."""

    def test_move_node_updates_element_coordinates(self):
        s = eb.Scene(seed=99)
        nid = s.box("X", 0, 0, 80, 40)
        s._move_node(nid, 100, 200)
        el = next(e for e in s.elements if e["id"] == nid)
        self.assertEqual((el["x"], el["y"]), (100.0, 200.0))
        self.assertEqual(s._geom[nid][:2], (100, 200))

    def test_move_node_shifts_bound_text(self):
        s = eb.Scene(seed=99)
        nid = s.box("Hello", 0, 0, 80, 40)
        el = next(e for e in s.elements if e["id"] == nid)
        txt = next(e for e in s.elements if e["id"] == el["boundElements"][0]["id"])
        ox, oy = txt["x"], txt["y"]
        s._move_node(nid, 50, 30)
        self.assertAlmostEqual(txt["x"], ox + 50)
        self.assertAlmostEqual(txt["y"], oy + 30)

    def test_move_node_textless_box_ok(self):
        s = eb.Scene(seed=99)
        nid = s.box("", 0, 0, 40, 40)        # no bound text -> no children to shift
        s._move_node(nid, 10, 10)            # must not raise
        self.assertEqual(s._geom[nid][:2], (10, 10))

    def test_save_crossing_check_error_raises(self):
        s = eb.Scene(seed=99)
        left = s.box("L", 0, 0, 80, 40)
        s.box("M", 200, 0, 80, 40)
        right = s.box("R", 400, 0, 80, 40)
        s.arrow(left, right)                 # straight line passes through M
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                s.save("x", out_dir=d, crossing_check="error")

    def test_save_crossing_check_warn_default_does_not_raise(self):
        s = eb.Scene(seed=99)
        left = s.box("L", 0, 0, 80, 40)
        s.box("M", 200, 0, 80, 40)
        right = s.box("R", 400, 0, 80, 40)
        s.arrow(left, right)
        with tempfile.TemporaryDirectory() as d:
            s.save("x", out_dir=d)           # default "warn" — must not raise

    def test_fill_none_is_transparent(self):
        s = eb.Scene(seed=99, roles={"agent": "blue"})
        nid = s.box("T", 0, 0, fill=None)
        el = next(e for e in s.elements if e["id"] == nid)
        self.assertEqual(el["backgroundColor"], "transparent")

    def test_fill_role_resolves(self):
        s = eb.Scene(seed=99, roles={"agent": "blue"})
        nid = s.box("T", 0, 0, fill="agent")
        el = next(e for e in s.elements if e["id"] == nid)
        self.assertEqual(el["backgroundColor"], eb._FILL["blue"])

    def test_legend_coverage_clean_when_legend_covers_fills(self):
        s = eb.Scene(seed=99)
        s.box("a", 0, 0, fill="blue")
        s.box("b", 0, 200, fill="green")
        s.legend([("input", "blue"), ("output", "green")], x=400, y=0)
        self.assertEqual(s.check_legend_coverage(), [])

    def test_legend_coverage_flags_unlegended_fill(self):
        s = eb.Scene(seed=99)
        s.box("a", 0, 0, fill="blue")
        s.box("b", 0, 200, fill="indigo")          # not in the legend below
        s.legend([("input", "blue")], x=400, y=0)
        self.assertEqual(s.check_legend_coverage(), [eb._FILL["indigo"]])

    def test_legend_coverage_noop_without_legend(self):
        s = eb.Scene(seed=99)
        s.box("a", 0, 0, fill="indigo")            # no legend() -> nothing to enforce
        self.assertEqual(s.check_legend_coverage(), [])

    def test_save_legend_check_error_raises_on_uncovered_fill(self):
        s = eb.Scene(seed=99)
        s.box("a", 0, 0, fill="blue")
        s.box("b", 0, 200, fill="violet")          # uncovered
        s.legend([("input", "blue")], x=400, y=0)
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                s.save("x", out_dir=d, legend_check="error")

    def test_save_legend_check_warn_default_does_not_raise(self):
        s = eb.Scene(seed=99)
        s.box("a", 0, 0, fill="blue")
        s.box("b", 0, 200, fill="violet")          # uncovered, but warn-only
        s.legend([("input", "blue")], x=400, y=0)
        with tempfile.TemporaryDirectory() as d:
            s.save("x", out_dir=d)                  # default "warn" — must not raise

    def test_save_rejects_bad_legend_check(self):
        s = eb.Scene(seed=99)
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                s.save("x", out_dir=d, legend_check="nope")

    def test_path_label_overlapping_a_box_is_detected(self):
        s = eb.Scene(seed=99)
        s.box("B", 0, 0, 200, 80, fill="blue")
        s.path([(0, 40), (200, 40)], label="routed label over the box")
        hits = s.check_overlaps()
        self.assertTrue(any("label" in a or "label" in b for a, b in hits),
                        f"path label over a box must be flagged: {hits}")

    def test_path_label_in_clear_space_is_not_flagged(self):
        s = eb.Scene(seed=99)
        s.box("B", 0, 0, 100, 40, fill="blue")
        s.path([(0, 300), (200, 300)], label="clear")   # well below the box
        self.assertEqual(s.check_overlaps(), [])

    def test_polyline_midpoint_edges(self):
        self.assertEqual(eb.Scene._polyline_midpoint([(3, 7)]), (3, 7))
        self.assertEqual(eb.Scene._polyline_midpoint([(0, 0), (0, 0)]), (0, 0))
        mid = eb.Scene._polyline_midpoint([(0, 0), (0, 100), (200, 100), (200, 0)])
        self.assertAlmostEqual(mid[0], 100)
        self.assertAlmostEqual(mid[1], 100)

    def test_bounds_paths_only_and_empty(self):
        self.assertEqual(eb.Scene(seed=99).bounds(), (0, 0, 0, 0))
        s = eb.Scene(seed=99)
        s.path([(10, 20), (100, 200)])
        self.assertEqual(s.bounds(), (10, 20, 100, 200))


if __name__ == "__main__":
    unittest.main(verbosity=2)
