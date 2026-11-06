# Changelog

## plugin `v2.13.0` — 2026-11-07

**Run on a real dbt project, the mapping was wrong in a way it did not admit.** On the public
dbt-labs `jaffle_shop` (Apache-2.0) the usual shape, `with source as (...), renamed as (...)
select * from renamed`, gave sources like `renamed.customer_id`: the name of a CTE, not marked
for review. A column is now traced through every CTE's own SELECT to the models and source
tables underneath, so `customer_id` reads `raw_customers.id`, `rename`, and an expression done
inside a CTE (`amount / 100`) is shown rather than hidden behind `copy`.

A model's rows are now the columns its SQL produces, followed through `*`, not only those its
schema.yml lists. That adds columns the schema omits, drops a false "does not declare" warning
(schema.yml usually names only the columns it tests), and finds a real inconsistency in the
public project: its schema documents `total_order_amount` and the SQL produces
`customer_lifetime_value`. A bare name over several relations (`sum(amount)` over a join) goes to
the one relation known to hold it. Jinja control flow (a `{% for %}` loop, as in `orders`) is
still marked "needs review", never guessed.

**A model with no declared types is no longer always "unknown".** dbt schema files usually
declare none, so the measures-and-descriptions rule had nothing to read: `jaffle_shop`'s `orders`,
with five `*_amount` columns, came out unknown. A column with no type is now read from its name
(`amount`, `*_amount`, `number_of_*` as measures; `status`, `*_name` as descriptive), and the
reason says "guessed from the names". A declared type is never overridden by a name.

## plugin `v2.12.0` — 2026-11-07

**Changed: dbt lineage is drawn only with `--lineage`.** Rendered, a real dbt project's
`ref()` lines outnumbered its foreign keys and ran round the whole diagram, and a dashed
lineage line looked exactly like the dashed line to a review note. Without the flag the
diagram now shows models, foreign keys, roles and review notes; with it, each `ref()` is a
dashed line labelled `ref`. v2.10.0 drew lineage by default. The mapping file is unchanged
and always says what each model is built from.

**Confidence now means something.** It was the winner's share of the top two scores, so it
read 100% whenever no other role scored. It is now the winner's lead over the runner-up
times how much evidence it has, and reaches 100% only with a clear lead and eight points
or more: a well-evidenced table still reads 100%, a table that rests on little or has a
close rival reads lower, and a table that is only keys reads low.

**A data-model diagram a stranger can read.** The subtitle says how to read it (a box is a
table, an arrow from A to B means A holds a key that points at B). The legend gives every
colour an icon and a plain meaning; the glossary defines only the terms the picture uses (fact,
dimension, PK, SCD type 2 ...) in everyday words and says why each table has its role; key
columns and review notes carry icons beside the words. Arrows name their key column only where
labels cannot collide: with two facts sharing dimensions they used to stack on top of each
other, so the diagram now says to add `--columns` instead.

**A wide legend no longer overlaps the glossary.** `graph.json`'s glossary starts to the right
of the legend whatever its width, not at a fixed position.

**Review notes wrap wide.** A node in a `graph.json` takes an optional `max_chars` (the
wrap width of its label, default 22, so nothing existing changes). `data-model` sets 40 on
its review notes, which were 12-line towers.

## plugin `v2.11.0` — 2026-11-06

**`data-model --from-dbt ... --mapping map.md` writes a source-to-target mapping.** One
section per model, upstream models first; one row per target column with its source
(`model.column`, or `source.table.column` for a dbt source), the transformation (`copy`,
`rename`, or the expression as written) and the rule (the column's schema.yml tests,
including the target of a `relationships` test and the values of `accepted_values`).

The source is traced through aliases, joins and CTEs that only pass a table through. What
the reader cannot follow is not guessed: a union, Jinja control flow, a subquery in `FROM`,
a CTE that reshapes its input, an unaliased expression, a bare column over several
relations, or a model with no SQL file is marked **needs review** with the reason. The file
is written only after the diagram has passed its gates.

