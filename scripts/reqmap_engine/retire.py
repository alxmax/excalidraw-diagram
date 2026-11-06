"""`sync --retire`: the blast-radius plan and the command that runs it."""
import json, os

from .git import _git_dirty
from .model import _as_list
from .retireapply import _apply_one_retirement
from .text import _req_title


# ---------- retire: take a requirement out of service, code included ----------
def _retire_plan(reqs, members, cap_id):
    # implements: ARCH-RETIRE-064  # implements: REQ-RETIRE-960
    """Everything that points at `cap_id`, computed before anything is touched:
    dependents, children, members by file, the files where it is the ONLY tagged
    requirement (whose code is now unreferenced), and its cross-references in
    prose.
    
    The blast radius is the whole point. A requirement nobody depends on is a
    local edit; one with three dependents is a conversation, and the caller is
    told which."""
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
    # `depends_on` runs consumer -> foundation: a button declares the capability
    # it needs, never the reverse. So retiring a consumer cannot break anything
    # downstream, but it CAN stand a capability down: if this requirement was
    # the last thing pointing at one of its dependencies, that dependency now
    # has no consumer, and its code is a dead-code candidate. Nothing else in
    # the engine notices that, because the tag is still there and the gate is
    # satisfied.
    stranded = []
    for dep in _as_list(r["meta"].get("depends_on")) if r else []:
        if dep not in reqs:
            continue
        remaining = [rid for rid, rr in reqs.items()
                     if rid != cap_id
                     and dep in _as_list(rr["meta"].get("depends_on"))]
        if not remaining:
            stranded.append(dep)
    return {
        "id": cap_id,
        "title": _req_title(r["body"], cap_id) if r else "",
        "status": (r["meta"].get("status") if r else None),
        "path": (r.get("path") if r else None),
        "dependents": sorted(
            rid for rid, rr in reqs.items()
            if cap_id in _as_list(rr["meta"].get("depends_on"))),
        "children": sorted(
            rid for rid, rr in reqs.items()
            if cap_id in _as_list(rr["meta"].get("satisfies"))),
        "members": [{"role": role, "file": fp, "line": ln}
                    for role, fp, ln in mem],
        "exclusive_files": sorted(mine - others),
        "shared_files": sorted(mine & others),
        "referenced_by": refs,
        "leaves_unused": sorted(stranded),
    }


def _retire_blockers(reqs, plan, batch=()):  # implements: REQ-RETIRE-961
    """The dependents and children that actually stand in the way.

    Two kinds never do. A `deprecated` requirement is already out of
    service and exempt from every gate, so a pointer from one cannot
    make a retirement unsafe. A requirement being retired in the same
    call is handled by the ORDER, not by a refusal. Without both
    filters a class of N retires in N-1 forced writes: step two is
    blocked by step one, which is itself already gone."""
    return [rid for rid in plan["dependents"] + plan["children"]
            if rid not in batch
            and (reqs[rid]["meta"].get("status") if rid in reqs else None)
            != "deprecated"]


def _retire_order(reqs, ids):  # implements: REQ-RETIRE-963
    """The order a batch is safe to retire in: consumers before what
    they consume.

    `depends_on` runs consumer -> foundation and `satisfies` runs
    child -> parent, so a requirement is safe to take out only once
    everything pointing AT it has gone. Kahn over the in-batch pointers
    only; input order is preserved inside a layer, and a cycle (which
    the gate reports on its own) leaves its members at the end rather
    than dropping them from the batch."""
    batch = set(ids)
    first = {rid: set() for rid in ids}
    # rid -> batch members that must precede it
    for rid in ids:
        meta = reqs[rid]["meta"] if rid in reqs else {}
        for target in (_as_list(meta.get("depends_on"))
                      + _as_list(meta.get("satisfies"))):
            if target in batch and target != rid:
                first[target].add(rid)
    out, done = [], set()
    while True:
        ready = [rid for rid in ids
                 if rid not in done and not (first[rid] - done)]
        if not ready:
            break
        out.extend(ready)
        done.update(ready)
    out.extend(rid for rid in ids if rid not in done)
    return out


def _print_retire_plan(plan):  # implements: REQ-RETIRE-960
    """One requirement's blast radius, as a human reads it."""
    print("{} · {} · retire ({})".format(
        plan["id"], plan["status"], plan["mode"]))
    print(plan["title"])
    print("\nDepended on by: "
          + (", ".join(plan["dependents"]) or "(none)"))
    print("Satisfied by (children): "
          + (", ".join(plan["children"]) or "(none)"))
    print("Referenced in prose by: "
          + (", ".join(plan["referenced_by"]) or "(none)"))
    print("\nMembers in code ({}):".format(len(plan["members"])))
    for m in plan["members"]:
        print("  {:12} {}:{}".format(m["role"], m["file"], m["line"]))
    if plan["exclusive_files"]:
        print("\nFiles where this was the ONLY tagged requirement — "
              "their code is unreferenced once it goes:")
        for f in plan["exclusive_files"]:
            print("  " + f)
    if plan["shared_files"]:
        print("\nFiles shared with other requirements — only the tag "
              "line goes:")
        for f in plan["shared_files"]:
            print("  " + f)
    if plan["leaves_unused"]:
        print("\nLeft with no consumer once this goes — check whether "
              "their code is still reached:")
        for dep in plan["leaves_unused"]:
            print("  " + dep)


