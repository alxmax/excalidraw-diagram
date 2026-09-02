#!/usr/bin/env python3
# implements: ARCH-EXCALIDRAW-030
# implements: ARCH-EXCALIDRAW-031
# implements: ARCH-EXCALIDRAW-032
"""
excalidraw_builder.py — build valid .excalidraw scenes (and a self-contained
HTML viewer) from a small declarative API. Python standard library only.

Why this exists
---------------
The Excalidraw file format is a flat list of elements, each carrying a lot of
boilerplate (random seeds, version nonces, two-way arrow bindings, bound-text
back-references). Hand-writing that JSON is error-prone. This module hides the
boilerplate behind a handful of methods so the *diagram* is the only thing you
describe:

    from excalidraw_builder import Scene

    s = Scene()
    a = s.box("User prompt",     120,  40, fill="blue")
    b = s.box("Consilium skill", 120, 180, fill="indigo")
    s.arrow(a, b, label="activates")
    s.title("CONSILIUM", 120, -40, size=36)
    s.save("consilium")          # -> consilium.excalidraw + consilium.html

The .excalidraw file imports cleanly into excalidraw.com (drag & drop) and the
.html file renders the same scene in the browser via the official Excalidraw
component, read-only, with edit/export still available.

Public API (see method docstrings for detail)
    Scene(font="normal", sketch=False, hand_drawn=None, background="#ffffff",
          seed=None, roles=None)
    .box(text, x, y, w=160, h=70, *, fill=None, stroke=None, shape="rectangle",
         font_size=16, group=None, container=False)   -> node id
    .ellipse(text, x, y, w, h, ...)        -> node id   (shape="ellipse")
    .diamond(text, x, y, w, h, ...)        -> node id   (shape="diamond")
    .frame(x, y, w, h, *, fill=None, dashed=False, group=None) -> node id
    # ISO 5807 flowchart shapes (thin box() aliases):
    .process / .terminator / .decision / .data / .predefined_process
    / .preparation / .connector (text, x, y, ...)      -> node id
    .row / .column / .grid(items, x, y, ...)           -> [node id, ...]
    .enclose(ids, *, label=None) / .lane(ids, label)   -> frame id
    .section(title) -> y          # stack a labelled region below all content
    .pipeline(steps, x, y, *, gap=80, connect=True)    -> [node id, ...]
    .align(ids, axis) / .distribute(ids, axis, gap=40)
    .label(text, x, y, *, size=12, color=None, align="center")
    .title(text, x, y, *, size=28, color=None, align="left")
    .arrow(src, dst, *, label=None, dashed=False, color=None,
           start=None, end="arrow", curve=False, gap=14) -> arrow id
    .free_arrow((x1,y1),(x2,y2), ...)       -> arrow id  (unbound)
    .path(points, *, label=None, ...)       -> arrow id  (multi-point connector)
    .route_under(src, dst, *, drop=70, label=None)      -> arrow id  (feedback)
    .role(name, colour) / .legend(entries, x, y) / .glossary(entries, x, y)
    .check_overlaps() / .check_arrow_crossings()
    .check_legend_coverage() / .check_text_overflow() / .check_text_overlaps()
    .bounds() -> (min_x, min_y, max_x, max_y)
    .save(basename, out_dir=".", *, allow_overlap=False, crossing_check="warn",
          legend_check="warn", overflow_check="warn", text_overlap_check="warn")
                                            -> (path_excalidraw, path_html)

Colours accept either a hex string ("#a5d8ff") or a palette name:
    grey, red, orange, yellow, green, teal, blue, indigo, violet, pink.
"""

import json
import math
import os
import random
import sys
import time

# ---------------------------------------------------------------------------
# Palette — Excalidraw's own swatches (stroke = strong, fill = light tint)
# ---------------------------------------------------------------------------
_STROKE = {
    "grey":   "#343a40", "red":  "#e03131", "orange": "#e8590c",
    "yellow": "#f08c00", "green": "#2f9e44", "teal":   "#0c8599",
    "blue":   "#1971c2", "indigo": "#3b5bdb", "violet": "#6741d9",
    "pink":   "#c2255c", "black": "#1e1e1e",
}
_FILL = {
    "grey":   "#e9ecef", "red":  "#ffc9c9", "orange": "#ffd8a8",
    "yellow": "#ffec99", "green": "#b2f2bb", "teal":   "#99e9f2",
    "blue":   "#a5d8ff", "indigo": "#bac8ff", "violet": "#d0bfff",
    "pink":   "#fcc2d7", "transparent": "transparent",
}

# Excalidraw fontFamily codes: 1 = hand-drawn (Excalifont/Virgil),
# 2 = normal (Helvetica), 3 = code (Cascadia).
_FONT_HAND = 1
_FONT_NORMAL = 2


def _hex(color, table, default):
    if color is None:
        return default
    if isinstance(color, str) and color.startswith("#"):
        return color
    if color == "transparent":
        return "transparent"
    return table.get(color, default)


