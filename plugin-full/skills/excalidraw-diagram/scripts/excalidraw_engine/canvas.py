"""The state every part of a Scene shares, and the only code that touches it raw.

`Canvas` owns the element list, the geometry registry arrows and checks read, the
overlap bookkeeping and the random source. The mixins in the sibling modules build
on this surface and nothing else, which is what lets each of them be read — and
tested — against a bare Canvas.
"""

import random
import time

from .geometry import Rect
from .style import TYPEFACES, Style


class Canvas(object):
    """A drawing surface that accumulates elements and serialises them."""

    def __init__(self, *, typeface="normal", sketch=False, background="#ffffff",
                 seed=None, roles=None):
        # implements: REQ-EXCALIDRAW-845
        """typeface: "normal" (Helvetica), "hand" (Excalifont) or "code".
        sketch: True draws rough hand-drawn outlines, False clean lines.
        seed: an int makes output byte-stable, so a committed diagram re-saves to
              an identical file. None uses time and randomness.
        roles: an optional {role_name: palette_colour} map, so a shape can be
              painted by meaning (paint="agent") and legend() can render the key.
        """
        if typeface not in TYPEFACES:
            raise ValueError("typeface must be one of %s" % ", ".join(sorted(TYPEFACES)))
        self.elements = []
        self.background = background
        self.roles = dict(roles or {})   # semantic role -> palette colour
        # resolved hex fills declared by legend() — the colour-SSOT key. Empty
        # until a legend is rendered, which is when coverage is enforced.
        self._legend_colours = set()
        self.typeface = TYPEFACES[typeface]
        self.roughness = 1 if sketch else 0
        self._n = 0
        self._geom = {}           # id -> (x, y, w, h, shape): what arrows attach to
        self._nodes = []          # [(id, x, y, w, h, label)] overlap-checked at save()
        self._containers = set()  # frames + container=True shapes (overlap-exempt)
        # enclose() frame id -> (the ids it was drawn around, its caption's text id
        # or None): what lets the checks tell a member from a box that strayed in
        self._frames = {}
        # abs (min_x, min_y, max_x, max_y) of each routed connector — so bounds()
        # accounts for paths that dip outside the shapes' boxes
        self._path_extents = []
        self._rng = random.Random(seed) if seed is not None else random
        self._fixed_time = 1_700_000_000_000 if seed is not None else None
        self._saved = False

    # -- id / randomness ---------------------------------------------------
    def _rand(self):
        return self._rng.randint(1, 2_000_000_000)

    def _now(self):
        if self._fixed_time is not None:
            return self._fixed_time
        return int(time.time() * 1000)

    def _new_id(self, prefix):
        self._n += 1
        return f"{prefix}-{self._n}-{self._rand():08x}"

    # -- element factories -------------------------------------------------
    def _base(self, eid, etype, rect, style):
        """The element dict every shape starts from: identity, geometry (`rect`)
        and paint (`style`)."""
        return {
            "id": eid,
            "type": etype,
            "x": rect.x, "y": rect.y,
            "width": rect.w, "height": rect.h,
            "angle": 0,
            "strokeColor": style.stroke,
            "backgroundColor": style.fill,
            "fillStyle": "solid",
            "strokeWidth": 2,
            "strokeStyle": style.stroke_style,
            "roughness": self.roughness,
            "opacity": 100,
            "groupIds": style.groups,
            "frameId": None,
            "roundness": style.roundness,
            "seed": self._rand(),
            "version": 1,
            "versionNonce": self._rand(),
            "isDeleted": False,
            "boundElements": [],
            "updated": self._now(),
            "link": None,
            "locked": False,
        }

    def _text_el(self, text, rect, ts, *, container=None, group=None):
        """A text element filling `rect`, painted per the TextStyle `ts`."""
        eid = self._new_id("text")
        el = self._base(eid, "text", rect, Style(ts.color, group=group))
        el.update({
            "text": text,
            "fontSize": ts.size,
            "fontFamily": self.typeface,
            "textAlign": ts.align,
            "verticalAlign": ts.valign,
            "containerId": container,
            "originalText": text,
            "lineHeight": 1.25,
            "autoResize": True,
        })
        return el

    # -- the node registry -------------------------------------------------
    def _register(self, nid, rect, shape, *, label, container=False):
        """Record a placed shape: arrows attach to it by its geometry, and unless
        it is a container the overlap check at save() judges it."""
        self._geom[nid] = (rect.x, rect.y, rect.w, rect.h, shape)
        if container:
            self._containers.add(nid)
        else:
            self._nodes.append((nid, rect.x, rect.y, rect.w, rect.h, label))

    def rect(self, nid):
        """The Rect a placed node occupies — for positioning something relative
        to it without reaching into the registry."""
        x, y, w, h, _shape = self._geom[nid]
        return Rect(x, y, w, h)

    def _element(self, eid):
        """The element dict with this id, or None if it was never placed."""
        for el in self.elements:
            if el["id"] == eid:
                return el
        return None

    def _bound_texts(self, el):
        """The text elements bound to `el` — the labels that must travel with
        it whenever it moves."""
        ids = {be["id"] for be in el.get("boundElements", [])
               if be.get("type") == "text"}
        return [t for t in self.elements if t["id"] in ids]

    def _move_node(self, nid, new_x, new_y):
        """Move a placed node (and its bound label) to (new_x, new_y), keeping
        the registry in sync — so a later save() still validates the mutated
        layout and cannot silently reintroduce overlaps."""
        x, y, w, h, shape = self._geom[nid]
        dx, dy = new_x - x, new_y - y
        if dx == 0 and dy == 0:
            return
        el = self._element(nid)
        if el is not None:
            el["x"], el["y"] = float(new_x), float(new_y)
            for label in self._bound_texts(el):
                label["x"] += dx
                label["y"] += dy
        self._geom[nid] = (new_x, new_y, w, h, shape)
        self._nodes = [
            (i, new_x, new_y, aw, ah, lab) if i == nid
            else (i, ax, ay, aw, ah, lab)
            for (i, ax, ay, aw, ah, lab) in self._nodes
        ]

    def _segments(self):
        """[((x0, y0), (x1, y1)), ...]: every leg of every arrow and line drawn
        so far, in scene coordinates — what a caption must stay clear of."""
        legs = []
        for el in self.elements:
            if el.get("type") not in ("arrow", "line"):
                continue
            pts = el.get("points") or []
            abs_pts = [(el["x"] + px, el["y"] + py) for px, py in pts]
            legs += list(zip(abs_pts, abs_pts[1:]))
        return legs

    # -- extent and serialisation -----------------------------------------
    def bounds(self):
        """(min_x, min_y, max_x, max_y) over every shape AND every routed
        connector. Use it to start the next region below max_y — including the
        extents of feedback loops that dip beneath a row."""
        boxes = [(g[0], g[1], g[0] + g[2], g[1] + g[3]) for g in self._geom.values()]
        boxes += self._path_extents
        if not boxes:
            return (0, 0, 0, 0)
        return (min(b[0] for b in boxes), min(b[1] for b in boxes),
                max(b[2] for b in boxes), max(b[3] for b in boxes))

    def to_dict(self):
        """The scene as the JSON object an .excalidraw file holds."""
        return {
            "type": "excalidraw",
            "version": 2,
            "source": "excalidraw-diagram-skill",
            "elements": self.elements,
            "appState": {
                "gridSize": None,
                "viewBackgroundColor": self.background,
            },
            "files": {},
        }
