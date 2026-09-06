# Changelog

## plugin `v1.0.0` — 2026-09-06

First release as its own plugin. The skill was developed inside
[requirement-manager](https://github.com/alxmax/requirement-manager) and shipped there
through plugin `v6.0.0`; this is the same code, split into a repository of its own.

**Why split.** It shared a repository with the requirement engine and nothing else — no
imports in either direction, no shared runtime, no shared configuration. The only mentions
of `reqmap.py` inside the skill are strings drawn *inside* example diagrams. A consumer who
wanted diagrams had to install a requirements engine to get them, and a change to either
one took the other's CI with it.

**What came across.** Every file, and the history: `git log` reaches the original 43
commits through a `git subtree split`, so `git blame` still answers.

**What is new here.**

- `scripts/check_versions.py` — `plugin.json` is the source of truth and
  `marketplace.json` repeats the version twice; a bump that misses either place ships a
  release nobody receives, silently. Now checked, with `--fix` to sync.
- CI runs the builder smoke on **six** platform/version combinations (3.9, 3.12, 3.13 ×
  ubuntu, windows) rather than the two it had as a guest job, plus a job that runs every
  example generator — a worked example that raises is a documentation defect.
- A CHANGELOG-entry check on the version bump.

**Nothing about the skill's behaviour changed.** Same builder, same 60 tests, same output.
