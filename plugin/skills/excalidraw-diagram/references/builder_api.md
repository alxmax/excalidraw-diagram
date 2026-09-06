# Builder API — the full reference

The `Scene` API in `scripts/excalidraw_builder.py`, the two ways to import it, and
a complete first generator. `SKILL.md` states the rules; this file is what you
look things up in while writing one.

## Importing the builder

**Inside the plugin** (e.g. an `examples/` script): use a relative path.

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from excalidraw_builder import Scene
```

**In an external repo** (a generator script that lives in your own project,
not inside the plugin directory): use the dynamic resolver below. It scans
the plugin cache, picks the **highest installed semver**, and imports from
there. This survives any plugin update without ever needing to edit the script.

```python
import sys, os, glob, re

def _builder_path():
    cache = os.path.join(os.path.expanduser("~"), ".claude", "plugins",
                         "cache", "excalidraw-diagram", "excalidraw-diagram")
    hits = glob.glob(os.path.join(cache, "*", "skills",
                                  "excalidraw-diagram", "scripts"))
    if not hits:
        raise RuntimeError(
            "excalidraw-diagram skill not found — run: /plugin install excalidraw-diagram"
        )
    def _ver(p):
        m = re.search(r"(\d+)\.(\d+)\.(\d+)", p)
        return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)
    return max(hits, key=_ver)

sys.path.insert(0, _builder_path())
from excalidraw_builder import Scene
```

**Never hardcode a version number** (e.g. `1.32.0`) in the path — the plugin
cache keeps every version ever installed and the script will silently keep
using the old, limited API after any update.

## Minimal example

```python
import sys, os, glob, re

def _builder_path():
    cache = os.path.join(os.path.expanduser("~"), ".claude", "plugins",
                         "cache", "excalidraw-diagram", "excalidraw-diagram")
    hits = glob.glob(os.path.join(cache, "*", "skills",
                                  "excalidraw-diagram", "scripts"))
    if not hits:
        raise RuntimeError("excalidraw-diagram skill not found")
    def _ver(p):
        m = re.search(r"(\d+)\.(\d+)\.(\d+)", p)
        return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)
    return max(hits, key=_ver)

sys.path.insert(0, _builder_path())
from excalidraw_builder import Scene

s = Scene()                       # normal font, clean lines (the readable default)
# Scene(font="hand", sketch=True) # the classic hand-drawn whiteboard look instead
s.title("Auth flow", 40, -40, size=32)

a = s.box("Client",        40,  60, fill="grey")
b = s.box("API gateway",   40, 200, fill="blue")
c = s.box("Auth service",  40, 340, fill="violet")
d = s.diamond("Token\nvalid?", 320, 330, fill="orange")
ok  = s.box("200 OK",   560, 250, fill="green")
err = s.box("401",      560, 410, fill="red")

s.arrow(a, b, label="request")
s.arrow(b, c, label="verify")
s.arrow(c, d)
s.arrow(d, ok,  label="yes")
s.arrow(d, err, label="no", dashed=True)

