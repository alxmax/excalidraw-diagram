"""The gate verdict: cmd_check, over the rules and the workspace."""
import json, os, sys

from . import ENGINE_DIR, MAP_ENGINE_VERSION, config as cfg
from .author import _write_frontmatter_status
from .clarify import blocking_question_rules
from .findings import collect_findings
from .git import _git
from .locks import (
    DriftlogUnusable, compute_member_hashes, load_clarifylock, lock_path,
    record_accepted_drift, save_clarifylock, save_lock,
    save_memberlock, warn_if_stale
)
from .mapjson import _path_key, _since_changed_files
from .model import Finding, GateResult, GATE_RULES
from .registry import _check_integration_fresh
from .rulesrepo import DRIFT_RULES
from . import axis  # noqa: F401 — registers RM032 after every rule in `rules`
from . import docclaims  # noqa: F401 — registers RM035, same reason as `axis`
from . import wikilinks  # noqa: F401 — registers RM036, same reason as `axis`
from . import planinput  # noqa: F401 — registers RM037, same reason as `axis`
from .sections import _legacy_schema_ids
from .workspace import GateContext, Workspace


class GateMode(tuple):  # implements: ARCH-CHECK-006
    """How one gate run reports and what it looks at: `as_json` prints one JSON
    document, `since` scopes the rules to requirements whose members changed
    since a git ref, `quiet` runs only DEFAULT_RULES (the bare `gate` verb)."""
    __slots__ = ()

    def __new__(cls, as_json=False, since=None, quiet=False):
        return tuple.__new__(cls, (as_json, since, quiet))

    as_json = property(lambda self: self[0])
    since = property(lambda self: self[1])
    quiet = property(lambda self: self[2])


# The rules a bare `gate` runs (ADR-0049): every error, and the warnings that
# say a link or the drift baseline is broken. Everything else is advice, and
# advice printed on every commit is read by nobody: one consumer carried 18
# warnings a commit, 16 of them RM007, for three weeks. `gate --full` and
# `gate --audit` run the whole registry.
DEFAULT_RULES = frozenset((
    "RM001", "RM002", "RM003", "RM006",                    # errors
    "RM005", "RM012", "RM023", "RM033", "RM034", "RM036",  # a link is broken
    "RM016", "RM018", "RM019", "RM020",                    # the drift baseline
    "RM022", "RM027",                                      # the committed map
    "RM037",                                               # the plan's input
))


def run_gate_rules(ctx, strict=False):
    # implements: ARCH-RULES-059  # implements: REQ-RULES-947
    # implements: REQ-RULES-948  # implements: REQ-RULES-989
    """Run every registered rule over `ctx` -> (errors, warns) as Finding lists,
    in registry order. A rule's `strict` flag promotes its findings to errors
    under `--strict`, except RM012 on a non-confirmed requirement, which stays a
    plain warn so a draft-heavy consumer's strict CI cannot start failing on it.
    A requirement whose `gate_exempt:` names the rule's code is skipped for that
    rule.

    `DRIFT_SEVERITY: "error"` in a repo's `_config.json` promotes the two drift
    rules for THAT repo without `--strict` and without moving anyone else's
    default. The promotion is resolved here, per run, and never written back
    onto the Rule: the registry is module state shared by two `cmd_check` calls
    inside `audit`, and a mutation would leak from the first into the second.
    `gate_exempt:` is checked before any of this, so a requirement's own
    written-down exemption still wins — a repo-wide dial must not silently
    overrule a decision made per requirement.

    A context marked `quiet` runs only DEFAULT_RULES; every other caller gets
    the whole registry, as it always did."""
    # implements: REQ-CHECK-1036
    errors, warns = [], []
    for rule in GATE_RULES:
        if ctx.quiet and rule.id not in DEFAULT_RULES:
            continue
        for rid, msg in rule.fn(ctx):
            if rid is not None and ctx.req(rid).exempt_from(rule.id):
                continue
            sev = rule.severity
            if rule.strict and strict:
                confirmed = rid is None or ctx.req(rid).status == "confirmed"
                if rule.id != "RM012" or confirmed:
                    sev = "error"
            if (sev != "error" and rule.id in DRIFT_RULES
                    and cfg.DRIFT_SEVERITY == "error"):
                sev = "error"
            (errors if sev == "error" else warns).append(
                Finding(rule.id, sev, rid, msg))
    return errors, warns


