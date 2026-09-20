# Changelog

## plugin `v2.1.0` — 2026-09-20

**The viewer no longer fetches anything.** `<name>.html` used to load Excalidraw, React
and its fonts from unpkg on first open; now it carries them. The pinned runtime is
vendored in `excalidraw_engine/runtime/` (1.6 MB) and inlined into the page, so opening a
diagram issues **zero network requests** — verified against a Chrome net log with DNS
pointed at nothing. Nothing about the build changed: the builder still imports no HTTP
client and downloads nothing, at any point.

```python
s.save("flow", out_dir)                    # 1.6 MB page, opens offline (the default)
s.save("flow", out_dir, offline=False)     # ~100 KB page, loads the runtime from unpkg
```

```bash
python excalidraw_builder.py scene --from-json graph.json -o out/ --cdn
python excalidraw_builder.py render flow.excalidraw out/ --cdn
EXCALIDRAW_DIAGRAM_OFFLINE=0 python docs/make_repo_map.py out/   # the default, flipped
```

- **Fixed: the CDN page linked a stylesheet that does not exist.**
  `excalidraw.production.min.css` is not published in `dist/` for 0.17.6, so every viewer
  page has been 404-ing on it; the styles come from the bundle. The `<link>` is gone.
- **Fixed: an empty asset path sent the page to unpkg.** The bundle reads
  `window.EXCALIDRAW_ASSET_PATH || <unpkg>`, so `""` was falsy and the fonts and the lazy
  chunk were fetched anyway. The offline page sets `"./"`.
- The vendored bundle carries one edit: Excalidraw's `VITE_APP_FIREBASE_CONFIG` — the
  config for *their* collaboration backend, which this viewer never starts — is replaced
  by `'{}'`. Its `apiKey` is a Google API key by format, and a public repository is the
  wrong place to store another project's, however public it already is upstream.
- The lazily imported `vendor-*.js` chunk (2.96 MB) is deliberately **not** vendored: a
  scene renders identically without it. The Mermaid-to-Excalidraw dialog is the one
  feature that needs it, and `--cdn` still serves it.
- A scene that spells `__RUNTIME__` in a label can no longer forge part of the page: the
  template is filled in a single pass.
- New `REQ-EXCALIDRAW-854` with `CasesOfflineViewer`; `README.md` gains
  "Everything happens on your machine".

## plugin `v2.0.0` — 2026-09-16

**Breaking: the `Scene` API takes values, not argument lists.** A 1.x generator
passed `x, y, w=, h=, fill=, stroke=, dashed=, font_size=, color=, align=` to
nearly every call, and the same few names travelled through forty signatures.
Each call now takes one `at`, one `paint` and one `font`:

```python
s.box("API", (320, 60), paint="blue", font=14)          # was box("API", 320, 60, fill="blue", font_size=14)
s.label("note", (40, 90), font=Font(12, align="left"))  # was label("note", 40, 90, size=12, align="left")
s.save("flow", out_dir, gates=Gates.strict())           # was five *_check="error" arguments
```

`at` is `(x, y)`, `(x, y, w, h)` or a `Rect`. `paint` and `font` accept a plain
colour or size. A mistyped 1.x key raises instead of being silently dropped.
`row`/`column`/`grid` are now forms of one `arrange()`. `save()` takes one `Gates`
value in place of seven keyword arguments. `Gates.strict()` is the ship setting,
and `"off"` replaces `allow_overlap=` / `allow_short_arrows=`. `references/builder_api.md`
ends with a 1.x → 2.x migration table. **The graph JSON did not change.**

**Output did not change either.** Every example and `docs/repo_graph.json` was
rendered before and after, and the `.excalidraw` files match value for value.

**The 2,298-line file is now a package.** `excalidraw_builder.py` keeps the import
name and the CLI. The code lives in `excalidraw_engine/`, one module per
responsibility, none over 500 lines. `Scene` is assembled from focused mixins over
a shared `Canvas`. `pack()` is a run object with one method per step. The
requirement engine's design review goes from 48 candidates to none.

