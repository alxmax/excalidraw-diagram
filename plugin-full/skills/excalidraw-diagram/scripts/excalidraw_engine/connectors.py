"""Connectors: bound arrows between two nodes, and unbound paths through points."""

import math

from .geometry import Rect, polyline_midpoint, text_extent
from .style import STROKE, Paint, Style, TextStyle, resolve

# which ends of a connector carry an arrowhead
_HEADS = {"end": (None, "arrow"), "start": ("arrow", None),
          "both": ("arrow", "arrow"), "none": (None, None)}

# clear space kept between a bound arrow's end and the shape border it points at
_ARROW_GAP = 14

# an elbow connector sharing a side with another moves along it by this much, so no
# two of them meet the border at one point (the rule is at least 12px apart)
_PORT_STEP = 24
# two shapes this far into each other's span are joined by one straight leg
_ALIGN_MIN = 24

ROUTED = Paint(stroke="grey", dashed=True)


def _lean(delta, side):
    """A quarter of `side` in the direction of `delta`, when the other shape lies
    beyond this side's half-length; 0 when it lies within it."""
    if abs(delta) <= side / 2:
        return 0.0
    return side / 4 if delta > 0 else -side / 4


def _heads(heads):
    try:
        return _HEADS[heads]
    except KeyError:
        raise ValueError("heads must be one of %s, not %r"
                         % (", ".join(sorted(_HEADS)), heads))


def _line_fields(paint, heads):
    """The arrow-element fields a connector's paint and heads decide."""
    start, end = _heads(heads)
    return {"startArrowhead": start, "endArrowhead": end,
            "strokeStyle": "dashed" if paint.dashed else "solid", "elbowed": False}