def _scope_members_since(since, code_root, members):
    # implements: ARCH-CHECK-006  # implements: ARCH-RULES-059
    # implements: REQ-CHECK-832  # implements: REQ-CHECK-833
    # implements: REQ-RULES-948
    """Narrow `members` to files changed since `since`, WARN-ing and falling
    back to the full set if git is unavailable or the ref is invalid."""
    if not since:
        return members, []
    changed = _since_changed_files(since, code_root)
    if changed is None:
        warn = Finding("RM000", "warn", None,
                       f"--since {since!r}: git diff failed or ref not found; "
                       "falling back to full scan")
        return members, [warn]
    filtered = {}
    for cap, entries in members.items():
        kept = [(role, fp, ln) for role, fp, ln in entries
                if _path_key(os.path.join(code_root, fp)) in changed]
        if kept:
            filtered[cap] = kept
    return filtered, []


def _demote_drifted_confirmed(reqs, confirmed_drift, full_members):
    # implements: ARCH-CHECK-006  # implements: ARCH-RULES-059
    # implements: REQ-CHECK-832  # implements: REQ-CHECK-833
    # implements: REQ-RULES-948
    """Demote each drifted confirmed/implemented requirement back to draft,
    printing why and which member files to re-check."""
    print("Contract changed on %d confirmed requirement(s) — status back to "
          "`draft`, because nobody has re-validated them:"
          % len(confirmed_drift))
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
            locs = ["%s:%s" % (fp, ln)
                    for (_role, fp, ln) in full_members.get(rid, ())]
            if locs:
                print("      re-check %d member(s): %s"
                      % (len(locs), ", ".join(locs)))
            else:
                print("      no members tagged — add an `implements:` tag")
        else:
            print("  WARN  %s: no `status:` line to change" % rid)
    print("  These no longer gate. Re-read the code above against the new "
          "contract,")
    print("  change whichever is wrong, then set the status back by hand — or "
          "re-run")
    print("  with --accept-drift if the edit did not change what the code must "
          "do.")


def _unchanged_since_lock(reqs, reqs_dir, rids):  # implements: REQ-PROMOTE-974
    """(the ids among `rids` whose requirement file is byte-identical to its
    copy in the commit that last wrote the lock, that commit's short sha).

    Such a file cannot have been edited since it was baselined, so a hash that
    moved moved because the HASHING did: a newer engine computes the binding
    hash differently. Demoting it would strip every confirmation a consumer
    holds on the first sync after an upgrade (one consumer, 2026-09-21: 17 of
    17). That holds only if the engine changed, and the file being unchanged
    does not show it: a lock committed with a contract edit it never took up
    leaves the same picture. The map committed beside that lock records the
    engine that wrote it, so the exception needs that engine to differ from
    this one. Fail-closed: no git, a lock never committed, a file git does not
    track (added after the lock), or no map to read all answer "edited"."""
    root = os.path.dirname(os.path.abspath(lock_path(reqs_dir)))
    sha = (_git(["log", "-1", "--format=%H", "--",
                 os.path.basename(lock_path(reqs_dir))],
                cwd=root) or "").strip()
    if not sha:
        return [], ""
    try:
        wrote = json.loads(_git(["show", sha + ":./_map.json"], cwd=root)
                           or "").get("engine_version")
    except (ValueError, AttributeError):
        wrote = None
    if not wrote or wrote == MAP_ENGINE_VERSION:
        return [], ""
    same = []
    for rid in rids:
        path = os.path.abspath((reqs.get(rid) or {}).get("path") or "")
        if (os.path.isfile(path)
                and _git(["ls-files", "--error-unmatch", "--", path],
                         cwd=root) is not None
                and _git(["diff", "--quiet", sha, "--", path],
                         cwd=root) is not None):
            same.append(rid)
    return same, sha[:8]


