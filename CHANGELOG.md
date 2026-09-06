# Changelog

## plugin `v1.0.1` — 2026-09-06

**The skill now says out loud that it is for people who do not understand the thing.**
Most of the time this skill is reached for by someone who wants a picture *because*
the prose did not land. The contract only implied that: the readability rules were
there, `examples/make_explainer.py` was there, but nothing in the trigger phrases or
the worked examples named the case, and no requirement held the obligation.

- `SKILL.md` / `SKILL.universal.md` — "explain how X works" / "I don't understand X"
  (and the Romanian forms) are now triggers; a **When to use** bullet and worked
  example **6** show the teaching-diagram shape, with `make_explainer.py` as the
  template.
- `ARCH-EXCALIDRAW-033` (explanatory output) and `REQ-EXCALIDRAW-849` (the `legend()`
  and `glossary()` keys) are the requirement-side of that promise, tagged into the
  builder and covered by five new tests (60 → 65).

**Fixed: the import resolver pointed at the old plugin.** Both contracts told an
external generator to look in `~/.claude/plugins/cache/requirement-manager/...` and,
on failure, to `/plugin install requirement-manager`. That was where the skill lived
before the split; installing *this* plugin put the builder somewhere the resolver
never looked. Now `excalidraw-diagram/excalidraw-diagram`.

**Fixed: `SKILL.universal.md` had drifted.** It was missing the minimal example, the
full quality rules, the tips and all the worked examples — none of which are Claude
Code-specific. Re-synced; the two files differ only in the tool-specific parts again.

**Housekeeping in `requirements/`.** `ARCH-EXCALIDRAW-030/031/032` still carried
`milestone: v2.4` and `skills/...` paths from the repository they came from; now
`v1.0.0` and `plugin/skills/...`.

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
