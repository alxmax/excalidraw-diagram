"""The vendored Excalidraw runtime the offline viewer inlines.

`runtime/` beside this module holds the scripts and fonts, copied verbatim from the
pinned npm builds (its README records the sources). Reading them is all this module
does: it never downloads, so a diagram is still produced by a Python interpreter and
nothing else. The bytes become `<script>` and `@font-face` text in `viewer.py`.
"""

import base64
import functools
import os

VERSION = "0.17.6"                     # the pinned @excalidraw/excalidraw build
CDN = "https://unpkg.com/@excalidraw/excalidraw@" + VERSION + "/dist/"

_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runtime")

# Load order matters: React first, then the UMD bundle that expects it on `window`.
SCRIPTS = ("react.production.min.js", "react-dom.production.min.js",
           "excalidraw.production.min.js")
# Excalidraw resolves these through `window.EXCALIDRAW_ASSET_PATH`, which the offline
# page blanks out; the inlined @font-face rules below take their place.
FONTS = ("Virgil.woff2", "Cascadia.woff2", "Assistant-Regular.woff2",
         "Assistant-Medium.woff2", "Assistant-SemiBold.woff2", "Assistant-Bold.woff2")
_WEIGHTS = {"Regular": 400, "Medium": 500, "SemiBold": 600, "Bold": 700}


def available():
    # implements: REQ-EXCALIDRAW-854
    """Whether the whole vendored runtime is present and non-empty. False means the
    viewer falls back to the CDN rather than emitting a page that renders nothing."""
    return all(os.path.getsize(os.path.join(_DIR, n)) > 0
               if os.path.exists(os.path.join(_DIR, n)) else False
               for n in SCRIPTS + FONTS)


@functools.lru_cache(maxsize=1)
def scripts():
    """The runtime scripts, in load order, as inlinable JavaScript text. `</script>`
    is escaped: the sequence would close the tag the text is written into. Cached:
    1.3 MB re-read on every save() is a cost the caller never asked for."""
    out = []
    for name in SCRIPTS:
        with open(os.path.join(_DIR, name), encoding="utf-8") as f:
            out.append(f.read().replace("</script>", "<\\/script>"))
    return tuple(out)


@functools.lru_cache(maxsize=1)
def font_faces():
    """The `@font-face` rules for the vendored fonts, each carrying its woff2 as a
    data URI. Declared after Excalidraw's own rules so these win the match."""
    rules = []
    for name in FONTS:
        with open(os.path.join(_DIR, name), "rb") as f:
            payload = base64.b64encode(f.read()).decode("ascii")
        family, _, weight = name[:-len(".woff2")].partition("-")
        rule = ('@font-face{font-family:"%s";'
                'src:url(data:font/woff2;base64,%s) format("woff2");' % (family, payload))
        if weight:
            rule += "font-weight:%d;" % _WEIGHTS[weight]
        rules.append(rule + "font-display:swap}")
    return "".join(rules)
