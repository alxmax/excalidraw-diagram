"""The scene as a standalone SVG: the third output a caller can ask for.

Pure and stdlib-only: it reads the same scene dict an `.excalidraw` file holds and
writes text, so it also works on a scene edited on excalidraw.com. Lines come out
clean, not hand-drawn — the rough outlines are Excalidraw's own renderer, and writing
that would be a second implementation of it. The two typefaces that carry a look
(hand-drawn and code) are embedded from the vendored fonts, so a browser shows them;
another SVG reader may fall back to a system font.
"""

import math
import os
from xml.sax.saxutils import escape, quoteattr

from . import assets
from .viewer import load_scene

_PAD = 24                      # white space kept around the drawing
_HEAD_LEN, _HEAD_ANGLE = 16.0, math.radians(24)
_DASH = {"dashed": "8 8", "dotted": "2 7"}
_LINE_HEIGHT = 1.25
_SANS = "Helvetica, Arial, sans-serif"
# Excalidraw fontFamily code -> (vendored face to embed or None, CSS font stack)
_FAMILIES = {
    1: ("Virgil", "Virgil, 'Segoe Print', 'Comic Sans MS', cursive"),
    2: (None, _SANS),
    3: ("Cascadia", "Cascadia, Consolas, 'Courier New', monospace"),
}


def _n(value):
    """A number as the shortest text that still keeps two decimals."""
    return ("%.2f" % value).rstrip("0").rstrip(".") or "0"


def _paint(el, fill=True):
    """The presentation attributes every drawn element shares."""
    stroke = el.get("strokeColor") or "#1e1e1e"
    bg = el.get("backgroundColor") or "transparent"
    attrs = ['stroke=%s' % quoteattr(stroke),
             'stroke-width="%s"' % _n(el.get("strokeWidth", 2)),
             'fill=%s' % (quoteattr(bg) if fill and bg != "transparent" else '"none"'),
             'stroke-linecap="round"', 'stroke-linejoin="round"']
    dash = _DASH.get(el.get("strokeStyle"))
    if dash:
        attrs.append('stroke-dasharray="%s"' % dash)
    opacity = el.get("opacity", 100)
    if opacity != 100:
        attrs.append('opacity="%s"' % _n(opacity / 100.0))
    return " ".join(attrs)


def _points(el):
    """The absolute (x, y) points of a line or arrow."""
    return [(el["x"] + p[0], el["y"] + p[1]) for p in el.get("points") or []]


def _rounded(el):
    """The corner radius Excalidraw gives a rounded rectangle: a quarter of the
    shorter side, capped at 32."""
    if not el.get("roundness"):
        return 0.0
    return min(32.0, 0.25 * min(el["width"], el["height"]))


def _curve(pts):
    """A path through `pts` as a smooth cubic Bezier (Catmull-Rom), the way
    Excalidraw draws a curved connector."""
    d = ["M%s %s" % (_n(pts[0][0]), _n(pts[0][1]))]
    for i in range(len(pts) - 1):
        p0, p1 = pts[max(i - 1, 0)], pts[i]
        p2, p3 = pts[i + 1], pts[min(i + 2, len(pts) - 1)]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6.0, p1[1] + (p2[1] - p0[1]) / 6.0)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6.0, p2[1] - (p3[1] - p1[1]) / 6.0)
        d.append("C%s %s %s %s %s %s" % (_n(c1[0]), _n(c1[1]), _n(c2[0]), _n(c2[1]),
                                          _n(p2[0]), _n(p2[1])))
    return " ".join(d)


