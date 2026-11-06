"""The per-requirement gate rules: frontmatter, links, trace and tests
(RM001-RM015). The repository-wide ones follow in `rulesrepo`."""
import os

from .acceptance import _automatable_acs, _labeled_acs
from .model import (
    ENFORCED, LEVEL_TEST_PAIR, MILESTONE_RE, VALID_LAYER, VALID_LEVEL,
    VALID_STATUS, _as_list, _impl_exempt, gate_rule
)
from .sections import (
    ACCEPTANCE_LABELS, CONTRACT_LABELS, VALID_FORM, _atomic_spans, _has_any
)
from .workspace import _test_link_problem


@gate_rule("RM001", "error")
def _dangling_tag_rule(ctx):
    # implements: REQ-CHECK-828  # implements: REQ-RULES-947
    for cap in ctx.members:
        if cap not in ctx.cap_ids:
            yield None, (
                f"dangling tag: code references {cap} but no requirement "
                f"exists")


@gate_rule("RM002", "error")
def _frontmatter_rule(ctx):
    # implements: REQ-ATOMICFORM-053  # implements: ARCH-LEVEL-051
    # implements: REQ-CHECK-828  # implements: REQ-LEVEL-862
    for rid, r in ctx.reqs.items():
        m = r["meta"]
        if m.get("status") not in VALID_STATUS:
            yield rid, f"{rid}: invalid status {m.get('status')!r}"
        _frm = m.get("form")
        if _frm and _frm not in VALID_FORM:
            yield rid, (
                f"{rid}: invalid form {_frm!r} (expected one of "
                f"{sorted(VALID_FORM)})")
        if _frm == "atomic" and not _atomic_spans(r["body"]):
            yield rid, (
                f"{rid}: form: atomic but the body has no `>` statement "
                f"plus `Scenario:` block before the first `## ` heading")
        _lvl = m.get("level")
        if _lvl and _lvl not in VALID_LEVEL:
            yield rid, (
                f"{rid}: invalid level {_lvl!r} (expected one of "
                f"{sorted(VALID_LEVEL)})")
        if m.get("layer") not in VALID_LAYER:
            yield rid, f"{rid}: invalid layer {m.get('layer')!r}"


@gate_rule("RM031", "warn")
def _uncovered_aggregate_rule(ctx):
    # implements: ARCH-TRACE-020  # implements: REQ-TRACE-935
    """An `aggregate` is exempt from the implements and tested-by rules
    because it is covered downward by its `depends_on`. An empty list is
    therefore not a small omission: it claims the exemption and supplies
    nothing to be covered by."""
    for rid in sorted(ctx.cap_ids):
        r = ctx.req(rid)
        meta = r["meta"]
        if meta.get("layer") != "aggregate" \
                or meta.get("status") not in ENFORCED:
            continue
        if _as_list(meta.get("depends_on")) or not ctx.in_scope(rid):
            continue
        yield rid, (
            "{}: layer: aggregate with an empty `depends_on` — it is "
            "exempt from the implements and tested-by rules because its "
            "dependencies cover it, and it has none".format(rid))


@gate_rule("RM003", "error")
def _depends_on_missing_rule(ctx):  # implements: REQ-CHECK-828
    for rid, r in ctx.reqs.items():
        for dep in _as_list(r["meta"].get("depends_on")):
            if dep not in ctx.cap_ids:
                yield rid, f"{rid}: depends_on missing {dep}"


@gate_rule("RM004", "warn")
def _milestone_shape_rule(ctx):
    # an optional, roadmap-only field: a malformed value silently fails to sort
    # in the Roadmap rather than breaking the build, so it warns, only when
    # present and not deprecated.
    for rid, r in ctx.reqs.items():
        m = r["meta"]
        ms = m.get("milestone")
        if ms and m.get("status") != "deprecated" \
                and not MILESTONE_RE.match(str(ms).strip()):
            yield rid, (f"{rid}: milestone {ms!r} is malformed (expected "
                       f"v<digits>[.<digits>…], e.g. v1.14)")


