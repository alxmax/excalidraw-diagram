# Builder API — the full reference

The `Scene` API behind `scripts/excalidraw_builder.py`, the two ways to import it,
the value objects every call shares, and every signature. `SKILL.md` states the
rules; this file is what you look things up in while writing a generator.

## Importing the builder

**Inside the plugin** (e.g. an `examples/` script): use a relative path.

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from excalidraw_builder import Font, Gates, Paint, Scene
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
from excalidraw_builder import Font, Gates, Paint, Scene
```

**Never hardcode a version number** (e.g. `1.32.0`) in the path — the plugin
cache keeps every version ever installed and the script will silently keep
using an old API after any update. The resolver picks the newest, so a script
written for 1.x stops running once 2.x is installed: migrate it with the table
at the end of this file.

## Minimal example

```python
from excalidraw_builder import DASHED, Gates, Scene   # imported as shown above

s = Scene(seed=7)                 # normal font, clean lines (the readable default)
# Scene(typeface="hand", sketch=True) for the classic whiteboard look instead
s.title("Auth flow", (40, -40), font=32)

a = s.box("Client",       (40, 60),  paint="grey")
b = s.box("API gateway",  (40, 240), paint="blue")
c = s.box("Auth service", (40, 420), paint="violet")
d = s.diamond("Token\nvalid?", (360, 410), paint="orange")
ok = s.box("200 OK", (680, 300), paint="green")
err = s.box("401",   (680, 520), paint="red")

s.arrow(a, b, label="request")
s.arrow(b, c, label="verify")
s.arrow(c, d)
s.arrow(d, ok, label="yes")
s.arrow(d, err, label="no", paint=DASHED)

