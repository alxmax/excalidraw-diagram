"""`sync`'s audit tail: one line per corpus-shape signal."""
import datetime

from .groups import decomposable
from .lint import lint_requirement
from .lintrules import LINT_STATUSES, LINT_STRICT_PROMOTE
from .mapdata import (
    _read_roadmap, _roadmap_behind, _roadmap_plan_problems, _roadmap_signals
)
from .model import _as_list
from .orphans import _scan_untagged
from .relevel import relevel_residue_lines
from .similar import _corpus_shape, _exemptions_in_force
from .targets import has_plan, load_targets
from .versions import stale_plan_milestones, version_alignment_lines


def _exemption_line(reqs):
    # implements: ARCH-AUDIT-065  # implements: REQ-AUDIT-973
    """One line naming exemptions with no reason recorded, or None."""
    exemptions = _exemptions_in_force(reqs)
    unexplained = [e for e in exemptions if not e["reason"]]
    return ("{} exemption(s) silence a check with no reason recorded"
            .format(len(unexplained)) if unexplained else None)


def _lint_error_line(reqs, members):
    # implements: ARCH-AUDIT-065  # implements: REQ-AUDIT-973
    """One line naming lint ERRORs across the non-draft corpus, or None.
    
    Readability, reported where it is cheapest to act on. `gate` is what
    ENFORCES it (and the pre-commit hook runs `gate`), so this changes no exit
    code — it moves the moment a finding is seen to the one where the author
    still has the clause in mind.
    
    Errors only. A style warning is not a reason to break this summary's silence
    on an otherwise-clean corpus: this repo carries two long-standing ones, so a
    line keyed on warnings would fire on every sync forever, which is the habit
    ADR-0016 rejected. An ERROR is a confirmed requirement missing a
    load-bearing section — worth the line."""
    lint_errors = lint_warns = 0
    for rid, r in reqs.items():
        if r["meta"].get("status") not in LINT_STATUSES:
            continue
        for f in lint_requirement(rid, r, members.get(rid)):
            if f["severity"] == "error" or f["check"] in LINT_STRICT_PROMOTE:
                # the same promotion `gate` applies (it lints strict)
                lint_errors += 1
            else:
                lint_warns += 1
    if not lint_errors:
        return None
    return ("readability: {} error(s) across the non-draft corpus ({} "
           "warning(s) too) - run `reqmap.py gate` for the lines"
           .format(lint_errors, lint_warns))


def _level_gap_line(shape):
    # implements: ARCH-AUDIT-065  # implements: REQ-AUDIT-973
    """One line naming requirements with no declared `level:`, or None.
    
    Reported at ANY ratio, not only under `flat`. `flat` is `levelled * 10 <
    total`, so a corpus 85% of the way through a retrofit said nothing at all —
    and a partly-levelled corpus is precisely what a retrofit leaves behind, so
    the one state this tail could not see was the one it exists to report. The
    remedy is named here rather than left in `audit`: a signal whose command the
    reader has to go and find is a signal most readers will not act on."""
    unlevelled = shape["total"] - shape["levelled"]
    if not unlevelled:
        return None
    return ("{} of {} requirements declare no `level:`{} - "
           "`reqmap.py clarify --levels` proposes a rung for each and writes "
           "nothing without --apply".format(
               unlevelled, shape["total"],
               " - the corpus is flat" if shape["flat"] else ""))


def _decompose_candidates_line(reqs):
    # implements: ARCH-AUDIT-065  # implements: REQ-AUDIT-973
    """One line naming requirements with contract groups and no code
    children, or None.

    The code rung a tagged corpus could not reach (REQ-DECOMPOSE-994):
    requirements whose Description already draws the seams — bold group
    labels — and that have no child satisfying them. Reported here, never
    written here: `sync` runs inside the consumer's pre-commit hook, and a
    write that creates files the commit does not contain and drifts
    confirmed parents is what ADR-0031's "Why not on sync" refuses. The
    command is named so the fix is one step away from the place the signal
    appears."""
    kids = set()
    for _r in reqs.values():
        kids.update(_as_list(_r["meta"].get("satisfies")))
    splittable = [rid for rid, _r in reqs.items()
                 if rid not in kids and decomposable(_r)]
    if not splittable:
        return None
    return ("{} requirement(s) carry contract groups and no code children - "
           "`reqmap.py clarify --decompose` plans the split along those "
           "groups, --apply writes it".format(len(splittable)))


def _auto_level_line(shape):
    # implements: ARCH-AUDIT-065  # implements: REQ-AUDIT-973
    """One line naming requirements still carrying the engine's proposed
    level, or None.

    A corpus can be fully levelled and still be nothing but the engine's
    guesses, in which case every other number here reads as healthy.
    ADR-0030's revisit trigger is exactly this ratio. Reported beside the
    line above rather than
    instead of it: "some rungs are missing" and "some rungs are guesses" are two
    facts, and a corpus mid-retrofit is usually both."""
    if not shape.get("auto"):
        return None
    return ("{} of {} levelled requirement(s) still carry the rung the engine "
           "proposed (`level_source: auto`) - rename, merge or accept them"
           .format(shape["auto"], shape["levelled"]))