s.save("auth_flow", out_dir="docs")   # -> docs/auth_flow.excalidraw + .html
```

## The `scene --from-json` description

`python scripts/excalidraw_builder.py scene --from-json graph.json -o out/` is the
short path: you say what the parts are and what connects to what, `pack()` works out
where everything goes, and the same gates judge the result. Nothing here carries a
coordinate. Every key maps to one `Scene` call, so the JSON can never drift away from
the API above.

```jsonc
{
  "name": "auth_flow",                 // output basename (default: the file's stem)
  "title": "Auth flow",                // -> title()
  "subtitle": "Left to right: ...",    // -> label(), one line, say the direction
  "direction": "LR",                   // "LR" = layers are columns, "TB" = rows
  "seed": 7,                           // byte-identical re-runs; set it if committed
  "roles": {"service": "blue"},        // colour = meaning
  "nodes": [
    {"id": "api", "label": "API gateway", "fill": "service", "kind": "process"}
  ],                                   // kind: any box()/ISO shape name
  "edges": [
    {"src": "api", "dst": "auth", "label": "verify", "dashed": false}
  ],
  "groups": [{"label": "the service", "members": ["api", "auth"]}],
  "legend": true,                      // -> legend() from `roles`
  "glossary": [["back edge", "an arrow returning to an earlier step"]]
}
```

`pack()` layers the graph by how deep each node sits, orders each layer to keep
connected nodes near each other, and then decides per edge: a straight arrow when its
line clears every other box, a routed connector otherwise. Feedback edges are always
routed, so a cycle never cuts back across the flow.

Call `s.pack(nodes, edges, direction=..., groups=...)` directly when you want the
auto-layout inside a generator that also draws things by hand.

## Every call, in one table

Full signatures and the file-format details are in
[`references/excalidraw_format.md`](references/excalidraw_format.md). The
essentials:

| Call | Draws |
| --- | --- |
| `Scene(font="normal", sketch=False, background="#ffffff", seed=None, roles=None)` | the canvas (`seed=<int>` → byte-stable file for git; `roles={name:colour}` → semantic fills). `font="hand", sketch=True` for the whiteboard look |
| `s.box(text, x, y, w=160, h=70, fill=…, shape=…, font_size=…, container=…)` | a labelled rectangle (→ node id) |
| `s.ellipse(text, x, y, w, h, …, container=…)` | a labelled ellipse |
| `s.diamond(text, x, y, w, h, …)` | a labelled decision diamond |
| `s.frame(x, y, w, h, dashed=False)` | a container drawn *behind* children (overlap-exempt) |
| **ISO 5807 flowchart shapes** (thin `box` aliases, sized for flowcharts) | |
| `s.process(text, x, y)` / `s.terminator(...)` / `s.decision(...)` | rectangle / stadium (start-end) / diamond |
| `s.data(...)` / `s.predefined_process(...)` / `s.preparation(...)` / `s.connector(...)` | parallelogram / framed box / hexagon / small circle |
| **Auto-layout & grouping** | |
| `s.row(items, x, y, gap=…, connect=…)` | place items left→right → list of ids (`connect=True` chains arrows) |
| `s.column(items, x, y, gap=…, connect=…)` | place items top→down → list of ids |
| `s.grid(items, x, y, cols, …)` | place items in a `cols`-wide grid → list of ids |
| `s.enclose(ids, label=…, pad=…)` | auto-sized frame *behind* those nodes → frame id |
| `s.lane(ids, label)` | a swimlane: solid frame around `ids` with a top-left header |
| `s.align(ids, axis)` / `s.distribute(ids, axis, gap=…)` | tidy already-placed nodes (`axis`: left/right/center_x/top/bottom/center_y; distribute `"x"`/`"y"`) |
| **Poster helpers** (for "how a repo works" diagrams) | |
| `s.section(title) → y` | stack a left-aligned heading *below all existing content*; returns the y to place this region's shapes (no manual `bounds()` math) |
| `s.pipeline(steps, x, y, gap=80, connect=True) → [ids]` | lay out a horizontal flowchart band and chain arrows. Each step is `"text"`, `(text, kind)`, `(text, kind, fill)`, or a dict; `kind` is any ISO shape verb; a step's `label` becomes its outgoing arrow label. **Recommended gap: ≥80px for labeled arrows, ≥100px for multi-word labels** (stderr warning if gap < 80 with labeled steps) |
| **Roles, captions, arrows** | |
| `s.role(name, colour)` / `Scene(roles={…})` | declare a semantic fill so `box(fill="agent")` works and `legend()` renders the key |
| `s.legend(entries=None, x, y, title=…)` | colour→meaning key (`entries=[(label, colour),…]`, or omit to use `roles`) — **required when colour encodes a role** |
| `s.glossary(entries, x, y, title=…)` | term→meaning key (`entries=[(term, meaning),…]`) — decode jargon/acronyms; overlap-checked |
| `s.title(text, x, y, size=28, align="left")` | a large free-standing heading |
| `s.label(text, x, y, size=12)` | a small grey caption (e.g. "ONE AGENT") |
| `s.arrow(src, dst, label=…, dashed=…, curve=…, start=…, end="arrow", gap=14)` | a bound arrow node→node |
| `s.free_arrow(p0, p1, …)` | an unbound arrow between two points |
| `s.path(points, label=…, dashed=…, end="arrow")` | an unbound multi-point connector through absolute `(x,y)` points (crossing-free routing) |
| `s.route_under(src, dst, drop=70, label=…, color="grey", dashed=True)` | a connector routed below the row (feedback / backward) |
| **Inspection & save** | |
| `s.bounds()` | `(min_x, min_y, max_x, max_y)` of all shapes — for stacking regions |
| `s.check_arrow_crossings()` | `[(src, dst, crossed), …]` arrows running through an unrelated box |
| `s.check_legend_coverage()` | `[fill, …]` colours used but absent from the `legend()` key (colour-SSOT); `[]` when clean |
| `s.check_text_overflow()` | `[(id, …), …]` boxes whose bound text spills outside the shape |
| `s.check_text_overlaps()` | `[(a, b), …]` captions/labels that overlap each other |
| `s.save(basename, out_dir=".", crossing_check=…, legend_check=…, overflow_check=…, text_overlap_check=…, label_fit_check=…)` | writes both files; **raises if shapes overlap**; each `*_check` is `"warn"` (default, prints) or `"error"` (raises). Use all five at `"error"` for a ship-quality diagram |

**Colours** accept a hex string or a palette name: `grey, red, orange, yellow,
green, teal, blue, indigo, violet, pink`. Each name maps to Excalidraw's own
stroke + light-fill pair, so diagrams look native.

**Auto-layout** — prefer `row`/`column`/`grid` over hand-computing coordinates;
they space evenly (so shapes never overlap) and return the ids in order. Each
`items` entry is a `"text"` string, a `(text, fill)` pair, or a full dict of
`box()` options. `enclose(ids, label=…)` then draws a correctly-sized frame
behind them — no manual frame math.

**Grouping pattern** (an "agent" that holds several voices/boxes): draw a
`frame()` or `ellipse(..., container=True)` first, place the inner `box()`es on
top at coordinates inside it, and add a `label()` caption above. Mark the wrapper
`container=True` (frames are automatic) so the overlap check ignores
wrapper-vs-child. Or let `enclose(ids, label=...)` auto-size a frame around
boxes you have already placed (see the `excalidraw_builder.py` smoke test).
