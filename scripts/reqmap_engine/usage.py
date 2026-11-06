"""What `reqmap.py`, `reqmap.py --help` and `reqmap.py <verb> --help` print.

Rendered from the command registry, so the help cannot name a flag the parser
does not take or a verb it refuses. Loaded only for those three calls: the
parser itself stays flat, and no other command pays for this module.
"""
import sys
import textwrap

from .cliflags import WORKSPACE_FLAGS
from .commands import COMMAND_GROUPS, COMMANDS

# Verbs an assistant calls more than a person types: marked, never hidden.
ASSISTANT_VERBS = ("ask", "mcp")

START = (
    "Start here:",
    "  reqmap.py init --minimal   set up requirements/ in a new repo",
    "  reqmap.py gate             the verdict: do code and specs still agree?",
    "  reqmap.py gate --risk      what to do next, most important first",
    "  reqmap.py sync             rebuild the lock and the map after a change",
)


def _headline(text):
    """The summary's opening phrase: up to its first full stop or colon."""
    return text.split(". ")[0].split(": ")[0].rstrip(".")


def _verb_label(name):
    arg = COMMANDS[name].get("arg")
    return name + (" " + arg if arg else "")


def overview():  # implements: REQ-CMDREGISTRY-1085
    """The top-level help: every verb on one line, grouped, then where to
    start and how to see one verb's flags."""
    lines = ["usage: reqmap.py <verb> [flags]", ""]
    for group, names in COMMAND_GROUPS:
        lines.append(group.capitalize() + ":")
        for name in names:
            note = " (for assistants)" if name in ASSISTANT_VERBS else ""
            lines += textwrap.wrap(
                _headline(COMMANDS[name]["summary"]) + note, 78,
                initial_indent="  {:<24} ".format(_verb_label(name)),
                subsequent_indent=" " * 27)
        lines.append("")
    lines.extend(START)
    lines += ["", "`reqmap.py <verb> --help` lists that verb's flags."]
    return "\n".join(lines)


def verb_help(name):  # implements: REQ-CMDREGISTRY-1085
    """One verb's help: its summary, its own flags and the workspace flags
    every verb takes. Nothing another verb owns."""
    spec = COMMANDS[name]
    lines = ["usage: reqmap.py {} [flags]".format(_verb_label(name)), ""]
    lines += textwrap.wrap(spec["summary"], 78) + ["", "Flags:"]
    for p in spec["params"]:
        value = "" if p.get("type") == "bool" else " <{}>".format(p["type"])
        lines.append("  " + p["flag"] + value)
        lines += textwrap.wrap(p.get("help", ""), 72,
                               initial_indent="      ",
                               subsequent_indent="      ")
    lines += ["", "Workspace flags: " + " ".join(WORKSPACE_FLAGS)]
    return "\n".join(lines)


def intercept(argv):  # implements: REQ-CMDREGISTRY-1085
    """Answer a bare call or a help request before the parser runs. A bare
    call prints the overview on stderr and keeps exit 2, so a script that
    forgot its verb still fails; a help request prints on stdout, exit 0."""
    if not argv:
        print(overview() + "\n\nreqmap: choose a verb.", file=sys.stderr)
        return 2
    verb = next((a for a in argv if a in COMMANDS), None)
    print(verb_help(verb) if verb else overview())
    return 0
