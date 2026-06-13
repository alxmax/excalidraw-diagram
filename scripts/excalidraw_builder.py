#!/usr/bin/env python3
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

    s = Scene(hand_drawn=True)
    a = s.box("User prompt",     120,  40, fill="blue")
    b = s.box("Consilium skill", 120, 180, fill="indigo")
    s.arrow(a, b, label="activates")
    s.title("CONSILIUM", 120, -40, size=36)
    s.save("consilium")          # -> consilium.excalidraw + consilium.html

The .excalidraw file imports cleanly into excalidraw.com (drag & drop) and the
.html file renders the same scene in the browser via the official Excalidraw
component, read-only, with edit/export still available.

Public API (see method docstrings for detail)
    Scene(hand_drawn=True, background="#ffffff")
    .box(text, x, y, w=160, h=70, *, fill=None, stroke=None, shape="rectangle",
         font_size=16, group=None)        -> node id
    .ellipse(text, x, y, w, h, ...)        -> node id   (shape="ellipse")
    .diamond(text, x, y, w, h, ...)        -> node id   (shape="diamond")
    .frame(x, y, w, h, *, fill=None, dashed=False, group=None) -> node id
    .label(text, x, y, *, size=12, color=None, align="center", italic-ish caps)
    .title(text, x, y, *, size=28, color=None)
    .arrow(src, dst, *, label=None, dashed=False, color=None,
           start="dot"/None, end="arrow")  -> arrow id
    .free_arrow((x1,y1),(x2,y2), ...)       -> arrow id  (unbound)
    .save(basename, out_dir=".")            -> (path_excalidraw, path_html)

Colours accept either a hex string ("#a5d8ff") or a palette name:
    grey, red, orange, yellow, green, teal, blue, indigo, violet, pink.
"""

import json
import math
import os
import random
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


def _rand():
    return random.randint(1, 2_000_000_000)


def _now():
    return int(time.time() * 1000)


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
                 background="#ffffff"):
        """A drawing surface.

        font  : "normal" (Helvetica), "hand" (Excalifont), or "code".
        sketch: True = rough/hand-drawn shape outlines, False = clean lines.
        hand_drawn: back-compat alias — True sets font="hand", sketch=True.
        """
        if hand_drawn is not None:
            font = "hand" if hand_drawn else "normal"
            sketch = bool(hand_drawn)
        self.elements = []
        self.background = background
        self.font = {"hand": _FONT_HAND, "normal": _FONT_NORMAL,
                     "code": 3}.get(font, _FONT_NORMAL)
        self.roughness = 1 if sketch else 0
        self._n = 0
        # registry of geometry so arrows can compute endpoints
        self._geom = {}  # id -> (x, y, w, h, shape)
        # overlap bookkeeping: normal nodes are collision-checked at save()
        self._nodes = []          # [(id, x, y, w, h, label)] to check
        self._containers = set()  # frames + container=True shapes (exempt)

    # -- id helpers --------------------------------------------------------
    def _new_id(self, prefix):
        self._n += 1
        return f"{prefix}-{self._n}-{_rand():08x}"

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
            "seed": _rand(),
            "version": 1,
            "versionNonce": _rand(),
            "isDeleted": False,
            "boundElements": [],
            "updated": _now(),
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
        bg = _hex(fill, _FILL, "transparent")
        roundness = {"type": 3} if shape == "rectangle" else None
        cid = self._new_id(shape)
        cont = self._base(cid, shape, x, y, w, h, sc, bg,
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

        self._geom[cid] = (x, y, w, h, shape)
        if container:
            self._containers.add(cid)
        else:
            self._nodes.append((cid, x, y, w, h,
                                (text or "").split("\n")[0] or shape))
        return cid

    def ellipse(self, text, x, y, w=170, h=110, **kw):
        return self.box(text, x, y, w, h, shape="ellipse", **kw)

    def diamond(self, text, x, y, w=160, h=90, **kw):
        return self.box(text, x, y, w, h, shape="diamond", **kw)

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
    #  FREE-STANDING TEXT (titles & small caption labels)
    # ====================================================================
    def title(self, text, x, y, *, size=28, color=None, align="left",
              group=None):
        c = _hex(color, _STROKE, _STROKE["black"])
        tw, th = self._text_wh(text, size)
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
        # rectangle / diamond -> clip to the box border
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
        w = abs(pts[-1][0]); h = abs(pts[-1][1])

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
            # 2-point path: index 1 is the endpoint — use true midpoint instead
            if len(points_abs) == 2:
                mid = ((points_abs[0][0] + points_abs[1][0]) / 2,
                       (points_abs[0][1] + points_abs[1][1]) / 2)
            else:
                mid = points_abs[len(points_abs) // 2]
            tw, th = self._text_wh(label, 13)
            self.elements.append(
                self._text_el(label, mid[0] - tw / 2, mid[1] + 8, tw, th,
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

    def bounds(self):
        """(min_x, min_y, max_x, max_y) over every shape. Use it to stack
        several diagrams in one scene: start the next region below max_y."""
        if not self._geom:
            return (0, 0, 0, 0)
        x0 = min(g[0] for g in self._geom.values())
        y0 = min(g[1] for g in self._geom.values())
        x1 = max(g[0] + g[2] for g in self._geom.values())
        y1 = max(g[1] + g[3] for g in self._geom.values())
        return (x0, y0, x1, y1)

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

    def save(self, basename, out_dir=".", allow_overlap=False):
        hits = self.check_overlaps()
        if hits and not allow_overlap:
            pairs = "; ".join(f"'{a}' overlaps '{b}'" for a, b in hits)
            raise ValueError(
                f"{len(hits)} overlapping shape(s): {pairs}. "
                "Move the coordinates apart, wrap a grouping shape with "
                "container=True, or pass allow_overlap=True if intentional.")
        os.makedirs(out_dir, exist_ok=True)
        scene = self.to_dict()
        p_json = os.path.join(out_dir, basename + ".excalidraw")
        with open(p_json, "w", encoding="utf-8") as f:
            json.dump(scene, f, ensure_ascii=False, indent=2)
        p_html = os.path.join(out_dir, basename + ".html")
        with open(p_html, "w", encoding="utf-8") as f:
            f.write(_html_page(basename, scene))
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


if __name__ == "__main__":
    # tiny smoke test
    s = Scene()
    a = s.box("A", 80, 80, fill="blue")
    b = s.box("B", 80, 240, fill="green")
    s.arrow(a, b, label="next")
    s.title("demo", 80, 20, size=24)
    pj, ph = s.save("smoke", out_dir="/tmp/excd")
    print("wrote", pj, ph)