def _head(tip, behind, kind, el):
    """An arrowhead at `tip`, pointing away from `behind`."""
    dx, dy = tip[0] - behind[0], tip[1] - behind[1]
    length = math.hypot(dx, dy)
    if not length:
        return ""
    ang = math.atan2(dy, dx)
    color = quoteattr(el.get("strokeColor") or "#1e1e1e")
    width = _n(el.get("strokeWidth", 2))
    if kind in ("dot", "circle", "circle_outline"):
        return '<circle cx="%s" cy="%s" r="5" fill=%s/>' % (_n(tip[0]), _n(tip[1]), color)
    if kind == "bar":
        px, py = -math.sin(ang) * 7, math.cos(ang) * 7
        return '<line x1="%s" y1="%s" x2="%s" y2="%s" stroke=%s stroke-width="%s" ' \
               'stroke-linecap="round"/>' % (_n(tip[0] + px), _n(tip[1] + py),
                                              _n(tip[0] - px), _n(tip[1] - py), color, width)
    wing = [(tip[0] - _HEAD_LEN * math.cos(ang + s * _HEAD_ANGLE),
             tip[1] - _HEAD_LEN * math.sin(ang + s * _HEAD_ANGLE)) for s in (1, -1)]
    pts = "%s,%s %s,%s %s,%s" % (_n(wing[0][0]), _n(wing[0][1]), _n(tip[0]), _n(tip[1]),
                                  _n(wing[1][0]), _n(wing[1][1]))
    if kind == "triangle":
        return '<polygon points="%s" fill=%s stroke=%s stroke-width="%s" ' \
               'stroke-linejoin="round"/>' % (pts, color, color, width)
    return '<polyline points="%s" fill="none" stroke=%s stroke-width="%s" ' \
           'stroke-linecap="round" stroke-linejoin="round"/>' % (pts, color, width)


def _line(el):
    """A line or an arrow: its path, closed and filled when it is a polygon, plus
    the arrowheads an arrow carries."""
    pts = _points(el)
    if len(pts) < 2:
        return ""
    if el.get("polygon"):
        return '<polygon points="%s" %s/>' % (
            " ".join("%s,%s" % (_n(x), _n(y)) for x, y in pts[:-1]), _paint(el))
    curved = (el.get("roundness") or {}).get("type") == 2 and len(pts) > 2
    if curved:
        path = '<path d="%s" %s/>' % (_curve(pts), _paint(el, fill=False))
    else:
        path = '<polyline points="%s" %s/>' % (
            " ".join("%s,%s" % (_n(x), _n(y)) for x, y in pts), _paint(el, fill=False))
    if el["type"] != "arrow":
        return path
    heads = ""
    if el.get("endArrowhead"):
        heads += _head(pts[-1], pts[-2], el["endArrowhead"], el)
    if el.get("startArrowhead"):
        heads += _head(pts[0], pts[1], el["startArrowhead"], el)
    return path + heads


def _text(el):
    """A text element: one <tspan> per line, anchored the way its box is aligned."""
    size = float(el.get("fontSize", 16))
    lines = str(el.get("text", "")).split("\n")
    step = size * _LINE_HEIGHT
    total = step * len(lines)
    align = el.get("textAlign", "left")
    x = el["x"] + {"left": 0.0, "center": el["width"] / 2.0,
                   "right": el["width"]}.get(align, 0.0)
    anchor = {"left": "start", "center": "middle", "right": "end"}.get(align, "start")
    top = el["y"] + {"middle": (el["height"] - total) / 2.0,
                     "bottom": el["height"] - total}.get(el.get("verticalAlign"), 0.0)
    family = _FAMILIES.get(el.get("fontFamily"), _FAMILIES[2])[1]
    spans = "".join('<tspan x="%s" y="%s">%s</tspan>'
                    % (_n(x), _n(top + i * step + step / 2.0 + size * 0.32), escape(line))
                    for i, line in enumerate(lines))
    return ('<text font-size="%s" font-family=%s text-anchor="%s" fill=%s '
            'xml:space="preserve">%s</text>'
            % (_n(size), quoteattr(family), anchor,
               quoteattr(el.get("strokeColor") or "#1e1e1e"), spans))


def _shape(el):
    """The SVG for one scene element, or "" for a type with nothing to draw."""
    kind, x, y = el.get("type"), el.get("x", 0.0), el.get("y", 0.0)
    w, h = el.get("width", 0.0), el.get("height", 0.0)
    if kind == "rectangle":
        r = _rounded(el)
        return '<rect x="%s" y="%s" width="%s" height="%s"%s %s/>' % (
            _n(x), _n(y), _n(w), _n(h),
            ' rx="%s"' % _n(r) if r else "", _paint(el))
    if kind == "ellipse":
        return '<ellipse cx="%s" cy="%s" rx="%s" ry="%s" %s/>' % (
            _n(x + w / 2), _n(y + h / 2), _n(w / 2), _n(h / 2), _paint(el))
    if kind == "diamond":
        pts = [(x + w / 2, y), (x + w, y + h / 2), (x + w / 2, y + h), (x, y + h / 2)]
        return '<polygon points="%s" %s/>' % (
            " ".join("%s,%s" % (_n(a), _n(b)) for a, b in pts), _paint(el))
    if kind in ("line", "arrow"):
        return _line(el)
    if kind == "text":
        return _text(el)
    return ""


