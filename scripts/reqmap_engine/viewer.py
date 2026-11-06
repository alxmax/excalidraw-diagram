"""_map.html: the vendored single-file viewer."""
import os

from . import ENGINE_DIR
from .mapjson import _build_json_text


# A pre-built, single-file React viewer ships next to this engine as
# `_map_viewer.html`. It carries the marker `<!--REQMAP_DATA-->`; the
# engine swaps that for a <script> assigning this repo's graph to
# window.__REQMAP_DATA__, producing a self-contained `_map.html` that
# opens by double-click (no server).
VIEWER_TEMPLATE = "_map_viewer.html"
_REQMAP_DATA_MARKER = "<!--REQMAP_DATA-->"


def _viewer_template_path():
    # implements: ARCH-VIEWERFILE-074  # implements: REQ-VIEWER-940
    return os.path.join(ENGINE_DIR, VIEWER_TEMPLATE)


def _inject_viewer(template_text, data):
    # implements: ARCH-VIEWERFILE-074  # implements: REQ-VIEWER-941
    """Replace the data marker with an inline <script> assigning the graph to
    window.__REQMAP_DATA__. Three sequences are escaped so the HTML5 parser
    never changes state mid-blob:
      `</`   → `<\\/`  prevents `</script>` from closing the element early
      `<!--` → `<\\!--` prevents entering "script data escaped" state
      `-->`  → `-\\->`  closes "script data escaped" state
      prematurely if unclosed
    All three are valid JS string escapes (backslash ignored for `/`,
    `!`, `-`)."""
    blob = (
        _build_json_text(data, compact=True, stamped=True)
        .replace("</", "<\\/")
        .replace("<!--", "<\\!--")
        .replace("-->", "-\\->")
        # U+2028/U+2029 are LINE TERMINATORS in JavaScript but ordinary
        # characters in JSON, so ensure_ascii=False emits them raw and
        # any engine older than ES2019 reads the blob as an
        # unterminated string - one character in one requirement title
        # kills the whole viewer. The escaped forms are valid JSON for
        # the same characters, so the parsed value is unchanged.
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
    script = "<script>window.__REQMAP_DATA__=" + blob + ";</script>"
    return template_text.replace(_REQMAP_DATA_MARKER, script, 1)


def render_html(data, reqs_dir):
    # implements: ARCH-VIEWERFILE-074  # implements: REQ-VIEWER-940
    """Write the self-contained viewer `_map.html` by injecting `data` into the
    vendored template. Returns the path, or None when no template is present
    (the engine still emits _map.md + _map.json — the viewer is optional)."""
    tpl = _viewer_template_path()
    if not os.path.exists(tpl):
        return None
    with open(tpl, encoding="utf-8") as f:
        template_text = f.read()
    out = os.path.join(reqs_dir, "_map.html")
    os.makedirs(reqs_dir, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(_inject_viewer(template_text, data))
    return out
