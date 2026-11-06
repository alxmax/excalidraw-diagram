"""The repository-wide gate rules: the lock, drift, the scan's leftovers
and the map. Registered after every rule in `rules` (RM016 onward); RM030
sits here only because its place in GATE_RULES is between RM016 and RM018."""
from . import config as cfg
from . import rules  # noqa: F401 — RM001-RM015 register first
from .locks import (
    baseline_problems, load_memberlock, member_drift, untracked_locks
)
from .mapcmd import _absent_tracked_artifacts, _stale_artifacts
from .model import _as_list, _dependency_cycles, gate_rule
from .orphans import (
    orphan_code_files, tagged_unscanned_files, undecodable_source_files,
    untagged_doc_bundles, untracked_members
)
from .sections import _legacy_schema_ids
from .similar import EXEMPTION_FIELDS, _exemption_reason_recorded


@gate_rule("RM016", "warn", strict=True)
def _corrupt_lock_rule(ctx):
    # implements: ARCH-DRIFT-003  # implements: REQ-DRIFT-1103
    # load_lock and load_memberlock fail open ({}) on an absent OR unusable
    # baseline; surface the unusable case so a silently-disabled drift signal
    # is visible. An absent baseline is first use and says nothing.
    for message in baseline_problems(ctx.reqs_dir):
        yield None, message


# RM017 compared the viewer's demo fixture with the corpus. The fixture is gone and
# so is the rule; the code stays retired, never reused (see GATE_RULES).


@gate_rule("RM030", "warn")
def _exemption_without_reason_rule(ctx):
    # implements: ARCH-AUDIT-065  # implements: REQ-AUDIT-971
    """An exemption whose check is never mentioned in the requirement's
    own prose.

    Warn-only, and never promoted under `--strict`: the point is to make
    silencing a finding cost a sentence, not to make it impossible. A
    shape that is genuinely deliberate is one line away from clean; a
    shape that was silenced to make a run green has nobody willing to
    write that line."""
    for rid in sorted(ctx.reqs):
        r = ctx.reqs[rid]
        for field in EXEMPTION_FIELDS:
            for check in _as_list(r["meta"].get(field)):
                if not _exemption_reason_recorded(r["body"], check):
                    yield rid, (
                        "{}: `{}: [{}]` silences a finding with no "
                        "reason recorded \u2014 say why in the "
                        "requirement's prose, or drop the exemption and "
                        "fix what it hides".format(rid, field, check))


# The two rules that say "the spec and the code no longer agree". They warn by
# default and promote under `--strict`; a repo may also promote them for itself
# with `DRIFT_SEVERITY: "error"` in `_config.json`. The default stays `warn`
# because the evidence for that is recorded and unchanged (ADR-0002): a
# spec-first edit legitimately drifts the contract ahead of the code, and a
# check that fails on correct work is a check someone bolts `continue-on-error`
# onto and never reads again. Which side of that trade a repo wants is the
# repo's call, not the tool's.
DRIFT_RULES = ("RM018", "RM019")


@gate_rule("RM018", "warn", strict=True)
def _drift_rule(ctx):
    # implements: ARCH-DRIFT-003  # implements: ARCH-DRIFTIMPACT-035
    # implements: REQ-CHECK-829  # implements: REQ-DRIFTIMPACT-843
    for rid, r in ctx.reqs.items():
        h, old = ctx.new_lock[rid], ctx.lock.get(rid)
        if old and old != h and r["meta"].get("status") == "confirmed":
            locs = [f"{fp}:{ln}"
                    for (_role, fp, ln) in ctx.members.get(rid, [])]
            where = (", ".join(locs) if locs
                     else "no members tagged — add an implements: tag")
            deps_of = sorted(ctx.dependents.get(rid, ()))
            fanout = ("; review dependent(s): " + ", ".join(deps_of)
                      if deps_of else "")
            yield rid, (f"{rid}: DRIFT — contract changed since lock; "
                        f"re-check {len(locs)} member(s): {where}{fanout}")


@gate_rule("RM019", "warn", strict=True)
def _member_drift_rule(ctx):
    # implements: ARCH-MEMBERDRIFT-027
    memberlock = load_memberlock(ctx.reqs_dir)
    for rid, rel in member_drift(
            ctx.reqs, ctx.members, ctx.lock, memberlock, ctx.code_root,
            current=ctx.full_member_hashes):
        yield rid, (
            f"{rid}: MEMBER DRIFT — {rel} changed since lock but the "
            "contract was not re-touched; re-check the requirement, or "
            "run sync to re-baseline")


@gate_rule("RM020", "warn")
def _untracked_lock_rule(ctx):
    for lp_rel in untracked_locks(ctx.reqs_dir):
        yield None, (
            f"{lp_rel} exists on disk but is not git-tracked — `git add "
            f"{lp_rel}` so drift detection works in CI (an uncommitted "
            "lock is invisible to a fresh checkout)")


@gate_rule("RM021", "warn")
def _doc_bundle_rule(ctx):  # implements: ARCH-DOCBUNDLE-026
    for rel in untagged_doc_bundles(
            ctx.code_root, ctx.full_members, ctx.reqs_dir):
        yield None, (
            f"{rel}: large docs/ HTML bundle "
            f"({cfg.DOC_BUNDLE_MIN_BYTES // 1000}KB+) has no "
            "generated-from: tag — link it to the requirement(s) it "
            "derives from (`<!-- generated-from: A, B -->`), or add it "
            "to .reqmapignore")


