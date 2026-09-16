"""Placing several shapes without hand-computing coordinates: rows, columns and
grids, the pipeline band, the frames that group them, and moving placed nodes."""

import sys

from .geometry import as_point
from .shapes import SIZES
from .style import DASHED, Font, Paint

# the keys an item (or a cell template) may carry — box()'s options, by name
_ITEM_KEYS = {"text", "size", "paint", "font", "shape", "container"}
_GAPS = {"x": 80, "y": 60}
_GRID_GAP = (40, 30)

# a pipeline step's default size, per kind: flowchart proportions for a band
_STEP_SIZES = {
    "terminator": (120, 48), "process": (150, 64), "decision": (180, 92),
    "data": (170, 64), "predefined_process": (180, 64),
    "preparation": (190, 78), "connector": (46, 46), "box": (160, 70),
}
_STEP_SHAPES = {"box": "rectangle", "decision": "diamond"}

CAPTION_FONT = Font(13, "grey", "center")
LANE_FONT = Font(14, "black", "left")


def _item(it):  # implements: REQ-EXCALIDRAW-853
    """One arrange() item as a dict of box() options. An item is a text string,
    a (text, paint) pair, or a dict using box()'s option names."""
    if isinstance(it, dict):
        unknown = set(it) - _ITEM_KEYS
        if unknown:
            raise ValueError("unknown item key(s) %s; an item takes %s"
                             % (sorted(unknown), ", ".join(sorted(_ITEM_KEYS))))
        return dict(it)
    if isinstance(it, (tuple, list)):
        return {"text": it[0], "paint": it[1]} if len(it) > 1 else {"text": it[0]}
    return {"text": str(it)}


def _step(st):
    """One pipeline step as a dict: a text string, a (text, kind[, paint]) tuple,
    or a dict of {text, kind, paint, size, label, font}."""
    if isinstance(st, str):
        d = {"text": st}
    elif isinstance(st, (tuple, list)):
        d = dict(zip(("text", "kind", "paint"), st))
    else:
        d = dict(st)
    d.setdefault("kind", "process")
    if d["kind"] not in _STEP_SIZES:
        raise ValueError("unknown pipeline step kind %r; use one of %s"
                         % (d["kind"], ", ".join(sorted(_STEP_SIZES))))
    d.setdefault("size", _STEP_SIZES[d["kind"]])
    return d


