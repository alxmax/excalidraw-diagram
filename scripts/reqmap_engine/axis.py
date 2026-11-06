"""The level axis is complete in both directions. A system need groups
architecture requirements, an architecture requirement groups code
requirements, and every requirement below the apex belongs to exactly the
group one rung up. Read from `level:` alone, so a corpus that declares no
rung is never touched (ADR-0019); warn-only, like every rule on the axis
(ADR-0036, at the maintainer's direction). The axis is a tree (ADR-0064):
one parent each, needs nested one deep — read in `levelshape`."""
from . import rulesrepo  # noqa: F401 — RM032 registers after RM001-RM027
from .model import ENFORCED, _as_list, gate_rule

_RUNG_ABOVE = {"code": "architecture", "architecture": "system"}
_RUNG_BELOW = {"system": "architecture", "architecture": "code"}


def _level_of(ctx, rid):
    # implements: ARCH-TRACE-020  # implements: REQ-TRACE-934
    """The declared rung of `rid`, or None when it declares none or does not
    exist."""
    r = ctx.reqs.get(rid)
    return r["meta"].get("level") if r else None


def _group_gap(ctx, rid, level):
    # implements: ARCH-TRACE-020  # implements: REQ-TRACE-934
    """The message for a group with no member one rung down, or None. A
    need nothing satisfies at all is RM015's finding, not repeated here."""
    below = _RUNG_BELOW.get(level)
    if not below:
        return None
    kids = ctx.satisfied_by.get(rid) or []
    if not kids and level == "system":
        return None
    # An apex groups its sub-needs; the architecture sits under those.
    if any(_level_of(ctx, k) in (below, level) for k in kids):
        return None
    return (f"{rid}: level: {level} groups no `level: {below}` requirement "
            f"— every {level} is a group; give it a member one rung down, "
            f"or move it down a rung")


def _parent_gap(ctx, rid, level, meta):
    # implements: ARCH-TRACE-020  # implements: REQ-TRACE-934
    """The message for a requirement with no group one rung up, or None. A
    `satisfies:` id that resolves to nothing is RM005's finding and is
    skipped here."""
    above = _RUNG_ABOVE.get(level)
    if not above:
        return None
    ups = _as_list(meta.get("satisfies"))
    if not ups:
        return (f"{rid}: level: {level} satisfies nothing — every {level} "
                f"belongs to a `level: {above}` group; declare "
                f"`satisfies:`")
    wrong = [u for u in ups if _level_of(ctx, u) not in (None, above)]
    if wrong:
        return (f"{rid}: level: {level} satisfies {', '.join(wrong)} at "
                f"another rung — the group one rung up is "
                f"`level: {above}`")
    return None


@gate_rule("RM032", "warn")
def _pyramid_complete_rule(ctx):
    # implements: ARCH-TRACE-020  # implements: REQ-TRACE-934
    """Both directions, for every enforced requirement that declares a
    rung: a system need with satisfiers but no architecture one, an
    architecture requirement with no code member, a code or architecture
    requirement with no parent, or a parent at the wrong rung. Fired on
    this corpus at 5 of 67 architecture requirements when it was written
    (ADR-0036 records the rate and the decision). The tree's shape is read
    on drafts too: a draft is where a second parent is first written."""
    for rid, r in ctx.reqs.items():
        m = r["meta"]
        level = m.get("level")
        if level not in ("system", "architecture", "code"):
            continue
        from .levelshape import shape_gap   # the level axis is opt-in
        for msg in (shape_gap(ctx, rid, level, m),
                    m.get("status") in ENFORCED and _group_gap(ctx, rid, level),
                    m.get("status") in ENFORCED
                    and _parent_gap(ctx, rid, level, m)):
            if msg:
                yield rid, msg
