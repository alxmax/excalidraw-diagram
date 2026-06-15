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
import subprocess
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
        self.assertEqual(
            scene.check_text_overflow(), [],
            f"{os.path.basename(path)} has bound text bigger than its box "
            f"(label spills outside the shape)")
        self.assertEqual(
            scene.check_text_overlaps(), [],
            f"{os.path.basename(path)} has free text label(s) overlapping "
            f"(a caption/header sits on another)")

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

    # -- text-overflow gate (label bigger than its box) -------------------
    def test_check_text_overflow_detects_oversized_label(self):
        s = eb.Scene(seed=99)
        s.box("a label far too wide for this tiny box", 0, 0, 40, 30, fill="blue")
        self.assertTrue(s.check_text_overflow(),
                        "bound text wider than its box must be flagged")

    def test_check_text_overflow_clean_when_box_fits(self):
        s = eb.Scene(seed=99)
        s.box("ok", 0, 0, 160, 70, fill="blue")
        self.assertEqual(s.check_text_overflow(), [])

    def test_fit_text_box_clears_overflow_check(self):
        s = eb.Scene(seed=99)
        wrapped, w, h = eb.Scene.fit_text("a label far too wide for one line",
                                          font=14, max_chars=16)
        s.box(wrapped, 0, 0, w, h, fill="blue")
        self.assertEqual(s.check_text_overflow(), [],
                         "a box sized by fit_text must clear the overflow check")

    def test_save_overflow_check_error_raises(self):
        s = eb.Scene(seed=99)
        s.box("a label far too wide for this tiny box", 0, 0, 40, 30, fill="blue")
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                s.save("x", out_dir=d, overflow_check="error")

    def test_save_overflow_check_warn_default_does_not_raise(self):
        s = eb.Scene(seed=99)
        s.box("a label far too wide for this tiny box", 0, 0, 40, 30, fill="blue")
        with tempfile.TemporaryDirectory() as d:
            s.save("x", out_dir=d)                  # default "warn" — must not raise

    # -- free-text-overlap gate (caption colliding with header) -----------
    def test_check_text_overlaps_detects_overlapping_captions(self):
        s = eb.Scene(seed=99)
        s.label("a caption sitting right here", 100, 100, size=14)
        s.label("another caption on top of it", 100, 103, size=14)
        self.assertTrue(s.check_text_overlaps(),
                        "two overlapping free captions must be flagged")

    def test_check_text_overlaps_ignores_bound_labels(self):
        s = eb.Scene(seed=99)
        s.box("one", 0, 0, 160, 70, fill="blue")
        s.box("two", 0, 100, 160, 70, fill="green")
        s.legend([("input", "blue"), ("output", "green")], x=400, y=0)
        self.assertEqual(s.check_text_overlaps(), [],
                         "bound labels (box + legend rows) must not be flagged")

    def test_save_text_overlap_check_error_raises(self):
        s = eb.Scene(seed=99)
        s.label("caption one is here", 100, 100, size=14)
        s.label("caption two is here", 100, 103, size=14)
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                s.save("x", out_dir=d, text_overlap_check="error")

    def test_save_rejects_bad_overflow_check(self):
        s = eb.Scene(seed=99)
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                s.save("x", out_dir=d, overflow_check="nope")

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

    def test_glossary_renders_and_is_overlap_checked(self):
        s = eb.Scene(seed=99)
        s.glossary([("SSOT", "single source of truth"),
                    ("dogfood", "runs on its own requirements")], 0, 0)
        # the glossary box is registered as checkable content
        self.assertTrue(any("glossary" in lab for *_, lab in s._nodes))
        # a box dropped on top of it must be flagged
        s.box("X", 10, 10, 80, 40, fill="blue")
        self.assertNotEqual(s.check_overlaps(), [])

    def test_glossary_empty_raises(self):
        with self.assertRaises(ValueError):
            eb.Scene(seed=99).glossary([], 0, 0)

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


