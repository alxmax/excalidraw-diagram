#!/usr/bin/env python3
"""Assert the plugin's version is spelled the same in every manifest that carries it.

`plugin/.claude-plugin/plugin.json` is the source of truth. `.claude-plugin/marketplace.json`
repeats it twice — once at the top level, once inside `plugins[]` — and an installed copy
reads the marketplace entry, so a bump that misses either place ships a release nobody
receives. That is silent: nothing errors, the plugin simply never updates.

Exit 0 when they agree, 1 when they do not. `--fix` rewrites the marketplace manifest from
plugin.json rather than making the human retype it.
"""
import argparse
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = os.path.join(ROOT, "plugin", ".claude-plugin", "plugin.json")
MARKET = os.path.join(ROOT, ".claude-plugin", "marketplace.json")


def _load(path):
    with io.open(path, encoding="utf-8") as f:
        return json.load(f)


def _dump(path, data):
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fix", action="store_true",
                    help="rewrite marketplace.json from plugin.json instead of failing")
    a = ap.parse_args(argv)

    plugin, market = _load(PLUGIN), _load(MARKET)
    want = plugin["version"]

    # Named so a failure says WHICH copy disagreed, not just that something did.
    found = [("marketplace.json top level", market.get("version"))]
    for i, p in enumerate(market.get("plugins", [])):
        found.append(("marketplace.json plugins[%d] (%s)" % (i, p.get("name")), p.get("version")))

    wrong = [(where, got) for where, got in found if got != want]
    if not wrong:
        print("OK  version '%s' agrees across %d location(s)" % (want, len(found) + 1))
        return 0

    if a.fix:
        market["version"] = want
        for p in market.get("plugins", []):
            p["version"] = want
        _dump(MARKET, market)
        print("fixed  marketplace.json set to '%s'" % want)
        return 0

    print("MISMATCH  plugin.json says '%s'" % want)
    for where, got in wrong:
        print("  %-44s says %r" % (where, got))
    print("\nrun `python scripts/check_versions.py --fix` to sync them")
    return 1


if __name__ == "__main__":
    sys.exit(main())