@gate_rule("RM005", "warn")
def _satisfies_dangling_rule(ctx):
    # implements: ARCH-TRACE-020  # implements: REQ-TRACE-934
    # a dangling upstream id is a WARN not an ERROR — the need may be authored
    # later or live in an external tracker.
    for rid, r in ctx.reqs.items():
        for up in _as_list(r["meta"].get("satisfies")):
            if up not in ctx.cap_ids:
                yield rid, (f"{rid}: satisfies {up} but no such requirement "
                           f"(upstream trace dangling)")


@gate_rule("RM006", "error")
def _no_implements_rule(ctx):
    # implements: ARCH-TRACE-020  # implements: REQ-CHECK-828
    # implements: REQ-RULES-947
    for rid, r in ctx.reqs.items():
        m = r["meta"]
        if m.get("status") in ENFORCED and not _impl_exempt(m) \
                and "implements" not in ctx.roles(rid) and ctx.in_scope(rid):
            yield rid, (
                f"{rid}: status {m['status']} but no implements: tag "
                f"found in code")


@gate_rule("RM007", "warn")
def _no_tested_by_rule(ctx):  # implements: REQ-CHECK-829
    for rid, r in ctx.reqs.items():
        m = r["meta"]
        if m.get("status") == "confirmed" \
                and "tested-by" not in ctx.roles(rid) \
                and not m.get("test_exempt") and not _impl_exempt(m) \
                and ctx.in_scope(rid):
            yield rid, (
                f"{rid}: confirmed but no tested-by: tag — acceptance "
                f"tests not linked")


@gate_rule("RM008", "warn")
def _need_not_validated_rule(ctx):
    # implements: ARCH-VLEVEL-037  # implements: REQ-CHECK-831
    # a need is validated, not tested; opt-in via any `validated-against` tag in
    # the repo.
    if not ctx.any_validation:
        return
    for rid, r in ctx.reqs.items():
        m = r["meta"]
        if m.get("layer") == "need" and m.get("status") == "confirmed" \
                and "validated-against" not in ctx.roles(rid) \
                and ctx.in_scope(rid):
            yield rid, (
                f"{rid}: confirmed need with no `validated-against:` "
                f"tag — nothing shows the need was actually met")


@gate_rule("RM009", "warn")
def _bus_only_system_level_rule(ctx):
    # implements: ARCH-VLEVEL-037  # implements: REQ-CHECK-831
    for rid, r in ctx.reqs.items():
        m = r["meta"]
        if m.get("status") == "confirmed" and m.get("layer") == "bus" \
                and set(ctx.level_cover.get(rid, {})) == {"system"}:
            yield rid, (
                f"{rid}: bus capability verified only at @system level "
                f"— add a @unit or @integration `tested-by:` link")


@gate_rule("RM010", "warn")
def _level_rung_rule(ctx):  # implements: REQ-VRUNGS-054
    for rid, r in ctx.reqs.items():
        m = r["meta"]
        _want = LEVEL_TEST_PAIR.get(m.get("level"))
        if m.get("status") == "confirmed" and _want:
            _have = set(ctx.level_cover.get(rid, {}))
            if _have and _want not in _have:
                _seen = '/'.join('@' + x for x in sorted(_have))
                yield rid, (f"{rid}: level: {m['level']} is verified at "
                            f"{_seen} but not @{_want} — "
                            f"add a @{_want} `tested-by:` link, or "
                            f"change the level")


@gate_rule("RM011", "warn")
def _owner_auto_rule(ctx):
    for rid, r in ctx.reqs.items():
        m = r["meta"]
        if m.get("status") == "confirmed" \
                and m.get("owner", "auto") in ("auto", "", None):
            yield rid, (
                f"{rid}: confirmed requirement has owner: auto — assign "
                f"a named owner")


@gate_rule("RM012", "warn", strict=True)
def _test_link_rule(ctx):
    # implements: ARCH-TESTLINK-018  # implements: REQ-TESTLINK-933
    # checked at EVERY status; only a confirmed requirement's broken link is
    # strict-promoted (see cmd_check: a non-confirmed hit is downgraded to a
    # plain warn there). one read per test file, not one per requirement naming
    # it: a suite every requirement points at (this repo's test_reqmap.py) was
    # opened 206 times per gate
    problems = {}
    for rid, r in ctx.reqs.items():
        tests = [x for x in ctx.full_members.get(rid, [])
                 if x[0] == "tested-by"]
        for fp in sorted({t[1] for t in tests}):
            if fp not in problems:
                problems[fp] = _test_link_problem(
                    os.path.join(ctx.code_root, fp))
            if problems[fp]:
                yield rid, f"{rid}: tested-by {fp} {problems[fp]}"


