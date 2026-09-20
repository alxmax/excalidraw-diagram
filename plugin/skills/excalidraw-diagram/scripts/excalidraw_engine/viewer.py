"""The self-contained HTML viewer: the scene embedded in a page that renders it
with the official Excalidraw component, and the verb that rebuilds that page from an
existing .excalidraw file.

The page carries its renderer by default — the vendored runtime from `assets.py` is
inlined, so it opens with no network at all. `offline=False` links the unpkg CDN
instead, which keeps the page around 100 KB but needs a connection on first open."""

import json
import os
import re
import sys

from . import assets

# The viewer page. It is a template, not logic: keeping it as a module constant
# leaves `html_page` as the one substitution step it performs, and puts the markup
# where a reader looks for markup. `__RUNTIME__` is the whole renderer — inlined
# scripts and fonts, or CDN script tags — so the two modes differ in one block.
_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>__TITLE__ — Excalidraw</title>
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

__RUNTIME__
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
    if (!E || !window.React || !window.ReactDOM) throw new Error("runtime not loaded");
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


_CDN_RUNTIME = """<script>window.EXCALIDRAW_ASSET_PATH = "__CDN__";</script>
<script crossorigin
  src="https://unpkg.com/react@18.2.0/umd/react.production.min.js"></script>
<script crossorigin
  src="https://unpkg.com/react-dom@18.2.0/umd/react-dom.production.min.js"></script>
<script crossorigin src="__CDN__excalidraw.production.min.js"></script>"""


def _offline_default():
    """Offline unless the environment opts out with EXCALIDRAW_DIAGRAM_OFFLINE=0 —
    the escape hatch for a job that wants 100 KB pages and has a network anyway."""
    return os.environ.get("EXCALIDRAW_DIAGRAM_OFFLINE", "1").lower() \
        not in ("0", "false", "no")


def _runtime(offline):
    """The renderer block: the vendored scripts and fonts inlined, or CDN tags."""
    if not offline:
        return _CDN_RUNTIME.replace("__CDN__", assets.CDN)
    # "./" and not "": the bundle reads `window.EXCALIDRAW_ASSET_PATH || <unpkg>`, so
    # an empty string is falsy and would send the page to unpkg for the fonts and the
    # lazy chunk — the one thing an offline page must not do. A relative path resolves
    # beside the file, finds nothing, and asks no one. The font rules that follow the
    # bundle's own supply the faces it would have fetched.
    block = ['<script>window.EXCALIDRAW_ASSET_PATH = "./";</script>']
    block += ["<script>%s</script>" % s for s in assets.scripts()]
    block.append("<style>%s</style>" % assets.font_faces())
    return "\n".join(block)


def html_page(title, scene, offline=None):
    # implements: REQ-EXCALIDRAW-854
    """The scene rendered into the standalone viewer page. `offline` defaults to the
    environment's answer (on), inlining the vendored runtime so the page opens with no
    network; `offline=False` links the CDN instead. A missing vendored runtime warns
    and falls back to the CDN rather than writing a page that renders nothing."""
    if offline is None:
        offline = _offline_default()
    if offline and not assets.available():
        print("WARNING [viewer]: the vendored Excalidraw runtime is incomplete — "
              "writing a CDN viewer, which needs a network connection on first open.",
              file=sys.stderr)
        offline = False
    parts = {"TITLE": title, "SCENE": json.dumps(scene), "RUNTIME": _runtime(offline)}
    # One pass, so a placeholder occurring inside a substituted value (a scene that
    # spells __RUNTIME__ in a label, say) is left alone instead of being expanded.
    return re.sub(r"__(TITLE|SCENE|RUNTIME)__", lambda m: parts[m.group(1)],
                  _HTML_TEMPLATE)


def render_html(scene_path, out_dir=None, offline=None):
    # implements: REQ-EXCALIDRAW-848
    """Regenerate the self-contained .html viewer from an existing .excalidraw
    scene file — e.g. one edited on excalidraw.com, for which there is no
    generator script to re-run. Writes <basename>.html beside the scene unless
    out_dir is given; `offline` is `html_page`'s, so the page carries its renderer
    unless told otherwise. Returns the .html path. Raises ValueError if the file is
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
        f.write(html_page(base, scene, offline))
    return out_path