## plugin `v2.10.0` — 2026-11-06

**`data-model --from-dbt <project>` draws a dbt project.** One node per model under
`models/`. A `relationships` test on a column becomes a foreign key, so the model is
classified and reviewed like any DDL table; a column with `unique` and `not_null` tests is
the primary key; `data_type` gives the column type. A `ref()` in a model's SQL is lineage,
drawn as a dashed line from the model to what it is built from. Without `data_type` a model
may classify as unknown; `--roles` corrects it.

`schema.yml` is read by a small YAML subset reader written for this (the plugin installs
nothing from PyPI): maps, lists, scalars, flow collections and `|` / `>` blocks. Anchors,
tags, tabs, repeated keys and several documents are refused with the line number.

## plugin `v2.9.0` — 2026-11-06

**`data-model --columns` and `--roles`.** `--columns` lists each table's columns under its
name, `PK` / `FK` marked. `--roles roles.yml` corrects the classifier with flat
`table: role` lines; the table is drawn `set by you`, the review rules use the new role,
and a table the schema does not define is an error. The file is a small YAML subset, since
the plugin carries no YAML parser; anything richer is refused with the line number.

**A label's line breaks are kept.** `fit_text()`, and so every `pack()` and `pipeline()`
node, joined a label's lines into one run and re-wrapped it, so a label written as
several lines came out as one jumbled paragraph. Each line is now wrapped on its own;
a label without a newline is wrapped exactly as before.

## plugin `v2.8.0` — 2026-11-06

**Draw and review a data model from its SQL.** `data-model --from-ddl schema.sql -o out/`
reads `CREATE TABLE` and `ALTER TABLE ... ADD ... FOREIGN KEY` (PostgreSQL and generic
SQL, standard library only) and draws one node per table and one arrow per foreign key
through the same layout and gates as every other diagram.

Each table is classified as a fact, dimension, bridge or unknown, coloured by role, and
labelled with a confidence; the glossary gives the reason for every call. Five review
rules (`grain`, `surrogate-key`, `scd2`, `orphan-fk`, `snowflake`) draw their findings as
amber notes joined to the table they concern. The roles and the `scd2` rule are
heuristics on names and structure. The fact sits in one column with its dimensions
beside it rather than at the centre of a star. Not an MCP tool yet.

## plugin `v2.7.0` — 2026-10-21

**The viewer's download button saves your edits.** The page is a full editor, but the
button serialised the scene embedded when it was built, so a reader who edited the
page got back the file they were sent. It now saves the scene as it stands in the
page. A refresh or a closed tab with unsaved edits asks first.

**A fan-out can be drawn as a bus.** `PackOptions(edge_style="orthogonal")`, or
`"edge_style": "orthogonal"` in `graph.json`, draws every edge between neighbouring
layers as a trunk beside its source with a square branch into each target. A
one-to-eight fan-out lays out clean in both directions, with no leg cutting a box and
no detour round the diagram. A bus nested inside a wider one never crosses it.

**Labels stay readable on dark fills.** A shape's label with no colour of its own is
now white wherever black would fall short of WCAG's 4.5:1 against the fill. A colour
you give still wins.

**`pack()` nodes take a `font`**: a `Font`, a size, or a `{size, color, align}` dict in
`graph.json`. The box is sized at that size.

**Decision diamonds fit their question.** A `diamond` or `decision` node is sized so
its wrapped label sits inside the rhombus rather than inside its bounding box.

**Every `pack()` shape carries its node id** in `customData`, which survives an edit in
the viewer, so an edited scene can be matched back to the description that drew it.

**The plugin-cache resolver honours `CLAUDE_CONFIG_DIR`.** The import snippet in
`builder_api.md` and the fallback in every `discover` stub looked only under
`~/.claude`, and failed for a non-default config directory.

`REQ-EXCALIDRAW-858` holds the per-node contract with seven cases; `REQ-EXCALIDRAW-848`,
`-853` and `-854` gained one or two cases each.
## plugin `v2.6.0` — 2026-10-13

