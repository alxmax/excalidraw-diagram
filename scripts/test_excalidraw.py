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

    return case


def _install_cases():
    files = _example_files()
    assert files, f"no example diagrams found under {EXAMPLES_DIR}"
    for path in files:
        name = "test_" + os.path.splitext(os.path.basename(path))[0]
        setattr(TestExampleDiagrams, name, _make_case(path))


_install_cases()


if __name__ == "__main__":
    unittest.main(verbosity=2)
