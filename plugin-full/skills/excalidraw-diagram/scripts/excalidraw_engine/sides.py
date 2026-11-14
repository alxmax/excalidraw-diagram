"""Which side of its dimensions each fact is drawn on: the search that data_model.py asks.

pack() lays a flipped edge's source on the far side of its target, so every fact-like
table is either left of the dimensions it shares or right of them. Which tables go right
decides how many arrows cross, and the answer depends on the whole graph, so it is
measured rather than guessed: each candidate assignment is packed on a throwaway Scene and
its connectors counted.

Alternating sides (every second table on the right) is the baseline, which is right for two
facts. The search never returns an assignment worse than it, and the same schema always
gives the same answer.
"""

from .pack import PackOptions
from .scene import Scene

FREE_MAX = 8        # most tables whose side is searched: 2^8 = 256 layouts to measure


def _lines(elements):
    """Each connector as its list of segments ((x1, y1), (x2, y2)): arrows and plain lines."""
    out = []
    for el in elements:
        pts = el.get("points") or ()
        if el.get("type") in ("arrow", "line") and len(pts) >= 2:
            xy = [(el["x"] + p[0], el["y"] + p[1]) for p in pts]
            out.append((el.get("type") == "line" or not el.get("startBinding"),
                        list(zip(xy, xy[1:]))))
    return out


def _turn(p, q, r):
    return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])


def _cross(a, b):
    (p1, p2), (p3, p4) = a, b
    return (_turn(p3, p4, p1) * _turn(p3, p4, p2) < 0
            and _turn(p1, p2, p3) * _turn(p1, p2, p4) < 0)


def crossings(elements):
    """(routed, pairs): how many connectors are routed round the diagram instead of drawn
    straight, and how many pairs of connectors cross, in a scene's elements."""
    lines = _lines(elements)
    pairs = sum(1 for i in range(len(lines)) for j in range(i + 1, len(lines))
                if any(_cross(a, b) for a in lines[i][1] for b in lines[j][1]))
    return sum(1 for routed, _ in lines if routed), pairs


def _cost(spec):
    """The crossings of `spec` packed on its own: routed connectors first, because one that
    loops round the diagram is worse than a crossing, then crossing pairs."""
    scene = Scene(seed=spec.get("seed"), roles=spec.get("roles") or {})
    scene.pack(spec["nodes"], spec["edges"], groups=spec.get("groups") or (),
               options=PackOptions())
    return crossings(scene.elements)


def best_right(fact_like, spec_for):
    """The set of `fact_like` names to draw on the far side.

    `spec_for(right)` is the graph description when the names in `right` are on the far
    side. Every assignment is tried when there are at most FREE_MAX tables to place; the
    first one stays on the left, because a mirrored layout costs the same. The alternating
    assignment wins any tie, and beyond FREE_MAX tables it is the answer: the search grows
    as 2^n, and one that never finishes is worse than a layout that is merely good."""
    # implements: REQ-DATAMODEL-913
    alternating = set(fact_like[1::2])
    free = fact_like[1:]
    if not free or len(free) > FREE_MAX:
        return alternating
    best, found = _cost(spec_for(alternating)), alternating
    for mask in range(1 << len(free)):
        right = {name for k, name in enumerate(free) if mask >> k & 1}
        if right == alternating:
            continue
        cost = _cost(spec_for(right))
        if cost < best:
            best, found = cost, right
    return found