**The licence is Apache 2.0.** `LICENSE` holds the Apache License 2.0 and `plugin.json` says
`Apache-2.0`, the same licence as the other plugins by the same author. Releases up to v2.5.0
stay under MIT. The bundled Excalidraw, React and React DOM builds keep their own MIT licences.
No code change.

## plugin `v2.5.0` — 2026-10-03

**SVG export, on request.** A scene can now also be written as a standalone `<name>.svg`,
to go into a document or a slide: `save(svg=True)`, `scene --from-json ... --svg`,
`render <scene> --svg`, and `build_scene` with `svg: true`. It is opt-in, so the two-file
output existing callers rely on does not change, and `save()` returns a third path only
when asked.

The SVG is drawn from the scene's elements alone, so it also works on a scene edited on
excalidraw.com, and the same scene gives the same text. Lines come out clean, not
hand-drawn: the rough outlines are Excalidraw's own renderer. The hand-drawn and code
typefaces are embedded from the vendored fonts, so a browser shows them. There is no PNG;
rasterising that text needs a font rasteriser the standard library does not have.

`REQ-EXCALIDRAW-856` holds the contract, with six cases.

## plugin `v2.4.3` — 2026-10-03

**Tool annotations on the MCP server.** The directory policy asks an MCP server to give
every tool all of its applicable annotations, and the four tools had none. All four now
declare `readOnlyHint`, `destructiveHint`, `idempotentHint` and `openWorldHint`.
`build_scene`, `render_html` and `discover_repo` write files and replace a same-named
one, so they are destructive and not read-only; `graph_schema` is read-only. All four
are idempotent, since the same input writes the same bytes, and none is open-world.

**A privacy section in the README**, which the policy asks to be reachable from a link.

## plugin `v2.4.2` — 2026-10-03

**A listing icon.** The directory asks for a square PNG, and the icon can be set only
when the plugin is first saved or submitted, so it goes in before the first submission:
`.claude-plugin/icon.png`, 512 by 512.

**README corrections found while reading the directory policy.** `discover_repo` always
writes a starter script, to `make_diagram.py` in the server's working directory unless
given a path, and overwrites a file of that name; the README had said it wrote only when
given a path. It now also says where the local MCP server runs, and that a generated
starter script falls back to the plugin cache to find the builder. No code changed.

## plugin `v2.4.1` — 2026-10-03

**A README inside the plugin folder.** The directory listing shows the README that sits
beside `.claude-plugin/plugin.json`, and until now only the repository root had one. It
says what the plugin runs, what it writes and that it makes no network call, and it
records where the vendored renderer comes from and how to reproduce its one edit.

**macOS and Linux without `python`.** The MCP server starts with `python`, which a system
that ships only `python3` does not have. No single command works on every system, so
`.mcp.json` is unchanged and both skill contracts now say to run the builder with
`python3` where there is no `python`. The README explains how to get the MCP tools too.

**Independence from Excalidraw.** The README now says the plugin is not affiliated with
Excalidraw, writes its open file format and bundles its MIT-licensed library.

**A way to send feedback.** `homepage` in the manifest, a Feedback section in the README,
and two issue forms: something went wrong, and a diagram type you wish it had.

## plugin `v2.4.0` — 2026-09-21

**Three more diagram types, as worked examples.** No new builder primitive; each
generator asserts what the gates cannot see.

- `make_sequence_diagram.py`: participants, lifelines, requests and dashed replies, a
  self-call and an `alt` fragment. It asserts every message ends on a lifeline and
  messages run strictly downwards.
- `make_state_machine.py`: an order's life cycle through `pack()`, with a group and a
  back transition. It asserts every state is reachable and only final states are dead
  ends.
- `make_er_diagram.py`: tables as a header box over a column box, relationships as
  headless arrows labelled `1 x : N y`. It asserts foreign keys and relationships agree.

