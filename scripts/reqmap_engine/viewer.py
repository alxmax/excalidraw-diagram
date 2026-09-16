"""_map.html: the vendored single-file viewer, and the viewer fixture sync check."""
import os, re

from . import ENGINE_DIR
from .mapjson import _build_json_text


_VDS_STRING_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')
_VDS_ID_CONTRACT_START_RE = re.compile(r'id:"([A-Z][A-Z0-9-]+)"[^{}]*?contract:\[')
# An entry the fixture INVENTS: the viewer's demo dataset carries a fake orphan and a
# fake deprecated capability so the Risk and Problems tabs have something to show with
# no engine present. Those ids cannot exist in any registry, so comparing them against
# one reported permanent drift - the check crying wolf about data that is doing its job.
# Marked entries are skipped; an UNMARKED id missing from the registry still reports,
# because that is the real signal (a requirement renamed out from under the fixture).
_VDS_DEMO_ONLY_RE = re.compile(r'demoOnly\s*:\s*true')


def _vds_normalize(strings):
    return sorted(" ".join(s.split()) for s in strings)


def _vds_scan_array_body(text, start):
    """From text[start] (the char right after the '[' that opens a JS array),
    return the array's raw source text up to its matching ']' — tracking
    quoted-string state so a stray ']'/'[' INSIDE a contract bullet's own text
    (e.g. a bullet describing `[a, b]` syntax) doesn't end the scan early.
    Returns None if the array never closes before EOF."""
    depth, in_string, i = 1, False, start
    while i < len(text):
        c = text[i]
        if in_string:
            if c == "\\":
                i += 2
                continue
            if c == '"':
                in_string = False
            i += 1
            continue
        if c == '"':
            in_string = True
            i += 1
            continue
        if c == "[":
            depth += 1
            i += 1
            continue
        if c == "]":
            depth -= 1
            if depth == 0:
                return text[start:i]
            i += 1
            continue
        i += 1
    return None


def _vds_parse_baked(text):
    """{id: [contract strings]} from data.js's BAKED array, minus `demoOnly:true` entries."""
    out = {}
    for m in _VDS_ID_CONTRACT_START_RE.finditer(text):
        if _VDS_DEMO_ONLY_RE.search(m.group(0)):
            continue                      # invented demo state — no registry counterpart
        block = _vds_scan_array_body(text, m.end())
        if block is None:
            continue
        out[m.group(1)] = [s.replace('\\"', '"') for s in _VDS_STRING_RE.findall(block)]
    return out


def check_viewer_data_sync(data_js_path, map_nodes):  # implements: ARCH-VIEWER-007
    """Compare app/src/lib/data.js's hand-authored BAKED requirement fixture
    against the live registry (map_nodes: [{"id":..., "contract":[...]}, ...]).
    Returns a sorted list of requirement IDs where the two disagree — a baked id
    missing from the live registry, or a whitespace-normalized mismatch in its
    `contract` bullets. A warn-only heuristic (not a byte-exact diff): it locates
    each BAKED entry's `contract:[...]` array via bracket-depth + quoted-string
    tracking (a naive non-greedy regex stops at the FIRST ']', which truncates
    any bullet whose own text contains a bracket — this repo's actual contracts
    do, e.g. describing `[a, b]` syntax, so that naive form is not just imprecise
    but wrong on real data). Returns None (not []) when data_js_path doesn't
    exist OR can't be decoded as UTF-8 — fail-open, matching load_ignore()'s
    convention for an optional file."""
    try:
        with open(data_js_path, encoding="utf-8") as f:
            text = f.read()
    except (OSError, ValueError):   # ValueError covers UnicodeDecodeError
        return None
    baked = _vds_parse_baked(text)
    live = {n["id"]: n.get("contract", []) for n in map_nodes}
    drift = [rid for rid, contract in baked.items()
             if rid not in live or _vds_normalize(contract) != _vds_normalize(live[rid])]
    return sorted(drift)


# A pre-built, single-file React viewer ships next to this engine as
# `_map_viewer.html`. It carries the marker `<!--REQMAP_DATA-->`; the engine
# swaps that for a <script> assigning this repo's graph to window.__REQMAP_DATA__,
# producing a self-contained `_map.html` that opens by double-click (no server).
VIEWER_TEMPLATE = "_map_viewer.html"
_REQMAP_DATA_MARKER = "<!--REQMAP_DATA-->"


def _viewer_template_path():  # implements: ARCH-VIEWER-007  # implements: REQ-VIEWER-940
    return os.path.join(ENGINE_DIR, VIEWER_TEMPLATE)


def _inject_viewer(template_text, data):
    # implements: ARCH-VIEWER-007  # implements: REQ-VIEWER-941
    """Replace the data marker with an inline <script> assigning the graph to
    window.__REQMAP_DATA__. Three sequences are escaped so the HTML5 parser
    never changes state mid-blob:
      `</`   → `<\\/`  prevents `</script>` from closing the element early
      `<!--` → `<\\!--` prevents entering "script data escaped" state
      `-->`  → `-\\->`  closes "script data escaped" state prematurely if unclosed
    All three are valid JS string escapes (backslash ignored for `/`, `!`, `-`)."""
    blob = (
        _build_json_text(data)
        .replace("</", "<\\/")
        .replace("<!--", "<\\!--")
        .replace("-->", "-\\->")
        # U+2028/U+2029 are LINE TERMINATORS in JavaScript but ordinary characters
        # in JSON, so ensure_ascii=False emits them raw and any engine older than
        # ES2019 reads the blob as an unterminated string - one character in one
        # requirement title kills the whole viewer. The escaped forms are valid JSON
        # for the same characters, so the parsed value is unchanged.
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
    script = "<script>window.__REQMAP_DATA__=" + blob + ";</script>"
    return template_text.replace(_REQMAP_DATA_MARKER, script, 1)


def render_html(data, reqs_dir):  # implements: ARCH-VIEWER-007  # implements: REQ-VIEWER-940
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
