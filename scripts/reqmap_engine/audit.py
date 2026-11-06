"""`gate --audit`: the corpus-shape report."""
import contextlib, io, json, os

from . import MAP_ENGINE_VERSION, config as cfg
from .audittail import _roadmap_lag_lines, _version_lines
from .gate import cmd_check, run_gate_rules
from .health import _exempt_note, _health_record, cmd_coverage
from .mapdata import _read_roadmap
from .plandrift import plan_drift, plan_drift_lines, version_bar_lines
from .orphans import _scan_untagged
from .risk import cmd_next
from .similar import (
    _corpus_shape, _exemptions_in_force, _redundant_groups, cmd_similar
)
from .targets import load_targets
from .workspace import GateContext


def _session(reqs_dir):
    # implements: REQ-AUDITRUN-1107
    """The audit session's report, or None when no session is open. Loaded
    only when `_audit.json` exists."""
    if not reqs_dir or not os.path.isfile(os.path.join(reqs_dir, "_audit.json")):
        return None
    from .auditrun import session_report
    return session_report(reqs_dir)


# ---------- health (corpus coherence snapshot) ----------
def _audit_section(title, remedy, fn, fail_rc=0):
    # implements: ARCH-AUDIT-065  # implements: REQ-AUDIT-970
    """Run one discovery pass with its output captured, so the summary can be
    printed before the detail it summarises. Returns (title, remedy, text, rc).
    
    A crashing section is swallowed because advice must not fail a build — but
    the Gate section is not advice, it IS the exit code, and swallowing its
    crash to rc 0 printed `Gate  clean` for a run that never reached a verdict.
    `fail_rc` is how a section says what its own failure means; only the gate
    passes 1."""
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            rc = fn()
    except Exception as e:            # a section is advice, never a crash
        return (title, remedy, "  (section failed: {})".format(e), fail_rc)
    return (title, remedy, buf.getvalue().rstrip(), rc or 0)


def _version_bars(reqs_dir):
    # implements: ARCH-AUDIT-065  # implements: REQ-PLANVERSIONBAR-1091
    """The plan's bars that are a version, not work; [] with no plan."""
    if not reqs_dir:
        return []
    return version_bar_lines(load_targets(reqs_dir).get("bars", []))


def _print_audit_roadmap(reqs, code_root, reqs_dir=None):
    # implements: ARCH-AUDIT-065  # implements: REQ-AUDIT-970
    """Print the roadmap-lag block, the audit's third section with no verb
    of its own.

    These lines existed since REQ-AUDIT-973 but were reachable only from
    `sync`'s tail, so the report actually NAMED "audit" was structurally
    blind to them. That matters most for the unversioned-headings line,
    which does not describe a defect in the corpus: it says the roadmap
    feature is INERT for this repo, because its headings are not
    milestones. A consumer reported reading the engine's source to find
    that out.

    Deliberately here and not in the bare `gate`: the commit hook runs
    `gate` on every commit and ADR-0020 draws that line for corpus-shape
    signals. `--audit` is a question a reader asks on purpose."""
    lines = _version_lines(code_root, reqs_dir)
    lines += _roadmap_lag_lines(reqs, code_root)
    # Only here, never in `sync`'s tail: this one walks the tree a second time
    # and shells to git once per cited file. `--audit` is asked for on purpose;
    # `sync` runs on every edit and must not grow a second walk.
    drift = (plan_drift(_read_roadmap(code_root) or [], code_root, reqs_dir)
             if code_root else None)
    lines = lines + (plan_drift_lines(drift) if drift else [])
    lines += _version_bars(reqs_dir)
    if not lines:
        return
    print("-" * 72)
    print("Roadmap - how the plan and the requirements disagree")
    print("-" * 72)
    for text in lines:
        print("  " + text)
    if drift:
        for rec in drift["sure"][:5]:
            what = ", ".join(rec["paths"] + rec["symbols"])
            print("    gone: {}  <- {}".format(what, rec["name"][:60]))
        for rec in drift["rederive"][:5]:
            print("    since {}: {}  <- {}".format(
                rec["since"],
                ", ".join(f["path"] for f in rec["files"][:2]),
                rec["name"][:60]))
    print("")



