"""Plane geometry the builder needs, with no scene in sight: rectangles, text
extents, segment clipping and polyline midpoints. Everything here is a pure function
of its arguments, so the layout maths can be tested without drawing anything."""

import math


class Rect(object):  # implements: REQ-EXCALIDRAW-844
    """The (x, y, w, h) box that travels together through nearly every builder
    call. Holding the four as one value keeps width from being passed where
    height belongs, and gives the layout code the derived edges it used to
    recompute by hand at each call site."""

    __slots__ = ("x", "y", "w", "h")

    def __init__(self, x, y, w=0.0, h=0.0):
        self.x, self.y = float(x), float(y)
        self.w, self.h = float(w), float(h)

    @property
    def right(self):
        """The x of the right edge."""
        return self.x + self.w

    @property
    def bottom(self):
        """The y of the bottom edge."""
        return self.y + self.h

    @property
    def cx(self):
        """The x of the centre."""
        return self.x + self.w / 2.0

    @property
    def cy(self):
        """The y of the centre."""
        return self.y + self.h / 2.0

    def centred(self, w, h):
        """A `w` x `h` rect centred inside this one — how every bound label
        is positioned within the shape that carries it."""
        return Rect(self.x + (self.w - w) / 2.0, self.y + (self.h - h) / 2.0, w, h)

    def __iter__(self):
        """Unpacks as `x, y, w, h`."""
        return iter((self.x, self.y, self.w, self.h))

    def __eq__(self, other):
        return isinstance(other, Rect) and tuple(self) == tuple(other)

    def __repr__(self):
        return "Rect({:g}, {:g}, {:g}, {:g})".format(self.x, self.y, self.w, self.h)


def as_rect(at, size=None):  # implements: REQ-EXCALIDRAW-853
    """`at` as a Rect. It may already be one, an `(x, y, w, h)` tuple, or an
    `(x, y)` point that takes its width and height from `size`."""
    if isinstance(at, Rect):
        return at
    parts = tuple(at)
    if len(parts) == 4:
        return Rect(*parts)
    if len(parts) == 2:
        if size is None:
            raise ValueError("a point (x, y) needs a size here; pass (x, y, w, h)")
        return Rect(parts[0], parts[1], size[0], size[1])
    raise ValueError("expected (x, y) or (x, y, w, h), got %r" % (at,))


def as_point(at):
    """`at` as an `(x, y)` tuple — a point, or the top-left of a rect."""
    if isinstance(at, Rect):
        return at.x, at.y
    parts = tuple(at)
    if len(parts) not in (2, 4):
        raise ValueError("expected (x, y), got %r" % (at,))
    return parts[0], parts[1]


def text_extent(text, size):
    """The (w, h) a run of text occupies at font `size` — the heuristic every
    label, check and layout agrees on."""
    lines = text.split("\n")
    longest = max((len(ln) for ln in lines), default=1)
    w = max(longest * size * 0.58, 8)
    h = len(lines) * size * 1.25
    return w, h


def fit_text(text, *, size=14, max_chars=20, min_size=(120, 48)):
    """Word-wrap `text` to <=max_chars per line and return (wrapped, w, h) sized
    so the text never overflows its box. Use it for a box whose label length is
    not known in advance. The width margin is wider than text_extent's factor,
    so a box sized here always clears check_text_overflow()."""
    words, lines, cur = text.split(), [], ""
    for w in words:
        if not cur or len(cur) + 1 + len(w) <= max_chars:
            cur = (cur + " " + w).strip()
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    longest = max((len(ln) for ln in lines), default=1)
    width = max(min_size[0], int(longest * size * 0.6) + 24)
    height = max(min_size[1], int(len(lines) * size * 1.6) + 18)
    return "\n".join(lines), width, height


def free_spans(legs, band, margin=8.0):
    """The x-intervals of `band` (x, y, w, h) that no segment in `legs` passes
    through, each leg widened by `margin`, widest first."""
    bx, by, bw, bh = band
    blocked = []
    for (ax, ay), (cx, cy) in legs:
        if ay == cy:
            if not by <= ay <= by + bh:
                continue
            t0, t1 = 0.0, 1.0
        else:
            t0, t1 = sorted(((by - ay) / (cy - ay), (by + bh - ay) / (cy - ay)))
            t0, t1 = max(t0, 0.0), min(t1, 1.0)
            if t0 > t1:
                continue
        xs = (ax + (cx - ax) * t0, ax + (cx - ax) * t1)
        blocked.append((min(xs) - margin, max(xs) + margin))
    spans, cur = [], bx
    for lo, hi in sorted(blocked):
        if lo > cur:
            spans.append((cur, min(lo, bx + bw)))
        cur = max(cur, hi)
    if cur < bx + bw:
        spans.append((cur, bx + bw))
    return sorted((sp for sp in spans if sp[1] > sp[0]),
                  key=lambda sp: sp[0] - sp[1])


def seg_rect_overlap(p0, p1, rect):
    """Length of the portion of segment p0->p1 that lies inside `rect`
    (x, y, w, h); 0 if it never enters. Liang–Barsky slab clipping."""
    x0, y0 = p0
    rx, ry, rw, rh = rect
    dx, dy = p1[0] - x0, p1[1] - y0
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x0 - rx), (dx, rx + rw - x0),
                 (-dy, y0 - ry), (dy, ry + rh - y0)):
        if p == 0:
            if q < 0:
                return 0.0              # parallel to a slab and outside it
            continue
        r = q / p
        if p < 0:
            if r > t1:
                return 0.0
            t0 = max(t0, r)
        else:
            if r < t0:
                return 0.0
            t1 = min(t1, r)
    if t1 <= t0:
        return 0.0
    return (t1 - t0) * math.hypot(dx, dy)


def polyline_midpoint(points):
    """The point at half the total arc length along a polyline — the visual
    middle of a routed connector, not a corner waypoint."""
    if len(points) < 2:
        return points[0]
    segs = [(a, b, math.hypot(b[0] - a[0], b[1] - a[1]))
            for a, b in zip(points, points[1:])]
    total = sum(d for _, _, d in segs)
    if total == 0:
        return points[0]
    half, acc = total / 2, 0.0
    for a, b, d in segs:
        if acc + d >= half:
            t = (half - acc) / d if d else 0.0
            return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
        acc += d
    return points[-1]


def overlap_2d(a, b):
    """How far two (x, y, w, h) boxes overlap along each axis, as (ox, oy).
    Both are positive only when the boxes really intersect."""
    ox = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
    oy = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    return ox, oy
