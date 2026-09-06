---
id: ARCH-RELEASE-035
status: confirmed
level: architecture
layer: feature
owner: Alex
milestone: v1.1.0
satisfies: [SYS-DIAGRAM-001]
---

# A released version reaches the people who installed it

## Description
> The version number is written in three places and read from one of them. If a
> bump misses a copy, nothing errors, no test fails and the release looks shipped —
> it simply never arrives: an installed plugin keeps running the old build because
> the marketplace entry still advertises the old number. That is the worst shape a
> defect can take, silent and invisible from inside the repo, so it gets a check of
> its own rather than a line in a checklist.

Every bullet below is binding.
- `scripts/check_versions.py` compares the version in
  `plugin/.claude-plugin/plugin.json`, which is the source of truth, against both
  copies in `.claude-plugin/marketplace.json`: the top-level one and the one inside
  `plugins[]`.
- The script exits 0 when all three agree, and 1 when any disagrees. A failure names
  every copy that disagreed and what it says, so the reader fixes the right file
  instead of hunting.
- `--fix` rewrites `marketplace.json` from `plugin.json` instead of failing, because
  the copies exist only to be identical and retyping them by hand is where the
  mismatch came from.
- CI runs this check on every push and every pull request, so a mismatch cannot be
  merged.

## Cases
CASE-1 — three matching versions pass
  Given  `plugin.json` at a version and both `marketplace.json` copies at the same one
  When   `check_versions.py` runs
  Then   it exits 0 and prints that the version agrees across three locations

CASE-2 — a missed copy fails, and says which one
  Given  `plugin.json` bumped while the top-level `marketplace.json` version is left behind
  When   `check_versions.py` runs
  Then   it exits 1 and its output names the top-level copy and the value it holds

CASE-3 — a missed copy inside plugins[] fails too
  Given  both top-level versions agreeing while the entry in `plugins[]` lags
  When   `check_versions.py` runs
  Then   it exits 1 and its output names that entry

CASE-4 — `--fix` makes them agree instead of failing
  Given  a marketplace manifest whose two copies both disagree with `plugin.json`
  When   `check_versions.py --fix` runs
  Then   it exits 0, and a second run with no flag exits 0 because the file now agrees

## Context
**Notes**
- The count in the success line is three: `plugin.json` plus the two marketplace
  copies. It is printed so a future manifest that adds a fourth copy shows up as a
  changed number rather than passing unnoticed.
- This is a repo capability, not a shipped one: `scripts/` sits outside `plugin/`
  and never reaches an installed copy. It satisfies the diagram need indirectly —
  a fix nobody receives is a fix that did not happen.

**Current implementation**
- `scripts/check_versions.py`.
- `scripts/test_check_versions.py`.
- The `versions` job in `.github/workflows/ci.yml`.
