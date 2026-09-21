"""Shapes that carry a label: the native primitives, the ISO 5807 flowchart set
and the frame that sits behind a group of them."""

from .geometry import as_rect, text_extent
from .style import FILL, STROKE, Font, Paint, Style, TextStyle, resolve

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


class ShapesMixin(object):  # implements: REQ-EXCALIDRAW-844
    """Labelled shapes. Every method returns the node id arrows attach to."""

    def box(self, text, at, *, paint=None, font=None, shape="rectangle",
            container=False):
        """A shape carrying centred bound text.

        at:    (x, y) — sized by the shape's default — or (x, y, w, h), or a Rect.
        paint: a Paint, or a fill colour / role name.
        font:  a Font, or a size.
        shape: rectangle, ellipse, diamond, or an ISO 5807 name.
        container=True marks a visual wrapper meant to hold other shapes; it is
        exempt from the save-time overlap check, as frames always are.
        """
        if shape not in _NATIVE and shape not in _POLYGON:
            raise ValueError(f"unknown shape: {shape!r}")
        rect = as_rect(at, SIZES[shape])
        paint = Paint.coerce(paint)
        font = Font.coerce(font, BODY_FONT)
        stroke = resolve(paint.stroke, STROKE, STROKE["black"])
        fill = resolve(self.roles.get(paint.fill, paint.fill), FILL, "transparent")
        ts = TextStyle(font.size, resolve(font.color, STROKE, STROKE["black"]))
        label = (text or "").split("\n")[0] or shape
        if shape in _POLYGON:
            nid = self._polygon(shape, text, rect, Style(stroke, fill, group=paint.group), ts)
        else:
            nid = self._native(shape, text, rect, Style(stroke, fill, group=paint.group), ts)
        self._register(nid, rect, self._geom_shape(shape), label=label, container=container)
        return nid

    @staticmethod
    def _geom_shape(shape):
        """The outline arrows clip against: a polygon is treated as its box."""
        return "rectangle" if shape in _POLYGON else _NATIVE[shape][0]

    def _native(self, shape, text, rect, style, ts):
        """Draw a shape on a native primitive, with its label bound inside it."""
        etype, roundness, deco = _NATIVE[shape]
        style.roundness = roundness
        cid = self._new_id(etype)
        cont = self._base(cid, etype, rect, style)
        self.elements.append(cont)
        if text:
            tw, th = text_extent(text, ts.size)
            tel = self._text_el(text, rect.centred(tw, th), ts,
                                container=cid, group=style.group)
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

    def _polygon(self, shape, text, rect, style, ts):
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
            self.elements.append(
                self._text_el(text, rect.centred(tw, th), ts, group=style.group))
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
                      resolve(self.roles.get(paint.fill, paint.fill), FILL, "transparent"),
                      stroke_style="dashed" if paint.dashed else "solid",
                      roundness={"type": 3}, group=paint.group)
        fid = self._new_id("frame")
        self.elements.insert(0, self._base(fid, "rectangle", rect, style))
        self._register(fid, rect, "rectangle", label="frame", container=True)
        return fid