Worked example 8 in `references/worked_examples.md` is the recipe for all three, and
`mermaid_to_graph.md` now points sequence and ER diagrams at it instead of saying to
flatten them into a flow.

**Two builder bugs the examples found.**

- `frame(paint=Paint(fill="<role>"))` ignored `Scene(roles=…)`: `box()` resolved a
  role name, `frame()` did not, so a legended fragment colour never showed.
- A routed edge between neighbouring layers sent both legs through the same channel.
  The connector went down and came straight back up one vertical line, a stub instead
  of a loop. It now leaves through the far side of its source and enters through the
  near side of its target.

## plugin `v2.3.0` — 2026-09-21

**Group frames are no longer invisible to the gates.** `enclose()` now records which
ids a frame was drawn around, and two existing checks read it:

- `check_overlaps()`, the hard `overlap` gate, also names a box that sits inside a frame
  (or on its caption) without having been enclosed. A frame that claims a box it does
  not group now fails `save()` by default, like any other overlap.
- `check_arrow_crossings()`, the `crossing` gate, also names any arrow or routed line
  that runs through a frame caption.

Still seven gates; no gate changed its name or default.

**`pack()` stops producing both.** A non-member in a layer a group's frame spans is
pushed along its layer out past the frame. The arrows are drawn before the frames, so
`enclose()` can put the caption where nothing crosses it. It tries the top centre, then
the widest clear stretch above or below the frame, wrapped onto two or three lines if
that is what fits. Routed lanes keep a frame's width clear of groups.

`layout_corpus/` gains `group_with_outsider_tb` and `caption_under_fan_out_tb`. With
the new checks and the old `pack()`, the corpus reads nine hits (three captions crossed,
six boxes in frames that do not hold them); with the new `pack()`, none.

**Minor bump because the `overlap` gate is stricter.** A hand-written generator that
placed a box inside an `enclose()` frame without enclosing it now raises. Enclose it,
move it, or pass `Gates(overlap="warn")`. Every example in this repo stays clean.

## plugin `v2.2.1` — 2026-09-21

**A group on the first row no longer fails `scene --from-json`.** The title and subtitle
sat at a fixed height above `y = 0`, but a group frame that encloses first-row nodes puts
its label above `y = 0` too, so any description with a subtitle and such a group was
refused by the `text_overlap` gate. They now sit above the highest thing `pack()` drew.

**A layout ratchet.** `TestLayoutRatchet` packs the fourteen graphs in
`scripts/layout_corpus/`, which were written to stress the layout (a K5, a 12-way fan-out
and fan-in, skip edges, shared group members, forced tiny boxes, the case above) and not
to pass. It counts what each of the seven checks finds and compares that with
`_baseline.json`: a count that rises fails as a regression, and a count that falls must
be re-recorded (`EXCALIDRAW_RATCHET_UPDATE=1`) so the gain cannot slip back. The baseline
is not all zeros, so a change that silences a check shows up too.

## plugin `v2.2.0` — 2026-09-20

**Mermaid in, without a parser.** `references/mermaid_to_graph.md` says how a Mermaid
flowchart maps onto `graph.json`, node shape by node shape and edge kind by edge kind,
with a worked line-by-line translation and an explicit list of what Mermaid expresses and
this builder does not. The model reads it and writes the graph; nothing parses anything,
so there is no second authoring language to keep working. The output is a real editable
scene, which is what the official JS bridge gives up on for every diagram type but
flowcharts.

**The timing generators are examples now.** `make_timing_diagrams.py` and
`make_autosar_timing.py` moved from `docs/` into
`plugin/skills/excalidraw-diagram/examples/`, so `TestExampleDiagrams` runs them and
holds them to the same seven checks as every other example — they were outside the suite
while being cited as proof that timing diagrams need no builder primitive. Worked example
7 in `references/worked_examples.md` is the recipe: one unbound `path(heads="none")` per
signal, one `box()` per bus cell, and your own asserts, because three of the seven gates
never see an unbound trace.

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
