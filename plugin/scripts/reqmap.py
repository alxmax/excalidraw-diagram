#!/usr/bin/env python3
"""reqmap — requirement manager engine (stdlib only).

Subcommands:
  init              first-use bootstrap: scaffold requirements/ + .reqmapignore, draft
                    requirements from existing code, build the lock + map, print next steps
  new AREA-NAME-NNN   scaffold a requirement from the built-in template (--from-todo seeds from TODO.md)
  scan              list code members (implements/generated-from/... tags) per capability
  gate              the gate: link sync + drift + test-link integrity; exit non-zero on error (pre-commit/CI)
  sync              rescan + advance the drift baseline + regen the map and a committed _findings.md (--accept-drift for an edited contract)
  map               generate requirements/_map.md (Mermaid) + _map.json (graph) [+ _map.html viewer]
  site              inject/refresh engine-owned regions into a presentation page (--attach/--regions/--diagram)
  export            emit the registry graph as requirements/_map.json (for a front-end)
  next              terminal 'what should I do next': counted, actionable risk buckets
  lint [--strict]   readability/structure check on non-draft requirements (warn; --strict fails on errors)
  show <ID>         consolidated dossier for one requirement (contract, deps, members, risk)
  dupes [--threshold T]  flag requirement pairs with overlapping contracts (TF-IDF cosine)
  health [--json]   corpus coherence score + component counts (--json for a CI badge)
  draft             draft requirements from legacy code (status: draft, risk-scored)
  plan              read-only JSON capability-extraction plan (writes no .md)
  findings          aggregate open verify-intent items into requirements/_findings.md
  design            advisory design candidates in the repo's code, any language (four OOP pillars + metrics + standards; never the gate)
  confirm <ID>      flip a reviewed requirement's status to confirmed (one frontmatter edit)
  review [ID]       emit a JSON review plan (intent/contract/acceptance/anchors) for AI-assisted quality review
  translate [--to ro|en]  manual, opt-in: cache a `claude -p` translation of the corpus's
                    majority-language requirements into requirements/_i18n/<locale>.json.
                    Never called by gate/sync/lint/map/the pre-commit hook.
  check             DEPRECATED alias for `gate` (report) / `sync` (with --update-lock); removed in v4.0.0

Layout on disk (relative to repo root, override with --root / --reqs / --code):
  requirements/*.md     the source of truth (markdown + YAML-ish frontmatter)
  <code>/**            scanned for tags like:  # implements: <ID>
"""
import argparse, ast, contextlib, errno, fnmatch, hashlib, io, json, math, os, re, subprocess, sys

ROLES = ("implements", "generated-from", "validated-against", "tested-by")
# Both tag patterns are BUILT from ROLES rather than repeating it. The three used to be
# maintained by hand, which made ROLES look authoritative while driving nothing: adding a
# role there changed no behaviour, and the real vocabulary lived inside two regex literals.
_ROLE_ALT = "|".join(ROLES)
# the (?<![\w-]) left boundary stops substring matches like `reimplements:` or
# `x-implements:` from being picked up as a real `implements:` tag
_ID_PAT = r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+"
TAG_RE = re.compile(r"(?<![\w-])(" + _ROLE_ALT + r")\s*:\s*(" + _ID_PAT + r")")
# A single tag may bind several requirements via a comma-separated id list (one
# `<!-- generated-from: ... -->` listing several ids) — used for a whole-system doc
# generated from many requirements, so a contract drift on ANY of them lists the doc
# to re-sync. TAG_RE (single id) stays for callers that only need the tag's start
# position; TAG_LIST_RE captures the whole id list, which _findall_tags expands.
TAG_LIST_RE = re.compile(r"(?<![\w-])(" + _ROLE_ALT + r")\s*:\s*("
                         + _ID_PAT + r"(?:\s*,\s*" + _ID_PAT + r")*)")
_ID_RE = re.compile(_ID_PAT)


def _findall_tags(text):  # implements: REQ-VLEVEL-944
    """Like ``TAG_RE.findall`` but expands a comma-separated id list into one
    ``(role, id)`` pair per id, so ``generated-from: A-1, B-2`` yields two members."""
    out = []
    for role, idlist in TAG_LIST_RE.findall(text):
        for cap in _ID_RE.findall(idlist):
            out.append((role, cap))
    return out


# Phantom-member exclusion helpers used in _scan_file_tags
_FENCE_RE = re.compile(r'^(`{3,}|~{3,})')   # CommonMark fence opener/closer
# NOTE: only handles single-backtick spans; double/triple-backtick spans (CommonMark-valid)
# are not filtered. No instances exist in this corpus, but this is a known gap.
_BACKTICK_RE = re.compile(r'`[^`]*`')         # inline backtick span (strip before tag search)
# Per-acceptance-criterion coverage tag, placed in a test: `# verifies: REQ-X#AC-1`.
# Finer-grained sibling of `tested-by` — links ONE test to ONE labelled criterion so
# "Verifiable" becomes machine-checked per criterion, not just per requirement. The
# `#AC-N` suffix is what distinguishes it from a plain requirement reference.
AC_VERIFY_RE = re.compile(r"(?<![\w-])verifies\s*:\s*(" + _ID_PAT + r")#((?:CASE|AC)-\d+)")
# Verification level on a `tested-by:` tag, written `# tested-by: <ID> @integration`.
# The id is spelled `<ID>` here on purpose: a real-looking id in a PLAIN COMMENT would be
# scanned as an actual tag. `_scan_file_tags` strips backticked spans only on the .md/.html
# path; on the code path its guard is `_strip_py_strings`, which masks string literals and
# leaves comments alone. Docstrings are safe; comments are not.
# The level applies to the whole tag, so a comma-separated id list shares it — the only
# unambiguous reading, and it matches how TAG_LIST_RE already groups ids. The suffix is
# invisible to TAG_RE/TAG_LIST_RE, so an older vendored engine reads a levelled tag,
# resolves the id, and ignores the level (ARCH-VLEVEL-037).
TEST_LEVELS = ("unit", "integration", "system")
TEST_LEVEL_RE = re.compile(
    r"(?<![\w-])tested-by\s*:\s*(" + _ID_PAT + r"(?:\s*,\s*" + _ID_PAT + r")*)"
    r"\s*@(" + "|".join(TEST_LEVELS) + r")\b")
CODE_EXTS = (".py", ".js", ".ts", ".tsx", ".jsx", ".c", ".cpp", ".h", ".hpp",
             ".cc", ".java", ".go", ".rs", ".html", ".css", ".sql", ".yaml", ".yml",
             ".sh", ".tf",
             ".prisma", ".graphql", ".proto",   # schema files: a consumer tagged schema.prisma and nothing read it
             ".scss", ".sass", ".less", ".vue", ".svelte", ".mjs", ".cjs", ".mts", ".cts",   # frontend run: excalidraw's ONLY stylesheet format was .scss
             ".cs", ".php", ".rb", ".kt", ".kts", ".swift", ".scala", ".ex", ".exs", ".dart", ".toml",   # infra/backend runs
             ".md")  # .md scanned for tags so prose capabilities (prompts/specs) can be members

# Extensionless filenames scanned by exact basename match (no case-fold — CODE_EXTS
# is suffix-based and case-sensitive too, so this stays consistent). Git hook names
# (pre-commit, pre-push, ...) are as conventional and unambiguous as Dockerfile/
# Makefile — a repo's own .githooks/ scripts are exactly the kind of scannable
# pipeline code v2.9's "tag your own pipeline" item covers; an unrelated file that
# happens to share one of these names is a harmless no-op scan (no tag = no member).
BASENAME_CODE_FILES = {"Dockerfile", "Makefile",
                       "Caddyfile", "Jenkinsfile", "Procfile", "Vagrantfile",
                       "pre-commit", "pre-push", "pre-receive", "post-receive",
                       "commit-msg", "prepare-commit-msg", "post-checkout", "post-merge"}

# A repo whose source language the default set doesn't cover can declare extra
# scannable extensions via the REQMAP_EXTRA_CODE_EXTS env var — comma-separated,
# leading dot optional (e.g. "REQMAP_EXTRA_CODE_EXTS=.foo,bar"). Merged here so
# every scan site (endswith(CODE_EXTS)) picks them up without forking the engine.
_extra_exts = tuple(
    (e if e.startswith(".") else "." + e)
    for e in (x.strip() for x in os.environ.get("REQMAP_EXTRA_CODE_EXTS", "").split(","))
    if e.strip()
)
if _extra_exts:
    CODE_EXTS = CODE_EXTS + _extra_exts


def _is_code_file(fn):  # implements: ARCH-SCAN-002
    """True if fn should be scanned as code: matches CODE_EXTS, an extensionless
    basename like Dockerfile/Makefile, or a Dockerfile variant (`Dockerfile.dev`,
    `Dockerfile.converter` — a consumer tagged one and nothing read it)."""
    return fn.endswith(CODE_EXTS) or fn in BASENAME_CODE_FILES or fn.startswith("Dockerfile.")

# ---- prose auto-draft classification (cmd_extract) ----
# These buckets govern AUTO behavior (drafting) ONLY. scan_members still honors an
# explicit tag on ANY file, regardless of bucket — buckets never suppress a real tag.
PROSE_EXTS = (".md", ".html")
# Bucket 1 — meta/boilerplate: never auto-drafted, never sync-checked. Basename match.
META_IGNORE_NAMES = {"CLAUDE.md", "AGENTS.md", "GEMINI.md", "CONTRIBUTING.md",
                     "SKILL.md", "TODO.md", "CHANGELOG.md"}

VALID_STATUS = {"draft", "baseline", "in-progress", "implemented", "confirmed", "deprecated"}
# 'need'      = an upstream stakeholder need, satisfied-by (not implemented-by)
# 'aggregate' = a requirement whose implementation IS its dependencies' — it adds no
#               behavior of its own, it asserts that N capabilities work together
#               (an MVP acceptance requirement is the archetype). Covered by its
#               depends_on edges, the mirror of how a need is covered by satisfies.
VALID_LAYER = {"bus", "feature", "need", "aggregate"}
# The V-model specification level, an axis ORTHOGONAL to `layer:` and deliberately not a
# rename of it. `layer:` says how a requirement sits in the dependency graph (a `bus` is
# defined by fan-in; a `need`/`aggregate` is covered by an edge instead of a tag, which is
# what IMPL_EXEMPT_LAYERS keys on). `level:` says how abstract it is. They are independent:
# an `architecture` requirement OWNS code, so it must stay gate-checked, whereas `aggregate`
# is exempt precisely because it owns none — which is why `architecture` cannot be an alias
# of `aggregate`. Optional and absent by default: a corpus that never adopts it behaves
# exactly as before.
VALID_LEVEL = {"system", "architecture", "code"}   # implements: ARCH-LEVEL-051
# The rungs of the V: the verification level that discharges each specification level.
# Left arm `level:` <-> right arm `tested-by: <ID> @<level>`. Read only when the author has
# declared BOTH sides — a requirement with no `level:`, or with no levelled test link, is
# never judged, so the rule is silent on arrival in every existing corpus.
LEVEL_TEST_PAIR = {"system": "system", "architecture": "integration", "code": "unit"}
# Hierarchy breadth on the `satisfies:` graph: a parent normally carries between these many
# children. Warn-only, and silent on a leaf — a requirement nothing satisfies is not a
# malformed parent, it is simply not a parent.
LINT_FANOUT_MIN = 5
LINT_FANOUT_MAX = 20
# Per-level CEILINGS, keyed on the PARENT's `level:`. `None` means no floor at that level.
# One band for the whole hierarchy was wrong in both directions: an architecture requirement
# groups detailed design, where a dozen children is ordinary, while a system need groups
# architecture, where ten is already a lot.
#
# The floor is gone because the corpus's own shape refutes it (ADR-0023 — read it before
# restoring one). Measured at b0ce92b over the `satisfies:` graph, the old uniform band
# produced 10 findings: 7 below the floor and 3 above the ceiling. The floor is
# anti-correlated with corpus quality — several of those 7 appeared *because* commits
# e254a34 and 72213fc folded away leaves that should not have existed, dropping their
# parents from 5 children to 4. A check that gets louder as the corpus gets better is
# measuring the wrong thing. In this corpus a child count is also a CLAUSE count, since the
# `satisfies:` children were derived roughly one per Description bullet, so the floor
# measures what `ac-count-high` already measures on the other axis. And the distribution
# has no floor to find: 3:1, 4:6, 5:5, 6:8, 7:5, 8:9 is continuous. ADR-0019 pre-committed
# the response: "the band is wrong for this shape of corpus and should be widened or
# dropped — not lived with."
#
# NOTE: an earlier version of this comment claimed "a blind review confirmed 0 of 9 as
# real". That figure was withdrawn — no commit ever produced 9 FLOOR findings (4, then 6,
# then 7 as the corpus changed), and the one flag it called plausibly real, ARCH-CHECK-006,
# is a CEILING finding. The floor rests on the distribution and the anti-correlation above,
# both of which reproduce from a sha and a filter.
#
# The ceiling stays: the distribution DOES break at 19 -> 22 -> 23 -> 32, and the single
# finding above it is ARCH-CHECK-006 at 32, which is real and left standing.
# Measured after this change: 1 finding over 72 lintable requirements.
# A parent with no `level:` keeps the uniform 5-20 band — the level axis stays doubly
# opt-in (ADR-0019), so a repo that never declares it sees exactly what it saw before, and
# this corpus's evidence is not silently imposed on a corpus shaped differently.
#
# `system`'s ceiling is ten again (ADR-0025 restores the 3-tier split ADR-0024 had
# collapsed): a system need is satisfied by a handful of architecture capabilities, and
# the grouping nodes that briefly sat at `level: system` are back at `architecture`,
# whose own (None, 30) never moved.
LINT_FANOUT_BANDS = {"system": (None, 10), "architecture": (None, 30)}  # implements: REQ-FANOUT-852
MILESTONE_RE = re.compile(r"^v\d+(\.\d+)*$")  # roadmap milestone shape: v1, v1.0, v1.14 — validated (warn) in the gate
ENFORCED = {"in-progress", "implemented", "confirmed"}
# System Map declutter: hide depends_on edges into a node this many capabilities
# depend on (a hub) — the bus is hidden regardless of count. Full graph stays in
# the Dependency Map tab.
SYSTEM_HUB_FANIN = 8

# Scripted, deterministic guidance per risk signal — surfaced in the Risk tab,
# the detail panel, and the _map.md risk table so a flagged requirement comes
# with a concrete next action, not just a color.
RISK_ADVICE = {
    "unimplemented": "Confirmed but no code linked: tag the implementing code "
                     "`# implements: <ID>`, or drop status back to in-progress/draft "
                     "until it is built. A confirmed requirement must point to code.",
    "unreviewed": "Draft/baseline, not yet validated: review the contract, wire its "
                  "`tested-by` tests, then promote to `confirmed`. Until then it is "
                  "tracked, not enforced.",
    "untested": "Implemented but no `tested-by` member: write an acceptance test and tag "
                "it `# tested-by: <ID>`, or set `test_exempt: <reason>` in the frontmatter "
                "to acknowledge it intentionally and silence this signal.",
    "unverified-intent": "Has open `## Verify intent` question(s): run "
                         "`reqmap.py sync`, resolve each in `requirements/_findings.md`, "
                         "then fold the answer into the Contract or delete the bullet.",
}

# Bumped on any change to this engine. `check` warns a seeded repo when its
# vendored copy is older than the installed plugin's. ISO date with an optional
# `.N` same-day revision suffix (YYYY-MM-DD[.N]): lexicographic order ==
# chronological order, so a plain string compare is enough.
MAP_ENGINE_VERSION = "2026-09-06.15"

# Declared support floor, deliberately equal to the OLDEST version CI actually runs
# (the `tests` matrix in .github/workflows/ci.yml). The code itself needs only 3.7
# (subprocess.run's capture_output/text, stream.reconfigure), but 3.7 and 3.8 are not
# installable on current GitHub runners, so promising them would be a claim nothing
# proves - the failure mode this project exists to prevent. Move this only together
# with the matrix that tests it.
MIN_PYTHON = (3, 9)  # implements: REQ-PYFLOOR-902


def _python_floor_error(version_info=None):  # implements: ARCH-PYFLOOR-040  # implements: REQ-PYFLOOR-902
    """Return a message when the interpreter is below MIN_PYTHON, else None.

    A pure predicate rather than an inline exit, so a test can pin the floor on any
    interpreter - a test process cannot spawn a 3.8 to watch the real thing happen.
    Note what this cannot catch: the module uses f-strings, so an interpreter below
    3.6 fails at COMPILE time and never reaches this check. 3.6-3.8 - the range a
    real user plausibly still has - get the readable message. ASCII only: a legacy
    Windows codepage is exactly where an old interpreter turns up.
    """
    major, minor = tuple(version_info or sys.version_info)[:2]
    if (major, minor) >= MIN_PYTHON:
        return None
    return ("reqmap needs Python %d.%d or newer (running %d.%d). The engine is stdlib-only, "
            "so a newer interpreter is the entire fix - no install, no dependencies: re-run "
            "with one, e.g. `python%d.%d scripts/reqmap.py ...`."
            % (MIN_PYTHON[0], MIN_PYTHON[1], major, minor, MIN_PYTHON[0], MIN_PYTHON[1]))

# ---------------------------------------------------------------------------
# COMMANDS registry — single source of truth for the CLI command set.
# Each entry describes one user-facing command: its summary, the positional
# argument it accepts (or None), and the flags it owns (subset of the shared
# argparse flag pool; global flags --root/--reqs/--code/--cache are omitted).
# Later tasks will derive argparse choices, tool_definition.json, and a
# markdown command table from this registry — do NOT add behaviour here.
# ---------------------------------------------------------------------------
# implements: ARCH-CMDREGISTRY-033
COMMANDS = {
    "init": {
        "summary": (
            "First-use bootstrap: scaffold requirements/ and .reqmapignore if missing, "
            "draft requirements from existing code and prose, build the lock and map, and "
            "print guided next steps. Idempotent — safe to re-run; never clobbers an "
            "existing .reqmapignore. --plan emits the extraction plan as JSON and writes no "
            "requirement files, for looking before authoring. "
       
        ),
        "arg": None,
        "params": [
            {
                "name": "plan",
                "flag": "--plan",
                "type": "bool",
                "help": (
                    "Emit the extraction plan as JSON instead of writing requirement files."
                ),
            },
            {
                "name": "out",
                "flag": "--out",
                "type": "str",
                "help": (
                    "With --plan: write the plan JSON here ('-' or omitted = stdout)."
                ),
            },
            {
                "name": "md_glob",
                "flag": "--md-glob",
                "type": "str",
                "help": (
                    "With --plan: also scan these non-code globs for capabilities (repeatable)."
                ),
            },
            {
                "name": "wipe",
                "flag": "--wipe",
                "type": "bool",
                "help": (
                    "Hard-reset: delete all non-generated requirements and strip "
                    "membership tags from source files before re-extracting."
                ),
            },
            {
                "name": "no_site",
                "flag": "--no-site",
                "type": "bool",
                "help": "Skip the final site step (scaffolding docs/architecture.html).",
            },
        ],
    },
    "new": {
        "summary": (
            "Scaffold a new blank requirement from the built-in template. "
            "Use --from-todo and --id together to pre-fill from a TODO.md item instead."
        ),
        "arg": "AREA-NAME-NNN",
        "params": [
            {
                "name": "id",
                "flag": "--id",
                "type": "str",
                "help": (
                    "Requirement ID in AREA-NAME-NNN format (e.g. AUTH-LOGIN-001). "
                    "Required when using --from-todo."
                ),
            },
            {
                "name": "from_todo",
                "flag": "--from-todo",
                "type": "str",
                "help": (
                    "Scaffold the requirement from a TODO.md item matched by this name "
                    "(use with --id; add --mark-done to flip the item to [x])."
                ),
            },
            {
                "name": "mark_done",
                "flag": "--mark-done",
                "type": "bool",
                "help": (
                    "Also flip the matched TODO.md item to [x] (off by default). "
                    "Only used with --from-todo."
                ),
            },
        ],
    },
    "gate": {
        "summary": (
            "The commit/CI verdict, and every read-only question you can ask the corpus. "
            "Bare, it verifies that every code tag resolves to a real requirement, that "
            "every confirmed requirement has at least one implements: member, and that "
            "drift has not been introduced since the last sync, then checks requirement "
            "readability and map freshness. Exits non-zero on link-sync errors only. Never "
            "writes anything. The mode flags answer one question each instead of running "
            "the verdict: --audit for the whole problem report, --risk for what to do next, "
            "--show for one requirement's dossier, --search to rank by relevance, --dupes "
            "for overlapping contracts, --design for the code review, --review and "
            "--implement for the two machine-readable plans. "
       
        ),
        "arg": None,
        "params": [
            {
                "name": "mode_audit",
                "flag": "--audit",
                "type": "bool",
                "help": (
                    "Print every pass that discovers a problem as one report: the gate, corpus risk, duplicate contracts, design signals and tag coverage. The exit code still comes from the gate alone."
                ),
            },
            {
                "name": "mode_risk",
                "flag": "--risk",
                "type": "bool",
                "help": (
                    "Print the corpus risk snapshot and the actionable signals, most urgent first."
                ),
            },
            {
                "name": "mode_show",
                "flag": "--show",
                "type": "str",
                "help": (
                    "Print one requirement's dossier: intent, contract, dependencies both ways, code members with file:line, open questions and risk signals."
                ),
            },
            {
                "name": "mode_search",
                "flag": "--search",
                "type": "str",
                "help": (
                    "Rank requirements by lexical relevance to a free-text query."
                ),
            },
            {
                "name": "mode_dupes",
                "flag": "--dupes",
                "type": "bool",
                "help": (
                    "Rank requirement pairs whose contracts overlap, most similar first."
                ),
            },
            {
                "name": "mode_design",
                "flag": "--design",
                "type": "bool",
                "help": (
                    "Print the advisory design review of the code. Never part of the verdict."
                ),
            },
            {
                "name": "mode_review",
                "flag": "--review",
                "type": "str",
                "help": (
                    "Emit the deterministic review plan for one requirement, as JSON."
                ),
            },
            {
                "name": "mode_implement",
                "flag": "--implement",
                "type": "str",
                "help": (
                    "Emit the implementation brief for one requirement: obligations, required tags, similar existing code."
                ),
            },
            {
                "name": "show_all",
                "flag": "--all",
                "type": "bool",
                "help": (
                    "With --risk: expand every bucket instead of the top few."
                ),
            },
            {
                "name": "untagged",
                "flag": "--untagged",
                "type": "bool",
                "help": (
                    "With --risk: report membership-tag coverage per directory."
                ),
            },
            {
                "name": "as_badge",
                "flag": "--badge",
                "type": "bool",
                "help": (
                    "With --risk: print the coherence score as a badge string."
                ),
            },
            {
                "name": "threshold",
                "flag": "--threshold",
                "type": "str",
                "help": (
                    "With --dupes: override the similarity threshold."
                ),
            },
            {
                "name": "top",
                "flag": "--top",
                "type": "int",
                "help": (
                    "With --search or --dupes: how many results to print."
                ),
            },
            {
                "name": "strict",
                "flag": "--strict",
                "type": "bool",
                "help": (
                    "Promote drift and test-link integrity warnings to errors. "
                    "Useful in CI when all requirements are confirmed."
                ),
            },
            {
                "name": "json",
                "flag": "--json",
                "type": "bool",
                "help": "Emit structured JSON output instead of human-readable text.",
            },
            {
                "name": "since",
                "flag": "--since",
                "type": "str",
                "help": (
                    "Scope the gate to requirements whose member files changed since "
                    "this git ref (e.g. 'main', 'HEAD~1')."
                ),
            },
        ],
    },
    "sync": {
        "summary": (
            "The write path. Rescan code members, advance the drift baseline, and "
            "regenerate the map, the findings file and the generated integration artifacts "
            "in one step. Run after editing requirement files or tagging new code members. "
            "--accept-drift is required when a confirmed or implemented contract changed. "
            "--suggest-verifies proposes per-criterion verifies: tags, and writes them with "
            "--apply. "
       
        ),
        "arg": None,
        "params": [
            {
                "name": "mode_retire",
                "flag": "--retire",
                "type": "list",
                "help": (
                    "Take these requirements out of service instead of confirming them. Accepts one id or many; a batch retires in an order computed from the graph, under one working-tree check. Prints the blast radius; writes nothing without --apply."
                ),
            },
            {
                "name": "delete",
                "flag": "--delete",
                "type": "bool",
                "help": (
                    "With --retire: also remove the block, its lock entries and its membership tags. Never a function body."
                ),
            },
            {
                "name": "do_apply",
                "flag": "--apply",
                "type": "bool",
                "help": (
                    "With --retire or --suggest-verifies: actually write the change. Without it, the run is a dry report."
                ),
            },
            {
                "name": "force",
                "flag": "--force",
                "type": "bool",
                "help": (
                    "With --retire: proceed even though dependents still point at this requirement, or the working tree is dirty. Dependents that are already deprecated, and those retired in the same call, never block."
                ),
            },
            {
                "name": "mode_suggest",
                "flag": "--suggest-verifies",
                "type": "bool",
                "help": (
                    "Propose per-criterion `verifies:` tags for tests already named after the criterion they check."
                ),
            },
            {
                "name": "findings",
                "flag": "--findings",
                "type": "bool",
                "help": (
                    "Also regenerate the aggregated open-questions file."
                ),
            },
            {
                "name": "accept_drift",
                "flag": "--accept-drift",
                "type": "str",
                "help": (
                    "Explicitly advance the baseline when a confirmed or implemented "
                    "contract changed. Required when those contracts differ from the "
                    "lock; sync exits non-zero without it. Takes an optional reason, "
                    "recorded in requirements/_driftlog.json so the waiver and its "
                    "justification land in the diff."
                ),
            },
            {
                "name": "strict",
                "flag": "--strict",
                "type": "bool",
                "help": "Promote drift and test-link integrity from warn to error.",
            },
        ],
    },
    "clarify": {
        "summary": (
            "Ask what a requirement has not answered yet: vague terms with no threshold, "
            "numbers with no unit, unbounded quantities, clauses with no case, a missing "
            "failure path. Read-only, always exit 0, never a gate rule. --decompose is the "
            "write half of the same question: it scaffolds an over-scoped requirement's "
            "clauses into requirements of their own. Run it before implementing, so the "
            "ambiguity is resolved in the requirement instead of guessed in code. "
       
        ),
        "arg": "AREA-NAME-NNN",
        "params": [
            {
                "name": "decompose",
                "flag": "--decompose",
                "type": "bool",
                "help": (
                    "Scaffold an over-scoped requirement's clauses into requirements of their own."
                ),
            },
            {
                "name": "levels",
                "flag": "--levels",
                "type": "bool",
                "help": (
                    "Propose a V-model rung for every requirement that declares no `level:`; "
                    "--apply writes them, each marked `level_source: auto`."
                ),
            },
            {"name": "as_json", "flag": "--json", "type": "bool",
             "help": "Emit the questions as JSON for an agent to answer."},
        ],
    },
}


def _cli_choices():  # implements: REQ-CMDREGISTRY-834
    """The CLI command names, derived from the registry (single source of truth)."""
    return list(COMMANDS)


def _generate_schema():  # implements: ARCH-CMDREGISTRY-033
    """Function-calling schema (OpenAI tool format) generated from COMMANDS.
    Returns a JSON string (indent=2, trailing newline) — byte-stable for the gate
    drift-compare. Internal commands are excluded from the AI-facing schema."""
    # A flag that takes many values must not be advertised as a lone string: a caller
    # that believes the schema sends one id and never learns the other eleven were
    # dropped. `list` is the only entry whose JSON shape needs an `items` clause.
    _TYPE = {"bool": "boolean", "str": "string", "float": "number", "int": "integer",
             "list": "array"}
    tools = []
    for name, spec in COMMANDS.items():
        if spec.get("internal"):
            continue
        props = {"root": {"type": "string",
                          "description": "Repo root where requirements/ lives; defaults to the current directory."}}
        if spec.get("arg"):
            props["arg"] = {"type": "string", "description": spec["arg"]}
        for p in spec["params"]:
            props[p["name"]] = {"type": _TYPE[p["type"]], "description": p["help"]}
            if p["type"] == "list":
                props[p["name"]]["items"] = {"type": "string"}
        tools.append({"type": "function", "function": {
            "name": "reqmap_" + name.replace("-", "_"),
            "description": spec["summary"],
            "parameters": {"type": "object", "properties": props, "required": []},
        }})
    return json.dumps(tools, indent=2, ensure_ascii=False) + "\n"


# Which moment of the workflow each verb belongs to. The registry is the CLI's
# single source of truth, so the grouping the help text and the viewer both show is
# declared here once rather than restated in each surface.
COMMAND_GROUPS = (
    ("author", ("init", "new", "clarify")),
    ("build", ("sync",)),
    ("read", ("gate",)),
)


def commands_manifest():  # implements: ARCH-CMDREGISTRY-033  # implements: REQ-CMDREGISTRY-963
    """The command registry as data, for any surface that documents the CLI without
    running it — the map viewer's command reference is the first. Derived from
    COMMANDS, so a command that exists is documented and one that does not, is not."""
    group_of = {}
    for group, names in COMMAND_GROUPS:
        for n in names:
            group_of[n] = group
    out = []
    for name, spec in COMMANDS.items():
        if spec.get("internal"):
            continue
        out.append({
            "name": name,
            "group": group_of.get(name, "read"),
            "summary": " ".join(spec["summary"].split()),
            "arg": spec.get("arg"),
            "flags": [{"flag": p["flag"], "help": " ".join(p["help"].split())}
                      for p in spec["params"]],
        })
    return out


def _generate_command_table():  # implements: REQ-CMDREGISTRY-834
    """A markdown table of the user CLI commands from COMMANDS, for the generated
    region inside SKILL.universal.md. Internal commands are excluded."""
    rows = ["| Command | What it does | Flags |", "|---|---|---|"]
    for name, spec in COMMANDS.items():
        if spec.get("internal"):
            continue
        flags = ", ".join("`" + p["flag"] + "`" for p in spec["params"]) or "—"
        rows.append("| `{}` | {} | {} |".format(name, spec["summary"], flags))
    return "\n".join(rows)


def _generate_command_list():  # implements: REQ-CMDREGISTRY-834
    """The command reference for SKILL.md, grouped the way COMMAND_GROUPS groups the
    verbs, as the bullet list that file has always used. SKILL.md is the contract an
    assistant reads when it meets the engine on a fresh repo, and a hand-kept list there
    documented `scan` after it was gone and five different verbs under the name `sync`.
    Rendered from the registry, a verb that exists is documented and one that does not,
    is not — the same guarantee the universal table already had."""
    group_of = {}
    for group, names in COMMAND_GROUPS:
        for n in names:
            group_of[n] = group
    titles = {"author": "Author", "build": "Build", "read": "Read"}
    lines = []
    for group, _names in COMMAND_GROUPS:
        members = [(n, s) for n, s in COMMANDS.items()
                   if not s.get("internal") and group_of.get(n, "read") == group]
        if not members:
            continue
        lines.append("**{}**".format(titles.get(group, group.title())))
        for name, spec in members:
            call = "python scripts/reqmap.py " + name
            if spec.get("arg"):
                call += " " + spec["arg"]
            flags = "; ".join("`{}` {}".format(p["flag"], " ".join(p["help"].split()))
                              for p in spec["params"])
            lines.append("- `{}` — {}{}".format(
                call, " ".join(spec["summary"].split()),
                " Flags: " + flags + "." if flags else ""))
        lines.append("")
    return "\n".join(lines).rstrip()


_REGION_RE = re.compile(r"(<!--##REQMAP:COMMANDS##-->)(.*?)(<!--##/REQMAP:COMMANDS##-->)", re.DOTALL)

# Every generated region, with the renderer that owns it. Both the writer and the
# freshness check walk this one list, so adding a surface here is the whole job.
_SKILL_REGIONS = (
    (("skills", "requirement-manager", "SKILL.universal.md"), _generate_command_table),
    (("skills", "requirement-manager", "SKILL.md"), _generate_command_list),
)


def _write_region(path, body):  # implements: REQ-CMDREGISTRY-834
    """Replace the delimited region body in `path`; prose outside is untouched."""
    # newline="" on both ends: read/write the file's own line endings verbatim so
    # regenerating the region never silently normalizes the WHOLE file's CRLF to LF on
    # read (universal-newline translation) with no re-translation on write.
    with open(path, encoding="utf-8", newline="") as f:
        text = f.read()
    # The body is generated with bare "\n". Written as-is into a CRLF file it left
    # the region LF inside CRLF prose. `_check_integration_fresh` reads the file with
    # universal newlines, so CRLF collapses to LF before the comparison and the gate
    # saw nothing wrong; git did, and every `sync` on Windows left a line-ending-only
    # diff. The body takes the file's own convention, the way `tool_definition.json`
    # already did.
    eol = "\r\n" if "\r\n" in text else "\n"
    body = body.replace("\r\n", "\n").replace("\n", eol)
    new = _REGION_RE.sub(lambda m: m.group(1) + eol + body + eol + m.group(3), text)
    if new != text:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(new)


def cmd_gen_integration(reqs_dir, code_root):  # implements: REQ-CMDREGISTRY-834
    """Write tool_definition.json (OpenAI function-calling schema) generated from COMMANDS."""
    plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tj_path = os.path.join(plugin_root, "tool_definition.json")
    schema = _generate_schema()
    # newline="" on both ends: read the file's existing CRLF/LF convention verbatim and
    # re-apply it explicitly before writing. _generate_schema() always joins with bare
    # "\n", so a bare text-mode write here would flip the whole committed CRLF file to LF
    # on any non-Windows host (os.linesep == "\n" there) even though the JSON is unchanged.
    eol = "\n"
    if os.path.exists(tj_path):
        with open(tj_path, encoding="utf-8", newline="") as f:
            if "\r\n" in f.read():
                eol = "\r\n"
    if eol == "\r\n":
        schema = schema.replace("\n", "\r\n")
    with open(tj_path, "w", encoding="utf-8", newline="") as f:
        f.write(schema)
    print("wrote tool_definition.json")
    for parts, render in _SKILL_REGIONS:
        skill = os.path.join(plugin_root, *parts)
        if os.path.exists(skill):
            _write_region(skill, render())
            print("wrote {} command region".format(parts[-1]))
    return 0


def _check_integration_fresh(plugin_root):  # implements: REQ-CMDREGISTRY-834
    """Return a list of stale generated artifacts (empty = fresh). Compares the
    committed tool_definition.json + the SKILL.universal.md command-table region
    against a fresh generation from the registry. Mirrors map --check. Artifacts
    that don't exist (e.g. a consumer repo that doesn't ship them) are skipped, so
    this never breaks a vendored-engine gate."""
    stale = []
    tj = os.path.join(plugin_root, "tool_definition.json")
    if os.path.exists(tj):
        with open(tj, encoding="utf-8") as _f:
            if _f.read() != _generate_schema():
                stale.append("tool_definition.json")
    for parts, render in _SKILL_REGIONS:
        skill = os.path.join(plugin_root, *parts)
        if os.path.exists(skill):
            with open(skill, encoding="utf-8") as _f:
                m = _REGION_RE.search(_f.read())
            if m and m.group(2).strip() != render().strip():
                stale.append("/".join(parts))
    return stale


# ---------- core types: the records every command reads ----------
# The engine passed bare dicts around for its whole life: a requirement was
# {"meta", "body", "path", "block"}, a gate finding was a formatted string. Every
# caller then re-derived the same facts its own way — which is how `gate`, `health`,
# `next` and `confirm` came to disagree about who is exempt (ADR-0015) and which
# requirement is oversize (v3.1.0). These two classes are dict subclasses on purpose:
# every existing `r["meta"]` and `f["check"]` keeps working, and the derived facts
# gain exactly one home.
class Requirement(dict):  # implements: ARCH-PARSE-001
    """One requirement block as loaded from disk. Behaves as the dict it always was
    (`r["meta"]`, `r["body"]`, `r["path"]`, `r["block"]`) and adds the facts every
    rule used to recompute from `meta` by hand."""
    __slots__ = ()

    @property
    def meta(self):
        return self.get("meta") or {}

    @property
    def body(self):
        return self.get("body", "")

    @property
    def id(self):
        return self.meta.get("id")

    @property
    def status(self):
        return self.meta.get("status")

    @property
    def layer(self):
        return self.meta.get("layer")

    @property
    def level(self):
        return self.meta.get("level")

    @property
    def enforced(self):
        return self.status in ENFORCED

    @property
    def confirmed(self):
        return self.status == "confirmed"

    @property
    def impl_exempt(self):
        return _impl_exempt(self.meta)

    def list(self, key):
        """A frontmatter field as a list (`depends_on`, `satisfies`, `lint_exempt`...)."""
        return _as_list(self.meta.get(key))

    def exempt_from(self, rule_id):
        """True when `gate_exempt:` names this rule's code (`gate_exempt: [RM016]`)."""
        return rule_id in set(self.list("gate_exempt"))


class Finding(dict):  # implements: ARCH-RULES-059  # implements: REQ-RULES-948
    """One gate finding: `rule` (RMnnn), `severity` (error|warn), `rid` (or None for a
    corpus-wide finding) and `msg` — the exact text the gate printed before findings
    had a shape. `str(f)` is that text; the code goes in front of it on the printed
    line and travels as its own key in `--json`."""
    __slots__ = ()

    def __init__(self, rule, severity, rid, msg):
        super().__init__(rule=rule, severity=severity, rid=rid, msg=msg)

    def __str__(self):
        return self["msg"]


class Rule(object):  # implements: ARCH-RULES-059
    """A gate rule: a stable code, a default severity, whether `--strict` promotes it
    to an error, and the function that yields `(rid, msg)` pairs over a GateContext.
    `only_source_repo` marks a rule about this repository's own dogfooding (the
    viewer's baked fixture) — it never runs inside a consumer repo."""
    __slots__ = ("id", "severity", "strict", "fn", "only_source_repo")

    def __init__(self, id, severity, strict, fn, only_source_repo=False):
        self.id, self.severity, self.strict, self.fn = id, severity, strict, fn
        self.only_source_repo = only_source_repo


GATE_RULES = []   # the bus: every consumer of "what is wrong with this corpus" reads it


def gate_rule(rule_id, severity, strict=False, only_source_repo=False):  # implements: ARCH-RULES-059  # implements: REQ-RULES-947
    """Register a gate rule. Codes are permanent identifiers (a consumer writes
    `gate_exempt: [RM016]`), so a retired rule's number is never reused."""
    def wrap(fn):
        if any(r.id == rule_id for r in GATE_RULES):
            raise ValueError("duplicate gate rule id " + rule_id)
        GATE_RULES.append(Rule(rule_id, severity, strict, fn, only_source_repo))
        return fn
    return wrap


def gate_rule_by_id(rule_id):
    """The registered rule with this code, or None — how a caller resolves the
    `RMnnn` in a finding back to the rule that produced it."""
    for r in GATE_RULES:
        if r.id == rule_id:
            return r
    return None


# ---------- parsing ----------
def _as_list(v):  # implements: ARCH-PARSE-001
    """Coerce a frontmatter value to a list: lists pass through, a bare scalar
    becomes a one-element list, empty/None becomes []. Guards callers that
    iterate list-valued keys (e.g. depends_on) against a string written without
    brackets being walked character-by-character."""
    if isinstance(v, list):
        return v
    return [v] if v else []


def _scalar_value(v):  # implements: ARCH-PARSE-001
    """One frontmatter scalar value. If it opens with a matching quote, take the
    quoted span verbatim — a '#' inside is DATA, and any text after the closing
    quote (e.g. an inline comment) is dropped. Otherwise drop a ' #' / leading '#'
    comment, preserving an embedded '#' with no leading space (issue#123)."""
    v = v.strip()
    if len(v) >= 2 and v[0] in "\"'":
        end = v.find(v[0], 1)
        if end != -1:
            return v[1:end]                       # quoted: inner '#' is data
    return re.split(r'(?:^|\s)#', v, 1)[0].strip()




def _parse_meta_lines(lines):  # implements: ARCH-PARSE-001  # implements: REQ-PARSE-891
    """The frontmatter key/value reader: scalars, inline `[a, b]` lists, and the
    block form (`key:` then indented `- item` lines). Takes the lines between the
    fences, so it never has to know where the block began."""
    meta = {}
    i = 0
    while i < len(lines):
        line = lines[i]; i += 1
        s = line.strip()
        if not s or s.startswith("#") or ":" not in line:
            continue
        k, v = line.split(":", 1)
        k, v = k.strip(), v.strip()
        if v.startswith("["):
            # inline list; tolerate a missing `]` (lenient) — a '#' inside
            # the brackets is data, a '#' after the close is a comment
            inner = v[1:v.index("]")] if "]" in v else v[1:]
            meta[k] = [x for x in (_scalar_value(x) for x in inner.split(",")) if x]
        elif not v:
            # block-style list: consume following indented `- item` lines.
            # No items -> keep the empty scalar (e.g. an unset superseded_by).
            items = []
            while i < len(lines) and lines[i].lstrip().startswith("- "):
                items.append(_scalar_value(lines[i].lstrip()[2:]))
                i += 1
            meta[k] = [x for x in items if x] if items else ""
        else:
            # A quoted value keeps an inner '#' verbatim; a bare value treats
            # '#' as a comment only at the start or after whitespace (so
            # "issue#123" is preserved). See _scalar_value.
            meta[k] = _scalar_value(v)
    return meta


def parse_frontmatter(text):  # implements: ARCH-PARSE-001  # implements: REQ-PARSE-891  # implements: REQ-PARSE-892
    """Return (meta_dict, body). Minimal YAML: scalars, inline [a, b] lists, and the
    block form (`key:` then indented `- item` lines). An inline list missing its
    closing `]` is parsed leniently rather than silently kept as a literal string."""
    meta, body = {}, text.lstrip("﻿")  # tolerate a stray UTF-8 BOM
    if not body.startswith("---"):
        return meta, body
    end = body.find("\n---", 3)
    if end == -1:
        return meta, body
    block = body[3:end]
    body = body[end + 4:].lstrip("\r\n")   # tolerate a CRLF close (\r\n--- )
    return _parse_meta_lines(block.splitlines()), body


# A requirement file may hold SEVERAL requirements, one per frontmatter block — a module
# in the DOORS sense: the architecture requirement, then the code requirements beneath it.
# A block begins at a `---` line immediately followed by `id:`. That lookahead is what makes
# the split unambiguous: a bare `---` is a markdown horizontal rule and a frontmatter close,
# both of which appear inside a body, and neither is followed by an id line.
_REQ_BLOCK_RE = re.compile(r"(?m)^---[ \t]*\r?\n(?=id:)")   # implements: ARCH-MODULEFILE-056


def split_requirement_blocks(text):  # implements: ARCH-MODULEFILE-056
    """Split one file's text into its requirement blocks, each ready for
    `parse_frontmatter`. A single-requirement file yields exactly one block, byte-identical
    to the whole text, so nothing about the existing corpus changes."""
    text = text.lstrip("\ufeff")
    parts = _REQ_BLOCK_RE.split(text)
    if len(parts) <= 1:
        return [text]
    out = []
    if parts[0].strip():                 # anything before the first block is a file preamble
        out.append(parts[0])
    for chunk in parts[1:]:
        out.append("---\n" + chunk)
    return out or [text]


def load_requirements(reqs_dir):  # implements: ARCH-PARSE-001  # implements: ARCH-MODULEFILE-056  # implements: REQ-PARSE-890  # implements: REQ-PARSE-892
    """Every requirement in the directory, keyed by id: `{id: {meta, body, path, ...}}`.
    One file may hold several blocks (ARCH-MODULEFILE-056); an unreadable or
    id-less file is skipped rather than raising, so one bad file cannot blind
    the whole corpus."""
    reqs = {}
    if not os.path.isdir(reqs_dir):
        return reqs
    for name in sorted(os.listdir(reqs_dir)):
        if not name.endswith(".md") or name.startswith("_"):
            continue
        path = os.path.join(reqs_dir, name)
        try:
            with open(path, encoding="utf-8-sig") as f:  # tolerate a UTF-8 BOM
                text = f.read()
        except (OSError, ValueError) as exc:   # ValueError covers UnicodeDecodeError
            print("WARNING: skipping unreadable requirement file {!r}: {}".format(name, exc),
                  file=sys.stderr)
            continue
        for _i, _blk in enumerate(split_requirement_blocks(text)):
            meta, body = parse_frontmatter(_blk)
            # only the FIRST block may fall back to the filename; a later block without an
            # explicit id is a malformed block, not a second requirement named after the file.
            # A file preamble (ARCH-MODULEFILE-056) can also land at index 0 when the real
            # block 0 is preceded by prose — but a preamble never starts with the frontmatter
            # delimiter '---' (parse_frontmatter's own test for "this text has frontmatter"),
            # so gating the fallback on that same test keeps prose from minting a synthetic id
            # that can collide with (and silently shadow) the real block 0's own id.
            rid = meta.get("id") or (
                os.path.splitext(name)[0] if _i == 0 and _blk.startswith("---") else None)
            if not rid:
                continue
            if rid in reqs:
                # two blocks claim the same id: keep the first (sorted) and warn, rather
                # than let the later one silently shadow it (the gate can't catch this —
                # the id still resolves, just to the wrong block).
                print("WARNING: duplicate requirement id {!r} in {!r} — keeping {!r}".format(
                    rid, name, os.path.basename(reqs[rid]["path"])), file=sys.stderr)
                continue
            reqs[rid] = Requirement(meta=meta, body=body, path=path, block=_i)
    return reqs


_REQS_REAL_CACHE = {}   # reqs_dir -> realpath, resolved once per process


def _prune_dirs(dirpath, dirs, reqs_dir, code_root=None, ignore=()):  # implements: ARCH-SCAN-002  # implements: REQ-SCAN-909
    """Drop noise dirs and the SSOT output dir from an os.walk in place.

    Excludes ONLY the actual requirements dir (by realpath), not every folder
    that happens to be named 'requirements' — a source package named
    requirements/ must still be scanned. The realpath comparison runs only for a
    directory whose NAME matches the SSOT dir's: resolving every directory on the
    walk was 62% of one consumer's gate time (4,900 upload folders, 35k realpath
    calls for a 216-file scan).

    With `code_root` and `ignore`, a directory that a `.reqmapignore` pattern ending
    in `/**` or `/*` already covers is not descended at all. Every file under it
    matched the pattern anyway, so the result is identical — only the stat calls go."""
    reqs_name = os.path.normcase(os.path.basename(os.path.normpath(reqs_dir))) if reqs_dir else None
    dir_pats = [p for p in ignore if p.endswith(("/**", "/*"))]
    keep = []
    for d in dirs:
        if d in (".git", "node_modules", "__pycache__"):
            continue
        if reqs_name and os.path.normcase(d) == reqs_name:
            real = _REQS_REAL_CACHE.get(reqs_dir)
            if real is None:
                real = _REQS_REAL_CACHE[reqs_dir] = os.path.realpath(reqs_dir)
            if os.path.realpath(os.path.join(dirpath, d)) == real:
                continue
        if dir_pats and code_root is not None:
            rel = os.path.relpath(os.path.join(dirpath, d), code_root).replace(os.sep, "/") + "/"
            if any(fnmatch.fnmatch(rel, p) for p in dir_pats):
                continue
        keep.append(d)
    dirs[:] = keep


def load_ignore(code_root, reqs_dir=None):  # implements: ARCH-SCAN-002  # implements: REQ-SCAN-909
    """Read optional `.reqmapignore` (fnmatch globs over POSIX rel paths, one per
    line, blanks and # comments skipped). Looked up in `requirements/` first (the
    consolidated home for reqmap files) then at the scan root; first found wins.
    Patterns are still matched against repo-root-relative paths regardless of where
    the file lives. Fail-open: a missing/unreadable file yields no patterns."""
    pats = []
    for base in ([reqs_dir] if reqs_dir else []) + [code_root]:
        try:
            with open(os.path.join(base, ".reqmapignore"), encoding="utf-8") as f:
                for line in f:
                    s = line.strip()
                    if s and not s.startswith("#"):
                        pats.append(s)
            break   # first .reqmapignore found wins
        except (OSError, ValueError):   # unreadable OR undecodable: no patterns, no crash
            continue
    return pats


def _strip_py_strings(s):
    """Mask Python string literal contents with spaces; detect an unclosed triple-quote.

    Handles single-line '' / "" strings and triple-quoted forms (both ''' and \""").
    Triple-quote detection takes precedence over single-quote detection.
    A '#' after all string content is consumed is preserved as-is (it starts a comment).

    Returns (masked_line, in_triple_or_None):
      masked_line        — line with all string *content* replaced by spaces
      in_triple_or_None  — the triple-quote delimiter ('\"\"\"' or \"'''\") if one opened
                           and did not close on this line, else None.
    """
    out = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if i + 2 < n and s[i:i+3] in ('"""', "'''"):
            q = s[i:i+3]
            out.append('   ')    # mask the opening delimiter
            i += 3
            j = s.find(q, i)
            if j == -1:
                out.append(' ' * (n - i))
                return ''.join(out), q
            out.append(' ' * (j - i + 3))
            i = j + 3
        elif c in ('"', "'"):
            out.append(' ')
            i += 1
            while i < n and s[i] != c and s[i] != '\n':
                if s[i] == '\\' and i + 1 < n:
                    out.append('  ')
                    i += 2
                else:
                    out.append(' ')
                    i += 1
            if i < n and s[i] == c:
                out.append(' ')
                i += 1
        elif c == '#':
            out.append(s[i:])
            break
        else:
            out.append(c)
            i += 1
    return ''.join(out), None


def _visible_lines(fp, lines):  # implements: ARCH-SCAN-002  # implements: REQ-SCAN-908  # implements: REQ-SCAN-992
    """Yield `(lineno, text)` for every line of `fp` a tag may legitimately live on,
    with the excluded zones already removed or blanked.

    ONE masking pass for every scanner in the engine. There used to be three
    hand-copied ones — `_scan_file_tags`, `_extract_coverage` and `_walk_code_lines` —
    and they had already drifted: only the first knew what a Markdown fence was, so a
    `# verifies: ID#CASE-1` written inside a ```-fenced EXAMPLE counted as real
    per-criterion coverage and silenced the very warning that says the case is
    untested. A masking rule that lives in one place cannot be half-applied.

    PROSE (.md, .html): a fenced code block (``` / ~~~, CommonMark length-matched)
      and, in Markdown only, a >=4-space / tab indented block are code — those lines
      are not yielded at all. `<!-- implements: X -->` outside any such zone is a
      valid tag position and is yielded.
    PY: a triple-quoted string (state carried across lines) and single-line string
      literals are blanked. Comments are kept — `code()  # implements: X` is a real tag.
    Anything else: yielded unchanged.

    Backtick spans are deliberately NOT stripped here. The callers disagree on that
    (see `_extract_coverage`), and folding it in would hide a difference that is
    load-bearing. State is local, so nothing leaks between files.
    """
    ext = os.path.splitext(fp)[1].lower()
    if ext in PROSE_EXTS:
        fence = None   # None = not fenced; else the opening fence string e.g. "```"
        for i, raw in enumerate(lines, 1):
            s = raw.rstrip("\n\r")
            # Markdown indented code block (>=4 spaces / tab): treat as code so an
            # indented ```-prefixed line never opens a phantom fence that would
            # swallow every later tag, and an indented tag is excluded. Checked
            # BEFORE fence detection. HTML has no indented-code concept, so the
            # guard is Markdown-only — an indented tag comment in HTML stays valid.
            if ext == ".md" and (s.startswith("    ") or s.startswith("\t")):
                continue
            stripped = s.lstrip()
            fm = _FENCE_RE.match(stripped)
            if fm:
                marker = fm.group(1)
                rest = stripped[len(marker):].strip()
                if fence is None:
                    fence = marker
                    continue
                elif marker[0] == fence[0] and len(marker) >= len(fence) and not rest:
                    fence = None    # closer must be bare (no info string)
                    continue
            if fence is None:
                yield i, s

    elif ext == ".py":
        in_triple = None   # None or the opening triple-quote delimiter
        for i, raw in enumerate(lines, 1):
            s = raw.rstrip("\n\r")
            if in_triple is not None:
                idx = s.find(in_triple)
                if idx == -1:
                    continue
                s = s[idx + len(in_triple):]
                in_triple = None
            s, in_triple = _strip_py_strings(s)
            yield i, s

    else:
        for i, raw in enumerate(lines, 1):
            yield i, raw.rstrip("\n\r")


def _scan_file_tags(fp, lines=None):  # implements: ARCH-SCAN-002  # implements: REQ-SCAN-908
    """Membership tags in one file as [[role, cap, line], ...], or None on read error.

    `lines` lets a caller that has already read the file hand the content over, so the
    single-walk scanner (`scan_all`) reads each file once for all three extractors
    instead of three times. `fp` is still required: the masking rules key off its
    extension. Reading it here when `lines` is None keeps every existing caller working.

    Which positions count is `_visible_lines`' business; this adds the one rule that is
    its own — a prose backtick span is an example, not a tag — and de-duplicates the
    same (role, id) pair repeated on one line.
    """
    out = []
    if lines is None:
        try:
            with open(fp, encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
        except OSError:
            return None
    prose = os.path.splitext(fp)[1].lower() in PROSE_EXTS
    for i, s in _visible_lines(fp, lines):
        if prose:
            s = _BACKTICK_RE.sub("", s)
        seen = set()
        for role, cap in _findall_tags(s):
            key = (role, cap)
            if key not in seen:
                seen.add(key)
                out.append([role, cap, i])
    return out


def _scancache_path(reqs_dir):  # implements: ARCH-SCANCACHE-023  # implements: REQ-SCANCACHE-911
    return os.path.join(reqs_dir, "_scancache.json")


def _load_scancache(reqs_dir):  # implements: ARCH-SCANCACHE-023  # implements: REQ-SCANCACHE-911
    """Read the opt-in scan-cache sidecar; {} when absent/corrupt (fails open)."""
    try:
        with open(_scancache_path(reqs_dir), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_scancache(reqs_dir, cache):  # implements: ARCH-SCANCACHE-023  # implements: REQ-SCANCACHE-911
    """Write the scan cache, best-effort — an unwritable cache must never fail the scan."""
    try:
        with open(_scancache_path(reqs_dir), "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2, sort_keys=True)
    except OSError:
        pass


def _walk_files(code_root, reqs_dir=None, accept=None):  # implements: ARCH-SCAN-002  # implements: REQ-SCAN-909
    """Yield (abs_path, posix_rel_path) for every file under `code_root` the walk admits.

    The one place the walk discipline lives: prune the noise dirs and the SSOT output dir,
    prune a directory a `.reqmapignore` `/**` pattern already covers, descend and read in
    sorted order so a generated artifact is identical across platforms, and drop any path
    an ignore pattern matches. `accept(filename, rel)` is all a caller still decides —
    which files it wants.

    Six loops used to carry a copy of this, drifted in ways that only show up on someone
    else's repo: two never called `dirs.sort()`, so their output depended on filesystem
    order; two called `_prune_dirs` without `code_root`/`ignore`, so a `build/**` pattern
    still descended into build/ and stat'ed every file inside it; and the coverage report
    hand-rolled the prune list, matching neither the SSOT directory by realpath nor an
    ignored tree at all.
    """
    ignore = load_ignore(code_root, reqs_dir)
    for dirpath, dirs, files in os.walk(code_root):
        _prune_dirs(dirpath, dirs, reqs_dir, code_root, ignore)
        dirs.sort()                  # deterministic descent — raw os.walk order is OS-dependent
        for fn in sorted(files):     # deterministic file order — the map must not depend on the filesystem
            fp = os.path.join(dirpath, fn)
            rel = os.path.relpath(fp, code_root).replace(os.sep, "/")
            if any(fnmatch.fnmatch(rel, pat) for pat in ignore):
                continue
            if accept is None or accept(fn, rel):
                yield fp, rel


def _walk_code(code_root, reqs_dir=None):  # implements: ARCH-SCAN-002
    """(abs, rel) for every scannable SOURCE file — the walk with the code-file filter."""
    return _walk_files(code_root, reqs_dir, lambda fn, _rel: _is_code_file(fn))


def _extract_coverage(fp, rel, lines, ac_out, level_out):  # implements: ARCH-ACVERIFY-019  # implements: REQ-SCAN-992
    """Accumulate `verifies:` and levelled `tested-by:` hits from one file's lines.

    One `_visible_lines` pass feeding both regexes, because the two scanners this
    replaces did the identical per-line work twice. The asymmetry between them is
    preserved exactly: only the levelled scan strips backticked spans first, so a
    documented EXAMPLE of a levelled tag does not register as real coverage, while
    `verifies:` keeps its raw scan. Both now see prose fences, which they did not
    before — an example inside a ``` block is an example in either spelling.
    """
    for i, s in _visible_lines(fp, lines):
        for cap, ac in AC_VERIFY_RE.findall(s):
            ac_out.setdefault(cap, {}).setdefault(ac, []).append((rel, i))
        for idlist, level in TEST_LEVEL_RE.findall(_BACKTICK_RE.sub("", s)):
            for cap in _ID_RE.findall(idlist):
                level_out.setdefault(cap, {}).setdefault(level, []).append((rel, i))


def scan_all(code_root, reqs_dir=None, cache=False):  # implements: ARCH-SCAN-002  # implements: ARCH-SCANCACHE-023  # implements: REQ-SCAN-908  # implements: REQ-SCANCACHE-911
    """(members, ac_cover, level_cover) from ONE walk that reads each file once.

    The gate used to call three scanners that each walked the whole tree and opened
    every file: on a 10,000-file tree that measured 3.06s + 2.76s + 2.81s of its 8.49s
    total. Results are identical to calling `scan_members` / `scan_ac_verifies` /
    `scan_test_levels` separately; a test asserts that equality.

    Opt-in (cache=True with reqs_dir set): a sidecar keyed by (mtime_ns, size) lets an
    unchanged file skip the read+parse for ALL three extractions. The cache is a PURE
    performance optimization — results are byte-identical to cache=False — and OFF by
    default, so the gate/CI path is unaffected. A changed/new file is re-parsed, a
    vanished file is pruned (absent from the rewritten cache), and an entry written by
    the older members-only cache (no `ac`/`lv` keys) is treated as a miss. `--cache`
    used to be slower than no cache on `gate`: it kept the members walk cached and
    then re-walked the tree twice for the coverage maps."""
    members, ac_cover, level_cover = {}, {}, {}
    use_cache = bool(cache and reqs_dir)
    old = _load_scancache(reqs_dir) if use_cache else {}
    new = {}
    for fp, rel in _walk_code(code_root, reqs_dir):
        ent, st = None, None
        if use_cache:
            try:
                st = os.stat(fp)
            except OSError:
                continue
            e = old.get(rel)
            if (e and e.get("mtime_ns") == st.st_mtime_ns and e.get("size") == st.st_size
                    and "ac" in e and "lv" in e):
                ent = e
        if ent is None:
            try:
                with open(fp, encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
            except OSError:
                continue          # unreadable file is skipped, never fatal
            ac, lv = {}, {}
            _extract_coverage(fp, rel, lines, ac, lv)
            ent = {"tags": _scan_file_tags(fp, lines) or [],
                   "ac": [[cap, a, ln] for cap, d in ac.items() for a, locs in d.items() for (_r, ln) in locs],
                   "lv": [[cap, l, ln] for cap, d in lv.items() for l, locs in d.items() for (_r, ln) in locs]}
            if use_cache:
                ent["mtime_ns"], ent["size"] = st.st_mtime_ns, st.st_size
        if use_cache:
            new[rel] = ent
        for role, cap, line in ent["tags"]:
            members.setdefault(cap, []).append((role, rel, line))
        for cap, a, ln in ent["ac"]:
            ac_cover.setdefault(cap, {}).setdefault(a, []).append((rel, ln))
        for cap, l, ln in ent["lv"]:
            level_cover.setdefault(cap, {}).setdefault(l, []).append((rel, ln))
    if use_cache:
        _save_scancache(reqs_dir, new)   # `new` omits vanished files -> prune
    return members, ac_cover, level_cover


def scan_members(code_root, reqs_dir=None, cache=False):  # implements: ARCH-SCAN-002  # implements: REQ-SCAN-908
    """Walk the code root for `implements:`/`tested-by:` tags -> {cap_id: [(role, file, line)]}.
    The members third of `scan_all`, kept for every caller that only ever asked for
    members; it is not a second walk implementation."""
    return scan_all(code_root, reqs_dir, cache)[0]


_VDS_STRING_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')
_VDS_ID_CONTRACT_START_RE = re.compile(r'id:"([A-Z][A-Z0-9-]+)"[^{}]*?contract:\[')
# An entry the fixture INVENTS: the viewer's demo dataset carries a fake orphan and a
# fake deprecated capability so the Risk and Problems tabs have something to show with
# no engine present. Those ids cannot exist in any registry, so comparing them against
# one reported permanent drift - the check crying wolf about data that is doing its job.
# Marked entries are skipped; an UNMARKED id missing from the registry still reports,
# because that is the real signal (a requirement renamed out from under the fixture).
_VDS_DEMO_ONLY_RE = re.compile(r'demoOnly\s*:\s*true')


def _vds_normalize(strings):
    return sorted(" ".join(s.split()) for s in strings)


def _vds_scan_array_body(text, start):
    """From text[start] (the char right after the '[' that opens a JS array),
    return the array's raw source text up to its matching ']' — tracking
    quoted-string state so a stray ']'/'[' INSIDE a contract bullet's own text
    (e.g. a bullet describing `[a, b]` syntax) doesn't end the scan early.
    Returns None if the array never closes before EOF."""
    depth, in_string, i = 1, False, start
    while i < len(text):
        c = text[i]
        if in_string:
            if c == "\\":
                i += 2
                continue
            if c == '"':
                in_string = False
        elif c == '"':
            in_string = True
        elif c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                return text[start:i]
        i += 1
    return None


def _vds_parse_baked(text):
    """{id: [contract strings]} from data.js's BAKED array, minus `demoOnly:true` entries."""
    out = {}
    for m in _VDS_ID_CONTRACT_START_RE.finditer(text):
        if _VDS_DEMO_ONLY_RE.search(m.group(0)):
            continue                      # invented demo state — no registry counterpart
        block = _vds_scan_array_body(text, m.end())
        if block is None:
            continue
        out[m.group(1)] = [s.replace('\\"', '"') for s in _VDS_STRING_RE.findall(block)]
    return out


def check_viewer_data_sync(data_js_path, map_nodes):  # implements: ARCH-VIEWER-007
    """Compare app/src/lib/data.js's hand-authored BAKED requirement fixture
    against the live registry (map_nodes: [{"id":..., "contract":[...]}, ...]).
    Returns a sorted list of requirement IDs where the two disagree — a baked id
    missing from the live registry, or a whitespace-normalized mismatch in its
    `contract` bullets. A warn-only heuristic (not a byte-exact diff): it locates
    each BAKED entry's `contract:[...]` array via bracket-depth + quoted-string
    tracking (a naive non-greedy regex stops at the FIRST ']', which truncates
    any bullet whose own text contains a bracket — this repo's actual contracts
    do, e.g. describing `[a, b]` syntax, so that naive form is not just imprecise
    but wrong on real data). Returns None (not []) when data_js_path doesn't
    exist OR can't be decoded as UTF-8 — fail-open, matching load_ignore()'s
    convention for an optional file."""
    try:
        with open(data_js_path, encoding="utf-8") as f:
            text = f.read()
    except (OSError, ValueError):   # ValueError covers UnicodeDecodeError
        return None
    baked = _vds_parse_baked(text)
    live = {n["id"]: n.get("contract", []) for n in map_nodes}
    drift = [rid for rid, contract in baked.items()
             if rid not in live or _vds_normalize(contract) != _vds_normalize(live[rid])]
    return sorted(drift)


DOC_BUNDLE_MIN_BYTES = 50_000   # a docs/ HTML doc this big is a generated bundle, not a stub


def _git(args, cwd=None, timeout=10):  # implements: ARCH-GITRUN-067  # implements: REQ-GITRUN-993
    """Run one git command; return its stdout, or None when git could not answer.

    Every git call in this engine is advisory or fail-open — a missing git, a directory
    that is not a work tree, a non-zero exit all mean "unknown", never "raise". Eleven
    call sites each decided that for themselves and disagreed on the details that matter:

    - `encoding="utf-8"` is not cosmetic. With `text=True` alone Python decodes with the
      LOCALE codec, so on a Windows console (cp1252) a non-ASCII path or remote URL either
      mojibakes or raises inside a bare `except`, and the caller reads the empty result as
      "nothing found" — a check failing OPEN, silently, on one platform. Three sites had
      the encoding because someone was bitten; the other eight did not.
    - Two of them used `check_output(...).decode()`, which is the same bug with no `text=`.
    - The exception nets ranged from `Exception` to `(OSError, SubprocessError)`, so a
      `UnicodeDecodeError` was caught by some and fatal in others.

    Decoding stays strict on purpose: a path git could not hand over as UTF-8 must surface
    as None (fall back to the full, safe answer), never as a replacement character that
    silently fails to match a real file.
    """
    try:
        r = subprocess.run(["git"] + list(args), cwd=cwd or None,
                           capture_output=True, text=True, encoding="utf-8", timeout=timeout)
    except Exception:
        return None
    return r.stdout if r.returncode == 0 else None


def _git_root(root):  # implements: ARCH-GITRUN-067  # implements: REQ-GITRUN-993
    """The work-tree root containing `root`, or `root` itself when git cannot say.

    Three call sites resolved the toplevel with three spellings, which is one more than
    a repo entered from a sub-directory can afford: the site page and the scan root have
    to agree on where the project starts."""
    return (_git(["-C", root, "rev-parse", "--show-toplevel"], timeout=3) or "").strip() or root


def _git_remote_url(root):  # implements: ARCH-GITRUN-067  # implements: REQ-GITRUN-993
    """`remote.origin.url`, or "" when git is absent / there is no remote."""
    return (_git(["-C", root, "config", "--get", "remote.origin.url"], timeout=3) or "").strip()


def untracked_members(code_root, members):  # implements: ARCH-TRACKED-042  # implements: REQ-TRACKED-936
    """Sorted rel-paths of member files git does not track, or None when unknowable.

    The invariant: a committed generated artifact must depend only on TRACKED files.
    Break it and the map records members a fresh checkout cannot produce, so the
    committed _map.json is unreproducible - `map --check` then fails in CI for a file
    that is not in the repo, which reads as a mystery rather than a mistake. That
    happened twice in one day here: a subagent worktree (a full second copy of the
    tree, gitignored) and a Consilium report carrying a real `generated-from:` tag.
    Both were invisible locally, because the local scan can see what CI never will.

    One `git ls-files` call, not one `check-ignore` per path: being untracked is the
    property that matters, and it also catches a file that is merely uncommitted
    rather than ignored. Returns None - the fail-open signal, matching
    `_since_changed_files` - when git is absent or `code_root` is not a work tree.
    """
    tracked_out = _git(["-c", "core.quotepath=off", "ls-files", "-z"],
                       cwd=code_root, timeout=30)
    if tracked_out is None:
        return None
    tracked = {os.path.normcase(p.replace("/", os.sep))
               for p in tracked_out.split("\0") if p}
    seen = set()
    for hits in members.values():
        for _role, fp, _ln in hits:
            seen.add(fp)
    return sorted(fp for fp in seen
                  if os.path.normcase(fp.replace("/", os.sep)) not in tracked)



# Never worth opening for a tag: a tag can only live in text a human wrote.
_BINARY_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".gz", ".tgz", ".7z",
                ".woff", ".woff2", ".ttf", ".otf", ".eot", ".docx", ".xlsx", ".pptx", ".exe",
                ".dll", ".so", ".dylib", ".bin", ".jar", ".class", ".pyc", ".lock", ".mp3", ".mp4")
_UNSCANNED_MAX_BYTES = 1_000_000


def tagged_unscanned_files(code_root, reqs_dir=None):  # implements: ARCH-UNSCANNEDTAG-045  # implements: REQ-UNSCANNEDTAG-939
    """Sorted rel-paths of TRACKED files the scan never reads (extension/basename
    outside CODE_EXTS/BASENAME_CODE_FILES) that nonetheless carry a membership tag,
    or None when git cannot answer. A tag in such a file is silently not a member:
    the first consumer run had a tagged Caddyfile and a tagged Prisma schema, both
    invisible. Bounded by `git ls-files` like untracked_members, skips `.reqmapignore`
    matches, the SSOT dir, `_`-prefixed and binary/oversized files; a non-UTF-8 file
    is skipped, never reported."""
    tracked_out = _git(["-c", "core.quotepath=off", "ls-files", "-z"],
                       cwd=code_root, timeout=30)
    if tracked_out is None:
        return None
    ignore = load_ignore(code_root, reqs_dir)
    reqs_rel = None
    if reqs_dir:
        try:
            reqs_rel = os.path.relpath(reqs_dir, code_root).replace(os.sep, "/") + "/"
        except ValueError:
            reqs_rel = None
    out = []
    for rel in tracked_out.split("\0"):
        if not rel:
            continue
        fn = os.path.basename(rel)
        # git's and the engine's own dotfiles quote tags as examples (this repo's
        # .reqmapignore explains an illustration id); any other dotfile — .env was the
        # infra run's case — is as tag-worthy as a Makefile and is reported
        if _is_code_file(fn) or fn.startswith(("_", ".git", ".reqmap")) or fn.lower().endswith(_BINARY_EXTS):
            continue
        if reqs_rel and not reqs_rel.startswith("../") and rel.startswith(reqs_rel):
            continue
        if any(fnmatch.fnmatch(rel, pat) for pat in ignore):
            continue
        fp = os.path.join(code_root, rel.replace("/", os.sep))
        try:
            if os.path.getsize(fp) > _UNSCANNED_MAX_BYTES:
                continue
            with open(fp, encoding="utf-8") as f:
                text = f.read()
        except (OSError, ValueError):
            continue
        if TAG_RE.search(text):
            out.append(rel)
    return sorted(out)


def untagged_doc_bundles(code_root, members, reqs_dir=None):  # implements: ARCH-DOCBUNDLE-026  # implements: REQ-DOCBUNDLE-840
    """Sorted rel-paths of large `docs/` HTML docs that carry no `generated-from:`
    tag — the doc-sync blind spot: a whole-system doc (built from many requirements)
    that drifts from them with nothing linking the two. A bare `generated-from:` only
    pins ONE id, but the multi-id list (ARCH-SCAN-002) lets one doc name all its
    sources. Walk discipline matches scan_members: honors `.reqmapignore`, prunes
    noise. Skips engine-generated outputs (`_`-prefixed, the published `map.html`
    viewer). Threshold-only + warn-only by design, so it nudges without false alarms."""
    tagged = {fp for hits in members.values()
              for (role, fp, _ln) in hits if role == "generated-from"}
    def wanted(fn, rel):
        return (fn.endswith(".html") and not fn.startswith("_") and fn != "map.html"
                and rel.startswith("docs/") and rel not in tagged)

    out = []
    for fp, rel in _walk_files(code_root, reqs_dir, wanted):
        try:
            if os.path.getsize(fp) >= DOC_BUNDLE_MIN_BYTES:
                out.append(rel)
        except OSError:
            continue
    return sorted(out)


# Files the "untagged" bucket never lists: prose and repo boilerplate that will not
# carry a tag by design — decision records, issue/PR templates, security policy,
# dependabot config. Everything else scannable and tagless is a real signal.
_UNTAGGED_NOISE = ("adr/*", "*/adr/*", "decisions/*", "*/decisions/*",
                   "*/ISSUE_TEMPLATE/*", "*PULL_REQUEST_TEMPLATE.md",
                   "SECURITY.md", "*/SECURITY.md", "CODE_OF_CONDUCT.md", "*/CODE_OF_CONDUCT.md",
                   "*dependabot.yml", "*/FUNDING.yml")


def _scan_untagged(code_root, reqs_dir=None):  # implements: ARCH-NEXT-013  # implements: ARCH-COVERAGE-029  # implements: REQ-NEXT-886  # implements: REQ-COVERAGE-836
    """Scannable files that carry no membership tag at all, as sorted rel paths.
    Skips the auto-draft "ignore" bucket and `_UNTAGGED_NOISE`."""
    untagged = []
    for fp, rel in _walk_code(code_root, reqs_dir):
        fn = os.path.basename(rel)
        if fn.endswith(PROSE_EXTS) and classify_prose(rel) == "ignore":
            continue   # CLAUDE.md, TODO.md, CHANGELOG.md, LICENSE, _-prefixed: invisible by contract (ARCH-PROSE-024)
        if any(fnmatch.fnmatch(rel, pat) for pat in _UNTAGGED_NOISE):
            continue
        tags = _scan_file_tags(fp)
        if tags is not None and not tags:
            untagged.append(rel)
    return sorted(untagged)


ORPHAN_CODE_MIN_LOC = 150   # a program file this big with no tag is a coverage hole, not a stub
# program-logic extensions only: prose/config/styling coverage is ARCH-DOCBUNDLE-026's concern
ORPHAN_CODE_EXTS = (".py", ".js", ".ts", ".tsx", ".jsx", ".c", ".cc", ".cpp",
                    ".h", ".hpp", ".java", ".go", ".rs",
                    ".mjs", ".cjs", ".mts", ".cts", ".vue", ".svelte",
                    ".cs", ".php", ".rb", ".kt", ".kts", ".swift", ".scala", ".ex", ".exs", ".dart")


def orphan_code_files(code_root, covered, reqs_dir=None):  # implements: ARCH-ORPHANCODE-034  # implements: REQ-ORPHANCODE-888
    """Sorted rel-paths of program-logic files >= ORPHAN_CODE_MIN_LOC lines that
    carry no requirement link — code implementing behavior no requirement describes.
    `covered` is the rel-path set already linked (membership tags + `verifies:`
    coverage), derived from the caller's existing scans so this adds no second tag
    scan. Walk discipline matches scan_members: honors `.reqmapignore`, prunes noise.
    Warn-only at ANY flag combination (the ARCH-COVERAGE-029 Senate audit capped
    coverage signals at advisory — a hard gate makes hollow tags the way to pass CI)."""
    out = []
    for fp, rel in _walk_files(code_root, reqs_dir,
                               lambda fn, r: fn.endswith(ORPHAN_CODE_EXTS) and r not in covered):
        try:
            with open(fp, encoding="utf-8", errors="ignore") as f:
                loc = sum(1 for _ in f)
        except OSError:
            continue
        if loc >= ORPHAN_CODE_MIN_LOC:
            out.append(rel)
    return sorted(out)


def _walk_code_lines(code_root, reqs_dir=None):  # implements: ARCH-SCAN-002  # implements: REQ-SCAN-908
    """Yield `(rel_path, lineno, line)` for every scannable line under `code_root`.

    The one walk the tag scanners share: it prunes the same directories, honours the
    same `.reqmapignore`, descends in the same sorted order, and masks every excluded
    zone through `_visible_lines`, so a tag inside a Python docstring or a Markdown
    fence is not read as a real tag. A caller receives lines already masked and only
    has to say what a tag means."""
    for fp, rel in _walk_code(code_root, reqs_dir):
        try:
            with open(fp, encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
        except OSError:
            continue
        for i, masked in _visible_lines(fp, lines):
            yield rel, i, masked


def scan_ac_verifies(code_root, reqs_dir=None):  # implements: ARCH-ACVERIFY-019  # implements: REQ-ACVERIFY-821
    """Walk the code for `# verifies: REQ-X#AC-N` tags and return
    `{cap_id: {ac_label: [(file, line)]}}` — which labelled criterion each test
    covers. Same walk discipline as `scan_members` (respects .reqmapignore, prunes
    .git/node_modules). Empty when no `verifies:` tag exists anywhere."""
    cover = {}  # cap_id -> {ac_label -> [(file, line)]}
    for rel, i, line in _walk_code_lines(code_root, reqs_dir):
        for cap, ac in AC_VERIFY_RE.findall(line):
            cover.setdefault(cap, {}).setdefault(ac, []).append((rel, i))
    return cover


def scan_test_levels(code_root, reqs_dir=None):  # implements: ARCH-VLEVEL-037  # implements: REQ-VLEVEL-944  # implements: REQ-VLEVEL-945
    """Walk the code for `# tested-by: REQ-X @level` tags and return
    `{cap_id: {level: [(file, line)]}}` — at which V-model level each requirement is
    verified. Kept separate from `scan_members` on purpose: folding the level into the
    member tuples would change the `(role, file, line)` shape that `_map.json` and every
    member consumer depend on. Shares `_walk_code_lines` with `scan_ac_verifies`, so both honour the same
    `.reqmapignore` and the same string-masking. Empty when no levelled tag exists."""
    cover = {}  # cap_id -> {level -> [(file, line)]}
    for rel, i, line in _walk_code_lines(code_root, reqs_dir):
        # Strip backticked spans before the search, the same phantom-member guard
        # `_scan_file_tags` applies: a documented EXAMPLE of a levelled tag must not
        # register as real coverage. Without it this scanner matches the example in
        # its own constant's comment.
        line = _BACKTICK_RE.sub("", line)
        for idlist, level in TEST_LEVEL_RE.findall(line):
            for cap in _ID_RE.findall(idlist):
                cover.setdefault(cap, {}).setdefault(level, []).append((rel, i))
    return cover


_AC_LABEL_RE = re.compile(r"^((?:CASE|AC)-\d+)\b")   # CASE-N is current, AC-N legacy
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
# The template records how a criterion is checked as an HTML comment on its label:
# `AC-1  <!-- verifiable by: automated test -->`. Only this vocabulary marks a
# criterion a machine can never verify; an ABSENT marker means automatable, so a
# corpus that never adopted the marker keeps exactly the behavior it had.
_AC_VERIFIABLE_RE = re.compile(r"verifiable\s+by\s*:([^>]*)", re.I)
_AC_MANUAL_WORDS = ("manual", "inspection", "review", "demo", "walkthrough", "sign-off")


def _acc_blocks(body):  # implements: ARCH-ACVERIFY-019  # implements: ARCH-ATOMICFORM-053
    """Parse the HOW — Acceptance section into one record per criterion:
    `{"label": "AC-1" or "", "text": <folded prose>, "manual": bool}`.

    Two authoring shapes exist and both count: the labelled Gherkin BLOCK the
    template prescribes (`AC-1` followed by indented Given/When/Then lines) and a
    plain `- ` bullet. `_bullets` sees only the second, which is why the emitted
    `acc` list was empty for every requirement written the prescribed way — the map,
    the viewer, and any downstream count had nothing to read (50/50 nodes here).

    An atomic body has no Acceptance heading: its single `Scenario:` block is the one
    criterion, returned unlabelled so `# verifies: <ID>#AC-N` has nothing to point at —
    at one criterion per requirement, `tested-by:` is already per-criterion precision.

    One parser, three callers (`_acc_items`, `_labeled_acs`, `_count_ac`) so a
    criterion cannot be counted by one and missed by another. The block-start test
    is `_count_ac`'s verbatim, keeping `len(_acc_blocks(b)) == _count_ac(b)`."""
    _sp = _atomic_spans(body)
    if _sp:                                        # atomic: the Scenario is the one criterion
        _txt = " ".join(l.strip() for l in _sp[1])
        return [{"label": "", "text": _txt, "manual": bool(_AC_VERIFIABLE_RE.search(_txt))
                 and any(w in _txt.lower() for w in _AC_MANUAL_WORDS)}]
    out = []
    for s in _section_lines(body, ACCEPTANCE_LABELS):
        m = _AC_LABEL_RE.match(s)
        if m or s.startswith("- "):
            label = m.group(1) if m else ""
            out.append({"label": label, "raw": [s[len(label):] if m else s[2:]]})
        elif s and out:
            # continuation of the criterion above (an indented Given/When/Then line,
            # or a marker comment on its own line) — folded in, so a multi-line
            # criterion is never truncated to its first physical line.
            out[-1]["raw"].append(s)
    blocks = []
    for b in out:
        raw = " ".join(b["raw"]).strip()
        mark = _AC_VERIFIABLE_RE.search(raw)
        marker = mark.group(1) if mark else ""
        blocks.append({
            "label": b["label"],
            "text": _HTML_COMMENT_RE.sub("", raw).strip(),
            # `|` means the template's unedited placeholder list ("automated test |
            # manual | inspection | load test") — an author who never chose is not
            # declaring the criterion manual.
            "manual": "|" not in marker and any(w in marker.lower() for w in _AC_MANUAL_WORDS),
        })
    return blocks


def _acc_items(body):  # implements: ARCH-MAP-007
    """Acceptance criteria as display strings, for the emitted `acc` list: an
    `AC-1 — Given … When … Then …` line per labelled block, or the bullet text."""
    out = []
    for b in _acc_blocks(body):
        label, text = b["label"], b["text"]
        item = f"{label} — {text}" if label and text else (label or text)
        if item:
            out.append(item)
    return out


def _labeled_acs(body):  # implements: ARCH-ACVERIFY-019  # implements: REQ-ACVERIFY-822
    """Ordered list of `AC-N` labels declared in the HOW — Acceptance section.
    Empty when the requirement writes bullet ACs without labels — per-AC coverage
    only applies to requirements that label their criteria, so unlabelled ones are
    silently exempt (no false 'unverified' warning)."""
    out = []
    for b in _acc_blocks(body):
        if b["label"] and b["label"] not in out:
            out.append(b["label"])
    return out


def _automatable_acs(body):  # implements: ARCH-ACVERIFY-019  # implements: REQ-ACVERIFY-822
    """`_labeled_acs` minus the criteria marked `verifiable by: inspection|manual`.
    A criterion a human checks by reading can never carry a `# verifies:` tag, so
    counting it as unverified is a warning no one can ever clear — the marker the
    template already prescribes is the answer, it simply was not read here."""
    return [b["label"] for b in _acc_blocks(body)
            if b["label"] and not b["manual"]]


# ---------- hashing / drift ----------
# The binding-clause section, current name first. `## Description` merged the standalone
# `> WHY:` blockquote and `## WHAT — Contract (normative)` into one section: a reader met
# the same capability described twice, once as rationale and once as obligation, under two
# headings that both said WHAT. The legacy name keeps working forever — a consumer repo's
# existing files are not a migration this tool gets to demand.
CONTRACT_LABELS = ("description", "contract")   # implements: ARCH-DESCRIPTION-057

# The acceptance-criteria section, current name first. `## Cases` and its `CASE-N` labels
# replaced `## HOW — Acceptance (= tests)` and `AC-N`: a criterion IS a test case, and the
# old name made the section sound like a sign-off step rather than the cases a reader can
# run. Both names are honoured, and `# verifies: <ID>#AC-N` keeps working — the label is an
# identifier a tag points at, so dropping the old spelling would break every consumer tag
# already written against it.
ACCEPTANCE_LABELS = ("cases", "acceptan")       # implements: ARCH-DESCRIPTION-057

# A normative section heading: the canonical `## Description` / `## Cases`, the older
# `## WHAT — Contract …` / `## HOW — Acceptance …`, or a legacy bare
# `## Contract`/`## Acceptance`/`## Input`/`## Output`. Anchored so the keyword must be
# the label (right after `## ` or after a WHAT/HOW — prefix), NOT anywhere in the
# heading — otherwise a commentary heading like `## Notes — contract caveats` would leak
# into the drift hash.
# Built FROM CONTRACT_LABELS/ACCEPTANCE_LABELS (plus the legacy input/output pair those
# tuples never carry) rather than a hand-listed keyword set, so a label added to either
# tuple is automatically recognised here too — a hand-maintained second copy is exactly
# what let `## Cases` (the current spelling, most of this repo's own requirements) go
# unrecognised as a normative heading and silently exclude its criteria from the drift hash.
# prefix set MUST stay in lockstep with _heading_label_is so the drift hash and
# section detection agree on which heading is a normative section (see its docstring)
_NORMATIVE_HEADING_RE = re.compile(
    r"^##\s+(?:(?:what|why|where|how)\s*[—–-]?\s*)?"
    r"(?:" + "|".join(re.escape(n) for n in CONTRACT_LABELS + ACCEPTANCE_LABELS
                       + ("input", "output")) + ")", re.I)


def _body_lines(body):  # implements: ARCH-SECTIONS-068  # implements: REQ-SECTIONS-994
    """Yield `(is_heading, line)` for every line of a requirement body outside a ``` fence.

    The fence is checked BEFORE the heading test, so a `## ` written inside a fenced
    example is code, not a section boundary. Eight readers of these files carried a copy
    of this two-line state machine and `_has_section` carried none — which is why a
    heading inside a fence satisfied the presence check while every reader of that
    section came back empty.
    """
    fenced = False
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        yield s.startswith("## "), line


def _section_headings(body):  # implements: ARCH-SECTIONS-068  # implements: REQ-SECTIONS-994
    """Every `## ` heading in the body, stripped, in order."""
    return (line.strip() for is_heading, line in _body_lines(body) if is_heading)


def _section_lines(body, names, raw=False):  # implements: ARCH-SECTIONS-068  # implements: REQ-SECTIONS-994
    """Yield the lines of the FIRST section whose heading label matches any of `names`,
    up to the next `## `.

    `names` is one label or a tuple of them (`CONTRACT_LABELS`, `ACCEPTANCE_LABELS`) —
    current spelling first, legacy spellings after, so a section that was renamed still
    reads. The match is anchored to the label (`_heading_label_is`), so a commentary
    heading that merely mentions the word does not capture the section.

    `raw=True` keeps the physical line, indentation and blank lines included, for the
    Given/When/Then blocks the viewer renders as written; otherwise lines come back
    stripped. What each caller does with those lines — bullets, clauses, prose, criteria —
    is the caller's business; where the section starts and stops is not.
    """
    if isinstance(names, str):
        names = (names,)
    grab = seen = False
    for is_heading, line in _body_lines(body):
        if is_heading:
            if seen:
                return                    # the section ended at the next heading
            seen = grab = any(_heading_label_is(line.strip(), n) for n in names)
            continue
        if grab:
            yield line.rstrip() if raw else line.strip()


def _heading_label_is(heading, name):  # implements: ARCH-CHECK-006
    """True if a `## ` heading's LABEL is `name` (case-insensitive), allowing an
    optional `WHAT`/`HOW` prefix whose dash is optional — so `## WHAT — Contract`,
    `## WHAT Contract`, and bare `## Contract` all match name='contract'. Anchored
    to the label start so a commentary heading like `## Notes — contract caveats`
    does NOT match name='contract'. Keeps section detection (the gate, the linter)
    in agreement with the drift hash (_NORMATIVE_HEADING_RE) — see the silent-drift
    inconsistency this guards against."""
    return bool(re.match(
        r"##\s+(?:(?:what|why|where|how)\s*[—–-]?\s*)?" + re.escape(name.lower()),
        heading.strip().lower()))


_ATOMIC_SCENARIO_RE = re.compile(r"^\s*Scenario\s*:", re.I)
VALID_FORM = {"atomic"}                            # implements: ARCH-ATOMICFORM-053


def _atomic_spans(body):  # implements: ARCH-ATOMICFORM-053
    """`(statement_lines, scenario_lines)` for a body in the atomic form, else None.

    The atomic form carries no normative `## ` heading at all: a `>` blockquote states the
    single obligation and an unlabelled `Scenario:` block states its acceptance, both sitting
    between the `# ` title and the first `## ` (which begins the auto sections). Both parts
    are required, so a classic body — whose `>` WHY sits above `## WHAT — Contract` and whose
    Given/When/Then lives under a heading — returns None and every existing code path is
    unchanged.

    Detected from the BODY, not from `form: atomic` in the frontmatter, because every
    consumer of these spans (binding_hash, _has_section, _acc_blocks, _bullets) is handed a
    body and no meta. The frontmatter key is validated separately, as documentation."""
    story, scen, in_scen = [], [], False
    for line in body.splitlines():
        st = line.strip()
        if st.startswith("## "):
            break                                  # auto sections end the normative span
        if st.startswith("# "):
            continue                               # the title is not normative
        if _ATOMIC_SCENARIO_RE.match(line):
            in_scen = True
            scen.append(line.rstrip())
            continue
        if in_scen:
            if st:
                scen.append(line.rstrip())
            continue
        if st.startswith(">"):
            story.append(line.rstrip())
    if not story or not scen:
        return None
    return story, scen


_ATOMIC_THEN_RE = re.compile(r"^then\b", re.I)


def _atomic_story_bullets(story_lines):  # implements: ARCH-ATOMICFORM-053
    """Count of `- ` facts enumerated inside an atomic story's `>` blockquote.

    Mirrors `_bullets`' `>`-marker normalization (strip, then only the leading
    literal `>` chars, never a `"> "` char class — see the
    `bullets-lstrip-char-class` regression test) so the two never disagree on
    where the marker ends and the content begins. `_bullets` itself JOINS every
    story line into one clause and cannot see these; this is the one reader
    that counts them."""
    n = 0
    for line in story_lines:
        s = line.strip().lstrip(">").strip()
        if s.startswith("- "):
            n += 1
    return n


def _atomic_scenario_then_count(scen_lines):  # implements: ARCH-ATOMICFORM-053
    """Count of `Then`-led lines in an atomic Scenario block — one per proven fact.
    A wrapped continuation line of the same step does not open with the
    keyword and is not counted separately."""
    return sum(1 for line in scen_lines if _ATOMIC_THEN_RE.match(line.strip()))


_BLOCK_SEP_RE = re.compile(r"^-{3,}$")


def binding_hash(body):  # implements: ARCH-DRIFT-003  # implements: ARCH-ATOMICFORM-053  # implements: REQ-DRIFT-841
    """Hash only the NORMATIVE sections — the Contract and the Acceptance criteria.
    Everything else (Verify-intent, Notes, Current-implementation, links) is
    commentary and may drift freely without tripping the gate. (Legacy docs used
    Input/Output/Acceptance; those headers are still honored for back-compat.)"""
    keep, grab = [], False
    # `_body_lines`, so a `## Description` written inside a ```-fenced EXAMPLE neither
    # opens a normative span nor closes one. It was the last reader of these files that
    # could not see a fence, and it is the one whose answer is a contract's identity.
    for _is_heading, line in _body_lines(body):
        h = line.strip().lower()
        if h.startswith("## "):
            new_grab = bool(_NORMATIVE_HEADING_RE.match(h))
            if new_grab:
                # section boundary sentinel: keeps Contract and Acceptance distinct so
                # relocating a clause between them is not invisible to the drift hash.
                keep.append("\x1e")
            grab = new_grab
            continue
        if grab and line.strip():
            if line.strip().startswith(">"):
                # `## Description` opens with the intent blockquote — rationale, not an
                # obligation. Hashing it would report DRIFT on a confirmed contract every
                # time someone improved the explanation, which is the opposite of what
                # drift is for. The atomic form draws the same line, keeping `rationale:`
                # in the frontmatter and out of the span. No requirement carried a
                # blockquote inside a normative section when this was added, so no
                # existing hash changes.
                continue
            if _BLOCK_SEP_RE.match(line.strip()):
                # The `--------------------` that separates two requirements in a module
                # file rides along on the block BEFORE it, so it landed inside that
                # block's normative span. Adding a requirement to a module file then
                # changed the PREVIOUS one's hash — a phantom edit that now costs its
                # confirmation (REQ-PROMOTE-974). A separator is structure, never an
                # obligation.
                continue
            # rstrip (not strip): leading indent is structure — unnesting a sub-clause
            # is a real change and must drift.
            keep.append(line.rstrip())
    if not keep:
        # No normative heading: either the atomic form, whose obligation and Scenario ARE the
        # normative span, or a malformed body. Hashing the atomic span is what keeps drift
        # alive — without it every heading-less requirement hashes the empty string and
        # collides with every other, so no content change could ever be detected.
        _sp = _atomic_spans(body)
        if _sp:
            keep = _sp[0] + ["\x1e"] + _sp[1]
    return hashlib.sha256("\n".join(keep).encode()).hexdigest()[:12]


def lock_path(reqs_dir):  # implements: ARCH-DRIFT-003  # implements: REQ-DRIFT-842
    """The path of the drift baseline, `requirements/_reqlock.json`."""
    return os.path.join(reqs_dir, "_reqlock.json")


def load_lock(reqs_dir):  # implements: ARCH-DRIFT-003  # implements: REQ-DRIFT-842
    """The drift baseline as `{id: hash}`, or an empty dict when it is missing or
    unreadable — a corpus with no lock yet must still gate."""
    p = lock_path(reqs_dir)
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
            # a valid-JSON-but-non-object lock ([], null, 42) must also fail open —
            # consumers call lock.get(rid); fail open like load_memberlock/_load_scancache
            return data if isinstance(data, dict) else {}
        except (ValueError, OSError):
            # empty / corrupt / merge-conflicted / non-UTF-8 lock: treat as no lock.
            # ValueError covers both json.JSONDecodeError and UnicodeDecodeError, so
            # a binary-garbage lock fails open here instead of crashing the gate.
            return {}
    return {}


def save_lock(reqs_dir, lock):  # implements: ARCH-DRIFT-003  # implements: REQ-DRIFT-842
    """Write the drift baseline, creating the directory if needed."""
    os.makedirs(reqs_dir, exist_ok=True)
    with open(lock_path(reqs_dir), "w", encoding="utf-8") as f:
        json.dump(lock, f, indent=2, sort_keys=True)


# ---------- member-hash drift (reverse direction) ----------
# _reqlock.json keeps ONE hash per requirement = the contract; drift in that file only
# fires prose-ahead-of-code. The reverse — a MEMBER's content changed while the contract
# stayed put (behaviour shipped, spec not updated) — is invisible there. Member hashes
# live in a SEPARATE, versioned sidecar so _reqlock.json stays a byte-stable cross-repo
# contract: an older seeded engine never reads _memberlock.json and is wholly unaffected.
MEMBERLOCK_SCHEMA = 2   # 2: keys may be `file#definition`, not only `file`
MEMBER_ROLES = ("implements", "generated-from")   # roles that bind code/doc content to a contract


def _memberlock_path(reqs_dir):  # implements: ARCH-MEMBERDRIFT-027  # implements: REQ-MEMBERDRIFT-879
    return os.path.join(reqs_dir, "_memberlock.json")


def load_memberlock(reqs_dir):  # implements: ARCH-MEMBERDRIFT-027  # implements: REQ-MEMBERDRIFT-879
    """Return {rid: {relfile: sha}} from the sidecar, or {} when absent/corrupt or
    written by a NEWER schema than this engine knows — fail open (no false drift) the
    same way load_lock and the scan cache do, so a forward-incompatible sidecar degrades
    to 'reverse-drift off this run' rather than crashing or mis-comparing."""
    try:
        with open(_memberlock_path(reqs_dir), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict) or data.get("_schema") != MEMBERLOCK_SCHEMA:
        return {}
    members = data.get("members")
    return members if isinstance(members, dict) else {}


def save_memberlock(reqs_dir, member_hashes):  # implements: ARCH-MEMBERDRIFT-027  # implements: REQ-MEMBERDRIFT-879
    """Write the member-hash sidecar for reverse-direction drift, versioned by
    `_schema` and kept out of `_reqlock.json` so that file stays a byte-stable
    cross-repo contract an older seeded engine still reads."""
    os.makedirs(reqs_dir, exist_ok=True)
    payload = {"_schema": MEMBERLOCK_SCHEMA, "members": member_hashes}
    with open(_memberlock_path(reqs_dir), "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)


DRIFTLOG_SCHEMA = 1


def _driftlog_path(reqs_dir):  # implements: REQ-DRIFT-988
    return os.path.join(reqs_dir, "_driftlog.json")


def load_driftlog(reqs_dir):  # implements: REQ-DRIFT-988
    """Return {rid: {"hash": ..., "reason": ...}} for every contract whose drift was
    accepted, or {} when absent/corrupt or written by a NEWER schema — fail open like
    the other sidecars, so a forward-incompatible file degrades to 'no reasons on
    record' rather than crashing a gate."""
    try:
        with open(_driftlog_path(reqs_dir), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    schema = data.get("_schema", 0) if isinstance(data, dict) else None
    if not isinstance(schema, int) or schema > DRIFTLOG_SCHEMA:
        return {}
    got = data.get("accepted")
    return got if isinstance(got, dict) else {}


def save_driftlog(reqs_dir, accepted):  # implements: REQ-DRIFT-988
    """Write the accepted-drift record, versioned by `_schema` and kept OUT of
    `_reqlock.json` — that file is the byte-stable cross-repo contract an older seeded
    engine still reads (ADR-0003), so nothing new may be added to it."""
    os.makedirs(reqs_dir, exist_ok=True)
    payload = {"_schema": DRIFTLOG_SCHEMA, "accepted": accepted}
    with open(_driftlog_path(reqs_dir), "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)


def record_accepted_drift(reqs_dir, accepted_ids, new_lock, reason,
                          live_ids):  # implements: ARCH-DRIFT-003  # implements: REQ-DRIFT-988
    """Record who waived the drift check and why, where a reviewer reads it: the diff.

    `--accept-drift` advances the baseline on a contract nobody re-validated. That is
    the one escape hatch in the gate, and until now it left no trace at all — the lock
    hash moved and the reason lived in someone's head. The record is a file, not a log
    line, precisely so it shows up in the pull request beside the hash it excuses.

    A bare `--accept-drift` still works and is still recorded, with `reason: null`:
    silence is a legible answer, and hiding it would make the unexplained waiver the
    invisible one. Entries for requirements that have left the corpus are dropped, the
    same way the lock prunes its own."""
    if not accepted_ids:
        return {}
    log = {rid: e for rid, e in load_driftlog(reqs_dir).items()
           if rid in live_ids and isinstance(e, dict)}
    for rid in accepted_ids:
        log[rid] = {"hash": new_lock.get(rid), "reason": reason}
    save_driftlog(reqs_dir, log)
    return log


CLARIFYLOCK_SCHEMA = 1


def _clarifylock_path(reqs_dir):  # implements: REQ-CLARIFY-975
    return os.path.join(reqs_dir, "_clarifylock.json")


def load_clarifylock(reqs_dir):  # implements: REQ-CLARIFY-975
    """Return {rid: [rule, ...]} of the blocking questions each requirement had at the
    last sync, or {} when absent/corrupt or written by a NEWER schema — fail open, the
    same way the other sidecars do, so a forward-incompatible file degrades to
    'everything looks new' rather than crashing."""
    try:
        with open(_clarifylock_path(reqs_dir), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    schema = data.get("_schema", 0) if isinstance(data, dict) else None
    if not isinstance(schema, int) or schema > CLARIFYLOCK_SCHEMA:
        return {}   # fail-open like the other sidecars — a hand-edited `"1"` was a TypeError
    got = data.get("questions")
    return got if isinstance(got, dict) else {}


def save_clarifylock(reqs_dir, snapshot):  # implements: REQ-CLARIFY-975
    """Write the `clarify` answer snapshot, versioned by `_schema`."""
    os.makedirs(reqs_dir, exist_ok=True)
    payload = {"_schema": CLARIFYLOCK_SCHEMA, "questions": snapshot}
    with open(_clarifylock_path(reqs_dir), "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)


def blocking_question_rules(reqs):  # implements: REQ-CLARIFY-975
    """{rid: sorted [rule]} for EVERY requirement, empty list included.

    The RULE is the fingerprint, not the prose: two runs of the same defect are the
    same question, and rewording a clause does not invent a new one.

    Requirements with no questions are recorded too, on purpose. Otherwise "absent
    from the snapshot" would mean both "never seen" and "seen, and clean", so a
    requirement going from zero questions to one would be mistaken for a brand-new
    file and silenced — which is exactly the case this check exists to catch."""
    domain = _domain_heads(reqs)
    return {rid: sorted({q["rule"] for q in _clarify_questions(rid, r, reqs, domain)
                         if q["severity"] == "blocking"})
            for rid, r in reqs.items()}


def untracked_locks(reqs_dir):  # implements: ARCH-CHECK-006  # implements: REQ-CHECK-830
    """Lock sidecars (`_reqlock.json`, `_memberlock.json`) are committed-by-design: an
    uncommitted one silently disables drift detection on a fresh CI checkout (no baseline
    to compare against). Return the paths of any that exist on disk but are NOT git-tracked.
    Fail-open: returns [] when git is unavailable or the tree is not a work tree, so the
    gate never breaks on a non-git consumer — the same discipline the map's git-derived
    `repo` field uses."""
    paths = [p for p in (lock_path(reqs_dir), _memberlock_path(reqs_dir)) if os.path.isfile(p)]
    if not paths:
        return []
    root = os.path.dirname(os.path.abspath(reqs_dir)) or "."
    inside = _git(["-C", root, "rev-parse", "--is-inside-work-tree"], timeout=3)
    if (inside or "").strip() != "true":
        return []
    return [p for p in paths
            if _git(["-C", root, "ls-files", "--error-unmatch", os.path.abspath(p)],
                    timeout=3) is None]


def _file_sha(path):  # implements: ARCH-MEMBERDRIFT-027
    """SHA-256 of a member file with line endings normalized to LF, so the hash is identical
    whether the tree was checked out LF (Linux/CI) or CRLF (Windows core.autocrlf=true).
    Without this, a lock generated on one platform shows spurious whole-repo member drift on
    the other — under `gate --strict` that turns every member into a false error. Mirrors the
    contract hash, which is already LF-normalized via the text-mode body parse."""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return None
    data = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(data).hexdigest()


def _py_def_spans(path):  # implements: ARCH-MEMBERDRIFT-027  # implements: REQ-MEMBERDRIFT-982
    """`[(first_line, last_line, name)]` for the top-level definitions of a Python file,
    or None when it is not Python or does not parse. Nesting is deliberately not
    descended: a tag inside a method belongs to the class a reader opens, and per-method
    spans would split one contract's implementation across several keys."""
    if not path.lower().endswith(".py"):
        return None
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            tree = ast.parse(f.read())
    except (OSError, SyntaxError, ValueError):
        return None
    return [(n.lineno, getattr(n, "end_lineno", n.lineno), n.name) for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]


def _span_sha(path, lo, hi):  # implements: REQ-MEMBERDRIFT-982
    """SHA-256 of one line span, LF-normalized exactly as `_file_sha` normalizes a whole
    file — for the same reason: a CRLF checkout must not read as drift."""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return None
    data = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    lines = data.split(b"\n")
    return hashlib.sha256(b"\n".join(lines[lo - 1:hi])).hexdigest()


def compute_member_hashes(code_root, members):  # implements: ARCH-MEMBERDRIFT-027  # implements: REQ-MEMBERDRIFT-879
    """`{rid: {key: sha}}` for the members one requirement owns alone, where a key is
    `relfile#definition` for a tag inside a Python top-level definition and `relfile` for
    anything else.

    Ownership is what makes a hash attributable, and the unit of ownership is the unit the
    tag sits in. Keyed per file, a file tagged by several requirements had to be dropped
    entirely — a change in it cannot be blamed on one contract — which excluded this
    engine's own 9k-line file and its 205 requirements from reverse drift altogether.
    Keyed per definition, each requirement owns the definitions tagged with it and the
    ambiguity is gone; a definition tagged by SEVERAL requirements is still ambiguous and
    still dropped, at that finer granularity.

    Python only, because a wrong span is a wrong drift signal: the brace languages are
    read by heuristics elsewhere in this engine and keep the whole-file hash. The key says
    which was used, so the lock is self-describing."""
    owners = {}   # key -> set(rid);  where -> (path, lo, hi) or None for whole-file
    where = {}
    spans_by_file = {}
    for rid, hits in members.items():
        for role, fp, ln in hits:
            if role not in MEMBER_ROLES:
                continue
            path = os.path.join(code_root, fp)
            if fp not in spans_by_file:
                spans_by_file[fp] = _py_def_spans(path)
            spans = spans_by_file[fp]
            key, span = fp, None
            if spans:
                for lo, hi, name in spans:
                    if lo <= ln <= hi:
                        key, span = "{}#{}".format(fp, name), (path, lo, hi)
                        break
            owners.setdefault(key, set()).add(rid)
            where[key] = span
    out = {}
    for key, rids in owners.items():
        if len(rids) != 1:
            continue          # shared: a change here names no single contract
        span = where[key]
        sha = _span_sha(*span) if span else _file_sha(os.path.join(code_root, key))
        if sha is not None:
            out.setdefault(next(iter(rids)), {})[key] = sha
    return out


def member_drift(reqs, members, lock, memberlock, code_root, current=None):  # implements: ARCH-MEMBERDRIFT-027  # implements: REQ-MEMBERDRIFT-880
    """Sorted (rid, relfile) where a confirmed requirement's dedicated member changed
    since the member-lock while the requirement's OWN contract did not. A requirement
    whose contract also drifted is skipped — that is forward drift (the spec WAS
    re-touched) and the contract-drift warning already owns it. A member with no recorded
    baseline is skipped, so a freshly-tagged file is baselined on the next sync, not nagged.

    `current` lets a caller that already computed `compute_member_hashes(code_root, members)`
    (e.g. to also rebaseline `_memberlock.json` from the same member set) pass it in instead
    of paying for a second identical hash pass; omit it to compute it here as before."""
    if current is None:
        current = compute_member_hashes(code_root, members)
    out = []
    for rid, r in reqs.items():
        if r["meta"].get("status") != "confirmed":
            continue
        if lock.get(rid) and lock[rid] != binding_hash(r["body"]):
            continue   # forward drift owns this requirement
        recorded = memberlock.get(rid, {})
        for rel, sha in current.get(rid, {}).items():
            old = recorded.get(rel)
            if old and old != sha:
                out.append((rid, rel))
    return sorted(out)


# ---------- commands ----------
def _has_section(body, name):  # implements: ARCH-CHECK-006
    """True if the body has a normative `## ` heading whose LABEL is `name`
    (case-insensitive), e.g. `## WHAT — Verify intent` for name='verify intent'.
    Anchored to the label (see `_heading_label_is`) so a commentary heading that
    merely mentions the word — `## Notes — contract caveats` — does not count as a
    Contract section, and a dash-less `## WHAT Contract` does. This keeps the gate's
    section-presence check in agreement with the drift hash, closing the
    silent-drift gap where a heading passed the gate but produced an empty hash.
    The atomic form (ARCH-ATOMICFORM-053) has no normative headings by design; its statement
    and Scenario stand in for both, so it answers True for those two names."""
    if name in CONTRACT_LABELS + ACCEPTANCE_LABELS and _atomic_spans(body):
        return True
    return any(_heading_label_is(h, name) for h in _section_headings(body))


def _has_any(body, names):  # implements: ARCH-DESCRIPTION-057
    """True if the body carries any of `names` as a section. One requirement never uses two
    spellings of the same section at once, so 'any' is not a merge — it is 'whichever name
    this file happens to use'."""
    return any(_has_section(body, n) for n in names)


def _from_any(fn, body, names):  # implements: ARCH-DESCRIPTION-057
    """`fn(body, name)` for the first of `names` that yields content, else the empty value
    `fn` returns for the first name — so the caller's type (list, str) is preserved."""
    for n in names:
        got = fn(body, n)
        if got:
            return got
    return fn(body, names[0])


def _engine_version_at(path):
    """Best-effort MAP_ENGINE_VERSION parsed from a reqmap.py at `path`; None on any failure."""
    try:
        with open(path, encoding="utf-8") as f:
            # whole file + line-anchored: a bounded read() silently returned None
            # once the header outgrew the bound, and an unanchored search could
            # match a docstring mention before the real assignment.
            m = re.search(r'(?m)^MAP_ENGINE_VERSION\s*=\s*"([^"]+)"', f.read())
        return m.group(1) if m else None
    except Exception:  # fail open — never let the staleness probe break the gate
        return None


def _ver_key(v):  # implements: ARCH-CHECK-006
    """Sortable key for a MAP_ENGINE_VERSION (`YYYY-MM-DD` + optional `.N` suffix).
    Compares the numeric suffix as an int so `.10` sorts after `.9` (lexicographic
    string compare gets that wrong)."""
    date, _, n = (v or "").partition(".")
    return (date, int(n) if n.isdigit() else 0)


def warn_if_stale():  # implements: ARCH-CHECK-006
    """Print a non-fatal notice when this vendored copy is older than the installed
    plugin's. Silent in CI: only runs when CLAUDE_PLUGIN_ROOT is set. Never raises,
    never affects the exit code."""
    try:
        root = os.environ.get("CLAUDE_PLUGIN_ROOT")
        if not root:
            return
        plugin_ver = _engine_version_at(os.path.join(root, "scripts", "reqmap.py"))
        if plugin_ver and _ver_key(plugin_ver) > _ver_key(MAP_ENGINE_VERSION):
            print(f"WARN  vendored reqmap.py is stale ({MAP_ENGINE_VERSION} < plugin "
                  f"{plugin_ver}) - re-seed: cp \"$CLAUDE_PLUGIN_ROOT/scripts/reqmap.py\" "
                  f"scripts/reqmap.py")
    except Exception:
        return


# Unambiguous test markers, trusted in ANY file: Python `def test…(`, JS/TS
# `function test…(`, Go `func TestX/Benchmark/Example/Fuzz(`, Rust `#[test]` /
# `#[tokio::test]`. Used only to confirm a tested-by file holds tests — not to count.
# Case-insensitive for Python/JS/Rust idioms, but the Go branch stays
# case-sensitive: `go test` only runs exported TestXxx/BenchmarkXxx/ExampleXxx/
# FuzzXxx — a private `func testHelper(` is NOT a test and must not satisfy a link.
_DEF_TEST_RE = re.compile(
    r"(?i:def\s+test\w*\s*\()|(?i:function\s+test\w*\s*\()|"
    r"func\s+(?:Test|Benchmark|Example|Fuzz)\w*\s*\(|"
    r"(?i:#\[\s*(?:[\w:]+::)?test\b)")
# The bare Jest/Mocha `it(` / `test(` call is too common a word to trust in prose or
# config (e.g. "it (the parser) returns None" in a .md), so it is honored ONLY in a
# JS/TS source file, where it is a genuine test idiom.
_CALL_TEST_RE = re.compile(r"\b(?:it|test)\s*\(", re.IGNORECASE)
_CALL_TEST_EXTS = (".js", ".ts", ".tsx", ".jsx", ".mjs", ".cjs")

# A stdlib-only Python suite often exposes no `def test…` — it drives its checks from a
# runnable entry point (`run` / `run_tests` / `main`) under an `if __name__ == "__main__"`
# guard, signalling pass/fail via the process exit code. Honored ONLY for a `tested-by`
# target (the author has already declared the file a test) and ONLY in a `.py` file, so a
# non-test module that merely defines a `main()` is never mistaken for a test elsewhere.
_PY_TEST_ENTRY_RE = re.compile(r"^\s*def\s+(?:run|run_tests|main)\s*\(", re.MULTILINE)
_PY_MAIN_GUARD_RE = re.compile(r"""if\s+__name__\s*==\s*["']__main__["']""")

# A shell suite declares a test as a bash function (`test_x() {`, `function test_x {`)
# or a bats case (`@test "…" {`) — none of which match the Python/JS/Go/Rust idioms
# above, so four real bash suites warned permanently in a consumer repo. The filename
# conventions are honored too: naming a file `*.test.sh` AND tagging it `tested-by`
# are two independent declarations that it is a test.
_SH_TEST_EXTS = (".sh", ".bash", ".zsh", ".bats")
_SH_TEST_NAME_RE = re.compile(r"(?:^|[._-])test[._-]|[._-]test$|^test[._-]|^tests?$", re.I)
_SH_TEST_RE = re.compile(
    r"(?m)^\s*(?:@test\b"
    r"|(?:function\s+)?(?:test|assert|check|expect|should)[\w:.-]*\s*\(\s*\)"
    r"|function\s+(?:test|assert|check|expect|should)[\w:.-]*\b)", re.I)


# A requirement whose implementation is not its own code. Both layers are covered by
# an EDGE instead of an `implements:` tag: a `need` by the `satisfies:` edges pointing
# up at it, an `aggregate` by its own `depends_on` edges pointing down.
IMPL_EXEMPT_LAYERS = ("need", "aggregate")


def _impl_exempt(meta):  # implements: ARCH-TRACE-020  # implements: REQ-TRACE-935
    """True when a requirement is exempt from the "confirmed code must exist" rule.

    One predicate, three callers (gate link-sync, `health`, the risk signals). They
    disagreed before, when `confirm` was a verb and a fourth caller: it alone did not
    exempt `layer: need`, so the layer's own reference case could not be promoted by
    the command that existed to promote it. `confirm` was removed in v5.0.0; the
    exemption it granted is now guarded by RM031 instead."""
    return (meta or {}).get("layer") in IMPL_EXEMPT_LAYERS


def _oversize(rid, r, threshold=None):  # implements: ARCH-DECOMPOSE-050  # implements: ARCH-NEXT-013
    """True when a requirement is over the shared AC-count threshold and neither
    scoped out by status nor exempted from the check.

    One predicate, two callers (`cmd_next`'s Granularity bucket and
    `lint_requirement`'s `ac-count-high` check) - they disagreed before: `next`
    iterated every status with no exempt check, `lint` scoped to `LINT_STATUSES`
    and honored `lint_exempt`, so the two commands could and did report different
    sets for the same corpus. Scoped to `LINT_STATUSES` like every other lint
    check (drafts are TODO stubs, not yet-scoped contracts - pinned down
    explicitly per Control's mandatory dissent, not left to fall out of an
    unscoped iteration by accident) and reads `lint_exempt` with the same
    `_as_list` handling `lint_requirement` already uses, so a scalar-string
    exemption behaves identically to a one-item list here too."""
    meta = r.get("meta") or {}
    if meta.get("status") not in LINT_STATUSES:
        return False
    if threshold is None:
        threshold = LINT_AC_MAX
    if _count_ac(r.get("body", "")) <= threshold:
        return False
    return "ac-count-high" not in set(_as_list(meta.get("lint_exempt")))


def _test_link_problem(path):  # implements: ARCH-TESTLINK-018  # implements: REQ-TESTLINK-930  # implements: REQ-TESTLINK-931  # implements: REQ-TESTLINK-932
    """Return a short reason a `tested-by` file fails the behavior-sync check, or ''
    when it is fine. A file that is missing, unreadable, or holds no recognizable
    test function means the link asserts coverage it does not have. Deterministic
    and warn-only — it never proves per-criterion coverage, only that real tests
    exist at the link target (per-AC mapping needs a per-AC tag, deferred)."""
    if not os.path.isfile(path):
        return "does not exist (broken tested-by link)"
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            src = f.read()
    except OSError:
        return "is unreadable"
    if _DEF_TEST_RE.search(src):
        return ""
    if path.lower().endswith(_CALL_TEST_EXTS) and _CALL_TEST_RE.search(src):
        return ""
    if (path.lower().endswith(".py")
            and _PY_TEST_ENTRY_RE.search(src) and _PY_MAIN_GUARD_RE.search(src)):
        return ""
    if path.lower().endswith(_SH_TEST_EXTS):  # implements: ARCH-TESTLINK-018  # implements: REQ-TESTLINK-932
        stem = os.path.splitext(os.path.basename(path))[0]
        if _SH_TEST_NAME_RE.search(stem) or _SH_TEST_RE.search(src):
            return ""
    return ("contains no test function "
            "(def test.../func TestX.../#[test]/it()/bash test_x()/py run|main under __main__)")


# ---------- the workspace a command runs against ----------
class Workspace(object):  # implements: ARCH-RULES-059
    """One repo, scanned once: the requirement corpus, the membership scan, the
    two roots every command resolves paths against, and the two coverage views
    the same walk produced.

    These six values are computed together in `main` and were then passed
    together to fifteen command functions, which is why `gate --design` reported
    the clump fifteen times. Naming the bundle is the whole point: a command now
    asks for the workspace it operates on, not for six positional arguments a
    caller can transpose.

    `reqs_dir` and `code_root` stay optional because two commands are defined for
    a caller that has neither: `health` skips the sections that need a code root
    rather than failing, and `next` does the same.
    """

    __slots__ = ("reqs", "members", "reqs_dir", "code_root", "ac_cover", "level_cover",
                 "_map_data")

    def __init__(self, reqs, members=None, reqs_dir=None, code_root=None,
                 ac_cover=None, level_cover=None):
        self.reqs, self.members = reqs, members
        self.reqs_dir, self.code_root = reqs_dir, code_root
        self.ac_cover, self.level_cover = ac_cover, level_cover
        self._map_data = None

    def map_data(self, root=".", members=None):
        """The assembled map document, built once per (members, root) and reused.
        `gate` asked for it twice — the RM027 freshness rule and the explicit
        `map --check` that follows — and each assembly re-ran the design review,
        the health record and the TODO parse (about a tenth of a gate's wall time)."""
        members = self.members if members is None else members
        cached = self._map_data
        if cached is None or cached[0] is not members or cached[1] != root:
            data = _assemble_map_data(self.reqs, members, self.reqs_dir, root, self.ac_cover)
            self._map_data = cached = (members, root, data)
        return cached[2]

    @classmethod
    def load(cls, reqs_dir, code_root, cache=False):
        """Parse the corpus and walk the code once — the startup path `main`
        takes before dispatching to any command."""
        members, ac_cover, level_cover = scan_all(code_root, reqs_dir, cache=cache)
        return cls(load_requirements(reqs_dir), members, reqs_dir, code_root,
                   ac_cover, level_cover)

    def levels(self):
        """The per-requirement test levels, walking for them only if the cached
        members-only scan skipped them (see `scan_all`'s docstring)."""
        if self.level_cover is None:
            self.level_cover = scan_test_levels(self.code_root, self.reqs_dir)
        return self.level_cover


# ---------- gate rules ----------
class GateContext(object):  # implements: ARCH-RULES-059  # implements: REQ-RULES-947
    """Everything a gate rule may read, computed once per run. `members` is the view
    `--since` may have narrowed; `full_members` is always the whole scan, because an
    existence check ("does an implements tag exist AT ALL") must never be answered
    from a filtered view."""
    # Set by `cmd_check` when a full scan already hashed every member; any other
    # caller of run_gate_rules leaves it None and the member-drift rule hashes
    # for itself. Defaulted here so a second caller cannot trip over its absence.
    full_member_hashes = None


    def __init__(self, ws, since=None, full_members=None, update_lock=False):
        reqs, members = ws.reqs, ws.members
        reqs_dir, code_root = ws.reqs_dir, ws.code_root
        self.ws = ws
        self.reqs = reqs
        self.members = members
        self.full_members = members if full_members is None else full_members
        self.reqs_dir, self.code_root, self.since = reqs_dir, code_root, since
        self.update_lock = update_lock
        self.cap_ids = set(reqs)
        self.ac_cover = (scan_ac_verifies(code_root, reqs_dir)
                         if ws.ac_cover is None else ws.ac_cover)
        self.level_cover = (scan_test_levels(code_root, reqs_dir)
                            if ws.level_cover is None else ws.level_cover)
        # the FULL scan, not the --since-narrowed one: whether this repo has adopted
        # `validated-against:` at all is a property of the repo, not of one diff. Read
        # narrowed, a push that happened to touch one validation file switched the rule
        # on for every OTHER need — half a pair is not a corpus-wide opt-in.
        self.any_validation = any(x[0] == "validated-against"
                                  for hits in self.full_members.values() for x in hits)
        self.satisfied_by = {rid: [] for rid in reqs}
        self.dependents = {}
        for rid, r in reqs.items():
            for up in _as_list(r["meta"].get("satisfies")):
                if up in self.satisfied_by:
                    self.satisfied_by[up].append(rid)
            for dep in _as_list(r["meta"].get("depends_on")):
                self.dependents.setdefault(dep, set()).add(rid)
        self.lock = load_lock(reqs_dir)
        self.new_lock = {rid: binding_hash(r["body"]) for rid, r in reqs.items()}
        self.source_repo = _is_source_repo(code_root)

    def req(self, rid):
        r = self.reqs[rid]
        return r if isinstance(r, Requirement) else Requirement(r)

    def in_scope(self, rid):
        """--since scoping: an already-true finding is reported only when the
        requirement's members are in the diff, or when there is no --since at all."""
        return rid in self.members or not self.since

    def roles(self, rid):
        """Tag roles a requirement carries, always over the FULL scan. A rule asks
        `--since` for its SCOPE (`in_scope`), never for its FACTS: the narrowed member
        set is missing every unchanged file, so reading a fact from it reports the
        absence of a tag that is sitting in the tree."""
        return [x[0] for x in self.full_members.get(rid, [])]


@gate_rule("RM001", "error")
def _rule_dangling_tag(ctx):  # implements: REQ-CHECK-828  # implements: REQ-RULES-947
    for cap in ctx.members:
        if cap not in ctx.cap_ids:
            yield None, f"dangling tag: code references {cap} but no requirement exists"


@gate_rule("RM002", "error")
def _rule_frontmatter(ctx):  # implements: ARCH-ATOMICFORM-053  # implements: ARCH-LEVEL-051  # implements: REQ-CHECK-828  # implements: REQ-LEVEL-862
    for rid, r in ctx.reqs.items():
        m = r["meta"]
        if m.get("status") not in VALID_STATUS:
            yield rid, f"{rid}: invalid status {m.get('status')!r}"
        _frm = m.get("form")
        if _frm and _frm not in VALID_FORM:
            yield rid, f"{rid}: invalid form {_frm!r} (expected one of {sorted(VALID_FORM)})"
        if _frm == "atomic" and not _atomic_spans(r["body"]):
            yield rid, (f"{rid}: form: atomic but the body has no `>` statement plus "
                        f"`Scenario:` block before the first `## ` heading")
        _lvl = m.get("level")
        if _lvl and _lvl not in VALID_LEVEL:
            yield rid, f"{rid}: invalid level {_lvl!r} (expected one of {sorted(VALID_LEVEL)})"
        if m.get("layer") not in VALID_LAYER:
            yield rid, f"{rid}: invalid layer {m.get('layer')!r}"


@gate_rule("RM031", "warn")
def _rule_uncovered_aggregate(ctx):  # implements: ARCH-TRACE-020  # implements: REQ-TRACE-935
    """An `aggregate` is exempt from the implements and tested-by rules because it is
    covered downward by its `depends_on`. An empty list is therefore not a small
    omission: it claims the exemption and supplies nothing to be covered by."""
    for rid in sorted(ctx.cap_ids):
        r = ctx.req(rid)
        meta = r["meta"]
        if meta.get("layer") != "aggregate" or meta.get("status") not in ENFORCED:
            continue
        if _as_list(meta.get("depends_on")) or not ctx.in_scope(rid):
            continue
        yield rid, ("{}: layer: aggregate with an empty `depends_on` — it is exempt "
                    "from the implements and tested-by rules because its dependencies "
                    "cover it, and it has none".format(rid))


@gate_rule("RM003", "error")
def _rule_depends_on_missing(ctx):  # implements: REQ-CHECK-828
    for rid, r in ctx.reqs.items():
        for dep in _as_list(r["meta"].get("depends_on")):
            if dep not in ctx.cap_ids:
                yield rid, f"{rid}: depends_on missing {dep}"


@gate_rule("RM004", "warn")
def _rule_milestone_shape(ctx):
    # an optional, roadmap-only field: a malformed value silently fails to sort in the
    # Roadmap rather than breaking the build, so it warns, only when present and not deprecated.
    for rid, r in ctx.reqs.items():
        m = r["meta"]
        ms = m.get("milestone")
        if ms and m.get("status") != "deprecated" and not MILESTONE_RE.match(str(ms).strip()):
            yield rid, f"{rid}: milestone {ms!r} is malformed (expected v<digits>[.<digits>…], e.g. v1.14)"


@gate_rule("RM005", "warn")
def _rule_satisfies_dangling(ctx):  # implements: ARCH-TRACE-020  # implements: REQ-TRACE-934
    # a dangling upstream id is a WARN not an ERROR — the need may be authored later
    # or live in an external tracker.
    for rid, r in ctx.reqs.items():
        for up in _as_list(r["meta"].get("satisfies")):
            if up not in ctx.cap_ids:
                yield rid, f"{rid}: satisfies {up} but no such requirement (upstream trace dangling)"


@gate_rule("RM006", "error")
def _rule_no_implements(ctx):  # implements: ARCH-TRACE-020  # implements: REQ-CHECK-828  # implements: REQ-RULES-947
    for rid, r in ctx.reqs.items():
        m = r["meta"]
        if m.get("status") in ENFORCED and not _impl_exempt(m) \
                and "implements" not in ctx.roles(rid) and ctx.in_scope(rid):
            yield rid, f"{rid}: status {m['status']} but no implements: tag found in code"


@gate_rule("RM007", "warn")
def _rule_no_tested_by(ctx):  # implements: REQ-CHECK-829
    for rid, r in ctx.reqs.items():
        m = r["meta"]
        if m.get("status") == "confirmed" and "tested-by" not in ctx.roles(rid) \
                and not m.get("test_exempt") and not _impl_exempt(m) and ctx.in_scope(rid):
            yield rid, f"{rid}: confirmed but no tested-by: tag — acceptance tests not linked"


@gate_rule("RM008", "warn")
def _rule_need_not_validated(ctx):  # implements: ARCH-VLEVEL-037  # implements: REQ-CHECK-831
    # a need is validated, not tested; opt-in via any `validated-against` tag in the repo.
    if not ctx.any_validation:
        return
    for rid, r in ctx.reqs.items():
        m = r["meta"]
        if m.get("layer") == "need" and m.get("status") == "confirmed" \
                and "validated-against" not in ctx.roles(rid) and ctx.in_scope(rid):
            yield rid, (f"{rid}: confirmed need with no `validated-against:` tag — "
                        "nothing shows the need was actually met")


@gate_rule("RM009", "warn")
def _rule_bus_only_system_level(ctx):  # implements: ARCH-VLEVEL-037  # implements: REQ-CHECK-831
    for rid, r in ctx.reqs.items():
        m = r["meta"]
        if m.get("status") == "confirmed" and m.get("layer") == "bus" \
                and set(ctx.level_cover.get(rid, {})) == {"system"}:
            yield rid, (f"{rid}: bus capability verified only at @system level — "
                        "add a @unit or @integration `tested-by:` link")


@gate_rule("RM010", "warn")
def _rule_level_rung(ctx):  # implements: ARCH-VRUNGS-054
    for rid, r in ctx.reqs.items():
        m = r["meta"]
        _want = LEVEL_TEST_PAIR.get(m.get("level"))
        if m.get("status") == "confirmed" and _want:
            _have = set(ctx.level_cover.get(rid, {}))
            if _have and _want not in _have:
                yield rid, (f"{rid}: level: {m['level']} is verified at "
                            f"{'/'.join('@' + x for x in sorted(_have))} but not @{_want} — "
                            f"add a @{_want} `tested-by:` link, or change the level")


@gate_rule("RM011", "warn")
def _rule_owner_auto(ctx):
    for rid, r in ctx.reqs.items():
        m = r["meta"]
        if m.get("status") == "confirmed" and m.get("owner", "auto") in ("auto", "", None):
            yield rid, f"{rid}: confirmed requirement has owner: auto — assign a named owner"


@gate_rule("RM012", "warn", strict=True)
def _rule_test_link(ctx):  # implements: ARCH-TESTLINK-018  # implements: REQ-TESTLINK-933
    # checked at EVERY status; only a confirmed requirement's broken link is strict-promoted
    # (see cmd_check: a non-confirmed hit is downgraded to a plain warn there).
    # one read per test file, not one per requirement naming it: a suite every
    # requirement points at (this repo's test_reqmap.py) was opened 206 times per gate
    problems = {}
    for rid, r in ctx.reqs.items():
        tests = [x for x in ctx.full_members.get(rid, []) if x[0] == "tested-by"]
        for fp in sorted({t[1] for t in tests}):
            if fp not in problems:
                problems[fp] = _test_link_problem(os.path.join(ctx.code_root, fp))
            if problems[fp]:
                yield rid, f"{rid}: tested-by {fp} {problems[fp]}"


@gate_rule("RM013", "warn")
def _rule_case_coverage(ctx):  # implements: ARCH-ACVERIFY-019
    # ONE aggregated line per requirement, only once it has adopted per-case tagging.
    for rid, r in ctx.reqs.items():
        if r["meta"].get("status") != "confirmed":
            continue
        labels = _automatable_acs(r["body"])
        covered = ctx.ac_cover.get(rid, {})
        if labels and covered:
            missing = [ac for ac in labels if ac not in covered]
            if missing:
                yield rid, (f"{rid}: {len(labels) - len(missing)}/{len(labels)} automatable criteria "
                            f"carry a `# verifies:` tag — missing " + ", ".join(missing))


@gate_rule("RM014", "warn")
def _rule_confirmed_sections(ctx):  # implements: REQ-CHECK-829
    for rid, r in ctx.reqs.items():
        if r["meta"].get("status") != "confirmed":
            continue
        if not _has_any(r["body"], CONTRACT_LABELS):
            yield rid, (f"{rid}: confirmed but missing '## Description' section — "
                        "add the normative contract or drop status back to in-progress")
        if not _has_any(r["body"], ACCEPTANCE_LABELS):
            yield rid, (f"{rid}: confirmed but missing '## Cases' section — "
                        "add acceptance criteria or drop status back to in-progress")


@gate_rule("RM015", "warn")
def _rule_need_unsatisfied(ctx):  # implements: ARCH-TRACE-020  # implements: REQ-TRACE-934
    for rid, r in ctx.reqs.items():
        m = r["meta"]
        if m.get("layer") == "need" and m.get("status") in ENFORCED and not ctx.satisfied_by.get(rid):
            yield rid, f"{rid}: need has no requirement that satisfies it (upstream trace unaddressed)"


@gate_rule("RM016", "warn")
def _rule_corrupt_lock(ctx):
    # load_lock fails open ({}) on an absent OR corrupt lock; surface the corrupt case so a
    # silently-disabled drift signal is visible.
    lp = lock_path(ctx.reqs_dir)
    if os.path.exists(lp):
        try:
            with open(lp, encoding="utf-8") as f:
                if not isinstance(json.load(f), dict):
                    raise ValueError("not a JSON object")   # `[]`/`null`: load_lock swallows it too
        except (ValueError, OSError):
            yield None, ("_reqlock.json present but unreadable (corrupt/merge-conflicted) "
                         "— drift detection skipped this run; re-run with --update-lock")


@gate_rule("RM017", "warn", only_source_repo=True)
def _rule_viewer_fixture(ctx):  # implements: ARCH-VIEWER-007
    # the viewer's fallback fixture vs the live registry — this repository only.
    candidate = os.path.join(ctx.code_root, "app", "src", "lib", "data.js")
    if not os.path.exists(candidate):
        return
    nodes = [{"id": rid, "contract": _from_any(_bullets, r["body"], CONTRACT_LABELS)}
             for rid, r in ctx.reqs.items()]
    drifted = check_viewer_data_sync(candidate, nodes)
    if drifted:
        yield None, ("app/src/lib/data.js out of sync with {} requirement(s): {} — regenerate its "
                     "BAKED fixture or accept the drift is intentional for this fallback demo data."
                     .format(len(drifted), ", ".join(drifted)))


@gate_rule("RM029", "warn")
def _rule_translation_parity(ctx):  # implements: ARCH-TRANSLATE-044  # implements: REQ-TRANSLATE-967
    """A cached translation carrying a field the requirement itself does not emit.

    `translate` and the map both derive from the same requirement, and each was correct
    against it: the map emits no intent when the quote IS the obligation, while the
    translator had been handed the raw quote. Nothing compared the two, so a translated
    document showed a section the untranslated one hides — invisible until a corpus had
    both features populated at once. Fields the requirement has and the translation
    lacks are NOT reported: a partial translation is a normal intermediate state."""
    translations = _load_translations(ctx.reqs, ctx.reqs_dir)
    if not translations:
        return
    for rid in sorted(translations):
        r = ctx.reqs.get(rid)
        if not r:
            continue
        body = r["body"]
        source = {
            "title": _req_title(body, rid),
            "intent": _distinct_intent(body),
            "contract": _from_any(_section_raw, body, CONTRACT_LABELS) or "",
            "acceptance": _from_any(_section_raw, body, ACCEPTANCE_LABELS) or "",
        }
        for locale in sorted(translations[rid]):
            entry = translations[rid][locale] or {}
            extra = sorted(f for f, v in source.items()
                           if not str(v).strip() and str(entry.get(f, "")).strip())
            if extra:
                yield rid, ("{}: translation `{}` carries {} the requirement does not emit — "
                            "re-run `translate` so the two agree, or clear the field"
                            .format(rid, locale, ", ".join("`" + f + "`" for f in extra)))


@gate_rule("RM030", "warn")  # implements: ARCH-AUDIT-065  # implements: REQ-AUDIT-971
def _rule_exemption_without_reason(ctx):
    """An exemption whose check is never mentioned in the requirement's own prose.

    Warn-only, and never promoted under `--strict`: the point is to make silencing a
    finding cost a sentence, not to make it impossible. A shape that is genuinely
    deliberate is one line away from clean; a shape that was silenced to make a run
    green has nobody willing to write that line."""
    for rid in sorted(ctx.reqs):
        r = ctx.reqs[rid]
        for field in ("lint_exempt", "gate_exempt"):
            for check in _as_list(r["meta"].get(field)):
                if not _exemption_reason_recorded(r["body"], check):
                    yield rid, ("{}: `{}: [{}]` silences a finding with no reason recorded "
                                "\u2014 say why in the requirement's prose, or drop the "
                                "exemption and fix what it hides".format(rid, field, check))


# The two rules that say "the spec and the code no longer agree". They warn by default
# and promote under `--strict`; a repo may also promote them for itself with
# `DRIFT_SEVERITY: "error"` in `_config.json`. The default stays `warn` because the
# evidence for that is recorded and unchanged (ADR-0002): a spec-first edit legitimately
# drifts the contract ahead of the code, and a check that fails on correct work is a
# check someone bolts `continue-on-error` onto and never reads again. Which side of that
# trade a repo wants is the repo's call, not the tool's.
DRIFT_RULES = ("RM018", "RM019")
DRIFT_SEVERITY = "warn"          # or "error", per repo, via `_config.json`


@gate_rule("RM018", "warn", strict=True)
def _rule_drift(ctx):  # implements: ARCH-DRIFT-003  # implements: ARCH-DRIFTIMPACT-035  # implements: REQ-CHECK-829  # implements: REQ-DRIFTIMPACT-843
    for rid, r in ctx.reqs.items():
        h, old = ctx.new_lock[rid], ctx.lock.get(rid)
        if old and old != h and r["meta"].get("status") == "confirmed":
            locs = [f"{fp}:{ln}" for (_role, fp, ln) in ctx.members.get(rid, [])]
            where = ", ".join(locs) if locs else "no members tagged — add an implements: tag"
            deps_of = sorted(ctx.dependents.get(rid, ()))
            fanout = "; review dependent(s): " + ", ".join(deps_of) if deps_of else ""
            yield rid, (f"{rid}: DRIFT — contract changed since lock; "
                        f"re-check {len(locs)} member(s): {where}{fanout}")


@gate_rule("RM019", "warn", strict=True)
def _rule_member_drift(ctx):  # implements: ARCH-MEMBERDRIFT-027
    memberlock = load_memberlock(ctx.reqs_dir)
    for rid, rel in member_drift(ctx.reqs, ctx.members, ctx.lock, memberlock, ctx.code_root,
                                 current=ctx.full_member_hashes):
        yield rid, (f"{rid}: MEMBER DRIFT — {rel} changed since lock but the contract "
                    "was not re-touched; re-check the requirement, or run sync to re-baseline")


@gate_rule("RM020", "warn")
def _rule_untracked_lock(ctx):
    for lp_rel in untracked_locks(ctx.reqs_dir):
        yield None, (f"{lp_rel} exists on disk but is not git-tracked — `git add {lp_rel}` so "
                     "drift detection works in CI (an uncommitted lock is invisible to a fresh checkout)")


@gate_rule("RM021", "warn")
def _rule_doc_bundle(ctx):  # implements: ARCH-DOCBUNDLE-026
    for rel in untagged_doc_bundles(ctx.code_root, ctx.full_members, ctx.reqs_dir):
        yield None, (f"{rel}: large docs/ HTML bundle ({DOC_BUNDLE_MIN_BYTES // 1000}KB+) has no "
                     "generated-from: tag — link it to the requirement(s) it derives from "
                     "(`<!-- generated-from: A, B -->`), or add it to .reqmapignore")


@gate_rule("RM022", "warn")
def _rule_untracked_members(ctx):  # implements: ARCH-TRACKED-042
    _untracked = untracked_members(ctx.code_root, ctx.full_members)
    if _untracked:
        yield None, (
            "{} member(s) are not tracked by git: {} — the committed map records them, but a "
            "fresh checkout has no such file, so it cannot be regenerated there. Commit them, "
            "or exclude them in .reqmapignore.".format(
                len(_untracked), ", ".join(_untracked[:5])
                + ("" if len(_untracked) <= 5 else ", …")))


@gate_rule("RM023", "warn")
def _rule_unscanned_tags(ctx):  # implements: ARCH-UNSCANNEDTAG-045
    _unscanned = tagged_unscanned_files(ctx.code_root, ctx.reqs_dir)
    if _unscanned:
        yield None, (
            "{} tag(s) in file type(s) the scan never reads: {} — those files are not members. "
            "Move the tag into a scannable file, or ask for the type to be added to the scan.".format(
                len(_unscanned), ", ".join(_unscanned[:5])
                + ("" if len(_unscanned) <= 5 else ", …")))


@gate_rule("RM024", "warn")
def _rule_orphan_code(ctx):  # implements: ARCH-ORPHANCODE-034
    covered = {fp for hits in ctx.full_members.values() for (_role, fp, _ln) in hits}
    covered.update(fp for acs in ctx.ac_cover.values()
                   for locs in acs.values() for (fp, _ln) in locs)
    for rel in orphan_code_files(ctx.code_root, covered, ctx.reqs_dir):
        yield None, (f"{rel}: {ORPHAN_CODE_MIN_LOC}+-line code file has no membership tag — "
                     "link it (`# implements: <ID>`), draft a requirement for it "
                     "(`reqmap.py init`), or add it to .reqmapignore")


def _legacy_schema_ids(reqs):  # implements: ARCH-ATOMICFORM-053
    """"Legacy" is the Input/Description/Output triad only. It used to be "no `## Verify
    intent` section", which made the lean form read as legacy and produced one warning
    naming every requirement in the corpus."""
    return [rid for rid in sorted(reqs) if _has_any(reqs[rid]["body"], ("input", "output"))]


@gate_rule("RM025", "warn")
def _rule_legacy_schema(ctx):  # implements: REQ-CHECK-831
    legacy = _legacy_schema_ids(ctx.reqs)
    if legacy:
        yield None, ("{}/{} requirement(s) use the legacy schema (the Input/Description/"
                     "Output triad) — `findings` is inactive for them: {}"
                     .format(len(legacy), len(ctx.reqs), ", ".join(legacy)))


@gate_rule("RM026", "warn")
def _rule_depends_on_cycle(ctx):  # implements: ARCH-CHECK-006  # implements: REQ-CHECK-831
    # warn, not error: a cycle is a modelling call across several requirements (ADR-0002).
    for _cyc in _dependency_cycles(ctx.reqs):
        yield None, ("depends_on cycle: " + " -> ".join(_cyc)
                     + " — no requirement in a cycle can be built before the others; "
                       "drop the edge that closes it")


@gate_rule("RM027", "warn")
def _rule_map_stale(ctx):  # implements: ARCH-MAP-007
    # skipped under update_lock: `sync` regenerates the map moments later.
    if ctx.update_lock:
        return
    try:
        stale_map = _stale_artifacts(
            ctx.ws.map_data(ctx.code_root, ctx.full_members),
            ctx.reqs_dir, ctx.code_root, ctx.reqs)
    except Exception:
        stale_map = []            # fail-open — a freshness probe never blocks the gate
    if stale_map:
        yield None, ("committed map is stale: " + ", ".join(stale_map)
                     + " — run `reqmap.py sync` (or `map`) and commit the result")


def run_gate_rules(ctx, strict=False):  # implements: ARCH-RULES-059  # implements: REQ-RULES-947  # implements: REQ-RULES-948  # implements: REQ-RULES-989
    """Run every registered rule over `ctx` -> (errors, warns) as Finding lists, in
    registry order. A rule's `strict` flag promotes its findings to errors under
    `--strict`, except RM012 on a non-confirmed requirement, which stays a plain warn
    so a draft-heavy consumer's strict CI cannot start failing on it. A requirement
    whose `gate_exempt:` names the rule's code is skipped for that rule.

    `DRIFT_SEVERITY: "error"` in a repo's `_config.json` promotes the two drift rules
    for THAT repo without `--strict` and without moving anyone else's default. The
    promotion is resolved here, per run, and never written back onto the Rule: the
    registry is module state shared by two `cmd_check` calls inside `audit`, and a
    mutation would leak from the first into the second. `gate_exempt:` is checked
    before any of this, so a requirement's own written-down exemption still wins —
    a repo-wide dial must not silently overrule a decision made per requirement."""
    errors, warns = [], []
    for rule in GATE_RULES:
        if rule.only_source_repo and not ctx.source_repo:
            continue
        for rid, msg in rule.fn(ctx):
            if rid is not None and ctx.req(rid).exempt_from(rule.id):
                continue
            sev = rule.severity
            if rule.strict and strict:
                confirmed = rid is None or ctx.req(rid).status == "confirmed"
                if rule.id != "RM012" or confirmed:
                    sev = "error"
            if sev != "error" and rule.id in DRIFT_RULES and DRIFT_SEVERITY == "error":
                sev = "error"
            (errors if sev == "error" else warns).append(Finding(rule.id, sev, rid, msg))
    return errors, warns


def _link_sync_errors(reqs, members):  # implements: ARCH-HEALTH-017  # implements: REQ-RULES-947
    """`gate`'s ERROR-level link-sync problems (dangling tags, enforced requirements
    with no `implements:` member) as message strings, for `health` — the same two
    rules the gate runs (RM001, RM006), read from the registry so the two commands
    cannot drift apart again (RM-6 / Senate run reqmap-health-gate-cleanliness)."""
    ctx = GateContext.__new__(GateContext)
    ctx.reqs, ctx.members, ctx.full_members = reqs, members, members
    ctx.cap_ids, ctx.since = set(reqs), None
    # honour `gate_exempt:` exactly as run_gate_rules does, or a requirement the gate
    # passes still counts as a link-sync error in `health` and the committed map
    return [msg for rule_id in ("RM001", "RM006")
            for rid, msg in gate_rule_by_id(rule_id).fn(ctx)
            if rid is None or not ctx.req(rid).exempt_from(rule_id)]


def _is_source_repo(code_root):
    """True inside the requirement-manager repository itself (the one that dogfoods
    the engine), never in a consumer: the plugin manifest and the viewer's source
    both sit under `code_root`. Rules about this repo's own artifacts key on it."""
    return (os.path.exists(os.path.join(code_root, "plugin", ".claude-plugin", "plugin.json"))
            and os.path.exists(os.path.join(code_root, "app", "src", "lib", "data.js")))


def cmd_check(ws, update_lock, strict=False, as_json=False, since=None,
              accept_drift=True, drift_reason=None):  # implements: ARCH-CHECK-006  # implements: ARCH-RULES-059  # implements: REQ-CHECK-832  # implements: REQ-CHECK-833  # implements: REQ-RULES-948
    """The gate: run GATE_RULES, print findings with their codes, advance the lock when
    asked. Report-only unless `update_lock` (that is `sync`).

    `accept_drift` stays a plain boolean and the reason travels beside it. Folding the
    two into one value would have made `--accept-drift ""` falsy, and an empty string
    is a caller who passed the flag — reading it as 'did not' would demote contracts
    they meant to keep."""
    reqs, members, reqs_dir, code_root = ws.reqs, ws.members, ws.reqs_dir, ws.code_root
    code_root = code_root or "."   # a workspace built without one gates the cwd
    ac_cover, level_cover = ws.ac_cover, ws.level_cover
    warn_if_stale()
    full_members = members
    pre_warns = []
    # --since: scope checks to requirements whose member files changed since ref.
    # Fail-open: fall back to full scan with WARN if git is unavailable or ref invalid.
    if since:
        changed = _since_changed_files(since, code_root)
        if changed is None:
            pre_warns.append(Finding("RM000", "warn", None,
                                     f"--since {since!r}: git diff failed or ref not found; falling back to full scan"))
        else:
            filtered = {}
            for cap, entries in members.items():
                kept = [(role, fp, ln) for role, fp, ln in entries
                        if _path_key(os.path.join(code_root, fp)) in changed]
                if kept:
                    filtered[cap] = kept
            members = filtered
    # built from the resolved locals, not from `ws` directly: `--since` narrowed
    # `members`, and `code_root` fell back to the cwd just above.
    ctx = GateContext(Workspace(reqs, members, reqs_dir, code_root,
                                ac_cover, level_cover),
                      since=since, full_members=full_members, update_lock=update_lock)
    # the CALLER's workspace carries the map-document cache, so the freshness rule and
    # the `map --check` that `gate` runs next share one assembly instead of two
    ctx.ws = ws
    # sync on a full scan re-baselines _memberlock below from this same hash set —
    # computed once and handed to the member-drift rule instead of hashing twice.
    _reuse_full_hashes = update_lock and members is full_members
    ctx.full_member_hashes = compute_member_hashes(code_root, full_members) if _reuse_full_hashes else None
    errors, warns = run_gate_rules(ctx, strict=strict)
    warns = pre_warns + warns
    legacy = _legacy_schema_ids(reqs)
    lock, new_lock = ctx.lock, ctx.new_lock

    if update_lock:
        changed = [(rid, lock.get(rid), h)
                   for rid, h in sorted(new_lock.items()) if lock.get(rid) != h]
        removed = [rid for rid in sorted(lock) if rid not in new_lock]
        for rid, old_h, new_h in changed:
            old_short = old_h[:8] if old_h else "new"
            print(f"  lock update: {rid} hash changed ({old_short}->{new_h[:8]})")
        for rid in removed:
            print(f"  lock update: {rid} removed from lock")
        # sync drift guard: refuse to silently re-baseline an EDITED confirmed/implemented
        # contract unless the caller explicitly accepts it (accept_drift). A brand-new
        # requirement (old hash None) is not drift.
        confirmed_drift = [rid for (rid, old_h, _h) in changed
                           if old_h is not None
                           and reqs.get(rid, {}).get("meta", {}).get("status") in ("confirmed", "implemented")]
        if confirmed_drift and accept_drift:
            record_accepted_drift(reqs_dir, confirmed_drift, new_lock,
                                  drift_reason, set(new_lock))
            print("  accepted drift on %d confirmed contract(s), reason: %s"
                  % (len(confirmed_drift), drift_reason or "(none given)"))
        if confirmed_drift and not accept_drift:  # implements: REQ-PROMOTE-974
            # An edited contract has not been re-validated by anyone, so it stops
            # claiming it was: status goes back to `draft` and the baseline advances.
            # Say it loudly — a demoted requirement leaves the gate's enforcement
            # (no implements: requirement, no drift check) until a human confirms it
            # again, and that is exactly the kind of thing that must not happen
            # quietly. `--accept-drift` is the escape hatch for "I edited it and it
            # is still valid": it keeps the status and advances the baseline.
            print("Contract changed on %d confirmed requirement(s) \u2014 status back to "
                  "`draft`, because nobody has re-validated them:" % len(confirmed_drift))
            for rid in confirmed_drift:
                r = reqs.get(rid) or {}
                was = r.get("meta", {}).get("status")
                if r and _write_frontmatter_status(r, "draft"):
                    r["meta"]["status"] = "draft"   # keep this run's own report honest
                    print("  demoted: %s  %s -> draft" % (rid, was))
                    # Name the code, not just the requirement: a changed contract is a
                    # question about whether the code still matches it, and the answer
                    # lives in these files. Without them the demotion says what happened
                    # and not what to do about it.
                    locs = ["%s:%s" % (fp, ln) for (_role, fp, ln) in full_members.get(rid, ())]
                    if locs:
                        print("      re-check %d member(s): %s" % (len(locs), ", ".join(locs)))
                    else:
                        print("      no members tagged — add an `implements:` tag")
                else:
                    print("  WARN  %s: no `status:` line to change" % rid)
            print("  These no longer gate. Re-read the code above against the new contract,")
            print("  change whichever is wrong, then set the status back by hand — or re-run")
            print("  with --accept-drift if the edit did not change what the code must do.")
        save_lock(reqs_dir, new_lock)
        save_memberlock(reqs_dir, ctx.full_member_hashes
                         if ctx.full_member_hashes is not None
                         else compute_member_hashes(code_root, full_members))
        print("lock updated.")
        # Clarifying one requirement can raise questions the previous text never had —
        # a new clause with an unbounded quantity, a case with no failure path. Nobody
        # re-reads the whole corpus after an edit, so the diff is reported here, where
        # every edit already passes.  # implements: REQ-CLARIFY-975
        _q_now = blocking_question_rules(reqs)
        _q_before = load_clarifylock(reqs_dir)
        _fresh = sorted((rid, sorted(set(rules) - set(_q_before.get(rid, []))))
                        for rid, rules in _q_now.items())
        _fresh = [(rid, rules) for rid, rules in _fresh if rules and rid in _q_before]
        if _fresh:
            print("")
            print("New open question(s) since the last sync — an edit raised them:")
            for rid, rules in _fresh:
                print("  %s: %s" % (rid, ", ".join(rules)))
            print("  Read them with `reqmap.py clarify <ID>`.")
        save_clarifylock(reqs_dir, _q_now)

    # Integration-artifact freshness (this repo's generated tool_definition.json + the
    # SKILL.universal.md command table); skipped silently when the artifacts don't exist.
    # Must run BEFORE the as_json early-return so --json also exits non-zero on it.
    # Only inside the plugin package itself: two directories above a VENDORED engine
    # (`<consumer>/scripts/reqmap.py`) is the consumer's repo root, and a consumer that
    # ships its own `tool_definition.json` there was failing its gate on ours.
    plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _stale = []
    if os.path.exists(os.path.join(plugin_root, ".claude-plugin", "plugin.json")):
        _stale = _check_integration_fresh(plugin_root)
    if _stale:
        errors = list(errors) + [Finding("RM028", "error", None,
                                         "stale integration artifact(s): " + ", ".join(_stale))]
    # counted after the demotion loop above, so a `sync` that just demoted reports the
    # corpus it leaves behind rather than the one it found
    n_confirmed = sum(1 for r in reqs.values() if r["meta"].get("status") == "confirmed")

    if as_json:
        print(json.dumps({"ok": not errors,
                          "errors": [str(e) for e in errors],
                          "warnings": [str(w) for w in warns],
                          "findings": [dict(f) for f in errors + warns]}))
        return 1 if errors else 0

    for w in warns:
        print("WARN ", w["rule"], str(w))
    for e in errors:
        print("ERROR", e["rule"], str(e))
    if _stale:
        print("ERROR: stale generated integration artifact(s): " + ", ".join(_stale)
              + " — run `python scripts/reqmap.py sync` and commit.", file=sys.stderr)

    n_find = sum(len(items) for _rid, _t, items in collect_findings(reqs))
    if n_find:
        print(f"info  {n_find} open verify-intent finding(s) — run `reqmap.py sync`")

    # recompute: the demotion loop above may have flipped some status from
    # "confirmed" to "draft" since n_confirmed was first snapshotted.
    n_confirmed = sum(1 for r in reqs.values() if r["meta"].get("status") == "confirmed")
    print(f"\n{len(reqs)} requirements ({n_confirmed} confirmed, {len(legacy)} legacy-schema), "
          f"{sum(len(v) for v in members.values())} members, "
          f"{len(errors)} errors, {len(warns)} warnings.")
    return 1 if errors else 0



# Built-in scaffold so `new` needs no separate templates/ dir — the engine is
# self-contained (one file). An on-disk templates/requirement.md still overrides
# it when cmd_new is given a tmpl_path that exists.
REQUIREMENT_TEMPLATE = """\
---
id: AREA-NAME-NNN
status: draft        # draft | baseline | in-progress | implemented | confirmed | deprecated
layer: feature       # bus | feature | need | aggregate
owner: Alex
priority:            # must-have | should-have | could-have | wont-have (optional)
depends_on: []       # ids of bus/other capabilities this builds on
superseded_by:       # <ID>, if replaced
# level:             # optional: system | architecture | code — the V-model left arm.
#                    #   Adopting it turns on the level-fit and rung checks; a corpus
#                    #   that never sets it keeps the pre-V-model behaviour exactly.
# satisfies: []      # optional: the level above this one (system <- architecture <- code)
# area:              # optional: System Map grouping label (else the id prefix is used)
---

# Short name

## Description
> 1–3 plain sentences anyone can follow — what this is, why it exists, and what
> breaks without it. No jargon; this is the angle a non-expert reads first. The
> quote is rationale, not an obligation: it is not hashed and never trips drift.

Every bullet below is binding.
<!-- Audience: a developer new to this project. Six rules:
     1. Name the subject: "`init` creates the folder", never "It creates the folder".
     2. Present tense — no "shall", no "must". The line above already binds every clause.
     3. One binding statement per bullet, in at most three sentences; the extra
        sentences state the first's consequence, never a second obligation.
     4. Define project-specific terms inline on first use; programming terms need none.
     5. Group clauses past five, with bold labels (see below).
     6. Keep a clause to at most 3 sentences and 150 words — `lint` enforces both.
     Scope: one capability = one behavior that fails independently. Many clauses AND
     many acceptance criteria together mean several capabilities — split them
     (`lint` flags this as 'over-scoped'). -->

**What it does**
- `<subject>` does one thing, stated so a test could check it. No function names; true
  regardless of how the code is implemented.
  <!-- Rationale: why this specific behavior, one clause, only when not self-evident -->

**What it produces**
- `<subject>` returns <output shape and allowed values>.
- `<subject>` handles a missing or invalid optional input by <behavior>.

## Verify intent (open questions for the human)
- Observed: <a behavior that may be an AI accident — swallowed error, empty-string
  fallback, magic constant, unreachable branch>. Intended, or a bug to fix?

## Cases (= tests)
<!-- Write at least one case from the CALLER's side, not the implementation's: the
     cases an author reaches for first vary the quality of one kind of input and
     never its kind. `clarify` names that shape (case-monoculture).
     Keep Given/When/Then concrete and self-explanatory; spell out any term the
     Description introduced. -->
CASE-1  <!-- verifiable by: automated test | manual | inspection | load test -->
  Given  <precondition>
  When   <action>
  Then   <observable, pass/fail result>   (one test per case; each maps to tested-by)

## Context (non-binding)
<!-- Everything here is commentary: not hashed, not linted, never trips drift. On
     any conflict with the Description + Cases above, they win. Bold sub-labels
     are the same clause-group convention the Description uses (ADR-0017) — keep
     only the ones you need. -->
**Notes**
- A known fragility/footgun the implementer should know but which is NOT enforced.

**Example**
- e.g. Ana marks AUTH-001 confirmed, later edits its contract text; at commit
  `check` tells her "DRIFT — contract changed since lock" so she re-reviews.

**Current implementation**
- How the code does it today (the volatile narrative — may drift from the contract).

"""


_REQ_ID_RE = re.compile(r"\A" + _ID_PAT + r"\Z")


def _reject_bad_id(cap_id):  # implements: ARCH-NEW-004  # implements: REQ-NEW-881
    """Print why `cap_id` cannot be a requirement id and return True, or return False.

    The id is not decoration: it is the string a `# implements:` tag has to spell, and
    `TAG_RE` only ever matches `_ID_PAT`. Scaffolding `my req.md` therefore minted a
    requirement no tag could ever name — a permanent RM006 error with no legal fix but
    deleting the file — and a `../` or `A/B` id wrote outside the requirements
    directory entirely. Both are refused at the door instead."""
    if _REQ_ID_RE.match(cap_id or ""):
        return False
    print("invalid id {!r}: a requirement id is what a `# implements:` tag must spell — "
          "two or more UPPERCASE parts joined by '-' (AREA-NAME-NNN), letters and digits "
          "only. Nothing else can ever be tagged in code.".format(cap_id))
    return True


def _warn_number_collision(reqs_dir, cap_id):  # implements: ARCH-NEW-004
    """Advisory: another requirement in the same area already uses this NNN. Ids are
    unique by their full text, so nothing breaks — but ARCH-MAP-007 beside
    ARCH-VIEWER-007 is the kind of pair people talk past each other about."""
    parts = cap_id.split("-")
    if len(parts) < 3:
        return
    area, num = parts[0], parts[-1]
    try:
        names = sorted(os.listdir(reqs_dir))
    except OSError:
        return
    for fn in names:
        if not fn.endswith(".md") or fn.startswith("_"):
            continue
        other = fn[:-3]
        op = other.split("-")
        if other != cap_id and len(op) >= 3 and op[0] == area and op[-1] == num:
            print("WARN  {} already uses number {} in area {} — ids stay unique by their full "
                  "text, but a distinct NNN keeps the two from being confused.".format(other, num, area))


def cmd_new(reqs_dir, tmpl_path, cap_id):  # implements: ARCH-NEW-004  # implements: REQ-NEW-881  # implements: REQ-NEW-882
    """Scaffold one blank requirement from the template and return an exit code;
    refuses rather than overwriting a file that already exists."""
    if _reject_bad_id(cap_id):
        return 2
    dest = os.path.join(reqs_dir, cap_id + ".md")
    if os.path.exists(dest):
        print(f"exists: {dest}"); return 1
    t = None
    if tmpl_path:                      # an on-disk template, if supplied, wins
        try:
            with open(tmpl_path, encoding="utf-8") as f:
                t = f.read()
        except OSError:
            t = None
    if t is None:                      # otherwise use the built-in scaffold
        t = REQUIREMENT_TEMPLATE
    t = t.replace("AREA-NAME-NNN", cap_id)
    os.makedirs(reqs_dir, exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        f.write(t)
    print(f"created {dest}")
    _warn_number_collision(reqs_dir, cap_id)
    return 0


def cmd_promote_todo(reqs_dir, tmpl_path, name, cap_id, mark_done=False, root="."):  # implements: ARCH-PROMOTE-TODO-001  # implements: REQ-PROMOTE-TODO-897  # implements: REQ-PROMOTE-TODO-898  # implements: REQ-PROMOTE-TODO-899
    """Scaffold a requirement draft from an unfinished TODO.md item (matched by name),
    seeding title / layer / milestone from the item. Requires an explicit cap_id — the
    engine runs headless (CI, pre-commit hook), so there is no interactive prompt. With
    mark_done it flips the matched TODO line to [x]; otherwise TODO.md is never touched."""
    if not cap_id:
        print('usage: reqmap new --from-todo "<todo name>" --id AREA-NAME-NNN [--mark-done]'); return 2
    if _reject_bad_id(cap_id):
        return 2
    key = name.strip().casefold()
    open_todos = [t for t in _parse_todos(root) if not t["done"]]
    matches = [t for t in open_todos if t["name"].strip().casefold() == key]
    if not matches:
        avail = "; ".join(t["name"] for t in open_todos) or "(none)"
        print(f"no open TODO named {name!r}. Open items: {avail}"); return 1
    if len(matches) > 1:
        where = ", ".join(t["milestone"] for t in matches)
        print(f"ambiguous: {len(matches)} open TODOs named {name!r} (milestones {where}) — rename to disambiguate")
        return 1
    todo = matches[0]
    dest = os.path.join(reqs_dir, cap_id + ".md")
    if os.path.exists(dest):
        print(f"exists: {dest}"); return 1
    t = None
    if tmpl_path:
        try:
            with open(tmpl_path, encoding="utf-8") as f:
                t = f.read()
        except OSError:
            t = None
    if t is None:
        t = REQUIREMENT_TEMPLATE
    layer = todo["lane"] if todo["lane"] in VALID_LAYER else "feature"   # 'ops' is a TODO lane, not a layer
    t = t.replace("AREA-NAME-NNN", cap_id)
    t, _layer_n = re.subn(r"(?m)^layer:\s*feature\b", f"layer: {layer}", t, count=1)
    if _layer_n == 0:
        print(f"warning: template has no 'layer: feature' anchor; layer {layer!r} not recorded")
    # inject milestone at the template's anchor; if a custom template lacks it,
    # fall back to the frontmatter fence, else warn rather than silently drop it
    if "superseded_by:" in t:
        t = t.replace("superseded_by:", f"milestone: {todo['milestone']}\nsuperseded_by:", 1)
    elif t.startswith("---\n"):
        t = t.replace("---\n", f"---\nmilestone: {todo['milestone']}\n", 1)
    else:
        print(f"warning: template has no frontmatter anchor; milestone {todo['milestone']} not recorded")
    if "# Short name" in t:
        t = t.replace("# Short name", "# " + todo["name"], 1)
    else:
        print(f"warning: template has no '# Short name' title anchor; TODO title {todo['name']!r} not inserted")
    os.makedirs(reqs_dir, exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        f.write(t)
    print(f"created {dest} (draft, milestone {todo['milestone']}, layer {layer}) from TODO {todo['name']!r}")
    _warn_number_collision(reqs_dir, cap_id)
    if mark_done:
        n = _mark_todo_done(root, todo["name"])
        print(f"marked TODO {todo['name']!r} done in TODO.md" if n
              else "warning: could not mark the TODO done (TODO.md not writable or line not found)")
    return 0


def _mark_todo_done(root, name):  # implements: ARCH-PROMOTE-TODO-001  # implements: REQ-PROMOTE-TODO-899
    """Flip the first unfinished TODO.md line whose name matches to [x]. Best-effort:
    returns 1 if a line was rewritten, 0 if TODO.md is absent/unwritable or no line matched."""
    key = name.strip().casefold()
    for base in dict.fromkeys([root, os.path.dirname(os.path.abspath(root))]):
        path = os.path.join(base, "TODO.md")
        if not os.path.exists(path):
            continue
        try:
            with open(path, encoding="utf-8", newline="") as f:
                lines = f.readlines()
        except OSError:
            continue          # unreadable here -> try the next candidate (parent), like _parse_todos
        changed = 0
        for i, line in enumerate(lines):
            m = re.match(r"^(\s*-\s+\[)[ ](\]\s+)(.+?)(\r?\n?)$", line)
            # rsplit on the LAST '|' to mirror _parse_todos_from_text's name
            # derivation — else a TODO whose name contains a '|' never matches
            if m and m.group(3).rsplit("|", 1)[0].strip().casefold() == key:
                lines[i] = m.group(1) + "x" + m.group(2) + m.group(3) + m.group(4)
                changed = 1
                break
        if changed:
            try:
                with open(path, "w", encoding="utf-8", newline="") as f:
                    f.writelines(lines)
            except OSError:
                return 0
        return changed
    return 0


def _set_frontmatter_status(text, value):  # implements: ARCH-PROMOTE-011  # implements: REQ-PROMOTE-894
    """Replace the value of the first `status:` line inside the leading frontmatter
    block, preserving its indentation and any trailing inline comment. Returns
    (new_text, n_replaced); n=0 when there is no frontmatter or no status line."""
    body = text.lstrip("﻿")            # drop a BOM if present (rewritten without it)
    if not body.startswith("---"):
        return text, 0
    end = body.find("\n---", 3)
    if end == -1:
        return text, 0
    head, rest = body[:end], body[end:]     # only the frontmatter block, never the body
    # Replace only the VALUE, keeping any trailing inline comment (and its spacing).
    # The value group excludes '#' so a blank `status:  # hint` line is filled in
    # place instead of swallowing the '#' as the value (which glued the leftover
    # comment text onto the status, corrupting the YAML).
    def _repl(m):
        comment = m.group(3)
        if comment:
            return m.group(1) + " " + value + (m.group(2) or "  ") + comment
        return m.group(1) + " " + value
    new_head, n = re.subn(
        r"(?m)^([ \t]*status[ \t]*:)[ \t]*[^#\r\n]*?([ \t]*)(#[^\r\n]*)?$",
        _repl, head, count=1)
    return new_head + rest, n


def _write_frontmatter_status(r, new_status):  # implements: ARCH-PROMOTE-011
    """Set one requirement's `status:` in its own file, in place. Returns True on a
    write, False when the block has no `status:` line to change.

    newline="" on both ends: read/write the file's own line endings verbatim so a
    CRLF-committed requirement file isn't silently flipped to LF on a POSIX host
    (universal-newline translation on read + os.linesep on write would do exactly
    that). Per-line EOL, so a file with MIXED line endings keeps every untouched
    bare-LF line bare-LF — only the substituted VALUE changes."""
    with open(r["path"], encoding="utf-8-sig", newline="") as f:
        raw = f.read()
    orig_lines = raw.splitlines(keepends=True)
    line_eols = [ln[len(ln.rstrip("\r\n")):] for ln in orig_lines]
    eol = "\r\n" if "\r\n" in raw else "\n"
    text = raw.replace("\r\n", "\n") if eol == "\r\n" else raw
    # A module file holds several requirements; flip the status of THIS one, not of
    # the first block in the file.  # implements: ARCH-MODULEFILE-056
    blocks = split_requirement_blocks(text)
    if len(blocks) > 1:
        idx = r.get("block", 0)
        blocks[idx], n = _set_frontmatter_status(blocks[idx], new_status)
        new_text = "".join(blocks)
    else:
        new_text, n = _set_frontmatter_status(text, new_status)
    if n == 0:
        return False
    new_lines = new_text.splitlines()
    if len(new_lines) == len(line_eols):
        new_text = "".join(nl + le for nl, le in zip(new_lines, line_eols))
    elif eol == "\r\n":
        new_text = new_text.replace("\n", "\r\n")
    with open(r["path"], "w", encoding="utf-8", newline="") as f:
        f.write(new_text)
    return True


def _draft_id(rel):  # implements: ARCH-EXTRACT-008  # implements: REQ-EXTRACT-850
    """Mint a draft capability id from a file's relative path. Path-aware so
    same-basename files in different dirs don't collide; falls back to FILE when
    the name has no usable A-Z0-9 token (e.g. `_.py`, non-ASCII stems)."""
    slug = re.sub(r"[^A-Z0-9]+", "-", os.path.splitext(rel)[0].upper()).strip("-")
    return "DRAFT-" + (slug or "FILE")


def classify_prose(rel):  # implements: ARCH-PROSE-024  # implements: REQ-PROSE-900
    """Bucket a POSIX-relative .md/.html path for the auto-draft path. Returns
    'ignore' (meta/boilerplate, invisible), 'sync_only' (README/docs/*.html — never
    drafted, but a drift- and semantic-checked member when explicitly tagged), or
    'capability' (prompt/spec prose — auto-drafted as a `draft` stub). Governs AUTO
    behavior only: scan_members still honors an explicit tag on any file."""
    base = os.path.basename(rel)
    # Bucket 1 — meta/boilerplate.
    if base in META_IGNORE_NAMES:
        return "ignore"
    if base == "LICENSE" or base.startswith("LICENSE."):
        return "ignore"
    if base.startswith("_"):                      # generated _map.*, _findings.md
        return "ignore"
    # Bucket 2 — sync-only.
    if base.upper() == "README" or base.upper().startswith("README."):   # readme.md is a README too
        return "sync_only"
    if rel == "docs" or rel.startswith("docs/"):
        return "sync_only"
    if rel.endswith(".html"):                      # all HTML is an overview/derived doc
        return "sync_only"
    # Bucket 3 — capability source (prompts/specs/modes and other prose .md).
    return "capability"


def _prose_facts(src):  # implements: ARCH-PROSE-024  # implements: REQ-PROSE-901
    """(title, [headings]) from markdown/HTML prose, for a draft scaffold.
    Title: markdown frontmatter `title:`, else first `# ` H1, else <title>/<h1>.
    Headings: markdown `## ` H2 lines, else <h2>. Returns (None, []) when absent.
    The scaffold lists headings as an authoring hint — never the contract."""
    meta, body = parse_frontmatter(src)
    title = meta.get("title") or None
    headings, h1_sections = [], []
    for line in body.splitlines():
        s = line.strip()
        if title is None:
            m = re.match(r"#\s+(.+)", s)                      # markdown H1
            if m:
                title = m.group(1).strip()
                continue
            m = re.search(r"<(?:title|h1)[^>]*>(.*?)</(?:title|h1)>", s, re.I)
            if m:
                title = re.sub(r"<[^>]+>", "", m.group(1)).strip()
                # no continue: a line may carry both <title> and <h2> (see test_html_title_and_h2)
        m = re.match(r"##\s+(.+)", s)                         # markdown H2 (not H3)
        if m:
            headings.append(m.group(1).strip())
            continue
        m = re.match(r"#\s+(.+)", s)                          # a further H1: flat, single-level prose
        if m:
            h1_sections.append(m.group(1).strip())
            continue
        for inner in re.findall(r"<h2[^>]*>(.*?)</h2>", s, re.I):  # html H2
            headings.append(re.sub(r"<[^>]+>", "", inner).strip())
    # A prompt corpus (fabric: 255 files) writes every section as `# `: with no H2 at
    # all, the later H1s ARE the sections, and the hint would otherwise be empty.
    return title, (headings or h1_sections)


SYS_PLACEHOLDER_ID = "SYS-NEEDS-A-NAME-001"   # implements: ARCH-EXTRACT-008  # implements: REQ-EXTRACT-981


def _arch_id_for(rel_dir):  # implements: ARCH-EXTRACT-008  # implements: REQ-EXTRACT-981
    """The architecture id proposed for a source directory.

    The directory is the only structural signal a per-file draft has, and it is a weak
    one: on this repo it would name capabilities `scripts` and `app/src/lib`, which are
    not capabilities. That is why the node it produces is a `draft` carrying
    `level_source: auto` — a proposal to rename, not a claim."""
    parts = [p for p in rel_dir.replace(os.sep, "/").split("/") if p not in ("", ".")]
    stem = "-".join(parts[-2:]) if parts else "ROOT"
    slug = re.sub(r"[^A-Za-z0-9]+", "-", stem).strip("-").upper() or "ROOT"
    return "ARCH-{}-001".format(slug)


def _write_sys_placeholder(reqs_dir, arch_ids):  # implements: ARCH-EXTRACT-008  # implements: REQ-EXTRACT-981
    """The apex, written as an explicit hole.

    A stakeholder need is not in the source — nothing in a repository says why a user
    wants the thing — so the engine refuses to guess one and mints a node whose title
    says so. Skipped when the corpus already has a `layer: need`."""
    dest = os.path.join(reqs_dir, SYS_PLACEHOLDER_ID + ".md")
    if os.path.exists(dest) or not arch_ids:
        return 0
    with open(dest, "w", encoding="utf-8") as f:
        f.write("---\nid: {}\nstatus: draft\nlevel: system\nlayer: need\n"
                "owner: auto\nlevel_source: auto\n---\n\n"
                "# NAME THIS NEED\n\n"
                "> The engine cannot read a stakeholder need out of source code, so it "
                "left this hole rather than invent one. Replace the title and the clause "
                "below with the outcome a user actually wants, then rename the file and "
                "the id. Every architecture draft points here until you do.\n\n"
                "## Description\n"
                "Every bullet below is binding.\n"
                "- TODO: the outcome a user wants, in their words, not the system's.\n\n"
                "## Cases\n"
                "CASE-1\n"
                "  Given  TODO\n"
                "  When   TODO\n"
                "  Then   TODO\n".format(SYS_PLACEHOLDER_ID))
    return 1


def _write_arch_drafts(reqs_dir, by_dir):  # implements: ARCH-EXTRACT-008  # implements: REQ-EXTRACT-981
    """One architecture draft per source directory that produced code drafts.

    Returns the ids written, newest-corpus-first order irrelevant. Each is a proposal:
    `status: draft`, `owner: auto`, `level_source: auto`, and a title that names the
    directory rather than pretending to name a capability."""
    written = []
    for rel_dir in sorted(by_dir):
        aid = _arch_id_for(rel_dir)
        dest = os.path.join(reqs_dir, aid + ".md")
        if os.path.exists(dest):
            written.append(aid)
            continue
        kids = sorted(by_dir[rel_dir])
        with open(dest, "w", encoding="utf-8") as f:
            f.write("---\nid: {aid}\nstatus: draft\nlevel: architecture\n"
                    "layer: feature\nowner: auto\nlevel_source: auto\n"
                    "satisfies: [{sys}]\n---\n\n"
                    "# {label}\n\n"
                    "> PROPOSED grouping, not a capability. The engine had one structural "
                    "signal — the directory `{rel_dir}` — and a directory is not a "
                    "capability. Rename this to the thing these {n} behaviour group(s) "
                    "together let a user do, merge it with a sibling, or delete it and "
                    "re-point its children.\n\n"
                    "## Description\n"
                    "Every bullet below is binding.\n"
                    "{bullets}\n\n"
                    "## Cases\n"
                    "CASE-1\n"
                    "  Given  TODO\n"
                    "  When   TODO\n"
                    "  Then   TODO\n".format(
                        aid=aid, sys=SYS_PLACEHOLDER_ID, label=rel_dir or "root",
                        rel_dir=rel_dir or ".", n=len(kids),
                        bullets="\n".join(
                            "- TODO: one obligation this capability owes. [[{}]]".format(k)
                            for k in kids)))
        written.append(aid)
    return written


def cmd_extract(ws):  # implements: ARCH-EXTRACT-008  # implements: ARCH-PROSE-024  # implements: REQ-EXTRACT-849  # implements: REQ-EXTRACT-850
    """Propose DRAFT requirements for code files that have no member tag yet."""
    members, reqs_dir, code_root = ws.members, ws.reqs_dir, ws.code_root
    tagged = {fp for hits in members.values() for (_, fp, _) in hits}
    proposed, used = 0, set()
    by_dir = {}          # rel dir -> [code-level draft ids], for the ARCH rung
    os.makedirs(reqs_dir, exist_ok=True)
    for fp, rel in _walk_files(code_root, reqs_dir,
                               lambda fn, _r: _is_code_file(fn) or fn.endswith(PROSE_EXTS)):
        dirpath, fn = os.path.dirname(fp), os.path.basename(fp)
        is_prose = fn.endswith(PROSE_EXTS)
        if rel in tagged:
            continue
        if is_prose and classify_prose(rel) != "capability":
            continue                           # bucket 1/2 -> never auto-drafted
        cap = base = _draft_id(rel)
        k = 2
        while cap in used:                 # residual collision (case/ext only)
            cap = "{}-{}".format(base, k); k += 1
        used.add(cap)
        dest = os.path.join(reqs_dir, cap + ".md")
        if os.path.exists(dest):
            continue
        with open(os.path.join(dirpath, fn), encoding="utf-8", errors="ignore") as f:
            src = f.read()
        if is_prose:
            title, headings = _prose_facts(src)
            review = "REVIEW"   # intent is unrecoverable from prose — always author
            hint = "\n".join("  - {}".format(h) for h in headings) \
                or "  - (no section headings detected)"
            # str.format (not f-string): the template embeds literal {cap}/{rel} inside backticked instructions
            with open(dest, "w", encoding="utf-8") as f:
                f.write("---\nid: {cap}\nstatus: draft\nlayer: feature\n"
                        "owner: auto\ndepends_on: []\n"
                        "risk: 2  # REVIEW — prose capability, author the contract "
                        "before promoting\n---\n\n"
                        "# {title}\n\n"
                        "> DRAFT extracted from {rel} (prose capability). The source "
                        "prose is NOT the contract — author the normative behavior "
                        "below, then tag the source `# generated-from: {cap}` "
                        "(HTML: `<!-- generated-from: {cap} -->`) and promote.\n\n"
                        "## Description\n"
                        "Every bullet below is binding.\n"
                        "<!-- Name the subject, write in present tense, one statement per "
                        "bullet, at most 3 sentences and 150 words. -->\n"
                        "- TODO: the capability this prose defines (author from "
                        "intent, do not copy the prose).\n\n"
                        "## Verify intent (open questions for the human)\n"
                        "- TODO: which source sections are normative vs illustrative?\n\n"
                        "## Cases (= tests)\n"
                        "- TODO: Given/When/Then checks for the contract above.\n\n"
                        # the hint belongs in Context: bullets under Verify intent
                        # are read back as open questions by `findings`
                        "## Context (non-binding)\n**Current implementation**\n- {rel}\n\n"
                        "**Source sections detected (authoring hint, not the contract)**\n"
                        "{hint}\n".format(
                            cap=cap, title=(title or os.path.splitext(fn)[0]),
                            rel=rel, hint=hint))
        else:
            risk = _risk(src)
            review = "REVIEW" if risk >= 2 else "auto-baseline"
            surface = _observed_surface(_file_facts(os.path.join(dirpath, fn), rel))
            with open(dest, "w", encoding="utf-8") as f:
                # emission schema matches REQUIREMENT_TEMPLATE so a promoted draft
                # needs no reshaping
                f.write(f"---\nid: {cap}\nstatus: draft\nlevel: code\n"
                        f"layer: feature\nowner: auto\nlevel_source: auto\n"
                        f"satisfies: [{_arch_id_for(os.path.relpath(dirpath, code_root))}]\n"
                        f"depends_on: []\n"
                        f"risk: {risk}  # {review} — author triage hint, not read by the engine\n---\n\n"
                        f"# {os.path.splitext(fn)[0]}\n\n"
                        f"> DRAFT extracted from {rel}. Describes observed behavior, "
                        f"not validated intent.\n\n"
                        f"## Description\n"
                        f"Every bullet below is binding.\n"
                        f"<!-- Name the subject, write in present tense, one statement per "
                        f"bullet, at most 3 sentences and 150 words. -->\n"
                        f"- TODO: the observed behavior (characterization — correctness UNVERIFIED).\n\n"
                        f"## Verify intent (open questions for the human)\n"
                        f"- TODO: anything that looks like an accident (swallowed error, magic "
                        f"constant, dead branch) — intended, or a bug to fix?\n\n"
                        f"## Cases (= tests)\n"
                        f"- characterization: current behavior captured, correctness UNVERIFIED\n\n"
                        f"## Context (non-binding)\n**Current implementation**\n- {rel}\n{surface}")
        proposed += 1
        if not is_prose:   # a file that passed the filter is one or the other
            rel_dir = os.path.relpath(dirpath, code_root).replace(os.sep, "/")
            by_dir.setdefault(rel_dir, []).append(cap)
        print(f"{review:14} {cap}  <- {rel}")
    # The two rungs above the code level. Written last, so they know their children.
    arch_ids = _write_arch_drafts(reqs_dir, by_dir)
    n_sys = _write_sys_placeholder(reqs_dir, arch_ids)
    if arch_ids:
        print(f"\n{len(arch_ids)} architecture draft(s) proposed from directory names, and "
              f"{n_sys} system placeholder. Both carry `level_source: auto` — the engine "
              f"invented them and a directory is not a capability. Rename, merge or delete "
              f"them; the code level below is the only rung it can assert.")
    print(f"\n{proposed} draft requirements proposed. Review the REVIEW ones before promoting.")
    return 0


def _observed_surface(facts, limit=12):  # implements: ARCH-EXTRACT-008
    """Authoring hint for a code draft's Context/Current-implementation group: the
    module docstring's first line and the top-level signatures `plan` already knows
    how to read. Empty string when the language has no parser. Non-binding by
    construction — it lives under Context, never in the Contract, so a promoted
    draft still needs an authored contract."""
    sigs = list(facts.get("signatures") or [])
    doc = (facts.get("docstrings") or {}).get("module")
    if not sigs and not doc:
        return ""
    lines = ["", "Observed surface (auto, non-binding — an authoring hint, not the contract):"]
    if doc:
        lines.append("- module: {}".format(doc))
    lines += ["- `{}`".format(s) for s in sigs[:limit]]
    if len(sigs) > limit:
        lines.append("- … {} more".format(len(sigs) - limit))
    return "\n".join(lines) + "\n"


def _risk(src):  # implements: ARCH-EXTRACT-008  # implements: REQ-EXTRACT-851
    score = 0
    if re.search(r"\b(TODO|FIXME|HACK|XXX)\b", src): score += 1
    if "# noqa" in src or "eslint-disable" in src: score += 1
    if len(src.splitlines()) > 300: score += 1
    return score


# ---------- candidates (capability extraction plan) ----------
# Stage 1 of AI extraction: gather the raw material an authoring step (a human or
# an LLM agent) needs to write a real, capability-level requirement. READ-ONLY —
# emits a JSON plan, writes NO .md, so it cannot repeat extract's empty-stub failure.
# Languages `plan` can read FACTS from (docstrings, signatures). Every scannable code
# file is a candidate regardless — three evidence runs (zlib: 0 candidates for 94 C
# files, gin: none for 99 Go files, awesome-compose: none for 35 Dockerfiles) showed
# a plan that silently omitted most of what `draft` then produced.
CANDIDATE_EXTS = (".py", ".js", ".ts", ".tsx", ".jsx", ".mjs", ".cjs", ".mts", ".cts")
_TEST_DIR_NAMES = {"test", "tests", "spec", "specs", "__tests__", "testing", "e2e"}
_TEST_FILE_SUFFIXES = ("_test.py", "_test.go", "_test.rs", "_spec.rb", ".test.ts", ".test.tsx",
                       ".test.js", ".test.jsx", ".spec.ts", ".spec.tsx", ".spec.js", ".e2e.ts")


def _is_test_path(rel):  # implements: ARCH-CANDIDATES-009  # implements: REQ-CANDIDATES-827
    """Test code by convention (a `tests/` segment, `test_*.py`, `*_test.go`, `*.spec.ts`)."""
    parts = rel.replace(os.sep, "/").split("/")
    base = parts[-1]
    return (any(p in _TEST_DIR_NAMES for p in parts[:-1])
            or base.startswith("test_") or base.endswith(_TEST_FILE_SUFFIXES))
BUS_FANIN_THRESHOLD = 5      # a module this many capabilities depend on is bus-like
SPLIT_LOC_THRESHOLD = 300    # oversize file -> flag for human split, do not auto-split


def _py_facts(src):  # implements: ARCH-CANDIDATES-009  # implements: REQ-CANDIDATES-826
    """Module/symbol docstrings, top-level signatures and import targets via the
    stdlib `ast`. A SyntaxError/ValueError yields empty facts so one unparseable
    file (incl. a source with an embedded NUL byte, which ast.parse rejects with
    ValueError, not SyntaxError) never aborts the whole plan."""
    facts = {"signatures": [], "docstrings": {}, "imports": []}
    try:
        tree = ast.parse(src)
    except (SyntaxError, ValueError):
        return facts
    mod_doc = ast.get_docstring(tree)
    if mod_doc and mod_doc.strip():
        facts["docstrings"]["module"] = mod_doc.strip().splitlines()[0][:200]
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            facts["signatures"].append("def {}({})".format(
                node.name, ", ".join(a.arg for a in node.args.args)))
        elif isinstance(node, ast.ClassDef):
            facts["signatures"].append("class {}".format(node.name))
            # the public surface of a class-based module IS its methods (httpx's
            # _client.py hid 78 of them behind 3 module-level helpers)
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and not sub.name.startswith("_"):
                    facts["signatures"].append("def {}.{}({})".format(
                        node.name, sub.name, ", ".join(a.arg for a in sub.args.args if a.arg != "self")))
        else:
            continue
        d = ast.get_docstring(node)
        if d and d.strip():
            facts["docstrings"][node.name] = d.strip().splitlines()[0][:200]
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                imports.add(n.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imports.add(node.module.split(".")[0])
    facts["imports"] = sorted(imports)
    return facts


def _js_facts(src):  # implements: ARCH-CANDIDATES-009  # implements: REQ-CANDIDATES-826
    """Best-effort JS/TS facts via regex (no stdlib JS parser): the leading block
    comment as the module doc, and top-level function/binding names. Imports are
    not resolved for JS in v1 (the agent and _capmap.json fill that gap)."""
    facts = {"signatures": [], "docstrings": {}, "imports": []}
    # Leading block comment via plain string scan over a capped prefix — NOT a regex.
    # The old `/\*+(.*?)\*/` backtracks O(n^2) on a file opening with a long run of
    # `*` (a DoS on `candidates`); str.find is linear and cannot backtrack. The
    # leading `*`s of `/***` are stripped by the per-line `.strip(" *")` below.
    head_src = src[:8000].lstrip()
    if head_src.startswith("/*"):
        close = head_src.find("*/", 2)
        if close != -1:
            head = [ln.strip(" *") for ln in head_src[2:close].strip().splitlines()
                    if ln.strip(" *")]
            if head:
                facts["docstrings"]["module"] = head[0][:200]
    names = re.findall(r"(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)", src)
    names += re.findall(r"(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=", src)
    facts["signatures"] = list(dict.fromkeys(names))   # dedupe, keep order
    return facts


def _md_facts(src):  # implements: ARCH-CANDIDATES-009
    """Best-effort capability facts from a Markdown prompt/spec file (no parser):
    the first H1 (`# `) is the title, the first blockquote (`>`) AFTER that H1 is the
    intent, and each `## ` H2 heading is a structural-signature line. Free prose is
    never hashed — these facts only seed a human-authored requirement (Stage 2); the
    binding hash anchors on the authored Contract+Acceptance, like any code requirement."""
    facts = {"signatures": [], "docstrings": {}, "imports": []}
    title, intent, after_h1 = None, None, False
    for line in src.splitlines():
        s = line.strip()
        if title is None and s.startswith("# "):
            title = s[2:].strip(); after_h1 = True; continue
        if after_h1 and intent is None and s.startswith(">"):
            intent = s.lstrip(">").strip()
        if s.startswith("## "):
            facts["signatures"].append("## " + s[3:].strip())
    if title:
        facts["docstrings"]["title"] = title[:200]
    if intent:
        facts["docstrings"]["module"] = intent[:200]
    return facts


def _file_facts(path, rel):  # implements: ARCH-CANDIDATES-009  # implements: REQ-CANDIDATES-826
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            src = f.read()
    except OSError:
        return {"signatures": [], "docstrings": {}, "imports": [], "loc": 0}
    if rel.endswith(".py"):
        facts = _py_facts(src)
    elif rel.endswith(".md"):
        facts = _md_facts(src)
    elif rel.endswith(CANDIDATE_EXTS):
        facts = _js_facts(src)
    else:   # a candidate the engine has no parser for: still listed, facts empty
        facts = {"signatures": [], "docstrings": {}, "imports": []}
    facts["loc"] = len(src.splitlines())
    facts["signatures"] = facts["signatures"][:40]
    return facts


def _load_capmap(reqs_dir):  # implements: ARCH-CANDIDATES-009  # implements: REQ-CANDIDATES-827
    """Optional `requirements/_capmap.json`: a hand-authored capability grouping,
    authoritative when present. Shape: {"capabilities": [{id, layer, files:[...]}]}
    (a bare list is also accepted). Returns []; fail-open on absent/unreadable."""
    try:
        with open(os.path.join(reqs_dir, "_capmap.json"), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    caps = data.get("capabilities", []) if isinstance(data, dict) else data
    out = []
    if isinstance(caps, list):
        for c in caps:
            if isinstance(c, dict) and c.get("id") and c.get("files"):
                out.append({"id": c["id"], "layer": c.get("layer"),
                            "files": [f.replace(os.sep, "/") for f in _as_list(c["files"])]})
    return out


def _mint_cap_id(rel):  # implements: ARCH-CANDIDATES-009  # implements: REQ-CANDIDATES-827
    """A TAG_RE-valid suggested id from a path stem (Stage 2 may rename it)."""
    slug = re.sub(r"[^A-Z0-9]+", "-", os.path.splitext(rel)[0].upper()).strip("-")
    return (slug or "MOD") + "-001"


def _collect_files(code_root, reqs_dir, md_globs=None):  # implements: ARCH-CANDIDATES-009  # implements: REQ-CANDIDATES-826
    """Sorted rel paths of candidate source files, honoring _prune_dirs (noise +
    the SSOT dir) and .reqmapignore — the same exclusions scan_members uses.

    `md_globs` is the opt-in, scope-bounding allowlist for non-code discovery: a
    `.md` file is included ONLY when it matches one of these globs (and is not
    ignored). Empty/None -> no `.md` is ever collected (behavior unchanged). The
    presence of a glob IS the opt-in; there is no separate on/off flag."""
    md_globs = md_globs or []
    out = []
    for fp, rel in _walk_files(code_root, reqs_dir):
        fn = os.path.basename(fp)
        if _is_code_file(fn) and not fn.endswith(PROSE_EXTS):
            out.append(rel)
        elif fn.endswith(".md") and any(fnmatch.fnmatch(rel, g) for g in md_globs):
            out.append(rel)
    return out


def cmd_candidates(ws, out, md_globs=None):  # implements: ARCH-CANDIDATES-009  # implements: REQ-CANDIDATES-826
    """Emit a deterministic JSON capability-extraction plan and write NO .md.
    Grouping: authoritative `requirements/_capmap.json` when present, else one
    candidate per file (the Stage-2 agent merges/splits using judgment).
    `md_globs` opts non-code `.md` files (prompts, specs) into discovery — advisory
    only, never auto-written; a human authors + confirms each into the SSOT."""
    reqs, members, reqs_dir, code_root = ws.reqs, ws.members, ws.reqs_dir, ws.code_root
    files = _collect_files(code_root, reqs_dir, md_globs)
    facts_by_file = {rel: _file_facts(os.path.join(code_root, rel), rel) for rel in files}

    tagged = {}   # file -> already-implemented requirement id (idempotency hint)
    for cap, hits in members.items():
        for role, fp, _ln in hits:
            if role == "implements":
                tagged.setdefault(fp, cap)

    # depends_on is resolved by matching an import name to a file STEM. Known
    # limitation (Stage-1 heuristic): an import that shadows a stdlib/3rd-party name
    # (e.g. `import json` next to a local json.py) or collides with a same-basename
    # file in another dir can yield a false edge — the Stage-2 author prunes these.
    stem_of = {os.path.splitext(os.path.basename(r))[0]: r for r in files}  # for depends_on

    # ----- grouping: _capmap.json wins; uncovered files fall back to one-per-file
    groups, claimed = [], set()
    for entry in _load_capmap(reqs_dir):
        present = [f for f in entry["files"] if f in facts_by_file]
        if present:
            groups.append({"id": entry["id"], "layer": entry.get("layer"), "files": present})
            claimed.update(present)
    # de-duplicate minted ids: two files sharing a slug (foo.py + foo.js, or
    # foo-bar + foo_bar) would otherwise mint the same id and conflate two
    # distinct candidates downstream — bump the numeric suffix on collision.
    # Seed from capmap groups AND existing requirement ids so a minted id never
    # duplicates a real requirement either.
    used_ids = {g["id"] for g in groups} | set(reqs)
    for rel in files:
        if rel in claimed:
            continue
        cid = _mint_cap_id(rel)
        if cid in used_ids:
            stem = cid[:-3]                 # _mint_cap_id always ends in "-001"
            n = 2
            while "{}{:03d}".format(stem, n) in used_ids:
                n += 1
            cid = "{}{:03d}".format(stem, n)
        used_ids.add(cid)
        groups.append({"id": cid, "layer": None, "files": [rel]})

    group_id_of_file = {f: g["id"] for g in groups for f in g["files"]}

    # Precompute once: which test_ files exist per stem, so the per-group tested_by
    # lookup below is O(1) per stem instead of rescanning the whole `files` list
    # once per group (O(groups * files)).
    test_by_stem = {}
    for r in files:
        b = os.path.basename(r)
        if b.startswith("test_"):
            test_by_stem.setdefault(os.path.splitext(b)[0][len("test_"):], []).append(r)

    cands = []
    for g in groups:
        sigs, docs, imps, loc = [], {}, set(), 0
        my_stems = set()
        for f in g["files"]:
            ff = facts_by_file[f]
            sigs += ["{}: {}".format(f, s) for s in ff["signatures"]]
            for k, v in ff["docstrings"].items():
                docs["{}:{}".format(f, k)] = v
            imps.update(ff["imports"])
            loc += ff.get("loc", 0)
            my_stems.add(os.path.splitext(os.path.basename(f))[0])
        own = set(g["files"])
        deps = sorted({group_id_of_file[stem_of[m]] for m in imps
                       if m in stem_of and stem_of[m] not in own})
        tested_by = sorted(t for stem in my_stems for t in test_by_stem.get(stem, ()))
        existing = next((tagged[f] for f in g["files"] if f in tagged), None)
        cands.append({  # implements: REQ-CANDIDATES-827
            "suggested_id": g["id"], "_layer": g["layer"], "files": g["files"],
            "docstrings": docs, "signatures": sigs[:60], "imports": sorted(imps),
            "depends_on": deps, "tested_by": tested_by, "loc": loc,
            "existing_req": existing, "split_candidate": loc > SPLIT_LOC_THRESHOLD,
            "is_test": bool(g["files"]) and all(_is_test_path(f) for f in g["files"]),
        })

    fanin = {}
    for c in cands:
        for d in c["depends_on"]:
            fanin[d] = fanin.get(d, 0) + 1
    for c in cands:
        n = fanin.get(c["suggested_id"], 0)
        c["importer_count"] = n
        c["suggested_layer"] = c.pop("_layer") or ("bus" if n >= BUS_FANIN_THRESHOLD else "feature")  # implements: REQ-CANDIDATES-827

    authored = sum(1 for c in cands if c["existing_req"])
    plan = {
        "engine_version": MAP_ENGINE_VERSION,
        # surfaces the unfilled-plan gap so an advisory plan nobody authored cannot
        # masquerade as coverage (with_existing_req = candidates already tagged in code)
        "coverage_summary": {"total_candidates": len(cands), "with_existing_req": authored},
        "lineage_note": ("A generated-from/implements tag records authoring lineage only; it "
                         "does NOT mean the requirement auto-tracks later edits to the source "
                         "file. Re-touch the requirement's Contract+Acceptance when the source's "
                         "behavior changes."),
        "bus": sorted(c["suggested_id"] for c in cands if c["suggested_layer"] == "bus"),
        "candidates": cands,
    }
    text = json.dumps(plan, indent=2, ensure_ascii=False)
    if out and out != "-":
        with open(out, "w", encoding="utf-8") as f:
            f.write(text)
        print("wrote {} ({} candidates)".format(out, len(cands)))
    else:
        print(text)
    return 0


# ---------- findings (open verify-intent items) ----------
FINDINGS_SIDECAR = "_findings_triage.json"
_SEV_RANK = {"high": 0, "medium": 1, "low": 2, "none": 3, "": 4}
_SEV_BADGE = {"high": "HIGH", "medium": "MEDIUM", "low": "LOW"}


def _req_title(body, rid):
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return rid


def collect_findings(reqs):  # implements: ARCH-FINDINGS-010  # implements: REQ-FINDINGS-853
    """Per requirement, the open '## WHAT — Verify intent' bullets minus the
    'None - ...' placeholder. Returns [(rid, title, [item, ...]), ...] for reqs
    that have >=1 real finding, in id order. Deterministic; reads only the md."""
    out = []
    for rid in sorted(reqs):
        body = reqs[rid]["body"]
        items = [b for b in _verify_bullets(body)
                 if b and not b.lstrip("*_ ").lower().startswith("none")]
        if items:
            out.append((rid, _req_title(body, rid), items))
    return out


def _render_findings_raw(groups, total):  # implements: REQ-FINDINGS-854
    L = ["# Open findings", "",
         "> {} open verify-intent item(s) across {} requirement(s), aggregated from each "
         "requirement's `## WHAT — Verify intent` section by `reqmap.py sync`."
         .format(total, len(groups)),
         ">",
         "> These are open questions raised while reconstructing intent from code - NOT "
         "confirmed bugs. Resolve each by fixing the code or promoting the behavior into a "
         "Contract line. Run the AI triage pass (see SKILL.md) and drop a `{}` beside this "
         "file for a verified, prioritized view.".format(FINDINGS_SIDECAR),
         "", "---", ""]
    if not groups:
        L.append("_No open findings._")
        return "\n".join(L) + "\n", 0, 0
    for rid, title, items in groups:
        L.append("## {} - {}  ({})".format(rid, title, len(items)))
        L.append("")
        for it in items:
            L.append("- {}".format(it))
        L.append("")
    return "\n".join(L) + "\n", 0, 0


def _render_findings_triaged(triage, raw_total):  # implements: REQ-FINDINGS-855
    items = [it for it in triage.get("items", []) if isinstance(it, dict)]
    buckets = {"REAL_BUG": [], "USER_DECISION": [], "INTENTIONAL": [], "FALSE_POSITIVE": []}
    for it in items:
        # an unknown/typo'd/missing classification folds into USER_DECISION rather
        # than landing in an orphan bucket that no block renders (silent loss). The
        # AI triage sidecar is LLM-authored, so an off-enum value is realistic.
        cls = it.get("classification")
        buckets[cls if cls in buckets else "USER_DECISION"].append(it)
    bugs = sorted(buckets.get("REAL_BUG", []),
                  key=lambda x: _SEV_RANK.get((x.get("severity") or "").lower(), 9))
    n = len(items)
    L = ["# Open findings - triaged", "",
         "> {} finding(s) classified: {} confirmed bug(s), {} product/config decision(s), "
         "{} intentional, {} false-positive. Source: `{}`{}."
         .format(n, len(bugs), len(buckets.get("USER_DECISION", [])),
                 len(buckets.get("INTENTIONAL", [])), len(buckets.get("FALSE_POSITIVE", [])),
                 FINDINGS_SIDECAR,
                 " (generated {})".format(triage["generated_at"]) if triage.get("generated_at") else "")]
    if raw_total and raw_total != n:
        L += [">", "> WARN  {} raw verify-intent item(s) currently in the requirements vs {} "
                   "triaged - re-run the AI triage pass to refresh.".format(raw_total, n)]
    L += ["", "---", ""]

    def block(title, rows, detail):
        L.append("## {} ({})".format(title, len(rows)))
        L.append("")
        for it in rows:
            rid = it.get("req_id", "?")
            sev = (it.get("severity") or "").lower()
            head = "**[{}] `{}`**".format(_SEV_BADGE[sev], rid) if (detail and sev in _SEV_BADGE) \
                else "**`{}`**".format(rid)
            L.append("- {} {}".format(head, it.get("finding", "")))
            if detail and it.get("location"):
                L.append("  - where: `{}`".format(it["location"]))
            if detail and it.get("fix"):
                L.append("  - fix: {}".format(it["fix"]))
        L.append("")

    if bugs:
        block("Confirmed bugs", bugs, True)
    if buckets.get("USER_DECISION"):
        block("Your call - config / product decisions", buckets["USER_DECISION"], True)
    if buckets.get("INTENTIONAL"):
        block("Intentional", buckets["INTENTIONAL"], False)
    if buckets.get("FALSE_POSITIVE"):
        block("False-positive", buckets["FALSE_POSITIVE"], False)
    return "\n".join(L) + "\n", n, len(bugs)


def _render_findings(reqs, reqs_dir, raw=False):  # implements: ARCH-FINDINGS-010
    """The `_findings.md` text and its counts, without writing anything. Shared by
    `findings` (which writes it) and `map --check` (which compares the committed
    copy against it). Returns (md, total, n_groups, used_triage, n_tri, n_bugs)."""
    groups = collect_findings(reqs)
    total = sum(len(items) for _rid, _t, items in groups)

    triage = None
    if not raw:
        sidecar = os.path.join(reqs_dir, FINDINGS_SIDECAR)
        if os.path.exists(sidecar):
            try:
                with open(sidecar, encoding="utf-8") as f:
                    triage = json.load(f)
            except (json.JSONDecodeError, OSError):
                triage = None

    if triage and isinstance(triage.get("items"), list):
        md, n_tri, n_bugs = _render_findings_triaged(triage, total)
        used_triage = True
    else:
        md, n_tri, n_bugs = _render_findings_raw(groups, total)
        used_triage = False
    return md, total, len(groups), used_triage, n_tri, n_bugs


def cmd_findings(reqs, reqs_dir, raw=False):  # implements: ARCH-FINDINGS-010  # implements: REQ-FINDINGS-854
    """Aggregate every requirement's open verify-intent items into
    requirements/_findings.md. If a `_findings_triage.json` sidecar exists (and
    --raw is off), render the verified, classified view from it instead; else the
    raw grouped list. Stdlib-only: the AI triage that produces the sidecar lives
    in the skill, not here (same split as candidates vs AI-authoring)."""
    md, total, n_groups, used_triage, n_tri, n_bugs = _render_findings(reqs, reqs_dir, raw)
    os.makedirs(reqs_dir, exist_ok=True)
    out = os.path.join(reqs_dir, "_findings.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write(md)
    # gate the suffix on the renderer actually used — a malformed sidecar that is
    # truthy but whose `items` is not a list falls back to raw, so don't claim a
    # triage view was rendered
    extra = ", {} triaged, {} confirmed bug(s)".format(n_tri, n_bugs) if used_triage else ""
    print("{} open finding(s) across {} requirement(s){} -> {}"
          .format(total, n_groups, extra, out))
    return 0


# ---------- map (HTML) ----------
def _attach_ac_coverage(node, body, covered):  # implements: ARCH-ACVERIFY-019  # implements: REQ-ACVERIFY-823
    """Add `clauses` / `covered` / `gap` to a node, but ONLY when the requirement has
    adopted per-AC tagging: it labels criteria AND at least one carries a `verifies:`
    tag. Absent means "not measured", and every reader must render it as such.

    The viewer used to invent the pair when it was absent — `clauses` from the number
    of CONTRACT lines, `covered` all-or-nothing from the tested-by badge — so a
    requirement with three real tests read "0 / 8 clauses covered" and sent its owner
    on an investigation. A number nobody computed is worse than no number."""
    labels = [b["label"] for b in _acc_blocks(body) if b["label"] and not b["manual"]]
    if not labels or not covered:
        return
    missing = [ac for ac in labels if ac not in covered]
    node["clauses"] = len(labels)
    node["covered"] = len(labels) - len(missing)
    if missing:
        node["gap"] = "no `verifies:` tag for " + ", ".join(missing)


def _build_map_data(reqs, members, ac_cover=None):  # implements: ARCH-MAP-007  # implements: REQ-MAP-870  # implements: REQ-TRACE-935
    """Assemble the {nodes, edges} registry graph that drives every rendered
    surface (HTML map, Mermaid blocks, and the JSON export). Pure: no IO.

    `ac_cover` ({id: {AC-N: [...]}}, from `scan_ac_verifies`) is what turns the
    per-criterion coverage the gate already computes into something the viewer can
    render honestly; omitted, the coverage fields are simply absent."""
    used_by = {rid: [] for rid in reqs}
    for rid, r in reqs.items():
        for dep in _as_list(r["meta"].get("depends_on")):
            if dep in used_by:
                used_by[dep].append(rid)
    satisfied_by = {rid: [] for rid in reqs}  # reverse upstream edges  # implements: ARCH-TRACE-020
    for rid, r in reqs.items():
        for up in _as_list(r["meta"].get("satisfies")):
            if up in satisfied_by:
                satisfied_by[up].append(rid)
    data = {"nodes": [], "edges": [], "upstream_edges": []}
    for rid, r in reqs.items():
        m = r["meta"]
        _verify = _verify_bullets(r["body"])
        data["nodes"].append({
            "id": rid, "layer": m.get("layer", "feature"),
            "level": m.get("level"),                       # implements: ARCH-LEVEL-051
            "status": m.get("status", "draft"),
            "area": (m.get("area") or "").strip() or _area_of(rid),
            "title": _title(r["body"]),
            "intent": _distinct_intent(r["body"]),
            # new emission schema (Contract / Verify-intent / Notes / Current-impl)
            "contract": _from_any(_bullets, r["body"], CONTRACT_LABELS),
            "verify": _verify,
            # legacy per-topic heading first; ADR-0017's consolidated Context section
            # (bold **Notes**/**Current implementation** sub-groups) is the fallback,
            # never both at once in one file, so this never masks real content.
            "notes": _bullets(r["body"], "notes") or _context_group(r["body"], "notes"),
            "current_impl": (_bullets(r["body"], "current implementation")
                              or _context_group(r["body"], "current implementation")),
            "acc": _acc_items(r["body"]),                    # AC blocks AND bullets
            "accept": _from_any(_section_raw, r["body"], ACCEPTANCE_LABELS),  # raw, line breaks kept
            # legacy schema (Input / Description / Output) — kept so old docs still render
            "input": _section(r["body"], "input"),
            "output": _section(r["body"], "output"),
            # Only the legacy Input/Description/Output triad, never the current
            # `## Description` — which is the Contract and is emitted above.
            "desc": (_section(r["body"], "description")
                     if _has_any(r["body"], ("input", "output")) else ""),
            # `deps` is the historical name and the one the vendored viewer reads
            # (`n.deps` in app/src/lib/loadData.js), so it stays. `depends_on` is the
            # same list under the name the frontmatter and every document use: a
            # consumer that asked for the documented name got a silent None and built
            # the wrong graph from it.
            "deps": _as_list(m.get("depends_on")),
            "depends_on": _as_list(m.get("depends_on")),
            "used_by": used_by.get(rid, []),
            "satisfies": _as_list(m.get("satisfies")),       # upstream needs this fulfils
            "satisfied_by": satisfied_by.get(rid, []),       # requirements fulfilling this need
            "members": [{"role": x[0], "loc": f"{x[1]}:{x[2]}"} for x in members.get(rid, [])],
            "test_exempt": m.get("test_exempt"),
            "milestone": m.get("milestone"),
            "priority": m.get("priority", ""),
            "risks": [{"signal": s, "advice": RISK_ADVICE[s]} for s in _risk_signals(
                {"status": m.get("status", "draft"), "layer": m.get("layer", "feature"),
                 "members": members.get(rid, []),
                 "verify": _verify, "test_exempt": m.get("test_exempt")})],
        })
        _attach_ac_coverage(data["nodes"][-1], r["body"], (ac_cover or {}).get(rid, {}))
    for rid, r in reqs.items():
        for dep in _as_list(r["meta"].get("depends_on")):
            if dep in reqs:                    # skip dangling targets — no phantom node
                data["edges"].append([rid, dep])
        for up in _as_list(r["meta"].get("satisfies")):  # implements: ARCH-TRACE-020
            if up in reqs:
                data["upstream_edges"].append([rid, up])
    return data


def _roadmap_signals(root):  # implements: ARCH-ROADMAP-038  # implements: REQ-ROADMAP-907  # implements: REQ-ROADMAP-983
    """Read TODO.md and report two read-only roadmap signals, or None when the file
    is absent (most repos have no TODO.md, and they must see nothing).

    Returns {"newest_milestone": "vX.Y" or None, "unversioned_headings": [str]}.

    `unversioned_headings` is the one that bites. `_parse_todos_from_text` keeps the
    CURRENT milestone when a `## ` heading does not start with a version, so items
    under such a heading are silently attributed to the section above instead of being
    skipped. A cosmetic rename therefore mis-files entries with no visible error."""
    for base in dict.fromkeys([root, os.path.dirname(os.path.abspath(root))]):
        path = os.path.join(base, "TODO.md")
        if not os.path.exists(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except OSError:
            return None
        versions, bad = [], []
        for line in text.splitlines():
            s = line.strip()
            if not s.startswith("## "):
                continue
            m = re.match(r"^##\s+(v\d[\d.]*)\b", s)
            if m:
                versions.append(m.group(1))
            else:
                bad.append(s[3:].strip())
        newest = max(versions, key=_version_key) if versions else None
        # The newest milestone the roadmap marks SHIPPED (at least one `[x]` item).
        # The reverse-direction check reads this, never `newest`: an open item under a
        # future heading is a plan, and warning on a plan would fire on every roadmap
        # that looks ahead — which is every useful one.
        shipped = [t["milestone"] for t in _parse_todos_from_text(text)
                   if t["done"] and t["milestone"]]
        return {"newest_milestone": newest, "unversioned_headings": bad,
                "newest_shipped": max(shipped, key=_version_key) if shipped else None}
    return None


def _version_key(v):  # implements: ARCH-ROADMAP-038  # implements: REQ-ROADMAP-907
    """Sort key for a `vX.Y.Z` string: compare numerically per segment, so v2.10
    sorts above v2.9 where a string compare would not."""
    return tuple(int(p) for p in v.lstrip("v").split(".") if p.isdigit())


def _roadmap_behind(reqs, roadmap):  # implements: ARCH-ROADMAP-038  # implements: REQ-ROADMAP-907  # implements: REQ-ROADMAP-983
    """(behind, newest_req, unmapped) — the highest `milestone:` any requirement
    declares, plus whether the roadmap and the corpus drifted apart, in EITHER direction.
    `behind`: TODO.md's newest heading trails the requirements. `unmapped`: the
    requirements trail the newest milestone TODO.md marks SHIPPED, so work that shipped
    carries no requirement and the roadmap chart ends before the product does — the
    direction that went unseen for six minors because only the first was checked. One
    comparison, read by `_audit_summary` and `cmd_health` so the two cannot disagree, and
    one line per direction — never one finding per milestone."""
    newest_req = max((m["milestone"] for m in (r["meta"] for r in reqs.values())
                      if m.get("milestone")), key=_version_key, default=None)
    behind = bool(roadmap["newest_milestone"] and newest_req and
                  _version_key(roadmap["newest_milestone"]) < _version_key(newest_req))
    shipped = roadmap.get("newest_shipped")
    unmapped = bool(shipped and newest_req and
                    _version_key(newest_req) < _version_key(shipped))
    return behind, newest_req, unmapped


def _parse_todos_from_text(text):
    """Parse TODO.md content → list of {name, lane, milestone, done} dicts. Pure.
    Items before the first ## vX.Y heading are silently ignored (milestone is required)."""
    todos, current_ms = [], None
    for line in text.splitlines():
        # match the version token at the heading start; a trailing annotation
        # like `## v2.8 (deferred — demand-gated)` is harmless (the capture group
        # isolates the version) and must not drop the milestone's items.
        ms_m = re.match(r"^##\s+(v\d[\d.]*)\b", line.strip())
        if ms_m:
            current_ms = ms_m.group(1)
            continue
        item_m = re.match(r"^-\s+\[([ xX])\]\s+(.+)$", line.strip())
        if item_m and current_ms:
            done = item_m.group(1).lower() == "x"
            rest = item_m.group(2)
            if "|" in rest:
                name_part, meta = rest.rsplit("|", 1)
                name = name_part.strip()
                lane_m = re.search(r"lane:\s*(\w+)", meta)  # lane must be a single word (bus|feature|ops)
                lane = lane_m.group(1) if lane_m else "feature"
            else:
                name, lane = rest.strip(), "feature"
            todos.append({"name": name, "lane": lane, "milestone": current_ms, "done": done})
    return todos


def _parse_todos(root):  # implements: REQ-MAP-871
    """Read TODO.md; tries root first, then one level up (covers plugin/ dogfood layout).
    Returns list of todo dicts; empty list if absent in both locations."""
    for base in dict.fromkeys([root, os.path.dirname(os.path.abspath(root))]):
        path = os.path.join(base, "TODO.md")
        try:
            with open(path, encoding="utf-8") as f:
                return _parse_todos_from_text(f.read())
        except OSError:
            continue
    return []


# ---------------------------------------------------------------------------
# Content translation, reading half — implements: ARCH-TRANSLATE-044
#
# READ-ONLY. The command that produced `requirements/_i18n/<locale>.json` was
# removed on 2026-09-05, together with everything that shelled out to an
# external LLM CLI. What is left reads an already-committed cache file, so no
# code path in this engine starts a subprocess and the gate/sync/CI path stays
# usable on a machine that has never heard of `claude`. A cache entry is served
# only while its hash matches the requirement, so the cache decays as
# requirements are edited and refreshing it is a manual step.
# ---------------------------------------------------------------------------
TRANSLATOR_VERSION = "1"   # part of the cache key: bump to invalidate every cached
                           # translation at once (the `translate` verb that wrote the
                           # cache was removed 2026-09-05; the reader below stays)


def _translation_source_text(body, title):  # implements: ARCH-TRANSLATE-044
    """The exact span that gets translated and hashed: title + WHY + Contract +
    Acceptance. Deliberately wider than binding_hash() (Contract+Acceptance only) —
    a title-only edit must also invalidate a cached translation."""
    return "\n".join([
        title, _first_quote(body),
        _from_any(_section_raw, body, CONTRACT_LABELS),
        _from_any(_section_raw, body, ACCEPTANCE_LABELS),
    ])


def translation_hash(body, title):  # implements: ARCH-TRANSLATE-044  # implements: REQ-TRANSLATE-937
    """Cache-invalidation key for one requirement's translation. NOT binding_hash() —
    see _translation_source_text. Includes TRANSLATOR_VERSION so bumping the prompt
    or the model invalidates every cached entry in one step, not file-by-file."""
    h = hashlib.sha256()
    h.update(_translation_source_text(body, title).encode("utf-8"))
    h.update(TRANSLATOR_VERSION.encode("utf-8"))
    return h.hexdigest()[:12]


def _load_translations(reqs, reqs_dir):  # implements: ARCH-TRANSLATE-044  # implements: REQ-TRANSLATE-938
    """Read every requirements/_i18n/<locale>.json cache file and return
    {rid: {locale: {title, intent, contract, acceptance}}} for entries whose
    stored hash still matches the requirement's CURRENT content. A stale entry
    (source edited since the last `translate` run) is silently dropped rather
    than served — this is what keeps `map`/`map --check` deterministic and
    `claude`-free: they only ever read a file already sitting on disk, and they
    never serve a translation known to be out of date."""
    i18n_dir = os.path.join(reqs_dir, "_i18n")
    if not os.path.isdir(i18n_dir):
        return {}
    out = {}
    for fname in sorted(os.listdir(i18n_dir)):
        if not fname.endswith(".json"):
            continue
        locale = fname[:-len(".json")]
        try:
            with open(os.path.join(i18n_dir, fname), encoding="utf-8") as f:
                cache = json.load(f)
        except (OSError, ValueError):
            continue
        if not isinstance(cache, dict):
            continue
        for rid, entry in cache.items():
            r = reqs.get(rid)
            if not r or not isinstance(entry, dict):
                continue
            title = _title(r["body"])
            if entry.get("hash") != translation_hash(r["body"], title):
                continue
            out.setdefault(rid, {})[locale] = {
                k: entry.get(k, "") for k in ("title", "intent", "contract", "acceptance")
            }
    return out


def _attach_translations(data, reqs, reqs_dir):  # implements: ARCH-TRANSLATE-044  # implements: REQ-TRANSLATE-938
    """Mutate data['nodes'] in place, adding node['i18n'] = {locale: {...}} for
    any node with a fresh cached translation. Shared by cmd_map
    so both emit the same graph — no `claude` call here, file reads only."""
    i18n = _load_translations(reqs, reqs_dir)
    for node in data["nodes"]:
        if node["id"] in i18n:
            node["i18n"] = i18n[node["id"]]
    return data


def cmd_map(ws, root=".", check=False):  # implements: ARCH-MAP-007  # implements: REQ-FINDINGS-856  # implements: REQ-MAP-870
    """Regenerate every derived view of the corpus — `_map.md`, `_map.json` and the
    single-file viewer `_map.html` — or, with `check`, write nothing and return non-zero
    when the committed copies are stale.

    One rendered viewer, and it never leaves `requirements/`. A published copy is built
    where it is published (ADR-0034)."""
    reqs, reqs_dir = ws.reqs, ws.reqs_dir
    data = ws.map_data(root)

    if check:
        return _map_check(data, reqs_dir, root, reqs)

    md_out   = render_md(data, reqs_dir)
    json_out = render_json(data, reqs_dir)
    html_out = render_html(data, reqs_dir)
    print("wrote {}".format(md_out))
    print("wrote {}".format(json_out))
    if html_out:
        print("wrote {}".format(html_out))
    print("({} nodes, {} edges)".format(len(data["nodes"]), len(data["edges"])))
    if os.path.exists(os.path.join(reqs_dir, "_findings.md")):  # implements: ARCH-FINDINGS-010
        cmd_findings(reqs, reqs_dir)   # a committed report follows the requirements it summarizes
    return 0


def _assemble_map_data(reqs, members, reqs_dir, root=".", ac_cover=None):  # implements: ARCH-MAP-007  # implements: REQ-MAP-870
    """The graph plus the three fields every rendered surface needs on top of it
    (repo, todos, translations). One assembler, so `map`, `export` and the gate's
    freshness probe cannot build three subtly different documents and disagree about
    which one is stale."""
    if ac_cover is None:
        # `init` and any embedding caller pass none; computing it here (instead of
        # emitting a coverage-less map) keeps every writer of _map.json byte-identical,
        # so `map --check` cannot flag a map as stale merely because a different
        # command wrote it.
        ac_cover = scan_ac_verifies(root, reqs_dir)
    data = _build_map_data(reqs, members, ac_cover)
    data["repo"] = _repo_name(root)
    data["todos"] = _parse_todos(root)
    _design = _design_summary(root, reqs_dir, with_findings=True)   # implements: REQ-DESIGN-954  # implements: REQ-DESIGN-976
    if _design is not None:
        data["design"] = _design
    # The same record `next` prints its headline from, so the viewer reads the score
    # rather than defining a second one.  # implements: REQ-HEALTH-968
    data["health"] = _health_record(reqs, members, reqs_dir)
    _attach_translations(data, reqs, reqs_dir)
    return data


def _risk_score(meta):  # implements: ARCH-NEXT-013  # implements: REQ-NEXT-885
    """Extract's per-file risk hint (0-3) from frontmatter, or 0 when absent /
    unparseable. Used only to float REVIEW-flagged drafts to the top of a bucket —
    never to gate. Hand-authored requirements have no `risk:` field -> 0."""
    try:
        return int(str(meta.get("risk")).strip())
    except (TypeError, ValueError):
        return 0


_PRIORITY_ORDER = {"must-have": 0, "should-have": 1, "could-have": 2, "wont-have": 3}


def _recorded_members(reqs_dir, ids):  # implements: ARCH-NEXT-013
    """{id: first member loc} from the committed `_map.json`, for those of `ids` whose
    node records a member there. The narrow default scan (no --code) cannot see a
    member outside its root, so a requirement lands in Orphans while the committed
    map proves it has code — this is what turns that into a hint instead of a
    puzzle. Fail-open ({}) when the map is absent or unreadable."""
    try:
        with open(os.path.join(reqs_dir, "_map.json"), encoding="utf-8") as f:
            nodes = json.load(f).get("nodes", [])
    except (OSError, ValueError):
        return {}
    want, out = set(ids), {}
    for n in nodes:
        mem = n.get("members") or []
        if n.get("id") in want and mem and isinstance(mem[0], dict):
            out[n["id"]] = mem[0].get("loc", "")
    return out


def _req_file(reqs, rid):  # implements: ARCH-MODULEFILE-056
    """Where to open `rid`, as `requirements/<file>`. One file may hold many requirements,
    so the id is NOT the filename: `load_requirements` records the real path per block and
    that is the only thing worth printing at a reader."""
    r = reqs.get(rid) or {}
    p = r.get("path")
    return "requirements/" + (os.path.basename(p) if p else str(rid) + ".md")


def _next_pending(reqs, members, code_root, reqs_dir):  # implements: ARCH-NEXT-013  # implements: REQ-NEXT-883
    """Everything `next` has to say about the corpus, before a word of it is
    formatted: the headline counts, the risk buckets in priority order, the
    untagged files, and the two corpus-shape advisories. Returns None when the
    corpus is empty, which the caller reports differently from a clean one."""
    total = len(reqs)
    if total == 0:   # distinguish "nothing set up yet" from "all clean"
        print("No requirements yet. Run `reqmap.py init` to bootstrap from existing "
              "code, or `reqmap.py new AREA-NAME-NNN` to author one.")
        return None
    confirmed = sum(1 for r in reqs.values() if r["meta"].get("status") == "confirmed")
    tested = sum(1 for rid in reqs if any(role == "tested-by" for role, *_ in members.get(rid, [])))
    # `unreviewed` = draft + baseline, the same population the "Drafts to review" bucket
    # holds; the header used to count `draft` only and disagree with the bucket beneath it.
    unreviewed = sum(1 for r in reqs.values() if r["meta"].get("status", "draft") in ("draft", "baseline"))
    print("{} requirement(s) · {} confirmed · {} tested · {} unreviewed\n".format(
        total, confirmed, tested, unreviewed))

    dependents = {rid: 0 for rid in reqs}
    for rid, r in reqs.items():
        for dep in _as_list(r["meta"].get("depends_on")):
            if dep in dependents:
                dependents[dep] += 1
    buckets = {}  # signal -> [(rid, risk_score)]
    for rid, r in reqs.items():
        m = r["meta"]
        node = {"status": m.get("status", "draft"), "layer": m.get("layer", "feature"),
                "members": members.get(rid, []),
                "verify": _verify_bullets(r["body"]), "test_exempt": m.get("test_exempt")}
        for sig in _risk_signals(node):
            buckets.setdefault(sig, []).append((rid, _risk_score(m)))
    # Action buckets, MOST-URGENT FIRST: an unimplemented contract outranks an
    # unreviewed draft. Each bucket is shown and truncated
    # independently, so a high-priority bucket is never hidden below a long low one.
    PLAN = [
        ("unimplemented",     "Orphans (confirmed, no code)"),
        ("untested",          "Needs tests"),
        ("unverified-intent", "Needs intent review"),
        ("unreviewed",        "Drafts to review"),
    ]
    def _priority_ord(rid):
        p = reqs[rid]["meta"].get("priority", "")
        return _PRIORITY_ORDER.get(p, 99)

    pending = [(sig, label, sorted(buckets[sig], key=lambda x: (_priority_ord(x[0]), -x[1], x[0])))
               for sig, label in PLAN if buckets.get(sig)]
    untagged = _scan_untagged(code_root, reqs_dir) if code_root else []
    # Granularity advisory: requirements with many ACs covering disjoint behaviors.
    # Shares `_oversize` with lint's `ac-count-high` check (same threshold, same
    # LINT_STATUSES scoping, same `lint_exempt` honoring) so `next` and `lint`
    # can never report a different set for the same corpus.
    oversize = sorted(
        [(rid, _count_ac(r["body"]))
         for rid, r in reqs.items()
         if _oversize(rid, r)],
        key=lambda x: (-x[1], x[0])
    )
    # The other direction of the same concern: covering the code with FEWER requirements.
    # Granularity above says "this one does too much"; this says "these say the same thing".
    redundant = _redundant_groups(reqs)
    return (total, confirmed, tested, unreviewed, pending, untagged,
            oversize, redundant)

def cmd_next(ws, show_all=False, top_n=3):  # implements: ARCH-NEXT-013  # implements: REQ-NEXT-883  # implements: REQ-NEXT-884  # implements: REQ-NEXT-885  # implements: REQ-NEXT-886  # implements: REQ-NEXT-887
    """Terminal 'what should I do next': a focused, counted worklist over the same
    `_risk_signals` + `RISK_ADVICE` that drive the Risk tab. Prints a progress
    header, leads with the most-urgent bucket, shows the top few per bucket (the
    extract REVIEW-flagged ones first), and collapses the rest behind --all. Each
    item names the requirement file to open. Also surfaces scannable files that
    carry no membership tag (untagged bucket). Read-only, always exit 0."""
    reqs, members, reqs_dir, code_root = ws.reqs, ws.members, ws.reqs_dir, ws.code_root
    found = _next_pending(reqs, members, code_root, reqs_dir)
    if found is None:
        return 0
    (total, confirmed, tested, unreviewed, pending, untagged,
     oversize, redundant) = found
    # Computed BEFORE the early return: Granularity/Redundancy are their own findings, not
    # a footnote on the four risk buckets above — a corpus clean on every bucket but still
    # carrying an oversize or redundant requirement is NOT "nothing pending".
    if not pending and not untagged and not oversize and not redundant:
        print("Nothing pending — every confirmed requirement is implemented, tested and intent-checked.")
        return 0
    if pending:
        total_actions = sum(len(ids) for _, _, ids in pending)
        n_cat = len(pending) + bool(untagged) + bool(oversize) + bool(redundant)
        print("{} item(s) need attention across {} {}:\n".format(
            total_actions, n_cat, "category" if n_cat == 1 else "categories"))
    for sig, label, ids in pending:
        print("{} ({})".format(label, len(ids)))
        shown = ids if show_all else ids[:top_n]
        for rid, score in shown:
            flag = "  [REVIEW]" if score >= 2 else ""
            print("  {}{}   {}".format(rid, flag, _req_file(reqs, rid)))
        if not show_all and len(ids) > top_n:
            print("  ... {} more — run `reqmap.py gate --risk --all`".format(len(ids) - top_n))
        print("  -> {}\n".format(RISK_ADVICE[sig]))
        if sig == "unimplemented" and reqs_dir:
            recorded = _recorded_members(reqs_dir, [rid for rid, _ in ids])
            if recorded:
                rid0 = sorted(recorded)[0]
                print("  note: the committed _map.json records member(s) for {} of these (e.g. {} <- {}) "
                      "that this scan did not reach — if they live outside the scan root, "
                      "re-run with `--code <dir>`.\n".format(len(recorded), rid0, recorded[rid0]))
    if untagged:
        shown_u = untagged if show_all else untagged[:top_n]
        print("Untagged files ({})".format(len(untagged)))
        for fp in shown_u:
            print("  {}".format(fp))
        if not show_all and len(untagged) > top_n:
            print("  ... {} more — run `reqmap.py gate --risk --all`".format(len(untagged) - top_n))
        print("  -> Run `reqmap.py init` to auto-extract requirements, "
              "or add to .reqmapignore to silence.\n")
    if oversize:
        print("Granularity ({})".format(len(oversize)))
        shown_o = oversize if show_all else oversize[:top_n]
        for rid, n in shown_o:
            print("  {}   ({} ACs) — consider splitting   {}".format(
                rid, n, _req_file(reqs, rid)))
        if not show_all and len(oversize) > top_n:
            print("  ... {} more — run `reqmap.py gate --risk --all`".format(len(oversize) - top_n))
        print(
            "  -> A requirement with more than {} acceptance criteria covering disjoint "
            "behaviors is a split candidate. Author two requirements, each with its own "
            "contract.\n"
            .format(LINT_AC_MAX)
        )
    if redundant:
        spare = sum(len(g) - 1 for g in redundant)
        print("Redundancy ({})".format(len(redundant)))
        shown_r = redundant if show_all else redundant[:top_n]
        for g in shown_r:
            print("  {}   identical contract   {}".format(", ".join(g), _req_file(reqs, g[0])))
        if not show_all and len(redundant) > top_n:
            print("  ... {} more — run `reqmap.py gate --risk --all`".format(len(redundant) - top_n))
        print(
            "  -> {} requirement(s) state an obligation another already states, word for "
            "word. Fold each group into one and re-point the tags, or make the contracts "
            "say different things. Exact matches only — run `reqmap.py gate --dupes` for the "
            "near-matches this cannot see.\n".format(spare)
        )
    return 0


# ---------- lint (readability / structure of requirement prose) ----------
# Makes the SKILL.md "Audience & writing level" rules mechanical so requirements
# stay easy to understand. Scoped narrowly to keep false positives near zero: only
# non-draft requirements (drafts are TODO stubs), only the Contract and Acceptance
# sections (Notes may stay dense by design). Jargon-before-definition is deliberately
# NOT checked in v1 — without a term dictionary it is too false-positive-prone on
# prose that carries code references.
LINT_STATUSES = {"baseline", "in-progress", "implemented", "confirmed"}
# Checks promoted from warn→error under `--strict` (structural, not style). One
# constant, because `gate` runs the lint strict and `sync`'s summary counted errors
# without the promotion — a corpus failing `gate` on `over-scoped` had a silent sync.
LINT_STRICT_PROMOTE = frozenset({"ac-count-high", "over-scoped",
                                 "atomic-bullet-then-mismatch", "atomic-story-overlong"})
LINT_STACKED_CONNECTORS = 3    # a normative line with this many 'and'/'or' joins (warn)
LINT_CLAUSE_SENTENCES = 3      # a Contract bullet spanning MORE sentences than this is
                               # flagged by `statement-too-long` (warn). Sentence count is
                               # the only dimension this check measures; words per clause
                               # belong to `statement-size`. A clause may hold two or three
                               # sentences — the extra ones state the first's consequence.
                               # A per-SENTENCE word ceiling was dropped on 2026-09-03: see
                               # ARCH-LINTCHECKS-025's notes for what that gave up.
LINT_STATEMENT_WORDS = 150     # a Contract CLAUSE — continuation lines joined — over this
                               # many words is reported by `statement-size`. Advisory only:
                               # ARCH-ATOMICITY-049 makes atomicity the normative rule and this
                               # threshold an explicit heuristic, so a longer clause stays valid.
LINT_AC_MIN = 3                # fewer ACs than this suggests under-specified (warn)
LINT_AC_MAX = 7                # more ACs than this suggests over-scoped — split candidate (warn)
LINT_ATOMIC_STORY_BULLETS_MAX = 3   # an atomic story quote may enumerate up to this many
                               # `- ` facts before it is no longer one obligation (warn,
                               # 'atomic-story-overlong'); each fact under the ceiling needs
                               # its own `Then` line or 'atomic-bullet-then-mismatch' fires
LINT_CONTRACT_MAX = 10         # contract clauses over this, COMBINED with AC over LINT_AC_MAX,
                               # is the composite 'over-scoped' cohesion signal (warn)
LINT_FILE_SPREAD_MAX = 3       # implements members spanning >= this many distinct files is a
                               # 'file-spread' diffuseness signal (warn) — auto-off below it,
                               # so silent in single-file repos (near-zero false positive)
LINT_BUS_FANOUT_MIN = 3        # a `layer: bus` with ZERO dependents and this many dependencies
                               # is the inverse of a bus ('layer-mismatch', warn). Three, because
                               # this corpus's largest fan-out is three and none of its bus
                               # requirements has zero fan-in — so the check is silent here and
                               # fires on the shape that produced it (0 in / 12 out).
# Closed list of vague QUALITY words that make a normative bullet un-testable
# (IEEE 29148 "Unambiguous"). Deliberately excludes size words (high/low/small/many)
# and weak modals — they are too often legitimately precise in this domain, and a
# false positive trains authors to ignore lint. Only words with no testable meaning.
LINT_VAGUE_TERMS = frozenset({
    "appropriate", "appropriately", "adequate", "adequately", "sufficient",
    "sufficiently", "reasonable", "reasonably", "robust", "robustly", "flexible",
    "efficient", "efficiently", "optimal", "scalable", "performant", "fast", "slow",
    "quick", "quickly", "easy", "easily", "simple", "user-friendly", "seamless",
    "seamlessly", "intuitive", "various", "etc",
})
# Redundant normative modals: the Contract section opens with "Every line in this
# section is binding.", so "shall"/"must" on each clause is dead weight — and in a
# non-English requirement corpus "shall" is also a stray anglicism (see Audience &
# writing level, rule 3). Closed list, checked as a whole word, case-insensitive.
LINT_MODAL_WORDS = frozenset({"shall", "must"})
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z-]*")


def _lint_prose(body, name):  # implements: ARCH-LINT-014  # implements: REQ-LINT-864
    """Yield the prose text lines under the FIRST `## ` heading whose text contains
    `name`, up to the next `## `. A bullet's leading `- ` is stripped so its text is
    linted as a sentence. Non-prose lines — headings, table rows, blockquotes, and
    anything inside a ``` fence — are skipped so the linter never flags code or
    markup as unreadable. Fence state is tracked BEFORE heading detection, so a
    `## ` comment inside a fenced block is treated as code, not a section boundary."""
    out = []
    for s in _section_lines(body, name):
        if not s or s.startswith(("|", ">", "#")):
            continue
        if s == "-" or s.startswith("- "):   # a real bullet marker (not '--strict' / '-5')
            s = s[1:].strip()
        if s:
            out.append(s)
    return out


def _sentences(text):  # implements: ARCH-LINTCHECKS-025  # implements: REQ-LINTCHECKS-865
    """Split a prose line into sentences on '.', '!', '?' boundaries. Crude but
    deterministic — enough to count words per sentence for the length check."""
    return [p.strip() for p in re.split(r"(?<=[.!?])\s+", text) if p.strip()]


def _clip(s, n=60):  # implements: ARCH-LINT-014  # implements: REQ-LINT-864
    """Shorten a snippet for one-line finding output."""
    return s if len(s) <= n else s[:n - 1] + "…"


def _clause_words(text):  # implements: ARCH-ATOMICITY-049  # implements: REQ-ATOMICITY-824  # implements: REQ-ATOMICITY-825
    """Word count for a Contract clause, counting each backticked span as one word.
    A clause carrying a long code sample is short prose, not a long statement. The span
    collapses to a bare token with no padding spaces: " x " would split trailing punctuation
    (`code`. -> "x" ".") into a second word and inflate every such clause by one."""
    return len(re.sub(r"`[^`]*`", "x", text).split())


def _contract_clauses(body):  # implements: ARCH-ATOMICITY-049  # implements: REQ-ATOMICITY-824  # implements: REQ-ATOMICITY-825
    """Yield (n, text) per clause of the Contract section, n 1-based.

    A clause is one bullet at ANY indent — a nested sub-bullet is its own clause because
    it states its own obligation — with its wrapped continuation lines joined back on.
    This is deliberately not `_lint_prose`, which yields physical LINES: these files are
    hard-wrapped near 95 columns, so a 90-word clause reaches `_lint_prose` as six ~15-word
    lines and no per-line ceiling can ever see it. Bold group labels, table rows, block
    quotes, fenced code and HTML comments are not clauses and are skipped."""
    out, cur, in_comment = [], None, False

    def flush():
        if cur is not None:
            out.append(cur)

    for s in _section_lines(body, CONTRACT_LABELS):
        if in_comment:                       # glossary comments are guidance, not clauses
            if "-->" in s:
                in_comment = False
            continue
        if s.startswith("<!--"):
            if "-->" not in s:
                in_comment = True
            continue
        if not s or s.startswith(("|", ">", "#")) or (s.startswith("**") and s.endswith("**")):
            flush(); cur = None
            continue
        if s == "-" or s.startswith("- "):
            flush()
            cur = s[1:].strip()
        elif cur is not None:
            cur += " " + s
    flush()
    return list(enumerate([c for c in out if c], 1))


def _count_ac(body):
    """Count acceptance criteria in the HOW — Acceptance section.
    Handles both bullet-list ACs (- ...) and labeled AC blocks (AC-N ...).
    Delegates to `_acc_blocks`, the single parser of that section, so the count
    `lint` and `next` reason about cannot drift from the criteria the map emits."""
    return len(_acc_blocks(body))


def _lint_sections(body):  # implements: ARCH-LINTCHECKS-025  # implements: REQ-LINT-863
    """The two load-bearing sections: present at all, and carrying anything."""
    findings = []
    # structural (error): a non-draft must carry both load-bearing sections
    if not _has_any(body, CONTRACT_LABELS):
        findings.append({"severity": "error", "check": "missing-section",
                         "detail": "no '## Description' section"})
    if not _has_any(body, ACCEPTANCE_LABELS):
        findings.append({"severity": "error", "check": "missing-section",
                         "detail": "no '## Cases' section"})
    # empty-section (warn): the heading is present but carries no clauses/criteria — it
    # passes `missing-section` yet documents nothing (and `ac-count-low` skips the zero
    # case). Precise zero/non-zero test, so near-zero false positive.
    if _has_any(body, CONTRACT_LABELS) and not _from_any(_bullets, body, CONTRACT_LABELS):
        findings.append({"severity": "warn", "check": "empty-section",
                         "detail": "'## Description' section present but has no clauses"})
    if _has_any(body, ACCEPTANCE_LABELS) and _count_ac(body) == 0:
        findings.append({"severity": "warn", "check": "empty-section",
                         "detail": "'## Cases' section present but has no criteria"})
    return findings

def _lint_readability(body):  # implements: ARCH-LINTCHECKS-025  # implements: REQ-LINT-863
    """Readability of the normative prose: joins per line, anonymous subjects,
    sentence and clause length, and one obligation per clause."""
    findings = []
    # prose readability (warn): only on the Contract + Acceptance sections
    for name in CONTRACT_LABELS + ACCEPTANCE_LABELS:
        for ln in _lint_prose(body, name):
            low = ln.lower()
            # Every line in a Contract/Acceptance section is normative by virtue of the
            # section it sits in, so the join count applies to all of them. This used to be
            # gated on `"shall" in low or "must" in low`, which made the check silent for the
            # plain present-tense voice — a clarity rule keyed on a magic word misses clauses.
            joins = len(re.findall(r"\b(?:and|or)\b", low))
            if joins >= LINT_STACKED_CONNECTORS:
                findings.append({
                    "severity": "warn", "check": "stacked-conditions",
                    "detail": "{} 'and'/'or' joins in one normative line: {}".format(
                        joins, _clip(ln))})
            # Contract only: a clause whose subject is a bare "It" forces the reader to hold
            # the requirement's title in their head to know what is being promised. Name it.
            # Acceptance prose is exempt — a Then clause saying "it returns …" reads fine.
            if name in CONTRACT_LABELS and re.match(r"^It\s+[a-z]", ln):
                findings.append({
                    "severity": "warn", "check": "anonymous-subject",
                    "detail": "clause opens with an unnamed 'It' — name the subject: {}".format(
                        _clip(ln))})
    # statement atomicity (warn): a Contract bullet spanning more than
    # LINT_CLAUSE_SENTENCES sentences packs several statements into one clause (split it).
    # Sentence COUNT is the only dimension here — `long-sentence` owns words per sentence
    # and `statement-size` owns words per clause — so the three checks never flag the same
    # line for the same reason, and a correct two- or three-sentence clause stays silent.
    # Read whole CLAUSES, not the physical lines `_lint_prose` yields. These files wrap
    # near 95 columns, so a line-based count can never see a clause that spans several
    # lines — which is why this check reported 0 corpus-wide while measuring the wrong
    # unit. Measured before the switch: 0 of 625 non-draft clauses hold more than three
    # sentences, so widening the unit changes nothing the check says today.
    clauses = _contract_clauses(body)
    for _cn, ln in clauses:
        sents = _sentences(ln)
        if len(sents) > LINT_CLAUSE_SENTENCES:
            findings.append({
                "severity": "warn", "check": "statement-too-long",
                "detail": "statement spans {} sentences (>{}): {}".format(
                    len(sents), LINT_CLAUSE_SENTENCES, _clip(ln))})
    # statement-size (warn, advisory): a Contract clause well past the length a single
    # obligation normally needs. Measured per CLAUSE, not per line — see _contract_clauses.
    # Advisory by contract: exceeding the threshold never makes a clause invalid and never
    # asserts that it holds two obligations, which the engine cannot observe
    # (ARCH-ATOMICITY-049). The finding carries clause_n/clause_text so `--decompose` can
    # scaffold from the same clause without re-parsing.
    for _n, _clause in clauses:
        _cw = _clause_words(_clause)
        if _cw > LINT_STATEMENT_WORDS:
            findings.append({
                "severity": "warn", "check": "statement-size",
                "clause_n": _n, "clause_text": _clause,
                "detail": "clause {} is {} words (>{}) \u2014 re-read it for decomposition: {}".format(
                    _n, _cw, LINT_STATEMENT_WORDS, _clip(_clause))})
    return findings

def _lint_acceptance(body, r, rid):  # implements: ARCH-LINTCHECKS-025  # implements: REQ-LINT-863
    """The acceptance criteria: how many there are, and whether the atomic form
    proves every fact its story claims."""
    findings = []
    # ac count (warn): too few = under-specified; too many = over-scoped
    if _has_any(body, ACCEPTANCE_LABELS):
        ac_n = _count_ac(body)
        # An atomic requirement holds ONE obligation, so one criterion is the correct
        # number, not an under-specified one. LINT_AC_MIN guards a dossier.
        if 0 < ac_n < LINT_AC_MIN and not _atomic_spans(body):
            findings.append({
                "severity": "warn", "check": "ac-count-low",
                "detail": "{} AC (< {}): requirement may be under-specified".format(
                    ac_n, LINT_AC_MIN)})
        elif _oversize(rid, r):
            findings.append({
                "severity": "warn", "check": "ac-count-high",
                # Name a remedy that EXISTS. The finding used to say only "consider
                # splitting", while `lint_exempt:` was documented as the one-line escape
                # hatch — so the cheapest visible action was to silence it, and that is
                # what readers (and assistants) reached for. Naming `--decompose` was the
                # fix for that, and it named the wrong thing: `--decompose` acts on
                # `statement-size` findings only (see the NOTE above `cmd_lint`), so an
                # author running it on an over-scoped requirement got `All clean` and no
                # files, from a command the gate had just called an error. A remedy that
                # no-ops is worse than no remedy: it sends the reader back to
                # `lint_exempt:`, which the skill says must never be the reflex.
                "detail": "{} AC (> {}): several capabilities in one requirement \u2014 move "
                          "criteria onto the child requirements that own them until {} or "
                          "fewer remain (`--decompose` does not cover this check)".format(
                              ac_n, LINT_AC_MAX, LINT_AC_MAX)})
    # atomic bullet/Then parity (warn, --strict-promotable): the atomic form's `>` story
    # quote may enumerate up to LINT_ATOMIC_STORY_BULLETS_MAX facts, but every existing
    # signal is blind to whether each one is actually proven — `_count_ac` counts the ONE
    # Scenario regardless of how many facts the story bundles into it, and `ac-count-low`
    # explicitly exempts the atomic form. A 3-bullet story with a single `Then` passed every
    # check that existed before this one (the REQ-FANOUT-391/392 shape: a leaf asserted
    # behavior its parent forbade, and nothing caught it).
    _sp = _atomic_spans(body)
    if _sp:
        _story_lines, _scen_lines = _sp
        _bn = _atomic_story_bullets(_story_lines)
        _tn = _atomic_scenario_then_count(_scen_lines)
        if _bn > LINT_ATOMIC_STORY_BULLETS_MAX:
            findings.append({
                "severity": "warn", "check": "atomic-story-overlong",
                "detail": "{} bullets in the story quote (> {}): no longer a single "
                          "obligation — split it into its own requirements".format(
                              _bn, LINT_ATOMIC_STORY_BULLETS_MAX)})
        elif _bn > 1 and _bn != _tn:
            findings.append({
                "severity": "warn", "check": "atomic-bullet-then-mismatch",
                "detail": "{} bullets in the story quote but {} 'Then' line(s) in the "
                          "Scenario — each enumerated fact needs its own Then".format(
                              _bn, _tn)})
    return findings

def _lint_shape(rid, r, body, children):  # implements: ARCH-LINTCHECKS-025  # implements: REQ-LINT-863
    """Corpus shape: a requirement over both ceilings at once, and a parent whose
    fan-out sits outside the band for its level."""
    findings = []
    # cohesion (warn): over BOTH the contract and acceptance ceilings at once is a strong
    # "several capabilities bundled into one" signal — each contract clause is a separate
    # binding, each AC an independent failure mode. Requiring BOTH axes (a composite) keeps
    # false positives near zero: a large-but-cohesive capability rarely maxes both. Advisory
    # only — it surfaces split candidates; the split decision stays with the human.
    if _has_any(body, CONTRACT_LABELS) and _has_any(body, ACCEPTANCE_LABELS):
        # Scope units, not sentences. A contract that groups its clauses under bold labels
        # states one facet per group, so the group count is what says how much the
        # requirement promises; the clause count only says how finely the prose was split.
        # Counting clauses alone punished the atomic voice — one obligation per bullet
        # multiplies bullets without widening scope at all. Ungrouped contracts fall back
        # to the clause count, which is what this check has always used.
        # Counted off _section_raw, not _lint_prose: _lint_prose strips each line, and a
        # label is defined by sitting at column 0 (see _is_label_line). Given stripped
        # input every wrapped clause that opens and closes on bold spans counts as a
        # group, inflating contract_n — and `over-scoped` is an ERROR under --strict, so
        # that miscount fails CI on a requirement that is not over-scoped.
        groups = sum(1 for ln in _from_any(_section_raw, body, CONTRACT_LABELS).split("\n")
                     if _is_label_line(ln))
        contract_n = groups or len(_from_any(_bullets, body, CONTRACT_LABELS))
        ac_count = _count_ac(body)
        if contract_n > LINT_CONTRACT_MAX and ac_count > LINT_AC_MAX:
            findings.append({
                "severity": "warn", "check": "over-scoped",
                # The trigger is an AND, so clearing EITHER number clears the finding —
                # which is genuinely useful to an author and was nowhere in the output.
                # Same correction as `ac-count-high`: `--decompose` cannot act on this.
                "detail": "{} contract {} + {} AC (both over {}/{}): likely several "
                          "capabilities \u2014 bring either number under its ceiling and this "
                          "clears (`--decompose` does not cover this check)".format(
                              contract_n, "groups" if groups else "clauses",
                              ac_count, LINT_CONTRACT_MAX, LINT_AC_MAX)})
    # fan-out (warn): a parent in the `satisfies:` hierarchy normally carries 5-20 children.
    # Too few and the level buys no grouping; too many and it is a bucket, not a level.
    # Counted on the satisfies graph, NOT on `depends_on` — the two are different axes, and
    # `depends_on` depth here maxes out at 3, so a band of 5-20 read against it would flag
    # every requirement in the corpus. A leaf (zero children) is skipped: it is not a
    # malformed parent, it is not a parent at all.
    # The band depends on which level the parent sits at — see LINT_FANOUT_BANDS. A parent
    # declaring no level keeps the uniform band it always had.
    _lo, _hi = LINT_FANOUT_BANDS.get(r["meta"].get("level"), (LINT_FANOUT_MIN, LINT_FANOUT_MAX))
    if children:
        if _lo is not None and children < _lo:
            findings.append({
                "severity": "warn", "check": "fan-out",
                "detail": "{} requirement(s) satisfy this one (below {}): too few to be "
                          "a level".format(children, _lo)})
        elif children > _hi:
            findings.append({
                "severity": "warn", "check": "fan-out",
                "detail": "{} requirement(s) satisfy this one (over {}): too many — "
                          "split it".format(children, _hi)})
    return findings

def _lint_terms(body):  # implements: ARCH-LINTCHECKS-025  # implements: REQ-LINT-863
    """Words that make a clause untestable: vague quality terms, and a modal the
    section header already supplies."""
    findings = []
    # vague terms (warn): a Contract bullet using a non-testable quality word is
    # ambiguous (IEEE 29148). Code spans (`backticked`) are stripped first so a
    # backticked identifier is never flagged. One finding per distinct term.
    # Iterates CONTRACT_LABELS (current `## Description` first, legacy `## Contract`
    # still honoured) rather than the literal string "contract" — a hardcoded legacy
    # label here left this check dead on every requirement using the current heading.
    seen_vague = set()
    for name in CONTRACT_LABELS:
        for ln in _lint_prose(body, name):
            bare = re.sub(r"`[^`]*`", " ", ln)
            for w in _WORD_RE.findall(bare):
                lw = w.lower()
                if lw in LINT_VAGUE_TERMS and lw not in seen_vague:
                    seen_vague.add(lw)
                    findings.append({
                        "severity": "warn", "check": "vague-term",
                        "detail": "vague word '{}' (no testable meaning): {}".format(
                                w, _clip(ln))})
    # redundant modal (warn): "shall"/"must" on a Contract clause is either dead weight
    # (the section header already binds every line) or a stray English modal dropped into
    # a non-English clause. Same one-finding-per-distinct-term shape as vague-term, above.
    # Same CONTRACT_LABELS iteration as vague-term, above, for the same reason.
    seen_modal = set()
    for name in CONTRACT_LABELS:
        for ln in _lint_prose(body, name):
            bare = re.sub(r"`[^`]*`", " ", ln)
            for w in _WORD_RE.findall(bare):
                lw = w.lower()
                if lw in LINT_MODAL_WORDS and lw not in seen_modal:
                    seen_modal.add(lw)
                    findings.append({
                        "severity": "warn", "check": "redundant-modal",
                        "detail": "redundant modal '{}' (the Contract header already binds "
                                  "every line — use plain present tense): {}".format(
                                      w, _clip(ln))})
    return findings

def _lint_graph(r, member_list, fanin):  # implements: ARCH-LINTCHECKS-025  # implements: REQ-LINT-863
    """What the requirement looks like from outside: how far its members are spread,
    and whether its declared layer matches its fan-in."""
    findings = []
    # file-spread (warn): a requirement whose implements members span many distinct FILES is
    # architecturally diffuse — a cohesion axis the intent-axis checks (over-scoped, ac-count)
    # cannot see, since a tight contract can still be smeared across many files. Auto-off when
    # the members live in fewer than LINT_FILE_SPREAD_MAX files, so it is silent in a single-file
    # repo (near-zero false positive). Needs member_list; skipped when not supplied.
    if member_list:
        impl_files = {m[1] for m in member_list if m and m[0] == "implements"}
        if len(impl_files) >= LINT_FILE_SPREAD_MAX:
            findings.append({
                "severity": "warn", "check": "file-spread",
                "detail": "implements span {} files (>= {}): capability may be diffuse — "
                          "confirm cohesion or split".format(len(impl_files), LINT_FILE_SPREAD_MAX)})
    # layer-mismatch (warn): `bus` is DEFINED by fan-in ("foundation, high fan-in"),
    # and nothing checked it. A requirement with no dependents and many dependencies is
    # the exact inverse — a roof labelled a foundation. It reads as bus in the map, in
    # `next`, and in every diagnostic built on the layer, so the mislabel misleads
    # precisely where the layer is supposed to help. `layer: aggregate` is the label
    # such a requirement wants.
    if (fanin is not None and r["meta"].get("layer") == "bus"
            and fanin == 0
            and len(_as_list(r["meta"].get("depends_on"))) >= LINT_BUS_FANOUT_MIN):
        findings.append({
            "severity": "warn", "check": "layer-mismatch",
            "detail": "layer: bus but nothing depends on it and it depends on {} "
                      "requirement(s) — that is a roof, not a foundation; consider "
                      "`layer: aggregate` or `feature`".format(
                          len(_as_list(r["meta"].get("depends_on"))))})
    return findings


def lint_requirement(rid, r, member_list=None, fanin=None, children=None):  # implements: ARCH-LINT-014  # implements: ARCH-LINTCHECKS-025  # implements: ARCH-FANOUT-052  # implements: REQ-LINT-863  # implements: REQ-LINTCHECKS-865  # implements: REQ-LINTCHECKS-866  # implements: REQ-LINTCHECKS-867  # implements: REQ-LINTCHECKS-868  # implements: REQ-LINTCHECKS-869
    """Return a list of {severity, check, detail} findings for one requirement;
    an empty list means clean. Checks the Contract + Acceptance sections only.
    `member_list` (optional [(role, file, line), ...]) enables the member-based
    file-spread check; when omitted, that check is skipped.
    `fanin` (optional int — how many requirements depend on this one) enables the
    layer-mismatch check; when omitted, that check is skipped.
    `children` (optional int — how many requirements declare `satisfies:` this one) enables
    the fan-out check; when omitted, or when it is zero, that check is skipped.
    Checks named in the requirement's `lint_exempt:` frontmatter list are silently
    skipped and not counted against the requirement."""
    exempt = set(_as_list(r["meta"].get("lint_exempt")))
    body = r["body"]
    findings = []
    findings += _lint_sections(body)
    findings += _lint_readability(body)
    findings += _lint_acceptance(body, r, rid)
    findings += _lint_shape(rid, r, body, children)
    findings += _lint_terms(body)
    findings += _lint_graph(r, member_list, fanin)
    if exempt:
        findings = [f for f in findings if f["check"] not in exempt]
    return findings



DECOMPOSED_TEMPLATE = """---
id: {new_id}
status: draft
layer: {layer}
owner: {owner}
depends_on: [{parent}]
superseded_by:
---

# Split from {parent} clause {n}

<!-- decomposed-from: {parent}#{n} -->

## Description
> Scaffolded by `lint --decompose` from a clause that ran past
> LINT_STATEMENT_WORDS words. Rewrite this quote before confirming: say what this
> capability is and what breaks without it.

Every bullet below is binding.
- {clause}

## Verify intent (open questions for the human)
- Does this clause state one obligation, or several? The split point was chosen by
  word count, so this file may hold a clause that was atomic all along.

## Cases (= tests)
CASE-1
  Given  <precondition>
  When   <action>
  Then   <observable, pass/fail result>

## Context (non-binding)
**Notes**
- SCAFFOLD, NOT A DECISION. `lint --decompose` copied clause {n} of {parent} here
  verbatim. The split point was chosen by WORD COUNT, never by obligation — the engine
  cannot observe how many obligations a clause holds (ARCH-ATOMICITY-049). Read the clause
  and decide for yourself whether it should have been split at all.
- The clause is still over the threshold here, because only a human can divide it. Confirming
  this file unedited re-raises the same `statement-size` finding, which is the intended
  reminder.
- {parent} was not modified. Deleting this file restores the corpus exactly.
"""


def _next_free_number(reqs_dir, reqs=None):  # implements: ARCH-DECOMPOSE-050  # implements: REQ-DECOMPOSE-838
    """Highest NNN across the corpus, plus one. Ids stay in AREA-NAME-NNN shape rather
    than taking a derived suffix such as REQ-AUTH-012-B: the suffix form passes _ID_PAT,
    but _warn_number_collision reads parts[-1] as the number and would compare "B".

    Read from the loaded ids when the caller has them: a module file
    (ARCH-MODULEFILE-056) holds many ids under one name, so the file names alone
    reported 110 on a corpus whose highest id was 982 — one `--decompose` away from a
    duplicate id. The directory listing is only the fallback for a caller with no corpus."""
    best = 0
    stems = list(reqs or ())
    try:
        stems += [fn[:-3] for fn in os.listdir(reqs_dir)
                  if fn.endswith(".md") and not fn.startswith("_")]
    except OSError:
        if reqs is None:
            return 1
    for stem in stems:
        parts = stem.split("-")
        if len(parts) >= 3 and parts[-1].isdigit():
            best = max(best, int(parts[-1]))
    return best + 1


def _already_decomposed(reqs_dir, parent_id, n, reqs=None):  # implements: ARCH-DECOMPOSE-050  # implements: REQ-DECOMPOSE-839
    """True when some requirement already carries the `decomposed-from: <parent>#<n>` marker.

    Re-running must be a no-op, and the allocated file NAME cannot detect that: the id comes
    from the next free number, so a second run picks a fresh name and `os.path.exists` never
    fires. Provenance is the only stable key. The marker is an HTML comment rather than a
    frontmatter field so it stays invisible to `binding_hash`, and `decomposed-from` is not
    a member role, so TAG_LIST_RE never reads it as a link. The loaded bodies answer it
    without re-reading the directory; the listing is the fallback for a caller without them."""
    needle = "decomposed-from: {}#{}".format(parent_id, n)
    if reqs is not None and any(needle in r["body"] for r in reqs.values()):
        return True   # else fall through: a draft written earlier in this run is on disk only
    try:
        names = os.listdir(reqs_dir)
    except OSError:
        return False
    for fn in names:
        if not fn.endswith(".md") or fn.startswith("_"):
            continue
        try:
            with open(os.path.join(reqs_dir, fn), encoding="utf-8") as f:
                if needle in f.read():
                    return True
        except (OSError, ValueError):
            continue
    return False


def _decompose_clause(reqs_dir, parent_id, parent, n, clause, reqs=None):  # implements: ARCH-DECOMPOSE-050  # implements: REQ-DECOMPOSE-837  # implements: REQ-DECOMPOSE-838
    """Scaffold one draft requirement from an over-threshold Contract clause.

    Creates exactly one file and never touches the parent, so a confirmed contract cannot
    drift and deleting the new file undoes the whole operation. Returns the created id, or
    None when this clause was already scaffolded (re-running is a no-op, reported by the
    caller)."""
    if _already_decomposed(reqs_dir, parent_id, n, reqs):
        return None
    parts = parent_id.split("-")
    stem = "-".join(parts[:-1]) if len(parts) >= 3 and parts[-1].isdigit() else parent_id
    new_id = "{}-{:03d}".format(stem, _next_free_number(reqs_dir, reqs))
    dest = os.path.join(reqs_dir, new_id + ".md")
    if os.path.exists(dest) or (reqs is not None and new_id in reqs):
        return None
    meta = parent["meta"]
    text = DECOMPOSED_TEMPLATE.format(
        new_id=new_id, parent=parent_id, n=n, clause=clause,
        layer=meta.get("layer", "feature") or "feature",
        owner=meta.get("owner", "") or "")
    os.makedirs(reqs_dir, exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        f.write(text)
    return new_id


# NOTE: `--decompose` deliberately covers `statement-size` ONLY. An `ac-count-high`
# triage-stub path was written and then removed before it ever shipped: `_oversize`
# fires on 0 of this corpus's 72 lintable requirements (all six over LINT_AC_MAX
# carry `lint_exempt: [ac-count-high]`), so the path was unreachable, and ADR-0022 —
# adopted in the same change — forbids shipping on a signal with no published fire
# rate AND no human-confirmation sample. `ac-count-high` had a 0.0% post-exempt rate
# and no independent sample, which is the profile ADR-0022 used to REJECT its sibling
# proposal. Re-adding it needs that ADR's bar met first, not a code review.


def cmd_lint(ws, strict=False, decompose=False, only=None):  # implements: ARCH-LINT-014  # implements: ARCH-DECOMPOSE-050  # implements: REQ-LINT-863
    """Report readability/structure violations on non-draft requirements so they
    stay easy to understand — the SKILL.md 'Audience & writing level' rules made
    mechanical. Checks: missing-section (error),
    stacked-conditions (warn), statement-too-long (warn), ac-count-low (warn),
    ac-count-high (warn), vague-term (warn), redundant-modal (warn). Read-only. Exit-neutral by default; with
    --strict it exits non-zero on any error-severity finding AND promotes structural
    checks (ac-count-high) to error severity.
    Requirements with `lint_exempt: [check-name]` frontmatter silently skip those checks;
    active exemptions are printed after the requirement header.
    The default run writes nothing. With `decompose` (the opt-in `--decompose` flag) each
    `statement-size` finding scaffolds one draft requirement from its clause. It covers
    that check ONLY - see the note above `cmd_lint` for why `ac-count-high` does not get
    the same treatment. The gate, the pre-commit hook and CI never pass it: `gate` runs
    the lint and the map-freshness check in one verdict, so a file written during the
    lint step would fail the freshness check of the same run (ARCH-DECOMPOSE-050).
    `only` narrows the run to one id — `clarify <ID> --decompose` promises to scaffold
    for that requirement, not for every over-long clause in the corpus. A run that
    scaffolds nothing says which findings the flag acts on: the two checks that are
    ERRORS under `--strict` are not among them, and a reader who has just been told to
    split something must not read `All clean` as agreement."""
    reqs, members, reqs_dir = ws.reqs, ws.members, ws.reqs_dir
    targets = [(rid, r) for rid, r in sorted(reqs.items())
               if r["meta"].get("status") in LINT_STATUSES
               and (only is None or rid == only)]
    fanin = {rid: 0 for rid in reqs}                      # implements: ARCH-LINTCHECKS-025
    kids = {rid: 0 for rid in reqs}                        # implements: ARCH-FANOUT-052
    for _rid, _r in reqs.items():                          # satisfies edges, child side
        for _up in _as_list(_r["meta"].get("satisfies")):
            if _up in kids:
                kids[_up] += 1
    for _rid, _r in reqs.items():
        for _dep in _as_list(_r["meta"].get("depends_on")):
            if _dep in fanin:
                fanin[_dep] += 1
    errors = warns = 0
    created = []
    for rid, r in targets:
        fs = lint_requirement(rid, r, (members or {}).get(rid), fanin.get(rid), kids.get(rid))
        exempt = set(_as_list(r["meta"].get("lint_exempt")))
        if not fs and not exempt:
            continue
        print("{}   {}".format(rid, _req_file(reqs, rid)))
        if exempt:
            print("  (exempt: {})".format(", ".join(sorted(exempt))))
        for f in fs:
            effective = f["severity"]
            if strict and f["check"] in LINT_STRICT_PROMOTE:
                effective = "error"
            if effective == "error":
                errors += 1; mark = "ERROR"
            else:
                warns += 1; mark = "warn "
            print("  {} {:18} {}".format(mark, f["check"], f["detail"]))
        if decompose and reqs_dir:
            for f in fs:
                if f["check"] == "statement-size":
                    made = _decompose_clause(reqs_dir, rid, r, f["clause_n"], f["clause_text"], reqs)
                    if made:
                        created.append(made)
                        print("  created  requirements/{}.md  (draft, seeded from clause {})".format(
                            made, f["clause_n"]))
                    else:
                        print("  skipped  clause {} \u2014 already scaffolded".format(f["clause_n"]))
    print("\n{} non-draft requirement(s) linted · {} error(s) · {} warning(s)".format(
        len(targets), errors, warns))
    if created:
        print("{} draft(s) scaffolded: {}".format(len(created), ", ".join(created)))
        print("note: each split point was chosen by word count, not by obligation \u2014 "
              "read each draft before confirming it.")
    elif decompose:
        # Silence here read as "nothing to split", which is the opposite of the truth when
        # the same run has just printed an over-scoped ERROR. Say which findings the flag
        # acts on, so a no-op is legible as a no-op rather than as a clean bill of health.
        print("nothing scaffolded: `--decompose` acts on `statement-size` findings, and "
              "{} none.".format("this requirement has" if only else "the corpus has"))
    if errors == 0 and warns == 0:
        print("All clean — every linted requirement is well-formed and readable.")
    if strict and errors:
        print("FAIL (--strict): {} structural error(s) (includes promoted structural warns).".format(errors))
        return 1
    return 0


def cmd_show(ws, cap_id, levels=None):  # implements: ARCH-SHOW-015  # implements: ARCH-VLEVEL-037  # implements: REQ-SHOW-917  # implements: REQ-SHOW-918  # implements: REQ-SHOW-919  # implements: REQ-TRACE-935  # implements: REQ-VLEVEL-946
    """Print one consolidated, human-readable dossier for a single requirement: its
    status/layer/intent, contract, dependencies (both directions), members grouped
    by role, open verify-intent questions, and risk signals — the 'what does this do
    / where is X' view in one command. Read-only; returns 1 on an unknown id so a
    typo is visible to a caller or CI. Reuses the same signal source as next/findings."""
    reqs, members = ws.reqs, ws.members
    r = reqs.get(cap_id)
    if not r:
        print("no requirement with id {} (expected requirements/{}.md)".format(cap_id, cap_id))
        return 1
    m, body = r["meta"], r["body"]
    head = "{} · {} · {}".format(cap_id, m.get("status", "draft"), m.get("layer", "?"))
    if m.get("priority"):
        head += " · " + m["priority"]
    if m.get("milestone"):
        head += " · " + m["milestone"]
    print(head)
    print(_req_title(body, cap_id))
    intent = _distinct_intent(body)         # "" when it would just repeat the Contract below
    if intent:
        print("  " + intent)

    contract = _from_any(_bullets, body, CONTRACT_LABELS)
    print("\nContract:")
    for b in contract:
        print("  - " + b)
    if not contract:
        print("  (none — no '## Description' section)")

    deps = _as_list(m.get("depends_on"))
    dependents = sorted(rid for rid, rr in reqs.items()
                        if cap_id in _as_list(rr["meta"].get("depends_on")))
    print("\nDepends on: " + (", ".join(deps) if deps else "(none)"))
    print("Depended on by: " + (", ".join(dependents) if dependents else "(none)"))

    # upstream traceability: only shown when the requirement participates in it,  # implements: ARCH-TRACE-020
    # so requirements that don't use `satisfies` get no extra noise.
    upstream = _as_list(m.get("satisfies"))
    satisfiers = sorted(rid for rid, rr in reqs.items()
                        if cap_id in _as_list(rr["meta"].get("satisfies")))
    if upstream or satisfiers:
        print("Satisfies (upstream): " + (", ".join(upstream) if upstream else "(none)"))
        print("Satisfied by: " + (", ".join(satisfiers) if satisfiers else "(none)"))

    mem = members.get(cap_id, [])
    # {(file, line): level} for this requirement, so a levelled tested-by link shows the
    # level it asserts rather than leaving the reader to open the file.
    at = {}
    for lvl, hits in (levels or {}).get(cap_id, {}).items():
        for hit in hits:
            at[hit] = lvl
    print("\nMembers in code ({}):".format(len(mem)))
    if mem:
        for role, fp, ln in sorted(mem):
            lvl = at.get((fp, ln))
            print("  {:18} {}:{}{}".format(role, fp, ln, " @" + lvl if lvl else ""))
    else:
        print("  (none tagged)")

    verify = [b for b in _verify_bullets(body)
              if b and not b.lstrip("*_ ").lower().startswith("none")]
    if verify:
        print("\nOpen verify-intent:")
        for b in verify:
            print("  - " + b)

    node = {"status": m.get("status", "draft"), "layer": m.get("layer", "feature"), "members": mem,
            "verify": _verify_bullets(body), "test_exempt": m.get("test_exempt")}
    signals = _risk_signals(node)
    if signals:
        print("\nRisk signals:")
        for s in signals:
            print("  [{}] {}".format(s, RISK_ADVICE[s]))
    print("\n{}".format(r["path"]))
    return 0


# ---------- similar (duplicate-capability detection) ----------
# Flags requirement pairs whose contracts overlap, so a human can catch a divergent
# re-implementation before it lands. Stdlib TF-IDF + cosine over the normative text
# (title + intent + Contract); Notes is excluded as too dense/noisy.
SIMILAR_THRESHOLD = 0.35       # cosine above this -> reported as a probable-duplicate pair
_SIMILAR_STOP = frozenset((
    "the", "and", "for", "shall", "with", "that", "this", "from", "into", "its",
    "not", "are", "has", "have", "when", "then", "given", "each", "one", "any",
    "per", "via", "use", "used", "must", "code", "requirement", "requirements",
))


def _sim_tokens(text):  # implements: ARCH-SIMILAR-016  # implements: REQ-SIMILAR-921
    """Lowercase alphanumeric tokens of length >= 3, minus stopwords and pure
    numbers — the bag of words a requirement is compared on. Deterministic."""
    return [t for t in re.findall(r"[a-z0-9]+", text.lower())
            if len(t) >= 3 and not t.isdigit() and t not in _SIMILAR_STOP]


def _placeholder_contract(body):  # implements: ARCH-SIMILAR-016
    """True when every Contract bullet is still a `TODO:` scaffold line. Five evidence
    runs scored thousands of freshly-drafted stubs as near-duplicates of each other on
    template text alone (fabric: 6,340 pairs for 638 drafts) — nothing authored, nothing
    to compare."""
    bullets = _from_any(_bullets, body, CONTRACT_LABELS)
    return bool(bullets) and all(b.strip().upper().startswith("TODO") for b in bullets)


def _exemption_reason_recorded(body, check):  # implements: ARCH-AUDIT-065  # implements: REQ-AUDIT-971
    """True when the requirement's own prose mentions the check it exempts itself from.

    Deliberately the crudest possible test: the check's name appearing anywhere in the
    body. It cannot judge whether the reason is a GOOD one — no mechanical test can —
    and it is not trying to. It only makes the exemption cost one sentence a reviewer
    can argue with, instead of one frontmatter token nobody ever reads."""
    return check.lower() in (body or "").lower()


def _exemptions_in_force(reqs):  # implements: ARCH-AUDIT-065  # implements: REQ-AUDIT-971
    """Every `lint_exempt:`/`gate_exempt:` entry in the corpus, as records carrying the
    requirement, the field, the silenced check and whether a reason is recorded.

    An exemption is a finding somebody decided not to see. Listing them is what keeps
    "silenced" from becoming "invisible": a corpus that exempted forty checks shows
    forty lines here, and the count is the debt."""
    out = []
    for rid in sorted(reqs):
        r = reqs[rid]
        meta, body = r["meta"], r["body"]
        for field in ("lint_exempt", "gate_exempt"):
            for check in _as_list(meta.get(field)):
                out.append({"id": rid, "field": field, "check": check,
                            "reason": _exemption_reason_recorded(body, check)})
    return out


def _corpus_shape(reqs):  # implements: ARCH-AUDIT-065  # implements: REQ-AUDIT-972
    """How the corpus sits on the V-model's left arm: how many requirements declare a
    `level:`, how they spread across the rungs, and how many `satisfies:` edges hold the
    pyramid together.

    `level:` is opt-in (the template ships it commented out) so an existing corpus keeps
    its behaviour, and the consequence is that a repo can run the engine for months with
    every requirement on one rung and nothing ever mentioning the other two. This says it
    once, in `audit`, and never in the gate: adopting a level axis is a decision, not a
    defect.

    `auto` counts the rungs the ENGINE wrote (`level_source: auto`, ADR-0030). Since
    `init` drafts a pyramid, a corpus can now be fully levelled and still be nothing but
    the engine's own guesses — every other number here would read as healthy. This is the
    number ADR-0030's revisit trigger asks for: a pyramid still made of proposals is
    untriaged, not done."""
    total = len(reqs)
    levels, edges, auto = {}, 0, 0
    for r in reqs.values():
        meta = r["meta"]
        lv = meta.get("level")
        if lv:
            levels[lv] = levels.get(lv, 0) + 1
            if meta.get("level_source") == "auto":
                auto += 1
        edges += len(_as_list(meta.get("satisfies")))
    levelled = sum(levels.values())
    return {"total": total, "levelled": levelled, "levels": levels,
            "satisfies_edges": edges, "auto": auto,
            "flat": bool(total) and levelled * 10 < total}


def _redundant_groups(reqs):  # implements: ARCH-REDUNDANCY-058
    """Requirements whose Description clauses are IDENTICAL once case and whitespace are
    normalised, grouped, each group sorted and the groups ordered by their first id.

    This is the exact-match floor under `dupes`, not a second opinion on it: no threshold,
    no scoring, so a group is a duplicate by construction and never a judgement call. It
    exists because decomposing several architecture requirements can mint the same
    obligation twice — the same clause authored in two parents becomes two detailed-design
    requirements — and nothing else in the engine notices. `dupes` finds the near-matches
    this cannot; neither replaces the other.

    Draft placeholders are skipped: every freshly scaffolded requirement carries the same
    `TODO:` line, so counting those would report the scaffold as a duplicate of itself
    hundreds of times and drown the real finding."""
    groups = {}
    for rid, r in sorted(reqs.items()):
        body = r["body"]
        if _placeholder_contract(body):
            continue
        key = re.sub(r"\s+", " ", " ".join(_from_any(_bullets, body, CONTRACT_LABELS))).strip().lower()
        if key:
            groups.setdefault(key, []).append(rid)
    return sorted((sorted(v) for v in groups.values() if len(v) > 1), key=lambda g: g[0])


def _sim_text(body):  # implements: ARCH-SIMILAR-016  # implements: REQ-SIMILAR-921
    """The text similarity is computed on: title, intent line, and Contract bullets.
    Notes & limitations is left out — it is dense and would only add noise."""
    parts = [_req_title(body, "")]
    for line in body.splitlines():
        if line.strip().startswith(">"):
            parts.append(line.strip().lstrip(">").strip())
            break
    parts += _from_any(_bullets, body, CONTRACT_LABELS)
    return " ".join(parts)


def _tfidf(docs):  # implements: ARCH-SIMILAR-016  # implements: REQ-SIMILAR-922
    """docs: {id: token_list}. Returns {id: {term: weight}} with smoothed idf =
    log((1 + N) / (1 + df)) + 1 — always positive (so a 2-doc corpus does not
    collapse to zero), while still down-weighting terms common across requirements."""
    N = len(docs)
    df = {}
    for toks in docs.values():
        for t in set(toks):
            df[t] = df.get(t, 0) + 1
    vecs = {}
    for rid, toks in docs.items():
        tf = {}
        for t in toks:
            tf[t] = tf.get(t, 0) + 1
        vecs[rid] = {t: c * (math.log((1 + N) / (1 + df[t])) + 1) for t, c in tf.items()}
    return vecs


def _cosine(a, b):  # implements: ARCH-SIMILAR-016  # implements: REQ-SIMILAR-922
    """Cosine similarity of two {term: weight} vectors, in [0, 1]. The result is
    clamped to 1.0 because floating-point rounding can push parallel vectors a hair
    over 1.0 (e.g. 1.0000000000000002), which would break the documented range."""
    if not a or not b:
        return 0.0
    dot = sum(a[t] * b[t] for t in set(a) & set(b))
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return min(1.0, dot / (na * nb)) if na and nb else 0.0


def _threshold_arg(v):  # implements: ARCH-SIMILAR-016
    """argparse type for `--threshold`: a finite number in (0, 1]. Rejects nan/inf
    (which silently swallow or admit every pair under `>=`) and out-of-range cutoffs."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError("threshold must be a number")
    if not math.isfinite(f) or not (0.0 < f <= 1.0):
        raise argparse.ArgumentTypeError("threshold must be a finite number in (0, 1]")
    return f


def _test_suite_pairs(members):  # implements: REQ-SIMILAR-921
    """Pairs (A, B) where a `tested-by` member file of A is an `implements` member of B —
    i.e. B is the requirement that IS A's test suite. Such a pair shares vocabulary by
    construction and is a known link, not a duplicate. Empty when no member map is given."""
    impl_of = {}   # file -> set of requirement ids implemented in it
    for rid, mem in (members or {}).items():
        for role, f, _ in mem:
            if role == "implements":
                impl_of.setdefault(f, set()).add(rid)
    linked = set()
    for rid, mem in (members or {}).items():
        for role, f, _ in mem:
            if role == "tested-by":
                for other in impl_of.get(f, ()):
                    if other != rid:
                        linked.add(frozenset((rid, other)))
    return linked


def cmd_similar(reqs, threshold=SIMILAR_THRESHOLD, members=None, top=None):  # implements: ARCH-SIMILAR-016  # implements: REQ-SIMILAR-920  # implements: REQ-SIMILAR-923
    """Report requirement pairs whose contracts overlap at or above `threshold`
    (cosine over TF-IDF of title + intent + Contract), most-similar-first, so a human
    can spot a probable duplicate or a capability that should be merged. Read-only and
    always exit 0 (advisory). Smoothed idf down-weights shared boilerplate so it
    does not inflate the score. Callers pass a validated threshold in (0, 1].
    With `members`, a pair linked by `tested-by` (one requirement is the other's test
    suite) is skipped and counted instead of reported."""
    linked = set(_test_suite_pairs(members))
    # a child restates part of its parent's contract by construction (the parent's
    # summary clause names it), so a parent-child pair is never a duplicate finding
    for rid, r in reqs.items():
        for up in _as_list((r.get("meta") or {}).get("satisfies")):
            linked.add(frozenset((rid, up)))
    placeholder = sorted(rid for rid, r in reqs.items() if _placeholder_contract(r["body"]))
    docs = {rid: _sim_tokens(_sim_text(r["body"])) for rid, r in reqs.items()
            if rid not in placeholder}
    docs = {rid: toks for rid, toks in docs.items() if toks}   # skip empty contracts
    if placeholder:
        print("skipped {} requirement(s) whose Contract is still the draft placeholder — "
              "dupes compares authored contracts only.\n".format(len(placeholder)))
    if len(docs) < 2:
        print("Need at least two requirements with contract text to compare.")
        return 0
    vecs = _tfidf(docs)
    ids = sorted(vecs)
    pairs = []
    skipped_linked = 0
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            s = _cosine(vecs[ids[i]], vecs[ids[j]])
            if s >= threshold:
                if frozenset((ids[i], ids[j])) in linked:
                    skipped_linked += 1
                    continue
                shared = sorted(set(vecs[ids[i]]) & set(vecs[ids[j]]),
                                key=lambda t: (-(vecs[ids[i]][t] + vecs[ids[j]][t]), t))[:5]
                pairs.append((s, ids[i], ids[j], shared))
    pairs.sort(key=lambda x: (-x[0], x[1], x[2]))
    if skipped_linked:
        print("skipped {} pair(s) linked by tested-by or satisfies (a requirement and its own "
              "test suite, or a parent and its child, share vocabulary by construction).\n".format(skipped_linked))
    if not pairs:
        print("No overlapping requirement pairs at or above {:.2f}. {} requirement(s) compared.".format(
            threshold, len(docs)))
        return 0
    print("{} probable-duplicate pair(s) at or above {:.2f} (of {} requirement(s)):\n".format(
        len(pairs), threshold, len(docs)))
    shown = pairs if top is None else pairs[:top]
    for s, a, b, shared in shown:
        print("  {:.2f}  {}  <->  {}".format(s, a, b))
        print("        shared terms: {}".format(", ".join(shared) or "(none)"))
    if len(shown) < len(pairs):
        print("  ... {} more pair(s) — raise --top to see them".format(len(pairs) - len(shown)))
    print("\nThese contracts overlap — check they are not the same capability "
          "implemented twice. Merge or differentiate, then re-run.")
    return 0


# ---------- search (free-text requirement lookup) ----------
# Ranks requirements against a free-text query with the SAME lexical TF-IDF/cosine
# used by `dupes` — reused, not re-implemented. The floor is NOT the dupes 0.35
# pair-threshold: a short query is a sparse vector, so query-vs-doc cosine runs far
# lower than doc-vs-doc. Calibrated on the 39-requirement corpus, a correct top hit
# scores ~0.13-0.67 while a no-lexical-overlap query tops out ~0.00-0.04, so 0.05
# cleanly separates a real match from noise. Below it, `search` says so rather than
# presenting a spurious top result with the same authority as a real one.
SEARCH_FLOOR = 0.05
SEARCH_TOP = 5


# Searching a requirement browser for `ARCH-CHECK-006` used to return
# REQ-ORPHANCODE-888 and not the requirement itself: the bag of words is title +
# intent + clauses, and an id is in none of them, so "arch" and "check" were matched
# as ordinary prose. An id is the primary key of this corpus; a query that names one
# is not asking to be ranked.
SEARCH_ID_MAX = 3          # substring id hits shown before the lexical ranking


def _id_matches(reqs, query):  # implements: ARCH-SEARCH-036  # implements: REQ-SEARCH-965
    """Requirement ids the query names, best first: an exact id, then ids it prefixes,
    then ids that contain it. An exact hit is alone and unconditional; the looser two
    are capped so a common word like `map` cannot crowd out the lexical ranking."""
    q = (query or "").strip().upper()
    if len(q) < 3:
        return []
    if q in reqs:
        return [q]
    prefix = sorted(rid for rid in reqs if rid.upper().startswith(q))
    inner = sorted(rid for rid in reqs if q in rid.upper() and rid not in prefix)
    return (prefix + inner)[:SEARCH_ID_MAX]


def _text_matches(reqs, query, translations=None, skip=()):  # implements: REQ-SEARCH-965
    """Requirements whose title, description or cases plainly contain the query, plus any
    cached translation of them.

    Scoped to exactly what the reader is asking about: the normative text and the cases
    that prove it. `## Context` is deliberately excluded, for the same reason the ranking
    bag excludes it — a word that appears only in commentary is not what the requirement
    is about, and REQ-SEARCH-912 already decided that.

    This is also the layer that answers a query in the language the reader is being
    shown: the ranking model weights one language's tokens, so a translated requirement
    is invisible to it. Substring, not ranked, and it only fills the slots the model
    left empty."""
    q = (query or "").strip().lower()
    if len(q) < 3:
        return []
    out = []
    for rid in sorted(reqs):
        if rid in skip:
            continue
        body = reqs[rid]["body"]
        hay = "\n".join([
            _req_title(body, rid),
            _from_any(_section_raw, body, CONTRACT_LABELS) or "",
            _from_any(_section_raw, body, ACCEPTANCE_LABELS) or "",
        ]).lower()
        for entry in ((translations or {}).get(rid) or {}).values():
            if isinstance(entry, dict):
                hay += "\n" + "\n".join(str(v).lower() for v in entry.values())
        if q in hay:
            out.append(rid)
    return out


def cmd_search(reqs, query, top=SEARCH_TOP, floor=SEARCH_FLOOR, reqs_dir=None):  # implements: ARCH-SEARCH-036  # implements: REQ-SEARCH-912  # implements: REQ-SEARCH-913  # implements: REQ-SEARCH-914  # implements: REQ-SEARCH-915
    """Rank requirements by lexical relevance to `query` (cosine over TF-IDF of the
    same title + intent + Contract text `dupes` compares on). Read-only, always exit
    zero. Prints each hit's cosine score so a weak match is visible as weak, and emits
    an explicit no-strong-match line when the best score is below `floor` — so a
    lexical near-miss is never dressed up as an answer."""
    ids = _id_matches(reqs, query)
    qtok = _sim_tokens(query or "")
    if not qtok and not ids:
        print("No searchable terms in {!r} (need a word of 3+ letters that is not a "
              "stopword). Nothing to rank.".format(query or ""))
        return 0
    docs = {rid: _sim_tokens(_sim_text(r["body"])) for rid, r in reqs.items()}
    docs = {rid: toks for rid, toks in docs.items() if toks}   # skip empty contracts
    if not docs:
        print("No requirements with contract text to search.")
        return 0
    top = max(1, top)
    corpus = dict(docs)
    corpus["\x00query"] = qtok        # fold the query into the corpus so idf spans docs+query
    vecs = _tfidf(corpus)
    qv = vecs["\x00query"]
    scored = sorted(((_cosine(qv, vecs[rid]), rid) for rid in docs),
                    key=lambda x: (-x[0], x[1]))
    # Order: id, then literal text, then the ranked model. A document that CONTAINS the
    # query is stronger evidence than a partial token overlap with it -- a phrase that
    # appears verbatim inside a case used to lose to a 0.10 cosine somewhere else.
    translations = _load_translations(reqs, reqs_dir) if reqs_dir else {}
    text = _text_matches(reqs, query, translations, skip=set(ids))[:max(0, top - len(ids))]
    seen = set(ids) | set(text)
    lexical = [(s, rid) for s, rid in scored
               if s >= floor and rid not in seen][:max(0, top - len(seen))]
    if not (ids or lexical or text):
        print("No match for {!r}: no id, no literal text, and the best lexical (cosine) "
              "score {:.3f} is below the {:.2f} floor. Try different words, or "
              "`dupes`/grep.".format(
                  query, scored[0][0] if scored else 0.0, floor))
        return 0
    print("{} match(es) for {!r} — id, then literal text, then cosine score (lexical, "
          "not synonym-aware):\n".format(len(ids) + len(lexical) + len(text), query))
    for rid in ids:
        print("  {:>6}  {}  {}".format("id", rid, _req_title(reqs[rid]["body"], rid)))
    for rid in text:
        print("  {:>6}  {}  {}".format("text", rid, _req_title(reqs[rid]["body"], rid)))
    for s, rid in lexical:
        print("  {:.3f}  {}  {}".format(s, rid, _req_title(reqs[rid]["body"], rid)))
    return 0


# ---------- health (corpus coherence snapshot) ----------
def _audit_section(title, remedy, fn, fail_rc=0):  # implements: ARCH-AUDIT-065  # implements: REQ-AUDIT-970
    """Run one discovery pass with its output captured, so the summary can be printed
    before the detail it summarises. Returns (title, remedy, text, rc).

    A crashing section is swallowed because advice must not fail a build — but the Gate
    section is not advice, it IS the exit code, and swallowing its crash to rc 0 printed
    `Gate  clean` for a run that never reached a verdict. `fail_rc` is how a section says
    what its own failure means; only the gate passes 1."""
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            rc = fn()
    except Exception as e:                      # a section is advice, never a crash
        return (title, remedy, "  (section failed: {})".format(e), fail_rc)
    return (title, remedy, buf.getvalue().rstrip(), rc or 0)


def _audit_summary(reqs, members, reqs_dir, code_root):  # implements: ARCH-AUDIT-065  # implements: REQ-AUDIT-973
    """The one-line-per-signal tail `sync` prints: what `audit` would report, without
    running the passes that cost a second walk of the tree. Silent about anything that
    is clean, so a healthy repo sees nothing and the lines that do appear are news."""
    lines = []
    exemptions = _exemptions_in_force(reqs)
    unexplained = [e for e in exemptions if not e["reason"]]
    if unexplained:
        lines.append("{} exemption(s) silence a check with no reason recorded".format(
            len(unexplained)))
    # Readability, reported where it is cheapest to act on. `gate` is what ENFORCES it
    # (and the pre-commit hook runs `gate`), so this changes no exit code — it moves the
    # moment a finding is seen to the one where the author still has the clause in mind.
    lint_errors = lint_warns = 0
    for rid, r in reqs.items():
        if r["meta"].get("status") not in LINT_STATUSES:
            continue
        for f in lint_requirement(rid, r, members.get(rid)):
            if f["severity"] == "error" or f["check"] in LINT_STRICT_PROMOTE:
                lint_errors += 1     # the same promotion `gate` applies (it lints strict)
            else:
                lint_warns += 1
    # Errors only. A style warning is not a reason to break this summary's silence on an
    # otherwise-clean corpus: this repo carries two long-standing ones, so a line keyed on
    # warnings would fire on every sync forever, which is the habit ADR-0016 rejected. An
    # ERROR is a confirmed requirement missing a load-bearing section — worth the line.
    if lint_errors:
        lines.append("readability: {} error(s) across the non-draft corpus ({} warning(s) "
                     "too) - run `reqmap.py gate` for the lines".format(lint_errors, lint_warns))
    shape = _corpus_shape(reqs)
    unlevelled = shape["total"] - shape["levelled"]
    if unlevelled:
        # Reported at ANY ratio, not only under `flat`. `flat` is `levelled * 10 < total`,
        # so a corpus 85% of the way through a retrofit said nothing at all — and a
        # partly-levelled corpus is precisely what a retrofit leaves behind, so the one
        # state this tail could not see was the one it exists to report. The remedy is
        # named here rather than left in `audit`: a signal whose command the reader has to
        # go and find is a signal most readers will not act on.
        lines.append("{} of {} requirements declare no `level:`{} - "
                     "`reqmap.py clarify --levels` proposes a rung for each and writes "
                     "nothing without --apply".format(
                         unlevelled, shape["total"],
                         " - the corpus is flat" if shape["flat"] else ""))
    if shape.get("auto"):
        # A corpus can be fully levelled and still be nothing but the engine's guesses,
        # in which case every other number here reads as healthy. ADR-0030's revisit
        # trigger is exactly this ratio. Reported beside the line above rather than
        # instead of it: "some rungs are missing" and "some rungs are guesses" are two
        # facts, and a corpus mid-retrofit is usually both.
        lines.append("{} of {} levelled requirement(s) still carry the rung the engine "
                     "proposed (`level_source: auto`) - rename, merge or accept them"
                     .format(shape["auto"], shape["levelled"]))
    design = _design_summary(code_root, reqs_dir) if code_root else None
    if design is not None and design["clean_files"] < design["files"]:
        lines.append("design {}/100 - {} of {} source files carry a candidate".format(
            design["score"], design["files"] - design["clean_files"], design["files"]))
    untagged = _scan_untagged(code_root, reqs_dir) if code_root else None
    if untagged:
        lines.append("{} code file(s) traced to no requirement".format(len(untagged)))
    roadmap = _roadmap_signals(code_root) if code_root else None
    if roadmap:
        behind, newest_req, unmapped = _roadmap_behind(reqs, roadmap)
        if behind:
            lines.append("TODO.md stops at {} while the requirements reach {} - the roadmap "
                         "is behind".format(roadmap["newest_milestone"], newest_req))
        if unmapped:
            lines.append("the requirements stop at {} while TODO.md marks work shipped "
                         "through {} - the roadmap chart ends before the product does"
                         .format(newest_req, roadmap["newest_shipped"]))
        if roadmap["unversioned_headings"]:
            lines.append("{} TODO.md heading(s) are not milestones, so their items never "
                         "reach the roadmap".format(len(roadmap["unversioned_headings"])))
    if not lines:
        return
    print("")
    for ln in lines:
        print("info  {}".format(ln))
    print("info  run `reqmap.py gate --audit` for the full report")


def cmd_audit(ws, strict=False, as_json=False):  # implements: ARCH-AUDIT-065  # implements: REQ-AUDIT-970
    """Run every pass that discovers a problem, and print one report.

    The engine grew one verb per question — is it linked, is it drifted, is it
    duplicated, is it tagged, is the design rotting — and answering "how is this repo
    doing" meant remembering all of them. This runs them together and prints a summary
    of what each found, then each section's own output underneath.

    Read-only. The exit code comes from the gate alone: everything else here is advice,
    and advice must not be able to fail a build. Two sections have no verb of their own
    because they only make sense in this report: the exemptions in force, and the shape
    of the corpus on the V-model's left arm."""
    reqs, members, reqs_dir, code_root = ws.reqs, ws.members, ws.reqs_dir, ws.code_root
    exemptions = _exemptions_in_force(reqs)
    unexplained = [e for e in exemptions if not e["reason"]]
    shape = _corpus_shape(reqs)
    health = _health_record(reqs, members, reqs_dir)
    design = _design_summary(code_root, reqs_dir) if code_root else None
    untagged = _scan_untagged(code_root, reqs_dir) if code_root else None

    if as_json:
        out = {"health": health, "shape": shape, "exemptions": exemptions,
               "redundant_groups": [sorted(g) for g in _redundant_groups(reqs)]}
        if design is not None:
            out["design"] = design
        if untagged is not None:
            out["untagged"] = len(untagged)
        errs, warns = run_gate_rules(
            GateContext(ws, full_members=members, update_lock=False),
            strict=strict)
        out["gate"] = {"errors": len(errs), "warnings": len(warns),
                       "findings": [dict(f) for f in list(errs) + list(warns)]}
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 1 if errs else 0

    sections = [
        _audit_section("Gate", "reqmap.py gate",
                       lambda: cmd_check(ws, False, strict=strict), fail_rc=1),
        _audit_section("Risk", "reqmap.py gate --risk", lambda: cmd_next(ws, False)),
        _audit_section("Duplicates", "reqmap.py gate --dupes",
                       lambda: cmd_similar(reqs, SIMILAR_THRESHOLD, members)),
        _audit_section("Design", "reqmap.py gate --design",
                       lambda: cmd_design(code_root, reqs_dir)),
        _audit_section("Tag coverage", "reqmap.py gate --risk --untagged",
                       lambda: cmd_coverage(ws, False)),
    ]
    gate_rc = sections[0][3]

    print("AUDIT  {} requirement(s) - engine {}".format(len(reqs), MAP_ENGINE_VERSION))
    print("")
    verdict = "FAIL" if gate_rc else "clean"
    rows = [("Gate", verdict, "reqmap.py gate"),
            ("Health", "{}/100 ({}/{} green on every axis)".format(
                health["score"], health["healthy"], health["total"]), "reqmap.py gate --risk")]
    if design is not None:
        rows.append(("Design OOP", "{}/100 ({}/{} files with no candidate)".format(
            design["score"], design["clean_files"], design["files"]), "reqmap.py gate --design"))
    if untagged is not None:
        rows.append(("Untagged code", "{} file(s) traced to no requirement".format(len(untagged)),
                     "reqmap.py gate --risk --untagged"))
    dups = _redundant_groups(reqs)
    if dups:
        rows.append(("Redundancy", "{} group(s) share an identical contract".format(len(dups)),
                     "reqmap.py gate --dupes"))
    rows.append(("Exemptions", "{} in force, {} with no recorded reason".format(
        len(exemptions), len(unexplained)), "see below"))
    rows.append(("Corpus shape", "{}/{} carry a `level:`{}".format(
        shape["levelled"], shape["total"], " - the corpus is flat" if shape["flat"] else ""),
        "see below"))
    width = max(len(r[0]) for r in rows)
    vwidth = max(len(r[1]) for r in rows)
    for name, value, remedy in rows:
        print("  {}  {}  {}".format(name.ljust(width), value.ljust(vwidth), remedy))
    print("")

    for title, remedy, text, _rc in sections:
        print("-" * 72)
        print("{}   ({})".format(title, remedy))
        print("-" * 72)
        print(text if text else "  nothing to report")
        print("")

    # ---- the two sections with no verb of their own -------------------------
    print("-" * 72)
    print("Exemptions in force")
    print("-" * 72)
    if not exemptions:
        print("  none - no requirement silences a check.")
    else:
        for e in exemptions:
            mark = " " if e["reason"] else "!"
            print("  {} {:<22} {}: [{}]{}".format(
                mark, e["id"], e["field"], e["check"],
                "" if e["reason"] else "   <- no reason recorded"))
        print("")
        print("  An exemption is a finding somebody decided not to see. It is legitimate")
        print("  when the shape is deliberate and the reason is written down; it is not a")
        print("  way to make a run green. For an over-scoped requirement the fix is")
        print("  `reqmap.py clarify <ID> --decompose`, which scaffolds the extra clause out.")
    print("")

    print("-" * 72)
    print("Corpus shape - the V-model's left arm")
    print("-" * 72)
    if shape["levelled"]:
        for lv in ("system", "architecture", "code"):
            if lv in shape["levels"]:
                print("  {:<14} {}".format(lv, shape["levels"][lv]))
        for lv in sorted(k for k in shape["levels"] if k not in ("system", "architecture", "code")):
            print("  {:<14} {}   (not one of the three rungs)".format(lv, shape["levels"][lv]))
        print("  satisfies:     {} edge(s)".format(shape["satisfies_edges"]))
    if shape["flat"]:
        print("  {} of {} requirements declare no `level:`, so every one of them reads as".format(
            shape["total"] - shape["levelled"], shape["total"]))
        print("  the same rung. `level:` is opt-in - the template ships it commented out - so")
        print("  a corpus never gains the axis by itself. The three rungs are:")
        print("    system        a stakeholder need, satisfied by architecture, not by code")
        print("    architecture  one capability: a command, or a shared engine facility")
        print("    code          one behaviour group, 3-7 labelled cases, tested per case")
        print("  The edge that builds the pyramid is `satisfies:` (the level axis), not")
        print("  `depends_on:` (the composition axis). Adopting it is a decision, not a")
        print("  defect: nothing here fails because a corpus is flat.")
        # A detection that names no next step leaves a reader knowing they are flat
        # and not knowing what to do about it. Now that a retrofit exists, say so.
        print("  If you decide to adopt it: `reqmap.py clarify --levels` proposes a rung")
        print("  for each requirement and writes nothing without --apply.")
    print("")
    return gate_rc


def cmd_coverage(ws, as_json=False):
    """Per-directory coverage report: how many scannable files in each top-level
    directory carry at least one membership tag vs. total scannable files.
    Helps identify which parts of the codebase have no requirement coverage."""
    members, reqs_dir, code_root = ws.members, ws.reqs_dir, ws.code_root
    # requirements dir holds spec files, not implementation files — excluded from coverage.
    # `_walk_files` already prunes it by realpath; this abspath test also catches an SSOT
    # dir reached through a symlink.
    reqs_abs = os.path.normcase(os.path.abspath(reqs_dir)) if reqs_dir else None
    tagged_files = set()
    for mlist in members.values():
        for _role, fp, _ln in mlist:
            tagged_files.add(os.path.normcase(os.path.abspath(os.path.join(code_root, fp))))

    buckets = {}  # dir_label -> [total, tagged]
    for fp, rel in _walk_code(code_root, reqs_dir):
        norm_fp = os.path.normcase(os.path.abspath(fp))
        if reqs_abs and norm_fp.startswith(reqs_abs + os.sep):
            continue
        # Group by first path component (top-level directory or "." for root files)
        parts = rel.split("/")
        label = parts[0] if len(parts) > 1 else "."
        if label not in buckets:
            buckets[label] = [0, 0]
        buckets[label][0] += 1
        if norm_fp in tagged_files:
            buckets[label][1] += 1

    rows = []
    for label in sorted(buckets):
        total, tagged = buckets[label]
        pct = round(100 * tagged / total) if total else 0
        rows.append({"dir": label, "total": total, "tagged": tagged, "pct": pct})

    if as_json:
        print(json.dumps(rows, indent=2))
        return 0

    if not rows:
        print("No scannable files found.")
        return 0

    w = max(len(r["dir"]) for r in rows)
    for r in rows:
        bar = "#" * (r["pct"] // 5) + "." * (20 - r["pct"] // 5)
        print("{:<{w}}  {:>3}/{:<3}  ({:>3}%)  [{}]".format(
            r["dir"], r["tagged"], r["total"], r["pct"], bar, w=w))
    total_all = sum(r["total"] for r in rows)
    tagged_all = sum(r["tagged"] for r in rows)
    pct_all = round(100 * tagged_all / total_all) if total_all else 0
    print("\nTotal: {}/{} files tagged ({:>3}%)".format(tagged_all, total_all, pct_all))
    return 0


def _dependency_cycles(reqs):  # implements: ARCH-CHECK-006
    """Every `depends_on` cycle in the registry, as a list of id lists, each ending
    where it began (`A, B, C, A`). Deterministic: nodes and edges are walked in
    sorted order, so the same corpus always reports the same cycles in the same
    shape.

    A cycle means the layering claim is false — no requirement in it can be built
    before the others — and nothing looked for one. It surfaced as a rendering
    artifact instead: the viewer ranks by longest path, which never converges on a
    cycle, so a 59-requirement corpus with three cycles laid out 236 columns wide
    and drew its edges as endless horizontal lines. That is the symptom; this is
    the cause, and it belongs in the gate's report, not in a diagram."""
    adj = {rid: [d for d in sorted(_as_list(r["meta"].get("depends_on"))) if d in reqs]
           for rid, r in reqs.items()}
    state, stack, cycles, seen = {}, [], [], set()
    for root in sorted(adj):
        if state.get(root):
            continue
        # iterative DFS — a deep chain must not hit the interpreter's recursion limit
        work = [(root, iter(adj[root]))]
        state[root] = 1
        stack.append(root)
        while work:
            node, it = work[-1]
            nxt = next(it, None)
            if nxt is None:
                state[node] = 2
                stack.pop()
                work.pop()
                continue
            if state.get(nxt) == 1:                      # closes a cycle
                cyc = stack[stack.index(nxt):] + [nxt]
                key = frozenset(cyc)
                if key not in seen:
                    seen.add(key)
                    cycles.append(cyc)
            elif state.get(nxt) != 2:
                state[nxt] = 1
                stack.append(nxt)
                work.append((nxt, iter(adj[nxt])))
    return cycles


def _commits_since_reqs_touch(code_root, reqs_dir):  # implements: ARCH-REGISTRYLAG-035  # implements: REQ-REGISTRYLAG-903
    """Count commits on HEAD since the last commit that touched `reqs_dir`.

    The advisory "registry lag" signal: a large number means the registry has
    sat frozen while code raced ahead of it — the exact 18-day-freeze condition
    that let a money value drift with no requirement update. Returns None (not 0)
    when unmeasurable — git missing, `code_root` not a git worktree, or `reqs_dir`
    has no commit in history — so the reading is absent rather than falsely 0.
    Read-only; never a gate, never enters the score."""
    # reqs_dir must resolve against the CALLER's cwd, not against code_root — `git -C
    # code_root` changes where the pathspec is resolved, so a relative reqs_dir (e.g.
    # `--code ..` from `plugin/`) would silently look for `../requirements` instead of
    # `../plugin/requirements`. Mirrors the abspath(p) pattern `untracked_locks` already
    # uses for the same reason (ARCH-CHECK-006).
    sha = (_git(["-C", code_root, "log", "-1", "--format=%H", "--", os.path.abspath(reqs_dir)],
                timeout=5) or "").strip()
    if not sha:
        return None
    cnt = _git(["-C", code_root, "rev-list", "--count", "{}..HEAD".format(sha)], timeout=5)
    try:
        return int((cnt or "").strip())
    except ValueError:
        return None


def _health_record(reqs, members, reqs_dir):  # implements: ARCH-HEALTH-017  # implements: REQ-HEALTH-968
    """The corpus coherence snapshot as a record, with no printing and no code
    root: the headline `score` plus the component counts behind it. Split out of
    `cmd_health` so the map can carry the same numbers the console prints instead
    of a viewer recomputing them in JavaScript — two definitions of one score is
    how the CLI and the UI come to disagree about how the repo is doing.

    Depends only on the requirements, their members and the lock, so it is as
    deterministic as the rest of `_map.json` and can be checked for freshness.
    Everything that needs a code root (untagged files, registry lag, the design
    score) stays in `cmd_health`, which layers it on top of this record."""
    total = len(reqs)
    lock = load_lock(reqs_dir)
    satisfied = set()  # need ids with >=1 `satisfies:` edge (ARCH-TRACE-020)
    for r in reqs.values():
        satisfied.update(_as_list(r["meta"].get("satisfies")))
    confirmed = implemented = tested = orphans = untested = open_intent = drifted = drafts = healthy = 0
    for rid, r in reqs.items():
        m, body = r["meta"], r["body"]
        status = m.get("status", "draft")
        roles = _member_roles(members.get(rid, []))
        has_impl = "implements" in roles
        # a need is covered by being satisfied, not implemented, and its test
        # axis is waived — a need is fulfilled by requirements, not by code.
        # An aggregate is covered the same way, downward: by its depends_on edges.
        is_need = m.get("layer") == "need"
        covered = has_impl
        if is_need:
            covered = rid in satisfied
        elif _impl_exempt(m):                     # aggregate: covered by its dependencies
            covered = bool(_as_list(m.get("depends_on")))
        has_test_member = "tested-by" in roles
        has_test = has_test_member or bool(m.get("test_exempt"))
        is_confirmed = status == "confirmed"
        open_now = status != "draft" and any(
            b and not b.lstrip("*_ ").lower().startswith("none")
            for b in _verify_bullets(body))
        old = lock.get(rid)
        is_drifted = bool(old) and old != binding_hash(body) and is_confirmed
        confirmed += is_confirmed
        implemented += has_impl
        tested += has_test_member
        drafts += status == "draft"
        orphans += is_confirmed and not covered
        untested += has_impl and not has_test_member and not m.get("test_exempt")
        open_intent += open_now
        drifted += is_drifted
        if is_confirmed and covered and (has_test or _impl_exempt(m)) and not open_now and not is_drifted:
            healthy += 1
    score = round(100 * healthy / total) if total else 0
    # Reviewed-subset score (read-only, ADDITIVE). `score` counts every requirement,
    # and a `draft` can never be green because the first axis is status `confirmed` —
    # so each draft caps `score` by construction until someone confirms it. That makes
    # the headline unable to tell "rotting" from "not reviewed yet": a repo that runs
    # `init` over legacy code gets hundreds of drafts and a near-zero score that no
    # amount of care moves. This second number scores only the reviewed part, so the
    # two readings are separable. `score` itself is NOT redefined — CASE-2 binds an
    # all-draft corpus to zero, and every consumer badge already reads `score`.
    # Absent (not zero) when nothing has been reviewed, like `untagged` above: 0 of 0
    # is not 0%, and a consumer's schema must not gain a meaningless key.
    # implements: ARCH-REVIEWEDSCORE-109
    # Emitted only when drafts and reviewed requirements BOTH exist: with no reviewed
    # requirement it would be 0 of 0, and with no draft it would restate `score` under a
    # second name, which is how a consumer's schema quietly grows a key that means nothing.
    # The denominator is `confirmed`, NOT "every non-draft". `healthy`'s first axis is
    # `status == confirmed`, so a `baseline`/`in-progress`/`implemented`/`deprecated`
    # requirement could enter a "non-draft" denominator but never the numerator — it
    # would depress the score with nothing rotting. A `deprecated` requirement is the
    # clearest case: retired, permanently un-green, and it would cap the score forever.
    # Invisible in THIS repo (all 72 non-drafts are `confirmed`, so the two readings
    # coincide at 100), which is exactly why it is pinned by a test instead of by luck.
    reviewed_total = confirmed  # implements: ARCH-REVIEWEDSCORE-109
    reviewed_score = round(100 * healthy / reviewed_total) if (reviewed_total and drafts) else None
    gate_errors = _link_sync_errors(reqs, members)
    data = {"score": score, "total": total, "healthy": healthy,
            "confirmed": confirmed, "implemented": implemented, "tested": tested,
            "drafts": drafts, "orphans": orphans, "untested": untested,
            "open_intent": open_intent, "drift": drifted,
            "gate_errors": len(gate_errors), "gate_link_sync_clean": not gate_errors}
    if reviewed_score is not None:
        data["reviewed_score"] = reviewed_score
        data["reviewed_total"] = reviewed_total
    return data


def cmd_health(ws, as_json=False, as_badge=False, headline_only=False):  # implements: ARCH-HEALTH-017  # implements: REQ-HEALTH-857  # implements: REQ-HEALTH-858  # implements: REQ-HEALTH-859
    """Print a corpus coherence snapshot: a headline score plus component counts.
    The score is transparent — the percentage of requirements green on EVERY axis
    (confirmed, has an `implements` member, tested-or-`test_exempt`, no open
    verify-intent, not drifted vs the lock). A `layer: need` is covered by ≥1
    `satisfies:` edge instead of code and its test axis is waived, mirroring how
    `check` treats the need layer. `--json` emits the same numbers as a
    parseable object for a CI badge. Read-only, always exit 0.

    `gate_errors`/`gate_link_sync_clean` (informational, never enters `score`):
    the count of `gate`'s own ERROR-level link-sync problems (dangling tags,
    enforced-status requirements with no `implements:` member), so a 100/100
    reading here can no longer coexist with an unseen `gate` failure — see
    RM-6 (Senate run reqmap-health-gate-cleanliness). This does NOT detect a
    value changed with no tag at all; that class of drift needs a sourced/
    `validated-against:` convention on the changed file, which is out of
    scope for this signal."""
    reqs, members, reqs_dir, code_root = ws.reqs, ws.members, ws.reqs_dir, ws.code_root
    data = _health_record(reqs, members, reqs_dir)
    score, total, healthy = data["score"], data["total"], data["healthy"]
    confirmed, implemented = data["confirmed"], data["implemented"]
    tested, drafts, orphans = data["tested"], data["drafts"], data["orphans"]
    untested, open_intent = data["untested"], data["open_intent"]
    drifted, gate_errors = data["drift"], data["gate_errors"]
    reviewed_score = data.get("reviewed_score")
    reviewed_total = data.get("reviewed_total")
    # Untagged-code coverage signal (read-only): count of scannable code files
    # carrying no membership tag — code traced to no requirement. Reuses
    # _scan_untagged (ARCH-NEXT-013). Informational only: it counts FILES, not
    # requirements, so it never enters the per-requirement score, and it is
    # absent (not zero) when no code root is available, e.g. a unit-test caller.
    # implements: ARCH-COVERAGE-029
    untagged = _scan_untagged(code_root, reqs_dir) if code_root else None  # implements: REQ-COVERAGE-836
    if untagged is not None:
        data["untagged"] = len(untagged)
    # Registry-lag signal (read-only): commits since requirements/ was last
    # touched — a frozen registry while code moves ahead. Absent (not 0) when
    # unmeasurable (no git / no code root), like `untagged`. implements: ARCH-REGISTRYLAG-035
    lag = _commits_since_reqs_touch(code_root, reqs_dir) if code_root else None
    if lag is not None:
        data["commits_since_req_touch"] = lag  # implements: REQ-REGISTRYLAG-904
    # Roadmap signals (read-only): does TODO.md still track what shipped, and does every
    # section heading actually parse as a milestone. Absent (not empty) when the repo has
    # no TODO.md, so a repo that does not keep one sees nothing. implements: ARCH-ROADMAP-038
    design = _design_summary(code_root, reqs_dir) if code_root else None   # implements: REQ-DESIGN-954
    if design is not None:
        data["design_score"] = design["score"]
        data["design_files"] = design["files"]
    roadmap = _roadmap_signals(code_root) if code_root else None
    if roadmap is not None:
        behind, newest_req, unmapped = _roadmap_behind(reqs, roadmap)
        if behind:
            data["roadmap_behind"] = {"todo": roadmap["newest_milestone"],
                                      "requirements": newest_req}
        if unmapped:
            data["roadmap_unmapped"] = {"shipped": roadmap["newest_shipped"],
                                        "requirements": newest_req}
        if roadmap["unversioned_headings"]:
            data["roadmap_unversioned_headings"] = roadmap["unversioned_headings"]
    if as_badge:
        color = "brightgreen" if score == 100 else "green" if score >= 80 else "yellow" if score >= 60 else "red"
        message = "{}/{} | {}%".format(confirmed, total, score)
        # a badge cannot read "clean" while gate has link-sync errors gate itself
        # would fail on — this is the exact false-positive RM-6 closes.
        if gate_errors:
            color = "red"
            message += " | gate:{}".format(gate_errors)
        badge = {"schemaVersion": 1, "label": "requirements",
                 "message": message, "color": color}
        print(json.dumps(badge))
        return 0
    if as_json:
        print(json.dumps(data, indent=2))
        return 0
    print("Requirement health: {}/100  ({}/{} green on every axis)".format(score, healthy, total))
    if headline_only:
        # `next` opens with the score and then lists what to do about it; the component
        # breakdown below would push the actionable part off the first screen. The design
        # score rides along because it is the other half of "how is this repo doing" and
        # folding `health` into `next` had quietly dropped it from every text surface.
        if design is not None:
            print("Design OOP:         {}/100  ({}/{} source files with no candidate)".format(
                design["score"], design["clean_files"], design["files"]))
        return 0
    # Say what the headline cannot: a draft caps `score` by construction, so a low
    # reading over a draft-heavy corpus means "not reviewed yet", not "rotting".
    # Printed only when drafts actually pull the two numbers apart.
    if reviewed_score is not None:
        print("  reviewed only:      {}/100  ({}/{} confirmed, {} not confirmed yet)".format(
            reviewed_score, healthy, reviewed_total, total - reviewed_total))
    print("  confirmed:   {}/{}".format(confirmed, total))
    print("  implemented: {}/{}".format(implemented, total))
    print("  tested:      {}/{}".format(tested, total))
    print("  drafts:      {}".format(drafts))
    if orphans:     print("  orphans (confirmed, no code):     {}".format(orphans))
    if untested:    print("  untested (code, no tests):        {}".format(untested))
    if open_intent: print("  open verify-intent:               {}".format(open_intent))
    if drifted:     print("  drift (contract changed vs lock): {}".format(drifted))
    if gate_errors: print("  gate link-sync errors (not clean):{}".format(gate_errors))
    if untagged:    print("  untagged code (no requirement):   {}".format(len(untagged)))
    if lag:         print("  commits since requirements touched:{}".format(lag))
    if design is not None:
        print("  design (source files w/o candidate): {}/100  ({}/{}) — run `reqmap.py gate --design`".format(
            design["score"], design["clean_files"], design["files"]))
    if total == 0:
        print("  (no requirements yet — run `reqmap.py init` or `new`)")
    return 0


def _strip_line_tag(line):
    """Remove a reqmap membership-tag comment from a source line.

    Strips only when a comment marker (#, //, <!--) *directly opens* the tag —
    i.e. nothing but whitespace sits between the marker and the tag id. A line
    that merely mentions a tag in prose or a heading (e.g. a doc line
    `# How implements: AREA-NAME-001 tags work`, or
    `<!-- note --> ... implements: AREA-NAME-001 is required <!-- end -->`) is
    left unchanged, so `init --wipe` never truncates documentation that
    documents the tagging convention. A multi-char heading/banner marker
    (`## `, `//// `) is removed whole rather than leaving a dangling bare `#`.
    Lines with no tag are returned unchanged."""
    m = TAG_RE.search(line)
    if m is None:
        return line
    pre = line[:m.start()]
    nl = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
    cut = -1
    for marker in ("#", "//", "<!--", "/*", "--", ";"):
        idx = pre.rfind(marker)
        if marker == "--" and idx >= 2 and pre[idx - 2:idx] == "<!":
            continue   # the tail of an HTML comment opener, handled as `<!--` above
        # the marker opens the tag's comment only when the gap between the
        # marker token and the tag id is whitespace-only; otherwise it is an
        # unrelated heading / inline comment and must not anchor the cut
        if idx > cut and pre[idx + len(marker):].strip() == "":
            cut = idx
    if cut < 0:
        return line  # no comment marker directly opens the tag — leave unchanged
    # walk back over a contiguous run of the same marker char (`## `, `//// `)
    # so the whole heading/banner marker is removed, not just its last char
    while cut > 0 and pre[cut - 1] == pre[cut]:
        cut -= 1
    return line[:cut].rstrip() + nl


def _wipe(reqs_dir, code_root):
    """Hard-reset: delete non-generated requirement files (names not starting
    with `_`) and strip membership tags from every scanned source file so that
    `cmd_extract` can re-draft from a clean slate."""
    deleted = 0
    if os.path.isdir(reqs_dir):
        for fn in os.listdir(reqs_dir):
            if fn.endswith(".md") and not fn.startswith("_"):
                try:
                    os.remove(os.path.join(reqs_dir, fn))
                    deleted += 1
                except OSError:
                    pass
    stripped_files = 0
    for fp, _rel in _walk_code(code_root, reqs_dir):
        try:
            # surrogateescape (read AND write) round-trips any non-UTF-8 bytes
            # verbatim, so stripping a tag never silently corrupts e.g. a
            # Latin-1 comment elsewhere in the file (errors="ignore" dropped them).
            # newline="" on both ends: read/write the file's own line endings verbatim
            # so stripping ONE tag comment never silently normalizes the WHOLE file to
            # the host platform's os.linesep (e.g. flips an LF-committed shell hook to
            # CRLF on Windows, which breaks /bin/sh on the CR).
            with open(fp, encoding="utf-8", errors="surrogateescape", newline="") as f:
                lines = f.readlines()
            # Only the lines the SCANNER reads as tags. Cutting every TAG_RE hit
            # sliced a tag-shaped string literal in a test fixture in half
            # (`"# implements: X\n..."` -> `"`, a SyntaxError) and blanked the fenced
            # examples in every README that documents the tagging convention.
            hits = {ln for _role, _cid, ln in (_scan_file_tags(fp, lines) or [])}
            new_lines = [_strip_line_tag(l) if i in hits else l
                         for i, l in enumerate(lines, 1)]
            if new_lines != lines:
                with open(fp, "w", encoding="utf-8", errors="surrogateescape", newline="") as f:
                    f.writelines(new_lines)
                stripped_files += 1
        except OSError:
            continue
    print("wipe: deleted {} requirement file(s), stripped tags from {} source file(s).".format(
        deleted, stripped_files))


def _reqmapignore_seed(code_root, reqs_dir):  # implements: ARCH-INIT-012  # implements: REQ-INIT-860
    """Content for a freshly-seeded `.reqmapignore`. Normally ignores the vendored
    engine at `scripts/reqmap.py` — its `implements:` self-tags would otherwise read
    as dangling refs in a consumer repo. EXCEPTION — a self-hosting repo: when that
    file carries membership tags that resolve to requirements already present, the
    engine IS the managed code and must stay scanned, so the line is omitted (a
    comment explains why) to avoid orphaning those requirements."""
    header = ("# Paths reqmap should not scan (one fnmatch glob per line, # comments ok).\n"
              "# The bundled single-file viewer is a generated artifact, never a member.\n"
              "scripts/_map_viewer.html\n"
              "# Isolated agent worktrees. Each holds a FULL second copy of this repo, so a\n"
              "# local scan counts every member twice and reads the copies' tags as dangling\n"
              "# refs — errors that do not exist in the code, in files CI never checks out.\n"
              "# Both spellings: Claude Code creates `.claude/worktrees/`, older\n"
              "# parallel-session tooling `.worktrees/`.\n"
              ".worktrees/**\n"
              ".claude/worktrees/**\n")
    engine = os.path.join(code_root, "scripts", "reqmap.py")
    req_ids = set(load_requirements(reqs_dir))
    if req_ids and os.path.isfile(engine):
        try:
            with open(engine, encoding="utf-8") as f:
                tagged = {cap for (_role, cap) in _findall_tags(f.read())}   # expand comma-lists like scan_members
        except OSError:
            tagged = set()
        if tagged & req_ids:   # self-hosting: the engine's tags point at local reqs
            return (header +
                    "# scripts/reqmap.py is intentionally NOT ignored: this repo hosts its own\n"
                    "# requirements there (its membership tags resolve to local requirements), so\n"
                    "# the engine must stay scanned. Add other vendored/generated paths below.\n")
    return (header +
            "# The engine carries its own `implements:` self-tags; ignore it so the\n"
            "# gate does not flag them as dangling refs.\n"
            "scripts/reqmap.py\n")


def cmd_init(reqs_dir, code_root, wipe=False, no_site=False):  # implements: ARCH-INIT-012  # implements: REQ-INIT-861
    """First-use bootstrap for a fresh repo: create requirements/, seed a minimal
    .reqmapignore (idempotent — never clobbers an existing one), draft requirements
    from existing code, build the lock + map, then print guided next steps.
    Pass wipe=True (--wipe flag) for a hard reset: all non-generated requirement
    files are deleted and membership tags stripped from source before re-extracting."""
    created = []
    if not os.path.isdir(reqs_dir):
        os.makedirs(reqs_dir, exist_ok=True)
        created.append(os.path.relpath(reqs_dir, code_root).replace(os.sep, "/") + "/")
    # Seed the ignore file BEFORE a wipe reads it: on a fresh consumer the wipe
    # otherwise ran with no patterns and stripped the vendored engine's own tags.
    ignore = os.path.join(code_root, ".reqmapignore")
    if not os.path.exists(ignore):
        with open(ignore, "w", encoding="utf-8") as f:
            f.write(_reqmapignore_seed(code_root, reqs_dir))
        created.append(".reqmapignore")
    if wipe:
        _wipe(reqs_dir, code_root)
    print("Bootstrapping draft requirements from existing code...\n")
    cmd_extract(Workspace(load_requirements(reqs_dir),
                          scan_members(code_root, reqs_dir), reqs_dir, code_root))
    # extract wrote new files -> reload before locking + mapping
    ws = Workspace(load_requirements(reqs_dir),
                   scan_members(code_root, reqs_dir), reqs_dir, code_root)
    reqs = ws.reqs
    cmd_check(ws, update_lock=True)
    cmd_map(ws, code_root)
    # implements: ARCH-SITE-026 — best-effort project site. Never aborts init.
    if not no_site:
        target = _site_default_target(code_root)
        if target:
            try:
                _site_pages_bootstrap(os.path.dirname(target))   # .nojekyll + index.html redirect
                cmd_site(ws, code_root, attach=target, regions=["nav", "stats"])
            except Exception as e:   # site is decorative; a failure must not break bootstrap
                print("note: site step skipped ({}).".format(e))
        else:
            print("note: no docs/ folder — run the requirement-manager skill to set up a project site.")
    print("\n" + "=" * 60)
    if not reqs:   # nothing to extract — don't masquerade as "all clean"
        print("reqmap initialized, but no requirements were extracted")
        print("(no supported source files found, or all are ignored by .reqmapignore).")
        if created:
            print("created: " + ", ".join(created))
        print("\nNext: author your first requirement with `reqmap.py new AREA-NAME-NNN`.")
        return 0
    print("reqmap initialized — {} requirement(s) tracked.".format(len(reqs)))
    if created:
        print("created: " + ", ".join(created))
    print("\nNext: run `reqmap.py gate --risk` — it shows what to do, most important first.")
    print("Then wire the gate: add `python scripts/reqmap.py gate` to your pre-commit hook.")
    # `init` drafts the three rungs only for code it EXTRACTED, and it extracts only
    # untagged files (ARCH-EXTRACT-008). On a repo that already carries membership tags
    # it therefore proposes nothing and says so — which reads as "nothing to do" when the
    # truth is "this run could not reach your existing requirements". `clarify --levels`
    # is the path that can (ADR-0031); naming it here is the difference between a gap a
    # reader can close and one they never learn about.
    _unlevelled = sum(1 for r in reqs.values() if not r["meta"].get("level"))
    if _unlevelled:
        print("\nNote: {} of {} requirement(s) declare no `level:`. `init` proposes rungs "
              "only for code it extracted, and it skips files that already carry a tag, so "
              "it cannot reach those.".format(_unlevelled, len(reqs)))
        print("Run `reqmap.py clarify --levels` to see a proposed rung for each "
              "(read-only; --apply writes them, marked `level_source: auto`).")
    return 0


# The top-level `"design"` key of `_map.json`, as `json.dumps(indent=2)` writes it.
# The block closes at the first line that is exactly `  },` or `  }` — every line
# inside it is nested deeper, so the two-space indent is what ends it.
_DESIGN_BLOCK_OPEN = '  "design": {'
_DESIGN_BLOCK_CLOSE = ("  },", "  }")


def _strip_generated(text):  # implements: REQ-DESIGN-991
    """Drop volatile lines so a freshness diff compares content, not the
    environment: the `generated: <timestamp>` frontmatter line (`_map.md`) and the
    `"repo": ...` field (`_map.json`), which is git-derived and differs across
    forks/clones — comparing it would make `map --check` spuriously fail on a fork.

    The advisory design payload goes with them, and for a sharper reason than
    volatility. `_map.json` is ONE freshness-gated artifact carrying three classes of
    data with three different severities — the requirement graph (normative), `health`
    (derived) and `design` (advisory by its own contract, ARCH-DESIGN-061). The
    comparison was all-or-nothing, so anything landing in that document acquired ERROR
    severity by construction, whatever its own contract said: one blank line inserted
    into a file no requirement claims moved a `line:` number in `design.findings`,
    which made the committed map stale, which failed `gate` with zero requirement
    errors. Determinism was the wrong test for what may be gated — a freshness-checked
    payload needs STABILITY UNDER UNRELATED EDITS, and per-line findings have none.

    The data itself stays in the artifact: the viewer renders those rows in its Design
    tab. What changes is that they no longer carry a verdict. The cost, taken with eyes
    open, is that the committed design rows may lag the code until the next `sync`,
    which is the correct trade for advice nobody should be blocked by."""
    out, in_design = [], False
    for l in text.splitlines():
        if in_design:
            in_design = l not in _DESIGN_BLOCK_CLOSE
            continue
        if l == _DESIGN_BLOCK_OPEN:
            in_design = True
            continue
        if (l.startswith("generated: ")
                or l.startswith("engine: ")
                # `_map.md`'s one-line design summary: the same advisory number, and
                # the same reason it must not be able to fail a build.
                or l.startswith("design OOP: ")
                or l.lstrip().startswith('"repo":')
                or l.lstrip().startswith('"engine_version":')):
            continue
        out.append(l)
    return "\n".join(out)


_ENGINE_STAT_RE = re.compile(r'<div class="stat"><b>[^<]*</b><span>engine</span></div>')


def _strip_engine_stat(html):  # implements: ARCH-SITE-026
    """Drop the `engine` stat cell before a site STATS-region freshness diff — it
    embeds the live MAP_ENGINE_VERSION, which changes on every engine change
    independent of requirement content, mirroring the `repo`/`engine_version`
    exclusions `_strip_generated` already applies to `_map.md`/`_map.json` for the
    same reason (a routine engine bump must not flag a committed site page stale)."""
    return _ENGINE_STAT_RE.sub("", html)


def _stale_artifacts(data, reqs_dir, root=".", reqs=None):  # implements: ARCH-MAP-007  # implements: REQ-FINDINGS-856  # implements: REQ-MAP-871
    """Names of the committed generated artifacts that no longer match a fresh
    render of `data` — the whole of the freshness verdict, with no printing and no
    exit code, so `map --check` (which fails) and `gate` (which warns) read the same
    answer instead of implementing it twice."""
    stale = []
    for name, fresh in (("_map.md", _build_md_text(data)),
                        ("_map.json", _build_json_text(data))):
        path = os.path.join(reqs_dir, name)
        if not os.path.exists(path):
            continue   # nothing committed to be stale against
        with open(path, encoding="utf-8") as f:
            on_disk = f.read()
        if _strip_generated(on_disk) != _strip_generated(fresh):
            stale.append(name)
    # Committed findings report: derived from the requirements' verify-intent bullets,
    # so a committed copy goes stale exactly like _map.* does (this repo's sat stale
    # for eleven weeks). Absent = never generated = not stale, same convention.
    findings_out = os.path.join(reqs_dir, "_findings.md")  # implements: ARCH-FINDINGS-010
    if reqs is not None and os.path.exists(findings_out):
        with open(findings_out, encoding="utf-8") as f:
            on_disk = f.read()
        if on_disk != _render_findings(reqs, reqs_dir)[0]:
            stale.append("_findings.md")
    # There is no second copy of the map to check. `requirements/_map.html` is the only
    # rendered viewer the engine writes, it is regenerable from two committed inputs
    # (`_map.json` and the vendored template) and is therefore gitignored — so nothing
    # here can go stale in a commit. A published copy is built where it is published:
    # see the `deploy-map` job.
    # Site presentation page: gate the deterministic STATS region only. NAV embeds
    # the git-derived repo URL (fork-specific) and is excluded, mirroring the
    # `repo`-field exclusion in _strip_generated.  # implements: ARCH-SITE-026
    site_target = _site_default_target(root)
    if site_target and os.path.exists(site_target):
        with open(site_target, encoding="utf-8") as f:
            on_disk = f.read()
        disk_stats = _extract_region(on_disk, "stats")
        if disk_stats is not None:
            ctx = _site_context_from_data(data, repo_url=None, map_ok=False, diagram_rel=None)
            fresh_stats = _render_region("stats", ctx)
            if _strip_engine_stat(disk_stats) != _strip_engine_stat(fresh_stats):
                stale.append(os.path.basename(site_target))
    return stale


def _map_check(data, reqs_dir, root=".", reqs=None):  # implements: ARCH-MAP-007  # implements: REQ-MAP-871
    """Freshness gate: regenerate the map in memory and compare to the committed
    files. Stale (committed != freshly-built) -> exit 1 so a code/requirement edit
    that shifts the map can't be committed without regenerating it. A map that was
    never generated (file absent) is NOT stale — consumers who don't track maps pass.
    The `generated:` timestamp is ignored so an unchanged map never trips on time."""
    stale = _stale_artifacts(data, reqs_dir, root, reqs)
    if stale:
        print("FAIL  map is stale: {} — run `reqmap.py sync` and commit the result."
              .format(", ".join(stale)))
        return 1
    print("OK  map is fresh.")
    return 0


def _title(body):  # implements: ARCH-MAP-007
    """The human title from the requirement's first `# ` heading."""
    for line in body.splitlines():
        if line.strip().startswith("# "):
            return line.strip()[2:].strip()
    return ""


def _distinct_intent(body):  # implements: ARCH-MAP-007  # implements: REQ-MAP-873
    """The intent quote, but only when it says something the Contract does not.

    In the atomic form ([[ARCH-ATOMICFORM-053]]) the `>` quote IS the obligation —
    `_atomic_spans` makes the same span both the intent and the single contract
    clause. Emitting it under both names makes every surface print one sentence
    twice: the viewer draws a `Why — Intent` blockquote directly above an identical
    `Description` bullet, and `show` prints the line under the title and again under
    `Contract:`. Measured before this existed: 588 of 646 nodes, 91% of the corpus.

    Returns "" when the quote and the joined contract are the same text, so a
    consumer sees no separate intent rather than a duplicate one. The sectioned form,
    where the quote is real rationale distinct from the clauses, is unaffected."""
    intent = _first_quote(body)
    if not intent:
        return ""
    contract = " ".join(_from_any(_bullets, body, CONTRACT_LABELS)).strip()
    return "" if contract and " ".join(intent.split()) == " ".join(contract.split()) else intent


def _first_quote(body):  # implements: ARCH-MAP-007  # implements: REQ-MAP-873  # implements: REQ-SHOW-917
    """The requirement's intent: the FIRST contiguous blockquote (the WHY), joined into
    one line. A multi-line `>` WHY (a richer plain-language summary) is gathered whole,
    not truncated to its first line. Fenced code is skipped so a `>` inside a fence
    never counts."""
    out, started = [], False
    for _is_heading, line in _body_lines(body):
        s = line.strip()
        if s.startswith(">"):
            content = s.lstrip(">").strip()
            if content:
                out.append(content)
            started = True
        elif started:            # first non-quote line after the block ends it
            break
    return " ".join(out)


def _section(body, name):  # implements: ARCH-MAP-007
    """One section folded to a single line."""
    # strip only a literal one-time "- " bullet marker, not a lstrip() char class -- a
    # class-lstrip also eats real leading "-"/">" content (e.g. "- -1 means error" must
    # keep its "-1", not become "1 means error")
    return " ".join(s[2:] if s.startswith("- ") else s
                    for s in _section_lines(body, name)
                    if s and not s.startswith("<!--"))


def _section_raw(body, name):  # implements: ARCH-MAP-007
    """Like _section but preserves line breaks + indentation — used for the
    multi-line Given/When/Then acceptance blocks so they read as written."""
    return "\n".join(l for l in _section_lines(body, name, raw=True)
                     if not l.strip().startswith("<!--")).strip()


def _is_label_line(line):  # implements: ARCH-MAP-007  # implements: REQ-MAP-872
    """True when `line` is a clause-group label: a bold-only line at column 0.

    The authoring voice groups clauses under bold labels once a contract passes
    five, and those labels are headings, not prose — folding one into the bullet
    above appends the NEXT group's title to the PREVIOUS group's last clause.

    Position, not marker shape, separates a label from a wrapped clause. A label
    is written flush left; a hanging-indent continuation is indented. Shape alone
    cannot tell them apart: a wrapped line may legitimately open and close on bold
    spans, and matching that as a heading silently deleted the containment half of
    a two-part join predicate. Pass the RAW line — a stripped string makes every
    clause look flush left and collapses the section to headings."""
    return not line[:1].isspace() and re.fullmatch(r"\*\*.+\*\*", line.strip()) is not None


def _bullets(body, name):  # implements: ARCH-MAP-007  # implements: ARCH-ATOMICFORM-053  # implements: REQ-MAP-872
    if name in CONTRACT_LABELS:
        _sp = _atomic_spans(body)
        if _sp:                                    # the atomic statement is the one clause
            # strip whitespace, then only the literal ">" quote-marker chars (never a
            # "> " char class -- that would also eat a real leading ">" in the content,
            # e.g. ">100 requests/sec" losing its ">100"). Mirrors _first_quote.
            return [" ".join(l.strip().lstrip(">").strip() for l in _sp[0]).strip()]
    out, in_comment = [], False
    for line in _section_lines(body, name, raw=True):
        s = line.strip()
        # A multi-line `<!-- ... -->` is one comment, not a first line to skip and
        # then prose to fold into the previous clause (the linter's _contract_clauses
        # already read it that way; the map, `show` and `dupes` did not).
        if in_comment:
            in_comment = "-->" not in s
            continue
        if s.startswith("<!--"):
            in_comment = "-->" not in s
            continue
        if _BLOCK_SEP_RE.match(s):
            continue                          # a `---` rule separates; it is not prose
        if s == "-" or s.startswith("- "):
            # `- ` opens a clause; a bare `-flag` continuation does not (the same test
            # _contract_clauses applies, so the two readers agree)
            out.append(s[1:].strip())
        elif _is_label_line(line):
            # A clause-group label — a heading, not prose. Folding it in would append
            # the NEXT group's title to the previous group's last clause, which then
            # leaks into `show`, the map, and the dupes/search bag of words. The test
            # is positional (see _is_label_line), so an indented wrapped clause that
            # merely opens and closes on bold spans still folds below.
            continue
        elif s and out:
            # hanging-indent continuation of the current bullet — fold it back in
            # so multi-line clauses are not truncated to their first physical line.
            out[-1] = (out[-1] + " " + s).strip()
    return out


# `draft` scaffolds a prose capability with the source file's own headings listed
# under this marker as an authoring hint. Until now it printed them INSIDE
# `## Verify intent`, and they are bullets, so every heading was read back as an
# open question: a 21-draft repository reported 103 findings, 82 of them the
# tool's own hint. The scaffold now writes the hint into `## Context`; this cut
# keeps files that were drafted before that fix honest.
_VERIFY_HINT_RE = re.compile(r"authoring hint,\s*not the contract", re.I)


def _verify_bullets(body):  # implements: ARCH-FINDINGS-010  # implements: REQ-FINDINGS-853
    """The open questions in `## Verify intent` — the section's bullets, minus
    anything below a line that declares itself a non-binding authoring hint.

    The single reader every verify-intent consumer goes through (`findings`, the
    map export, `next`, `health`), so the count in the viewer, the CLI and the
    gate summary cannot disagree."""
    section = _section_raw(body, "verify intent")
    if not section:
        return []
    kept = []
    for line in section.splitlines():
        if _VERIFY_HINT_RE.search(line):
            break
        kept.append(line)
    # re-parse through _bullets so bullet shape, fences, label lines and
    # hanging-indent continuations are handled in exactly one place
    return _bullets("## Verify intent\n" + "\n".join(kept), "verify intent")


def _context_group(body, label):  # implements: ARCH-CONTEXT-048  # implements: REQ-CONTEXT-835
    """Bullets under a bold `**<label>**` sub-group inside the consolidated
    `## Context (non-binding)` section — the form `new`'s template scaffolds since
    ADR-0017, replacing the legacy per-topic `## WHAT — Notes` / `## WHERE — Current
    implementation` headings for newly-authored requirements. Reuses the existing
    bold-label grouping convention (`_is_label_line`, already used by Contract
    clause-groups) rather than inventing a second syntax. Callers try the legacy
    heading via `_bullets()` first — this is the fallback for files that never had
    one, so an old-schema requirement is completely unaffected."""
    out, in_context, in_label, fenced = [], False, False, False
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        if s.lower().startswith("## "):
            in_context = _heading_label_is(s, "context")
            in_label = False
            continue
        if not in_context:
            continue
        if _is_label_line(line):
            in_label = s.strip("*").strip().lower() == label.lower()
            continue
        if not in_label:
            continue
        if s.startswith("-"):
            out.append(s[1:].strip())
        elif s and not s.startswith("<!--") and out:
            out[-1] = (out[-1] + " " + s).strip()
    return out


# ---------- mermaid generators ----------
def _safe_id(rid):
    """Mermaid-safe node ID: replace non-alphanumeric chars with underscores."""
    return re.sub(r"[^A-Za-z0-9]", "_", rid)


def _mlabel(text):
    """Make free text safe inside a quoted Mermaid node label.

    Even inside quotes, Mermaid's parser chokes on backticks, brackets,
    braces, pipes and backslashes; under securityLevel:loose, angle
    brackets would also be rendered as HTML. Neutralize all of them.
    """
    text = text or "—"
    for a, b in (('"', "'"), ("`", "'"), ("[", "("), ("]", ")"),
                 ("{", "("), ("}", ")"), ("|", "/"), ("\\", "/"),
                 ("<", "‹"), (">", "›")):
        text = text.replace(a, b)
    return text


def _node_label(n):
    """Two-line node label: human title big, capability id small below.

    The `<br>`/`<small>` tags are added outside `_mlabel` (which would
    otherwise neutralize the angle brackets); only the title text is
    passed through the sanitizer.
    """
    title = _mlabel(n.get("title") or n["id"])
    return "{}<br><small>{}</small>".format(title, _mlabel(n["id"]))


def _area_of(rid):  # implements: ARCH-MAP-007
    """Capability 'area' = the first id segment (BUS-PATHS-001 -> BUS). Used to
    cluster a large System Map into per-area subgraphs so 40+ nodes stay legible."""
    return rid.split("-", 1)[0] or rid


def _node_area(n):  # implements: ARCH-MAP-007
    """Grouping key for a node: an explicit `area:` frontmatter field wins (lets a
    repo group e.g. several standalone capabilities under one ANALYSIS box without
    renaming ids); otherwise fall back to the id prefix."""
    return (n.get("area") or "").strip() or _area_of(n["id"])


def _grouped_areas(nodes):  # implements: ARCH-MAPDIAGRAMS-055  # implements: REQ-MAPDIAGRAMS-876
    """Order nodes into [(area_label, [node,...]), ...]: multi-node areas first
    (sorted), then one 'misc' bucket of every single-node area. Shared by the
    System / Dependency / Risk diagrams so a 40+ node map stays navigable
    (Miller 7+-2 / C4 levels — split a big diagram by meaningful boundary)."""
    areas = {}
    for n in nodes:
        areas.setdefault(_node_area(n), []).append(n)
    groups = [(a, areas[a]) for a in sorted(areas) if len(areas[a]) > 1]
    singles = [n for a in sorted(areas) if len(areas[a]) == 1 for n in areas[a]]
    if singles:
        # fold the singletons into any pre-existing real "misc" multi-node group
        # rather than appending a second ("misc", …) tuple — two subgraphs with
        # the same _safe_id would break the Mermaid render
        existing = next((i for i, (a, _) in enumerate(groups) if a == "misc"), None)
        merged = sorted(singles, key=lambda n: n["id"])
        if existing is not None:
            groups[existing] = ("misc", groups[existing][1] + merged)
        else:
            groups.append(("misc", merged))
    return groups


def _emit_area_subgraphs(lines, nodes, label_fn=None):
    """Append per-area `subgraph` blocks (singletons collapse into 'misc')."""
    label_fn = label_fn or _node_label
    sg_used = {}
    for area, ns in _grouped_areas(nodes):
        base = _safe_id(area)
        k = sg_used.get(base, 0) + 1
        sg_used[base] = k
        # suffix on collision so two areas that sanitize to the same id (my-area /
        # my_area) don't emit duplicate `subgraph` ids and break the Mermaid render
        sg = base if k == 1 else "{}_{}".format(base, k)
        lines.append('  subgraph sg_{}["{}"]'.format(sg, _mlabel(area)))
        for n in ns:
            lines.append('    {}["{}"]'.format(_safe_id(n["id"]), label_fn(n)))
        lines.append("  end")


def _bus_ids(nodes):
    return [n["id"] for n in nodes if n.get("layer") == "bus"]


def _hub_targets(data, bus_ids):
    """Bus nodes + any node with fan-in >= SYSTEM_HUB_FANIN (the hub hairball)."""
    fanin = {}
    for _src, tgt in data["edges"]:
        fanin[tgt] = fanin.get(tgt, 0) + 1
    return set(bus_ids) | {nid for nid, c in fanin.items() if c >= SYSTEM_HUB_FANIN}


def _mermaid_system(data):  # implements: ARCH-MAPDIAGRAMS-055  # implements: REQ-MAPDIAGRAMS-876
    # Per-area subgraphs + hide edges into bus/hubs (the hairball); the full graph
    # is in the Dependency Map. Bus nodes keep a thick stroke.
    lines = ["graph LR"]   # left-right fills a wide/landscape area better than top-down
    bus_ids = _bus_ids(data["nodes"])
    _emit_area_subgraphs(lines, data["nodes"])
    hubs = _hub_targets(data, bus_ids)
    for a, b in data["edges"]:
        if b not in hubs:
            lines.append("  {} --> {}".format(_safe_id(a), _safe_id(b)))
    for bid in bus_ids:
        lines.append("  style {} stroke-width:3px".format(_safe_id(bid)))
    return "\n".join(lines)


def _mermaid_hierarchy(data):  # implements: ARCH-MAPDIAGRAMS-055  # implements: REQ-MAPDIAGRAMS-875
    """The specification hierarchy: system -> architecture, over `satisfies:` edges.

    Drawn from `upstream_edges`, not `depends_on` — those are different axes, and only this
    one forms a hierarchy. The `code` level is counted, never drawn: a corpus that has split
    its clauses carries hundreds of them, and past a few hundred nodes Mermaid stops being
    something a reader can take in (or GitHub renders at all). Each grouping box shows how
    many code requirements sit under it, which is the fan-out the band judges.

    The bold-double-boxed root style keys on having no counted code children, not on the
    literal `level:` string — a corpus that collapsed `architecture` into `system` (ADR-0024)
    can carry two populations under `level: system`: root stakeholder-need nodes (no code
    children of their own; their children are other `system`-level nodes) and promoted
    grouping nodes (real code children). Levelled on `level:` alone, both would draw as
    identical bare-labelled roots and the promoted nodes would silently lose their fan-out
    annotation — this counts children instead, which reads correctly whether or not a
    consumer repo still uses a real 3-tier split."""
    levels = {n["id"]: n.get("level") for n in data["nodes"]}
    drawn = [n for n in data["nodes"] if levels.get(n["id"]) in ("system", "architecture")]
    if not drawn:
        return ""
    kids = {}
    for child, parent in data.get("upstream_edges", []):
        if levels.get(child) == "code":
            kids[parent] = kids.get(parent, 0) + 1
    lines = ["graph TD"]
    for n in drawn:
        rid = n["id"]
        is_root = kids.get(rid, 0) == 0
        label = rid if is_root else "{}<br/>{} code".format(rid, kids.get(rid, 0))
        shape = "[[{}]]" if is_root else "[{}]"
        lines.append("  {}{}".format(_safe_id(rid), shape.format(label)))
    for child, parent in data.get("upstream_edges", []):
        # both ends must be drawn: a parent with no `level:` (a corpus that adopted the
        # axis partially) is not in `drawn`, and Mermaid would mint a bare node for it
        if (levels.get(child) in ("system", "architecture")
                and levels.get(parent) in ("system", "architecture")):
            lines.append("  {} --> {}".format(_safe_id(parent), _safe_id(child)))
    for n in drawn:
        if kids.get(n["id"], 0) == 0:
            lines.append("  style {} stroke-width:3px".format(_safe_id(n["id"])))
    return "\n".join(lines)


def _mermaid_deps(data):  # implements: ARCH-MAPDIAGRAMS-055  # implements: REQ-MAPDIAGRAMS-877
    # Area-level coupling overview (C4 'container' zoom-out): one box per area, an
    # edge A->B when ANY capability in A depends on one in B. Aggregating the
    # per-capability edges here kills the bus hub hairball; the System Map keeps
    # the per-capability detail and the detail panel lists each node's deps.
    groups = _grouped_areas(data["nodes"])
    if not groups:
        return 'graph LR\n  none["(no requirements)"]'
    label_of, counts, bus_areas = {}, {}, set()
    for label, ns in groups:
        counts[label] = len(ns)
        for n in ns:
            label_of[n["id"]] = label
            if n.get("layer") == "bus":
                bus_areas.add(label)
    edges = set()
    for a, b in data["edges"]:
        la, lb = label_of.get(a), label_of.get(b)
        if la and lb and la != lb:
            edges.add((la, lb))
    # suffix on collision so two areas that sanitize to the same id (my-area /
    # my_area) don't collapse into one Mermaid node -- mirrors _emit_area_subgraphs,
    # which already guards its own sg_ ids the same way.
    id_used, id_of = {}, {}
    for label in sorted(counts):
        base = _safe_id(label)
        k = id_used.get(base, 0) + 1
        id_used[base] = k
        id_of[label] = "a_" + (base if k == 1 else "{}_{}".format(base, k))

    lines = ["graph LR"]
    for label in sorted(counts):
        lines.append('  {}["{}<br><small>{} caps</small>"]'.format(
            id_of[label], _mlabel(label), counts[label]))
    for la, lb in sorted(edges):
        lines.append("  {} --> {}".format(id_of[la], id_of[lb]))
    for label in sorted(bus_areas):
        lines.append("  style {} stroke-width:3px".format(id_of[label]))
    return "\n".join(lines)


def _mermaid_req_to_code(data):  # implements: ARCH-MAPDIAGRAMS-055  # implements: REQ-MAPDIAGRAMS-877
    lines = ["graph LR"]
    loc_sid, sid_used = {}, {}        # distinct file:line locs must get distinct node ids
    for n in data["nodes"]:
        if n.get("level") == "code":
            # Counted, never drawn, like the hierarchy: a corpus with its behaviour
            # groups split out carries hundreds of code-level nodes and their members
            # at function granularity — the block passed 83,000 characters, past what
            # GitHub renders. The viewer has that detail; this diagram is the overview.
            continue
        rid = n["id"]
        sid = _safe_id(rid)
        lines.append('  {}["{}"]'.format(sid, _node_label(n)))
        if not n["members"]:
            # enforced-but-unlinked is a real gap (red); a baseline/draft not yet
            # tagged is expected, so render it muted grey rather than alarming red
            if n.get("status") in ENFORCED:
                lines.append("  style {} fill:#fee,stroke:#c66".format(sid))
            else:
                lines.append("  style {} fill:#eee,stroke:#bbb,color:#888".format(sid))
            continue
        # group by role+file, compute min/max line numbers
        groups = {}
        for m in n["members"]:
            c = m["loc"].rfind(":")
            f, ln = m["loc"][:c], int(m["loc"][c + 1:])
            k = m["role"] + "|" + f
            if k not in groups:
                groups[k] = {"role": m["role"], "f": f, "min": ln, "max": ln}
            else:
                groups[k]["min"] = min(groups[k]["min"], ln)
                groups[k]["max"] = max(groups[k]["max"], ln)
        for g in groups.values():
            loc = "{}:{}".format(g["f"], g["min"]) if g["min"] == g["max"] \
                  else "{}:{}-{}".format(g["f"], g["min"], g["max"])
            if loc in loc_sid:
                file_sid = loc_sid[loc]
            else:
                base = "f_" + re.sub(r"[^A-Za-z0-9]", "_", loc)
                k = sid_used.get(base, 0) + 1
                sid_used[base] = k
                # suffix on collision so two different locs that sanitize to the same
                # id (e.g. a-b.py vs a_b.py) don't merge into one mislabeled node
                file_sid = base if k == 1 else "{}_{}".format(base, k)
                loc_sid[loc] = file_sid
            lines.append('  {}["{}"]'.format(file_sid, _mlabel(loc)))
            lines.append("  {} -->|{}| {}".format(sid, g["role"], file_sid))
    return "\n".join(lines)


def _member_roles(members):
    """Roles of a node's members, tolerant of both member shapes in play: the raw
    scan tuples (role, file, line) used by cmd_check and the {role, loc}
    dicts attached to map data nodes."""
    roles = []
    for m in members or []:
        if isinstance(m, dict):
            roles.append(m.get("role"))
        elif isinstance(m, (list, tuple)) and m:
            roles.append(m[0])
    return roles


def _risk_signals(node):
    signals = []
    # 'unimplemented' must mirror the gate, which errors when an ENFORCED requirement
    # has no `implements:` member (a `tested-by`-only member must not satisfy it).
    # Keying on the implements ROLE (not raw member-list emptiness) keeps next/show/
    # the Risk map agreeing with `check`. A `layer: need` is satisfied-by other
    # requirements, not implemented by code, so the gate exempts it (ARCH-TRACE-020) —
    # mirror that here, else the Risk/Problems views flag a passing gate as failing.
    roles = _member_roles(node.get("members"))
    if node["status"] in ENFORCED and "implements" not in roles and not _impl_exempt(node):
        signals.append("unimplemented")
    if node["status"] in ("draft", "baseline"):
        signals.append("unreviewed")
    # implemented-but-untested: has hand-written code linked but no acceptance test.
    # Gated on an implements member so not-yet-built drafts (already 'unreviewed')
    # are not double-flagged. Opt out per requirement with `test_exempt: <reason>`.
    if "implements" in roles and "tested-by" not in roles and not node.get("test_exempt"):
        signals.append("untested")
    # open verify-intent questions reconstructed from code — surface them on the map,
    # not just in the detail panel / _findings.md. Mirror collect_findings: a "None —"
    # placeholder bullet is not an open finding. A *draft* is suppressed here: its
    # intent questions are subsumed by 'unreviewed' (the whole draft is unreviewed),
    # and every auto-extracted draft carries a template verify TODO — flagging both
    # would double-count every draft. Re-surfaces once promoted past draft. This
    # rule lives in the shared signal source so `next` and the Risk tab agree.
    if node["status"] != "draft" and any(
            b and not b.lstrip("*_ ").lower().startswith("none") for b in (node.get("verify") or [])):
        signals.append("unverified-intent")
    return signals


def _mermaid_risk(data):  # implements: ARCH-MAPDIAGRAMS-055  # implements: REQ-MAPDIAGRAMS-878
    risky = [(n, _risk_signals(n)) for n in data["nodes"]]
    risky = [(n, s) for n, s in risky if s]

    lines = ["graph LR"]
    if not risky:
        lines.append('  ok["No risk signals detected"]')
        return "\n".join(lines)

    # Grouped by area, colored by signal, NO edges — Risk answers "which
    # capabilities need attention", not topology (the Dependency Map has edges).
    sigs_by = {n["id"]: s for n, s in risky}
    _emit_area_subgraphs(lines, [n for n, _ in risky],
                         label_fn=lambda n: _node_label(n) + "<br>" + ", ".join(sigs_by[n["id"]]))
    for n, sigs in risky:
        sid = _safe_id(n["id"])
        if "unimplemented" in sigs:
            lines.append("  style {} fill:#fee,stroke:#c00,color:#900".format(sid))
        elif "unreviewed" in sigs:
            lines.append("  style {} fill:#fff3cd,stroke:#a66,color:#630".format(sid))
        else:
            lines.append("  style {} fill:#fff9c4,stroke:#aa0,color:#550".format(sid))
    return "\n".join(lines)


# Per-tab legends (parallel to the 5 diagrams emitted by _build_md_text, same
# order) so each view is self-explanatory. HTML uses colored swatches; markdown
# uses words.
_LEGEND_MD = [
    "The spec hierarchy: system needs -> architecture requirements (`satisfies:`), each box showing how many code-level requirements sit under it. The code level itself is counted, not drawn.",
    "Capabilities grouped by area; thick border = bus; arrows = `depends_on`. Edges into the bus/hubs are hidden (the Dependency Map shows area-level coupling).",
    "Each system/architecture requirement → its code; arrow label = role (`implements` / `tested-by`). Red = confirmed but no code linked (a gap); grey = baseline/draft, not linked yet (expected). Code-level requirements are omitted here (see the viewer).",
    "Area-level coupling: one box per area (N caps), arrow A->B = some capability in A depends on one in B. The System Map has the per-capability detail.",
    "Requirements needing attention: red = unimplemented (confirmed, no code); orange = unreviewed (promote after review); yellow = untested (implemented but no tested-by — set `test_exempt` to silence), or unverified-intent (open verify-intent question).",
]


def _build_md_text(data):  # implements: ARCH-MAPDIAGRAMS-055  # implements: REQ-MAPDIAGRAMS-874
    from datetime import datetime

    dep_count = {n["id"]: 0 for n in data["nodes"]}
    for _, b in data["edges"]:
        dep_count[b] = dep_count.get(b, 0) + 1

    diagrams = [
        ("Specification Hierarchy", _mermaid_hierarchy(data)),
        ("System Map",          _mermaid_system(data)),
        ("Requirement-to-Code", _mermaid_req_to_code(data)),
        ("Dependency Map",      _mermaid_deps(data)),
        ("Risk & Unknowns",     _mermaid_risk(data)),
    ]

    lines = [
        "---",
        # The header is derived from content only. It used to carry a wall-clock
        # timestamp, which rewrote one line on every regeneration: two branches that
        # produced an identical graph still conflicted here, and the resolution was
        # always "regenerate", never "merge". Git already records when.
        "generated: {}".format(datetime.now().strftime("%Y-%m-%d")),
        "engine: {}".format(MAP_ENGINE_VERSION),
        "nodes: {}".format(len(data["nodes"])),
        "edges: {}".format(len(data["edges"])),
    ] + (["design OOP: {}/100 ({}/{} source files without a design candidate)".format(
        data["design"]["score"], data["design"]["clean_files"], data["design"]["files"])]
         if data.get("design") else []) + [
        "---",
        "",
        "# Requirement Map",
        "",
    ]
    for i, (title, diagram) in enumerate(diagrams):
        legend = _LEGEND_MD[i] if i < len(_LEGEND_MD) else ""
        lines += ["## {}".format(title), "", "_{}_".format(legend), "", "```mermaid", diagram, "```", ""]

    # risk table — each flagged requirement with its scripted recommendation
    risk_rows = []
    for n in data["nodes"]:
        sigs = _risk_signals(n)
        if sigs:
            rec = " ".join(RISK_ADVICE[s] for s in sigs).replace("|", "/").replace("\n", " ")
            risk_rows.append((n["id"], n["status"],
                              len(n["members"]), dep_count.get(n["id"], 0),
                              ", ".join(sigs), rec))
    if risk_rows:
        lines += [
            "### Risk Table", "",
            "| ID | status | members | dependents | risks | recommendation |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for row in risk_rows:
            lines.append("| {} | {} | {} | {} | {} | {} |".format(*row))
        lines.append("")

    return "\n".join(lines)


def render_md(data, reqs_dir):  # implements: ARCH-MAPDIAGRAMS-055  # implements: REQ-MAPDIAGRAMS-874
    """Write `_map.md`, the four Mermaid diagrams that render without JavaScript."""
    out = os.path.join(reqs_dir, "_map.md")
    os.makedirs(reqs_dir, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(_utf8_safe(_build_md_text(data)))
    return out


def _repo_name(root):  # implements: ARCH-MAP-007  # implements: REQ-MAP-871
    """Best-effort `owner/repo` (else the repo directory name) identifying the
    project this map describes, for display in the viewer header. Tries the git
    `remote.origin.url`, then the directory name; returns None when nothing
    resolves. Never raises and never blocks map generation — git may be absent or
    the tree may not be a checkout. Environment-derived (it differs across forks
    and clones), so it is excluded from the `map --check` freshness diff (see
    `_strip_generated`).

    `REQMAP_REPO` env var overrides the derived value: set it to a public-facing
    slug (e.g. on a private dev repo that publishes elsewhere, so the inlined
    `repo` never leaks the dev remote), or to "" to emit no repo at all."""
    override = os.environ.get("REQMAP_REPO")
    if override is not None:
        return override or None
    url = _git_remote_url(root)
    if url:
        slug = url[:-4] if url.endswith(".git") else url
        parts = [p for p in re.split(r"[:/]", slug.rstrip("/")) if p]
        if len(parts) >= 2:
            return "/".join(parts[-2:])
    return os.path.basename(os.path.abspath(root)) or None


def _normalise_remote(url):  # implements: ARCH-SITE-026
    """Normalise a git remote URL to a https web URL (https://host/owner/repo),
    or None when empty/unparseable. Handles scp-style (git@host:owner/repo.git),
    ssh:// and https:// forms; strips a trailing `.git`. Pure string work."""
    url = (url or "").strip()
    if not url:
        return None
    if url.endswith(".git"):
        url = url[:-4]
    m = re.match(r"^[\w.+-]+@([\w.-]+):(.+)$", url)          # scp-style
    if m:
        return "https://{}/{}".format(m.group(1), m.group(2))
    # optional :port (corporate / self-hosted ssh remotes) is dropped, keeping
    # group(1)=host and group(2)=path so the web URL stays clickable
    m = re.match(r"^(?:ssh|git|https?)://(?:[^@/]+@)?([\w.-]+)(?::\d+)?/(.+)$", url)
    if m:
        return "https://{}/{}".format(m.group(1), m.group(2))
    return url if "://" in url else None


def _git_remote_web_url(root):  # implements: ARCH-SITE-026
    """The project's web URL from git `remote.origin.url`, or None when git is
    absent / no remote / not a checkout. Honours the REQMAP_REPO override (a
    bare slug becomes https://github.com/<slug>; empty disables). Never raises."""
    override = os.environ.get("REQMAP_REPO")
    if override is not None:
        if not override:
            return None
        return override if "://" in override else "https://github.com/" + override
    url = _git_remote_url(root)
    return _normalise_remote(url)


SITE_REGIONS = ("nav", "stats")  # implements: ARCH-SITE-026  (commands/layers deferred to a follow-up)


def _region_markers(name):  # implements: ARCH-SITE-026
    key = name.upper()
    return "<!--##REQMAP:{}##-->".format(key), "<!--##/REQMAP:{}##-->".format(key)


def _inject_region(html, name, inner, anchor="<body>"):  # implements: ARCH-SITE-026  # implements: REQ-SITE-924
    """Replace the content between the paired markers for `name` with `inner`
    (idempotent). Markers absent -> insert a fresh marked block right after the
    first `anchor`; anchor absent too -> append. Only the marked block is
    written; surrounding (authored) bytes are untouched."""
    open_m, close_m = _region_markers(name)
    block = open_m + "\n" + inner + "\n" + close_m
    # find the close that belongs to THIS open (search after it) so a stray close
    # before the open isn't mistaken for the region end, which would append a
    # duplicate block on re-run instead of rewriting in place
    i = html.find(open_m)
    j = html.find(close_m, i + len(open_m)) if i != -1 else -1
    if i != -1 and j != -1:
        return html[:i] + block + html[j + len(close_m):]
    # `<body class="...">` is still the body tag: a literal find appended the
    # block after `</html>` on any authored page whose body carries attributes
    m = (re.search(r"<body\b[^>]*>", html, re.I) if anchor == "<body>" else None)
    a = m.end() if m else html.find(anchor)
    if a != -1:
        a += 0 if m else len(anchor)
        return html[:a] + "\n" + block + html[a:]
    return html + "\n" + block


def _extract_region(html, name):  # implements: ARCH-SITE-026
    """Inner text between the paired markers for `name`, or None when absent.
    Lets the freshness gate diff only engine-owned regions (prose is exempt)."""
    open_m, close_m = _region_markers(name)
    i = html.find(open_m)
    if i == -1:
        return None
    i += len(open_m)
    j = html.find(close_m, i)
    return html[i:j].strip("\n") if j != -1 else None


def _html_escape(s):  # implements: ARCH-SITE-026
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _site_context_from_data(data, repo_url, map_ok, diagram_rel):  # implements: ARCH-SITE-026
    """Deterministic region inputs derived from the map graph + already-resolved
    link facts. No wall-clock, no filesystem here — callers resolve repo_url /
    map_ok / diagram_rel, so a re-run with no change reproduces byte-identically."""
    nodes = data.get("nodes", [])
    layers = {n.get("layer", "feature") for n in nodes}
    return {
        "repo_url": repo_url,
        "map_ok": map_ok,
        "diagram_rel": diagram_rel,
        "counts": {
            "requirements": len(nodes),
            "confirmed": sum(1 for n in nodes if n.get("status") == "confirmed"),
            "layers": len(layers),
            "edges": len(data.get("edges", [])),
        },
    }


def _render_region(name, ctx):  # implements: ARCH-SITE-026  # implements: REQ-SITE-924
    """Inner HTML for an engine-owned region. NAV: plain target=_blank anchors,
    each emitted only when its target resolves (graceful degradation). STATS:
    deterministic stat cards from the graph counts + engine version."""
    if name == "nav":
        links = []
        if ctx.get("map_ok"):
            links.append('<a href="map.html" target="_blank" rel="noopener">Live Map ↗</a>')
        if ctx.get("diagram_rel"):
            links.append('<a href="{}" target="_blank" rel="noopener">Diagram ↗</a>'
                         .format(_html_escape(ctx["diagram_rel"])))
        if ctx.get("repo_url"):
            links.append('<a href="{}" target="_blank" rel="noopener">GitHub ↗</a>'
                         .format(_html_escape(ctx["repo_url"])))
        return '<nav class="nav-links">' + "".join(links) + '</nav>'
    if name == "stats":
        c = ctx["counts"]
        cells = [("requirements", c["requirements"]), ("confirmed", c["confirmed"]),
                 ("layers", c["layers"]), ("edges", c["edges"]),
                 ("engine", MAP_ENGINE_VERSION)]
        items = "".join('<div class="stat"><b>{}</b><span>{}</span></div>'.format(v, k)
                        for k, v in cells)
        return items
    return ""


# A self-contained default presentation page written by `site` scaffold mode.
# Inline (not a vendored file) so the engine stays hermetic. NAV and STATS are
# marker-delimited engine-owned regions; everything else is authored prose the
# user/skill rewrites. This template is the canonical source (the prototype that
# seeded it has been removed).
# Callers fill %%REPO_NAME%% / %%REPO_URL%% via str.replace (NOT str.format —
# the CSS contains literal braces).
SITE_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>%%REPO_NAME%% — project site</title>
<!--
  ============================================================================
  PROTOTYPE of `reqmap.py sync --attach` — HYBRID model.
    • Regions marked  <!##REQMAP:...##>  are regenerated by the engine on every
      run (nav links, stats band, commands grid, layer model) — never stale.
    • Everything else is AUTHORED prose, preserved across regenerations.
  Self-contained: no CDN, no network. Plain anchor links (no file:// iframes).
  Diagram is link-only (no builder coupling). Applies the Senate
  (2026-06-14, MODIFY) blocking conditions.
  ============================================================================
-->
<style>
  :root{
    --paper:#ECE9E1; --paper-2:#F4F2EC; --card:#FBFAF6;
    --ink:#1F1D1A; --muted:#6B655C; --line:#D9D4C8;
    --accent:#9A3B2E; --accent-2:#1F6F5C; --gate:#9A3B2E;
    --eng:#1F6F5C; --auth:#9A6700;
    --radius:12px; --maxw:980px;
  }
  *{box-sizing:border-box}
  html{scroll-behavior:smooth}
  body{
    margin:0; background:var(--paper); color:var(--ink);
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    line-height:1.55; -webkit-font-smoothing:antialiased;
  }
  a{color:inherit}
  .wrap{max-width:var(--maxw); margin:0 auto; padding:0 24px}

  /* ============ <!##REQMAP:NAV##>  engine-owned top bar ============ */
  .nav{position:sticky; top:0; z-index:20; background:rgba(236,233,225,.86);
       backdrop-filter:saturate(140%) blur(8px); border-bottom:1px solid var(--line)}
  .nav-inner{max-width:var(--maxw); margin:0 auto; padding:12px 24px;
             display:flex; align-items:center; justify-content:space-between; gap:16px}
  .brand{display:flex; align-items:center; gap:10px; font-weight:700; letter-spacing:-.01em}
  .mark{width:26px; height:26px; border-radius:7px; background:var(--accent);
        display:grid; place-items:center; color:#fff; font-size:14px; font-weight:800}
  .nav-links{display:flex; gap:6px; align-items:center; flex-wrap:wrap}
  .nav-links a{display:inline-flex; align-items:center; gap:4px; text-decoration:none;
               color:var(--ink); font-size:.9rem; font-weight:600; padding:7px 12px;
               border-radius:8px; border:1px solid transparent}
  .nav-links a:hover{background:var(--card); border-color:var(--line); color:var(--accent)}
  .arrow{font-size:.8em; opacity:.7}

  /* legend chip explaining the hybrid coloring */
  .legend{display:flex; gap:14px; align-items:center; justify-content:center;
          font-size:.74rem; color:var(--muted); padding:8px; background:var(--paper-2);
          border-bottom:1px solid var(--line)}
  .dot{display:inline-block; width:9px; height:9px; border-radius:50%; margin-right:5px; vertical-align:middle}
  .dot.eng{background:var(--eng)} .dot.auth{background:var(--auth)}

  /* region tag shown at the corner of engine/authored blocks */
  .tag{display:inline-block; font-size:.66rem; font-weight:700; letter-spacing:.04em;
       text-transform:uppercase; padding:.12rem .5rem; border-radius:999px}
  .tag.eng{color:var(--eng); background:#1F6F5C18; border:1px solid #1F6F5C40}
  .tag.auth{color:var(--auth); background:#9A670018; border:1px solid #9A670040}

  section{padding:56px 0; border-bottom:1px solid var(--line)}
  .eyebrow{font-size:.78rem; font-weight:700; letter-spacing:.08em; text-transform:uppercase; color:var(--accent); margin:0 0 10px}
  h1{font-size:clamp(2rem,5vw,3.2rem); line-height:1.05; letter-spacing:-.02em; margin:.2em 0 .3em; font-weight:800}
  h2{font-size:clamp(1.4rem,3vw,2rem); letter-spacing:-.01em; margin:0 0 .4em; font-weight:750}
  .lead{font-size:1.12rem; color:var(--muted); max-width:60ch}

  /* hero */
  .hero{padding:72px 0 60px; background:
        radial-gradient(60% 80% at 80% -10%, #9A3B2E14, transparent 60%), var(--paper)}
  .hero .cta{margin-top:26px; display:flex; gap:12px; flex-wrap:wrap}
  .btn{display:inline-flex; align-items:center; gap:6px; text-decoration:none; font-weight:650; font-size:.95rem;
       padding:.62rem 1.05rem; border-radius:9px}
  .btn.primary{background:var(--accent); color:#fff}
  .btn.primary:hover{filter:brightness(1.07)}
  .btn.ghost{background:var(--card); border:1px solid var(--line); color:var(--ink)}
  .btn.ghost:hover{border-color:var(--accent); color:var(--accent)}

  /* stats band — engine */
  .band{background:var(--paper-2)}
  .stats{display:grid; grid-template-columns:repeat(6,1fr); gap:14px; margin-top:8px}
  .stat{background:var(--card); border:1px solid var(--line); border-radius:var(--radius); padding:16px 14px; text-align:center}
  .stat b{display:block; font-size:1.7rem; font-weight:800; letter-spacing:-.02em; color:var(--ink)}
  .stat span{font-size:.74rem; color:var(--muted); text-transform:uppercase; letter-spacing:.04em}
  .src{margin-top:14px; font-size:.78rem; color:var(--muted)}
  .src code{font-family:ui-monospace,Menlo,Consolas,monospace}

  /* pillars — authored */
  .pillars{display:grid; grid-template-columns:repeat(3,1fr); gap:18px; margin-top:10px}
  .pill{background:var(--card); border:1px solid var(--line); border-radius:var(--radius); padding:20px}
  .pill h3{margin:.1em 0 .35em; font-size:1.05rem}
  .pill p{margin:0; color:var(--muted); font-size:.92rem}

  /* commands grid — engine */
  .cmds{display:grid; grid-template-columns:repeat(3,1fr); gap:12px; margin-top:10px}
  .cmd{background:var(--card); border:1px solid var(--line); border-radius:10px; padding:13px 14px}
  .cmd.gate{border-color:#9A3B2E66; box-shadow:0 0 0 1px #9A3B2E22 inset}
  .cmd code{font-family:ui-monospace,Menlo,Consolas,monospace; font-size:.85rem; font-weight:700; color:var(--accent)}
  .cmd p{margin:.35em 0 0; font-size:.82rem; color:var(--muted)}

  /* layers — engine/data */
  .layers{display:grid; grid-template-columns:repeat(3,1fr); gap:16px; margin-top:10px}
  .layer{border-radius:var(--radius); padding:18px; border:1px solid var(--line); background:var(--card)}
  .layer .l{font-family:ui-monospace,Menlo,Consolas,monospace; font-size:.78rem; font-weight:700; margin-bottom:6px}
  .layer.bus .l{color:var(--accent)} .layer.feat .l{color:var(--accent-2)} .layer.need .l{color:#6b4ea8}
  .layer h3{margin:.1em 0 .3em; font-size:1rem}
  .layer p{margin:0 0 8px; font-size:.85rem; color:var(--muted)}
  .layer .ids{font-family:ui-monospace,Menlo,Consolas,monospace; font-size:.72rem; color:var(--muted)}

  /* hybrid mechanism explainer */
  .mech pre{background:#1f1d1a; color:#e9e5db; border-radius:var(--radius); padding:18px 20px; overflow:auto; font-size:.82rem; line-height:1.5}
  .mech .c-eng{color:#7fd6bf} .mech .c-auth{color:#f0c674} .mech .c-dim{color:#9a948a}

  footer{padding:30px 0 60px; color:var(--muted); font-size:.82rem; text-align:center}
  footer code{font-family:ui-monospace,Menlo,Consolas,monospace}

  .secthead{display:flex; align-items:center; gap:10px; margin-bottom:4px}

  @media(max-width:760px){
    .stats{grid-template-columns:repeat(3,1fr)}
    .pillars,.cmds,.layers{grid-template-columns:1fr}
    .nav-links a{padding:6px 9px; font-size:.82rem}
  }
</style>
</head>
<body>

<div class="nav">
  <div class="nav-inner">
    <div class="brand"><span class="mark">R</span> %%REPO_NAME%%</div>
    <!--##REQMAP:NAV##--><!--##/REQMAP:NAV##-->
  </div>
</div>

<div class="legend">
  <span><span class="dot eng"></span>engine-generated (refreshed every run)</span>
  <span><span class="dot auth"></span>authored prose (preserved)</span>
</div>

<!-- HERO — authored -->
<header class="hero">
  <div class="wrap">
  <!-- author me -->
    <span class="tag auth">authored</span>
    <p class="eyebrow" style="margin-top:14px">Single source of truth</p>
    <h1>Keep your specs, code,<br>and intent in sync.</h1>
    <p class="lead">requirement-manager seeds one stdlib-only engine into any repo, then holds the line
      between what you <em>meant</em> to build and what the code actually does — a drift gate you run before
      every commit, a live map of every capability, and an answer to "where is this implemented?".</p>
    <div class="cta">
      <a class="btn primary" href="map.html" target="_blank" rel="noopener">Open the live map ↗</a>
      <a class="btn ghost" href="%%REPO_URL%%" target="_blank" rel="noopener">View on GitHub ↗</a>
    </div>
  </div>
</header>

<section class="band">
  <div class="wrap">
    <div class="secthead"><span class="tag eng">engine-generated</span></div>
    <p class="eyebrow">At a glance</p>
    <h2>The corpus, right now</h2>
    <div class="stats">
      <!--##REQMAP:STATS##--><!--##/REQMAP:STATS##-->
    </div>
    <p class="src">Auto-injected by <code>reqmap.py sync</code> from <code>_map.json</code> — re-computed on every run, so it never drifts.</p>
  </div>
</section>

<!-- PILLARS — authored -->
<section>
  <div class="wrap">
    <div class="secthead"><span class="tag auth">authored</span></div>
    <p class="eyebrow">Why it exists</p>
    <h2>Three jobs, one engine</h2>
    <div class="pillars">
      <div class="pill"><h3>Catch drift early</h3><p>Every code tag resolves to a real requirement; every confirmed requirement has code behind it. <code>gate</code> fails the build the moment intent and implementation diverge.</p></div>
      <div class="pill"><h3>Map the system</h3><p>One command renders the whole capability graph — system map, req→code, dependencies, risk — into a self-contained viewer you open by double-click.</p></div>
      <div class="pill"><h3>Prevent duplicates</h3><p>Before a second team re-implements an existing capability, <code>dupes</code> flags the overlapping contracts. The SSOT is the place you look first.</p></div>
    </div>
  </div>
</section>

<!--##REQMAP:COMMANDS## — engine lists the registered subcommands -->
<section class="band">
  <div class="wrap">
    <div class="secthead"><span class="tag eng">engine-generated</span></div>
    <p class="eyebrow">Surface</p>
    <h2>All 18 commands</h2>
    <div class="cmds">
      <div class="cmd gate"><code>gate</code><p>The gate. Links resolve, drift detected, test-links verified. Run before every commit + in CI.</p></div>
      <div class="cmd"><code>sync</code><p>Rescan + advance the drift baseline + regen the map (and a committed _findings.md). --accept-drift for an edited confirmed contract.</p></div>
      <div class="cmd"><code>init</code><p>First-time bootstrap: scaffold, draft from code, lock, map, next-steps. Idempotent.</p></div>
      <div class="cmd"><code>map</code><p>Generate _map.md (Mermaid) + _map.json (graph) + _map.html (viewer).</p></div>
      <div class="cmd"><code>site</code><p>Inject engine-owned regions (nav links + counts) into a presentation page. --attach/--diagram.</p></div>
      <div class="cmd"><code>next</code><p>"What should I work on?" — prioritised, actionable risk buckets.</p></div>
      <div class="cmd"><code>show &lt;ID&gt;</code><p>Consolidated dossier: contract, deps, members by role, risk.</p></div>
      <div class="cmd"><code>lint</code><p>Readability/structure check on non-draft requirements.</p></div>
      <div class="cmd"><code>dupes</code><p>Flag requirement pairs with overlapping contracts (TF-IDF).</p></div>
      <div class="cmd"><code>health</code><p>Corpus coherence score + component counts. --json for a badge.</p></div>
      <div class="cmd"><code>confirm &lt;ID&gt;</code><p>Flip a reviewed requirement to confirmed (needs a member).</p></div>
      <div class="cmd"><code>review</code><p>Emit a JSON review plan (intent/contract/acceptance) for AI-assisted quality review.</p></div>
      <div class="cmd"><code>new</code><p>Scaffold a new requirement from the built-in template.</p></div>
      <div class="cmd"><code>scan</code><p>List which code members belong to which capability.</p></div>
      <div class="cmd"><code>draft</code><p>Draft requirements from untagged legacy code + prose.</p></div>
      <div class="cmd"><code>plan</code><p>Read-only JSON extraction plan (AI-assist), writes nothing.</p></div>
      <div class="cmd"><code>findings</code><p>Aggregate open verify-intent questions into _findings.md.</p></div>
      <div class="cmd"><code>export</code><p>Emit _map.json for an external front-end. --out PATH or -.</p></div>
    </div>
  </div>
</section>
<!--##/REQMAP:COMMANDS##-->

<!--##REQMAP:LAYERS## — engine derives layers from requirement frontmatter -->
<section>
  <div class="wrap">
    <div class="secthead"><span class="tag eng">engine-generated</span></div>
    <p class="eyebrow">Layer model</p>
    <h2>Bus, feature, need, aggregate</h2>
    <div class="layers">
      <div class="layer bus"><div class="l">layer: bus</div><h3>Foundation</h3><p>High fan-in capabilities — config, parse, scan, drift. Change only behind the contract.</p><div class="ids">ARCH-PARSE-001 · ARCH-SCAN-002 · ARCH-DRIFT-003</div></div>
      <div class="layer feat"><div class="l">layer: feature</div><h3>Composed</h3><p>Built on the bus via <code>depends_on</code>; each carries its own contract, acceptance, tests.</p><div class="ids">ARCH-CHECK-006 · ARCH-MAP-007 · ARCH-INIT-012</div></div>
      <div class="layer need"><div class="l">layer: need</div><h3>Stakeholder need</h3><p>An upstream need, satisfied-by features via <code>satisfies:</code>; exempt from the code gate.</p><div class="ids">SYS-SSOT-001</div></div>
      <div class="layer need"><div class="l">layer: aggregate</div><h3>Roof</h3><p>No code of its own: its implementation is its <code>depends_on</code> requirements'. Exempt from the code gate, like a need — downward instead of upward.</p><div class="ids">—</div></div>
    </div>
  </div>
</section>
<!--##/REQMAP:LAYERS##-->

<!-- HYBRID MECHANISM — meta, explains the split -->
<section class="mech">
  <div class="wrap">
    <div class="secthead"><span class="tag auth">authored</span></div>
    <p class="eyebrow">How this page stays current</p>
    <h2>The hybrid: markers</h2>
    <p class="lead" style="margin-bottom:18px">The engine only rewrites what lives between its markers. Your prose is never touched.
      Re-run <code>reqmap.py site</code> after any change and the nav links, stats, commands, and layers refresh — the hero and narrative survive.</p>
<pre><span class="c-dim">&lt;!--##REQMAP:NAV##--&gt;</span>      <span class="c-eng">← engine: Live Map / Diagram / GitHub, from `git remote` + artifact paths</span>
   ...your logo, your wording...   <span class="c-auth">← authored, preserved</span>
<span class="c-dim">&lt;!--##/REQMAP:NAV##--&gt;</span>

<span class="c-auth">&lt;header class="hero"&gt; ... your headline + story ... &lt;/header&gt;</span>   <span class="c-auth">← authored, preserved</span>

<span class="c-dim">&lt;!--##REQMAP:STATS##--&gt;</span>    <span class="c-eng">← engine: counts from _map.json, recomputed every run</span>
<span class="c-dim">&lt;!--##REQMAP:COMMANDS##--&gt;</span> <span class="c-eng">← engine: the registered subcommands</span>
<span class="c-dim">&lt;!--##REQMAP:LAYERS##--&gt;</span>   <span class="c-eng">← engine: layers from requirement frontmatter</span></pre>
  </div>
</section>

<footer>
  Prototype of <code>reqmap.py site</code> · hybrid (engine links + data / authored prose) ·
  self-contained, no network, no <code>file://</code> iframes · Senate 2026-06-14 verdict <strong>MODIFY</strong> conditions applied.
</footer>

</body>
</html>
"""  # implements: ARCH-SITE-026


def _path_key(path):  # implements: ARCH-CHECK-006
    """Comparison key for a filesystem path: fully resolved, then case-folded.

    `abspath` is not enough where a git-derived path meets a caller-derived one.
    It normalizes separators and (with normcase) case, but leaves an 8.3 SHORT
    component alone: `C:/Users/RUNNER~1/...` from the caller and
    `C:/Users/runneradmin/...` from `git rev-parse --show-toplevel` (always long
    form) are the same directory and compare unequal. In `--since` that made every
    member fall out of the changed-set, so the gate reported a clean tree with a
    dangling tag still in it - a gate failing OPEN, silently, on Windows only.
    Found by the CI portability matrix on its first run (ARCH-PYFLOOR-040).

    realpath resolves the short form, and symlinks with it - a repo reached through
    a symlinked path hit the same mismatch on POSIX. Both sides of every comparison
    go through this one function, so resolution can never apply to just one of them.
    """
    return os.path.normcase(os.path.realpath(path))


def _since_changed_files(ref, code_root):
    """Return set of absolute paths changed since `ref`, or None on failure.

    Returns None as the fail-open signal: caller must fall back to full scan.
    """
    try:
        # core.quotepath=off: emit non-ASCII paths verbatim, not octal-escaped &
        # double-quoted — otherwise those files silently drop out of the since-set
        # and the gate falsely reports clean.
        diff = _git(["-c", "core.quotepath=off", "diff", "--name-only",
                     "{}...HEAD".format(ref)], cwd=code_root, timeout=10)
        if diff is None:
            return None
        # `git diff` emits paths relative to the repo ROOT, not to cwd. Resolve
        # the toplevel so these abspaths line up with member abspaths (which are
        # relative to code_root) even when code_root is a subdirectory of the
        # git root — otherwise the since-set and member-set never intersect and
        # the gate silently checks zero requirements. Falls back to code_root.
        root = _git_root(code_root)
        files = set()
        for line in diff.splitlines():
            line = line.strip()
            if line:
                files.add(_path_key(os.path.join(root, line)))
        return files
    except Exception:
        return None


def _utf8_safe(text):  # implements: ARCH-MAP-007  # implements: REQ-MAP-870
    """Text with any lone surrogate replaced by U+FFFD, so the write cannot fail.

    A lone surrogate has no UTF-8 encoding, so `open(..., encoding="utf-8").write()`
    raises UnicodeEncodeError and takes the whole `map` run down - and with it the
    gate's map-freshness check. It is not a theoretical input: os.walk hands back a
    filename whose bytes are not valid UTF-8 surrogate-escaped, and member paths go
    straight into the map. Losing one character beats losing the command.

    The fast path is a C-level encode that touches nothing; the per-character walk
    runs only for a string that genuinely cannot be encoded.
    """
    try:
        text.encode("utf-8")
        return text
    except UnicodeEncodeError:
        return "".join("\uFFFD" if 0xD800 <= ord(c) <= 0xDFFF else c for c in text)


def _build_json_text(data):  # implements: ARCH-MAP-007  # implements: REQ-MAP-870
    """The registry graph as a JSON string:
    {engine_version, repo, nodes, edges, upstream_edges, todos, commands[, design][, health]}.
    json.dumps neutralizes any hostile id/title/body by construction — there is
    no markup context to break out of — so no extra escaping is needed."""
    payload = {"engine_version": MAP_ENGINE_VERSION, "repo": data.get("repo"),
               "nodes": data["nodes"], "edges": data["edges"],
               # `satisfies:` edges — the specification hierarchy. Computed since
               # ARCH-TRACE-020 and, until now, discarded here: the graph carried the
               # dependency axis and dropped the level axis on the floor.
               "upstream_edges": data.get("upstream_edges", []),
               "todos": data.get("todos", []),
               # the CLI, as data: the viewer documents the verbs it was generated by
               "commands": commands_manifest()}
    if data.get("design"):                      # implements: REQ-DESIGN-954
        payload["design"] = data["design"]
    if data.get("health"):                      # implements: REQ-HEALTH-968
        payload["health"] = data["health"]
    return _utf8_safe(json.dumps(payload, indent=2, ensure_ascii=False))


def render_json(data, reqs_dir):  # implements: ARCH-MAP-007  # implements: REQ-MAP-870
    """Write `_map.json`, the registry graph the viewer and any external front-end
    read."""
    out = os.path.join(reqs_dir, "_map.json")
    os.makedirs(reqs_dir, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(_build_json_text(data))
    return out


# A pre-built, single-file React viewer ships next to this engine as
# `_map_viewer.html`. It carries the marker `<!--REQMAP_DATA-->`; the engine
# swaps that for a <script> assigning this repo's graph to window.__REQMAP_DATA__,
# producing a self-contained `_map.html` that opens by double-click (no server).
VIEWER_TEMPLATE = "_map_viewer.html"
_REQMAP_DATA_MARKER = "<!--REQMAP_DATA-->"


def _site_pages_bootstrap(docs_dir):  # implements: ARCH-SITE-026  # implements: REQ-SITE-924
    """Ensure docs/ carries a GitHub Pages signal so ARCH-PAGES-021 publishes and
    the page is servable: write .nojekyll and an index.html redirect when absent.
    Idempotent — never clobbers an existing index.html."""
    os.makedirs(docs_dir, exist_ok=True)
    nojekyll = os.path.join(docs_dir, ".nojekyll")
    if not os.path.exists(nojekyll):
        open(nojekyll, "w").close()
    index = os.path.join(docs_dir, "index.html")
    if not os.path.exists(index):
        with open(index, "w", encoding="utf-8") as f:
            f.write('<!doctype html><meta charset="utf-8">'
                    '<meta http-equiv="refresh" content="0; url=./architecture.html">'
                    '<link rel="canonical" href="./architecture.html">'
                    '<title>Project site</title>'
                    '<p>Redirecting to <a href="./architecture.html">the project site</a>…</p>\n')


def _site_diagram_ok(target_path, diagram_rel):  # implements: ARCH-SITE-026
    """True when `diagram_rel` (relative to the page's directory) names an existing
    file — so the Diagram link is emitted only when the artifact is actually there."""
    if not diagram_rel:
        return False
    return os.path.isfile(os.path.join(os.path.dirname(target_path) or ".", diagram_rel))


def _site_default_target(root):  # implements: ARCH-SITE-026
    """docs/architecture.html at the git root (so running from plugin/ still finds
    the project-root docs/), or None when there is no docs/.

    The site page is the ONE thing the engine writes into docs/. The map used to be
    copied there too; it is not any more — `requirements/_map.html` is the only
    rendered viewer, and a published copy is built where it is published."""
    git_root = _git_root(root)
    docs = os.path.join(git_root, "docs")
    return os.path.join(docs, "architecture.html") if os.path.isdir(docs) else None


def cmd_site(ws, root=".", attach=None,  # implements: REQ-SITE-924
             regions=None, diagram=None, detect=False):  # implements: ARCH-SITE-026
    """Inject engine-owned regions into a presentation page (attach mode) or write
    a default page when the target is absent (scaffold mode). Deterministic and
    headless-safe: never prompts, never raises on missing git/files. `detect`
    prints findings + the suggested command and writes nothing."""
    reqs, members = ws.reqs, ws.members
    regions = regions or ["nav"]
    data = _build_map_data(reqs, members)
    repo_url = _git_remote_web_url(root)

    if detect:
        default = _site_default_target(root)
        cands = [p for p in (default,) if p and os.path.isfile(p)]
        print("repo: {}".format(repo_url or "(no remote)"))
        print("presentation candidates: {}".format(", ".join(cands) or "(none)"))
        tgt = default or os.path.join(root, "docs", "architecture.html")
        print("suggested: reqmap sync --attach {} --regions nav,stats".format(tgt))
        return 0

    if not attach:
        print("usage: reqmap sync --attach <page.html> [--regions nav,stats] [--diagram <rel>]")
        print("   or: reqmap sync --detect")
        return 0

    map_ok = os.path.isfile(os.path.join(os.path.dirname(attach) or ".", "map.html"))
    diagram_rel = diagram if _site_diagram_ok(attach, diagram) else None
    ctx = _site_context_from_data(data, repo_url=repo_url, map_ok=map_ok, diagram_rel=diagram_rel)

    if os.path.isfile(attach):
        with open(attach, encoding="utf-8") as f:
            html = f.read()
        mode = "refreshed"
    else:                                   # scaffold mode
        os.makedirs(os.path.dirname(attach) or ".", exist_ok=True)
        # escape before substituting — a repo dir name or remote URL with < > " &
        # would otherwise break out of the title/href sinks in the scaffold template
        html = (SITE_TEMPLATE.replace("%%REPO_NAME%%", _html_escape(_repo_name(root) or "this project"))
                             .replace("%%REPO_URL%%", _html_escape(repo_url or "#")))
        mode = "scaffolded"

    for name in regions:
        if name in SITE_REGIONS:
            html = _inject_region(html, name, _render_region(name, ctx))

    with open(attach, "w", encoding="utf-8") as f:
        f.write(html)
    print("{} {} (regions: {})".format(mode, attach, ",".join(regions)))
    return 0


def _viewer_template_path():  # implements: ARCH-VIEWER-007  # implements: REQ-VIEWER-940
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), VIEWER_TEMPLATE)


def _inject_viewer(template_text, data):  # implements: ARCH-VIEWER-007  # implements: REQ-VIEWER-941
    """Replace the data marker with an inline <script> assigning the graph to
    window.__REQMAP_DATA__. Three sequences are escaped so the HTML5 parser
    never changes state mid-blob:
      `</`   → `<\\/`  prevents `</script>` from closing the element early
      `<!--` → `<\\!--` prevents entering "script data escaped" state
      `-->`  → `-\\->`  closes "script data escaped" state prematurely if unclosed
    All three are valid JS string escapes (backslash ignored for `/`, `!`, `-`)."""
    blob = (
        _build_json_text(data)
        .replace("</", "<\\/")
        .replace("<!--", "<\\!--")
        .replace("-->", "-\\->")
        # U+2028/U+2029 are LINE TERMINATORS in JavaScript but ordinary characters
        # in JSON, so ensure_ascii=False emits them raw and any engine older than
        # ES2019 reads the blob as an unterminated string - one character in one
        # requirement title kills the whole viewer. The escaped forms are valid JSON
        # for the same characters, so the parsed value is unchanged.
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
    script = "<script>window.__REQMAP_DATA__=" + blob + ";</script>"
    return template_text.replace(_REQMAP_DATA_MARKER, script, 1)


def render_html(data, reqs_dir):  # implements: ARCH-VIEWER-007  # implements: REQ-VIEWER-940
    """Write the self-contained viewer `_map.html` by injecting `data` into the
    vendored template. Returns the path, or None when no template is present
    (the engine still emits _map.md + _map.json — the viewer is optional)."""
    tpl = _viewer_template_path()
    if not os.path.exists(tpl):
        return None
    with open(tpl, encoding="utf-8") as f:
        template_text = f.read()
    out = os.path.join(reqs_dir, "_map.html")
    os.makedirs(reqs_dir, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(_inject_viewer(template_text, data))
    return out


# A test function's own NAME — never its class, never its parameter list. Both mislead:
# a class `TestCiUploadSiDosar` carries the tokens of TWO requirements, so every test
# inside it looked like it belonged to both; and a fixture parameter
# (`def test_export_ac2_x(self, ctx, campaign)`) made a test look like it belonged to
# the requirement whose token happens to name the fixture.
_FUNC_DEF_RE = re.compile(r"^[ \t]*(?:async\s+)?(?:def|function|func)\s+([A-Za-z_]\w*)\s*\(")
_JS_CASE_RE = re.compile(r"""^[ \t]*(?:it|test)\s*\(\s*["'`]([^"'`]{3,120})["'`]""")
_HASH_COMMENT_EXTS = (".py", ".sh", ".bash", ".rb", ".yaml", ".yml", ".tf", ".ex", ".exs", ".jl", ".pl", ".r")


def _test_functions(path):  # implements: ARCH-SUGGESTVERIFIES-047  # implements: REQ-SUGGESTVERIFIES-927
    """`[(line_no, name)]` for the test cases declared in a file: a `def`/`function`/
    `func` whose own name says "test", plus the Jest/Mocha `it("…")` label. Names only
    (see above). Returns [] for an unreadable file — a suggestion tool never raises."""
    out = []
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except OSError:
        return out
    for i, line in enumerate(lines, 1):
        m = _FUNC_DEF_RE.match(line)
        if m and "test" in m.group(1).lower():
            out.append((i, m.group(1)))
            continue
        m = _JS_CASE_RE.match(line)
        if m:
            out.append((i, m.group(1)))
    return out


def _ac_name_re(ac):  # implements: ARCH-SUGGESTVERIFIES-047  # implements: REQ-SUGGESTVERIFIES-928
    """Match `CASE-3` (or the legacy `AC-3`) inside a test name as `case3`, `case_3`,
    `ac3`, `ac_3`, `ac-3` or `ac 3` — and NOT as a prefix of `case30`, which is a
    different criterion."""
    n = ac.split("-", 1)[1]
    return re.compile(r"(?:^|[^a-z0-9])(?:case|ac)[ _-]?0*{}(?![0-9])".format(re.escape(n)), re.I)


def _comment_prefix(path):
    return "#" if path.lower().endswith(_HASH_COMMENT_EXTS) else "//"


def _verifies_proposals(reqs, members, code_root, ac_cover):  # implements: ARCH-SUGGESTVERIFIES-047  # implements: REQ-SUGGESTVERIFIES-927  # implements: REQ-SUGGESTVERIFIES-928
    """`(proposals, ambiguous)` — the machine-checkable half of "this test already
    verifies that criterion", recovered from naming.

    A proposal is made only when ALL of these hold, each rule paid for by a WRONG link
    it produced when it was missing:
      1. the test's name carries the criterion (`test_ac3_…`);
      2. the file belongs to exactly ONE requirement, OR the test name carries a token
         unique to this requirement's id — a `tested-by` file shared by four
         requirements holds four different `ac1` tests;
      3. the name carries no OTHER requirement's number — `test_ac1_083_…` sits in one
         requirement's file but verifies id 083;
      4. exactly one test matches. Two candidates are reported as ambiguous and never
         written: the tool proposes, the human confirms."""
    counts = {}
    for rid in reqs:
        for part in rid.lower().split("-"):
            counts[part] = counts.get(part, 0) + 1
    numbers = {}
    for rid in reqs:
        m = re.search(r"(\d{2,})$", rid)
        if m:
            numbers[rid] = m.group(1)
    owners = {}
    for rid, hits in members.items():
        for role, fp, _ln in hits:
            if role == "tested-by":
                owners.setdefault(fp, set()).add(rid)
    proposals, ambiguous = [], []
    for rid in sorted(reqs):
        labels = _automatable_acs(reqs[rid]["body"])
        covered = ac_cover.get(rid, {})
        missing = [ac for ac in labels if ac not in covered]
        if not missing:
            continue
        files = sorted({fp for role, fp, _ln in members.get(rid, []) if role == "tested-by"})
        tests_by_file = {fp: _test_functions(os.path.join(code_root, fp)) for fp in files}
        distinctive = [p for p in rid.lower().split("-") if counts.get(p) == 1]
        foreign = {n for other, n in numbers.items() if other != rid}
        mine = numbers.get(rid)
        for ac in missing:
            want = _ac_name_re(ac)
            hits = []
            for fp in files:
                shared = len(owners.get(fp, ())) > 1
                for ln, name in tests_by_file[fp]:
                    low = name.lower()
                    if not want.search(low):
                        continue
                    if shared and not any(d in low for d in distinctive):
                        continue
                    nums = set(re.findall(r"\d{2,}", low)) - {ac.split("-", 1)[1]}
                    if (nums & foreign) and mine not in nums:
                        continue
                    hits.append((fp, ln, name))
            if len(hits) == 1:
                proposals.append((rid, ac) + hits[0])
            elif hits:
                ambiguous.append((rid, ac, hits))
    return proposals, ambiguous


def _apply_verifies(proposals, code_root):  # implements: ARCH-SUGGESTVERIFIES-047  # implements: REQ-SUGGESTVERIFIES-929
    """Append `# verifies: <id>#AC-N` to each proposed test's declaration line.
    Returns the number of lines written. Idempotent: a line already carrying that
    exact tag is left alone."""
    by_file = {}
    for rid, ac, fp, ln, _name in proposals:
        by_file.setdefault(fp, []).append((ln, rid, ac))
    written = 0
    for fp, items in sorted(by_file.items()):
        path = os.path.join(code_root, fp)
        try:
            with open(path, encoding="utf-8", newline="") as f:
                lines = f.readlines()
        except OSError:
            print("  skipped {} (unreadable)".format(fp))
            continue
        changed = False
        for ln, rid, ac in sorted(items):
            if ln > len(lines):
                continue
            line = lines[ln - 1]
            tag = "{} {}: {}#{}".format(_comment_prefix(fp), "verifies", rid, ac)
            # Exact-tag match, not substring: `tag in line` would treat an existing
            # `...#CASE-11` as already covering a proposed `...#CASE-1` (CASE-1 is a
            # literal prefix of CASE-11), silently dropping the real, missing tag.
            if re.search(re.escape(tag) + r"(?!\d)", line):
                continue
            body, nl = line.rstrip("\r\n"), line[len(line.rstrip("\r\n")):]
            lines[ln - 1] = "{}  {}{}".format(body, tag, nl)
            changed = True
            written += 1
        if changed:
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.writelines(lines)
            print("  wrote {}".format(fp))
    return written


def cmd_suggest_verifies(ws, apply_tags=False):  # implements: ARCH-SUGGESTVERIFIES-047  # implements: REQ-SUGGESTVERIFIES-929
    """Propose `# verifies: <id>#AC-N` tags for tests already NAMED after the criterion
    they check, so a corpus can adopt per-criterion coverage without re-deriving the
    matching rules (and their three traps) by hand. Read-only unless --apply."""
    reqs, members, reqs_dir, code_root = ws.reqs, ws.members, ws.reqs_dir, ws.code_root
    ac_cover = ws.ac_cover
    if ac_cover is None:
        ac_cover = scan_ac_verifies(code_root, reqs_dir)
    proposals, ambiguous = _verifies_proposals(reqs, members, code_root, ac_cover)
    for rid, ac, fp, ln, name in proposals:
        print("{} {}\n  {}:{}  {}  -> {} {}: {}#{}".format(
            rid, ac, fp, ln, name, _comment_prefix(fp), "verifies", rid, ac))
    for rid, ac, hits in ambiguous:
        print("{} {}  AMBIGUOUS — {} candidates, none applied:".format(rid, ac, len(hits)))
        for fp, ln, name in hits:
            print("    {}:{}  {}".format(fp, ln, name))
    if not proposals and not ambiguous:
        print("no suggestions — every automatable criterion is tagged, or no test is "
              "named after one.")
        return 0
    print("\n{} proposal(s), {} ambiguous.".format(len(proposals), len(ambiguous)))
    if apply_tags and proposals:
        n = _apply_verifies(proposals, code_root)
        print("applied {} tag(s). Re-run `reqmap.py sync` to refresh the map.".format(n))
    elif proposals:
        print("re-run with --apply to write them (ambiguous ones are never written).")
    return 0


# ---------- clarify: the questions a requirement has not answered yet ----------
# Deterministic and read-only, like every other advisory surface here: it names a
# shape that is under-specified, never a defect, and never blocks. The point is the
# moment BEFORE code exists -- an author writes "the gate reports errors quickly",
# nobody asks what quickly means, and the ambiguity is discovered by the reader of
# the failing test three weeks later.
CLARIFY_HEDGES = (
    "appropriate", "appropriately", "properly", "reasonable", "reasonably", "efficient",
    "efficiently", "robust", "user-friendly", "intuitive", "quickly", "fast", "slow",
    "soon", "as needed", "if necessary", "where possible", "and/or", "etc.", "and so on",
    "optimal", "best-effort", "gracefully", "large", "small", "many", "several", "various",
)
# A case mentioning any of these is exercising a failure path. Absence of ALL of them
# across every case is the signal -- a requirement whose acceptance is pure happy path.
CLARIFY_FAILURE_WORDS = (
    "invalid", "missing", "empty", "absent", "error", "fails", "failure", "refuse",
    "refuses", "reject", "rejects", "corrupt", "malformed", "unreadable", "not found",
    "timeout", "conflict", "duplicate", "unknown", "no ", "none", "cannot", "without",
)
CLARIFY_LIMIT_WORDS = ("at most", "up to", "no more than", "maximum", "max ", "limit",
                       "capped", "bounded", "first ", "top ")
CLARIFY_UNIT_RE = re.compile(
    r"^(ms|s|sec|secs|second|seconds|min|mins|minute|minutes|hour|hours|day|days|"
    r"kb|mb|gb|b|%|percent|char|chars|character|characters|line|lines|file|files|"
    r"byte|bytes|request|requests|item|items|entry|entries|pair|pairs|clause|clauses|"
    r"criterion|criteria|px|em|rem|x)$", re.I)
# A bare number in a clause. Excluded by construction: anything glued to a word or a
# dot (`v4.0.0`, `CASE-2`, `utf-8`), because those are identifiers, not quantities.
_CLARIFY_NUM_RE = re.compile(r"(?<![\w.\-#])(\d+(?:\.\d+)?)\s*([A-Za-z%]*)")


# Every case of ARCH-SEARCH-036 described its input as prose to be matched: terms that
# match, terms that do not, terms that tokenize to nothing, more matches than --top. The
# author varied the QUALITY of one kind of input and never its KIND, so nobody asked what
# happens when the query is an id -- and the answer, for two years, was "the wrong
# requirement". A gate cannot catch that: the code did what the contract said. This asks.
CLARIFY_MONOCULTURE_MIN = 3     # cases needed before the shape means anything
CLARIFY_MONOCULTURE_SHARE = 0.75
CLARIFY_DOMAIN_SHARE = 0.10     # a Given-head this common across the corpus IS the domain
CLARIFY_DOMAIN_MIN = 30         # ...but "common across the corpus" needs a corpus to be common in
_GIVEN_RE = re.compile(r"^\s+Given\s+(.*)$", re.M)
_CLARIFY_ARTICLES = frozenset((
    "a", "an", "the", "one", "two", "three", "no", "any", "some", "its", "their",
    "new", "old", "same", "other", "first", "second", "empty", "valid", "invalid",
    "single", "confirmed", "draft", "deprecated", "stale", "fresh", "missing", "real",
))


def _given_head(text):
    """The kind of thing a Given starts from: its first word that is not an article or a
    leading adjective. Crude on purpose -- it only has to be stable across cases."""
    for w in re.findall(r"[A-Za-z_`][\w`.-]*", text.lower()):
        w = w.strip("`")
        if len(w) < 3 or w in _CLARIFY_ARTICLES:
            continue
        return w
    return ""


def _given_heads(body):
    return [h for h in (_given_head(g) for g in
                        _GIVEN_RE.findall(_from_any(_section_raw, body, ACCEPTANCE_LABELS) or ""))
            if h]


def _domain_heads(reqs):
    """Words that open Givens across the whole corpus are that corpus's subject, not a
    narrow focus: in this repository every other case starts "a requirement ...". Flagging
    those would fire on 18% of the corpus and say nothing."""
    counts = {}
    total = 0
    for r in (reqs or {}).values():
        for h in _given_heads(r["body"]):
            counts[h] = counts.get(h, 0) + 1
            total += 1
    # Below a real sample every word looks dominant: in a two-requirement corpus the one
    # noun under examination is 75% of all Given heads and would exclude itself.
    if total < CLARIFY_DOMAIN_MIN:
        return frozenset()
    return frozenset(w for w, c in counts.items() if c / float(total) >= CLARIFY_DOMAIN_SHARE)


def _clarify_questions(rid, r, reqs=None, domain=None):  # implements: ARCH-CLARIFY-062  # implements: REQ-CLARIFY-956
    """The open questions one requirement has not answered, as records:
    {rule, severity, where, quote, question, suggest}. Deterministic -- the same
    requirement always yields the same list, in the same order. `blocking` means the
    requirement cannot be implemented as written; everything else is advice.
    `domain` is `_domain_heads(reqs)`, passed in by the corpus-wide callers so it is
    read once rather than recomputed per requirement (it was 90% of a `sync`'s
    question pass, and quadratic in the corpus)."""
    body = r["body"]
    clauses = _from_any(_bullets, body, CONTRACT_LABELS)
    cases_raw = _from_any(_section_raw, body, ACCEPTANCE_LABELS) or ""
    cases_low = cases_raw.lower()
    n_cases = _count_ac(body)
    out = []

    def ask(rule, severity, where, quote, question, suggest):
        out.append({"rule": rule, "severity": severity, "where": where,
                    "quote": quote, "question": question, "suggest": suggest})

    if not clauses:
        ask("no-contract", "blocking", "Description", "",
            "What is this requirement's binding obligation? The Description carries no clause.",
            "Write one statement per obligation, present tense, naming the subject.")
    if n_cases == 0:
        ask("no-cases", "blocking", "Cases", "",
            "What observable behaviour proves this requirement holds? No labelled case is present.",
            "Add `CASE-1` with Given / When / Then, one per clause.")

    for i, c in enumerate(clauses, 1):
        low = c.lower()
        where = "clause {}".format(i)
        for w in CLARIFY_HEDGES:
            if w in low:
                ask("vague-term", "advisory", where, c,
                    'What is the measurable threshold behind "{}"?'.format(w.strip()),
                    "Replace it with a number and a unit, or with the observable condition it stands for.")
                break                                   # one hedge per clause is enough to start the conversation
        m = _CLARIFY_NUM_RE.search(c)
        if m and not CLARIFY_UNIT_RE.match(m.group(2) or ""):
            ask("number-without-unit", "advisory", where, c,
                'What unit is "{}" in?'.format(m.group(1)),
                "State the unit beside the number so a test can assert it.")
        if (" all " in " " + low or low.startswith("all ") or " every " in low or " any " in low) \
                and not any(w in low for w in CLARIFY_LIMIT_WORDS):
            ask("unbounded-quantity", "advisory", where, c,
                "Is there an upper bound, and what happens when it is reached?",
                "Name the limit, or say explicitly that there is none.")
        if low.startswith("it ") or " the system " in low:
            ask("ambiguous-actor", "advisory", where, c,
                "Who performs this -- which command or component?",
                "Name the subject the title names, so the clause reads on its own.")

    if clauses and n_cases and len(clauses) > n_cases:
        # ONE question about the gap, not one per tail clause. The count is all this
        # check knows: it compares two numbers and never reads a case to see which
        # clause it proves. Accusing clauses n_cases+1.. by position was therefore a
        # guess dressed as a finding, and a wrong one whenever an early clause is the
        # uncovered one — e.g. a clause that delegates its cases to another
        # requirement, which the counter cannot see. It sent the reader to rewrite a
        # clause that already had its case.
        gap = len(clauses) - n_cases
        ask("clause-without-case", "advisory", "Cases", "",
            "{} clause(s) have no case: there are {} clauses and {} cases. This check "
            "counts, it does not read, so it cannot say WHICH — that is the part only "
            "you can do.".format(gap, len(clauses), n_cases),
            "Walk the clauses and find the one no case proves. Add a case for it, fold "
            "it into an existing case, or move it out of the binding list if another "
            "requirement already carries its cases.")

    if n_cases and not any(w in cases_low for w in CLARIFY_FAILURE_WORDS):
        ask("no-failure-case", "advisory", "Cases", "",
            "What happens on the failure path -- missing input, invalid value, nothing to do?",
            "Add one case for the way this can go wrong; it is the case implementations skip.")

    heads = _given_heads(body)
    if len(heads) >= CLARIFY_MONOCULTURE_MIN:
        counts = {}
        for h in heads:
            counts[h] = counts.get(h, 0) + 1
        common = max(sorted(counts), key=lambda k: counts[k])
        share = counts[common] / float(len(heads))
        if domain is None:
            domain = _domain_heads(reqs)
        if share >= CLARIFY_MONOCULTURE_SHARE and common not in domain:
            ask("case-monoculture", "advisory", "Cases", "",
                'Every case starts from the same kind of input ("{}"). What is the other kind '
                'a caller would supply?'.format(common),
                "Add one case written from the caller's side, not the implementation's.")

    if len(clauses) > LINT_AC_MAX:
        ask("over-scoped", "advisory", "Description", "",
            "This requirement carries {} clauses (advisory limit {}). Which of them is a separate "
            "requirement?".format(len(clauses), LINT_AC_MAX),
            "Split the ones that could change for a different reason.")
    return out


def cmd_clarify(reqs, cap_id, as_json=False):  # implements: ARCH-CLARIFY-062  # implements: REQ-CLARIFY-957
    """Print the open questions for one requirement (or the whole corpus's blocking
    ones when no id is given). Advisory: always exit 0, writes nothing, and is never
    a gate rule -- an unanswered question is a conversation, not a build failure."""
    if cap_id and cap_id not in reqs:
        print("no requirement with id {} (expected requirements/{}.md)".format(cap_id, cap_id))
        return 1
    ids = [cap_id] if cap_id else sorted(reqs)
    items = []
    domain = _domain_heads(reqs)
    for rid in ids:
        qs = _clarify_questions(rid, reqs[rid], reqs, domain)
        if not cap_id:
            qs = [q for q in qs if q["severity"] == "blocking"]
        if qs:
            items.append({"id": rid, "title": _req_title(reqs[rid]["body"], rid), "questions": qs})
    if as_json:
        print(json.dumps({"engine_version": MAP_ENGINE_VERSION,
                          "advisory": ("Deterministic open questions. Answer them in the requirement, "
                                       "not in code; nothing here is a gate rule."),
                          "requirements": items}, indent=2, ensure_ascii=False))
        return 0
    if not items:
        print("{}: nothing unclear that this check can see.".format(cap_id or "corpus"))
        print("  next: reqmap.py gate --implement {}".format(cap_id or "<ID>"))
        return 0
    for it in items:
        blocking = [q for q in it["questions"] if q["severity"] == "blocking"]
        print("{} · {}".format(it["id"], it["title"]))
        print("{} open question(s){}".format(
            len(it["questions"]), " — {} blocking".format(len(blocking)) if blocking else ""))
        n = 0
        for sev in ("blocking", "advisory"):
            group = [q for q in it["questions"] if q["severity"] == sev]
            if not group:
                continue
            print("\n{}".format(sev.upper()))
            for q in group:
                n += 1
                print(" {:>2}. [{}] {}".format(n, q["rule"], q["where"]))
                if q["quote"]:
                    print("     \"{}\"".format(_ellipsis(q["quote"], 92)))
                print("     {}".format(q["question"]))
                print("     -> {}".format(q["suggest"]))
        print("")
    if cap_id:
        print("Answer them in {}.md, then: reqmap.py gate --implement {}".format(cap_id, cap_id))
    return 0


def _ellipsis(s, n):
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[:n - 1] + "\u2026"


# ---------- implement: the brief a coding agent needs, and nothing more ----------
def _neighbours(reqs, members, rid, k=2):  # implements: ARCH-IMPLEMENT-063  # implements: REQ-IMPLEMENT-959
    """The k requirements most similar to `rid` that already have code, by the same
    TF-IDF cosine `search` and `dupes` rank on. Similar prose almost always means
    neighbouring code, so this answers "where does this kind of thing live here?"
    without the engine knowing anything about the host project."""
    docs = {q: _sim_tokens(_sim_text(rr["body"])) for q, rr in reqs.items()}
    docs = {q: toks for q, toks in docs.items() if toks}
    if rid not in docs:
        return []
    vecs = _tfidf(docs)
    scored = []
    for other in docs:
        if other == rid or not members.get(other):
            continue
        scored.append((_cosine(vecs[rid], vecs[other]), other))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [{"id": q, "score": round(s, 3),
             "files": sorted({fp for _role, fp, _ln in members.get(q, [])})}
            for s, q in scored[:k] if s > 0]


def cmd_implement(ws, cap_id, as_json=False):  # implements: ARCH-IMPLEMENT-063  # implements: REQ-IMPLEMENT-958
    """Emit the brief for implementing one requirement in code: its obligations, its
    cases, the tags the new code must carry, where similar code already lives, and the
    command that proves the work landed. The engine writes no code -- it states the
    contract and then verifies it, which is the only half a deterministic tool can own."""
    reqs, members = ws.reqs, ws.members
    r = reqs.get(cap_id)
    if not r:
        print("no requirement with id {} (expected requirements/{}.md)".format(cap_id, cap_id))
        return 1
    body, meta = r["body"], r["meta"]
    clauses = _from_any(_bullets, body, CONTRACT_LABELS)
    cases_raw = _from_any(_section_raw, body, ACCEPTANCE_LABELS) or ""
    labels = [b["label"] for b in _acc_blocks(body) if b.get("label")]
    mem = sorted(members.get(cap_id, []))
    questions = _clarify_questions(cap_id, r, reqs)
    blocking = [q for q in questions if q["severity"] == "blocking"]
    brief = {
        "engine_version": MAP_ENGINE_VERSION,
        "id": cap_id,
        "title": _req_title(body, cap_id),
        "status": meta.get("status", "draft"),
        "level": meta.get("level", ""),
        "layer": meta.get("layer", "feature"),
        "intent": _distinct_intent(body),
        "contract": clauses,
        "cases": cases_raw,
        "case_labels": labels,
        "members": [{"role": role, "file": fp, "line": ln} for role, fp, ln in mem],
        "depends_on": _as_list(meta.get("depends_on")),
        "open_questions": questions,
        "neighbours": _neighbours(reqs, members, cap_id),
        "tags": {
            "implements": "# implements: {}".format(cap_id),
            "tested_by": "# tested-by: {}".format(cap_id),
            "verifies": ["# verifies: {}#{}".format(cap_id, lb) for lb in labels],
        },
        "verify": ["reqmap.py gate", "reqmap.py sync"],
        "contract_note": ("Write the code and the tests, carry the tags verbatim, then run verify. "
                          "Do not edit the requirement to match the code -- if the contract is wrong, "
                          "change it deliberately and run sync --accept-drift."),
    }
    if as_json:
        print(json.dumps(brief, indent=2, ensure_ascii=False))
        return 0
    print("{} · {} · {}".format(cap_id, brief["status"], brief["layer"]))
    print(brief["title"])
    if brief["intent"]:
        print("  " + brief["intent"])
    if blocking:
        print("\nBLOCKING — {} question(s) unanswered; implementing now guesses the contract:"
              .format(len(blocking)))
        for q in blocking:
            print("  - [{}] {}".format(q["rule"], q["question"]))
        print("  run: reqmap.py clarify {}".format(cap_id))
    print("\nObligations ({}):".format(len(clauses)))
    for i, c in enumerate(clauses, 1):
        print("  {}. {}".format(i, c))
    if cases_raw:
        print("\nCases:")
        for line in cases_raw.splitlines():
            print("  " + line)
    print("\nAlready implemented by ({}):".format(len(mem)))
    for role, fp, ln in mem:
        print("  {:12} {}:{}".format(role, fp, ln))
    if not mem:
        print("  (nothing yet — this is new code)")
    if brief["neighbours"]:
        print("\nSimilar requirements, for where this kind of code lives here:")
        for n in brief["neighbours"]:
            print("  {} ({:.2f})".format(n["id"], n["score"]))
            for f in n["files"][:6]:
                print("      " + f)
    print("\nTags the new code must carry:")
    print("  " + brief["tags"]["implements"] + "        (on the implementing file/function)")
    print("  " + brief["tags"]["tested_by"] + "         (on the test file)")
    for v in brief["tags"]["verifies"]:
        print("  " + v)
    if not labels:
        print("  (no labelled case — add CASE-N labels to get per-criterion coverage)")
    print("\nThen: reqmap.py gate   (and reqmap.py sync once it passes)")
    return 0


# ---------- retire: take a requirement out of service, code included ----------
def _retire_plan(reqs, members, cap_id):  # implements: ARCH-RETIRE-064  # implements: REQ-RETIRE-960
    """Everything that points at `cap_id`, computed before anything is touched:
    dependents, children, members by file, the files where it is the ONLY tagged
    requirement (whose code is now unreferenced), and its cross-references in prose.

    The blast radius is the whole point. A requirement nobody depends on is a local
    edit; one with three dependents is a conversation, and the caller is told which."""
    r = reqs.get(cap_id)
    mem = sorted(members.get(cap_id, []))
    mine = {fp for _role, fp, _ln in mem}
    others = set()
    for rid, ms in members.items():
        if rid == cap_id:
            continue
        for _role, fp, _ln in ms:
            if fp in mine:
                others.add(fp)
    refs = sorted(rid for rid, rr in reqs.items()
                  if rid != cap_id and ("[[{}]]".format(cap_id)) in rr["body"])
    # `depends_on` runs consumer -> foundation: a button declares the capability it
    # needs, never the reverse. So retiring a consumer cannot break anything downstream,
    # but it CAN stand a capability down: if this requirement was the last thing pointing
    # at one of its dependencies, that dependency now has no consumer, and its code is a
    # dead-code candidate. Nothing else in the engine notices that, because the tag is
    # still there and the gate is satisfied.
    stranded = []
    for dep in _as_list(r["meta"].get("depends_on")) if r else []:
        if dep not in reqs:
            continue
        remaining = [rid for rid, rr in reqs.items()
                     if rid != cap_id and dep in _as_list(rr["meta"].get("depends_on"))]
        if not remaining:
            stranded.append(dep)
    return {
        "id": cap_id,
        "title": _req_title(r["body"], cap_id) if r else "",
        "status": (r["meta"].get("status") if r else None),
        "path": (r.get("path") if r else None),
        "dependents": sorted(rid for rid, rr in reqs.items()
                             if cap_id in _as_list(rr["meta"].get("depends_on"))),
        "children": sorted(rid for rid, rr in reqs.items()
                           if cap_id in _as_list(rr["meta"].get("satisfies"))),
        "members": [{"role": role, "file": fp, "line": ln} for role, fp, ln in mem],
        "exclusive_files": sorted(mine - others),
        "shared_files": sorted(mine & others),
        "referenced_by": refs,
        "leaves_unused": sorted(stranded),
    }


def _retire_blockers(reqs, plan, batch=()):  # implements: REQ-RETIRE-961
    """The dependents and children that actually stand in the way.

    Two kinds never do. A `deprecated` requirement is already out of service and exempt
    from every gate, so a pointer from one cannot make a retirement unsafe. A requirement
    being retired in the same call is handled by the ORDER, not by a refusal. Without
    both filters a class of N retires in N-1 forced writes: step two is blocked by step
    one, which is itself already gone."""
    return [rid for rid in plan["dependents"] + plan["children"]
            if rid not in batch
            and (reqs[rid]["meta"].get("status") if rid in reqs else None) != "deprecated"]


def _retire_order(reqs, ids):  # implements: REQ-RETIRE-963
    """The order a batch is safe to retire in: consumers before what they consume.

    `depends_on` runs consumer -> foundation and `satisfies` runs child -> parent, so a
    requirement is safe to take out only once everything pointing AT it has gone. Kahn
    over the in-batch pointers only; input order is preserved inside a layer, and a cycle
    (which the gate reports on its own) leaves its members at the end rather than
    dropping them from the batch."""
    batch = set(ids)
    first = {rid: set() for rid in ids}      # rid -> batch members that must precede it
    for rid in ids:
        meta = reqs[rid]["meta"] if rid in reqs else {}
        for target in _as_list(meta.get("depends_on")) + _as_list(meta.get("satisfies")):
            if target in batch and target != rid:
                first[target].add(rid)
    out, done = [], set()
    while True:
        ready = [rid for rid in ids if rid not in done and not (first[rid] - done)]
        if not ready:
            break
        out.extend(ready)
        done.update(ready)
    out.extend(rid for rid in ids if rid not in done)
    return out


def _print_retire_plan(plan):  # implements: REQ-RETIRE-960
    """One requirement's blast radius, as a human reads it."""
    print("{} · {} · retire ({})".format(plan["id"], plan["status"], plan["mode"]))
    print(plan["title"])
    print("\nDepended on by: " + (", ".join(plan["dependents"]) or "(none)"))
    print("Satisfied by (children): " + (", ".join(plan["children"]) or "(none)"))
    print("Referenced in prose by: " + (", ".join(plan["referenced_by"]) or "(none)"))
    print("\nMembers in code ({}):".format(len(plan["members"])))
    for m in plan["members"]:
        print("  {:12} {}:{}".format(m["role"], m["file"], m["line"]))
    if plan["exclusive_files"]:
        print("\nFiles where this was the ONLY tagged requirement — their code is "
              "unreferenced once it goes:")
        for f in plan["exclusive_files"]:
            print("  " + f)
    if plan["shared_files"]:
        print("\nFiles shared with other requirements — only the tag line goes:")
        for f in plan["shared_files"]:
            print("  " + f)
    if plan["leaves_unused"]:
        print("\nLeft with no consumer once this goes — check whether their code is "
              "still reached:")
        for dep in plan["leaves_unused"]:
            print("  " + dep)


def cmd_retire(ws, cap_ids, delete=False, do_apply=False, force=False,
               as_json=False):  # implements: ARCH-RETIRE-064  # implements: REQ-RETIRE-961  # implements: REQ-RETIRE-963
    """Take a requirement — or a whole class of them — out of service. Without --apply
    this only reports the blast radius, so the destructive half is always preceded by a
    readable plan.

    Deprecating is the default and is reversible: the requirement stays in the corpus,
    exempt from the gates, and its code keeps working. --delete removes the block, its
    lock entries and its membership TAGS -- never a function body: deciding which code
    is now dead needs to understand the code, which this engine deliberately cannot do.
    The plan names the files where the removed tag was the only one, which is exactly
    the list a human or an agent needs for that second half.

    Many ids retire as ONE operation: one aggregated plan, one working-tree check, one
    --apply, in an order computed from the graph. A class retired one call at a time cost
    either a commit per step (the clean-tree guard) or --force on every step after the
    first (each blocked by the one already gone) — the two safeguards cancelled each
    other out on the exact case they exist for.

    `cap_ids` takes a string or a list, and a list of one behaves like the string: the
    single-requirement output and `--json` document are unchanged."""
    reqs, members, reqs_dir, code_root = ws.reqs, ws.members, ws.reqs_dir, ws.code_root
    ids = [cap_ids] if isinstance(cap_ids, str) else list(dict.fromkeys(cap_ids))
    if not ids:
        print("usage: reqmap sync --retire AREA-NAME-NNN [ID ...]")
        return 2
    single = len(ids) == 1
    unknown = [i for i in ids if i not in reqs]
    if unknown:
        for i in unknown:
            print("no requirement with id {} (expected requirements/{}.md)".format(i, i))
        return 1

    mode = "delete" if delete else "deprecate"
    order = _retire_order(reqs, ids)
    plans = []
    for cap_id in order:
        plan = _retire_plan(reqs, members, cap_id)
        plan["mode"] = mode
        plan["applied"] = False
        plan["blocked_by"] = _retire_blockers(reqs, plan, set(ids))
        plans.append(plan)

    def _emit(rc):
        if as_json:
            print(json.dumps(plans[0] if single else
                             {"mode": mode, "order": order, "plans": plans},
                             indent=2, ensure_ascii=False))
        return rc

    if not as_json:
        if not single:
            print("retire ({}) · {} requirements, in this order:".format(mode, len(order)))
            print("  " + " -> ".join(order) + "\n")
        for i, plan in enumerate(plans):
            if i:
                print("\n" + "-" * 60)
            _print_retire_plan(plan)

    blocked = [p for p in plans if p["blocked_by"]]
    if blocked and not force:
        names = sorted({b for p in blocked for b in p["blocked_by"]})
        msg = ("refusing: {} still has {} dependent(s)/child(ren) outside this retirement — "
               "{}. Retire or re-point them first, or pass --force once you have "
               "decided.".format(", ".join(p["id"] for p in blocked), len(names),
                                 ", ".join(names)))
        for plan in plans:
            plan["refused"] = msg
        if not as_json:
            print("\n" + msg)
        return _emit(1)

    if not do_apply:
        note = ("plan only — nothing was changed. Re-run with --apply to {} {}."
                .format(mode, ids[0] if single else "all {}".format(len(ids))))
        for plan in plans:
            plan["note"] = note
        if not as_json:
            print("\n" + note)
        return _emit(0)

    if not force and _git_dirty(os.path.dirname(reqs_dir) or "."):
        print("\nrefusing: the working tree has uncommitted changes. Commit or stash first so "
              "this is one reviewable diff, or pass --force.")
        return 1

    rc = 0
    for plan in plans:
        cap_id = plan["id"]
        # Re-parsed between steps: retiring one requirement rewrites the file that may
        # hold the next one, and a module file's stale block span would cut the wrong
        # lines out. Only the corpus is re-read — the code walk cannot change here.
        live = reqs if single else load_requirements(reqs_dir)
        if cap_id not in live:
            print("\n{}: already gone, skipped.".format(cap_id))
            continue
        if not delete:
            ok, msg = _apply_status(live[cap_id], "deprecated")
            print("\n" + msg)
            if not ok:
                rc = 1
                continue
            plan["applied"] = True
            if not as_json:
                print("  its code and tags are untouched; a deprecated requirement is "
                      "exempt from the gates.")
            continue
        removed_tags = _strip_member_tags(code_root or os.path.dirname(reqs_dir) or ".",
                                          plan["members"], cap_id)
        block_ok = _remove_requirement_block(live[cap_id])
        _drop_lock_entries(reqs_dir, cap_id)
        plan["applied"] = True
        plan["tags_removed"] = removed_tags
        if not as_json:
            print("\ndeleted {}: {} tag(s) stripped, requirement {}, lock entries dropped."
                  .format(cap_id, removed_tags,
                          "block removed" if block_ok else "NOT removed (see above)"))
            if plan["exclusive_files"]:
                print("  the files listed above now hold code nothing points at — "
                      "delete what is dead.")
    if not as_json:
        print("  next: reqmap.py sync")
    return _emit(rc)


def _git_dirty(root):  # implements: REQ-RETIRE-961
    """True when the working tree has uncommitted changes. Fails OPEN (False) when
    git is absent or this is not a repository: a missing safety net must not block a
    legitimate operation, and the plan was printed before this point either way."""
    return bool((_git(["status", "--porcelain"], cwd=root or ".", timeout=20) or "").strip())


_EMPTIED_COMMENT_RE = re.compile(r"[^\S\r\n]*(?:\#|//)[^\S\r\n]*(\r?\n?)$")


def _trim_emptied_comment(line):  # implements: REQ-RETIRE-962
    """Drop a comment marker the tag strip left with nothing after it.

    `x = f()  # implements: X` must come back as `x = f()`, not as `x = f()  #`. The
    marker only ever opened the comment the tag lived in, so leaving it behind litters
    every consumer file a retire touches. Anchored to end-of-line and requiring nothing
    but horizontal space after the marker, so a real trailing comment — and a second tag
    on the same line — is untouched."""
    return _EMPTIED_COMMENT_RE.sub(r"\1", line)


def _strip_member_tags(code_root, mem, cap_id):  # implements: REQ-RETIRE-962
    """Remove `# implements: <id>` / `tested-by` / `verifies` tokens for one id from
    the files that carry them. Pure text: a line that carried ONLY this tag goes; a
    line that carried other tags too keeps them. Function bodies are never touched."""
    # `code_root`, not the requirements directory's parent: a member path is relative
    # to the scan root, and `--code ..` makes those two different directories. Deriving
    # one from the other built `plugin/plugin/scripts/...` and silently stripped nothing.
    by_file = {}
    for m in mem:
        by_file.setdefault(m["file"], []).append(m["line"])
    removed = 0
    # Same left guard as TAG_RE and no `#` requirement, so a `// implements:` in a JS
    # or Go member is stripped too (it used to survive and fail the next gate as a
    # dangling tag); the right guard keeps `X-001` from eating the tag of `X-0011`.
    # The trailing run is HORIZONTAL whitespace only. `\s` matches `\n`, and these lines
    # carry their own terminator (splitlines(keepends=True)) — so a tag at the END of a
    # line of code took the newline with it and glued the next line into the comment:
    #     x = compute()  # implements: X   ->   x = compute()  #     if x:
    #     if x:                                 (the branch is now comment text)
    # Silent whenever the swallowed line happened to keep the file parseable. A tag
    # trailing a line of code is the shape SKILL.md documents, and every fixture in the
    # suite put its tag on a line of its own, which is why nothing caught it.
    tag_re = re.compile(r"(?<![\w-])(?:" + _ROLE_ALT + r"|verifies)\s*:\s*" + re.escape(cap_id) +
                        r"(?![\w-])(?:#[A-Za-z]+-\d+)?[^\S\r\n]*")
    for rel in sorted(by_file):
        path = os.path.join(code_root or ".", rel.replace("/", os.sep))
        try:
            with open(path, encoding="utf-8", newline="") as f:
                text = f.read()
        except OSError as e:
            print("  WARN  cannot read {} to strip its tag(s): {}".format(rel, e))
            continue
        lines = text.splitlines(keepends=True)
        out = []
        for line in lines:
            if not tag_re.search(line):
                out.append(line)
                continue
            removed += len(tag_re.findall(line))
            stripped = tag_re.sub("", line)
            # a line that was nothing but this tag (in whatever comment syntax) goes
            if re.fullmatch(r"[\s/*#<!\-]*", stripped.replace("\r", "").replace("\n", "")):
                continue
            out.append(_trim_emptied_comment(stripped))
        try:
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write("".join(out))
        except OSError:
            continue
    return removed


def _remove_requirement_block(r):  # implements: REQ-RETIRE-962
    """Delete one requirement from its file: the whole file when it is the only block,
    otherwise just its block, leaving every sibling byte-identical."""
    path = r["path"]
    try:
        with open(path, encoding="utf-8-sig", newline="") as f:
            raw = f.read()
    except OSError:
        return False
    eol = "\r\n" if "\r\n" in raw else "\n"
    text = raw.replace("\r\n", "\n") if eol == "\r\n" else raw
    blocks = split_requirement_blocks(text)
    if len(blocks) <= 1:
        try:
            os.remove(path)
            return True
        except OSError:
            return False
    idx = r.get("block", 0)
    if idx >= len(blocks):
        return False
    del blocks[idx]
    new_text = "".join(blocks)
    if eol == "\r\n":
        new_text = new_text.replace("\n", "\r\n")
    try:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(new_text)
        return True
    except OSError:
        return False


def _drop_lock_entries(reqs_dir, cap_id):  # implements: REQ-RETIRE-962
    """Drop the retired id from the contract lock and from the member sidecar, so the
    next gate does not carry a baseline for a requirement that no longer exists."""
    lock = load_lock(reqs_dir)
    if cap_id in lock:
        del lock[cap_id]
        save_lock(reqs_dir, lock)
    ml = load_memberlock(reqs_dir)
    if cap_id in ml:
        del ml[cap_id]
        save_memberlock(reqs_dir, ml)


def _apply_status(r, status):  # implements: REQ-RETIRE-961  # implements: REQ-PROMOTE-894
    """Rewrite one requirement's `status:` in place, preserving the file's own line
    endings and every sibling block in a module file. Returns (ok, message).

    Extracted so `confirm` and `retire` cannot drift apart on the mechanics of editing
    a requirement in a file that may hold several."""
    cur = r["meta"].get("status")
    if cur == status:
        return True, "{} is already {}.".format(r["meta"].get("id", "?"), status)
    with open(r["path"], encoding="utf-8-sig", newline="") as f:
        raw = f.read()
    orig_lines = raw.splitlines(keepends=True)
    line_eols = [ln[len(ln.rstrip("\r\n")):] for ln in orig_lines]
    eol = "\r\n" if "\r\n" in raw else "\n"
    text = raw.replace("\r\n", "\n") if eol == "\r\n" else raw
    blocks = split_requirement_blocks(text)
    if len(blocks) > 1:
        idx = r.get("block", 0)
        blocks[idx], n = _set_frontmatter_status(blocks[idx], status)
        new_text = "".join(blocks)
    else:
        new_text, n = _set_frontmatter_status(text, status)
    if n == 0:
        return False, "could not find a `status:` line in {}".format(r["path"])
    new_lines = new_text.splitlines()
    if len(new_lines) == len(line_eols):
        new_text = "".join(nl + le for nl, le in zip(new_lines, line_eols))
    elif eol == "\r\n":
        new_text = new_text.replace("\n", "\r\n")
    with open(r["path"], "w", encoding="utf-8", newline="") as f:
        f.write(new_text)
    return True, "{}: {} -> {}".format(r["meta"].get("id", "?"), cur or "(unset)", status)


# ---------------------------------------------------------------------------
# Level retrofit — implements: ARCH-LEVELRETROFIT-066
#
# ADR-0030 gives a corpus the three rungs at `init`, and only for a requirement
# `init` EXTRACTED from an untagged source file: the architecture and system rungs
# are minted from those drafts, so a repo whose files already carry tags proposes
# zero drafts and gets zero pyramid. Its requirements were authored before the axis
# existed, and no shipped command could give the axis to them.
#
# This is the explicit, human-invoked half. It reads the corpus, proposes one rung
# per requirement that declares none, prints the reason for each, and writes nothing
# without `--apply`. Every write carries `level_source: auto` (ADR-0030's marker), and
# the footprint is those two lines: delete `level:` and `level_source:` and the corpus
# reads as it did. ADR-0030's reversibility is cleaner than this one, because there the
# whole FILE was engine-written; here a field is added to a file a human wrote, which is
# exactly why the write is opt-in and marked. It is deliberately NOT reachable from
# `sync`, which the pre-commit hook runs on every commit.
# ---------------------------------------------------------------------------

def _propose_levels(reqs, members=None, ac_cover=None):  # implements: ARCH-LEVELRETROFIT-066  # implements: REQ-LEVELRETROFIT-985
    """{rid: (level, reason)} for every requirement that declares no `level:`.

    Four rules, first match wins, each carrying the sentence it will print. A
    requirement that already declares a level is absent from the result: the retrofit
    proposes onto silence and never overrules an author.

    `code` is the one rung that needs evidence rather than a default, because it is
    the rung an author reaches by DECOMPOSING a capability, not by renaming one. It
    is proposed only where the requirement already behaves like one: it has
    implementing code, at least LINT_AC_MIN labelled cases, and at least one of those
    cases linked to a test by a `# verifies:` tag. Absent that evidence the proposal
    is `architecture`, which is the honest reading of a flat corpus."""
    members = members or {}
    ac_cover = ac_cover or {}
    out = {}
    for rid in sorted(reqs):
        r = reqs[rid]
        meta = r["meta"]
        if meta.get("level"):
            continue                       # an author's declaration is never overruled
        layer = meta.get("layer", "feature")
        if layer == "need":
            out[rid] = ("system", "layer: need already says stakeholder need")
            continue
        if layer == "aggregate":
            out[rid] = ("architecture",
                        "layer: aggregate has no code of its own, covered by depends_on")
            continue
        impls = sum(1 for (role, _fp, _ln) in members.get(rid, ()) if role == "implements")
        labels = _labeled_acs(r["body"])
        covered = [ac for ac in labels if ac in (ac_cover.get(rid) or {})]
        if impls and len(labels) >= LINT_AC_MIN and covered:
            out[rid] = ("code",
                        "{} case(s), {} linked to a test, {} implementing member(s)".format(
                            len(labels), len(covered), impls))
            continue
        out[rid] = ("architecture",
                    "no decomposed-behaviour evidence ({} case(s), {} verified, {} member(s))".format(
                        len(labels), len(covered), impls))
    return out


def _insert_frontmatter_level(text, level):  # implements: ARCH-LEVELRETROFIT-066  # implements: REQ-LEVELRETROFIT-986
    """Add `level:` and `level_source: auto` to one block's frontmatter, right after
    `status:` so the field lands where the template puts it. Returns (text, n), with
    n=0 when there is no frontmatter to edit or a `level:` is already present, so the
    caller reports a miss instead of writing a corrupt file."""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return text, 0
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return text, 0
    fm = lines[1:end]
    if any(ln.startswith("level:") for ln in fm):
        return text, 0
    at = next((i for i, ln in enumerate(fm) if ln.startswith("status:")), -1)
    fm[at + 1:at + 1] = ["level: " + level, "level_source: auto"]
    return "\n".join(lines[:1] + fm + lines[end:]), 1


def _apply_level(r, level):  # implements: ARCH-LEVELRETROFIT-066  # implements: REQ-LEVELRETROFIT-986
    """Write one requirement's proposed rung into its file, preserving the file's own
    line endings and every sibling block in a module file. Returns (ok, message).

    The mechanics mirror `_apply_status` deliberately: these are the same two hazards
    — a module file holds several requirements, and a repo's files may be CRLF — and
    the two paths must not drift apart on either."""
    with open(r["path"], encoding="utf-8-sig", newline="") as f:
        raw = f.read()
    eol = "\r\n" if "\r\n" in raw else "\n"
    text = raw.replace("\r\n", "\n") if eol == "\r\n" else raw
    blocks = split_requirement_blocks(text)
    if len(blocks) > 1:
        idx = r.get("block", 0)
        blocks[idx], n = _insert_frontmatter_level(blocks[idx], level)
        new_text = "".join(blocks)
    else:
        new_text, n = _insert_frontmatter_level(text, level)
    if n == 0:
        return False, "no editable frontmatter for {} in {}".format(
            r["meta"].get("id", "?"), r["path"])
    if eol == "\r\n":
        new_text = new_text.replace("\n", "\r\n")
    with open(r["path"], "w", encoding="utf-8", newline="") as f:
        f.write(new_text)
    return True, "{}: level: {}".format(r["meta"].get("id", "?"), level)


def cmd_levels(ws, apply_it=False, only=None):  # implements: ARCH-LEVELRETROFIT-066  # implements: REQ-LEVELRETROFIT-987
    """Propose the V-model rung for every requirement that declares none.

    Read-only unless `--apply`, always exit 0, and never a gate rule. It reports the
    two things a reader has to know before adopting: what each proposal rests on, and
    that `satisfies:` edges are NOT written, because the pyramid's edges are a
    modelling decision and `depends_on` is a different axis."""
    reqs = ws.reqs
    if only and only not in reqs:
        print("no requirement with id {}".format(only))
        return 1
    scope = {only: reqs[only]} if only else reqs
    proposals = _propose_levels(scope, ws.members, ws.ac_cover)
    already = sum(1 for r in scope.values() if r["meta"].get("level"))
    if not proposals:
        print("{} of {} requirement(s) already declare a `level:` — nothing to propose.".format(
            already, len(scope)))
        return 0
    by_level = {}
    for rid, (lv, _why) in proposals.items():
        by_level.setdefault(lv, []).append(rid)
    print("Proposed rungs for {} requirement(s) that declare none ({} already declare one):\n".format(
        len(proposals), already))
    for lv in ("system", "architecture", "code"):
        for rid in by_level.get(lv, []):
            print("  {:<14} {:<26} {}".format(lv, rid, proposals[rid][1]))
    if not by_level.get("code"):
        print("\n  No requirement is proposed at `code`. That rung is one behaviour group with")
        print("  {}-{} labelled cases each linked to a test, and an author reaches it by".format(
            LINT_AC_MIN, LINT_AC_MAX))
        print("  DECOMPOSING a capability (`reqmap.py clarify <ID> --decompose`), not by renaming")
        print("  one. A two-rung corpus is a real end state, not a half-finished one.")
    print("\n  `satisfies:` edges are NOT proposed. They are the level axis and `depends_on` is")
    print("  the composition axis; deriving one from the other is the conflation the engine")
    print("  refuses to make. Add them by hand, or leave the rungs unlinked — nothing fails")
    print("  because a pyramid has no edges.")
    if not apply_it:
        print("\n  Nothing written. Re-run with --apply. The whole footprint is two lines")
        print("  per requirement, `level:` and `level_source: auto`; delete both and the")
        print("  corpus reads exactly as it does now. The file is one a human wrote, not")
        print("  one the engine created, which is why the write is opt-in and the marker")
        print("  says who put the rung there.")
        return 0
    ok = 0
    for rid in sorted(proposals):
        good, msg = _apply_level(reqs[rid], proposals[rid][0])
        print("  " + ("wrote  " if good else "SKIP   ") + msg)
        ok += 1 if good else 0
    print("\n{} requirement(s) updated. Run `reqmap.py sync` to rebuild the map, and review".format(ok))
    print("  every proposal — the engine guessed a rung from shape, which is not the same as")
    print("  knowing what the requirement is for.")
    return 0


def cmd_review(reqs, one_id=None):  # implements: ARCH-REVIEW-022  # implements: REQ-REVIEW-906
    """Emit a DETERMINISTIC, read-only review PLAN as JSON for an out-of-band AI quality
    pass. The engine never calls an LLM and writes no file — it gathers each requirement's
    prose (WHY/contract/acceptance/verify-intent) plus cheap STRUCTURAL anchors the AI
    consumer should focus on, a corpus coverage_summary, and the finding contract. The plan
    is byte-reproducible across runs; the AI findings DERIVED from it are advisory and NOT
    reproducible, and no gate path reads this output or any AI sidecar."""
    if one_id and one_id not in reqs:
        print("no requirement with id {} (expected requirements/{}.md)".format(one_id, one_id))
        return 1
    ids = [one_id] if one_id else sorted(reqs)
    items = []
    for rid in ids:
        r = reqs.get(rid)
        if not r:
            continue
        body = r["body"]
        contract = _from_any(_bullets, body, CONTRACT_LABELS)
        intent = _first_quote(body)
        ac_n = _count_ac(body)
        intent_words = len(intent.split())
        items.append({
            "id": rid,
            "title": _title(body),
            "layer": r["meta"].get("layer", "feature"),
            "status": r["meta"].get("status", "draft"),
            "intent": intent,
            "contract": contract,
            "acceptance": _from_any(_bullets, body, ACCEPTANCE_LABELS),
            "verify_intent": _bullets(body, "verify"),
            # cheap STRUCTURAL anchors (deterministic facts, NOT judgments) the AI examines:
            "anchors": {
                "contract_clauses": len(contract),
                "acceptance_count": ac_n,
                "intent_words": intent_words,
                "intent_terse": intent_words < 12,                    # WHY may merely restate the title
                "more_contract_than_acceptance": len(contract) > ac_n,  # a clause may be uncovered
            },
        })
    plan = {
        "engine_version": MAP_ENGINE_VERSION,
        "advisory": ("DETERMINISTIC read-only review plan. AI findings derived from it are ADVISORY "
                     "and NON-reproducible; they are never part of the gate and never auto-applied."),
        "categories": [
            {"key": "untestable-contract", "desc": "a contract clause so vague it cannot be verified"},
            {"key": "why-restates-title", "desc": "the WHY restates the title instead of explaining why it exists"},
            {"key": "acceptance-doesnt-cover-contract", "desc": "a contract clause with no acceptance criterion exercising it"},
        ],
        "finding_contract": ("every AI finding MUST carry a concrete suggested_rewrite; emit only "
                             "high-confidence findings; severity is advisory-only (never error/warn, never the gate)."),
        "coverage_summary": {"total_requirements": len(reqs), "requirements_in_plan": len(items)},
        "requirements": items,
    }
    print(json.dumps(plan, indent=2, ensure_ascii=False))
    return 0


# ---------- design: advisory design review of the repo's code ----------
# Reads the consumer's code and names candidates against the four OOP pillars, the
# per-class C&K metrics, plus a
# few house standards. It is advice: read-only, never part of the gate, exit 0, and a
# finding asserts a SHAPE worth a look ("these six functions share five parameters"),
# never a defect. Python is read through `ast`; the brace languages (JS/TS, C/C++,
# Java, C#, Go, Rust, Kotlin, Swift, Scala, Dart, PHP) through heuristics over the
# source with comments and strings masked out — the engine ships no parser for them
# and must stay stdlib-only. Every threshold is a CONFIG_KEYS entry.
DESIGN_FUNC_MAX_LINES = 80      # abstraction: a function longer than this is a split candidate
DESIGN_NESTING_MAX = 4          # abstraction: blocks nested deeper than this
DESIGN_PARAMS_MAX = 6           # encapsulation: a parameter list longer than this wants an object
DESIGN_CLUMP_MIN = 3            # encapsulation: this many parameters travelling together ...
DESIGN_CLUMP_FUNCS = 3          # ... through this many functions is a data clump
DESIGN_PREFIX_GROUP = 6         # abstraction: top-level functions sharing a name prefix -> namespace
DESIGN_SHARED_METHODS = 3       # inheritance: unrelated classes sharing this many method names
DESIGN_ISINSTANCE_CHAIN = 3     # polymorphism: type tests on one name in one if/else-if chain
DESIGN_BRANCH_CHAIN = 4         # polymorphism: `x == literal` branches (or switch cases) on one name
DESIGN_FILE_MAX_LINES = 500     # standards: a source file longer than this
DESIGN_LINE_MAX = 100           # standards: a physical line wider than this
DESIGN_FILE_MAX_FUNCS = 30      # standards: top-level functions/classes in one file
DESIGN_DOCSTRING_PUBLIC = 1     # standards (Python): 1 = public defs/classes need a docstring, 0 = off
# Chidamber & Kemerer, per class, Python only (see `_design_metrics` for what is absent
# and why). C&K (1994) proposed the metrics and NO thresholds; these are the conventional
# textbook numbers, and there is no primary source to cite for them. Calibrated once, on
# 65 unique classes across 7 Python corpora with an independent review of every flag —
# see REQ-DESIGN-980. Retune per repo through CONFIG_KEYS like every other threshold.
DESIGN_RFC_MAX = 50             # metrics: own methods + distinct methods it calls (C&K RFC)

DESIGN_PILLARS = ("encapsulation", "abstraction", "inheritance", "polymorphism",
                  "metrics", "standards")
# Printed whenever the metrics pillar renders, and when the review renders empty.
# An absent finding must never be readable as a measured pass on something that was
# never computed — that is the reassuring-wrong-count failure ADR-0016 rejected.
DESIGN_METRICS_SCOPE = (
    "metrics reads Python classes only and reports 1 of Chidamber & Kemerer's 6: RFC. "
    "WMC and LCOM1 were measured and dropped — across 65 classes in 7 corpora neither "
    "ever fired without RFC, and an independent review confirmed 0 of their flags. "
    "DIT, NOC and CBO are not measured, so silence says nothing about inheritance "
    "depth, subclass count or coupling. RFC is a proxy for a class that mixes "
    "toolchains; it over-reports routers, GUI callback classes and builder DSLs, whose "
    "call count is library calls rather than collaborators."
)
DESIGN_EXTS = ORPHAN_CODE_EXTS          # program-logic files; prose/config/styling are not reviewed
DESIGN_BRACE_EXTS = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".mts", ".cts", ".vue", ".svelte",
                     ".c", ".cc", ".cpp", ".h", ".hpp", ".java", ".cs", ".go", ".rs",
                     ".kt", ".kts", ".swift", ".scala", ".dart", ".php")
_DESIGN_ADVICE = {
    "global-state": "module state mutated from inside a function has no owner: hold it in an object, or pass it in and return it",
    "long-parameter-list": "a parameter list this long is an object waiting to be named: group the parameters that travel together",
    "high-response": "a class that reaches this many distinct methods is hard to test alone, because its collaborators are part of its interface: narrow them",
    "data-clump": "the same parameters travel through several functions: make them one object with those functions as methods",
    "long-function": "a function this long hides several steps: extract each step under a name that says what it does",
    "deep-nesting": "nesting this deep hides the main path: return early, or extract the inner block",
    "prefix-family": "functions sharing a prefix are a namespace: a class (or module) with that name makes the boundary explicit",
    "shared-methods": "unrelated classes with the same method names describe one interface: name a base class or protocol",
    "duplicate-method": "the same method body in two classes is one method: pull it up into a shared base",
    "isinstance-chain": "a chain of type tests dispatches by hand: give each type the method and let the call dispatch",
    "type-switch": "a chain of equality tests on one value is a dispatch table: a dict of handlers, or a method per case",
    "file-too-long": "a file this long is several modules sharing a name: split it along the prefix families it already shows",
    "line-too-long": "lines wider than the limit hide their tail in every diff and side-by-side view: wrap them",
    "missing-docstring": "a public name without a docstring makes every caller read the body: one sentence saying what it returns is enough",
    "too-many-definitions": "this many top-level definitions in one file is a package, not a module: group them",
}
_DESIGN_PILLAR_OF = {
    "global-state": "encapsulation", "long-parameter-list": "encapsulation", "data-clump": "encapsulation",
    "high-response": "metrics",
    "long-function": "abstraction", "deep-nesting": "abstraction", "prefix-family": "abstraction",
    "shared-methods": "inheritance", "duplicate-method": "inheritance",
    "isinstance-chain": "polymorphism", "type-switch": "polymorphism",
    "file-too-long": "standards", "line-too-long": "standards",
    "missing-docstring": "standards", "too-many-definitions": "standards",
}


def _design_finding(kind, rel, line, name, detail):  # implements: ARCH-DESIGN-061
    return {"pillar": _DESIGN_PILLAR_OF[kind], "kind": kind, "file": rel, "line": line,
            "name": name, "detail": detail, "advice": _DESIGN_ADVICE[kind]}


def _design_prefix(name):
    """The family token of a function name: `_scan_tags` -> `scan`, `scanTags` -> `scan`."""
    core = name.strip("_")
    if "_" in core:
        return core.split("_", 1)[0]
    m = re.match(r"[a-z]{3,}(?=[A-Z])", core)
    return m.group(0) if m else ""


# ---- shared shape checks over abstract "function" and "class" records, so the Python
# and the brace analyzers report the same kinds with the same thresholds.
# fn record: {name, line, n_lines, depth, params:[names], top:bool}
# class record: {name, line, bases:set, methods:{name: body_key}}
def _design_shape_findings(rel, fns, classes):  # implements: REQ-DESIGN-950  # implements: REQ-DESIGN-951
    out = []
    for f in fns:
        if len(f["params"]) > DESIGN_PARAMS_MAX:
            out.append(_design_finding("long-parameter-list", rel, f["line"], f["name"],
                                       "`{}` takes {} parameters (over {})".format(f["name"], len(f["params"]), DESIGN_PARAMS_MAX)))
        if f["n_lines"] > DESIGN_FUNC_MAX_LINES:
            out.append(_design_finding("long-function", rel, f["line"], f["name"],
                                       "`{}` is {} lines (over {})".format(f["name"], f["n_lines"], DESIGN_FUNC_MAX_LINES)))
        if f["depth"] > DESIGN_NESTING_MAX:
            out.append(_design_finding("deep-nesting", rel, f["line"], f["name"],
                                       "`{}` nests {} levels deep (over {})".format(f["name"], f["depth"], DESIGN_NESTING_MAX)))
    seen = set()
    plist = [(f, frozenset(f["params"])) for f in fns]
    for i in range(len(plist)):
        for j in range(i + 1, len(plist)):
            common = plist[i][1] & plist[j][1]
            if len(common) < DESIGN_CLUMP_MIN or common in seen:
                continue
            carriers = [f for f, ps in plist if common <= ps]
            if len(carriers) >= DESIGN_CLUMP_FUNCS:
                seen.add(common)
                first = min(carriers, key=lambda f: f["line"])
                out.append(_design_finding("data-clump", rel, first["line"], first["name"],
                                           "{} travel together through {} functions: {}".format(
                                               ", ".join(sorted(common)), len(carriers),
                                               ", ".join(sorted(f["name"] for f in carriers)[:6]))))
    families = {}
    for f in fns:
        if f["top"]:
            p = _design_prefix(f["name"])
            if p:
                families.setdefault(p, []).append(f)
    for prefix, group in sorted(families.items()):
        if len(group) >= DESIGN_PREFIX_GROUP:
            first = min(group, key=lambda f: f["line"])
            out.append(_design_finding("prefix-family", rel, first["line"], prefix,
                                       "{} top-level functions start with `{}`: {}".format(
                                           len(group), prefix, ", ".join(sorted(f["name"] for f in group)[:6]))))
    for i in range(len(classes)):
        for j in range(i + 1, len(classes)):
            a, b = classes[i], classes[j]
            if a["bases"] & b["bases"] or a["name"] in b["bases"] or b["name"] in a["bases"]:
                continue
            shared = sorted(n for n in a["methods"] if n in b["methods"] and not n.startswith("__"))
            if len(shared) >= DESIGN_SHARED_METHODS:
                out.append(_design_finding("shared-methods", rel, a["line"], "{}/{}".format(a["name"], b["name"]),
                                           "`{}` and `{}` share {} method names with no common base: {}".format(
                                               a["name"], b["name"], len(shared), ", ".join(shared[:6]))))
            for n in shared:
                if a["methods"][n] == b["methods"][n]:
                    out.append(_design_finding("duplicate-method", rel, b["line"], "{}.{}".format(b["name"], n),
                                               "`{}.{}` is byte-for-byte `{}.{}`".format(b["name"], n, a["name"], n)))
    return out


def _design_chain_findings(rel, chains):  # implements: REQ-DESIGN-951
    """chains: [(line, [(kind, name), ...])] where kind is 'type' or 'eq'."""
    out = []
    for line, tests in chains:
        for kind, floor, label in (("type", DESIGN_ISINSTANCE_CHAIN, "isinstance-chain"),
                                   ("eq", DESIGN_BRANCH_CHAIN, "type-switch")):
            names = [n for k, n in tests if k == kind]
            for name in sorted(set(names)):
                if names.count(name) >= floor:
                    out.append(_design_finding(label, rel, line, name,
                                               "{} branches test `{}` in one chain".format(names.count(name), name)))
    return out


def _design_standards(rel, src, n_top, undocumented):  # implements: REQ-DESIGN-953
    out = []
    lines = src.split("\n")
    base = os.path.basename(rel)
    if len(lines) > DESIGN_FILE_MAX_LINES:
        out.append(_design_finding("file-too-long", rel, 1, base,
                                   "{} lines (over {})".format(len(lines), DESIGN_FILE_MAX_LINES)))
    wide = [i for i, l in enumerate(lines, 1) if len(l.rstrip("\r")) > DESIGN_LINE_MAX]
    if wide:
        out.append(_design_finding("line-too-long", rel, wide[0], base,
                                   "{} line(s) wider than {} columns, first at line {}".format(
                                       len(wide), DESIGN_LINE_MAX, wide[0])))
    if n_top > DESIGN_FILE_MAX_FUNCS:
        out.append(_design_finding("too-many-definitions", rel, 1, base,
                                   "{} top-level definitions (over {})".format(n_top, DESIGN_FILE_MAX_FUNCS)))
    if DESIGN_DOCSTRING_PUBLIC and undocumented:
        out.append(_design_finding("missing-docstring", rel, undocumented[0][1], undocumented[0][0],
                                   "{} public definition(s) without a docstring: {}".format(
                                       len(undocumented), ", ".join(n for n, _l in undocumented[:6]))))
    return out


# ---- Python, through ast
def _design_py_params(fn):
    a = fn.args
    return [x.arg for x in a.posonlyargs + a.args + a.kwonlyargs if x.arg not in ("self", "cls")]


_DESIGN_NESTING_NODES = (ast.If, ast.For, ast.While, ast.With, ast.Try, ast.AsyncFor, ast.AsyncWith)
_DESIGN_SCOPE_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def _design_py_nesting(node, depth=0):
    """Deepest block nesting under `node`. Iterative on purpose: a generated
    1,000-term expression or a 1,000-branch `elif` chain parses fine but sits deeper
    than the interpreter's recursion limit, and a RecursionError here escaped every
    handler and killed `gate` and `sync` (advisory pass, fatal exit)."""
    best, stack = depth, [(node, depth)]
    while stack:
        n, d = stack.pop()
        for child in ast.iter_child_nodes(n):
            if isinstance(child, _DESIGN_NESTING_NODES):
                best = max(best, d + 1)
                stack.append((child, d + 1))
            elif not isinstance(child, _DESIGN_SCOPE_NODES):
                stack.append((child, d))
    return best


def _design_py_test(test):
    """('type', name) for isinstance(name, ...), ('eq', name) for name == <constant>, else None."""
    if (isinstance(test, ast.Call) and isinstance(test.func, ast.Name) and test.func.id == "isinstance"
            and test.args and isinstance(test.args[0], ast.Name)):
        return ("type", test.args[0].id)
    if (isinstance(test, ast.Compare) and len(test.ops) == 1 and isinstance(test.ops[0], ast.Eq)
            and isinstance(test.left, ast.Name) and isinstance(test.comparators[0], ast.Constant)):
        return ("eq", test.left.id)
    return None


def _design_py_fields(cls):  # implements: REQ-DESIGN-978
    """The class's real instance fields: every name assigned through `self.<name>`,
    plus whatever `__slots__` declares. Only these count as state — a class whose
    state lives somewhere else (a `dict` subclass keys its own data) has no field for
    two methods to share, and is skipped rather than scored as maximally incohesive."""
    out = set()
    for n in ast.walk(cls):
        targets = []
        if isinstance(n, ast.Assign):
            targets = list(n.targets)
        elif isinstance(n, (ast.AnnAssign, ast.AugAssign)):
            targets = [n.target]
        for t in targets:
            if isinstance(t, ast.Tuple):
                targets.extend(t.elts)
            elif (isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name)
                    and t.value.id == "self"):
                out.add(t.attr)
    for st in cls.body:
        # A declarative class names its state in the class body instead of assigning it:
        # `@dataclass`, attrs and Pydantic all write `name: type`, and the assignment
        # this function looks for happens in an __init__ that is synthesised at runtime
        # and never appears in the tree. Without this branch cohesion was skipped in
        # silence for the commonest class shape in modern Python — and the skip was
        # indistinguishable from a class measured and found cohesive.
        if isinstance(st, ast.AnnAssign) and isinstance(st.target, ast.Name):
            out.add(st.target.id)
        if not (isinstance(st, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "__slots__" for t in st.targets)):
            continue
        if isinstance(st.value, (ast.Tuple, ast.List)):
            out |= {e.value for e in st.value.elts
                    if isinstance(e, ast.Constant) and isinstance(e.value, str)}
    return out


def _design_lcom(methods, fields):  # implements: REQ-DESIGN-980
    """LCOM1 over the methods that actually touch state: pairs sharing no instance
    field, minus the pairs that share one, floored at zero.

    Methods that touch no field at all are excluded, not counted as disjoint from
    everything. A pure helper has no state to share, so pairing it with every other
    method measures nothing about how the class is split — it just adds one pair per
    sibling. An independent review found this dominating the score on two builder
    classes, and six field-less helpers on a one-field class scoring 26 against a
    threshold of 20 with no split anywhere in the class."""
    touched = []
    for m in methods:
        fs = {n.attr for n in ast.walk(m)
              if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
              and n.value.id == "self" and n.attr in fields}
        if fs:
            touched.append(fs)
    apart = together = 0
    for i in range(len(touched)):
        for j in range(i + 1, len(touched)):
            if touched[i] & touched[j]:
                together += 1
            else:
                apart += 1
    return max(0, apart - together)


def _design_cohesion_skipped(tree):  # implements: REQ-DESIGN-979
    """How many classes in this tree have two or more methods but no field the engine
    can see, so their cohesion was not measured.

    Reported rather than inferred: a class keeping its state somewhere `ast` cannot
    follow (a `dict` subclass, `setattr`, a metaclass) yields no `low-field-sharing`
    candidate, and an absent candidate is otherwise indistinguishable from a measured
    pass."""
    n = 0
    for cls in [x for x in ast.walk(tree) if isinstance(x, ast.ClassDef)]:
        methods = [m for m in cls.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))]
        if len(methods) >= 2 and not _design_py_fields(cls):
            n += 1
    return n


def _design_metrics(rel, tree):  # implements: ARCH-DESIGN-061  # implements: REQ-DESIGN-978
    """Chidamber & Kemerer per class, for the three of the six that say something here.

    WMC (methods), RFC (own methods plus the distinct methods they call) and LCOM1
    (methods sharing no field) each name a shape the function-level checks cannot see:
    they measure a CLASS, where everything else in this review measures a function or a
    file. DIT and NOC are left out because they measure an inheritance tree, and a repo
    that composes instead of subclassing has none to measure — they would report zero
    forever and teach a reader to ignore the pillar. CBO is left out because resolving
    which class a Python name refers to needs type inference this engine does not do,
    and a coupling number that is wrong is worse than no coupling number.

    Python only: these count methods and field access, which the brace-language
    heuristics cannot identify without parsing. `cmd_design` therefore prints what this
    pillar did NOT measure whenever it renders — an empty Metrics block on a
    subclass-heavy repo would otherwise read as "your classes are fine" when it means
    "the two metrics that would have spoken were never computed"."""
    out = []
    for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
        methods = [m for m in cls.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))]
        if not methods:
            continue
        called = set()
        for m in methods:
            for n in ast.walk(m):
                if not isinstance(n, ast.Call):
                    continue
                f = n.func
                nm = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
                if nm:
                    called.add(nm)
        rfc = len(methods) + len(called)
        if rfc > DESIGN_RFC_MAX:
            out.append(_design_finding("high-response", rel, cls.lineno, cls.name,
                                       "`{}` reaches {} methods (over {}): {} of its own "
                                       "plus {} it calls".format(cls.name, rfc, DESIGN_RFC_MAX,
                                                                 len(methods), len(called))))
    return out


def _design_cohesion_skipped_in(src):  # implements: REQ-DESIGN-979
    """The skipped-cohesion count for one file's source, 0 when it does not parse."""
    try:
        return _design_cohesion_skipped(ast.parse(src))
    except (SyntaxError, ValueError):
        return 0


def _design_python(rel, src):  # implements: REQ-DESIGN-950  # implements: REQ-DESIGN-951
    try:
        tree = ast.parse(src)
    except (SyntaxError, ValueError):
        return []
    out = []
    top = {id(n) for n in tree.body}
    fns, classes = [], []
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names = sorted({g for s in ast.walk(n) if isinstance(s, ast.Global) for g in s.names})
            if names:
                out.append(_design_finding("global-state", rel, n.lineno, n.name,
                                           "`{}` writes module state: {}".format(n.name, ", ".join(names))))
            end = getattr(n, "end_lineno", None) or n.lineno
            fns.append({"name": n.name, "line": n.lineno, "n_lines": end - n.lineno + 1,
                        "depth": _design_py_nesting(n), "params": _design_py_params(n), "top": id(n) in top})
        elif isinstance(n, ast.ClassDef):
            classes.append({"name": n.name, "line": n.lineno,
                            "bases": {b.id if isinstance(b, ast.Name) else ast.dump(b) for b in n.bases},
                            "methods": {m.name: ast.dump(m) for m in n.body
                                        if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))}})
    out += _design_shape_findings(rel, fns, classes)
    out += _design_metrics(rel, tree)
    chains, seen = [], set()
    for n in ast.walk(tree):
        if not isinstance(n, ast.If) or id(n) in seen:
            continue
        tests, node = [], n
        while isinstance(node, ast.If):
            seen.add(id(node))
            t = _design_py_test(node.test)
            if t:
                tests.append(t)
            node = node.orelse[0] if len(node.orelse) == 1 and isinstance(node.orelse[0], ast.If) else None
        chains.append((n.lineno, tests))
    out += _design_chain_findings(rel, chains)
    defs = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
    undocumented = [(n.name, n.lineno) for n in defs if not n.name.startswith("_") and not ast.get_docstring(n)]
    return out + _design_standards(rel, src, len(defs), undocumented)


# ---- brace languages, through masked text
_BRACE_KEYWORDS = frozenset(("if", "for", "while", "switch", "catch", "else", "return", "do", "try",
                             "sizeof", "typeof", "new", "throw", "await", "yield", "defer", "match",
                             "elif", "unless", "until", "foreach", "using", "lock", "synchronized"))
_BRACE_FUNC_RE = re.compile(
    r"(?<![\w.])(?:(?:async|static|public|private|protected|export|default|override|virtual|inline|"
    r"constexpr|extern|final|abstract|unsafe|pub(?:\([^)]*\))?|func|fn|fun|function|def)\s+)*"
    r"(?:[A-Za-z_][\w:<>\[\],*&?]*\s+[*&]*)?([A-Za-z_]\w*)\s*(?:<[^>()]*>)?\s*\(([^()]*(?:\([^()]*\)[^()]*)*)\)"
    r"\s*(?:->\s*[\w:<>\[\],*&?.]+|:\s*[\w:<>\[\],*&?.|]+|const|override|noexcept|throws\s+[\w, ]+)?\s*\{")
_BRACE_ARROW_RE = re.compile(r"(?<![\w.])(?:const|let|var|val)\s+([A-Za-z_]\w*)\s*(?::[^=]+)?=\s*(?:async\s*)?\(([^()]*)\)\s*(?::\s*[^=]+)?=>\s*\{")
_BRACE_CLASS_RE = re.compile(r"(?<![\w.])(?:class|struct|interface)\s+([A-Za-z_]\w*)(?:\s*<[^>{]*>)?\s*([^{;]*)\{")
_BRACE_IF_RE = re.compile(r"(?<![\w.])(else\s+)?if\s*\(")
_BRACE_SWITCH_RE = re.compile(r"(?<![\w.])switch\s*\(\s*([A-Za-z_][\w.]*)\s*\)\s*\{")
_BRACE_CASE_RE = re.compile(r"(?<![\w.])case\s+[^:]{1,60}:")
_BRACE_TYPE_TEST_RE = re.compile(r"(?:([A-Za-z_]\w*)\s+instanceof\b|typeof\s+([A-Za-z_]\w*)\s*[!=]==?|"
                                 r"dynamic_cast\s*<[^>]*>\s*\(\s*([A-Za-z_]\w*)|([A-Za-z_]\w*)\s+is\s+[A-Z]\w*)")
_BRACE_EQ_TEST_RE = re.compile(r"(?<![\w.])([A-Za-z_][\w.]*)\s*[!=]==?\s*(?:\d+|[A-Z_][A-Z0-9_]{2,}|\w+::\w+)")


def _design_mask(src):
    """The source with comments and string/char literals replaced by spaces (newlines
    kept), so brace matching and keyword searches never see text."""
    out, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        two = src[i:i + 2]
        if two == "//":
            j = src.find("\n", i)
            j = n if j == -1 else j
            out.append(" " * (j - i)); i = j
        elif two == "/*":
            j = src.find("*/", i + 2)
            j = n if j == -1 else j + 2
            out.append("".join("\n" if ch == "\n" else " " for ch in src[i:j])); i = j
        elif c in "\"'`":
            q, j = c, i + 1
            while j < n and src[j] != q:
                j += 2 if src[j] == "\\" else 1
                if j < n and src[j] == "\n" and q != "`":
                    break
            j = min(j + 1, n)
            out.append("".join("\n" if ch == "\n" else " " for ch in src[i:j])); i = j
        else:
            out.append(c); i += 1
    return "".join(out)


def _design_block_end(masked, open_idx):
    """Index just past the `}` matching the `{` at open_idx (or len(masked))."""
    depth, i, n = 0, open_idx, len(masked)
    while i < n:
        if masked[i] == "{":
            depth += 1
        elif masked[i] == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return n


def _design_param_names(params):
    names = []
    for p in params.split(","):
        p = p.strip()
        if not p or p in ("...", "void"):
            continue
        p = p.split("=", 1)[0]
        if ":" in p:                      # TS / Kotlin / Swift: name: Type
            p = p.split(":", 1)[0]
        toks = re.findall(r"[A-Za-z_]\w*", p)
        if toks:
            names.append(toks[-1] if ":" not in p else toks[0])
    return names


def _design_brace(rel, src):  # implements: REQ-DESIGN-955
    masked = _design_mask(src)
    out, fns, classes = [], [], []
    n_top = 0

    def depth_at(idx):
        return masked.count("{", 0, idx) - masked.count("}", 0, idx)

    def add_fn(name, params, brace_idx, line):
        end = _design_block_end(masked, brace_idx)
        body = masked[brace_idx:end]
        depth, best = 0, 0
        for ch in body:
            if ch == "{":
                depth += 1; best = max(best, depth)
            elif ch == "}":
                depth -= 1
        fns.append({"name": name, "line": line, "n_lines": body.count("\n") + 1,
                    "depth": max(best - 1, 0), "params": _design_param_names(params),
                    "top": depth_at(brace_idx) == 0, "end": end})
    for m in _BRACE_FUNC_RE.finditer(masked):
        if m.group(1) in _BRACE_KEYWORDS:
            continue
        add_fn(m.group(1), m.group(2), m.end() - 1, masked.count("\n", 0, m.start()) + 1)
    for m in _BRACE_ARROW_RE.finditer(masked):
        add_fn(m.group(1), m.group(2), m.end() - 1, masked.count("\n", 0, m.start()) + 1)
    fns.sort(key=lambda f: f["line"])
    n_top = sum(1 for f in fns if f["top"])
    for m in _BRACE_CLASS_RE.finditer(masked):
        start, end = m.end() - 1, _design_block_end(masked, m.end() - 1)
        bases = set(re.findall(r"[A-Za-z_]\w*", re.sub(r"\b(?:extends|implements|public|private|protected|virtual|final|with)\b", " ", m.group(2))))
        methods = {}
        for f in fns:
            if start < f["end"] <= end and f["name"] not in _BRACE_KEYWORDS:
                fstart = masked.rfind(f["name"], start, f["end"])
                methods[f["name"]] = re.sub(r"\s+", " ", src[fstart:f["end"]]).strip()
        classes.append({"name": m.group(1), "line": masked.count("\n", 0, m.start()) + 1,
                        "bases": bases, "methods": methods})
        if depth_at(start) == 0:
            n_top += 1
    out += _design_shape_findings(rel, fns, classes)
    chains, cur = [], None
    for m in _BRACE_IF_RE.finditer(masked):
        paren = m.end() - 1
        depth, i = 0, paren
        while i < len(masked):
            if masked[i] == "(":
                depth += 1
            elif masked[i] == ")":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        cond = masked[paren:i + 1]
        tests = [("type", next(g for g in t if g)) for t in _BRACE_TYPE_TEST_RE.findall(cond)]
        tests += [("eq", n) for n in _BRACE_EQ_TEST_RE.findall(cond)]
        if m.group(1) and cur is not None:
            cur[1].extend(tests)
        else:
            cur = (masked.count("\n", 0, m.start()) + 1, tests)
            chains.append(cur)
    for m in _BRACE_SWITCH_RE.finditer(masked):
        body = masked[m.end() - 1:_design_block_end(masked, m.end() - 1)]
        n_cases = len(_BRACE_CASE_RE.findall(body))
        chains.append((masked.count("\n", 0, m.start()) + 1, [("eq", m.group(1))] * n_cases))
    out += _design_chain_findings(rel, chains)
    return out + _design_standards(rel, src, n_top, [])


def _design_file(rel, src):  # implements: ARCH-DESIGN-061  # implements: REQ-DESIGN-950  # implements: REQ-DESIGN-951  # implements: REQ-DESIGN-953  # implements: REQ-DESIGN-955
    """All findings for one source file, in source order: Python through `ast`, a brace
    language through the masked-text heuristics, anything else standards only."""
    low = rel.lower()
    try:
        if low.endswith(".py"):
            out = _design_python(rel, src)
        elif low.endswith(DESIGN_BRACE_EXTS):
            out = _design_brace(rel, src)
        else:
            out = _design_standards(rel, src, 0, [])
    except RecursionError:
        # `ast.dump` on a pathological class body is recursive too. This review is
        # advisory and never the gate; a file it cannot measure is a file with no
        # candidates, not a crashed commit hook.
        return []
    out.sort(key=lambda f: (f["line"], f["kind"]))
    return out


def _design_files(code_root, reqs_dir=None):
    """(abs_path, rel) for every non-test program-logic file the scanner would walk."""
    for fp, rel in _walk_code(code_root, reqs_dir):
        if rel.lower().endswith(DESIGN_EXTS) and not _is_test_path(rel):
            yield fp, rel


def _design_summary(code_root, reqs_dir=None, with_findings=False):  # implements: ARCH-DESIGN-061  # implements: REQ-DESIGN-954  # implements: REQ-DESIGN-976
    """The design health of the repo's code as one small record, or None when the tree
    holds no non-test program-logic file: `files`, `clean_files` (no candidate at all),
    `score` (clean files as a percentage — the same "green on every axis" reading `health`
    uses for requirements), `candidates` (count per group). Deterministic, so it can live
    in the committed `_map.json` and be checked for freshness.

    `with_findings` adds the candidates themselves, for the one caller that lists them
    (`map`, whose viewer shows them in their own tab). It is off by default because
    `health --json` is a CI badge payload: a caller reading a score must keep getting
    the same small object, not a few hundred rows it never asked for. The advice text
    is emitted once per kind rather than repeated on every row — it is a property of
    the rule, not of the occurrence."""
    files = clean = 0
    per = {p: 0 for p in DESIGN_PILLARS}
    rows = []
    for fp, rel in _design_files(code_root, reqs_dir):
        try:
            with open(fp, encoding="utf-8", errors="ignore") as f:
                src = f.read()
        except OSError:
            continue
        files += 1
        found = _design_file(rel, src)
        if not found:
            clean += 1
        for x in found:
            per[x["pillar"]] += 1
        if with_findings:
            rows.extend(found)
    if not files:
        return None
    out = {"files": files, "clean_files": clean, "score": round(100 * clean / files),
           "candidates": per}
    if with_findings:
        out["findings"] = [{"pillar": x["pillar"], "kind": x["kind"], "file": x["file"],
                            "line": x["line"], "name": x["name"], "detail": x["detail"]}
                           for x in rows]
        out["advice"] = {k: _DESIGN_ADVICE[k] for k in sorted({x["kind"] for x in rows})}
    return out


def cmd_design(code_root, reqs_dir=None, as_json=False):  # implements: ARCH-DESIGN-061  # implements: REQ-DESIGN-952
    """Print (or emit as JSON) the design candidates found in every non-test program-logic
    file under `code_root`, grouped by pillar. Read-only, always exit 0: this is advice a
    reader weighs, not a gate a build fails on."""
    findings, n_files, skipped = [], 0, 0
    for fp, rel in _design_files(code_root, reqs_dir):
        try:
            with open(fp, encoding="utf-8", errors="ignore") as f:
                src = f.read()
        except OSError:
            continue
        n_files += 1
        findings.extend(_design_file(rel, src))
        if rel.lower().endswith(".py"):
            skipped += _design_cohesion_skipped_in(src)
    if as_json:
        # The machine surface carries the same caveats as the text one. A consumer
        # dashboard reading `findings` and nothing else would otherwise render an empty
        # metrics group as a clean bill of health on metrics that were never computed.
        print(json.dumps({"files": n_files, "findings": findings,
                          "metrics_scope": DESIGN_METRICS_SCOPE,
                          "cohesion_skipped": skipped}, indent=2, ensure_ascii=False))
        return 0
    if not findings:
        print("No design candidates in {} source file(s) at the current thresholds.".format(n_files))
        print("note: " + DESIGN_METRICS_SCOPE)
        if skipped:
            print("note: cohesion not measured for {} class(es) with 2+ methods and no "
                  "field this engine can see.".format(skipped))
        return 0
    for pillar in DESIGN_PILLARS:
        mine = [f for f in findings if f["pillar"] == pillar]
        if not mine:
            continue
        print("{} ({})".format(pillar.capitalize(), len(mine)))
        for f in mine:
            print("  {}:{}  {:<20} {}".format(f["file"], f["line"], f["kind"], f["detail"]))
        print("  -> " + "; ".join(dict.fromkeys(_DESIGN_ADVICE[f["kind"]] for f in mine)))
        if pillar == "metrics":
            print("  note: " + DESIGN_METRICS_SCOPE)
            if skipped:
                print("  note: cohesion not measured for {} class(es) with 2+ methods and no "
                      "field this engine can see.".format(skipped))
        print("")
    print("{} candidate(s) in {} source file(s). Advisory only: a candidate is a shape worth a "
          "look, never a defect, and this never enters the gate.".format(len(findings), n_files))
    return 0


# ---------- per-repo configuration ----------
# Every threshold above is a module constant, and a consumer could change none of them
# without forking the engine. `requirements/_config.json` overrides the named ones —
# read fail-open, applied once at startup, a key of the wrong type or an unknown name
# is reported and ignored. Set constants without rewiring: the circuit network.
CONFIG_FILE = "_config.json"
CONFIG_KEYS = ("LINT_AC_MIN", "LINT_AC_MAX", "LINT_STATEMENT_WORDS", "LINT_CONTRACT_MAX",
               "LINT_FILE_SPREAD_MAX", "LINT_FANOUT_MIN", "LINT_FANOUT_MAX", "LINT_FANOUT_BANDS",
               "LINT_STACKED_CONNECTORS", "LINT_CLAUSE_SENTENCES", "LINT_BUS_FANOUT_MIN",
               "SIMILAR_THRESHOLD", "ORPHAN_CODE_MIN_LOC", "DOC_BUNDLE_MIN_BYTES",
               "SYSTEM_HUB_FANIN", "BUS_FANIN_THRESHOLD", "SPLIT_LOC_THRESHOLD",
               "DESIGN_FUNC_MAX_LINES", "DESIGN_NESTING_MAX", "DESIGN_PARAMS_MAX", "DESIGN_CLUMP_MIN",
               "DESIGN_CLUMP_FUNCS", "DESIGN_PREFIX_GROUP", "DESIGN_SHARED_METHODS",
               "DESIGN_ISINSTANCE_CHAIN", "DESIGN_BRANCH_CHAIN", "DESIGN_FILE_MAX_LINES",
               "DESIGN_LINE_MAX", "DESIGN_FILE_MAX_FUNCS", "DESIGN_DOCSTRING_PUBLIC",
               "DESIGN_RFC_MAX", "DRIFT_SEVERITY")

# A string-valued config key names a behaviour, so its accepted spellings are declared
# here and a value outside them is reported rather than applied. Without this, a repo
# that wrote `"eror"` would get the default back in silence — precisely the failure the
# whole config mechanism exists to avoid.
CONFIG_ENUMS = {"DRIFT_SEVERITY": ("warn", "error")}


def load_config(reqs_dir):  # implements: ARCH-CONFIG-060  # implements: REQ-CONFIG-949
    """The parsed `requirements/_config.json`, or {} when absent, unreadable or not an object."""
    try:
        with open(os.path.join(reqs_dir, CONFIG_FILE), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def apply_config(cfg, out=None):  # implements: ARCH-CONFIG-060  # implements: REQ-CONFIG-949
    """Apply `cfg` to the module constants. Returns the names applied. A key that is
    not in CONFIG_KEYS, or whose value has a different type than the default, is
    reported on `out` (stderr) and skipped — a typo must never silently change nothing."""
    global CODE_EXTS
    out = out or sys.stderr
    applied = []
    g = globals()
    for key, value in (cfg or {}).items():
        if key == "extra_code_exts":
            if isinstance(value, list) and all(isinstance(x, str) for x in value):
                extra = tuple(x if x.startswith(".") else "." + x for x in value if x)
                CODE_EXTS = CODE_EXTS + tuple(e for e in extra if e not in CODE_EXTS)
                applied.append(key)
            else:
                print("config: ignoring extra_code_exts (expected a list of strings)", file=out)
            continue
        if key not in CONFIG_KEYS:
            print("config: ignoring unknown key {!r}".format(key), file=out)
            continue
        default = g[key]
        # A string-valued key is an ENUM, never free text: every one of them names a
        # behaviour, so an unrecognised spelling is a typo that must be reported. The
        # numeric branch below would otherwise reject strings outright and a repo
        # could never set one at all.
        if isinstance(default, str):
            allowed = CONFIG_ENUMS.get(key, ())
            if not isinstance(value, str) or (allowed and value not in allowed):
                print("config: ignoring {} (expected one of {})".format(
                    key, ", ".join(allowed) or "a string"), file=out)
                continue
            g[key] = value
            applied.append(key)
            continue
        if isinstance(default, dict):
            if not isinstance(value, dict):
                print("config: ignoring {} (expected an object)".format(key), file=out)
                continue
            merged = dict(default)
            for k, v in value.items():
                merged[k] = tuple(v) if isinstance(v, list) else v
            g[key] = merged
        elif isinstance(default, bool) or not isinstance(default, (int, float)) \
                or isinstance(value, bool) or not isinstance(value, (int, float)):
            print("config: ignoring {} (expected {})".format(key, type(default).__name__), file=out)
            continue
        else:
            g[key] = type(default)(value)
        applied.append(key)
    return applied



def _build_parser():  # implements: ARCH-CMDREGISTRY-033
    """The argument parser for every verb and flag, built from the command
    registry. Separate from `main` because it is a hundred and fifty lines of
    declaration with no decision in it, and reading the dispatch meant
    scrolling past all of them."""
    # The epilog is rendered from the registry: a hand-written one listed twelve verbs
    # argparse rejected (`draft`, `confirm`, `translate`, ...) for a whole release.
    epilog = []
    for group, names in COMMAND_GROUPS:
        epilog.append(group.capitalize() + ":")
        for name in names:
            spec = COMMANDS[name]
            verb = name + (" " + spec["arg"] if spec.get("arg") else "")
            flags = " ".join(p["flag"] for p in spec["params"])
            epilog.append("  {:<22} {}".format(verb, spec["summary"].split(". ")[0]))
            if flags:
                epilog.append("  {:<22} flags: {}".format("", flags))
    ap = argparse.ArgumentParser(
        prog="reqmap",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\n".join(epilog),
    )
    ap.add_argument("cmd", choices=_cli_choices())
    ap.add_argument("arg", nargs="?")
    ap.add_argument("--root", default=".")
    ap.add_argument("--reqs", default=None)
    ap.add_argument("--code", default=None)
    ap.add_argument("--out", default=None, help="candidates: write plan JSON here ('-' or omit = stdout); "
                    "export: write graph JSON here ('-' = stdout, omit = requirements/_map.json)")
    ap.add_argument("--md-glob", action="append", default=None,
                    help="candidates: also discover .md files matching this glob (repeatable; "
                         "comma-separated ok). Off unless given. e.g. --md-glob 'prompts/**' --md-glob 'modes/**'")
    ap.add_argument("--all", dest="show_all", action="store_true",
                    help="next: list every pending item instead of the top few per bucket")
    ap.add_argument("--strict", action="store_true",
                    help="lint: exit non-zero on errors. check: promote drift and "
                         "test-link integrity from warn to error.")
    ap.add_argument("--no-lint", dest="no_lint", action="store_true",
                    help="gate: skip the requirement readability check")
    ap.add_argument("--no-map-check", dest="no_map_check", action="store_true",
                    help="gate: skip the committed-map freshness check")
    ap.add_argument("--findings", action="store_true",
                    help="sync: also create requirements/_findings.md the first time "
                         "(it is refreshed automatically once it exists)")
    ap.add_argument("--untagged", action="store_true",
                    help="next: list the source files carrying no implements: tag")
    ap.add_argument("--plan", action="store_true",
                    help="draft: emit the JSON extraction plan and write no requirement")
    ap.add_argument("--delete", action="store_true",
                    help="retire: remove the requirement outright instead of deprecating it")
    ap.add_argument("--force", action="store_true",
                    help="retire: proceed despite dependents, or on a dirty working tree")
    ap.add_argument("--decompose", action="store_true",
                    help="clarify --decompose: scaffold one draft requirement per statement-size "
                         "finding (opt-in; the only mode that writes files)")
    ap.add_argument("--levels", action="store_true",
                    help="clarify --levels: propose a V-model rung for every requirement that "
                         "declares none (read-only; --apply writes them)")
    ap.add_argument("--threshold", type=_threshold_arg, default=None,
                    help="gate --dupes: cosine cutoff in (0,1] for reporting a pair (default 0.35)")
    ap.add_argument("--top", type=int, default=None,
                    help="gate --search: max ranked matches to show (default 5); "
                         "gate --dupes: max pairs to print (default all)")
    ap.add_argument("--json", dest="as_json", action="store_true",
                    help="check|health|coverage|design: emit structured JSON output (for CI/badge consumption)")
    ap.add_argument("--badge", dest="as_badge", action="store_true",
                    help="health: emit Shields.io endpoint JSON (schemaVersion, label, message, color)")
    ap.add_argument("--accept-drift", dest="accept_drift", nargs="?", const=True,
                    default=False, metavar="REASON",
                    help="sync: advance the drift baseline even when a confirmed/implemented "
                         "contract changed (otherwise sync refuses and exits non-zero)")
    ap.add_argument("--since", metavar="REF",
                    help="gate: scope to requirements whose member files changed since REF "
                         "(hypothesis: highest-frequency changes; falls back to full scan on git error)")
    ap.add_argument("--wipe", action="store_true",
                    help="init: hard-reset — delete all non-generated requirements and strip "
                         "membership tags from source files before re-extracting")
    ap.add_argument("--id", dest="new_id", default=None,
                    help="new --from-todo: the AREA-NAME-NNN id for the scaffolded requirement (required)")
    ap.add_argument("--from-todo", dest="from_todo", default=None,
                    help="new: scaffold the requirement from a TODO.md item matched by this name "
                         "(use with --id; add --mark-done to flip the item to [x])")
    ap.add_argument("--mark-done", dest="mark_done", action="store_true",
                    help="new --from-todo: also flip the matched TODO.md item to [x] (off by default)")
    ap.add_argument("--cache", action="store_true",
                    help="opt-in: reuse a per-file scan cache (requirements/_scancache.json) so unchanged "
                         "files skip re-parsing. Off by default; results are identical with or without it.")
    ap.add_argument("--attach", default=None,
                    help="sync: target HTML to inject the site's engine-owned regions into "
                         "(scaffolds it if absent)")
    ap.add_argument("--no-site", dest="no_site", action="store_true",
                    help="init: skip the final site step")
    ap.add_argument("--apply", dest="do_apply", action="store_true",
                    help="sync --retire / --suggest-verifies: actually write the change "
                         "(without it, the run is a dry report)")
    # Mode flags: the read-only queries that used to be their own verbs. The work
    # they do is unchanged — only the entry point moved, so `gate` is the one place
    # a reader asks the corpus anything and `sync` the one place a write happens.
    ap.add_argument("--audit", dest="mode_audit", action="store_true",
                    help="gate: also print risk, duplicate contracts, design signals and tag coverage")
    ap.add_argument("--risk", dest="mode_risk", action="store_true",
                    help="gate: print the corpus risk snapshot and what to do next")
    ap.add_argument("--show", dest="mode_show", metavar="ID", nargs="?", default=None,
                    const="",
                    help="gate: print one requirement's dossier")
    ap.add_argument("--search", dest="mode_search", metavar="QUERY", nargs="?", default=None,
                    const="",
                    help="gate: rank requirements by lexical relevance to a query")
    ap.add_argument("--review", dest="mode_review", metavar="ID", nargs="?", default=None,
                    const="",
                    help="gate: emit the review plan for one requirement")
    ap.add_argument("--implement", dest="mode_implement", metavar="ID", nargs="?", default=None,
                    const="",
                    help="gate: emit the implementation brief for one requirement")
    ap.add_argument("--dupes", dest="mode_dupes", action="store_true",
                    help="gate: rank requirement pairs whose contracts overlap")
    ap.add_argument("--design", dest="mode_design", action="store_true",
                    help="gate: print the advisory design review of the code")
    ap.add_argument("--suggest-verifies", dest="mode_suggest", action="store_true",
                    help="sync: propose per-criterion `verifies:` tags (--apply writes them)")
    ap.add_argument("--retire", dest="mode_retire", metavar="ID", nargs="*", default=None,
                    help="sync: take one or more requirements out of service; prints the "
                         "blast radius first")
    return ap


def _dispatch_gate(a, ws, code_root, reqs_dir):
    """`gate` and every read-only question its mode flags ask. Returns the exit
    code; only the bare verdict can make it non-zero."""
    reqs, members = ws.reqs, ws.members   # the commands that take only part of it
    if a.mode_audit:
        return cmd_audit(ws, strict=a.strict, as_json=a.as_json)
    if a.mode_risk:
        if a.as_badge:
            return cmd_health(ws, False, True)
        if a.as_json:
            return cmd_health(ws, True, False)
        if a.untagged:
            return cmd_coverage(ws, False)
        cmd_health(ws, False, False, headline_only=True)
        return cmd_next(ws, a.show_all)
    if a.mode_show is not None:
        if not a.mode_show:
            print("usage: reqmap gate --show <ID>"); return 2
        # Workspace.load (the non-cache path) already produced level_cover in the
        # same walk; ws.levels() only re-walks when --cache forced the
        # scan_members-only path (cache is scan_members-only, see scan_all's docstring).
        return cmd_show(ws, a.mode_show, ws.levels())
    if a.mode_search is not None:
        if not a.mode_search:
            print("usage: reqmap gate --search \"<query>\"   [--top N]"); return 2
        return cmd_search(reqs, a.mode_search, a.top if a.top is not None else SEARCH_TOP,
                          reqs_dir=reqs_dir)
    if a.mode_review is not None:
        if not a.mode_review:
            print("usage: reqmap gate --review AREA-NAME-NNN"); return 2
        return cmd_review(reqs, a.mode_review)
    if a.mode_implement is not None:
        if not a.mode_implement:
            print("usage: reqmap gate --implement AREA-NAME-NNN"); return 2
        return cmd_implement(ws, a.mode_implement, as_json=a.as_json)
    if a.mode_dupes:
        return cmd_similar(reqs, a.threshold if a.threshold is not None else SIMILAR_THRESHOLD,
                           members, top=a.top)
    if a.mode_design:
        return cmd_design(code_root, reqs_dir, as_json=a.as_json)
    # The whole verdict, in the order every hook and CI already ran it: link sync +
    # drift + test-link, then requirement readability, then map freshness. They were
    # three commands because they were written on three days, not because a caller
    # ever wanted one without the others (the published Action defaults both extras
    # to on). Report-only throughout: never touches the lock, never writes a map.
    rc = cmd_check(ws, False, a.strict, a.as_json, getattr(a, "since", None))
    if a.as_json:
        return rc                      # one machine-readable document, not three
    if not a.no_lint:
        rc = cmd_lint(ws, strict=True) or rc
    if not a.no_map_check:
        rc = cmd_map(ws, code_root, True) or rc
    return rc
def _dispatch_sync(a, ws, code_root, reqs_dir):
    """`sync` and its write modes. Returns the exit code."""
    reqs, members = ws.reqs, ws.members   # the commands that take only part of it
    if a.mode_retire is not None:
        if not a.mode_retire:
            print("usage: reqmap sync --retire AREA-NAME-NNN [ID ...]"); return 2
        return cmd_retire(ws, a.mode_retire, delete=a.delete,
                          do_apply=a.do_apply, force=a.force, as_json=a.as_json)
    if a.mode_suggest:
        return cmd_suggest_verifies(ws, apply_tags=a.do_apply)
    # Before the gate, not after: the generated integration artifacts are derived
    # from the command registry, and RM028 reports them stale. Regenerating them
    # downstream of a check that fails ON them can never converge.
    if _is_source_repo(code_root):
        cmd_gen_integration(reqs_dir, code_root)
    # rescan + regenerate map + advance the drift baseline (guarded). Members were
    # already scanned above; cmd_check rewrites the lock unless confirmed drift is
    # detected without --accept-drift, then map regenerates only on success.
    _accepted = getattr(a, "accept_drift", False)
    # `--accept-drift` alone yields True; with a reason it yields the string. An empty
    # string is still a caller who passed the flag, so the boolean is `is not False`
    # rather than a truthiness test.
    rc = cmd_check(ws, True, strict=a.strict,
                   accept_drift=_accepted is not False,
                   drift_reason=(_accepted.strip() or None
                                 if isinstance(_accepted, str) else None))
    if rc == 0:
        cmd_map(ws, code_root)
        # Everything derived is rebuilt in one place: there is no state of the world
        # in which regenerating the map but not the findings digest, the presentation
        # page or (in this repository) the generated integration artifacts is what the
        # caller wanted. Each step below is a no-op when its target does not exist.
        # `map` already refreshes an existing digest; this is the create path,
        # kept opt-in so a consumer repo never gains a file it did not ask for.
        if a.findings and not os.path.exists(os.path.join(reqs_dir, "_findings.md")):
            cmd_findings(reqs, reqs_dir, raw=False)
        _site_page = a.attach or _site_default_target(code_root)
        if _site_page and os.path.isfile(_site_page):
            cmd_site(ws, code_root, attach=_site_page,
                     regions=["nav", "stats"], diagram=None, detect=False)
        # Deliberately here and not in cmd_check: `gate` runs on every commit via the
        # hook, and a corpus-shape advisory there is noise on work that is already
        # correct. `sync` is the moment the corpus was just rewritten, which is when
        # a newly-minted duplicate appears.  # implements: ARCH-REDUNDANCY-058
        _dups = _redundant_groups(reqs)
        if _dups:
            print("info  {} group(s) of requirements share an identical contract "
                  "({} could be folded away) — run `reqmap.py gate --risk` to see them"
                  .format(len(_dups), sum(len(g) - 1 for g in _dups)))
        # Everything the engine can discover, named in one place at the moment the
        # corpus was just rewritten. `sync` regenerates what is derived; until now it
        # said nothing about what is WRONG beyond the gate, so a repo could sync for
        # months without ever meeting `dupes`, `design`, the exemption list or the
        # fact that its corpus is flat.  # implements: REQ-AUDIT-973
        _audit_summary(reqs, members, reqs_dir, code_root)
    else:
        # The lock may still have advanced above (it is written unless CONFIRMED
        # drift was refused), while the map was not regenerated — the two then
        # disagree, `gate` passes locally, and CI fails on `map --check`. Say so
        # where it happens instead of leaving the reader to infer it.
        print("sync: gate failed — the map was NOT regenerated. Fix the errors above "
              "and re-run `sync`, or run `map` explicitly.", file=sys.stderr)
    return rc
def main():
    """Parse the command line, load the workspace once, and dispatch to the verb.
    Returns the process exit code."""
    # Refuse an interpreter below the declared floor before anything else runs, so the
    # user gets one readable line instead of an AttributeError from some stdlib call
    # that did not exist yet.
    floor = _python_floor_error()  # implements: REQ-PYFLOOR-902
    if floor:
        print(floor)
        return 2
    # The engine prints non-ASCII (em-dashes in WARN/info lines, the JSON plan with
    # ensure_ascii=False). On a legacy Windows codepage (cp437/cp850) a bare `python
    # reqmap.py check` would crash with UnicodeEncodeError and fail the gate on an
    # encoding error, not a real violation. Force UTF-8 so no caller has to remember
    # `-X utf8`. Guarded: reconfigure() is Python 3.7+ and may be absent on exotic streams.
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError, OSError):
            pass
    ap = _build_parser()
    a = ap.parse_args()
    reqs_dir = a.reqs or os.path.join(a.root, "requirements")
    code_root = a.code or a.root
    apply_config(load_config(reqs_dir))   # implements: ARCH-CONFIG-060
    # prefer an on-disk templates/requirement.md if present (back-compat), else the
    # built-in REQUIREMENT_TEMPLATE — so no templates/ dir is required.
    here = os.path.dirname(os.path.abspath(__file__))
    tmpl = os.path.join(here, "..", "templates", "requirement.md")
    if not os.path.exists(tmpl):
        tmpl = None

    if a.cmd == "new":
        if getattr(a, "from_todo", None):
            return cmd_promote_todo(reqs_dir, tmpl, a.from_todo, a.new_id, a.mark_done, code_root)
        if not a.arg:
            print("usage: reqmap new AREA-NAME-NNN   |   reqmap new --from-todo \"<todo name>\" --id AREA-NAME-NNN"); return 2
        return cmd_new(reqs_dir, tmpl, a.arg)
    if a.cmd == "init" and not a.plan:
        return cmd_init(reqs_dir, code_root, wipe=a.wipe, no_site=a.no_site)

    # One walk for the commands that need coverage too (gate/sync); the rest only ever
    # asked for members. --cache stays on scan_members, the only scanner that implements
    # it - see scan_all's docstring for why it is not duplicated there.
    ws = Workspace.load(reqs_dir, code_root, cache=a.cache)
    if a.cmd == "init":            # init --plan: the read-only extraction plan
        md_globs = []
        for g in (a.md_glob or []):
            md_globs += [x.strip() for x in g.split(",") if x.strip()]
        return cmd_candidates(ws, a.out, md_globs)
    if a.cmd == "gate":
        return _dispatch_gate(a, ws, code_root, reqs_dir)
    if a.cmd == "sync":
        return _dispatch_sync(a, ws, code_root, reqs_dir)
    if a.cmd == "clarify":
        if a.decompose:
            # scaffolding a clause into its own requirement is the write half of the
            # same question clarify asks about an over-scoped requirement — for THIS
            # requirement (it used to scaffold every over-long clause in the corpus)
            if a.arg and a.arg not in ws.reqs:
                print("no requirement with id {}".format(a.arg)); return 1
            return cmd_lint(ws, strict=False, decompose=True, only=a.arg or None)
        if a.levels:
            # the retrofit ADR-0030 leaves out: `init` mints the rungs only for the
            # drafts it extracts, so a corpus that was already tagged has no path to
            # the axis. Human-invoked on purpose, and never on `sync`.
            return cmd_levels(ws, apply_it=a.do_apply, only=a.arg or None)
        return cmd_clarify(ws.reqs, a.arg, as_json=a.as_json)


def _pipe_closed():  # implements: ARCH-PIPE-046
    """The reader (`| head`) stopped listening: point stdout at the null device so the
    interpreter's shutdown flush cannot raise a second time, and exit clean."""
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
    except Exception:
        pass
    # Measured on Windows: after the dup2 the interpreter's shutdown flush of the
    # original stdout buffer STILL raised EINVAL and the process exited 120 with
    # "Exception ignored in: <_io.TextIOWrapper ...>" on stderr — the fix above made
    # the traceback quieter, not the exit clean. Leave without that flush.
    try:
        sys.stderr.flush()
    except Exception:
        pass
    os._exit(0)


def _run_cli(entry=None):  # implements: ARCH-PIPE-046  # implements: REQ-PIPE-893
    """Run `main` (or `entry`), turning a closed output pipe into a quiet exit 0.
    Windows has no SIGPIPE: a reader that closes early surfaces as OSError EINVAL (22),
    on POSIX as BrokenPipeError/EPIPE — `dupes | head` on a 1,141-requirement corpus
    died with a traceback on the primary supported OS. Every other OSError propagates."""
    try:
        return (entry or main)() or 0
    except BrokenPipeError:
        return _pipe_closed()
    except OSError as e:
        if e.errno in (errno.EPIPE, errno.EINVAL):
            return _pipe_closed()
        raise


if __name__ == "__main__":
    sys.exit(_run_cli())
