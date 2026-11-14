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
> The version number is written in five places and read from one of them. If a
> bump misses a copy, nothing errors, no test fails and the release looks shipped —
> it simply never arrives: an installed plugin keeps running the old build because
> the marketplace entry still advertises the old number. That is the worst shape a
> defect can take, silent and invisible from inside the repo, so it gets a check of
> its own rather than a line in a checklist.

Every bullet below is binding.
- `plugin-full/.claude-plugin/plugin.json` is the source of truth, and every other copy of
  the version equals it. [[REQ-RELEASE-855]] details the check.
- CI runs the version check on every push and every pull request, so a mismatch
  cannot be merged.
- CI fails a pull request that bumps the version without a matching CHANGELOG heading.
- A release starts with one command that raises every copy together. [[REQ-RELEASE-857]]

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
  Then   `scripts/check_versions.py` is absent, because only the edition's own folder ships

## Context
**Notes**
- This is a repo capability, not a shipped one: `scripts/` sits outside `plugin-full/`
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

# check_versions.py: every copy of the version agrees

## Description
> The copies exist only to be identical, so the check compares them, names every
> one that disagrees, and can rewrite them from the source of truth instead of
> asking someone to retype a number by hand.

Every bullet below is binding.
- `scripts/check_versions.py` compares the version in
  `plugin-full/.claude-plugin/plugin.json` against `plugin/.claude-plugin/plugin.json`
  and every copy in `.claude-plugin/marketplace.json`: the top level and each `plugins[]` entry.
- The script exits 0 when all copies agree, and 1 when any disagrees.
- A failure names every copy that disagreed and the value it holds.
- `--fix` rewrites every other copy from `plugin.json` instead of failing.

## Cases
CASE-1 — matching versions pass
  Given  both `plugin.json` files and every `marketplace.json` copy at the same version
  When   `check_versions.py` runs
  Then   it exits 0 and prints that the version agrees across five locations

CASE-2 — a missed copy fails, and says which one
  Given  `plugin.json` bumped while the top-level `marketplace.json` version is left behind
  When   `check_versions.py` runs
  Then   it exits 1 and its output names the top-level copy and the value it holds

CASE-3 — a missed copy inside plugins[] fails too
  Given  the top-level versions agreeing while one entry in `plugins[]` lags
  When   `check_versions.py` runs
  Then   it exits 1 and its output names that entry

CASE-4 — `--fix` makes them agree instead of failing
  Given  every other copy disagreeing with `plugin.json`
  When   `check_versions.py --fix` runs
  Then   it exits 0, and a second run with no flag exits 0 because the files now agree

CASE-5 — a stale directory edition fails, and says so
  Given  `plugin/.claude-plugin/plugin.json` left behind a bump
  When   `check_versions.py` runs
  Then   it exits 1 and its output names the plugin copy and the value it holds

## Context
**Notes**
- The count in the success line is five: the two `plugin.json` files plus the three
  marketplace copies. It is printed so a future manifest that adds a fourth copy shows up as a
  changed number rather than passing unnoticed.

**Current implementation**
- `main()` in `scripts/check_versions.py`.
- `TestCheckVersions` in `scripts/test_check_versions.py`.


--------------------


---
id: REQ-RELEASE-857
status: confirmed
level: code
layer: feature
owner: Alex
satisfies: [ARCH-RELEASE-035]
---

# check_versions.py --bump: start a release with no copy left behind

## Description
> A release starts by raising the version, and the five places it is written are
> exactly where a hand edit goes wrong. `--bump` raises them in one step, so the
> state it leaves already passes the check.

Every bullet below is binding.
- `check_versions.py --bump patch|minor|major` raises the version in `plugin.json`
  and writes the same value to every other copy.
- `--bump` changes only the version string in `plugin.json`, leaving its layout and
  line endings as they were.
- `--bump` refuses a version that is not X.Y.Z, and changes no file when it does.
- After a bump, the script reminds the author to add the matching CHANGELOG heading
  when it is missing.

## Cases
CASE-1 — `--bump` raises every copy together
  Given  every copy of the version at `2.4.9`
  When   `check_versions.py --bump minor` runs
  Then   it exits 0 and every copy holds `2.5.0`
  Then   a second run with no flag exits 0, and only the version string in `plugin.json` changed

CASE-2 — `--bump` resets the parts below the one raised
  Given  every copy at `2.4.9`
  When   `--bump` runs with `patch`, `minor` and `major`, each from `2.4.9`
  Then   the results are `2.4.10`, `2.5.0` and `3.0.0`

CASE-3 — `--bump` refuses a version that is not X.Y.Z
  Given  every copy at `2.5`
  When   `check_versions.py --bump patch` runs
  Then   it exits 1 and every copy still holds `2.5`

CASE-4 — the CHANGELOG reminder appears only when the heading is missing
  Given  a bump to `1.0.1` with and without a `` `v1.0.1` `` heading in `CHANGELOG.md`
  When   `check_versions.py --bump patch` runs
  Then   the output names `CHANGELOG.md` and `v1.0.1` when the heading is missing, and not otherwise

## Context
**Notes**
- It does not write the CHANGELOG entry: what changed is for the author to say, and CI
  already fails a pull request whose bump has no matching heading.

**Current implementation**
- `_bumped()` and the bump branch of `main()` in `scripts/check_versions.py`.
- `TestCheckVersions` in `scripts/test_check_versions.py`.