class ArrangeMixin(object):  # implements: REQ-EXCALIDRAW-844
    """Multi-shape placement. Placing methods return the node ids in order."""

    def arrange(self, items, at, *, across="x", cell=None, gap=None, connect=False):
        """Place items starting at `at` and return their ids.

        across:  "x" left -> right, "y" top -> down, or an int column count for a
                 row-major grid of uniform cells.
        cell:    the defaults every item overrides — a dict of box() options
                 (size, paint, font, shape, container).
        gap:     the space between items; a grid takes an (x, y) pair.
        connect: chain consecutive items with arrows."""
        cell = _item(cell or {})
        gap = self._gap(across, gap)
        if connect and across == "x" and gap < 80:
            print(f"excalidraw_builder: row gap={gap}px with connect=True — arrows "
                  f"may be invisible (recommended: >=80px)", file=sys.stderr)
        x, y = as_point(at)
        ids, cursor = [], [x, y]
        for i, it in enumerate(items):
            opts = dict(cell, **_item(it))
            size = opts.get("size") or SIZES[opts.get("shape", "rectangle")]
            if isinstance(across, int):
                csize = cell.get("size") or SIZES[cell.get("shape", "rectangle")]
                r, c = divmod(i, across)
                cursor = [x + c * (csize[0] + gap[0]), y + r * (csize[1] + gap[1])]
            ids.append(self._place(opts, cursor, size))
            if across == "x":
                cursor[0] += size[0] + gap
            elif across == "y":
                cursor[1] += size[1] + gap
        if connect:
            for a, b in zip(ids, ids[1:]):
                self.arrow(a, b)
        return ids

    @staticmethod
    def _gap(across, gap):
        """The gap for this direction, defaulted and validated."""
        if isinstance(across, int) and not isinstance(across, bool):
            if across < 1:
                raise ValueError("a grid needs at least one column")
            g = _GRID_GAP if gap is None else gap
            return (g, g) if isinstance(g, (int, float)) else tuple(g)
        if across not in _GAPS:
            raise ValueError("across must be 'x', 'y' or a column count, not %r" % (across,))
        return _GAPS[across] if gap is None else gap

    def _place(self, opts, xy, size):
        """Draw one resolved item at `xy`."""
        return self.box(opts.get("text", ""), (xy[0], xy[1], size[0], size[1]),
                        paint=opts.get("paint"), font=opts.get("font"),
                        shape=opts.get("shape", "rectangle"),
                        container=opts.get("container", False))

    def row(self, items, at, **kw):
        """arrange() left -> right."""
        return self.arrange(items, at, across="x", **kw)

    def column(self, items, at, **kw):
        """arrange() top -> down."""
        return self.arrange(items, at, across="y", **kw)

    def grid(self, items, at, cols, **kw):
        """arrange() in a `cols`-wide grid of uniform cells."""
        return self.arrange(items, at, across=cols, **kw)

    def pipeline(self, steps, at, *, gap=80, band=None, font=None, connect=True):
        """A horizontal flowchart band, left -> right, vertically centred on one
        midline, chained with bound arrows. Each step is a string, a
        (text, kind[, paint]) tuple, or a dict of {text, kind, paint, size, label,
        font}; `kind` is an ISO shape verb or "box"; a step's `label` names the
        arrow leaving it. `band` fixes the band height. Returns the node ids."""
        norm = [_step(st) for st in steps]
        if not norm:
            return []
        if connect and gap < 80 and any(d.get("label") for d in norm):
            print(f"excalidraw_builder: pipeline gap={gap}px with labeled arrows — "
                  f"labels may overlap (recommended: >=80px; >=100px for multi-word "
                  f"labels)", file=sys.stderr)
        font = Font.coerce(font, Font(14))
        x, y = as_point(at)
        mid = y + (band or max(d["size"][1] for d in norm)) / 2
        for d in norm:
            w, h = d["size"]
            d["_id"] = self.box(d["text"], (x, mid - h / 2, w, h), paint=d.get("paint"),
                                font=Font.coerce(d.get("font"), font),
                                shape=_STEP_SHAPES.get(d["kind"], d["kind"]))
            x += w + gap
        if connect:
            for a, b in zip(norm, norm[1:]):
                self.arrow(a["_id"], b["_id"], label=a.get("label"))
        return [d["_id"] for d in norm]

    # -- grouping frames ---------------------------------------------------
    def enclose(self, ids, *, label=None, pad=24, paint=None, caption=None):
        """A frame auto-sized around placed nodes (call it after placing them,
        so it sits behind), dashed unless `paint` is given, with an optional
        caption centred above. Returns the frame id."""
        if not ids:
            raise ValueError("enclose() needs at least one node id")
        geoms = [self._geom[i] for i in ids]
        x0, y0 = min(g[0] for g in geoms), min(g[1] for g in geoms)
        x1 = max(g[0] + g[2] for g in geoms)
        y1 = max(g[1] + g[3] for g in geoms)
        fx, fy = x0 - pad, y0 - pad
        fw, fh = (x1 - x0) + 2 * pad, (y1 - y0) + 2 * pad
        fid = self.frame((fx, fy, fw, fh), paint=DASHED if paint is None else paint)
        if label:
            self.label(label, (fx + fw / 2, fy - 22),
                       font=Font.coerce(caption, CAPTION_FONT))
        return fid

    def lane(self, ids, label, *, pad=24, paint=None, caption=None):
        """A swimlane: a solid frame around `ids` with a prominent top-left
        header — to group a stage or an actor."""
        fid = self.enclose(ids, pad=pad, paint=Paint.coerce(paint))
        fx, fy, _fw, _fh, _ = self._geom[fid]
        self.label(label, (fx + 12, fy + 8), font=Font.coerce(caption, LANE_FONT))
        return fid

    # -- adjusting placed nodes -------------------------------------------
    # One entry per alignment axis: `target` reduces the selected geometries to
    # the shared coordinate, `place` says where one node goes once it is known.
    # Each geometry is the (x, y, w, h, shape) tuple the registry stores.
    _ALIGN_AXES = {
        "left":     (lambda gs: min(g[0] for g in gs),
                     lambda t, g: (t, g[1])),
        "right":    (lambda gs: max(g[0] + g[2] for g in gs),
                     lambda t, g: (t - g[2], g[1])),
        "center_x": (lambda gs: sum(g[0] + g[2] / 2 for g in gs) / len(gs),
                     lambda t, g: (t - g[2] / 2, g[1])),
        "top":      (lambda gs: min(g[1] for g in gs),
                     lambda t, g: (g[0], t)),
        "bottom":   (lambda gs: max(g[1] + g[3] for g in gs),
                     lambda t, g: (g[0], t - g[3])),
        "center_y": (lambda gs: sum(g[1] + g[3] / 2 for g in gs) / len(gs),
                     lambda t, g: (g[0], t - g[3] / 2)),
    }

    def align(self, ids, axis="center_x"):
        """Align placed nodes on a shared edge or axis: left, right, center_x,
        top, bottom or center_y. Mutates positions and keeps the overlap check
        honest. Returns ids."""
        try:
            target_of, placed_at = self._ALIGN_AXES[axis]
        except KeyError:
            raise ValueError(f"align: unknown axis {axis!r}")
        # dict first: a repeated id must count once toward a centre average
        geoms = {i: self._geom[i] for i in ids}
        target = target_of(list(geoms.values()))
        for i in ids:
            self._move_node(i, *placed_at(target, geoms[i]))
        return ids

    def distribute(self, ids, axis="x", *, gap=40):
        """Space placed nodes evenly along 'x' or 'y', in their current order,
        `gap` px apart. Mutates positions. Returns ids."""
        if axis not in ("x", "y"):
            raise ValueError("distribute: axis must be 'x' or 'y'")
        k = 0 if axis == "x" else 1
        order = sorted(ids, key=lambda i: self._geom[i][k])
        cur = self._geom[order[0]][k] if order else 0
        for i in order:
            x, y, w, h, _s = self._geom[i]
            self._move_node(i, *((cur, y) if k == 0 else (x, cur)))
            cur += (w, h)[k] + gap
        return ids
