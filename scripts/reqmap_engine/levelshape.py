"""The level axis as a tree (ADR-0064): one parent each, needs nested one
deep — an apex, then its sub-needs — and no parent past its fan-out band.

Loaded at call time, only for a corpus that declares a `level:` or by the
commands that write one, the way the plan's modules load only for a repo
that keeps a plan (ADR-0057); a corpus with no rung never imports it."""
from . import config as cfg
from .axis import _RUNG_ABOVE, _level_of
from .model import _as_list

_PARENT_RUNG = dict(_RUNG_ABOVE, system="system")


def shape_gap(ctx, rid, level, meta):
    # implements: ARCH-TRACE-020  # implements: REQ-TRACE-934
    """The message for a requirement whose parents break the tree, or None:
    two parents on the rung above, a sub-need under a sub-need, or an
    architecture requirement on an apex that has sub-needs."""
    rung = _PARENT_RUNG[level]
    ups = [u for u in _as_list(meta.get("satisfies"))
           if _level_of(ctx, u) == rung]
    if len(ups) > 1:
        return (f"{rid}: level: {level} satisfies {len(ups)} `level: {rung}` "
                f"requirements ({', '.join(ups)}) — the axis is a tree; keep "
                f"the one it belongs to and move the others to `depends_on`")
    if not ups or level == "code":
        return None
    up_meta, kids = ctx.reqs[ups[0]]["meta"], ctx.satisfied_by.get(ups[0], [])
    if level == "system" and any(_level_of(ctx, u) == "system"
                                 for u in _as_list(up_meta.get("satisfies"))):
        return (f"{rid}: level: system under the sub-need {ups[0]} — needs "
                f"nest one deep: an apex, then its sub-needs")
    if level == "architecture" and any(_level_of(ctx, k) == "system"
                                       for k in kids):
        return (f"{rid}: satisfies {ups[0]}, an apex with sub-needs — point "
                f"it at the sub-need it serves")
    return None


def note_over_band(children, level):
    # implements: ARCH-EXTRACT-008  # implements: REQ-EXTRACT-981
    # implements: ARCH-LEVELRETROFIT-066  # implements: REQ-LEVELRETROFIT-987
    """Print one note naming the `level` parents a write gave more children
    (`{parent: count}`) than their LINT_FANOUT_BANDS ceiling; silent when
    none does. The lint never reads a draft, so without this `init` wrote a
    placeholder ten times past its band in silence."""
    ceiling = cfg.LINT_FANOUT_BANDS.get(level, (None, cfg.LINT_FANOUT_MAX))[1]
    over = sorted((n, pid) for pid, n in children.items() if n > ceiling)
    if over:
        print("note: {} `level: {}` parent(s) hold more than {} children "
              "(largest: {}, {}) - split each into the areas a reader would "
              "name, ex. by the words its children's names share".format(
                  len(over), level, ceiling, over[-1][1], over[-1][0]))
