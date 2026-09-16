"""`gate --show`: one requirement's consolidated dossier."""

from .model import RISK_ADVICE, _as_list
from .risk import _risk_signals
from .sections import CONTRACT_LABELS, _from_any
from .text import _bullets, _distinct_intent, _req_title, _verify_bullets


def cmd_show(ws, cap_id, levels=None):
    # implements: ARCH-SHOW-015  # implements: ARCH-VLEVEL-037  # implements: REQ-SHOW-917
    # implements: REQ-SHOW-918  # implements: REQ-SHOW-919  # implements: REQ-TRACE-935
    # implements: REQ-VLEVEL-946
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

    # implements: ARCH-TRACE-020
    # upstream traceability: only shown when the requirement participates in it,
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