s.save("auth_flow", out_dir="docs", gates=Gates.strict())
```

## The three values every call takes

**`at` — where it goes.** One value, never separate x/y/w/h arguments:

| You pass | It means |
| --- | --- |
| `(x, y)` | the top-left point; a shape call sizes it by the shape's default |
| `(x, y, w, h)` | the exact box |
| `Rect(x, y, w, h)` | the same, as an object (`.right`, `.bottom`, `.cx`, `.cy`) |

`s.rect(node_id)` hands back the `Rect` a placed node occupies, so the next shape
can be positioned from it (`s.rect(clear).y`).

**`paint` — how it is coloured.** `Paint(fill=None, stroke=None, dashed=False,
group=None)`. A bare string is the element's *natural* colour: a shape's fill, a
connector's stroke. So `paint="blue"` on a box and `paint="red"` on an arrow both
do the obvious thing. `DASHED` is `Paint(dashed=True)`. A colour is a palette
name, a hex string, or a role declared with `Scene(roles=…)`.

**`font` — how its text is set.** `Font(size=None, color=None, align=None)`. A bare
number is a size. A field left `None` keeps the calling method's own default, so
`label(..., font=14)` stays grey and centred, `title(..., font=Font(align="center"))`
keeps title size.

## The `scene --from-json` description

`python scripts/excalidraw_builder.py scene --from-json graph.json -o out/` is the
short path: you say what the parts are and what connects to what, `pack()` works out
where everything goes, and the same gates judge the result. Nothing here carries a
coordinate. Every key maps to one `Scene` call, so the JSON can never drift away from
the API above. The MCP tool `build_scene` takes the same object as its `graph`.

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
  ],                                   // kind: any box() shape name
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

Call `s.pack(nodes, edges, groups=…, options=PackOptions(direction="TB"))` directly
when you want the auto-layout inside a generator that also draws things by hand.
`scene_from_spec(spec, out_dir, name=None)` builds a description already in memory.

## Every call

| Call | Draws / returns |
| --- | --- |
| `Scene(typeface="normal", sketch=False, background="#ffffff", seed=None, roles=None)` | the canvas. `typeface`: normal, hand or code. `seed=<int>` → byte-stable file for git |
| **Shapes** — each returns a node id | |
| `s.box(text, at, paint=…, font=…, shape="rectangle", container=False)` | a labelled shape; `container=True` exempts a wrapper from the overlap gate |
| `s.ellipse(text, at, …)` / `s.diamond(text, at, …)` | the same with that shape |
| `s.process` / `terminator` / `decision` / `data` / `predefined_process` / `preparation` / `connector` `(text, at, …)` | ISO 5807: rectangle / stadium / diamond / parallelogram / framed box / hexagon / small circle, each with its own default size |
| `s.frame(at, paint=…)` | a rounded container drawn *behind* everything so far (`at` is `(x, y, w, h)`) |
| **Placing several** — each returns the ids in order | |
| `s.arrange(items, at, across="x", cell=None, gap=None, connect=False)` | `across`: `"x"` a row, `"y"` a column, an int a grid of that many columns. Default gap 80 / 60 / `(40, 30)` |
| `s.row(items, at, …)` / `s.column(items, at, …)` / `s.grid(items, at, cols, …)` | `arrange()` with `across` filled in |
| `s.pipeline(steps, at, gap=80, band=None, font=…, connect=True)` | a horizontal flowchart band on one midline, chained with arrows |
| `s.enclose(ids, label=None, pad=24, paint=None, caption=None)` | a frame sized around placed nodes — dashed unless `paint` is given; the caption goes where no arrow already drawn crosses it, so draw the arrows first → frame id |
| `s.lane(ids, label, pad=24, paint=None, caption=None)` | a solid frame with a top-left header, one per actor or tool → frame id |
| `s.align(ids, axis)` / `s.distribute(ids, axis, gap=40)` | move placed nodes (and their labels); `axis`: left/right/center_x/top/bottom/center_y, or `"x"`/`"y"` |
| **Text and keys** | |
| `s.title(text, at, font=…)` | a heading: 28px, left-aligned on `at` |
| `s.label(text, at, font=…)` | a caption: 12px, grey, centred on `at` |
| `s.section(heading, x=40, gap=70, font=…) → y` | a heading below *all* content so far; returns the y for this region's shapes |
| `s.role(name, colour)` | declare a semantic colour so `paint="agent"` works and `legend()` can list it |
| `s.legend(entries=None, at=(0, 0), title="Legend", font=…)` | colour → meaning key; `entries=[(label, colour), …]` or omit for the roles |
| `s.glossary(entries, at, title="Glossary", font=…)` | term → meaning key; overlap-checked like a box |
| **Connectors** — each returns its id | |
| `s.arrow(src, dst, label=None, paint=…, heads="end", curve=False)` | a bound arrow node → node; `heads`: end, start, both, none |
| `s.path(points, label=None, paint=…, heads="end")` | an unbound connector through absolute `(x, y)` points; its label gets an overlap-checked knock-out panel |
| `s.free_arrow(p0, p1, …)` | `path()` with two points |
| `s.route_under(src, dst, drop=70, label=None, paint=…)` | a dashed grey feedback connector below the row |
| **Graph layout** | |
| `s.pack(nodes, edges=(), groups=(), at=(40, 0), options=None) → {id: node id}` | the coordinate-free layout; `PackOptions(direction, gap_major, gap_minor, lane_gap, font_size)` |
| **Inspection and save** | |
| `s.bounds()` / `s.rect(node_id)` | `(min_x, min_y, max_x, max_y)` of everything / one node's `Rect` |
| `s.check_overlaps()` `check_arrow_crossings()` `check_legend_coverage()` `check_text_overflow()` `check_text_overlaps()` `check_short_arrows()` `check_arrow_label_fit()` | the seven checks, each a list of offenders, `[]` when clean. `check_overlaps()` also names a box inside an `enclose()` frame that was not enclosed; `check_arrow_crossings()` also names an arrow through a frame caption |
| `s.save(basename, out_dir=".", gates=None, offline=None) → (excalidraw, html)` | runs the gates and writes both files, once |
| `fit_text(text, size=14, max_chars=20, min_size=(120, 48)) → (wrapped, w, h)` | wrap a label and size a box that will not overflow |

**Gates.** `Gates(advisory="warn", hard="error", **per_gate)` sets each gate to
`"error"` (raise), `"warn"` (print to stderr) or `"off"`. The hard gates are
`overlap` and `short_arrows`; the advisory ones `crossing`, `legend`, `overflow`,
`text_overlap`, `label_fit`. `Gates.strict()` puts all seven at `"error"` — ship with
it. `Gates(overlap="off")` is how a deliberately overlapping demo gets written.

**The viewer's renderer.** `save()` and `render_html()` inline the vendored Excalidraw
build into the `.html`, so the page opens with no network at all: about 1.6 MB, zero
requests, fonts included. `offline=False` (the CLI's `--cdn`) writes the ~100 KB page
that loads the same pinned build from unpkg — smaller, but it needs a connection and it
tells unpkg who is opening it. `EXCALIDRAW_DIAGRAM_OFFLINE=0` flips the default for a
whole run. The lazily imported `vendor-*.js` chunk is deliberately not vendored, so the
Mermaid-to-Excalidraw dialog is the one thing an offline page cannot open.

**Items.** An `arrange()` item is `"text"`, a `(text, paint)` pair, or a dict with
`box()`'s option names: `text`, `size` (a `(w, h)` pair), `paint`, `font`, `shape`,
`container`. `cell=` takes the same dict as the default every item overrides. A
pipeline step is `"text"`, `(text, kind[, paint])`, or `{text, kind, paint, size,
label, font}`, where a step's `label` names the arrow leaving it. An unknown key
raises `ValueError` rather than being ignored.

**Colours** are a hex string or a palette name: `grey, red, orange, yellow, green,
teal, blue, indigo, violet, pink` (+ `black`, `transparent`). Each name maps to
Excalidraw's own stroke + light-fill pair, so diagrams look native.

**Grouping pattern** (an "agent" that holds several boxes): draw a `frame()` or an
`ellipse(..., container=True)` first, place the inner boxes on top, and add a
`label()` caption above. Or let `enclose(ids, label=…)` size a frame around boxes
you have already placed.

## MCP tools

`scripts/mcp_server.py` (registered by the plugin's `.mcp.json`) offers the entry
points to an MCP client over stdio: `build_scene(graph, out_dir, name?)`,
`render_html(scene_path, out_dir?)`, `discover_repo(repo, out_path?)`, and
`graph_schema()`, which returns the `jsonc` block above. A failed gate comes back as
a tool error carrying the gate's message.

## Migrating a 1.x generator

| 1.x | 2.x |
| --- | --- |
| `s.box(t, x, y, w=…, h=…, fill=…, font_size=…)` | `s.box(t, (x, y, w, h), paint=…, font=…)` |
| `stroke=`, `dashed=`, `color=`, `group=` | `paint=Paint(stroke=…, dashed=…, group=…)` |
| `s.title(t, x, y, size=…, color=…, align=…)` | `s.title(t, (x, y), font=Font(size, color, align))` |
| `s.row(items, x, y, w=…, h=…, fill=…, font_size=…)` | `s.row(items, (x, y), cell={"size": (w, h), "paint": …, "font": …})` |
| `s.grid(…, gap_x=…, gap_y=…)` | `s.grid(…, gap=(gx, gy))` |
| item / step keys `fill`, `w`, `h`, `font_size` | `paint`, `size`, `font` |
| `s.arrow(a, b, start="arrow", end="arrow")` | `s.arrow(a, b, heads="both")` |
| `s.legend(x=…, y=…)` / `s.glossary(e, x, y)` | `s.legend(at=(x, y))` / `s.glossary(e, (x, y))` |
| `s.pack(n, e, direction="TB", x=…, y=…)` | `s.pack(n, e, at=(x, y), options=PackOptions(direction="TB"))` |
| `save(…, crossing_check="error", …)` | `save(…, gates=Gates(crossing="error"))`, or `Gates.strict()` |
| `save(…, allow_overlap=True)` | `save(…, gates=Gates(overlap="off"))` |
| `Scene(font="hand")` / `Scene(hand_drawn=True)` | `Scene(typeface="hand", sketch=True)` |
| `Scene.fit_text(t, font=…, min_w=…, min_h=…)` | `fit_text(t, size=…, min_size=(w, h))` |
| `s._geom[node][1]` | `s.rect(node).y` |

The graph JSON (`scene --from-json`) did not change.
