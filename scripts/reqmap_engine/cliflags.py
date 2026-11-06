"""Every `--flag` the CLI accepts, registered on a parser argparse already
built.

Lifted out of `reqmap.py` because it is not the command line's shape, only its
surface: mechanical `add_argument` calls that pushed the CLI module past the
500-line bar `ask --design` holds every engine file to. `reqmap.py` keeps what
reads as the command line — the floor check, the parser assembly, dispatch.
No flag carries help text here: `commands.py` holds it and `usage.py` renders
it, so the two cannot drift apart.
"""
import sys

from .commands import COMMANDS
from .similar import _threshold_arg


def _add_workspace_flags(ap):
    # implements: ARCH-CMDREGISTRY-033  # implements: REQ-EXTREPO-1094
    ap.add_argument("--root", default=".")
    ap.add_argument("--reqs", default=None)
    ap.add_argument("--code", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--md-glob", action="append", default=None)


def _add_query_flags(ap):
    # implements: ARCH-CMDREGISTRY-033
    ap.add_argument("--all", dest="show_all", action="store_true")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--no-lint", dest="no_lint", action="store_true")
    ap.add_argument("--full", dest="full", action="store_true")
    ap.add_argument("--no-map-check", dest="no_map_check", action="store_true")
    ap.add_argument("--findings", action="store_true")
    ap.add_argument("--untagged", action="store_true")
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--delete", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--decompose", action="store_true")
    ap.add_argument("--levels", action="store_true")
    ap.add_argument("--threshold", type=_threshold_arg, default=None)
    ap.add_argument("--top", type=int, default=None)
    ap.add_argument("--json", dest="as_json", action="store_true")
    ap.add_argument("--badge", dest="as_badge", action="store_true")
    ap.add_argument("--accept-drift",
                    dest="accept_drift", nargs="?", const=True,
                    default=False, metavar="REASON")
    ap.add_argument("--since", metavar="REF")
    ap.add_argument("--wipe", action="store_true")
    ap.add_argument("--watch", metavar="REF", default=None)
    ap.add_argument("--propose", metavar="TEXT", default=None)
    ap.add_argument("--propose-files", dest="propose_files", default=None)

def _add_todo_and_mode_flags(ap):
    # implements: ARCH-CMDREGISTRY-033
    ap.add_argument("--cache", action="store_true")
    ap.add_argument("--attach", default=None)
    ap.add_argument("--minimal", action="store_true")
    ap.add_argument("--no-site", dest="no_site", action="store_true")
    ap.add_argument("--allow-writes", dest="allow_writes", action="store_true")
    ap.add_argument("--apply", dest="do_apply", action="store_true")
    # Mode flags: the read-only queries that used to be their own verbs.
    # The work they do is unchanged — only the entry point moved: `gate`
    # keeps the verdict and the reports on it, `ask` every other question
    # (ADR-0044), `sync` every write.
    ap.add_argument("--audit", dest="mode_audit", action="store_true")
    ap.add_argument("--risk", dest="mode_risk", action="store_true")
    ap.add_argument("--i18n", dest="mode_i18n", action="store_true")
    ap.add_argument("--show", dest="mode_show", metavar="ID", nargs="?",
                    default=None, const="")
    ap.add_argument("--search",
                    dest="mode_search", metavar="QUERY", nargs="?",
                    default=None, const="")
    ap.add_argument("--review", dest="mode_review", metavar="ID", nargs="?",
                    default=None, const="")
    ap.add_argument("--dupes", dest="mode_dupes", action="store_true")
    ap.add_argument("--design", dest="mode_design", action="store_true")
    ap.add_argument("--retire", dest="mode_retire", metavar="ID", nargs="*",
                    default=None)
    ap.add_argument("--release", dest="mode_release", metavar="VERSION",
                    nargs="?", const=True,
                    default=None)
    # implements: REQ-AUDITRUN-1105
    ap.add_argument("--audit-plan", dest="audit_plan", action="store_true")
    ap.add_argument("--ranked", type=int, default=None)
    ap.add_argument("--random", dest="audit_random", type=int, default=None)
    ap.add_argument("--seed", type=int, default=None)
    # implements: REQ-BUGS-1119  # implements: REQ-BUGS-1120
    ap.add_argument("--bug", dest="mode_bug", metavar="TITLE", default=None)
    ap.add_argument("--bugs", dest="mode_bugs", action="store_true")
    ap.add_argument("--module", default=None)
    ap.add_argument("--prio", default=None)
    ap.add_argument("--date", default=None)
    ap.add_argument("--where", default=None)
    ap.add_argument("--why", default=None)
    ap.add_argument("--source", default=None)
    # implements: REQ-BUGS-1127
    ap.add_argument("--fix", dest="mode_fix", metavar="ID", default=None)
    ap.add_argument("--commit", default=None)
    ap.add_argument("--version", dest="bug_version", default=None)
    ap.add_argument("--note", default=None)


# The flags every verb accepts: where the workspace is, and whether to
# cache the scan.
WORKSPACE_FLAGS = ("--root", "--reqs", "--code", "--cache")


def _owners(flag):
    """The verbs whose registry entry gives them `flag`."""
    return [v for v in COMMANDS
           if any(p["flag"] == flag for p in COMMANDS[v]["params"])]


def _foreign_flags(ap, a, verb):  # implements: REQ-CMDREGISTRY-1031
    """The flags given on this call that `verb` does not own. The parser
    is flat, so the registry is what says which verb a flag belongs to."""
    owned = set(WORKSPACE_FLAGS) | {p["flag"] for p in COMMANDS[verb]["params"]}
    out = []
    for action in ap._actions:
        longs = [o for o in action.option_strings if o.startswith("--")]
        if not longs or longs[0] in owned or action.dest == "help":
            continue
        if getattr(a, action.dest, action.default) != action.default:
            out.append(longs[0])
    return out


def _verb_scope(ap, a):  # implements: REQ-CMDREGISTRY-1031
    """Refuse a flag the registry gives another verb, on every verb,
    naming the verb that owns it. `gate`'s old spellings of `ask`'s
    questions are refused the same way since v8.0.0 (ADR-0044). Returns
    2 when the call is refused, else 0."""
    foreign = _foreign_flags(ap, a, a.cmd)
    if not foreign:
        return 0
    hints = ["{} is `{}`'s".format(f, "`/`".join(_owners(f)) or "no verb")
             for f in foreign]
    print("reqmap {0}: not a `{0}` flag: {1}. `{0}` takes {2}".format(
        a.cmd, "; ".join(hints),
        " ".join(p["flag"] for p in COMMANDS[a.cmd]["params"]) or "no flags"),
        file=sys.stderr)
    return 2