def _json_audit_report(ws, signals, strict):
    # implements: ARCH-AUDIT-065  # implements: REQ-AUDIT-970
    """Build and print the `--json` audit report; return the gate's exit code.

    `signals` bundles the already-computed shape/health/design/untagged/
    exemptions (and their unexplained subset) `cmd_audit` gathers once for
    both report forms — an object in place of the parameter list those
    separate values would be."""
    reqs, members = ws.reqs, ws.members
    health, shape = signals["health"], signals["shape"]
    design, untagged = signals["design"], signals["untagged"]
    out = {"health": health, "shape": shape,
           "exemptions": signals["exemptions"],
           "redundant_groups": [sorted(g) for g in _redundant_groups(reqs)]}
    if design is not None:
        out["design"] = design
    if untagged is not None:
        out["untagged"] = len(untagged)
    # Same lines the console report prints under "Roadmap" — a JSON consumer
    # that could not see them would be back in the position REQ-AUDIT-973's
    # reporter was in.
    roadmap = _version_lines(ws.code_root, ws.reqs_dir)
    roadmap += _roadmap_lag_lines(reqs, ws.code_root)
    # The text report appends plan-drift lines under the same "Roadmap"
    # heading. Leaving them out of `--json` made a clean JSON audit hide
    # a plan that cites code which is no longer there.
    if ws.code_root:
        roadmap += plan_drift_lines(plan_drift(
            _read_roadmap(ws.code_root) or [], ws.code_root, ws.reqs_dir))
    roadmap += _version_bars(ws.reqs_dir)
    if roadmap:
        out["roadmap"] = roadmap
    session = _session(ws.reqs_dir)
    if session is not None:
        out["audit_session"] = session
    errs, warns = run_gate_rules(
        GateContext(ws, full_members=members, update_lock=False),
        strict=strict)
    out["gate"] = {"errors": len(errs), "warnings": len(warns),
                   "findings": [dict(f) for f in list(errs) + list(warns)]}
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 1 if errs else 0


def _summary_table_rows(gate_rc, signals, dups):
    # implements: ARCH-AUDIT-065  # implements: REQ-AUDIT-970
    """The audit's summary table: one row per signal, in report order.

    `signals` is the same bundle `_json_audit_report` reads — see its
    docstring."""
    health, untagged = signals["health"], signals["untagged"]
    design = signals["design"]
    exemptions, unexplained, shape = (signals["exemptions"],
                                      signals["unexplained"],
                                      signals["shape"])
    verdict = "FAIL" if gate_rc else "clean"
    rows = [("Gate", verdict, "reqmap.py gate"),
            ("Health", "{}/100 ({}/{} green on every axis{})".format(
                health["score"], health["healthy"],
                health.get("scored", health["total"]),
                _exempt_note(health)),
             "reqmap.py gate --risk")]
    if design is not None:
        rows.append(("Design pass-rate",
                     "{}% ({}/{} files with no candidate)".format(
                         design["score"], design["clean_files"],
                         design["files"]),
                     "reqmap.py ask --design"))
    if untagged is not None:
        rows.append(("Untagged code",
                     "{} file(s) traced to no requirement".format(
                         len(untagged)),
                     "reqmap.py gate --risk --untagged"))
    if dups:
        rows.append(("Redundancy",
                     "{} group(s) share an identical contract".format(
                         len(dups)),
                     "reqmap.py ask --dupes"))
    rows.append(("Exemptions", "{} in force, {} with no recorded reason".format(
        len(exemptions), len(unexplained)), "see below"))
    rows.append(("Corpus shape", "{}/{} carry a `level:`{}".format(
        shape["levelled"], shape["total"],
        " - the corpus is flat" if shape["flat"] else ""),
        "see below"))
    return rows


def _print_audit_sections(sections):
    # implements: ARCH-AUDIT-065  # implements: REQ-AUDIT-970
    """Print each discovery section's captured output under its own banner."""
    for title, remedy, text, _rc in sections:
        print("-" * 72)
        print("{}   ({})".format(title, remedy))
        print("-" * 72)
        print(text if text else "  nothing to report")
        print("")


def _print_audit_exemptions(exemptions):
    # implements: ARCH-AUDIT-065  # implements: REQ-AUDIT-970
    """Print the exemptions-in-force block, one of the audit's two sections
    with no verb of its own."""
    print("-" * 72)
    print("Exemptions in force")
    print("-" * 72)
    if not exemptions:
        print("  none - no requirement silences a check.")
    else:
        for e in exemptions:
            mark = " " if e["reason"] else "!"
            print("  {} {:<22} {}: [{}]{}".format(
                mark, e["id"], e["field"], e["check"],
                "" if e["reason"] else "   <- no reason recorded"))
        print("")
        print("  An exemption is a finding somebody decided not to see. "
              "It is legitimate")
        print("  when the shape is deliberate and the reason is written "
              "down; it is not a")
        print("  way to make a run green. For an over-scoped requirement "
              "the fix is")
        print("  `reqmap.py clarify <ID> --decompose`, which scaffolds "
              "the extra clause out.")
    print("")


