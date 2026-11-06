"""`RM036`: an `[[ID]]` in a Description that names no requirement.

A binding clause that reads `see [[REQ-X-012]]` hands its obligation to
another file. When that file is deleted the clause still reads as a
contract and the gate still passes: `depends_on:` and code tags were
checked, prose links never were. That is how a rejected split once
destroyed nine confirmed contracts with a green gate — the parents held
only pointers, and the children were deleted.

Narrow on purpose, so it fires on the broken link and nothing else: only
the Description is read (the normative text), inline code spans are
skipped (`[[ID]]` written as an example), and only an id-shaped target
counts, so a note like `[[child]]` is prose. Warn, like RM034: the link is
broken, the build is not.
"""
import re

from . import docclaims  # noqa: F401 — RM036 registers after RM035
from .model import gate_rule
from .sections import CONTRACT_LABELS, _section_lines
from .tags import _ID_PAT

_ID_LINK_RE = re.compile(r"\[\[(" + _ID_PAT + r")\]\]")


def dangling_links(body, known):  # implements: REQ-CHECK-1035
    """The id-shaped `[[ID]]` targets in `body`'s Description that are not
    in `known`, in order of first appearance."""
    out = []
    for raw in _section_lines(body, CONTRACT_LABELS, raw=True):
        for target in _ID_LINK_RE.findall(re.sub(r"`[^`]*`", "", raw)):
            if target not in known and target not in out:
                out.append(target)
    return out


@gate_rule("RM036", "warn")
def _dangling_wikilink_rule(ctx):  # implements: REQ-CHECK-1035
    for rid in sorted(ctx.reqs):
        missing = dangling_links(ctx.reqs[rid]["body"], ctx.reqs)
        if missing:
            yield rid, ("{}: its Description links {} — no such "
                        "requirement. The clause that pointed there now "
                        "binds nothing: restore the text, or the "
                        "requirement it named".format(
                            rid, ", ".join(
                                "[[{}]]".format(t) for t in missing)))
