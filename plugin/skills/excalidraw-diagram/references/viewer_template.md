# The HTML viewer page

Write `<name>.html` as the page below with two substitutions, made once each and
nowhere else:

- `__TITLE__` (three places): the diagram's basename. Keep it plain: letters, digits,
  spaces, `-` and `_`. It lands in HTML text and in a download file name.
- `__SCENE__` (one place): the exact JSON you wrote to `<name>.excalidraw`, with every
  `</` replaced by `<\/`. JSON reads `<\/` as `</`, and the page cannot be cut short by
  a label that spells `</script>`.

The runtime is the official Excalidraw UMD build, `@excalidraw/excalidraw@0.17.6`, with
React and ReactDOM `18.2.0`, pinned to those exact versions on unpkg. 0.18 and later are
ESM-only and do not load through `<script>` tags, so do not "upgrade" them. The page needs
a network connection the first time it opens. If the CDN cannot be reached, it hides the
canvas and offers the embedded scene as a download.

```html
<!DOCTYPE html>
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
<script crossorigin
  src="https://unpkg.com/react@18.2.0/umd/react.production.min.js"></script>
<script crossorigin
  src="https://unpkg.com/react-dom@18.2.0/umd/react-dom.production.min.js"></script>
<script crossorigin
  src="https://unpkg.com/@excalidraw/excalidraw@0.17.6/dist/excalidraw.production.min.js"></script>
<script>
const SCENE = __SCENE__;
let api = null, saved = null, edited = false, touched = false;

function current(){
  const E = window.ExcalidrawLib;
  if (api && E && E.serializeAsJSON)
    return E.serializeAsJSON(api.getSceneElements(), api.getAppState(),
                             api.getFiles(), "local");
  return JSON.stringify(SCENE, null, 2);
}

function download(){
  const blob = new Blob([current()], {type:"application/json"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "__TITLE__.excalidraw";
  a.click();
  URL.revokeObjectURL(a.href);
  if (api) saved = window.ExcalidrawLib.getSceneVersion(api.getSceneElements());
  edited = false;
}
document.getElementById("dl").onclick = download;
document.getElementById("dl2").onclick = download;
window.addEventListener("beforeunload", function(ev){
  if (edited) { ev.preventDefault(); ev.returnValue = ""; }
});

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
      excalidrawAPI: function(a){ api = a; },
      onChange: function(elements){
        const v = E.getSceneVersion(elements);
        if (!touched) saved = v;
        edited = v !== saved;
      },
      UIOptions: { canvasActions: { loadScene: false } }
    }));
    setTimeout(function(){
      if (api) api.scrollToContent(api.getSceneElements(),
                                   {fitToViewport: true, viewportZoomFactor: 0.92});
    }, 600);
    for (const ev of ["pointerdown", "keydown"])
      document.getElementById("app").addEventListener(ev, function(){ touched = true; }, true);
  } catch (err) {
    console.error(err);
    document.getElementById("app").style.display = "none";
    document.getElementById("fallback").style.display = "block";
  }
});
</script>
</body>
</html>
```

Why the page tracks `edited`: it is an editor, so the download hands back the scene as it
stands now. Loading the fonts re-measures every label and bumps the scene version with no
edit made, so the baseline follows the scene until the reader first touches the canvas.
