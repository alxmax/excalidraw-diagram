"""The COMMANDS registry: the CLI's single source of truth, one entry per
command (data only).
"""



# ---------------------------------------------------------------------------
# COMMANDS registry — single source of truth for the CLI command set.
# Each entry describes one user-facing command: its summary, the positional
# argument it accepts (or None), and the flags it owns (subset of the shared
# argparse flag pool; global flags --root/--reqs/--code/--cache are omitted).
# Later tasks will derive argparse choices, tool_definition.json, and a
# markdown command table from this registry — do NOT add behaviour here.
# ---------------------------------------------------------------------------
# implements: ARCH-CMDREGISTRY-033  # implements: REQ-NEWGONE-1034
# implements: REQ-SURFACE-1095
COMMANDS = {
    "init": {
        "summary": (
            "First-use bootstrap: scaffold requirements/ and .reqmapignore if "
            "missing, draft requirements from existing code and prose, build "
            "the lock and map, and print guided next steps. Idempotent — safe "
            "to re-run; never clobbers an existing .reqmapignore. --plan emits "
            "the extraction plan as JSON and writes no requirement files, for "
            "looking before authoring. --watch REF prints draft suggestions "
            "for code files changed since REF, and the commit subjects in "
            "between, and writes nothing. --propose TEXT prints one "
            "requirement draft for a person to confirm, and writes nothing. "
       
        ),
        "arg": None,
        "params": [
            {"name": "plan", "flag": "--plan",
             "consumer": "plugin/skills/requirement-manager/SKILL.md",
             "type": "bool",
             "help": "Emit the extraction plan as JSON instead of writing "
                     "requirement files."},
            {"name": "out", "flag": "--out", "consumer": "none recorded",
             "type": "str",
             "help": "With --plan: write the plan JSON here ('-' or omitted "
                     "= stdout)."},
            {"name": "md_glob", "flag": "--md-glob",
             "consumer": "none recorded", "type": "str",
             "help": "With --plan: also scan these non-code globs for "
                     "capabilities (repeatable)."},
            {"name": "wipe", "flag": "--wipe", "consumer": "none recorded",
             "type": "bool",
             "help": "Hard-reset: delete all non-generated requirements and "
                     "strip membership tags from source files before "
                     "re-extracting."},
            {"name": "minimal", "flag": "--minimal", "type": "bool",
             "consumer": "docs/commands.md",
             "help": "Skip planning, release, MCP and site scaffolding."},
            {"name": "no_site", "flag": "--no-site",
             "consumer": [
                 "plugin/skills/requirement-manager/references/site.md",
             ],
             "type": "bool",
             "help": "Skip the final site step (scaffolding "
                     "docs/architecture.html)."},
            {"name": "watch", "flag": "--watch",
             "consumer": [
                 "docs/commands.md",
                 "docs/stability.md",
             ],
             "type": "str",
             "help": "Print draft suggestions for code files changed since "
                     "this git ref, and the commit subjects in between. "
                     "Writes nothing and exits 0."},
            {"name": "propose", "flag": "--propose",
             "consumer": [
                 "docs/commands.md",
                 "docs/stability.md",
             ],
             "type": "str",
             "help": "Print one requirement draft from this description. "
                     "status stays draft. Writes nothing."},
            {"name": "propose_files", "flag": "--propose-files",
             "consumer": "docs/commands.md",
             "type": "str",
             "help": "With --propose: comma-separated paths the draft is "
                     "about."},
        ],
    },
    "gate": {
        "summary": (
            "The commit/CI verdict. Bare, it verifies that every code tag "
            "resolves to a real requirement, that every confirmed requirement "
            "has at least one implements: member, and that drift has not been "
            "introduced since the last sync, then checks requirement "
            "readability and map freshness. Exits non-zero on link-sync errors "
            "only. Never writes anything. Three mode flags report on the "
            "verdict's own subject instead of running it: --audit for the "
            "whole problem report, --risk for what to do next, --show for one "
            "requirement's dossier. Every other question is `ask`. "
        ),
        "arg": None,
        "params": [
            {"name": "mode_audit", "flag": "--audit",
             "consumer": [
                 "plugin/skills/requirement-manager/SKILL.md",
                 "plugin/scripts/reqmap_engine/mcp.py",
             ],
             "type": "bool",
             "help": "Print every pass that discovers a problem as one "
                     "report: the gate, corpus risk, duplicate contracts and "
                     "tag coverage. The exit code still comes from the gate "
                     "alone."},
            {"name": "mode_risk", "flag": "--risk",
             "consumer": [
                 "plugin/skills/requirement-manager/SKILL.md",
                 "plugin/scripts/reqmap_engine/mcp.py",
             ],
             "type": "bool",
             "help": "Print the corpus risk snapshot and the actionable "
                     "signals, most urgent first."},
            {"name": "mode_show", "flag": "--show",
             "consumer": [
                 "plugin/skills/requirement-manager/references/mcp.md",
                 "plugin/scripts/reqmap_engine/mcp.py",
             ],
             "type": "str",
             "help": "Print one requirement's dossier: intent, contract, "
                     "dependencies both ways, code members with file:line, "
                     "open questions and risk signals."},
            {"name": "show_all", "flag": "--all",
             "consumer": "plugin/scripts/reqmap_engine/mcp.py", "type": "bool",
             "help": "With --risk: expand every bucket instead of the top "
                     "few."},
            {"name": "untagged", "flag": "--untagged",
             "consumer": [
                 "plugin/skills/requirement-manager/references/mcp.md",
                 "plugin/scripts/reqmap_engine/mcp.py",
             ],
             "type": "bool",
             "help": "With --risk: report membership-tag coverage per "
                     "directory."},
            {"name": "as_badge", "flag": "--badge", "consumer": "none recorded",
             "type": "bool",
             "help": "With --risk: print the coherence score as a badge "
                     "string."},
            {"name": "strict", "flag": "--strict",
             "consumer": [
                 "plugin/skills/requirement-manager/SKILL.md",
                 "plugin/scripts/reqmap_engine/mcp.py",
             ],
             "type": "bool",
             "help": "Promote drift and test-link integrity warnings to "
                     "errors. Useful in CI when all requirements are "
                     "confirmed."},
            {"name": "json", "flag": "--json",
             "consumer": "plugin/scripts/reqmap_engine/mcp.py", "type": "bool",
             "help": "Emit structured JSON output instead of human-readable "
                     "text."},
            {"name": "since", "flag": "--since",
             "consumer": "plugin/scripts/reqmap_engine/mcp.py", "type": "str",
             "help": "Scope the gate to requirements whose member files "
                     "changed since this git ref (e.g. 'main', 'HEAD~1')."},
            {"name": "no_lint", "flag": "--no-lint",
             "consumer": "check/action.yml", "type": "bool",
             "help": "Skip the requirement readability check."},
            {"name": "no_map_check", "flag": "--no-map-check",
             "consumer": "check/action.yml", "type": "bool",
             "help": "Skip the committed-map freshness check."},
            {"name": "full", "flag": "--full", "type": "bool",
             "help": "Run every gate rule and print every readability "
                     "warning. Bare, the gate runs only the rules that say a "
                     "link, the drift baseline or the committed map is "
                     "broken, and prints readability errors only."},
        ],
    },
    "ask": {
        "summary": (
            "Ask the corpus a question without running the verdict. Read-only, "
            "never writes, and its exit code is the question's, never the "
            "gate's: --search ranks requirements by relevance, --dupes ranks "
            "overlapping contracts, --design reviews the code against the OOP "
            "pillars, --review emits the machine-readable review plan, --bugs "
            "lists the known bugs by module. Exactly "
            "one mode per call. Since v8.0.0, `gate` refuses these flags and "
            "names `ask`. "
        ),
        "arg": None,
        "consumer": [
            "plugin/skills/requirement-manager/SKILL.md",
            "plugin/skills/requirement-quality-review/SKILL.md",
            "plugin/scripts/reqmap_engine/mcp.py",
        ],
        "params": [
            {"name": "mode_search", "flag": "--search",
             "consumer": [
                 "plugin/skills/requirement-manager/references/mcp.md",
                 "plugin/scripts/reqmap_engine/mcp.py",
             ],
             "type": "str",
             "help": "Rank requirements by lexical relevance to a free-text "
                     "query."},
            {"name": "mode_dupes", "flag": "--dupes",
             "consumer": [
                 "plugin/skills/requirement-manager/SKILL.md",
                 "plugin/scripts/reqmap_engine/mcp.py",
             ],
             "type": "bool",
             "help": "Rank requirement pairs whose contracts overlap, most "
                     "similar first."},
            {"name": "mode_design", "flag": "--design",
             "consumer": [
                 "plugin/skills/requirement-manager/SKILL.universal.md",
             ],
             "type": "bool",
             "help": "Advisory design review of the code: encapsulation, "
                     "abstraction, inheritance and polymorphism candidates "
                     "plus file length and line width, grouped by pillar. "
                     "Read-only, exit 0, never the gate."},
            {"name": "mode_review", "flag": "--review",
             "consumer": [
                 "plugin/skills/requirement-quality-review/SKILL.md",
                 "plugin/scripts/reqmap_engine/mcp.py",
             ],
             "type": "str",
             "help": "Emit the deterministic review plan as JSON: for one "
                     "requirement, or with no id for the whole corpus."},
            {"name": "mode_bugs", "flag": "--bugs",
             "consumer": "docs/commands.md", "type": "bool",
             "help": "List the known bugs by module, highest priority first: "
                     "`requirements/bugs/*.md` and any file `BUG_SOURCES` "
                     "names. Takes --module and --prio."},
            {"name": "module", "flag": "--module",
             "consumer": "docs/commands.md", "type": "str",
             "help": "With --bugs: only modules whose name contains this, "
                     "ignoring case, diacritics and punctuation."},
            {"name": "prio", "flag": "--prio",
             "consumer": "docs/commands.md", "type": "str",
             "help": "With --bugs: only these priorities, as P1 or P0,P1."},
            {"name": "mode_i18n", "flag": "--i18n", "consumer": "none recorded",
             "type": "bool",
             "help": "Removed in v8.2.0 (ADR-0047): accepted and ignored, "
                     "refused from v9.0.0."},
            {"name": "top", "flag": "--top",
             "consumer": "plugin/scripts/reqmap_engine/mcp.py", "type": "int",
             "help": "With --search or --dupes: how many results to print."},
            {"name": "threshold", "flag": "--threshold",
             "consumer": "plugin/scripts/reqmap_engine/mcp.py", "type": "str",
             "help": "With --dupes: override the similarity threshold."},
            {"name": "json", "flag": "--json",
             "consumer": "plugin/scripts/reqmap_engine/mcp.py", "type": "bool",
             "help": "Emit structured JSON output instead of human-readable "
                     "text."},
        ],
    },
    "sync": {
        "summary": (
            "The write path. Rescan code members, advance the drift baseline, "
            "and regenerate the map, the findings file and the generated "
            "integration artifacts in one step. Run after editing requirement "
            "files or tagging new code members. --accept-drift is required "
            "when a confirmed or implemented contract changed. "
       
        ),
        "arg": None,
        "params": [
            {"name": "mode_retire", "flag": "--retire",
             "consumer": "none recorded", "type": "list",
             "help": "Take these requirements out of service instead of "
                     "confirming them. Accepts one id or many; a batch "
                     "retires in an order computed from the graph, under one "
                     "working-tree check. Prints the blast radius; writes "
                     "nothing without --apply."},
            {"name": "mode_release", "flag": "--release",
             "consumer": [
                 "docs/planning.md",
                 "plugin/scripts/reqmap_engine/release.py",
                 "plugin/scripts/reqmap_engine/mcp.py",
             ],
             "type": "str",
             "help": "Cut a release instead of syncing: the next version "
                     "planned in _planning.json above what is already "
                     "declared, or the vX.Y.Z named here. Prints the plan - "
                     "version files to bump, the CHANGELOG entry, the "
                     "milestone the plan drops - and writes nothing without "
                     "--apply. With --json it also reports the declared "
                     "version, whether its tag exists and its notes, which "
                     "is what a release workflow reads."},
            {"name": "delete", "flag": "--delete", "consumer": "none recorded",
             "type": "bool",
             "help": "With --retire: also remove the block, its lock entries "
                     "and its membership tags. Never a function body."},
            {"name": "do_apply", "flag": "--apply",
             "consumer": [
                 "docs/planning.md",
                 "plugin/scripts/reqmap_engine/mcp.py",
             ],
             "type": "bool",
             "help": "With --retire or --release: actually write the change. "
                     "Without it, the run is a dry report."},
            {"name": "force", "flag": "--force", "consumer": "none recorded",
             "type": "bool",
             "help": "With --retire: proceed even though dependents still "
                     "point at this requirement, or the working tree is "
                     "dirty. Dependents that are already deprecated, and "
                     "those retired in the same call, never block."},
            {"name": "findings", "flag": "--findings",
             "consumer": "none recorded", "type": "bool",
             "help": "Also regenerate the aggregated open-questions file."},
            {"name": "attach", "flag": "--attach",
             "consumer": [
                 "plugin/skills/requirement-manager/SKILL.md",
                 "plugin/skills/requirement-manager/references/site.md",
             ],
             "type": "str",
             "help": "HTML page to refresh the site's engine-owned regions "
                     "in (scaffolds it if absent). Without it, `sync` "
                     "refreshes docs/architecture.html when that exists."},
            {"name": "accept_drift", "flag": "--accept-drift",
             "consumer": [
                 "plugin/skills/requirement-manager/SKILL.md",
                 "plugin/scripts/reqmap_engine/mcp.py",
             ],
             "type": "str",
             "help": "Explicitly advance the baseline when a confirmed or "
                     "implemented contract changed. Required when those "
                     "contracts differ from the lock; sync exits non-zero "
                     "without it. Takes an optional reason, recorded in "
                     "requirements/_driftlog.json so the waiver and its "
                     "justification land in the diff."},
            {"name": "strict", "flag": "--strict", "consumer": "none recorded",
             "type": "bool",
             "help": "Promote drift and test-link integrity from warn to "
                     "error."},
            {"name": "json", "flag": "--json",
             "consumer": [
                 "plugin/scripts/reqmap_engine/release.py",
                 "plugin/scripts/reqmap_engine/mcp.py",
             ],
             "type": "bool",
             "help": "With --retire or --release: emit the plan as JSON."},
            {"name": "audit_plan", "flag": "--audit-plan",
             "consumer": "plugin/skills/requirement-manager/references/audit.md",
             "type": "bool",
             "help": "Write an audit plan to requirements/_audit.json instead "
                     "of syncing: a ranked set and a seeded random set of "
                     "confirmed requirements, and the decision bands. Written "
                     "once; an existing file is never replaced (ADR-0076)."},
            {"name": "ranked", "flag": "--ranked",
             "consumer": "plugin/skills/requirement-manager/references/audit.md",
             "type": "int",
             "help": "With --audit-plan: how many requirements to rank by "
                     "risk (default 25)."},
            {"name": "audit_random", "flag": "--random",
             "consumer": "plugin/skills/requirement-manager/references/audit.md",
             "type": "int",
             "help": "With --audit-plan: how many to draw at random from the "
                     "rest (default 25)."},
            {"name": "seed", "flag": "--seed",
             "consumer": "plugin/skills/requirement-manager/references/audit.md",
             "type": "int",
             "help": "With --audit-plan: the seed of the random draw "
                     "(default: today as YYYYMMDD)."},
            {"name": "mode_bug", "flag": "--bug",
             "consumer": "app/src/views/problems/BugsPanel.jsx", "type": "str",
             "help": "Add one bug to the module's file under "
                     "`requirements/bugs/` instead of syncing, creating the "
                     "file if needed. Needs --module; a title the module "
                     "already holds needs --force. Run `sync` after it to "
                     "show the bug on the map."},
            {"name": "module", "flag": "--module",
             "consumer": "app/src/views/problems/BugsPanel.jsx", "type": "str",
             "help": "With --bug: the module the bug belongs to, which names "
                     "its file."},
            {"name": "prio", "flag": "--prio",
             "consumer": "app/src/views/problems/BugsPanel.jsx", "type": "str",
             "help": "With --bug: P0 critical, P1 high, P2 medium (the "
                     "default), P3 low or P4 minor; `*` after it marks an "
                     "estimate no person has confirmed."},
            {"name": "date", "flag": "--date",
             "consumer": "app/src/views/problems/BugsPanel.jsx", "type": "str",
             "help": "With --bug: the day it was found, YYYY-MM-DD (default: "
                     "today)."},
            {"name": "where", "flag": "--where",
             "consumer": "app/src/views/problems/BugsPanel.jsx", "type": "str",
             "help": "With --bug: where it is, usually `file:line`."},
            {"name": "why", "flag": "--why",
             "consumer": "app/src/views/problems/BugsPanel.jsx", "type": "str",
             "help": "With --bug: why it matters."},
            {"name": "source", "flag": "--source",
             "consumer": "app/src/views/problems/BugsPanel.jsx", "type": "str",
             "help": "With --bug: where the report came from."},
            {"name": "mode_fix", "flag": "--fix",
             "consumer": "plugin/skills/requirement-manager/references/bugs.md",
             "type": "str",
             "help": "Close one bug instead of syncing: move its row to the "
                     "register, `requirements/bugs/_fixed.md`, as `FILE:REF` "
                     "or `FILE REF`. A plain `sync` does the same for every "
                     "`Fixes-bug: ID` trailer in the commit history."},
            {"name": "commit", "flag": "--commit",
             "consumer": "plugin/skills/requirement-manager/references/bugs.md",
             "type": "str",
             "help": "With --fix: the commit that fixed it (default: HEAD)."},
            {"name": "bug_version", "flag": "--version",
             "consumer": "plugin/skills/requirement-manager/references/bugs.md",
             "type": "str",
             "help": "With --fix: the version that fixed it (default: the "
                     "repository's version file, when it has one)."},
            {"name": "note", "flag": "--note",
             "consumer": "plugin/skills/requirement-manager/references/bugs.md",
             "type": "str",
             "help": "With --fix: close without a fix, and say why."},
        ],
    },
    "clarify": {
        "summary": (
            "Ask what a requirement has not answered yet: vague terms with no "
            "threshold, numbers with no unit, clauses "
            "with no case, a missing failure path. Read-only, always exit 0, "
            "never a gate rule. --decompose is the write half of the same "
            "question: it splits a requirement into code-rung children along "
            "the bold group labels in its Description (--apply writes), or "
            "scaffolds one draft per over-long clause when it has none. Run it "
            "before implementing, so the ambiguity is resolved in the "
            "requirement instead of guessed in code. "
       
        ),
        "arg": "AREA-NAME-NNN",
        "consumer": [
            "plugin/skills/requirement-manager/SKILL.md",
            "plugin/skills/requirement-manager/references/assistant-steps.md",
            "plugin/scripts/reqmap_engine/mcp.py",
        ],
        "params": [
            {"name": "decompose", "flag": "--decompose",
             "consumer": "plugin/skills/requirement-manager/SKILL.md",
             "type": "bool",
             "help": "Split a requirement into code-rung children along the "
                     "bold group labels its author wrote in the Description; "
                     "--apply writes them and never edits the parent. With "
                     "no id, every requirement carrying groups. A "
                     "requirement with no groups falls back to one draft per "
                     "over-long clause."},
            {"name": "levels", "flag": "--levels", "consumer": "none recorded",
             "type": "bool",
             "help": "Propose a V-model rung for every requirement that "
                     "declares no `level:`, plus the rungs above: one draft "
                     "`ARCH-<FAMILY>-001` per id-prefix family, "
                     "`SYS-NEEDS-A-NAME-001` at the apex, and the "
                     "`satisfies:` edges between them. --apply writes all of "
                     "it, each line marked `level_source: auto`."},
            {"name": "as_json", "flag": "--json", "type": "bool",
             "consumer": [
                 "plugin/skills/requirement-manager/references/mcp.md",
                 "plugin/scripts/reqmap_engine/mcp.py",
             ],
             "help": "Emit the questions as JSON for an agent to answer."},
            {"name": "do_apply", "flag": "--apply", "type": "bool",
             "consumer": "plugin/skills/requirement-manager/SKILL.md",
             "help": (
                 "With --decompose or --levels: write the proposal instead of "
                 "printing it."
             )},
        ],
    },
    # `tool: False` — a server is not a function to call, so the generated
    # function-calling schema leaves it out; the help text and SKILL.md still
    # document it.
    "mcp": {
        "summary": (
            "Serve this repository's requirements to an AI assistant over the "
            "Model Context Protocol (stdio). Each tool is one reqmap "
            "invocation in a fresh process. Read-only unless --allow-writes."
        ),
        "arg": None,
        "consumer": [
            ".mcp.json",
            ".vscode/mcp.json",
        ],
        "tool": False,
        "params": [
            {"name": "allow_writes", "flag": "--allow-writes",
             "consumer": "none recorded", "type": "bool",
             "help": "Also offer the tools that write: sync and release."},
        ],
    },
}


# Which moment of the workflow each verb belongs to. The registry is the
# CLI's single source of truth, so the grouping the help text and the viewer
# both show is declared here once rather than restated in each surface.
COMMAND_GROUPS = (
    ("author", ("init", "clarify")),
    ("build", ("sync",)),
    ("read", ("gate", "ask", "mcp")),
)


# Tiers, read off the automated callers rather than chosen by taste.
# CORE-path: what `.githooks/pre-commit` and CI's `gate-and-tests` job run
# (`gate --full`; the global --root/--code are not registry flags), bare
# `sync` (the write path the hook's failure message sends the author to)
# and bare `init` (the bootstrap). Every other verb or flag is OPTIONAL and
# carries a `"consumer"`: where a real use is written down (a workflow, a
# hook, the shipped skill, a config, a named repo), or "none recorded".
# `consumer` is registry-only: no generated artifact reads it.
CORE_PATH = {"init": (), "gate": ("--full",), "sync": ()}
