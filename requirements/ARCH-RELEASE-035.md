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
- `plugin/.claude-plugin/plugin.json` is the source of truth, and every other copy of
  the version equals it. [[REQ-RELEASE-855]] details the check.
- CI runs the version check on every push and every pull request, so a mismatch
  cannot be merged.
- CI fails a pull request that bumps the version without a matching CHANGELOG heading.

## Cases
CASE-1 — CI runs the version check on every push and pull request <!-- verifiable by: inspection -->
  Given  `.github/workflows/ci.yml`
  When   a commit is pushed or a pull request opened
  Then   the `versions` job runs `scripts/check_versions.py` and its own tests

CASE-2 — a bump without a CHANGELOG heading fails the pull request <!-- verifiable by: inspection -->
  Given  a pull request that changes the version in `plugin.json`
  When   the `changelog` job runs
  Then   it fails unless `CHANGELOG.md` holds a `` `vX.Y.Z` `` heading for that version

CASE-3 — the release check never ships <!-- verifiable by: inspection -->
  Given  the directory `/plugin install` hands a consumer
  When   its contents are listed
  Then   `scripts/check_versions.py` is absent, because only `plugin/` ships

## Context
**Notes**
- This is a repo capability, not a shipped one: `scripts/` sits outside `plugin/`
  and never reaches an installed copy. It satisfies the diagram need indirectly —
  a fix nobody receives is a fix that did not happen.

**Current implementation**
- `scripts/check_versions.py` and `scripts/test_check_versions.py`.
- The `versions` and `changelog` jobs in `.github/workflows/ci.yml`.


--------------------


---
id: REQ-RELEASE-855
status: confirmed
level: code
layer: feature
owner: Alex
satisfies: [ARCH-RELEASE-035]
---

# check_versions.py: the three copies of the version agree

## Description
> The copies exist only to be identical, so the check compares them, names every
> one that disagrees, and can rewrite them from the source of truth instead of
> asking someone to retype a number by hand.

Every bullet below is binding.
- `scripts/check_versions.py` compares the version in
  `plugin/.claude-plugin/plugin.json` against both copies in
  `.claude-plugin/marketplace.json`: the top-level one and the one inside `plugins[]`.
- The script exits 0 when all three agree, and 1 when any disagrees.
- A failure names every copy that disagreed and the value it holds.
- `--fix` rewrites `marketplace.json` from `plugin.json` instead of failing.

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

**Current implementation**
- `main()` in `scripts/check_versions.py`.
- `TestCheckVersions` in `scripts/test_check_versions.py`.
