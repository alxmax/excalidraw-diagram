#!/usr/bin/env python3
# implements: ARCH-RELEASE-035
"""Assert the plugin's version is spelled the same in every manifest that carries it.

`plugin/.claude-plugin/plugin.json` is the source of truth. `.claude-plugin/marketplace.json`
repeats it twice — once at the top level, once inside `plugins[]` — and an installed copy
reads the marketplace entry, so a bump that misses either place ships a release nobody
receives. That is silent: nothing errors, the plugin simply never updates.

Exit 0 when they agree, 1 when they do not. `--fix` rewrites the marketplace manifest from
plugin.json rather than making the human retype it. `--bump patch|minor|major` raises the
version in plugin.json and writes it to both marketplace copies in one step, so a release
cannot be started with one of the three places left behind.
"""
import argparse
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = os.path.join(ROOT, "plugin", ".claude-plugin", "plugin.json")
MARKET = os.path.join(ROOT, ".claude-plugin", "marketplace.json")
CHANGELOG = os.path.join(ROOT, "CHANGELOG.md")
_SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def _load(path):
    with io.open(path, encoding="utf-8") as f:
        return json.load(f)


def _dump(path, data):
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def _bumped(version, part):  # implements: REQ-RELEASE-857
    """`version` (X.Y.Z) with `part` raised and the parts below it reset."""
    m = _SEMVER.match(str(version))
    if not m:
        raise ValueError("plugin.json version %r is not X.Y.Z" % (version,))
    major, minor, patch = (int(g) for g in m.groups())
    if part == "major":
        return "%d.0.0" % (major + 1)
    if part == "minor":
        return "%d.%d.0" % (major, minor + 1)
    return "%d.%d.%d" % (major, minor, patch + 1)


def _set_plugin_version(new):
    """Write `new` into plugin.json by editing the one version string, so the file's
    layout and line endings are left exactly as they were."""
    with io.open(PLUGIN, encoding="utf-8", newline="") as f:
        text = f.read()
    text, n = re.subn(r'("version"\s*:\s*")[^"]*(")',
                      lambda m: m.group(1) + new + m.group(2), text, count=1)
    if n != 1:
        raise ValueError("plugin.json has no version string to change")
    with io.open(PLUGIN, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def _sync_marketplace(market, version):
    """Set every version in the marketplace manifest to `version` and save it."""
    market["version"] = version
    for p in market.get("plugins", []):
        p["version"] = version
    _dump(MARKET, market)


def main(argv=None):  # implements: REQ-RELEASE-855
    """Compare (or with --fix, sync) the three version copies; returns the exit code."""
    ap = argparse.ArgumentParser(description=__doc__)
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--fix", action="store_true",
                       help="rewrite marketplace.json from plugin.json instead of failing")
    group.add_argument("--bump", choices=("patch", "minor", "major"),
                       help="raise the version in plugin.json and in both marketplace copies")
    a = ap.parse_args(argv)

    plugin, market = _load(PLUGIN), _load(MARKET)
    want = plugin["version"]

    if a.bump:
        try:
            new = _bumped(want, a.bump)
        except ValueError as exc:
            print("error: %s" % exc)
            return 1
        _set_plugin_version(new)
        _sync_marketplace(market, new)
        print("bumped  %s -> %s  (plugin.json and both marketplace copies)" % (want, new))
        with io.open(CHANGELOG, encoding="utf-8") as f:
            if "`v%s`" % new not in f.read():
                print("next    add a `v%s` heading to CHANGELOG.md; CI fails the PR without one"
                      % new)
        return 0

    # Named so a failure says WHICH copy disagreed, not just that something did.
    found = [("marketplace.json top level", market.get("version"))]
    for i, p in enumerate(market.get("plugins", [])):
        found.append(("marketplace.json plugins[%d] (%s)" % (i, p.get("name")), p.get("version")))

    wrong = [(where, got) for where, got in found if got != want]
    if not wrong:
        print("OK  version '%s' agrees across %d location(s)" % (want, len(found) + 1))
        return 0

    if a.fix:
        _sync_marketplace(market, want)
        print("fixed  marketplace.json set to '%s'" % want)
        return 0

    print("MISMATCH  plugin.json says '%s'" % want)
    for where, got in wrong:
        print("  %-44s says %r" % (where, got))
    print("\nrun `python scripts/check_versions.py --fix` to sync them")
    return 1


if __name__ == "__main__":
    sys.exit(main())