def _advance_lock_and_report(ctx, accept_drift, drift_reason):
    # implements: ARCH-CHECK-006  # implements: ARCH-RULES-059
    # implements: REQ-CHECK-832  # implements: REQ-CHECK-833
    # implements: REQ-RULES-948
    """Print the lock diff, accept or demote drifted confirmed contracts, then
    save the lock, memberlock and clarify baselines. Reads
    `reqs`/`reqs_dir`/`code_root`/`full_members`/`lock`/`new_lock`/
    `full_member_hashes` off `ctx` — everything a gate rule can already
    read, so the caller passes nothing it did not already put there."""
    reqs, reqs_dir, code_root = ctx.reqs, ctx.reqs_dir, ctx.code_root
    full_members, lock, new_lock = ctx.full_members, ctx.lock, ctx.new_lock
    full_member_hashes = ctx.full_member_hashes
    changed = [(rid, lock.get(rid), h)
               for rid, h in sorted(new_lock.items()) if lock.get(rid) != h]
    removed = [rid for rid in sorted(lock) if rid not in new_lock]
    for rid, old_h, new_h in changed:
        old_short = old_h[:8] if old_h else "new"
        print(f"  lock update: {rid} hash changed ({old_short}->{new_h[:8]})")
    for rid in removed:
        print(f"  lock update: {rid} removed from lock")
    # sync drift guard: refuse to silently re-baseline an EDITED
    # confirmed/implemented contract unless the caller explicitly accepts it
    # (accept_drift). A brand-new requirement (old hash None) is not drift.
    confirmed_drift = [rid for (rid, old_h, _h) in changed
                       if old_h is not None
                       and reqs.get(rid, {}).get("meta", {}).get("status")
                       in ("confirmed", "implemented")]
    try:
        if confirmed_drift and not accept_drift:  # implements: REQ-PROMOTE-974
            same, sha = _unchanged_since_lock(reqs, reqs_dir, confirmed_drift)
            if same:
                record_accepted_drift(
                    reqs_dir, same, new_lock,
                    "text unchanged since lock commit %s: the binding hash "
                    "changed, not the contract (engine upgrade)" % sha,
                    set(new_lock))
                print("  re-baselined %d confirmed contract(s) whose file is "
                      "unchanged since the lock was committed (%s): the hash "
                      "moved, the text did not — kept confirmed"
                      % (len(same), sha))
                confirmed_drift = [rid for rid in confirmed_drift
                                   if rid not in same]
        if confirmed_drift and accept_drift:
            record_accepted_drift(reqs_dir, confirmed_drift, new_lock,
                                  drift_reason, set(new_lock))
            print("  accepted drift on %d confirmed contract(s), reason: %s"
                  % (len(confirmed_drift), drift_reason or "(none given)"))
    except DriftlogUnusable as e:   # implements: REQ-DRIFT-1104
        print("  ERROR: %s; the baseline was not advanced." % e)
        return str(e)
    if confirmed_drift and not accept_drift:  # implements: REQ-PROMOTE-974
        _demote_drifted_confirmed(reqs, confirmed_drift, full_members)
    save_lock(reqs_dir, new_lock)
    save_memberlock(reqs_dir, full_member_hashes
                     if full_member_hashes is not None
                     else compute_member_hashes(code_root, full_members))
    print("lock updated.")
    # An edit can leave a requirement with no clause or no case, which the
    # previous text never had. Nobody re-reads the whole corpus after an edit,
    # so the diff is reported here, where every edit already passes. Only the
    # blocking rules are kept; the advisory ones are read with `clarify`.
    # implements: REQ-CLARIFY-975
    _q_now = blocking_question_rules(reqs)
    _q_before = load_clarifylock(reqs_dir)
    _fresh = sorted((rid, sorted(set(rules) - set(_q_before.get(rid, []))))
                    for rid, rules in _q_now.items())
    _fresh = [(rid, rules) for rid, rules in _fresh
              if rules and rid in _q_before]
    if _fresh:
        print("")
        print("New open question(s) since the last sync — an edit raised them:")
        for rid, rules in _fresh:
            print("  %s: %s" % (rid, ", ".join(rules)))
        print("  Read them with `reqmap.py clarify <ID>`.")
    save_clarifylock(reqs_dir, _q_now)


def _stale_integration_artifacts():
    # implements: ARCH-CHECK-006  # implements: ARCH-RULES-059
    # implements: REQ-CHECK-832  # implements: REQ-CHECK-833
    # implements: REQ-RULES-948
    """Check this plugin repo's generated integration artifacts for staleness,
    if this tree is the plugin repo itself (skipped silently for a
    vendored/consumer copy)."""
    # Only inside the plugin package itself: two directories above a VENDORED
    # engine (`<consumer>/scripts/reqmap.py`) is the consumer's repo root, and a
    # consumer that ships its own `tool_definition.json` there was failing its
    # gate on ours.
    plugin_root = os.path.dirname(ENGINE_DIR)
    if os.path.exists(os.path.join(plugin_root, ".claude-plugin",
                                    "plugin.json")):
        return _check_integration_fresh(plugin_root)
    return []


def _drift_acceptance(accept_drift):
    # implements: ARCH-CHECK-006  # implements: REQ-PROMOTE-974
    """(accepted, reason) from the one `accept_drift` value a caller passes:
    True or False, or the reason string `--accept-drift REASON` yields.

    Read with `is not False`, never with truthiness: `--accept-drift ""` is a
    caller who passed the flag with an empty reason, and reading it as falsy
    would demote contracts they meant to keep."""
    if isinstance(accept_drift, str):
        return True, accept_drift.strip() or None
    return accept_drift is not False, None


