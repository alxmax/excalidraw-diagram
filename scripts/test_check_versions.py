#!/usr/bin/env python3
# tested-by: ARCH-RELEASE-035
"""Tests for the version-coherence check.

The defect this guards is silent: a bump that misses one of the three places the
version is written ships a release nobody receives, with nothing on fire. So the
tests here care less about the happy path than about the two ways a copy can be
left behind, and about `--fix` actually converging.

Each test builds a throwaway repo with the two manifests at chosen versions and
imports check_versions with its module-level paths pointed at it — the script
resolves PLUGIN and MARKET once at import, so they are patched per test rather
than re-imported.
"""
import io
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import check_versions as cv  # noqa: E402


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=2)


class TestCheckVersions(unittest.TestCase):  # tested-by: ARCH-RELEASE-035  # tested-by: REQ-RELEASE-855
    """Every case of ARCH-RELEASE-035, against a throwaway pair of manifests."""

    def setUp(self):
        self._saved = (cv.PLUGIN, cv.MARKET)
        self._tmp = tempfile.TemporaryDirectory()
        root = self._tmp.name
        cv.PLUGIN = os.path.join(root, "plugin", ".claude-plugin", "plugin.json")
        cv.MARKET = os.path.join(root, ".claude-plugin", "marketplace.json")

    def tearDown(self):
        cv.PLUGIN, cv.MARKET = self._saved
        self._tmp.cleanup()

    def _manifests(self, plugin_v, top_v, entry_v):
        _write(cv.PLUGIN, {"name": "excalidraw-diagram", "version": plugin_v})
        _write(cv.MARKET, {"name": "excalidraw-diagram", "version": top_v,
                           "plugins": [{"name": "excalidraw-diagram",
                                        "version": entry_v, "source": "./plugin"}]})

    def _run(self, *argv):
        """main() with stdout captured; returns (exit code, printed text)."""
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = cv.main(list(argv))
        return code, buf.getvalue()

    def test_three_matching_versions_pass(self):  # verifies: REQ-RELEASE-855#CASE-1
        self._manifests("1.1.0", "1.1.0", "1.1.0")
        code, out = self._run()
        self.assertEqual(code, 0, out)
        self.assertIn("1.1.0", out)
        self.assertIn("3 location(s)", out)

    def test_a_stale_top_level_copy_fails_and_is_named(self):  # verifies: REQ-RELEASE-855#CASE-2
        self._manifests("1.2.0", "1.1.0", "1.2.0")
        code, out = self._run()
        self.assertEqual(code, 1)
        self.assertIn("top level", out)
        self.assertIn("1.1.0", out)          # says what the stale copy holds
        self.assertIn("1.2.0", out)          # and what it should hold

    def test_a_stale_entry_inside_plugins_fails_and_is_named(self):  # verifies: REQ-RELEASE-855#CASE-3
        self._manifests("1.2.0", "1.2.0", "1.1.0")
        code, out = self._run()
        self.assertEqual(code, 1)
        self.assertIn("plugins[0]", out)
        self.assertIn("1.1.0", out)

    def test_fix_makes_them_agree(self):  # verifies: REQ-RELEASE-855#CASE-4
        self._manifests("2.0.0", "1.1.0", "1.0.9")
        code, _ = self._run("--fix")
        self.assertEqual(code, 0)
        # the point of --fix is that the next plain run passes
        code, out = self._run()
        self.assertEqual(code, 0, out)
        with io.open(cv.MARKET, encoding="utf-8") as f:
            market = json.load(f)
        self.assertEqual(market["version"], "2.0.0")
        self.assertEqual(market["plugins"][0]["version"], "2.0.0")

    def test_the_real_manifests_agree(self):  # verifies: REQ-RELEASE-855#CASE-1
        # not a fixture: the repo's own manifests, so a bump that misses a copy
        # fails here as well as in the CI job that runs the script directly
        cv.PLUGIN, cv.MARKET = self._saved
        code, out = self._run()
        self.assertEqual(code, 0, out)


if __name__ == "__main__":
    unittest.main()