class Scene:
    """A drawing surface that accumulates elements and serialises them."""

    def __init__(self, hand_drawn=None, font="normal", sketch=False,
                 background="#ffffff", seed=None, roles=None):
        """A drawing surface.

        font  : "normal" (Helvetica), "hand" (Excalifont), or "code".
        sketch: True = rough/hand-drawn shape outlines, False = clean lines.
        hand_drawn: back-compat alias — True sets font="hand", sketch=True.
        seed: pass an int for byte-stable output (the same scene re-saves to an
              identical file — useful when the diagram is committed to git).
              Default None uses time + randomness, so every run differs.
        roles: an optional {role_name: palette_colour} map so boxes can be
              filled by meaning (fill="agent") and legend() can render the key
              automatically. Also settable per-role with .role(name, colour).
        """
        if hand_drawn is not None:
            font = "hand" if hand_drawn else "normal"
            sketch = bool(hand_drawn)
        self.elements = []
        self.background = background
        self.roles = dict(roles or {})   # semantic role -> palette colour
        # resolved hex fills declared by legend() — the colour-SSOT key. Empty
        # until a legend is rendered, which is when coverage is enforced.
        self._legend_colours = set()
        self.font = {"hand": _FONT_HAND, "normal": _FONT_NORMAL,
                     "code": 3}.get(font, _FONT_NORMAL)
        self.roughness = 1 if sketch else 0
        self._n = 0
        # registry of geometry so arrows can compute endpoints
        self._geom = {}  # id -> (x, y, w, h, shape)
        # overlap bookkeeping: normal nodes are collision-checked at save()
        self._nodes = []          # [(id, x, y, w, h, label)] to check
        self._containers = set()  # frames + container=True shapes (exempt)
        # abs (min_x, min_y, max_x, max_y) of each routed connector — so bounds()
        # accounts for paths/route_under that dip outside the shapes' boxes
        self._path_extents = []
        # randomness source — fixed when a seed is given (reproducible files)
        self._rng = random.Random(seed) if seed is not None else random
        self._fixed_time = 1_700_000_000_000 if seed is not None else None

    # -- id / randomness helpers -------------------------------------------
    def _rand(self):
        return self._rng.randint(1, 2_000_000_000)

    def _now(self):
        if self._fixed_time is not None:
            return self._fixed_time
        return int(time.time() * 1000)

    def _new_id(self, prefix):
        self._n += 1
        return f"{prefix}-{self._n}-{self._rand():08x}"

    # -- base element ------------------------------------------------------
    def _base(self, eid, etype, x, y, w, h, stroke, fill, *,
              fill_style="solid", stroke_width=2, stroke_style="solid",
              roundness=None, group=None):
        groups = [group] if group else []
        return {
            "id": eid,
            "type": etype,
            "x": float(x), "y": float(y),
            "width": float(w), "height": float(h),
            "angle": 0,
            "strokeColor": stroke,
            "backgroundColor": fill,
            "fillStyle": fill_style,
            "strokeWidth": stroke_width,
            "strokeStyle": stroke_style,
            "roughness": self.roughness,
            "opacity": 100,
            "groupIds": groups,
            "frameId": None,
            "roundness": roundness,
            "seed": self._rand(),
            "version": 1,
            "versionNonce": self._rand(),
            "isDeleted": False,
            "boundElements": [],
            "updated": self._now(),
            "link": None,
            "locked": False,
        }

    def _text_el(self, text, x, y, w, h, *, size, color, container=None,
                 align="center", valign="middle", group=None):
        eid = self._new_id("text")
        line_h = 1.25
        el = self._base(eid, "text", x, y, w, h, color, "transparent",
                        roundness=None, group=group)
        el.update({
            "text": text,
            "fontSize": size,
            "fontFamily": self.font,
            "textAlign": align,
            "verticalAlign": valign,
            "containerId": container,
            "originalText": text,
            "lineHeight": line_h,
            "autoResize": True,
        })
        return el

    # -- text-sizing heuristics -------------------------------------------
    @staticmethod
    def _text_wh(text, size):
        lines = text.split("\n")
        longest = max((len(ln) for ln in lines), default=1)
        w = max(longest * size * 0.58, 8)
        h = len(lines) * size * 1.25
        return w, h

    @staticmethod
    def fit_text(text, *, font=14, max_chars=20, min_w=120, min_h=48):
        """Word-wrap `text` to <=max_chars per line and return (wrapped, w, h)
        sized so the text never overflows its box. Use it for boxes whose label
        length is not known in advance (extracted/generated names): call it and
        pass the returned w/h to box()/pipeline(). The engine does NOT auto-size
        box() by default — changing that default would re-flow every existing
        layout — so sizing-to-text is this opt-in helper. The width margin is
        wider than _text_wh's factor, so a box sized here always clears
        check_text_overflow()."""
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
        width = max(min_w, int(longest * font * 0.6) + 24)
        height = max(min_h, int(len(lines) * font * 1.6) + 18)
        return "\n".join(lines), width, height

    # ====================================================================
    #  SHAPES WITH A CENTERED LABEL
    # ====================================================================
    def box(self, text, x, y, w=160, h=70, *, fill=None, stroke=None,
            shape="rectangle", font_size=16, font_color=None, group=None,
            container=False):
        """A rectangle / ellipse / diamond carrying centered bound text.

        Returns the node id (use it in .arrow()).

        container=True marks this shape as a visual wrapper meant to hold other
        shapes (e.g. an ellipse drawn around inner boxes, or a backing panel).
        Containers are exempt from the save-time overlap check; frames always
        are.
        """
        sc = _hex(stroke, _STROKE, _STROKE["black"])
        bg = _hex(self.roles.get(fill, fill), _FILL, "transparent")  # role -> colour

        # ISO 5807 polygon symbols (data=parallelogram, preparation=hexagon) have
        # no native Excalidraw primitive — drawn as a closed line + free label,
        # with their bounding box registered for arrows/overlap.
        if shape in self._ISO_POLYGON:
            return self._iso_polygon(shape, text, x, y, w, h, sc, bg,
                                     font_size, font_color, group, container)

        etype, roundness, deco = self._resolve_native(shape)
        cid = self._new_id(etype)
        cont = self._base(cid, etype, x, y, w, h, sc, bg,
                          roundness=roundness, group=group)

        if text:
            tcolor = _hex(font_color, _STROKE, _STROKE["black"])
            tw, th = self._text_wh(text, font_size)
            tx = x + (w - tw) / 2
            ty = y + (h - th) / 2
            tel = self._text_el(text, tx, ty, tw, th, size=font_size,
                                color=tcolor, container=cid, group=group)
            cont["boundElements"].append({"type": "text", "id": tel["id"]})
            self.elements.append(cont)
            self.elements.append(tel)
        else:
            self.elements.append(cont)

        self._geom[cid] = (x, y, w, h, etype)
        if container:
            self._containers.add(cid)
        else:
            self._nodes.append((cid, x, y, w, h,
                                (text or "").split("\n")[0] or shape))
        # ISO 5807 predefined-process: two vertical bars inset from the sides
        if deco == "predefined":
            bar = min(12.0, w * 0.12)
            for bx in (x + bar, x + w - bar):
                self.elements.append(self._vline(bx, y, h, sc, group))
        return cid

    def ellipse(self, text, x, y, w=170, h=110, **kw):
        return self.box(text, x, y, w, h, shape="ellipse", **kw)

    def diamond(self, text, x, y, w=160, h=90, **kw):
        return self.box(text, x, y, w, h, shape="diamond", **kw)

    # ====================================================================
    #  ISO 5807 FLOWCHART SHAPES (process/decision/terminator/data/...)
    # ====================================================================
    # The two true polygons have no native Excalidraw primitive; the rest map
    # onto native shapes (sharp vs rounded rectangle, diamond, circle).
    _ISO_POLYGON = {"data", "preparation"}

    @staticmethod
    def _resolve_native(shape):
        """Map a shape name to (excalidraw_type, roundness, decoration).

        ISO 5807 names render on native primitives:
        process -> sharp rectangle, terminator -> rounded rectangle (start/end),
        decision -> diamond, connector -> circle, predefined_process -> rectangle
        with two side bars. Unknown names raise."""
        iso = {
            "process":            ("rectangle", None, None),         # sharp box
            "terminator":         ("rectangle", {"type": 3}, None),  # rounded ends
            "decision":           ("diamond", None, None),
            "connector":          ("ellipse", None, None),           # on-page conn.
            "predefined_process": ("rectangle", None, "predefined"),
        }
        if shape in iso:
            return iso[shape]
        if shape in ("rectangle", "ellipse", "diamond"):
            return (shape, {"type": 3} if shape == "rectangle" else None, None)
        raise ValueError(f"unknown shape: {shape!r}")

    def _vline(self, x, y, h, sc, group=None):
        """A bare vertical line element (decoration, not a tracked node)."""
        el = self._base(self._new_id("line"), "line", x, y, 0.0, float(h),
                        sc, "transparent", roundness=None, group=group)
        el.update({"points": [[0.0, 0.0], [0.0, float(h)]],
                   "lastCommittedPoint": None,
                   "startBinding": None, "endBinding": None,
                   "startArrowhead": None, "endArrowhead": None})
        return el

    def _iso_polygon(self, shape, text, x, y, w, h, sc, bg,
                     font_size, font_color, group, container):
        """Draw an ISO 5807 polygon (parallelogram/hexagon) as a closed line
        with a free centered label; register the bounding box as the node."""
        if shape == "data":            # parallelogram — input / output
            sk = min(w * 0.18, 26.0)
            pts = [(sk, 0), (w, 0), (w - sk, h), (0, h), (sk, 0)]
        elif shape == "preparation":   # hexagon — setup / initialisation
            ins = min(w * 0.18, h * 0.5, 30.0)
            pts = [(0, h / 2), (ins, 0), (w - ins, 0), (w, h / 2),
                   (w - ins, h), (ins, h), (0, h / 2)]
        else:
            raise ValueError(f"unknown ISO polygon shape: {shape!r}")
        pid = self._new_id(shape)
        el = self._base(pid, "line", x, y, w, h, sc, bg,
                        roundness=None, group=group)
        el.update({"points": [[float(px), float(py)] for px, py in pts],
                   "lastCommittedPoint": None,
                   "startBinding": None, "endBinding": None,
                   "startArrowhead": None, "endArrowhead": None,
                   "polygon": True})
        self.elements.append(el)
        if text:
            tcolor = _hex(font_color, _STROKE, _STROKE["black"])
            tw, th = self._text_wh(text, font_size)
            self.elements.append(
                self._text_el(text, x + (w - tw) / 2, y + (h - th) / 2, tw, th,
                              size=font_size, color=tcolor, group=group))
        self._geom[pid] = (x, y, w, h, "rectangle")   # bbox for arrows/overlap
        if container:
            self._containers.add(pid)
        else:
            self._nodes.append((pid, x, y, w, h,
                                (text or "").split("\n")[0] or shape))
        return pid

    # -- ISO 5807 convenience aliases (readable generators) ----------------
    def process(self, text, x, y, w=170, h=64, **kw):
        return self.box(text, x, y, w, h, shape="process", **kw)

    def terminator(self, text, x, y, w=170, h=54, **kw):
        return self.box(text, x, y, w, h, shape="terminator", **kw)

    def decision(self, text, x, y, w=180, h=100, **kw):
        return self.box(text, x, y, w, h, shape="decision", **kw)

    def data(self, text, x, y, w=190, h=66, **kw):
        return self.box(text, x, y, w, h, shape="data", **kw)

    def predefined_process(self, text, x, y, w=185, h=66, **kw):
        return self.box(text, x, y, w, h, shape="predefined_process", **kw)

    def preparation(self, text, x, y, w=200, h=82, **kw):
        return self.box(text, x, y, w, h, shape="preparation", **kw)

    def connector(self, text, x, y, w=46, h=46, **kw):
        return self.box(text, x, y, w, h, shape="connector", **kw)

    # ====================================================================
    #  POSTER HELPERS (stacked sections + a horizontal workflow pipeline)
    # ====================================================================
    def section(self, title, *, x=40, gap=70, size=18, color="black"):
        """Open a stacked section: place a left-aligned heading below ALL existing
        content (shapes, connectors, and text) and return the y at which to place
        this section's shapes. Removes the manual y-band bookkeeping when stacking
        regions top -> bottom."""
        bottom = max((e.get("y", 0) + e.get("height", 0) for e in self.elements),
                     default=0)
        top = bottom + gap
        self.label(title, x, top, size=size, color=color, align="left")
        return top + size * 1.6 + 10

    _PIPE_WH = {
        "terminator": (120, 48), "process": (150, 64), "decision": (180, 92),
        "data": (170, 64), "predefined_process": (180, 64),
        "preparation": (190, 78), "connector": (46, 46), "box": (160, 70),
    }

    def pipeline(self, steps, x, y, *, gap=80, row_h=None, font_size=14,
                 connect=True):
        """Lay out a horizontal flowchart pipeline left -> right and (by default)
        chain bound arrows between consecutive steps. Steps are vertically centred
        on a common midline so terminators/processes/decisions align.

        Each step is a string, a (text, kind) or (text, kind, fill) tuple, or a
        dict of {text, kind, fill, w, h, label, font_size}. `kind` is any ISO/C4
        shape verb: process (default), decision, terminator, data,
        predefined_process, preparation, connector, box. A step's `label` becomes
        the arrow label leaving it. Returns the list of node ids (index them for
        route_under() feedback loops)."""
        method = {
            "terminator": self.terminator, "process": self.process,
            "decision": self.diamond, "data": self.data,
            "predefined_process": self.predefined_process,
            "preparation": self.preparation, "connector": self.connector,
            "box": self.box,
        }
        norm = []
        for st in steps:
            if isinstance(st, str):
                d = {"text": st}
            elif isinstance(st, (tuple, list)):
                d = {"text": st[0]}
                if len(st) > 1:
                    d["kind"] = st[1]
                if len(st) > 2:
                    d["fill"] = st[2]
            else:
                d = dict(st)
            d.setdefault("kind", "process")
            dw, dh = self._PIPE_WH.get(d["kind"], (150, 64))
            d.setdefault("w", dw)
            d.setdefault("h", dh)
            norm.append(d)
        if not norm:
            return []          # empty steps -> no nodes (consistent with row/column/grid)
        if connect and gap < 80 and any(d.get("label") for d in norm):
            print(
                f"excalidraw_builder: pipeline gap={gap}px with labeled arrows —"
                f" labels may overlap (recommended: ≥80px; ≥100px for"
                f" multi-word labels)",
                file=sys.stderr,
            )
        band = row_h or max(d["h"] for d in norm)
        mid = y + band / 2
        cx = x
        for d in norm:
            fn = method.get(d["kind"], self.process)
            d["_id"] = fn(d["text"], cx, mid - d["h"] / 2, w=d["w"], h=d["h"],
                          fill=d.get("fill"), font_size=d.get("font_size", font_size))
            cx += d["w"] + gap
        if connect:
            for a, b in zip(norm, norm[1:]):
                self.arrow(a["_id"], b["_id"], label=a.get("label"))
        return [d["_id"] for d in norm]

    # ====================================================================
    #  FRAME / GROUPING CONTAINER (a big rounded rectangle, drawn behind)
    # ====================================================================
    def frame(self, x, y, w, h, *, fill=None, stroke=None, dashed=False,
              group=None):
        """A large rounded rectangle used as a visual container.

        Inserted at the *back* of the z-order so child shapes sit on top.
        """
        sc = _hex(stroke, _STROKE, _STROKE["black"])
        bg = _hex(fill, _FILL, "transparent")
        fid = self._new_id("frame")
        el = self._base(fid, "rectangle", x, y, w, h, sc, bg,
                        stroke_style="dashed" if dashed else "solid",
                        roundness={"type": 3}, group=group)
        self.elements.insert(0, el)          # behind everything so far
        self._geom[fid] = (x, y, w, h, "rectangle")
        self._containers.add(fid)            # frames hold children — never flag
        return fid

    # ====================================================================
    #  AUTO-LAYOUT  (place several nodes without hand-computing coordinates)
    # ====================================================================
    @staticmethod
    def _norm(items):
        """Normalise row/grid items to dicts. An item may be a plain string
        (text), a (text, fill) pair, or a full dict of box() options."""
        out = []
        for it in items:
            if isinstance(it, dict):
                out.append(dict(it))
            elif isinstance(it, (tuple, list)):
                d = {"text": it[0]}
                if len(it) > 1:
                    d["fill"] = it[1]
                out.append(d)
            else:
                out.append({"text": str(it)})
        return out

    def _place(self, it, x, y, w, h, fill, font_size, shape):
        return self.box(it.get("text", ""), x, y,
                        it.get("w", w), it.get("h", h),
                        fill=it.get("fill", fill), stroke=it.get("stroke"),
                        shape=it.get("shape", shape),
                        font_size=it.get("font_size", font_size),
                        container=it.get("container", False))

    def row(self, items, x, y, *, w=160, h=70, gap=80, fill=None,
            font_size=16, shape="rectangle", connect=False):
        """Place items left→right starting at (x, y); return their ids.
        connect=True chains them with arrows (a quick pipeline).
        Recommended gap: ≥80px when connect=True so arrows are visible."""
        if connect and gap < 80:
            print(
                f"excalidraw_builder: row gap={gap}px with connect=True —"
                f" arrows may be invisible (recommended: ≥80px)",
                file=sys.stderr,
            )
        ids, cx = [], x
        for it in self._norm(items):
            ids.append(self._place(it, cx, y, w, h, fill, font_size, shape))
            cx += it.get("w", w) + gap
        if connect:
            for a, b in zip(ids, ids[1:]):
                self.arrow(a, b)
        return ids

    def column(self, items, x, y, *, w=160, h=70, gap=60, fill=None,
               font_size=16, shape="rectangle", connect=False):
        """Place items top→down starting at (x, y); return their ids."""
        ids, cy = [], y
        for it in self._norm(items):
            ids.append(self._place(it, x, cy, w, h, fill, font_size, shape))
            cy += it.get("h", h) + gap
        if connect:
            for a, b in zip(ids, ids[1:]):
                self.arrow(a, b)
        return ids

    def grid(self, items, x, y, cols, *, w=160, h=70, gap_x=40, gap_y=30,
             fill=None, font_size=16, shape="rectangle"):
        """Place items in a `cols`-wide grid (row-major); return their ids.
        Cell size is uniform so columns and rows stay aligned."""
        ids = []
        for i, it in enumerate(self._norm(items)):
            r, c = divmod(i, cols)
            ids.append(self.box(it.get("text", ""),
                                x + c * (w + gap_x), y + r * (h + gap_y), w, h,
                                fill=it.get("fill", fill),
                                stroke=it.get("stroke"),
                                shape=it.get("shape", shape),
                                font_size=it.get("font_size", font_size)))
        return ids

    def enclose(self, ids, *, pad=24, dashed=True, fill=None, stroke=None,
                label=None, label_size=13, label_color="grey"):
        """Draw a frame auto-sized around the given node ids (call it AFTER
        placing them, so it sits behind). Optional centered caption above.
        Returns the frame id."""
        if not ids:
            raise ValueError("enclose() needs at least one node id")
        x0 = min(self._geom[i][0] for i in ids)
        y0 = min(self._geom[i][1] for i in ids)
        x1 = max(self._geom[i][0] + self._geom[i][2] for i in ids)
        y1 = max(self._geom[i][1] + self._geom[i][3] for i in ids)
        fx, fy = x0 - pad, y0 - pad
        fw, fh = (x1 - x0) + 2 * pad, (y1 - y0) + 2 * pad
        fid = self.frame(fx, fy, fw, fh, fill=fill, stroke=stroke, dashed=dashed)
        if label:
            self.label(label, fx + fw / 2, fy - 22, size=label_size,
                       color=label_color, align="center")
        return fid

    # ====================================================================
    #  LEGEND & SWIMLANE  (make colour meaning and grouping explicit)
    # ====================================================================
    def role(self, name, color):
        """Declare a semantic role -> palette-colour alias, usable as a fill
        (role('agent','violet') then box(fill='agent')) and as the source for
        legend()."""
        self.roles[name] = color
        return self

    def legend(self, entries=None, x=0, y=0, *, title="Legend",
               swatch=18, gap=10, font_size=13, pad=14):
        """A colour key mapping each fill to its meaning, so a reader with no
        context can decode the diagram. `entries` is a list of (label, colour);
        if omitted, the Scene's declared roles are used. Returns the frame id.

        Use this whenever colour encodes a role — a coloured diagram without a
        legend is not self-explanatory."""
        if entries is None:
            entries = list(self.roles.items())
        if not entries:
            raise ValueError("legend() needs entries or Scene(roles=...)")
        row_h = max(swatch, font_size * 1.25) + gap
        longest = max((len(str(lbl)) for lbl, _ in entries), default=1)
        title_h = (font_size + 1) * 1.5 if title else 0
        w = pad * 2 + swatch + 8 + int(longest * font_size * 0.62) + 6
        if title:
            w = max(w, pad * 2 + int(len(title) * (font_size + 1) * 0.62))
        h = pad * 2 + title_h + row_h * len(entries)
        fid = self.frame(x, y, w, h, fill="#ffffff")
        cy = y + pad
        if title:
            self.label(title, x + pad, cy, size=font_size + 1, color="black",
                       align="left")
            cy += title_h
        for lbl, col in entries:
            self.box("", x + pad, cy, swatch, swatch, fill=col, container=True)
            # record the resolved hex so check_legend_coverage() can assert that
            # every semantic fill in the scene is explained by this key
            self._legend_colours.add(
                _hex(self.roles.get(col, col), _FILL, "transparent"))
            self.label(str(lbl), x + pad + swatch + 8,
                       cy + (swatch - font_size) / 2, size=font_size,
                       color="black", align="left")
            cy += row_h
        return fid

    def glossary(self, entries, x, y, *, title="Glossary", font_size=13,
                 pad=14, gap=8):
        """A term→meaning key so a reader can decode jargon / acronyms on the
        canvas — distinct from legend() (which maps colour→role). `entries` is a
        list of (term, meaning); each renders as one left-aligned "TERM — meaning"
        line (no colour, no wrapping — keep each meaning to one short line). The
        box is overlap-checked like real content. Returns the frame id."""
        if not entries:
            raise ValueError("glossary() needs at least one (term, meaning)")
        rows = [f"{t} — {m}" for t, m in entries]
        row_h = font_size * 1.25 + gap
        title_h = (font_size + 1) * 1.5 if title else 0
        longest = max(len(r) for r in rows)
        w = pad * 2 + int(longest * font_size * 0.58)
        if title:
            w = max(w, pad * 2 + int(len(title) * (font_size + 1) * 0.62))
        h = pad * 2 + title_h + row_h * len(entries)
        fid = self.frame(x, y, w, h, fill="#ffffff")
        # overlap-checked content: frame() is container-exempt, so register the
        # box in _nodes explicitly (mirrors path()'s knock-out panel). Left out
        # of _geom so it is not treated as an arrow-crossing obstacle.
        self._nodes.append((fid + "-box", x, y, w, h, f'glossary "{title}"'))
        cy = y + pad
        if title:
            self.label(title, x + pad, cy, size=font_size + 1, color="black",
                       align="left")
            cy += title_h
        for r in rows:
            self.label(r, x + pad, cy, size=font_size, color="black",
                       align="left")
            cy += row_h
        return fid

    def lane(self, ids, label, *, pad=24, fill=None, stroke=None,
             font_size=14, label_color="black"):
        """Swimlane: a solid frame around `ids` with a prominent top-left
        header. Thin wrapper over enclose() — use to group a stage or actor."""
        fid = self.enclose(ids, pad=pad, dashed=False, fill=fill,
                           stroke=stroke, label=None)
        fx, fy, fw, fh, _ = self._geom[fid]
        self.label(label, fx + 12, fy + 8, size=font_size, color=label_color,
                   align="left")
        return fid

    # ====================================================================
    #  POST-PLACEMENT ADJUSTMENT  (align / distribute already-placed nodes)
    # ====================================================================
    def _move_node(self, nid, new_x, new_y):
        """Move a placed node (and its bound label) to (new_x, new_y), keeping
        _geom and the overlap-check bookkeeping in sync — so a later save() still
        validates the mutated layout and cannot silently reintroduce overlaps."""
        x, y, w, h, shape = self._geom[nid]
        dx, dy = new_x - x, new_y - y
        if dx == 0 and dy == 0:
            return
        for el in self.elements:
            if el["id"] == nid:
                el["x"] = float(new_x)
                el["y"] = float(new_y)
                for be in el.get("boundElements", []):
                    if be.get("type") == "text":
                        for t in self.elements:
                            if t["id"] == be["id"]:
                                t["x"] += dx
                                t["y"] += dy
                                break
                break
        self._geom[nid] = (new_x, new_y, w, h, shape)
        self._nodes = [
            (i, new_x, new_y, aw, ah, lab) if i == nid
            else (i, ax, ay, aw, ah, lab)
            for (i, ax, ay, aw, ah, lab) in self._nodes
        ]

    def align(self, ids, axis="center_x"):
        """Align already-placed nodes on a shared edge/axis:
        left|right|center_x|top|bottom|center_y. Mutates positions in place and
        keeps the overlap check honest. Returns ids."""
        g = {i: self._geom[i] for i in ids}
        if axis == "left":
            t = min(v[0] for v in g.values())
            for i in ids:
                self._move_node(i, t, g[i][1])
        elif axis == "right":
            t = max(v[0] + v[2] for v in g.values())
            for i in ids:
                self._move_node(i, t - g[i][2], g[i][1])
        elif axis == "center_x":
            c = sum(v[0] + v[2] / 2 for v in g.values()) / len(g)
            for i in ids:
                self._move_node(i, c - g[i][2] / 2, g[i][1])
        elif axis == "top":
            t = min(v[1] for v in g.values())
            for i in ids:
                self._move_node(i, g[i][0], t)
        elif axis == "bottom":
            t = max(v[1] + v[3] for v in g.values())
            for i in ids:
                self._move_node(i, g[i][0], t - g[i][3])
        elif axis == "center_y":
            c = sum(v[1] + v[3] / 2 for v in g.values()) / len(g)
            for i in ids:
                self._move_node(i, g[i][0], c - g[i][3] / 2)
        else:
            raise ValueError(f"align: unknown axis {axis!r}")
        return ids

    def distribute(self, ids, axis="x", *, gap=40):
        """Place nodes evenly along an axis ('x' or 'y'), in their current
        positional order, separated by `gap`. Mutates positions in place."""
        if axis not in ("x", "y"):
            raise ValueError("distribute: axis must be 'x' or 'y'")
        order = sorted(ids, key=lambda i: self._geom[i][0] if axis == "x"
                       else self._geom[i][1])
        cur = None
        for i in order:
            x, y, w, h, s = self._geom[i]
            if cur is None:
                cur = x if axis == "x" else y
            if axis == "x":
                self._move_node(i, cur, y)
                cur += w + gap
            else:
                self._move_node(i, x, cur)
                cur += h + gap
        return ids

    # ====================================================================
    #  FREE-STANDING TEXT (titles & small caption labels)
    # ====================================================================
    def title(self, text, x, y, *, size=28, color=None, align="left",
              group=None):
        c = _hex(color, _STROKE, _STROKE["black"])
        tw, th = self._text_wh(text, size)
        # Anchor semantics: for centered/right text the caller passes the
        # center/right point, so shift the element's left edge — Excalidraw only
        # aligns text *within* the element's own (tight) width, not around x.
        if align == "center":
            x = x - tw / 2
        elif align == "right":
            x = x - tw
        el = self._text_el(text, x, y, tw, th, size=size, color=c,
                           align=align, valign="top", group=group)
        self.elements.append(el)
        return el["id"]

    def label(self, text, x, y, *, size=12, color=None, align="center",
              group=None):
        """A small caption (e.g. the 'ONE AGENT' tags above the ellipses)."""
        return self.title(text, x, y, size=size, color=color or "grey",
                          align=align, group=group)

    # ====================================================================
    #  ARROWS
    # ====================================================================
    def _border_point(self, gid, toward):
        """Point on the border of element `gid` in the direction of `toward`
        (a global (x,y) point). Handles rectangles and ellipses."""
        x, y, w, h, shape = self._geom[gid]
        cx, cy = x + w / 2, y + h / 2
        dx, dy = toward[0] - cx, toward[1] - cy
        if dx == 0 and dy == 0:
            return cx, cy
        if shape == "ellipse":
            # parametric: scale the direction onto the ellipse boundary
            ang = math.atan2(dy, dx)
            return cx + (w / 2) * math.cos(ang), cy + (h / 2) * math.sin(ang)
        if shape == "diamond":
            # rhombus boundary: |X|/(w/2) + |Y|/(h/2) = 1 — meet the slanted edge
            t = 1.0 / (2 * abs(dx) / w + 2 * abs(dy) / h)
            return cx + dx * t, cy + dy * t
        # rectangle -> clip to the box border
        scale = 0.5 / max(abs(dx) / w, abs(dy) / h)
        return cx + dx * scale, cy + dy * scale

    def arrow(self, src, dst, *, label=None, dashed=False, color=None,
              start=None, end="arrow", curve=False, gap=14, group=None):
        """A bound arrow from node `src` to node `dst`.

        The arrow starts/ends a few pixels *outside* each shape's border. The
        gap is automatically clamped when the two shapes are close together, so
        the endpoints never cross over (which would flip the arrow's direction).
        Returns the arrow id.
        """
        sc = _hex(color, _STROKE, _STROKE["black"])
        sx, sy, sw, sh, _ = self._geom[src]
        dx_, dy_, dw, dh, _ = self._geom[dst]
        s_center = (sx + sw / 2, sy + sh / 2)
        d_center = (dx_ + dw / 2, dy_ + dh / 2)
        b0 = self._border_point(src, d_center)
        b1 = self._border_point(dst, s_center)
        dist = math.hypot(b1[0] - b0[0], b1[1] - b0[1]) or 1.0
        # clamp the per-side gap so the two endpoints keep ~10px between them
        g = min(gap, max(2.0, (dist - 10) / 2))
        ux, uy = (b1[0] - b0[0]) / dist, (b1[1] - b0[1]) / dist
        p0 = (b0[0] + ux * g, b0[1] + uy * g)   # just outside src, toward dst
        p1 = (b1[0] - ux * g, b1[1] - uy * g)   # just outside dst, toward src

        aid = self._new_id("arrow")
        ax, ay = p0
        pts = [[0.0, 0.0], [p1[0] - ax, p1[1] - ay]]
        if curve:
            midx = (pts[0][0] + pts[1][0]) / 2
            midy = (pts[0][1] + pts[1][1]) / 2
            pts = [pts[0], [midx, midy - 30], pts[1]]
        # bounding box must span ALL points (incl. a curve's control point), not
        # just the endpoint — otherwise the curved connector's selection/export
        # bounds understate its extent (matches path()'s bbox computation)
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        w = max(xs) - min(xs); h = max(ys) - min(ys)

        el = self._base(aid, "arrow", ax, ay, w, h, sc, "transparent",
                        roundness={"type": 2} if curve else None, group=group)
        el.update({
            "points": pts,
            "lastCommittedPoint": None,
            "startBinding": {"elementId": src, "focus": 0.0, "gap": g},
            "endBinding": {"elementId": dst, "focus": 0.0, "gap": g},
            "startArrowhead": start,
            "endArrowhead": end,
            "strokeStyle": "dashed" if dashed else "solid",
            "elbowed": False,
        })

        # two-way binding bookkeeping
        for nid in (src, dst):
            for e in self.elements:
                if e["id"] == nid:
                    e["boundElements"].append({"type": "arrow", "id": aid})
                    break
        self.elements.append(el)

        if label:
            tw, th = self._text_wh(label, 14)
            pts = el["points"]
            # 2-point arrow: index 1 is the endpoint, not midpoint — average instead
            if len(pts) == 2:
                mx = (pts[0][0] + pts[1][0]) / 2
                my = (pts[0][1] + pts[1][1]) / 2
            else:
                mx, my = pts[len(pts) // 2]
            lx = ax + mx - tw / 2
            ly = ay + my - th / 2
            tel = self._text_el(label, lx, ly, tw, th, size=14,
                                color=_STROKE["grey"], container=aid,
                                group=group)
            el["boundElements"].append({"type": "text", "id": tel["id"]})
            self.elements.append(tel)
        return aid

    def free_arrow(self, p0, p1, *, label=None, dashed=False, color=None,
                   end="arrow", start=None, group=None):
        """An unbound arrow between two absolute points."""
        return self.path([p0, p1], dashed=dashed, color=color, end=end,
                         start=start, label=label, group=group)

    @staticmethod
    def _polyline_midpoint(points):
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

    def path(self, points_abs, *, dashed=False, color=None, end="arrow",
             start=None, label=None, group=None):
        """An unbound multi-point connector through absolute (x, y) points.

        Use for routed connectors (e.g. a feedback loop that goes down, across,
        and back up) so the line visibly connects its two ends instead of
        floating in space."""
        sc = _hex(color, _STROKE, _STROKE["black"])
        aid = self._new_id("arrow")
        ax, ay = points_abs[0]
        rel = [[p[0] - ax, p[1] - ay] for p in points_abs]
        xs = [p[0] for p in rel]
        ys = [p[1] for p in rel]
        self._path_extents.append((min(p[0] for p in points_abs),
                                   min(p[1] for p in points_abs),
                                   max(p[0] for p in points_abs),
                                   max(p[1] for p in points_abs)))
        el = self._base(aid, "arrow", ax, ay,
                        max(xs) - min(xs), max(ys) - min(ys),
                        sc, "transparent", roundness=None, group=group)
        el.update({
            "points": rel, "lastCommittedPoint": None,
            "startBinding": None, "endBinding": None,
            "startArrowhead": start, "endArrowhead": end,
            "strokeStyle": "dashed" if dashed else "solid", "elbowed": False,
        })
        self.elements.append(el)
        if label:
            # place the label at the polyline's arc-length midpoint (the visual
            # middle of the routed line), never a corner waypoint
            mid = self._polyline_midpoint(points_abs)
            tw, th = self._text_wh(label, 13)
            lx, ly = mid[0] - tw / 2, mid[1] + 8
            # A10: white knock-out panel so the (unbound) label reads cleanly
            # over the LINE it sits on. The panel is overlap-CHECKED (added to
            # _nodes, not _containers): a routed label that lands on a box is a
            # real overlap — its white fill hides the box — so check_overlaps()
            # must catch it. It is left out of _geom so it is NOT treated as an
            # arrow-crossing obstacle (the path's own line legitimately runs
            # under it, and bound arrows elsewhere must not false-positive on it).
            lw, lh = tw + 8, th + 4
            bg = self._base(self._new_id("rectangle"), "rectangle",
                            lx - 4, ly - 2, lw, lh,
                            "transparent", "#ffffff", roundness={"type": 3})
            self.elements.append(bg)
            self._nodes.append((bg["id"], lx - 4, ly - 2, lw, lh,
                                f'label "{label.splitlines()[0][:24]}"'))
            self.elements.append(
                self._text_el(label, lx, ly, tw, th,
                              size=13, color=_STROKE["grey"], group=group))
        return aid

    def route_under(self, src, dst, *, drop=70, label=None, color="grey",
                    dashed=True, group=None):
        """A connector that leaves the bottom of `src`, runs below the row, and
        returns into the bottom of `dst`. Stays clear of the boxes in between."""
        sx, sy, sw, sh, _ = self._geom[src]
        dx_, dy_, dw, dh, _ = self._geom[dst]
        start = (sx + sw / 2, sy + sh)
        endp = (dx_ + dw / 2, dy_ + dh)
        low = max(sy + sh, dy_ + dh) + drop
        return self.path([start, (start[0], low), (endp[0], low), endp],
                         dashed=dashed, color=color, end="arrow", label=label,
                         group=group)

    # ====================================================================
    #  LAYOUT SANITY
    # ====================================================================
    def check_overlaps(self, min_px=1.0):
        """Return [(label_a, label_b), ...] for every pair of non-container
        nodes whose bounding boxes overlap by more than `min_px` in BOTH axes.

        Containers (frames, and shapes created with container=True) are exempt,
        because they are meant to sit behind their children."""
        hits = []
        nodes = self._nodes
        for i in range(len(nodes)):
            _, ax, ay, aw, ah, al = nodes[i]
            for j in range(i + 1, len(nodes)):
                _, bx, by, bw, bh, bl = nodes[j]
                ox = min(ax + aw, bx + bw) - max(ax, bx)
                oy = min(ay + ah, by + bh) - max(ay, by)
                if ox > min_px and oy > min_px:
                    hits.append((al, bl))
        return hits

    @staticmethod
    def _seg_rect_overlap(p0, p1, rect):
        """Length of the portion of segment p0->p1 that lies inside `rect`
        (x, y, w, h); 0 if it never enters. Liang–Barsky slab clipping."""
        x0, y0 = p0
        x1, y1 = p1
        rx, ry, rw, rh = rect
        dx, dy = x1 - x0, y1 - y0
        t0, t1 = 0.0, 1.0
        for p, q in ((-dx, x0 - rx), (dx, rx + rw - x0),
                     (-dy, y0 - ry), (dy, ry + rh - y0)):
            if p == 0:
                if q < 0:
                    return 0.0          # parallel to a slab and outside it
            else:
                r = q / p
                if p < 0:
                    if r > t1:
                        return 0.0
                    if r > t0:
                        t0 = r
                else:
                    if r < t0:
                        return 0.0
                    if r < t1:
                        t1 = r
        if t1 <= t0:
            return 0.0
        return (t1 - t0) * math.hypot(dx, dy)

    def check_arrow_crossings(self, threshold=12.0, inset=4.0):
        """Return [(src, dst, crossed), ...] where a bound arrow's straight
        src→dst path runs through an unrelated node by more than `threshold`
        pixels. Endpoints, containers and unbound arrows are ignored. This is a
        heuristic readability check — a clean layout returns []."""
        labels = {nid: lab for (nid, _x, _y, _w, _h, lab) in self._nodes}

        def center(gid):
            gx, gy, gw, gh, _s = self._geom[gid]
            return (gx + gw / 2, gy + gh / 2)

        hits = []
        for el in self.elements:
            if el.get("type") != "arrow":
                continue
            sb, eb = el.get("startBinding"), el.get("endBinding")
            if not sb or not eb:
                continue
            src, dst = sb["elementId"], eb["elementId"]
            if src not in self._geom or dst not in self._geom:
                continue
            p0, p1 = center(src), center(dst)
            # if an endpoint is a container, stop at its border so the segment
            # does not traverse the container's own children
            if src in self._containers:
                p0 = self._border_point(src, p1)
            if dst in self._containers:
                p1 = self._border_point(dst, p0)
            for nid, (nx, ny, nw, nh, _s) in self._geom.items():
                if nid in (src, dst) or nid in self._containers:
                    continue
                rw, rh = nw - 2 * inset, nh - 2 * inset
                if rw <= 0 or rh <= 0:
                    continue
                if self._seg_rect_overlap(
                        p0, p1, (nx + inset, ny + inset, rw, rh)) > threshold:
                    hits.append((labels.get(src, "?"), labels.get(dst, "?"),
                                 labels.get(nid, "?")))
        return hits

    def check_legend_coverage(self):
        """Colour-SSOT gate. Return the sorted list of fill colours used by real
        (non-container) nodes that the legend does NOT explain — `[]` when the
        legend covers every used fill, or when no `legend()` was rendered.

        The documented rule is "colour is the single source of truth for role;
        the legend lists every colour used." This is its mechanical form: once a
        legend exists, a box filled with a colour absent from the key is a
        silent inconsistency (a reader decoding by the legend gets the wrong
        meaning), so save() flags it. transparent / white / the background fill
        are neutral and never counted."""
        if not self._legend_colours:
            return []
        neutral = {"transparent", "#ffffff", self.background}
        shapes = {"rectangle", "ellipse", "diamond"}
        used = set()
        for el in self.elements:
            if el["id"] in self._containers:
                continue
            # native fillable shapes + ISO polygons (data/preparation): the latter
            # are serialized as type "line" with polygon:True but carry a real fill,
            # so their colour must also be explained by the legend
            if el.get("type") not in shapes and not el.get("polygon"):
                continue
            bg = el.get("backgroundColor")
            if bg and bg not in neutral:
                used.add(bg)
        return sorted(used - self._legend_colours)

    def check_text_overflow(self, tol=2.0):
        """Return [(label, text_w, box_w, text_h, box_h), ...] for every bound
        text whose rendered size exceeds its container SHAPE by more than `tol`
        px in either axis — a label too big for its box. The text then spills
        outside the box onto its neighbours, a silent failure the shape-overlap
        check cannot see (the shapes themselves do not overlap). Text bound to an
        arrow is ignored: arrow labels float on the connector by design."""
        shapes = {"rectangle", "ellipse", "diamond"}
        by_id = {e["id"]: e for e in self.elements}
        hits = []
        for e in self.elements:
            if e.get("type") != "text" or not e.get("containerId"):
                continue
            cont = by_id.get(e["containerId"])
            if not cont or cont.get("type") not in shapes:
                continue
            tw, th = e.get("width", 0), e.get("height", 0)
            cw, ch = cont.get("width", 0), cont.get("height", 0)
            if tw - cw > tol or th - ch > tol:
                label = (e.get("text") or "").split("\n")[0]
                hits.append((label, round(tw, 1), round(cw, 1),
                             round(th, 1), round(ch, 1)))
        return hits

    def check_text_overlaps(self, tol=2.0):
        """Return [(text_a, text_b), ...] for pairs of FREE (unbound) text
        elements whose bounding boxes overlap by more than `tol` px in BOTH axes.
        Free text = a title()/section()/label() caption (containerId is None);
        bound text — labels inside a box or on an arrow — is excluded, so
        legend/glossary row labels never false-fire. Catches a caption colliding
        with a section header or another caption: invisible to check_overlaps()
        because that only inspects shapes."""
        free = [e for e in self.elements
                if e.get("type") == "text" and not e.get("containerId")]
        hits = []
        for i in range(len(free)):
            ax, ay = free[i]["x"], free[i]["y"]
            aw, ah = free[i].get("width", 0), free[i].get("height", 0)
            for j in range(i + 1, len(free)):
                bx, by = free[j]["x"], free[j]["y"]
                bw, bh = free[j].get("width", 0), free[j].get("height", 0)
                ox = min(ax + aw, bx + bw) - max(ax, bx)
                oy = min(ay + ah, by + bh) - max(ay, by)
                if ox > tol and oy > tol:
                    hits.append(((free[i].get("text") or "")[:40],
                                 (free[j].get("text") or "")[:40]))
        return hits

    def check_short_arrows(self, min_len=24.0):
        """Return [(src_label, dst_label, length), ...] for every BOUND arrow
        whose drawn length (distance between its first and last point) is below
        `min_len` px — an arrow too short to render as a visible line.

        Why this is its own check: when two shapes sit close but do NOT overlap,
        arrow() clamps the per-side gap (g = min(gap, max(2, (dist-10)/2))) so the
        connector collapses toward zero length (e.g. ~40px of clear space leaves a
        ~12px arrow; <=4px leaves 0px). Excalidraw then draws no line — only the
        arrow's bound text label floats in place, the 'text without arrow' defect.
        check_overlaps() cannot see it (the boxes don't overlap), so this is its
        non-overlapping sibling: the deterministic guardrail for a degenerate
        connector. Only bound arrows (both endpoints bound to a shape) are checked
        — unbound path()/free_arrow()/route_under() connectors are intentional
        routed lines, not box-to-box links. `min_len` defaults to ~2x an
        Excalidraw arrowhead (~12px): below that the line is essentially just the
        head. Prior partial fixes (default-gap bump 4ea5f97, pipeline/row stderr
        warning 08ea0aa) did not cover manual box()+arrow() placement; this does.
        """
        labels = {nid: lab for (nid, _x, _y, _w, _h, lab) in self._nodes}
        hits = []
        for el in self.elements:
            if el.get("type") != "arrow":
                continue
            sb, eb = el.get("startBinding"), el.get("endBinding")
            if not sb or not eb:
                continue                          # unbound = intentional routed line
            pts = el.get("points") or []
            if len(pts) < 2:
                continue
            length = math.hypot(pts[-1][0] - pts[0][0], pts[-1][1] - pts[0][1])
            if length < min_len:
                hits.append((labels.get(sb.get("elementId"), "?"),
                             labels.get(eb.get("elementId"), "?"),
                             round(length, 1)))
        return hits

    def check_arrow_label_fit(self, min_stub=24.0):
        """Return [(label, stub_px), ...] for every BOUND arrow whose text label
        is too wide for the connector it sits on — leaving less than `min_stub`
        px of visible line on each side of the label.

        stub = (arrow_line_length - label_extent) / 2, where label_extent is the
        label's bounding box projected onto the arrow's direction (so a wide label
        eats a horizontal arrow, a tall label eats a vertical one). When the stub
        is small the label crowds the arrowheads; when it is NEGATIVE the label is
        longer than the whole arrow and spills onto the two boxes the arrow joins
        — a real overlap that check_text_overflow() (box labels only) and
        check_text_overlaps() (free captions only, bound labels excluded) both
        miss by design. This is the arrow-label sibling of those checks: a
        labelled connector reads cleanly only when its label fits between its ends
        with line still showing. Widen the gap between the two shapes, or
        shorten/wrap the label.
        """
        by_id = {e["id"]: e for e in self.elements}
        hits = []
        for el in self.elements:
            if el.get("type") != "arrow":
                continue
            if not el.get("startBinding") or not el.get("endBinding"):
                continue
            lab = next((by_id.get(b["id"]) for b in (el.get("boundElements") or [])
                        if b.get("type") == "text"), None)
            if not lab:
                continue
            pts = el.get("points") or []
            if len(pts) < 2:
                continue
            dx, dy = pts[-1][0] - pts[0][0], pts[-1][1] - pts[0][1]
            line = math.hypot(dx, dy)
            if line == 0:
                continue                       # zero-length: check_short_arrows' job
            ux, uy = dx / line, dy / line       # arrow direction (unit vector)
            # extent of the (axis-aligned) label box along the arrow direction
            extent = abs(lab.get("width", 0) * ux) + abs(lab.get("height", 0) * uy)
            stub = (line - extent) / 2
            if stub < min_stub:
                label = (lab.get("text") or "").split("\n")[0]
                hits.append((label, round(stub, 1)))
        return hits

    def bounds(self):
        """(min_x, min_y, max_x, max_y) over every shape AND every routed
        connector (path/route_under/free_arrow). Use it to stack several
        diagrams in one scene: start the next region below max_y — including the
        extents of feedback loops that dip beneath the row, so they don't
        collide with the region below."""
        xs0 = [g[0] for g in self._geom.values()] + [e[0] for e in self._path_extents]
        ys0 = [g[1] for g in self._geom.values()] + [e[1] for e in self._path_extents]
        xs1 = ([g[0] + g[2] for g in self._geom.values()]
               + [e[2] for e in self._path_extents])
        ys1 = ([g[1] + g[3] for g in self._geom.values()]
               + [e[3] for e in self._path_extents])
        if not xs0:
            return (0, 0, 0, 0)
        return (min(xs0), min(ys0), max(xs1), max(ys1))

    # ====================================================================
    #  SERIALISATION
    # ====================================================================
    def to_dict(self):
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

    def save(self, basename, out_dir=".", allow_overlap=False,
             allow_short_arrows=False,
             crossing_check="warn", legend_check="warn",
             overflow_check="warn", text_overlap_check="warn",
             label_fit_check="warn"):
        """Write <basename>.excalidraw + .html. Always re-runs the overlap
        check AND the short-arrow check first (so post-placement
        align()/distribute() or close manual placement can't ship a hidden
        overlap or a degenerate, invisible connector). Both are hard checks that
        RAISE by default — they are real defects, not readability heuristics; pass
        `allow_overlap=True` / `allow_short_arrows=True` to ship one deliberately.
        `crossing_check`, `legend_check`, `overflow_check`, `text_overlap_check`
        and `label_fit_check` each take "warn" (default, prints) or "error"
        (raises — opt-in gate):
          - crossing_check     — a bound arrow runs through an unrelated box.
          - legend_check       — a fill colour is missing from the legend (only
            fires when a legend() was rendered).
          - overflow_check     — bound text is bigger than its box (the label
            spills outside the shape). Shapes don't overlap, so check_overlaps()
            misses it.
          - text_overlap_check — two free captions/headers overlap each other.
            Also invisible to check_overlaps(), which only inspects shapes.
          - label_fit_check    — an arrow's label is wider than the connector it
            sits on, so it crowds the arrowheads or spills onto the joined
            boxes. Bound arrow labels are excluded from the two checks above."""
        # one scene, one save(): SKILL.md's "one file, many diagrams" rule —
        # stack extra views in the SAME scene instead of saving twice.
        if getattr(self, "_saved", False):
            raise RuntimeError(
                "save() already called on this Scene — one scene, one save(). "
                "Stack additional views as labelled regions in the same scene "
                "(use bounds() to start the next region below the previous one).")
        for name, val in (("crossing_check", crossing_check),
                          ("legend_check", legend_check),
                          ("overflow_check", overflow_check),
                          ("text_overlap_check", text_overlap_check),
                          ("label_fit_check", label_fit_check)):
            if val not in ("warn", "error"):
                raise ValueError(f"{name} must be 'warn' or 'error'")
        hits = self.check_overlaps()
        if hits and not allow_overlap:
            pairs = "; ".join(f"'{a}' overlaps '{b}'" for a, b in hits)
            raise ValueError(
                f"{len(hits)} overlapping shape(s): {pairs}. "
                "Move the coordinates apart, wrap a grouping shape with "
                "container=True, or pass allow_overlap=True if intentional.")
        shorts = self.check_short_arrows()
        if shorts and not allow_short_arrows:
            pairs = "; ".join(f"'{a}'->'{b}' ({ln:g}px)" for a, b, ln in shorts)
            raise ValueError(
                f"{len(shorts)} arrow(s) too short to render as a visible line "
                f"(only the label would show): {pairs}. Move the shapes farther "
                "apart (~60px+ of clear space), or pass allow_short_arrows=True "
                "if intentional.")
        crossings = self.check_arrow_crossings()
        if crossings:
            seen = sorted({f"{a}->{b} crosses '{c}'" for a, b, c in crossings})
            detail = "; ".join(seen)
            if crossing_check == "error":
                raise ValueError(
                    "arrow(s) run through an unrelated box: " + detail
                    + ". Reroute with route_under()/path(), move the box, or "
                    "pass crossing_check='warn' to downgrade to a warning.")
            print("WARNING: arrow(s) may run through an unrelated box — "
                  "reroute or move the box: " + detail)
        uncovered = self.check_legend_coverage()
        if uncovered:
            detail = ", ".join(uncovered)
            if legend_check == "error":
                raise ValueError(
                    "fill colour(s) used but missing from the legend: " + detail
                    + ". Add a legend() entry for each, recolour the box to a "
                    "legended colour, or pass legend_check='warn' to downgrade "
                    "to a warning.")
            print("WARNING: fill colour(s) used but not in the legend — a "
                  "reader decoding by the key gets no meaning for: " + detail)
        overflows = self.check_text_overflow()
        if overflows:
            detail = "; ".join(f"'{lab}' (text {tw}px in {cw}px box)"
                               for lab, tw, cw, _th, _ch in overflows)
            if overflow_check == "error":
                raise ValueError(
                    "bound text overflows its box: " + detail
                    + ". Widen the box (or wrap the label with fit_text()), or "
                    "pass overflow_check='warn' to downgrade to a warning.")
            print("WARNING: bound text is bigger than its box — the label spills "
                  "outside the shape: " + detail)
        text_overlaps = self.check_text_overlaps()
        if text_overlaps:
            detail = "; ".join(f"'{a}' overlaps '{b}'" for a, b in text_overlaps)
            if text_overlap_check == "error":
                raise ValueError(
                    "free text label(s) overlap: " + detail
                    + ". Move the caption/header apart, or pass "
                    "text_overlap_check='warn' to downgrade to a warning.")
            print("WARNING: free text label(s) overlap (a caption/header sits on "
                  "another): " + detail)
        label_fits = self.check_arrow_label_fit()
        if label_fits:
            detail = "; ".join(f"'{lab}' ({stub:g}px line each side)"
                               for lab, stub in label_fits)
            if label_fit_check == "error":
                raise ValueError(
                    "arrow label(s) too wide for their connector (the label "
                    "crowds or spills onto the boxes): " + detail
                    + ". Widen the gap between the shapes, shorten/wrap the "
                    "label, or pass label_fit_check='warn' to downgrade to a "
                    "warning.")
            print("WARNING: arrow label(s) wider than their connector — the "
                  "label crowds the arrowheads or spills onto a box: " + detail)
        os.makedirs(out_dir, exist_ok=True)
        scene = self.to_dict()
        p_json = os.path.join(out_dir, basename + ".excalidraw")
        # newline="\n" on every write: the default (None) translates "\n" to
        # os.linesep, so this generator emitted CRLF on Windows and LF on Linux -
        # the same scene, two different files. A committed diagram then differed by
        # the platform that regenerated it, which is exactly what a reproducibility
        # check cannot tolerate.
        with open(p_json, "w", encoding="utf-8", newline="\n") as f:
            json.dump(scene, f, ensure_ascii=False, indent=2)
        p_html = os.path.join(out_dir, basename + ".html")
        with open(p_html, "w", encoding="utf-8", newline="\n") as f:
            f.write(_html_page(basename, scene))
        self._saved = True
        return p_json, p_html


# ---------------------------------------------------------------------------
# Self-contained HTML viewer (renders the scene with the official component)
# ---------------------------------------------------------------------------
def _html_page(title, scene):
    scene_js = json.dumps(scene)
    tmpl = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>__TITLE__ — Excalidraw</title>
<link rel="stylesheet"
  href="https://unpkg.com/@excalidraw/excalidraw@0.17.6/dist/excalidraw.production.min.css" />
<style>
  html,body{margin:0;height:100%;font-family:ui-sans-serif,system-ui,sans-serif;background:#fff}
  #bar{display:flex;gap:.5rem;align-items:center;padding:.5rem .75rem;
       border-bottom:1px solid #e9ecef;background:#fafafa}
  #bar b{font-size:.95rem;color:#1e1e1e}
  #bar small{color:#868e96}
  #bar .sp{flex:1}
  #bar button{font:inherit;font-size:.85rem;padding:.35rem .7rem;border:1px solid #ced4da;
       border-radius:6px;background:#fff;cursor:pointer}
  #bar button:hover{background:#f1f3f5}
  #app{position:absolute;top:49px;left:0;right:0;bottom:0}
  #fallback{display:none;padding:2rem;color:#495057;max-width:640px;margin:0 auto;line-height:1.6}
  #fallback code{background:#f1f3f5;padding:.1rem .3rem;border-radius:4px}
</style>
</head>
<body>
<div id="bar">
  <b>__TITLE__</b>
  <small>· Excalidraw scene</small>
  <span class="sp"></span>
  <button id="dl">⬇ Download .excalidraw</button>
</div>
<div id="app"></div>
<div id="fallback">
  <h2>Couldn't load the Excalidraw renderer</h2>
  <p>The diagram is still embedded in this file. Download it below and open it
     at <a href="https://excalidraw.com" target="_blank" rel="noopener">excalidraw.com</a>
     (menu → Open) or drag the file onto the canvas.</p>
  <p><button id="dl2">⬇ Download .excalidraw</button></p>
</div>

<script>window.EXCALIDRAW_ASSET_PATH = "https://unpkg.com/@excalidraw/excalidraw@0.17.6/dist/";</script>
<script crossorigin src="https://unpkg.com/react@18.2.0/umd/react.production.min.js"></script>
<script crossorigin src="https://unpkg.com/react-dom@18.2.0/umd/react-dom.production.min.js"></script>
<script crossorigin src="https://unpkg.com/@excalidraw/excalidraw@0.17.6/dist/excalidraw.production.min.js"></script>
<script>
const SCENE = __SCENE__;

function download(){
  const blob = new Blob([JSON.stringify(SCENE, null, 2)],
                        {type:"application/json"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "__TITLE__.excalidraw";
  a.click();
  URL.revokeObjectURL(a.href);
}
document.getElementById("dl").onclick = download;
const dl2 = document.getElementById("dl2"); if (dl2) dl2.onclick = download;

window.addEventListener("load", function(){
  try {
    const E = window.ExcalidrawLib;
    if (!E || !window.React || !window.ReactDOM) throw new Error("CDN not loaded");
    const root = window.ReactDOM.createRoot(document.getElementById("app"));
    root.render(window.React.createElement(E.Excalidraw, {
      initialData: {
        elements: SCENE.elements,
        appState: { viewBackgroundColor: SCENE.appState.viewBackgroundColor },
        scrollToContent: true
      },
      viewModeEnabled: false,
      zenModeEnabled: false,
      gridModeEnabled: false,
      UIOptions: { canvasActions: { loadScene: false } }
    }));
  } catch (err) {
    console.error(err);
    document.getElementById("app").style.display = "none";
    document.getElementById("fallback").style.display = "block";
  }
});
</script>
</body>
</html>
"""
    return (tmpl.replace("__SCENE__", scene_js)
                .replace("__TITLE__", title))


# ---------------------------------------------------------------------------
# CLI verbs — render an existing scene, discover a repo into a generator stub
# (the skill's only authoring path stays Python; `build` from a declarative
# spec was deliberately not added — it would fork a second, divergent path.)
# ---------------------------------------------------------------------------
def render_html(scene_path, out_dir=None):
    """Regenerate the self-contained .html viewer from an existing .excalidraw
    scene file — e.g. one edited on excalidraw.com, for which there is no
    generator script to re-run. Writes <basename>.html beside the scene unless
    out_dir is given. Returns the .html path. Raises ValueError if the file is
    not a valid Excalidraw scene (a JSON object carrying an 'elements' list of
    element objects)."""
    with open(scene_path, encoding="utf-8") as f:
        scene = json.load(f)                      # JSONDecodeError (a ValueError) on bad JSON
    elements = scene.get("elements") if isinstance(scene, dict) else None
    if not isinstance(scene, dict) or not isinstance(elements, list) \
            or not all(isinstance(e, dict) for e in elements):
        raise ValueError(
            f"{scene_path}: not a valid Excalidraw scene "
            "(expected a JSON object with an 'elements' list of element objects)")
    base = os.path.splitext(os.path.basename(scene_path))[0]
    out_dir = out_dir or (os.path.dirname(os.path.abspath(scene_path)))
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, base + ".html")
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(_html_page(base, scene))
    return out_path


_DISCOVER_EXTS = (".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs",
                  ".c", ".cpp", ".h", ".java", ".rb", ".php")
_DISCOVER_PRUNE = {".git", "node_modules", "__pycache__", ".venv", "venv",
                   "env", "dist", "build", "target", ".idea", ".vscode",
                   ".pytest_cache", ".mypy_cache"}


def _dir_has_source(d):
    """True if directory d (recursively, minus pruned dirs) holds any source file."""
    for dirpath, dirs, files in os.walk(d):
        dirs[:] = [x for x in dirs if x not in _DISCOVER_PRUNE and not x.startswith(".")]
        if any(f.endswith(_DISCOVER_EXTS) for f in files):
            return True
    return False


def discover_components(repo):
    """Scan a repo and return its top-level 'components', sorted: each immediate
    child directory that (recursively) contains source, plus each top-level
    source file. Deterministic and cross-platform (sorted, pruned). A heuristic
    scaffold only — the human/LLM refines the real edges + grouping in the stub."""
    repo = os.path.abspath(repo)
    comps = []
    for entry in sorted(os.listdir(repo)):
        if entry in _DISCOVER_PRUNE or entry.startswith("."):
            continue
        full = os.path.join(repo, entry)
        if os.path.isdir(full):
            if _dir_has_source(full):
                comps.append(entry)
        elif entry.endswith(_DISCOVER_EXTS):
            comps.append(entry)
    return comps


# Import preamble baked into every generated stub: try the builder next to the
# stub (or on PYTHONPATH — how CI runs it), else fall back to the newest builder
# in the plugin cache, so a stub generated into ANY repo still runs. Plain raw
# string (not an f-string) so the regex backslashes survive verbatim.
_STUB_IMPORT = r'''import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from excalidraw_builder import Scene
except ModuleNotFoundError:                      # not alongside the stub — find the plugin
    # Falls back to the newest INSTALLED plugin build; if you run this stub outside
    # the plugin, that cached build may lag an unreleased local edit to the builder.
    import glob, re
    _cache = os.path.join(os.path.expanduser("~"), ".claude", "plugins",
                          "cache", "requirement-manager", "requirement-manager")
    _hits = glob.glob(os.path.join(_cache, "*", "skills",
                                   "excalidraw-diagram", "scripts"))
    if not _hits:
        raise
    def _ver(p):
        m = re.search(r"(\d+)\.(\d+)\.(\d+)", p)
        return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)
    sys.path.insert(0, max(_hits, key=_ver))     # newest installed version
    from excalidraw_builder import Scene'''


def _render_stub(repo_name, comps, truncated):
    """Render the text of a runnable, multi-LAYER poster stub from the components.

    The stub is a single-file architecture poster: layer 1 (STRUCTURE) is live and
    runs as-is; layers 2-6 are commented scaffolds the author keeps/deletes per what
    the repo actually needs. This encodes the skill's adaptive recipe — pick the
    layers that explain THIS repo, emit them all in one file."""
    items = comps or ["component-a", "component-b"]
    items_repr = ", ".join(repr(c) for c in items)
    cols = min(4, max(1, len(items)))
    # Size the grid cells to the longest component name so the live STRUCTURE layer
    # never trips overflow_check (the stub ships with all five gates at "error").
    longest = max((len(c) for c in items), default=12)
    gw = max(160, int(longest * 13 * 0.62) + 26)
    # Sanitize the repo name before it lands in the generated stub: a name with a
    # quote (or `"""`) would otherwise break the stub's docstring / string literals
    # on filesystems that allow such characters. Also keeps the saved filename sane.
    safe = "".join(c if (c.isalnum() or c in " _-.") else "_" for c in repo_name) or "diagram"
    notes = []
    if not comps:
        notes.append("# NOTE: no source components auto-detected — placeholders shown; replace them.")
    if truncated:
        notes.append("# NOTE: repo had more components than the cap; only the first are shown.")
    note_block = ("\n".join(notes) + "\n") if notes else ""
    return f'''#!/usr/bin/env python3
"""Diagram generator for {safe} — scaffolded by `excalidraw_builder.py discover`.

A multi-LAYER architecture poster in ONE file. Layer 1 (STRUCTURE) is live and
runnable now; layers 2-6 are commented scaffolds. DECIDE PER REPO which layers
explain it, KEEP those, delete the rest, and fill in the real content:

  1. STRUCTURE       (always)   the components and how they group
  2. WORKFLOW        if it has a pipeline / run-order / algorithm
  3. INTEGRATION     if it is invoked by / connects to external systems, CI, a loop
  4. MODES/VARIANTS  if it has modes / strategies / variants of the same flow
  5. MODEL/RUNNERS   if parts run on different models / workers / runtimes
  6. DATA/SCHEMA     if it produces a core record / output shape

Colour = role: give each distinct meaning its own colour and add ONE legend()
when colour is used. Keep all five save() gates at "error". Then run this file to
emit {safe}.excalidraw + {safe}.html.
"""
{_STUB_IMPORT}

s = Scene(seed=7)
s.title({safe!r}, 40, -70, size=30)
s.label("What it is, how it runs, how it integrates. Left -> right within a layer.",
        40, -34, size=14, align="left")

# ---- 1 - STRUCTURE (live: one box per discovered component) ----------------
y = s.section("1 - STRUCTURE   the components")
{note_block}nodes = s.grid([{items_repr}], 40, y, {cols}, w={gw}, h=64, font_size=13)
# TODO: group related nodes -> s.enclose([nodes[0], nodes[1]], label="subsystem")

# ---- 2 - WORKFLOW (optional: uncomment if the repo has a pipeline) ----------
# y = s.section("2 - WORKFLOW   run order (left -> right)")
# s.pipeline([("Start", "terminator"), ("step", "process"),
#             ("ok?", "decision"), ("Done", "terminator")], 40, y)
# Multi-tool repo (bundles 2+ skills/services with distinct flows)? Do NOT hide
# them in one pipeline — give each its own labelled lane (single-tool: skip this):
# t1 = s.pipeline([("step1", "process"), ("step2", "process")], 120, y + 40)
# s.lane(t1, "tool-one - one-line role")
# t2 = s.pipeline([("step1", "process"), ("step2", "process")], 120, y + 210)
# s.lane(t2, "tool-two - one-line role")

# ---- 3 - INTEGRATION (optional: entry points, external systems, loops) ------
# y = s.section("3 - INTEGRATION   how it is invoked and what it touches")
# entry = s.box("entry point", 40, y, fill="blue")
# ext   = s.box("external system", 320, y, fill="grey")
# s.arrow(entry, ext, label="calls")

# ---- 4 - MODES / VARIANTS (optional: one column per mode, enclosed) ---------
# y = s.section("4 - MODES   variants of the same flow")
# m1 = s.column(["step A", "step B"], 40, y + 40, fill="violet", connect=True)
# s.enclose(m1, label="mode one")

# ---- 5 - MODEL / RUNNERS (optional: group -> arrow -> runtime) --------------
# y = s.section("5 - MODEL ASSIGNMENT   what runs where")
# grp = s.enclose(s.column(["part a", "part b"], 40, y + 40), label="components")
# s.arrow(grp, s.box("runtime / model", 420, y + 60, fill="yellow"), label="runs on")

# ---- 6 - DATA / SCHEMA (optional: the record it produces) -------------------
# y = s.section("6 - DATA SCHEMA   the record it produces")
# s.box("record / field_a / field_b / field_c", 40, y, w=300, h=140, fill="green")

# When colour encodes a role, add ONE legend() that decodes the whole poster:
# s.legend([("component", "blue"), ("external system", "grey")],
#          40, s.bounds()[3] + 50, title="Legend - colour = role")

s.save({safe!r}, crossing_check="error", legend_check="error",
       overflow_check="error", text_overlap_check="error", label_fit_check="error")
print("wrote {safe}.excalidraw + .html")
'''


def discover_stub(repo, out_path=None, max_components=20):
    """Emit a runnable Python generator stub (default: ./make_diagram.py) seeded
    from a repo scan — one box per discovered component on a no-overlap grid, with
    TODO markers for the edges/grouping the author adds. Returns the stub path.
    Running the stub produces a valid (if skeletal) .excalidraw + .html."""
    comps = discover_components(repo)
    truncated = len(comps) > max_components
    if truncated:
        comps = comps[:max_components]
    repo_name = os.path.basename(os.path.abspath(repo)) or "repo"
    out_path = out_path or os.path.join(os.getcwd(), "make_diagram.py")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(_render_stub(repo_name, comps, truncated))
    return out_path


_USAGE = """usage: excalidraw_builder.py [<command>]

  (no command)                         run the builder self-test (smoke test)
  render <scene.excalidraw> [out_dir]  rebuild the .html viewer from an existing scene
  discover <repo> [out.py]             scan a repo -> a runnable Python generator stub

The skill's authoring path is Python: write (or `discover`-scaffold) a generator
script against the Scene API, then run it. `render` re-emits the viewer for a scene
edited elsewhere (e.g. excalidraw.com)."""


def _selftest():
    # smoke test — exercises auto-layout, the new Phase-1 helpers, and checks
    import tempfile
    out = os.path.join(tempfile.gettempdir(), "excd")
    s = Scene(seed=1, roles={"source": "blue", "worker": "violet"})
    s.title("demo", 0, -40, size=24)
    stages = s.row(["ingest", "process", "store"], 0, 0, fill="source",
                   connect=True)            # role-colour fill (A4)
    workers = s.grid([f"n{i}" for i in range(9)], 0, 150, 3,
                     w=120, h=60, fill="worker")
    s.enclose(workers, label="parallel workers")
    done = s.box("done", 720, 0, fill="green")
    s.arrow(stages[-1], done)
    s.path([(0, 460), (620, 460)], label="feedback")   # A10 labelled path (clear of the grid)
    s.legend([("source", "blue"), ("worker", "violet"), ("done", "green")],
             x=760, y=150)                  # A2 legend
    # A5 align/distribute must keep the overlap check honest
    movers = s.column(["a", "b", "c"], 760, 360, w=80, h=40)
    s.align(movers, "left")
    s.distribute(movers, "y", gap=20)
    assert not s.check_overlaps(), s.check_overlaps()
    assert not s.check_arrow_crossings(), s.check_arrow_crossings()
    # colour-SSOT: every fill used (blue/violet/green) is in the legend above
    assert not s.check_legend_coverage(), s.check_legend_coverage()
    # ISO polygons (data/preparation) are serialized as type "line" + polygon but
    # carry a real fill — an unexplained one must still be flagged by the gate
    iso = Scene(seed=7)
    iso.data("input", 0, 0, fill="blue")
    iso.legend([("worker", "violet")], 0, 200)
    assert iso.check_legend_coverage(), "unexplained ISO polygon fill must be flagged"
    # short-arrow gate: this clean scene has none; a close pair must be caught
    # and save() must raise on it by default (the 'text without arrow' defect)
    assert not s.check_short_arrows(), s.check_short_arrows()
    sa = Scene(seed=4)
    ca = sa.box("A", 0, 0, w=120, h=60)
    cb = sa.box("B", 124, 0, w=120, h=60)   # 4px apart -> degenerate connector
    sa.arrow(ca, cb, label="x")
    assert sa.check_overlaps() == [], "close-but-not-touching boxes don't overlap"
    assert len(sa.check_short_arrows()) == 1, sa.check_short_arrows()
    try:
        sa.save("smoke_short", out_dir=out)
        raise SystemExit("FAIL: short-arrow gate did not raise by default")
    except ValueError:
        pass
    sa.save("smoke_short", out_dir=out, allow_short_arrows=True)  # escape works
    pj, ph = s.save("smoke", out_dir=out)   # crossing_check defaults to "warn"
    # A7 opt-in gate: a deliberate crossing must raise under crossing_check="error"
    s2 = Scene(seed=2)
    left = s2.box("L", 0, 0, w=80, h=40)
    mid = s2.box("M", 200, 0, w=80, h=40)
    right = s2.box("R", 400, 0, w=80, h=40)
    s2.arrow(left, right)                    # straight line passes through M
    try:
        s2.save("smoke_err", out_dir=out, crossing_check="error")
        raise SystemExit("FAIL: crossing_check='error' did not raise")
    except ValueError:
        pass
    # pipeline([]) returns [] instead of crashing on max() of an empty sequence
    assert Scene(seed=8).pipeline([], 0, 0) == [], "empty pipeline must return []"
    # a curved arrow's bbox spans its control-point dip, not just the endpoint
    sc = Scene(seed=9)
    cca = sc.box("A", 0, 0, w=80, h=40)
    ccb = sc.box("B", 300, 0, w=80, h=40)   # horizontally aligned -> flat endpoints
    caid = sc.arrow(cca, ccb, curve=True)
    cael = next(e for e in sc.elements if e["id"] == caid)
    assert cael["height"] >= 29, ("curved arrow bbox must span the control point", cael["height"])
    # routed-path label sits at the arc-length midpoint, not a corner waypoint
    mid = Scene._polyline_midpoint([(0, 0), (0, 100), (200, 100), (200, 0)])
    assert abs(mid[0] - 100) < 1 and abs(mid[1] - 100) < 1, mid
    # bounds() includes a routed connector's extents (route_under's drop below)
    sb = Scene(seed=3)
    ba = sb.box("a", 0, 0, w=80, h=40)
    bb = sb.box("b", 200, 0, w=80, h=40)
    sb.route_under(ba, bb, drop=60)
    assert sb.bounds()[3] >= 100, sb.bounds()
    print("wrote", pj, ph)
    print("overlaps:", s.check_overlaps(),
          "crossings:", s.check_arrow_crossings())
    print("OK smoke test (legend/role/align/distribute/path-bg/crossing-gate)")


def _main(argv):
    """CLI dispatch. No command -> self-test (so `python excalidraw_builder.py`
    stays the smoke test CI relies on). Returns a process exit code."""
    if not argv:
        _selftest()
        return 0
    verb = argv[0]
    if verb in ("-h", "--help", "help"):
        print(_USAGE)
        return 0
    if verb == "selftest":
        _selftest()
        return 0
    try:
        if verb == "render":
            if len(argv) < 2:
                print("usage: excalidraw_builder.py render <scene.excalidraw> [out_dir]", file=sys.stderr)
                return 2
            print("wrote", render_html(argv[1], argv[2] if len(argv) > 2 else None))
            return 0
        if verb == "discover":
            if len(argv) < 2:
                print("usage: excalidraw_builder.py discover <repo> [out.py]", file=sys.stderr)
                return 2
            print("wrote", discover_stub(argv[1], argv[2] if len(argv) > 2 else None))
            return 0
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"unknown command: {verb!r} — use render, discover, or no command for the self-test",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