**An MCP server.** `scripts/mcp_server.py`, registered by `plugin/.mcp.json`, gives
an MCP client `build_scene`, `render_html`, `discover_repo` and `graph_schema`. It is
stdlib only, and new `REQ-EXCALIDRAW-852` covers it with 16 tests.

- Gate warnings print to stderr, not stdout.
- `Scene(font=…)` is `Scene(typeface=…)`; the `hand_drawn=` alias is gone.
- `s.rect(node)` replaces reaching into `s._geom`.
- `fit_text()` is a module function taking `size=` and `min_size=(w, h)`.
- `pipeline()` and `arrange()` refuse an unknown step kind or item key.
- `ARCH-EXCALIDRAW-031` CASE-2 described a legend check that fires with no legend
  drawn; it now matches the behaviour its child requirement always stated.
- `test_excalidraw.py` called `unittest.main()` mid-file, so running it as a
  script skipped the last three test classes. The call is now at the end.

## plugin `v1.1.0` — 2026-09-07

**A diagram without writing Python.** Until now the only way in was to write a
generator script and choose every coordinate — right when the layout carries
meaning, and a poor trade when you just want a picture of a fifteen-node flow.

```
python scripts/excalidraw_builder.py scene --from-json graph.json -o out/
```

`graph.json` names nodes, edges, groups and a direction. No coordinates anywhere.
`Scene.pack()` layers the graph by depth, orders each layer to keep connected
nodes together, places everything, and runs the same seven gates a hand-written
generator answers to. `pack()` is also callable from a generator, for a diagram
that is auto-laid-out in one region and hand-placed in another.

**The routing is the part that matters.** Barycenter ordering — the classic
second pass — minimises crossings between *edges*; this builder's gate measures
an edge cutting through a *box*. So ordering narrows the problem and never closes
it: an edge whose straight line would cut a third box is routed instead, out
through the gap between rows, across the empty strip between two layers, and
along a lane of its own past the diagram. Feedback edges are always routed, so a
cycle never cuts back across the flow.

Fifteen tests cover it (65 → 80), including two independently authored
feedback-edge graphs — a layout that only works on the graph it was written
against is not a layout — plus both orientations, a 200-node chain, disconnected
components, a 12-way fan-out, and every malformed description.

**`SKILL.md` is 196 lines, down from 731.** Every binding rule still states
itself in the file. What moved out is the material that *illustrates* them:
`references/builder_api.md` (every call, how to import the builder, the
`graph.json` schema) and `references/worked_examples.md` (the repo-poster recipe
and the ❌ → ✅ variants). `SKILL.universal.md` is 200 lines and back in step.

- New `ARCH-EXCALIDRAW-034` (auto-layout) with `REQ-EXCALIDRAW-851` (`pack()`),
  and `REQ-EXCALIDRAW-850` (the `scene` verb) under the CLI capability.
  `ARCH-EXCALIDRAW-032` / `REQ-EXCALIDRAW-848` now say four verbs, not three.
- `check_arrow_crossings()` and `pack()` read one geometry helper, so the layout
  cannot disagree with the check that judges it.
- `ARCH-EXCALIDRAW-033` cited a quality rule by its number; it now cites the rule
  by name, because renumbering the list would have broken the link silently.

**The skill no longer explains someone else's tool.** Three of the four worked
generators drew requirement-manager — the repo this skill was split out of. They
draw *this* one now: `make_explainer.py` teaches what the skill is,
`make_full_architecture.py` is the layered poster of this plugin, and
`make_iso5807_flowchart.py` is the builder's own path from a description to two
files. The ❌ → ✅ variants and the quality rules stopped citing `reqmap.py` as
their example of a real identifier.

That pass found one real defect: the stub `discover` writes into an external repo
still resolved the builder from the **old** plugin's cache path, so every
scaffold it generated would have failed to import. Fixed.

**The no-arg smoke test, `render` and `discover` are untouched.**

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
