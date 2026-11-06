"""The rows behind the health score: the green-on-every-axis predicate
the score counts, and the requirements it leaves out (REQ-HEALTHROWS-1083).
Kept apart from `health` so the predicate and its explanation live in one
place the map and the console both read."""
from .model import _as_list

EXEMPT_KEYS = ("lint_exempt", "test_exempt", "gate_exempt")


def _is_healthy(f):
    # implements: ARCH-HEALTH-017  # implements: REQ-HEALTH-968
    """Green on every axis: the one predicate the score counts and
    the rows below explain."""
    return (f["is_confirmed"] and f["covered"]
            and (f["has_test"] or f["impl_exempt"])
            and not f["open_now"] and not f["is_drifted"])


def _health_rows(reqs, flags):
    # implements: ARCH-HEALTH-017  # implements: REQ-HEALTHROWS-1083
    """The requirements behind the score, for a reader who wants the
    rows and not just the number: every scored requirement that is not
    green, with the axes it fails, and every one carrying a waiver.
    Both are derived from the same flags the score counts, so the
    list can never disagree with the number beside it."""
    unhealthy, exempt = [], []
    for rid in sorted(flags):
        f = flags[rid]
        if f["status"] == "deprecated":
            continue
        keys = [k for k in EXEMPT_KEYS
                if _as_list(reqs[rid]["meta"].get(k))]
        if keys:
            exempt.append({"id": rid, "keys": keys})
        if _is_healthy(f):
            continue
        why = [axis for axis, failed in (
            ("not confirmed", not f["is_confirmed"]),
            ("not implemented", not f["covered"]),
            ("not tested",
             not (f["has_test"] or f["impl_exempt"])),
            ("open question", f["open_now"]),
            ("drift", f["is_drifted"])) if failed]
        unhealthy.append({"id": rid, "status": f["status"],
                          "why": why})
    return unhealthy, exempt
