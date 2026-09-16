"""The seven inspection checks: what makes a diagram unreadable while its JSON
stays perfectly valid. Each returns its offenders, `[]` when clean, and none of
them writes or raises — save() decides what a hit means (see gates.py)."""

import math

from .geometry import overlap_2d, seg_rect_overlap

_FILLABLE = {"rectangle", "ellipse", "diamond"}


def _bound_ends(el):
    """(src id, dst id) for an arrow bound at both ends, else None."""
    if el.get("type") != "arrow":
        return None
    sb, eb = el.get("startBinding"), el.get("endBinding")
    if not sb or not eb:
        return None
    return sb["elementId"], eb["elementId"]


class ChecksMixin(object):
    """Readability checks over the scene built so far."""

    def _labels(self):
        return {nid: lab for (nid, _x, _y, _w, _h, lab) in self._nodes}

    def check_overlaps(self, min_px=1.0):
        """[(label_a, label_b), ...] for every pair of non-container nodes whose
        boxes overlap by more than `min_px` in BOTH axes. Containers (frames and
        container=True shapes) are exempt: they sit behind their children."""
        # implements: REQ-EXCALIDRAW-847
        nodes = self._nodes
        hits = []
        for i, a in enumerate(nodes):
            for b in nodes[i + 1:]:
                ox, oy = overlap_2d(a[1:5], b[1:5])
                if ox > min_px and oy > min_px:
                    hits.append((a[5], b[5]))
        return hits

    def _straight_hits(self, src, dst, threshold=12.0, inset=4.0):
        """Ids of the nodes a straight src -> dst centre line would cut through.
        pack() asks it BEFORE drawing, to choose a straight arrow or a route."""
        p0, p1 = self._centre(src), self._centre(dst)
        # a container endpoint: stop at its border, not at its children
        if src in self._containers:
            p0 = self._border_point(src, p1)
        if dst in self._containers:
            p1 = self._border_point(dst, p0)
        hits = []
        for nid, (nx, ny, nw, nh, _s) in self._geom.items():
            if nid in (src, dst) or nid in self._containers:
                continue
            rw, rh = nw - 2 * inset, nh - 2 * inset
            if rw > 0 and rh > 0 and seg_rect_overlap(
                    p0, p1, (nx + inset, ny + inset, rw, rh)) > threshold:
                hits.append(nid)
        return hits

    def check_arrow_crossings(self, threshold=12.0, inset=4.0):
        """[(src, dst, crossed), ...] where a bound arrow's straight path runs
        through an unrelated node by more than `threshold` px. Endpoints,
        containers and unbound connectors are ignored."""
        # implements: REQ-EXCALIDRAW-846
        labels = self._labels()
        hits = []
        for el in self.elements:
            ends = _bound_ends(el)
            if not ends or ends[0] not in self._geom or ends[1] not in self._geom:
                continue
            for nid in self._straight_hits(ends[0], ends[1], threshold, inset):
                hits.append((labels.get(ends[0], "?"), labels.get(ends[1], "?"),
                             labels.get(nid, "?")))
        return hits

    def check_legend_coverage(self):
        """Sorted fill colours used by real nodes that the legend does NOT
        explain — `[]` when the legend covers every fill, or no legend exists.
        Colour is the single source of truth for role, so an unexplained fill is
        a silent inconsistency. Transparent, white and the background are neutral."""
        # implements: REQ-EXCALIDRAW-846
        if not self._legend_colours:
            return []
        neutral = {"transparent", "#ffffff", self.background}
        used = set()
        for el in self.elements:
            # ISO polygons serialise as type "line" with polygon:True but carry a
            # real fill, so they count too
            if el["id"] in self._containers or not (
                    el.get("type") in _FILLABLE or el.get("polygon")):
                continue
            bg = el.get("backgroundColor")
            if bg and bg not in neutral:
                used.add(bg)
        return sorted(used - self._legend_colours)

    def check_text_overflow(self, tol=2.0):
        """[(label, text_w, box_w, text_h, box_h), ...] for bound text bigger
        than its shape by more than `tol` px — a label spilling onto neighbours,
        which the shape-overlap check cannot see. Arrow labels are ignored."""
        # implements: REQ-EXCALIDRAW-846
        by_id = {e["id"]: e for e in self.elements}
        hits = []
        for e in self.elements:
            cont = by_id.get(e.get("containerId")) if e.get("type") == "text" else None
            if not cont or cont.get("type") not in _FILLABLE:
                continue
            tw, th = e.get("width", 0), e.get("height", 0)
            cw, ch = cont.get("width", 0), cont.get("height", 0)
            if tw - cw > tol or th - ch > tol:
                hits.append(((e.get("text") or "").split("\n")[0], round(tw, 1),
                             round(cw, 1), round(th, 1), round(ch, 1)))
        return hits

    def check_text_overlaps(self, tol=2.0):
        """[(text_a, text_b), ...] for pairs of FREE text elements (titles,
        labels, section headings) overlapping by more than `tol` px in both
        axes. Bound text — inside a box or on an arrow — is excluded."""
        # implements: REQ-EXCALIDRAW-847
        free = [(e["x"], e["y"], e.get("width", 0), e.get("height", 0),
                 (e.get("text") or "")[:40])
                for e in self.elements
                if e.get("type") == "text" and not e.get("containerId")]
        hits = []
        for i, a in enumerate(free):
            for b in free[i + 1:]:
                ox, oy = overlap_2d(a, b)
                if ox > tol and oy > tol:
                    hits.append((a[4], b[4]))
        return hits

    def check_short_arrows(self, min_len=24.0):
        """[(src_label, dst_label, length), ...] for bound arrows shorter than
        `min_len` px. Two close but non-overlapping shapes clamp the arrow toward
        zero length, and Excalidraw then draws only its floating label. Unbound
        connectors are intentional routed lines and are not checked."""
        # implements: REQ-EXCALIDRAW-847
        labels = self._labels()
        hits = []
        for el in self.elements:
            ends, pts = _bound_ends(el), el.get("points") or []
            if not ends or len(pts) < 2:
                continue
            length = math.hypot(pts[-1][0] - pts[0][0], pts[-1][1] - pts[0][1])
            if length < min_len:
                src, dst = ends
                hits.append((labels.get(src, "?"), labels.get(dst, "?"), round(length, 1)))
        return hits

    def check_arrow_label_fit(self, min_stub=24.0):
        """[(label, stub_px), ...] for bound arrows whose label leaves less than
        `min_stub` px of visible line on each side. The label's box is projected
        onto the arrow's direction; a negative stub means the label spills onto
        the joined boxes, which neither text check sees."""
        # implements: REQ-EXCALIDRAW-847
        by_id = {e["id"]: e for e in self.elements}
        hits = []
        for el in self.elements:
            pts = el.get("points") or []
            if not _bound_ends(el) or len(pts) < 2:
                continue
            lab = next((by_id.get(b["id"]) for b in (el.get("boundElements") or [])
                        if b.get("type") == "text"), None)
            dx, dy = pts[-1][0] - pts[0][0], pts[-1][1] - pts[0][1]
            line = math.hypot(dx, dy)
            if not lab or line == 0:       # zero length is check_short_arrows' job
                continue
            # the label box's extent along the arrow's direction
            extent = (abs(lab.get("width", 0) * dx) + abs(lab.get("height", 0) * dy)) / line
            stub = (line - extent) / 2
            if stub < min_stub:
                hits.append(((lab.get("text") or "").split("\n")[0], round(stub, 1)))
        return hits