class ConnectorsMixin(object):
    """Arrows and routed lines. Every method returns the connector's id."""

    def _border_point(self, gid, toward):
        """Point on the border of node `gid` in the direction of `toward`
        (a global (x, y) point). Handles rectangles, ellipses and diamonds."""
        x, y, w, h, shape = self._geom[gid]
        cx, cy = x + w / 2, y + h / 2
        dx, dy = toward[0] - cx, toward[1] - cy
        if dx == 0 and dy == 0:
            return cx, cy
        if shape == "ellipse":
            ang = math.atan2(dy, dx)
            return cx + (w / 2) * math.cos(ang), cy + (h / 2) * math.sin(ang)
        if shape == "diamond":
            # rhombus boundary: |X|/(w/2) + |Y|/(h/2) = 1 — meet the slanted edge
            t = 1.0 / (2 * abs(dx) / w + 2 * abs(dy) / h)
            return cx + dx * t, cy + dy * t
        scale = 0.5 / max(abs(dx) / w, abs(dy) / h)
        return cx + dx * scale, cy + dy * scale

    def _centre(self, gid):
        x, y, w, h, _shape = self._geom[gid]
        return (x + w / 2, y + h / 2)

    def _endpoints(self, src, dst):
        """Where a bound arrow starts and ends: just outside each border, with
        the gap clamped when the shapes are close so the ends never cross."""
        b0 = self._border_point(src, self._centre(dst))
        b1 = self._border_point(dst, self._centre(src))
        dist = math.hypot(b1[0] - b0[0], b1[1] - b0[1]) or 1.0
        g = min(_ARROW_GAP, max(2.0, (dist - 10) / 2))
        ux, uy = (b1[0] - b0[0]) / dist, (b1[1] - b0[1]) / dist
        return (b0[0] + ux * g, b0[1] + uy * g), (b1[0] - ux * g, b1[1] - uy * g), g

    def arrow(self, src, dst, *, label=None, paint=None, heads="end", curve=False,
              elbow=False):
        """A bound arrow from node `src` to node `dst`.

        paint: a Paint, or a stroke colour ("accent" is the scene's accent).
        heads: end, start, both or none. curve=True bends it through a raised
        midpoint. elbow=True draws it with right angles only: one straight leg
        when the shapes share a row or column, else three legs that turn in the
        gap between them, each end on its own point of the side it meets."""
        # implements: REQ-EXCALIDRAW-845  # implements: REQ-EXCALIDRAW-861
        paint = Paint.coerce(paint, natural="stroke")
        if elbow:
            route, g = self._elbow_route(src, dst, bool(label))
            p0 = route[0]
        else:
            p0, p1, g = self._endpoints(src, dst)
            route = [p0, p1]
        ax, ay = p0
        pts = [[p[0] - ax, p[1] - ay] for p in route]
        if curve and not elbow:
            pts = [pts[0], [pts[1][0] / 2, pts[1][1] / 2 - 30], pts[1]]
        # the bounding box spans every point, a curve's control point included
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        aid = self._new_id("arrow")
        el = self._base(aid, "arrow", Rect(ax, ay, max(xs) - min(xs), max(ys) - min(ys)),
                        Style(resolve(self._stroke_of(paint.stroke), STROKE, STROKE["black"]),
                              roundness={"type": 2} if curve else None, group=paint.group))
        el.update({"points": pts, "lastCommittedPoint": None,
                   "startBinding": {"elementId": src, "focus": 0.0, "gap": g},
                   "endBinding": {"elementId": dst, "focus": 0.0, "gap": g}})
        el.update(_line_fields(paint, heads))
        if elbow:
            self._elbows.add(aid)
        for nid in (src, dst):           # the binding is recorded on both ends
            node = self._element(nid)
            if node is not None:
                node["boundElements"].append({"type": "arrow", "id": aid})
        self.elements.append(el)
        if label:
            self._arrow_label(el, label, paint.group)
        return aid

    def _arrow_label(self, el, label, group):
        """Bind `label` to the middle of arrow element `el`, where the editor puts
        it: the middle point of an odd count, the middle leg's midpoint of an even."""
        tw, th = text_extent(label, 14)
        pts = el["points"]
        if len(pts) % 2 == 0:
            a, b = pts[len(pts) // 2 - 1], pts[len(pts) // 2]
            mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        else:
            mx, my = pts[len(pts) // 2]
        rect = Rect(el["x"] + mx - tw / 2, el["y"] + my - th / 2, tw, th)
        tel = self._text_el(label, rect, TextStyle(14, STROKE["grey"]),
                            container=el["id"], group=group)
        el["boundElements"].append({"type": "text", "id": tel["id"]})
        self.elements.append(tel)

    # -- right-angle connectors --------------------------------------------
    def _port(self, ends, span, toward=0.0):
        """The offset from a side's midpoint for the next connector that meets it.

        `ends` is the (node id, side) pairs the leg touches (a straight leg takes
        an offset free at both), `span` how far either way it may go. The first
        choice leans a quarter of the side `toward` the other shape (its sign),
        so two connectors leaving for opposite sides part at once; after that
        the offsets step by 24px, and no two connectors meet a side closer than
        that, so each keeps its own attach point."""
        span = max(0.0, span)
        base = max(-span, min(span, toward))
        used = [u for end in ends for u in self._ports.get(end, ())]
        pick = base
        for k in range(0, 40):
            off = base + _PORT_STEP * ((k + 1) // 2) * (1 if k % 2 else -1)
            off = max(-span, min(span, off))
            if all(abs(off - u) >= _PORT_STEP - 0.5 for u in used):
                pick = off
                break
        for end in ends:
            self._ports.setdefault(end, []).append(pick)
        return pick

    def _elbow_route(self, src, dst, labelled):
        """[(x, y), ...] for a right-angle connector, and its gap from the borders.

        Shapes that share enough of a row or a column get one straight leg in the
        shared span. Otherwise the connector leaves the side facing the target,
        turns once in the gap between them, and enters the facing side: a label
        reads best on a horizontal leg, so a labelled connector turns in the
        vertical gap when there is one."""
        sx, sy, sw, sh, _ = self._geom[src]
        dx, dy, dw, dh, _ = self._geom[dst]
        g = _ARROW_GAP
        right = dx >= sx + sw        # the target lies wholly to the right ...
        left = dx + dw <= sx         # ... or wholly to the left
        below = dy >= sy + sh
        above = dy + dh <= sy
        lo_y, hi_y = max(sy, dy), min(sy + sh, dy + dh)
        lo_x, hi_x = max(sx, dx), min(sx + sw, dx + dw)
        if (right or left) and hi_y - lo_y >= _ALIGN_MIN:
            sides = ((src, "right"), (dst, "left")) if right else ((src, "left"), (dst, "right"))
            y = (lo_y + hi_y) / 2 + self._port(sides, (hi_y - lo_y) / 2 - 8)
            x0, x1 = (sx + sw + g, dx - g) if right else (sx - g, dx + dw + g)
            return [(x0, y), (x1, y)], g
        if (below or above) and hi_x - lo_x >= _ALIGN_MIN:
            sides = ((src, "bottom"), (dst, "top")) if below else ((src, "top"), (dst, "bottom"))
            x = (lo_x + hi_x) / 2 + self._port(sides, (hi_x - lo_x) / 2 - 8)
            y0, y1 = (sy + sh + g, dy - g) if below else (sy - g, dy + dh + g)
            return [(x, y0), (x, y1)], g
        vertical_first = (below or above) and (labelled or not (right or left))
        if vertical_first or not (right or left):
            s_side, d_side = ("bottom", "top") if below else ("top", "bottom")
            lean = (dx + dw / 2) - (sx + sw / 2)        # + when the target is right
            x0 = sx + sw / 2 + self._port(((src, s_side),), sw / 2 - 8,
                                          _lean(lean, sw))
            x1 = dx + dw / 2 + self._port(((dst, d_side),), dw / 2 - 8,
                                          _lean(-lean, dw))
            y0, y1 = (sy + sh + g, dy - g) if below else (sy - g, dy + dh + g)
            mid = ((sy + sh + dy) / 2) if below else ((dy + dh + sy) / 2)
            return [(x0, y0), (x0, mid), (x1, mid), (x1, y1)], g
        s_side, d_side = ("right", "left") if right else ("left", "right")
        lean = (dy + dh / 2) - (sy + sh / 2)            # + when the target is below
        y0 = sy + sh / 2 + self._port(((src, s_side),), sh / 2 - 8, _lean(lean, sh))
        y1 = dy + dh / 2 + self._port(((dst, d_side),), dh / 2 - 8, _lean(-lean, dh))
        x0, x1 = (sx + sw + g, dx - g) if right else (sx - g, dx + dw + g)
        mid = ((sx + sw + dx) / 2) if right else ((dx + dw + sx) / 2)
        return [(x0, y0), (mid, y0), (mid, y1), (x1, y1)], g

    def free_arrow(self, p0, p1, **kw):
        """An unbound arrow between two absolute points."""
        return self.path([p0, p1], **kw)

    def path(self, points, *, label=None, paint=None, heads="end"):
        """An unbound multi-point connector through absolute (x, y) points — a
        routed line that visibly joins its two ends instead of floating."""
        paint = Paint.coerce(paint, natural="stroke")
        aid = self._new_id("arrow")
        ax, ay = points[0]
        rel = [[p[0] - ax, p[1] - ay] for p in points]
        xs, ys = [p[0] for p in rel], [p[1] for p in rel]
        self._path_extents.append((min(p[0] for p in points), min(p[1] for p in points),
                                   max(p[0] for p in points), max(p[1] for p in points)))
        el = self._base(aid, "arrow", Rect(ax, ay, max(xs) - min(xs), max(ys) - min(ys)),
                        Style(resolve(self._stroke_of(paint.stroke), STROKE, STROKE["black"]),
                              group=paint.group))
        el.update({"points": rel, "lastCommittedPoint": None,
                   "startBinding": None, "endBinding": None})
        el.update(_line_fields(paint, heads))
        self.elements.append(el)
        if label:
            self._path_label(points, label, paint.group)
        return aid

    def _path_label(self, points, label, group):
        """A label at the path's arc-length midpoint, on a white knock-out panel.

        The panel is overlap-CHECKED: a routed label landing on a box hides the
        box, which is a real overlap. It stays out of the geometry registry, so
        it is never an arrow-crossing obstacle for the line running under it.
        Returns the panel's id."""
        mid = polyline_midpoint(points)
        tw, th = text_extent(label, 13)
        lx, ly = mid[0] - tw / 2, mid[1] + 8
        panel = Rect(lx - 4, ly - 2, tw + 8, th + 4)
        bg = self._base(self._new_id("rectangle"), "rectangle", panel,
                        Style("transparent", "#ffffff",
                              roundness={"type": 3}))
        self.elements.append(bg)
        self._nodes.append((bg["id"], panel.x, panel.y, panel.w, panel.h,
                            f'label "{label.splitlines()[0][:24]}"'))
        self.elements.append(self._text_el(label, Rect(lx, ly, tw, th),
                                           TextStyle(13, STROKE["grey"]), group=group))
        return bg["id"]

    def route_under(self, src, dst, *, drop=70, label=None, paint=None):
        """A connector that leaves the bottom of `src`, runs `drop` px below the
        row, and returns into the bottom of `dst` — clear of the boxes between.
        Dashed grey unless `paint` says otherwise."""
        sx, sy, sw, sh, _ = self._geom[src]
        dx, dy, dw, dh, _ = self._geom[dst]
        start, end = (sx + sw / 2, sy + sh), (dx + dw / 2, dy + dh)
        low = max(sy + sh, dy + dh) + drop
        return self.path([start, (start[0], low), (end[0], low), end], label=label,
                         paint=Paint.coerce(paint, natural="stroke", default=ROUTED))