def _extent(elements):
    """(min_x, min_y, max_x, max_y) over everything that will be drawn."""
    xs, ys = [], []
    for el in elements:
        if el.get("type") in ("line", "arrow") and el.get("points"):
            pts = _points(el)
            xs += [p[0] for p in pts]
            ys += [p[1] for p in pts]
        else:
            xs += [el.get("x", 0.0), el.get("x", 0.0) + el.get("width", 0.0)]
            ys += [el.get("y", 0.0), el.get("y", 0.0) + el.get("height", 0.0)]
    return (min(xs), min(ys), max(xs), max(ys)) if xs else (0.0, 0.0, 0.0, 0.0)


def _fonts(elements):
    """The @font-face rules for the embedded typefaces these elements use."""
    used = {_FAMILIES.get(el.get("fontFamily"), _FAMILIES[2])[0]
            for el in elements if el.get("type") == "text"}
    names = tuple(sorted(n + ".woff2" for n in used if n))
    if not names or not all(os.path.exists(os.path.join(assets._DIR, n)) for n in names):
        return ""
    return "<defs><style>%s</style></defs>" % assets.font_faces(names)


def scene_svg(scene, title=None):
    # implements: REQ-EXCALIDRAW-856
    """The scene dict as a complete SVG document, sized to its drawing plus a margin
    and painted on the scene's own background. Deterministic: the same scene is the
    same text. Deleted elements are skipped. `title` becomes the SVG's <title>."""
    elements = [e for e in scene.get("elements", []) if not e.get("isDeleted")]
    x0, y0, x1, y1 = _extent(elements)
    x0, y0, x1, y1 = x0 - _PAD, y0 - _PAD, x1 + _PAD, y1 + _PAD
    w, h = x1 - x0, y1 - y0
    bg = (scene.get("appState") or {}).get("viewBackgroundColor") or "#ffffff"
    arrows = {e.get("id") for e in elements if e.get("type") == "arrow"}
    body = []
    for el in elements:
        svg = _shape(el)
        if not svg:
            continue
        if el.get("type") == "text" and el.get("containerId") in arrows:
            # a label bound to an arrow sits on a patch of background, so the line
            # does not strike through it — as Excalidraw's own renderer does
            svg = '<rect x="%s" y="%s" width="%s" height="%s" fill=%s/>%s' % (
                _n(el["x"] - 3), _n(el["y"]), _n(el["width"] + 6), _n(el["height"]),
                quoteattr(bg), svg)
        angle = el.get("angle") or 0
        if angle:
            cx, cy = el["x"] + el["width"] / 2.0, el["y"] + el["height"] / 2.0
            svg = '<g transform="rotate(%s %s %s)">%s</g>' % (
                _n(math.degrees(angle)), _n(cx), _n(cy), svg)
        body.append(svg)
    head = '<title>%s</title>' % escape(title) if title else ""
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="%s %s %s %s" '
            'width="%s" height="%s">%s%s<rect x="%s" y="%s" width="%s" height="%s" '
            'fill=%s/>\n%s\n</svg>\n'
            % (_n(x0), _n(y0), _n(w), _n(h), _n(w), _n(h), head, _fonts(elements),
               _n(x0), _n(y0), _n(w), _n(h), quoteattr(bg), "\n".join(body)))


def render_svg(scene_path, out_dir=None):
    # implements: REQ-EXCALIDRAW-856
    """Write <basename>.svg from an existing .excalidraw scene file, beside it unless
    `out_dir` is given, and return its path. Raises ValueError, as `render_html`
    does, if the file is not a valid Excalidraw scene."""
    scene = load_scene(scene_path)
    base = os.path.splitext(os.path.basename(scene_path))[0]
    out_dir = out_dir or os.path.dirname(os.path.abspath(scene_path))
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, base + ".svg")
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(scene_svg(scene, base))
    return out_path