@gate_rule("RM022", "warn")
def _untracked_members_rule(ctx):  # implements: ARCH-TRACKED-042
    _untracked = untracked_members(ctx.code_root, ctx.full_members)
    if _untracked:
        yield None, (
            "{} member(s) are not tracked by git: {} — the committed "
            "map records them, but a fresh checkout has no such file, "
            "so it cannot be regenerated there. Commit them, or "
            "exclude them in .reqmapignore.".format(
                len(_untracked), ", ".join(_untracked[:5])
                + ("" if len(_untracked) <= 5 else ", …")))


@gate_rule("RM023", "warn")
def _unscanned_tags_rule(ctx):  # implements: ARCH-UNSCANNEDTAG-045
    _unscanned = tagged_unscanned_files(ctx.code_root, ctx.reqs_dir)
    if _unscanned:
        yield None, (
            "{} tag(s) in file type(s) the scan never reads: {} — those "
            "files are not members. Move the tag into a scannable "
            "file, or ask for the type to be added to the scan."
            .format(
                len(_unscanned), ", ".join(_unscanned[:5])
                + ("" if len(_unscanned) <= 5 else ", …")))


@gate_rule("RM033", "warn")
def _undecodable_source_rule(ctx):
    # implements: ARCH-UNREADABLE-070
    # implements: REQ-UNREADABLE-1004
    _bad = undecodable_source_files(ctx.code_root, ctx.reqs_dir)
    for rel, reason in _bad:
        yield None, (
            f"{rel}: {reason} — the scan cannot read it, so any tag "
            "in it is invisible and it counts as untagged. Re-save it "
            "as UTF-8, or add it to .reqmapignore.")


@gate_rule("RM024", "warn")
def _orphan_code_rule(ctx):  # implements: ARCH-ORPHANCODE-034
    covered = {fp for hits in ctx.full_members.values()
               for (_role, fp, _ln) in hits}
    covered.update(fp for acs in ctx.ac_cover.values()
                   for locs in acs.values() for (fp, _ln) in locs)
    for rel in orphan_code_files(ctx.code_root, covered, ctx.reqs_dir):
        yield None, (
            f"{rel}: {cfg.ORPHAN_CODE_MIN_LOC}+-line code file has no "
            "membership tag — link it (`# implements: <ID>`), draft a "
            "requirement for it (`reqmap.py init`), or add it to "
            ".reqmapignore")


@gate_rule("RM025", "warn")
def _legacy_schema_rule(ctx):  # implements: REQ-CHECK-831
    legacy = _legacy_schema_ids(ctx.reqs)
    if legacy:
        yield None, (
            "{}/{} requirement(s) use the legacy schema (the "
            "Input/Description/Output triad) — `findings` is inactive "
            "for them: {}"
            .format(len(legacy), len(ctx.reqs), ", ".join(legacy)))


@gate_rule("RM026", "warn")
def _depends_on_cycle_rule(ctx):
    # implements: ARCH-CHECK-006  # implements: REQ-CHECK-831
    # warn, not error: a cycle is a modelling call across several requirements
    # (ADR-0002).
    for _cyc in _dependency_cycles(ctx.reqs):
        # The second sentence is the SYMPTOM, not the defect, and it is here
        # because a consumer hit the symptom and could not get from it to this
        # message: the map layout ranks by longest path, which does not converge
        # on a cyclic graph, so a few nodes get pushed hundreds of columns out
        # and every edge into them renders as a near-horizontal line. "The map
        # looks like stripes" does not read as "the graph has a cycle" to anyone
        # who has not been told.
        yield None, (
            "depends_on cycle: " + " -> ".join(_cyc)
            + " — no requirement in a cycle can be built before the "
              "others; drop the edge that closes it. This also "
              "flattens the map: the layout ranks by longest path, so "
              "a cycle stretches the canvas and its edges render as "
              "near-horizontal lines")


@gate_rule("RM027", "warn")
def _map_stale_rule(ctx):  # implements: ARCH-MAP-007
    # skipped under update_lock: `sync` regenerates the map moments later.
    if ctx.update_lock:
        return
    try:
        absent_map = _absent_tracked_artifacts(ctx.reqs_dir, ctx.code_root)
        stale_map = _stale_artifacts(
            ctx.ws.map_data(ctx.code_root, ctx.full_members,
                            with_design=False),
            ctx.ws, ctx.code_root)
    except Exception as exc:  # implements: REQ-MAP-871
        # A freshness probe never blocks the gate, but a probe that
        # could not run must not read as "fresh": it says so.
        yield None, ("freshness probe failed ({}: {}) — the map was "
                     "not checked; run `reqmap.py sync` to see the "
                     "error".format(type(exc).__name__, exc))
        return
    if absent_map:
        yield None, ("committed map is missing from the working tree: "
                     + ", ".join(absent_map)
                     + " — git tracks it; restore it or run `reqmap.py sync`")
    if stale_map:
        yield None, (
            "committed map is stale: " + ", ".join(stale_map)
            + " — run `reqmap.py sync` (or `map`) and commit the result")
