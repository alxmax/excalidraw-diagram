"""The self-contained HTML viewer: the scene embedded in a page that renders it
with the official Excalidraw component, and the verb that rebuilds that page from an
existing .excalidraw file."""

import json
import os

# The viewer page. It is a template, not logic: keeping it as a module constant
# leaves `html_page` as the one substitution step it performs, and puts the markup
# where a reader looks for markup. The pinned Excalidraw root is substituted in, so
# a version bump is one edit and no template line runs past the width limit.
_EXCALIDRAW_CDN = "https://unpkg.com/@excalidraw/excalidraw@0.17.6/dist/"
_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>__TITLE__ — Excalidraw</title>
<link rel="stylesheet"
  href="__EXCALIDRAW__excalidraw.production.min.css" />
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

<script>window.EXCALIDRAW_ASSET_PATH = "__EXCALIDRAW__";</script>
<script crossorigin
  src="https://unpkg.com/react@18.2.0/umd/react.production.min.js"></script>
<script crossorigin
  src="https://unpkg.com/react-dom@18.2.0/umd/react-dom.production.min.js"></script>
<script crossorigin src="__EXCALIDRAW__excalidraw.production.min.js"></script>
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


def html_page(title, scene):
    """The scene rendered into the standalone viewer page."""
    return (_HTML_TEMPLATE.replace("__EXCALIDRAW__", _EXCALIDRAW_CDN)
                          .replace("__SCENE__", json.dumps(scene))
                          .replace("__TITLE__", title))


def render_html(scene_path, out_dir=None):
    # implements: REQ-EXCALIDRAW-848
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
        f.write(html_page(base, scene))
    return out_path
