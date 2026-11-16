"""Shapes that carry a label: the native primitives, the ISO 5807 flowchart set
and the frame that sits behind a group of them."""

from .geometry import Rect, as_rect, text_extent
from .style import FILL, STROKE, TYPEFACES, Font, Paint, Style, TextStyle, ink_on, resolve

# The size a shape gets when the caller gives only a point. A flowchart symbol has
# its own proportions, so the default follows the shape rather than the call.
SIZES = {
    "rectangle": (160, 70), "ellipse": (170, 110), "diamond": (160, 90),
    "process": (170, 64), "terminator": (170, 54), "decision": (180, 100),
    "data": (190, 66), "predefined_process": (185, 66), "preparation": (200, 82),
    "connector": (46, 46),
}

# ISO 5807 names that render on a native Excalidraw primitive:
# name -> (excalidraw type, roundness, decoration)
_NATIVE = {
    "rectangle":          ("rectangle", {"type": 3}, None),
    "ellipse":            ("ellipse", None, None),
    "diamond":            ("diamond", None, None),
    "process":            ("rectangle", None, None),          # sharp box
    "terminator":         ("rectangle", {"type": 3}, None),   # rounded ends
    "decision":           ("diamond", None, None),
    "connector":          ("ellipse", None, None),            # on-page connector
    "predefined_process": ("rectangle", None, "predefined"),  # two side bars
}

# The two true polygons have no native primitive: they are drawn as a closed line
# with a free label, and registered by their bounding box.
_POLYGON = {"data", "preparation"}

BODY_FONT = Font(16, None, "center")

# The second tier of a node's text: the file, port or command under its name, set in
# the code typeface and smaller, so the name stays the thing the eye reads first.
SUBLABEL_SIZE = 12
_TIER_GAP = 4