def _print_audit_corpus_shape(shape):
    # implements: ARCH-AUDIT-065  # implements: REQ-AUDIT-970
    """Print the corpus-shape block, the audit's other section with no verb
    of its own."""
    print("-" * 72)
    print("Corpus shape - the V-model's left arm")
    print("-" * 72)
    if shape["levelled"]:
        for lv in ("system", "architecture", "code"):
            if lv in shape["levels"]:
                print("  {:<14} {}".format(lv, shape["levels"][lv]))
        for lv in sorted(k for k in shape["levels"]
                        if k not in ("system", "architecture", "code")):
            print("  {:<14} {}   (not one of the three rungs)".format(
                lv, shape["levels"][lv]))
        print("  satisfies:     {} edge(s)".format(shape["satisfies_edges"]))
    if shape["flat"]:
        print("  {} of {} requirements declare no `level:`, so every one "
              "of them reads as".format(
                  shape["total"] - shape["levelled"], shape["total"]))
        print("  the same rung. `level:` is opt-in - the template ships "
              "it commented out - so")
        print("  a corpus never gains the axis by itself. The three rungs are:")
        print("    system        a stakeholder need, satisfied by "
              "architecture, not by code")
        print("    architecture  one capability: a command, or a shared "
              "engine facility")
        print("    code          one behaviour group, 3-7 labelled cases, "
              "tested per case")
        print("  The edge that builds the pyramid is `satisfies:` (the "
              "level axis), not")
        print("  `depends_on:` (the composition axis). Adopting it is a "
              "decision, not a")
        print("  defect: nothing here fails because a corpus is flat.")
        # A detection that names no next step leaves a reader knowing they are
        # flat and not knowing what to do about it. Now that a retrofit exists,
        # say so.
        print("  If you decide to adopt it: `reqmap.py clarify --levels` "
              "proposes a rung")
        print("  for each requirement and writes nothing without --apply.")
    print("")


def _print_audit_session(reqs_dir):
    # implements: REQ-AUDITRUN-1107
    """Print the audit session block when one is open."""
    session = _session(reqs_dir)
    if session is None:
        return
    from .auditrun import report_lines
    print("-" * 72)
    if "plan" not in session:
        print("Audit session - the file cannot be used")
        print("-" * 72)
        for m in session["problems"]:
            print("  ! INPUT:audit " + m)
        print("")
        return
    lines = report_lines(session)
    print(lines[0])
    print("-" * 72)
    for text in lines[1:]:
        print(text)
    print("")


def cmd_audit(ws, strict=False, as_json=False):
    # implements: ARCH-AUDIT-065  # implements: REQ-AUDIT-970
    """Run every pass that discovers a problem, and print one report.

    The engine grew one verb per question — is it linked, is it drifted, is
    it duplicated, is it tagged, is the design rotting — and answering "how
    is this repo doing" meant remembering all of them. This runs them
    together and prints a summary of what each found, then each section's
    own output underneath.

    Read-only. The exit code comes from the gate alone: everything else
    here is advice, and advice must not be able to fail a build. Two
    sections have no verb of their own because they only make sense in
    this report: the exemptions in force, and the shape of the corpus on
    the V-model's left arm."""
    reqs = ws.reqs
    members, reqs_dir, code_root = ws.members, ws.reqs_dir, ws.code_root
    # Imported here, not at module top: the gate never loads the design
    # review, and `gate` imports this module.
    from .design_report import _design_summary, cmd_design
    exemptions = _exemptions_in_force(reqs)
    unexplained = [e for e in exemptions if not e["reason"]]
    shape = _corpus_shape(reqs)
    health = _health_record(reqs, members, reqs_dir)
    design = _design_summary(code_root, reqs_dir) if code_root else None
    untagged = _scan_untagged(code_root, reqs_dir) if code_root else None
    # Bundled once, in place of the long parameter list this report's two shapes
    # (`--json` and the console table) would otherwise both need repeated.
    signals = {"shape": shape, "health": health, "design": design,
               "untagged": untagged,
               "exemptions": exemptions, "unexplained": unexplained}

    if as_json:
        return _json_audit_report(ws, signals, strict)

    sections = [
        _audit_section("Gate", "reqmap.py gate",
                       lambda: cmd_check(ws, False, strict=strict), fail_rc=1),
        _audit_section("Risk", "reqmap.py gate --risk",
                       lambda: cmd_next(ws, False)),
        _audit_section("Duplicates", "reqmap.py ask --dupes",
                       lambda: cmd_similar(reqs, cfg.SIMILAR_THRESHOLD,
                                           members)),
        _audit_section("Design", "reqmap.py ask --design",
                       lambda: cmd_design(code_root, reqs_dir)),
        _audit_section("Tag coverage", "reqmap.py gate --risk --untagged",
                       lambda: cmd_coverage(ws, False)),
    ]
    gate_rc = sections[0][3]
    dups = _redundant_groups(reqs)

    print("AUDIT  {} requirement(s) - engine {}".format(
        len(reqs), MAP_ENGINE_VERSION))
    print("")
    rows = _summary_table_rows(gate_rc, signals, dups)
    width = max(len(r[0]) for r in rows)
    vwidth = max(len(r[1]) for r in rows)
    for name, value, remedy in rows:
        print("  {}  {}  {}".format(
            name.ljust(width), value.ljust(vwidth), remedy))
    print("")

    _print_audit_sections(sections)
    _print_audit_exemptions(exemptions)
    _print_audit_corpus_shape(shape)
    _print_audit_roadmap(reqs, code_root, reqs_dir)
    _print_audit_session(reqs_dir)
    return gate_rc