@gate_rule("RM013", "warn")
def _case_coverage_rule(ctx):  # implements: ARCH-ACVERIFY-019
    # ONE aggregated line per requirement, only once it has adopted per-case
    # tagging.
    for rid, r in ctx.reqs.items():
        if r["meta"].get("status") != "confirmed":
            continue
        labels = _automatable_acs(r["body"])
        covered = ctx.ac_cover.get(rid, {})
        if labels and covered:
            missing = [ac for ac in labels if ac not in covered]
            if missing:
                yield rid, (
                    f"{rid}: {len(labels) - len(missing)}/{len(labels)} "
                    f"automatable criteria carry a `# verifies:` tag — "
                    "missing " + ", ".join(missing))


@gate_rule("RM034", "warn")
def _dangling_verifies_rule(ctx):
    # implements: ARCH-ACVERIFY-019  # implements: REQ-DANGLINGVERIFY-1009
    """RM013 read one direction only — a labelled case with no tag. The other
    direction was unguarded: a `# verifies: <id>#CASE-N` naming a case that does
    not exist was accepted in silence, AND it is what flips RM013 on (`covered`
    becomes non-empty), so a typo produced `0/2 criteria carry a tag` for a file
    that plainly carries one. The label is an identifier; an identifier with no
    referent is a broken link."""
    for rid in sorted(ctx.ac_cover):
        r = ctx.reqs.get(rid)
        if r is None:
            # RM001 does NOT cover this: it reads `members`
            # (implements/tested-by tags) and
            # never `ac_cover`, so a `verifies:` naming a requirement that
            # does not exist
            # was silent in both rules. Same broken link, so it is reported
            # here.
            locs = [l for ac in sorted(ctx.ac_cover[rid])
                    for l in ctx.ac_cover[rid][ac]]
            where = ", ".join(f"{fp}:{ln}" for fp, ln in locs[:3])
            yield None, (
                f"`# verifies: {rid}#…` names no such requirement ({where}"
                + (", …" if len(locs) > 3 else "") + ")")
            continue
        labels = set(_labeled_acs(r["body"]))
        if not labels:
            continue          # unlabelled acceptance: nothing to dangle against
        for ac in sorted(ctx.ac_cover[rid]):
            if ac in labels:
                continue
            locs = ctx.ac_cover[rid][ac]
            where = ", ".join(f"{fp}:{ln}" for fp, ln in locs[:3])
            yield rid, (
                f"{rid}: `# verifies: {rid}#{ac}` names no such case "
                f"({where}"
                + (", …" if len(locs) > 3 else "")
                + f") — the requirement labels {', '.join(sorted(labels))}. "
                "Fix the label, or the case it meant to name is missing.")


@gate_rule("RM014", "warn")
def _confirmed_sections_rule(ctx):  # implements: REQ-CHECK-1040
    for rid, r in ctx.reqs.items():
        if r["meta"].get("status") != "confirmed" or r["meta"].get(
                "source") in ("text", "html"):  # implements: REQ-CUSTOMTRACE-1113
            continue
        if not _has_any(r["body"], CONTRACT_LABELS):
            yield rid, (
                f"{rid}: confirmed but missing '## Description' section "
                "— add the normative contract or drop status back to "
                "draft")
        if not _has_any(r["body"], ACCEPTANCE_LABELS):
            yield rid, (
                f"{rid}: confirmed but missing '## Cases' section — add "
                "acceptance criteria or drop status back to draft")


@gate_rule("RM015", "warn")
def _need_unsatisfied_rule(ctx):
    # implements: ARCH-TRACE-020  # implements: REQ-TRACE-934
    for rid, r in ctx.reqs.items():
        m = r["meta"]
        if (m.get("layer") == "need" and m.get("status") in ENFORCED
                and not ctx.satisfied_by.get(rid)):
            yield rid, (f"{rid}: need has no requirement that satisfies it "
                       f"(upstream trace unaddressed)")