def _design_candidate_line(code_root, reqs_dir):
    # implements: ARCH-AUDIT-065  # implements: REQ-AUDIT-973
    """One line naming source files that carry a design candidate, or None."""
    from .design_report import _design_summary
    design = _design_summary(code_root, reqs_dir) if code_root else None
    if design is None or design["clean_files"] >= design["files"]:
        return None
    return ("design pass-rate {}% - {} of {} source files carry a "
            "candidate".format(design["score"],
                               design["files"] - design["clean_files"],
                               design["files"]))


def _untagged_files_line(code_root, reqs_dir):
    # implements: ARCH-AUDIT-065  # implements: REQ-AUDIT-973
    """One line naming code files traced to no requirement, or None."""
    untagged = _scan_untagged(code_root, reqs_dir) if code_root else None
    return ("{} code file(s) traced to no requirement".format(len(untagged))
            if untagged else None)


def _plan_stale_line(code_root, reqs_dir):
    # implements: ARCH-AUDIT-065  # implements: REQ-PLANSTALE-1013
    """One line naming planned milestones already declared, or None."""
    stale = stale_plan_milestones(reqs_dir, code_root) if reqs_dir else None
    if not stale:
        return None
    return ("_planning.json schedules {} at or below {} ({}) - the plan "
            "names a version already declared".format(
                ", ".join(stale["milestones"]), stale["baseline"],
                stale["source"]))


def _version_lines(code_root, reqs_dir):
    # implements: ARCH-AUDIT-065  # implements: REQ-VERSIONALIGN-1016
    """The plan-versus-release line plus every place the version sources
    disagree."""
    if not reqs_dir:
        return []
    stale = _plan_stale_line(code_root, reqs_dir)
    return ([stale] if stale else []) + version_alignment_lines(
        reqs_dir, code_root)


def _plan_lines(reqs, members, reqs_dir, code_root):
    # implements: ARCH-AUDIT-065  # implements: REQ-PLANDATES-1022
    # implements: REQ-PLANINPUT-1086
    """The dates `sync` suggests changing on bars whose work finished or
    ran over, the Now/Next items no bar schedules, and the plan keys
    nothing reads. The modules behind them load only for a repository that
    keeps a plan (ADR-0057)."""
    items = _read_roadmap(code_root) if code_root else None
    planned = bool(reqs_dir) and has_plan(reqs_dir)
    if not (planned or items):
        return []
    from .plandrift import bar_date_lines, bar_date_suggestions, unplanned_line
    from .planschema import plan_ignored_key_lines
    bars = load_targets(reqs_dir).get("bars", []) if planned else []
    lines = bar_date_lines(bar_date_suggestions(
        bars, reqs, members, code_root, datetime.date.today().isoformat(),
        items)) if bars and code_root else []
    unplanned = unplanned_line(items, bars) if code_root else None
    return lines + ([unplanned] if unplanned else []) + (
        plan_ignored_key_lines(reqs_dir) if planned else [])


def _roadmap_lag_lines(reqs, code_root):
    # implements: ARCH-AUDIT-065  # implements: REQ-AUDIT-973
    """Zero or more lines describing how TODO.md's roadmap and the requirements
    disagree about how far along the work is."""
    lines = _roadmap_plan_problems(code_root, reqs) if code_root else []
    roadmap = _roadmap_signals(code_root) if code_root else None
    if not roadmap:
        return lines
    # implements: REQ-ROADMAP-983
    # Each line ends with the edit that clears it: a finding with no next step
    # is one a reader has to go and research, and this one was left standing for
    # three minors.
    behind, newest_req, unmapped = _roadmap_behind(reqs, roadmap)
    if behind:
        lines.append(
            "TODO.md stops at {} while the requirements reach {} - add "
            "a `## {}` heading for that work".format(
                roadmap["newest_milestone"], newest_req, newest_req))
    if unmapped:
        lines.append(
            "the requirements stop at {} while TODO.md marks work shipped "
            "through {} - add `milestone:` to the requirements that "
            "shipped after {}"
            .format(newest_req, roadmap["newest_shipped"], newest_req))
    if roadmap["unversioned_headings"]:
        lines.append(
            "{} TODO.md heading(s) are not milestones, so their items "
            "are filed under the milestone above - start each with its "
            "version, `## vX.Y`, or end the heading with "
            "`<!-- reqmap: not-milestone -->` (first: {})"
            .format(len(roadmap["unversioned_headings"]),
                    roadmap["unversioned_headings"][0]))
    return lines


def _audit_summary(reqs, members, reqs_dir, code_root):
    # implements: ARCH-AUDIT-065  # implements: REQ-AUDIT-973
    """The one-line-per-signal tail `sync` prints: what `audit` would report,
    without running the passes that cost a second walk of the tree. Silent about
    anything that is clean, so a healthy repo sees nothing and the lines that do
    appear are news."""
    shape = _corpus_shape(reqs)
    lines = [text for text in (
        _exemption_line(reqs),
        _lint_error_line(reqs, members),
        _level_gap_line(shape),
        _decompose_candidates_line(reqs),
        _auto_level_line(shape),
        _design_candidate_line(code_root, reqs_dir),
        _untagged_files_line(code_root, reqs_dir),
    ) if text]
    lines.extend(_version_lines(code_root, reqs_dir))
    lines.extend(_plan_lines(reqs, members, reqs_dir, code_root))
    lines.extend(_roadmap_lag_lines(reqs, code_root))
    lines.extend(relevel_residue_lines(reqs))
    if not lines:
        return
    print("")
    for ln in lines:
        print("info  {}".format(ln))
    print("info  run `reqmap.py gate --audit` for the full report")