def _validate_retire_ids(cap_ids, reqs):
    # implements: ARCH-RETIRE-064  # implements: REQ-RETIRE-961
    # implements: REQ-RETIRE-963
    """(ids, rc) — `cap_ids` normalized to a deduped list, and the exit
    code `cmd_retire` should return immediately (already printed), or
    rc=None when the batch is valid and processing should continue."""
    ids = ([cap_ids] if isinstance(cap_ids, str)
           else list(dict.fromkeys(cap_ids)))
    if not ids:
        print("usage: reqmap sync --retire AREA-NAME-NNN [ID ...]")
        return ids, 2
    unknown = [i for i in ids if i not in reqs]
    if unknown:
        for i in unknown:
            print("no requirement with id {} (expected "
                  "requirements/{}.md)".format(i, i))
        return ids, 1
    return ids, None


def _build_retire_plans(reqs, members, order, mode, ids):
    # implements: ARCH-RETIRE-064  # implements: REQ-RETIRE-961
    # implements: REQ-RETIRE-963
    """One retire plan per id in `order`, each carrying its mode and its
    blockers computed against the whole batch."""
    plans = []
    for cap_id in order:
        plan = _retire_plan(reqs, members, cap_id)
        plan["mode"] = mode
        plan["applied"] = False
        plan["blocked_by"] = _retire_blockers(reqs, plan, set(ids))
        plans.append(plan)
    return plans


def _emit_retire_result(plans, single, mode, order, as_json, rc):
    # implements: ARCH-RETIRE-064  # implements: REQ-RETIRE-961
    # implements: REQ-RETIRE-963
    """Print the `--json` document (unless suppressed) and return `rc`."""
    if as_json:
        print(json.dumps(plans[0] if single else
                         {"mode": mode, "order": order, "plans": plans},
                         indent=2, ensure_ascii=False))
    return rc


def _refuse_if_blocked(plans, force, as_json):
    # implements: ARCH-RETIRE-064  # implements: REQ-RETIRE-961
    # implements: REQ-RETIRE-963
    """True (after recording the refusal message on every plan, and
    printing it unless --json) when the batch has a blocker and
    --force was not passed."""
    blocked = [p for p in plans if p["blocked_by"]]
    if not blocked or force:
        return False
    names = sorted({b for p in blocked for b in p["blocked_by"]})
    msg = ("refusing: {} still has {} dependent(s)/child(ren) outside "
           "this retirement — {}. Retire or re-point them first, or "
           "pass --force once you have decided.".format(
               ", ".join(p["id"] for p in blocked), len(names),
               ", ".join(names)))
    for plan in plans:
        plan["refused"] = msg
    if not as_json:
        print("\n" + msg)
    return True


def _plan_only_note(plans, mode, ids, single):
    # implements: ARCH-RETIRE-064  # implements: REQ-RETIRE-961
    # implements: REQ-RETIRE-963
    """Record (and return) the plan-only note every plan carries when
    --apply was not passed."""
    note = ("plan only — nothing was changed. Re-run with --apply to "
            "{} {}.".format(
                mode, ids[0] if single else "all {}".format(len(ids))))
    for plan in plans:
        plan["note"] = note
    return note


def cmd_retire(ws, cap_ids, delete=False, do_apply=False, force=False,
               as_json=False):
    # implements: ARCH-RETIRE-064  # implements: REQ-RETIRE-961
    # implements: REQ-RETIRE-963
    """Take a requirement — or a whole class of them — out of service.
    Without --apply this only reports the blast radius, so the
    destructive half is always preceded by a readable plan.

    Deprecating is the default and is reversible: the requirement
    stays in the corpus, exempt from the gates, and its code keeps
    working. --delete removes the block, its lock entries and its
    membership TAGS -- never a function body: deciding which code is
    now dead needs to understand the code, which this engine
    deliberately cannot do. The plan names the files where the removed
    tag was the only one, which is exactly the list a human or an
    agent needs for that second half.

    Many ids retire as ONE operation: one aggregated plan, one
    working-tree check, one --apply, in an order computed from the
    graph. A class retired one call at a time cost either a commit per
    step (the clean-tree guard) or --force on every step after the
    first (each blocked by the one already gone) — the two safeguards
    cancelled each other out on the exact case they exist for.

    `cap_ids` takes a string or a list, and a list of one behaves like
    the string: the single-requirement output and `--json` document
    are unchanged."""
    reqs, members, reqs_dir = ws.reqs, ws.members, ws.reqs_dir
    ids, rc = _validate_retire_ids(cap_ids, reqs)
    if rc is not None:
        return rc
    single = len(ids) == 1

    mode = "delete" if delete else "deprecate"
    order = _retire_order(reqs, ids)
    plans = _build_retire_plans(reqs, members, order, mode, ids)

    if not as_json:
        if not single:
            print("retire ({}) · {} requirements, in this order:".format(
                mode, len(order)))
            print("  " + " -> ".join(order) + "\n")
        for i, plan in enumerate(plans):
            if i:
                print("\n" + "-" * 60)
            _print_retire_plan(plan)

    if _refuse_if_blocked(plans, force, as_json):
        return _emit_retire_result(plans, single, mode, order, as_json, 1)

    if not do_apply:
        note = _plan_only_note(plans, mode, ids, single)
        if not as_json:
            print("\n" + note)
        return _emit_retire_result(plans, single, mode, order, as_json, 0)

    if not force and _git_dirty(os.path.dirname(reqs_dir) or "."):
        print("\nrefusing: the working tree has uncommitted changes. "
              "Commit or stash first so this is one reviewable diff, "
              "or pass --force.")
        return 1

    rc = 0
    for plan in plans:
        if _apply_one_retirement(plan, ws, single, delete, as_json):
            rc = 1
    if not as_json:
        print("  next: reqmap.py sync")
    return _emit_retire_result(plans, single, mode, order, as_json, rc)