class ShapesMixin(object):  # implements: REQ-EXCALIDRAW-844
    """Labelled shapes. Every method returns the node id arrows attach to."""

    def box(self, text, at, *, paint=None, font=None, shape="rectangle",
            container=False, sublabel=None):
        """A shape carrying centred bound text.

        at:    (x, y) — sized by the shape's default — or (x, y, w, h), or a Rect.
        paint: a Paint, or a fill colour / role name.
        font:  a Font, or a size. With no colour given, the label is black, or
               white on a fill too dark for black to reach 4.5:1 contrast.
        shape: rectangle, ellipse, diamond, or an ISO 5807 name.
        container=True marks a visual wrapper meant to hold other shapes; it is
        exempt from the save-time overlap check, as frames always are.
        sublabel: a technical second line (a file, a port, a command) set under
               the name in the code typeface at 12px. It is free text grouped
               with the shape, and the overflow gate checks that both tiers fit.
        """
        if shape not in _NATIVE and shape not in _POLYGON:
            raise ValueError(f"unknown shape: {shape!r}")
        rect = as_rect(at, SIZES[shape])
        paint = Paint.coerce(paint)
        font = Font.coerce(font, BODY_FONT)
        stroke = resolve(paint.stroke, STROKE, STROKE["black"])
        fill = resolve(self._colour_of(paint.fill), FILL, "transparent")
        ts = TextStyle(font.size, resolve(font.color, STROKE, ink_on(fill)))
        label = (text or "").split("\n")[0] or shape
        group = paint.group
        if sublabel and not group:          # the tiers move with the shape as one
            group = "node-%d-%08x" % (self._n + 1, self._rand())
        style = Style(stroke, fill, group=group)
        tiers = self._tiers(text, sublabel, rect, ts) if sublabel else None
        if shape in _POLYGON:
            nid = self._polygon(shape, text, rect, style, ts, tiers)
        else:
            nid = self._native(shape, text, rect, style, ts, tiers)
        if tiers:
            self._sublabel(nid, sublabel, tiers[1], ts, group)
        self._register(nid, rect, self._geom_shape(shape), label=label, container=container)
        return nid

    @staticmethod
    def _tiers(text, sublabel, rect, ts):
        """(name rect, sublabel rect): the two tiers stacked and centred as one
        block in `rect`, the name on top."""
        nw, nh = text_extent(text, ts.size) if text else (0.0, 0.0)
        sw, sh = text_extent(sublabel, SUBLABEL_SIZE)
        top = rect.y + (rect.h - (nh + _TIER_GAP + sh)) / 2
        return (Rect(rect.cx - nw / 2, top, nw, nh),
                Rect(rect.cx - sw / 2, top + nh + _TIER_GAP, sw, sh))

    def _sublabel(self, nid, sublabel, rect, ts, group):
        """Draw the code-typeface second tier and record it for the overflow gate."""
        # implements: REQ-EXCALIDRAW-862
        el = self._text_el(sublabel, rect, TextStyle(SUBLABEL_SIZE, ts.color, "center", "top"),
                           group=group, family=TYPEFACES["code"])
        self.elements.append(el)
        node = self._element(nid)
        name = next((b["id"] for b in node["boundElements"] if b.get("type") == "text"),
                    None) if node else None
        self._sublabels[el["id"]] = (nid, name)

    @staticmethod
    def _geom_shape(shape):
        """The outline arrows clip against: a polygon is treated as its box."""
        return "rectangle" if shape in _POLYGON else _NATIVE[shape][0]

    def _native(self, shape, text, rect, style, ts, tiers=None):
        """Draw a shape on a native primitive, with its label bound inside it.
        With `tiers`, the label sits in the upper tier, aligned to the top, so an
        editor that re-lays it keeps it clear of the sublabel below."""
        etype, roundness, deco = _NATIVE[shape]
        style.roundness = roundness
        cid = self._new_id(etype)
        cont = self._base(cid, etype, rect, style)
        self.elements.append(cont)
        if text:
            tw, th = text_extent(text, ts.size)
            at = rect.centred(tw, th)
            if tiers:
                at, ts = tiers[0], TextStyle(ts.size, ts.color, ts.align, "top")
            tel = self._text_el(text, at, ts, container=cid, group=style.group)
            cont["boundElements"].append({"type": "text", "id": tel["id"]})
            self.elements.append(tel)
        if deco == "predefined":
            bar = min(12.0, rect.w * 0.12)
            for bx in (rect.x + bar, rect.right - bar):
                self.elements.append(self._vline(bx, rect, style))
        return cid

    def _vline(self, x, rect, style):
        """A bare vertical line spanning `rect`'s height (decoration, not a node)."""
        el = self._base(self._new_id("line"), "line", as_rect((x, rect.y, 0.0, rect.h)),
                        Style(style.stroke, group=style.group))
        el.update({"points": [[0.0, 0.0], [0.0, float(rect.h)]],
                   "lastCommittedPoint": None,
                   "startBinding": None, "endBinding": None,
                   "startArrowhead": None, "endArrowhead": None})
        return el

    def _polygon(self, shape, text, rect, style, ts, tiers=None):
        """Draw an ISO 5807 polygon (parallelogram/hexagon) as a closed line
        with a free centred label."""
        w, h = rect.w, rect.h
        if shape == "data":            # parallelogram — input / output
            sk = min(w * 0.18, 26.0)
            pts = [(sk, 0), (w, 0), (w - sk, h), (0, h), (sk, 0)]
        else:                          # hexagon — preparation / initialisation
            ins = min(w * 0.18, h * 0.5, 30.0)
            pts = [(0, h / 2), (ins, 0), (w - ins, 0), (w, h / 2),
                   (w - ins, h), (ins, h), (0, h / 2)]
        pid = self._new_id(shape)
        el = self._base(pid, "line", rect, style)
        el.update({"points": [[float(px), float(py)] for px, py in pts],
                   "lastCommittedPoint": None,
                   "startBinding": None, "endBinding": None,
                   "startArrowhead": None, "endArrowhead": None,
                   "polygon": True})
        self.elements.append(el)
        if text:
            tw, th = text_extent(text, ts.size)
            at = tiers[0] if tiers else rect.centred(tw, th)
            self.elements.append(self._text_el(text, at, ts, group=style.group))
        return pid

    # -- the named shapes: box() with a shape and its default size ---------
    def ellipse(self, text, at, **kw):
        """A labelled ellipse."""
        return self.box(text, at, shape="ellipse", **kw)

    def diamond(self, text, at, **kw):
        """A labelled diamond."""
        return self.box(text, at, shape="diamond", **kw)

    def process(self, text, at, **kw):
        """ISO 5807 process: a sharp rectangle."""
        return self.box(text, at, shape="process", **kw)

    def terminator(self, text, at, **kw):
        """ISO 5807 terminator: a rounded start / end."""
        return self.box(text, at, shape="terminator", **kw)

    def decision(self, text, at, **kw):
        """ISO 5807 decision: a diamond."""
        return self.box(text, at, shape="decision", **kw)

    def data(self, text, at, **kw):
        """ISO 5807 data: a parallelogram for input / output."""
        return self.box(text, at, shape="data", **kw)

    def predefined_process(self, text, at, **kw):
        """ISO 5807 predefined process: a rectangle with two side bars."""
        return self.box(text, at, shape="predefined_process", **kw)

    def preparation(self, text, at, **kw):
        """ISO 5807 preparation: a hexagon for initialisation."""
        return self.box(text, at, shape="preparation", **kw)

    def connector(self, text, at, **kw):
        """ISO 5807 on-page connector: a small circle."""
        return self.box(text, at, shape="connector", **kw)

    # -- the container drawn behind a group --------------------------------
    def frame(self, at, *, paint=None):
        """A large rounded rectangle used as a visual container, inserted at the
        back of the z-order so child shapes sit on top. `at` is (x, y, w, h);
        `paint.dashed` gives it a dashed outline. Overlap-exempt."""
        rect = as_rect(at)
        paint = Paint.coerce(paint)
        style = Style(resolve(paint.stroke, STROKE, STROKE["black"]),
                      resolve(self._colour_of(paint.fill), FILL, "transparent"),
                      stroke_style="dashed" if paint.dashed else "solid",
                      roundness={"type": 3}, group=paint.group)
        fid = self._new_id("frame")
        self.elements.insert(0, self._base(fid, "rectangle", rect, style))
        self._register(fid, rect, "rectangle", label="frame", container=True)
        return fid