def _print_gate_verdict(as_json, errors, warns, _stale, reqs, members):
    # implements: ARCH-CHECK-006  # implements: ARCH-RULES-059
    # implements: REQ-CHECK-832  # implements: REQ-CHECK-833
    # implements: REQ-RULES-948
    """Print (or, under --json, emit) `cmd_check`'s verdict and summary
    line for an already-computed (errors, warns, _stale), and return the
    exit code. Derives `legacy` and the confirmed count itself from
    `reqs`, same as `cmd_check` did before this was split out."""
    # counted after the demotion loop above, so a `sync` that just demoted
    # reports the corpus it leaves behind rather than the one it found
    legacy = _legacy_schema_ids(reqs)
    n_confirmed = sum(1 for r in reqs.values()
                      if r["meta"].get("status") == "confirmed")

    if as_json:
        print(json.dumps(GateResult(errors + warns).payload()))
        return 1 if errors else 0

    for finding in warns + errors:
        print("ERROR" if finding["severity"] == "error" else "WARN ",
              finding["rule"], str(finding))
    if _stale:
        print("ERROR: stale generated integration artifact(s): "
              + ", ".join(_stale)
              + " — run `python scripts/reqmap.py sync` and commit.",
              file=sys.stderr)

    n_find = sum(len(items) for _rid, _t, items in collect_findings(reqs))
    if n_find:
        print(f"info  {n_find} open verify-intent finding(s) — run "
              f"`reqmap.py sync`")

    print(f"\n{len(reqs)} requirements ({n_confirmed} confirmed, "
          f"{len(legacy)} legacy-schema), "
          f"{sum(len(v) for v in members.values())} members, "
          f"{len(errors)} errors, {len(warns)} warnings.")
    return 1 if errors else 0


def cmd_check(ws, update_lock, strict=False, accept_drift=False, mode=None,
              findings=None):
    # implements: ARCH-CHECK-006  # implements: ARCH-RULES-059
    # implements: REQ-CHECK-832  # implements: REQ-CHECK-833
    # implements: REQ-RULES-948
    """The gate: run GATE_RULES, print findings with their codes, advance the
    lock when asked. Report-only unless `update_lock` (that is `sync`).

    `accept_drift` is True, False, or the reason string the flag carried; see
    `_drift_acceptance` for why an empty reason still accepts. `mode` is a
    `GateMode`; its `quiet` runs only DEFAULT_RULES — the bare `gate` verb;
    `sync`, `init` and `audit` never set it."""
    mode = mode or GateMode()
    as_json, since, quiet = mode.as_json, mode.since, mode.quiet
    reqs, members, reqs_dir, code_root = (
        ws.reqs, ws.members, ws.reqs_dir, ws.code_root)
    code_root = code_root or "."   # a workspace built without one gates the cwd
    ac_cover, level_cover = ws.ac_cover, ws.level_cover
    warn_if_stale()
    full_members = members
    # --since: scope checks to requirements whose member files changed since
    # ref. Fail-open: fall back to full scan with WARN if git is unavailable
    # or ref invalid.
    members, pre_warns = _scope_members_since(since, code_root, members)
    # built from the resolved locals, not from `ws` directly: `--since`
    # narrowed `members`, and `code_root` fell back to the cwd just above.
    ctx = GateContext(Workspace(reqs, members, reqs_dir, code_root,
                                ac_cover, level_cover),
                      since=since, full_members=full_members,
                      update_lock=update_lock)
    ctx.quiet = quiet
    # the CALLER's workspace carries the map-document cache, so the freshness
    # rule and the `map --check` that `gate` runs next share one assembly
    # instead of two
    ctx.ws = ws
    # sync on a full scan re-baselines _memberlock below from this same hash
    # set — computed once and handed to the member-drift rule instead of
    # hashing twice.
    _reuse_full_hashes = update_lock and members is full_members
    ctx.full_member_hashes = (compute_member_hashes(code_root, full_members)
                              if _reuse_full_hashes else None)
    errors, warns = run_gate_rules(ctx, strict=strict)
    errors.extend(Finding("INPUT:requirements", "error", None, message)
                  for message in getattr(reqs, "problems", ()))
    warns = pre_warns + warns

    if update_lock and not getattr(reqs, "problems", ()):
        refused = _advance_lock_and_report(ctx,
                                           *_drift_acceptance(accept_drift))
        if refused:
            errors.append(Finding("INPUT:driftlog", "error", None, refused))

    # Integration-artifact freshness must run BEFORE the as_json early-return so
    # --json also exits non-zero on it.
    _stale = _stale_integration_artifacts()
    if _stale:
        errors = list(errors) + [Finding("RM028", "error", None,
                                         "stale integration artifact(s): "
                                         + ", ".join(_stale))]
    if findings is not None:
        findings.extend(errors + warns)
    return _print_gate_verdict(as_json, errors, warns, _stale, reqs,
                               members)