class TestCli(unittest.TestCase):
    """The render + discover CLI verbs, and the preserved no-arg smoke test."""

    BUILDER = os.path.join(HERE, "excalidraw_builder.py")

    # --- render: rebuild the .html viewer from an existing .excalidraw scene ---
    def test_render_rebuilds_html_from_scene(self):
        with tempfile.TemporaryDirectory() as d:
            s = eb.Scene(seed=7)
            s.box("A", 0, 0)
            s.box("B", 0, 120)
            pj, ph = s.save("demo", out_dir=d)
            os.remove(ph)                          # delete html so render must recreate it
            out = eb.render_html(pj)
            self.assertEqual(out, os.path.join(d, "demo.html"))
            self.assertTrue(os.path.exists(out))
            with open(out, encoding="utf-8") as f:
                html = f.read()
            self.assertIn("excalidraw", html.lower())   # the embedded scene + viewer
            self.assertIn('"type":', html)              # scene JSON inlined

    def test_render_rejects_non_scene(self):
        with tempfile.TemporaryDirectory() as d:
            bad = os.path.join(d, "bad.excalidraw")
            with open(bad, "w", encoding="utf-8") as f:
                f.write('{"nope": 1}')               # valid JSON, but no "elements"
            with self.assertRaises(ValueError):
                eb.render_html(bad)

    def test_render_rejects_non_dict_elements(self):
        with tempfile.TemporaryDirectory() as d:
            bad = os.path.join(d, "bad.excalidraw")
            with open(bad, "w", encoding="utf-8") as f:
                f.write('{"elements": [1, 2, 3]}')    # a list, but not element objects
            with self.assertRaises(ValueError):
                eb.render_html(bad)

    # --- discover: scan a repo -> a runnable Python generator stub ---
    def test_discover_components_prunes_and_sorts(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "core"))
            with open(os.path.join(d, "core", "engine.py"), "w") as f:
                f.write("x = 1\n")
            with open(os.path.join(d, "app.py"), "w") as f:
                f.write("y = 2\n")
            os.makedirs(os.path.join(d, "node_modules"))     # must be pruned
            with open(os.path.join(d, "node_modules", "z.js"), "w") as f:
                f.write("zz\n")
            comps = eb.discover_components(d)
            self.assertIn("core", comps)
            self.assertIn("app.py", comps)
            self.assertNotIn("node_modules", comps)
            self.assertEqual(comps, sorted(comps))           # deterministic

    def test_discover_stub_is_runnable(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "core"))
            with open(os.path.join(d, "core", "engine.py"), "w") as f:
                f.write("x = 1\n")
            with open(os.path.join(d, "app.py"), "w") as f:
                f.write("y = 2\n")
            stub = eb.discover_stub(d, out_path=os.path.join(d, "make_diagram.py"))
            self.assertTrue(os.path.exists(stub))
            with open(stub, encoding="utf-8") as f:
                compile(f.read(), stub, "exec")        # syntactically valid
            env = dict(os.environ, PYTHONPATH=HERE)      # so `from excalidraw_builder import Scene` resolves
            r = subprocess.run([sys.executable, "-X", "utf8", stub],
                               cwd=d, capture_output=True, text=True, env=env)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(glob.glob(os.path.join(d, "*.excalidraw")),
                            "stub ran but saved no scene")

    def test_discover_empty_repo_stub_still_runs(self):
        with tempfile.TemporaryDirectory() as d:
            stub = eb.discover_stub(d, out_path=os.path.join(d, "make_diagram.py"))
            with open(stub, encoding="utf-8") as f:
                compile(f.read(), stub, "exec")        # placeholders, still valid
            env = dict(os.environ, PYTHONPATH=HERE)
            r = subprocess.run([sys.executable, "-X", "utf8", stub],
                               cwd=d, capture_output=True, text=True, env=env)
            self.assertEqual(r.returncode, 0, r.stderr)

    def test_discover_stub_truncates_at_cap(self):
        # a repo with more components than max_components emits the truncation
        # NOTE and caps the component list to the first `max_components`.
        with tempfile.TemporaryDirectory() as d:
            for i in range(25):
                sub = os.path.join(d, "mod%02d" % i)
                os.makedirs(sub)
                with open(os.path.join(sub, "x.py"), "w") as f:
                    f.write("x = 1\n")
            stub = eb.discover_stub(d, out_path=os.path.join(d, "make_diagram.py"),
                                    max_components=20)
            with open(stub, encoding="utf-8") as f:
                code = f.read()
            self.assertIn("more components than the cap", code)  # truncation NOTE present
            self.assertIn("mod00", code)                         # first component kept
            self.assertNotIn("mod24", code)                      # 25th is past the cap of 20

    # --- the no-arg invocation must still be the smoke test (CI depends on it) ---
    def test_cli_no_args_runs_selftest(self):
        env = dict(os.environ, PYTHONPATH=HERE)
        r = subprocess.run([sys.executable, "-X", "utf8", self.BUILDER],
                           capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("OK smoke test", r.stdout)

    def test_cli_render_subcommand(self):
        with tempfile.TemporaryDirectory() as d:
            s = eb.Scene(seed=8)
            s.box("X", 0, 0)
            pj, ph = s.save("scene", out_dir=d)
            os.remove(ph)
            r = subprocess.run([sys.executable, "-X", "utf8", self.BUILDER, "render", pj],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(os.path.exists(os.path.join(d, "scene.html")))

    def test_render_stub_handles_hostile_repo_name(self):
        # a repo dir name with quotes/triple-quotes must not break the generated
        # stub's docstring or string literals (FS-independent: call _render_stub direct)
        code = eb._render_stub('a"""b\'c"d', ["x"], False)
        compile(code, "<stub>", "exec")            # must not raise SyntaxError

    def test_cli_unknown_verb_exits_nonzero(self):
        r = subprocess.run([sys.executable, "-X", "utf8", self.BUILDER, "bogus"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
