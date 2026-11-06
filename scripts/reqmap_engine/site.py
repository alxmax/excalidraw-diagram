"""The project site: engine-owned regions injected into a presentation page.

`sync` refreshes the `nav` and `stats` regions of `docs/architecture.html`;
`init` scaffolds that page (plus a Pages signal) when it does not exist yet.
Everything outside the paired markers is authored prose and is never touched.
"""
import os, re

from . import MAP_ENGINE_VERSION
from .git import _git_remote_web_url, _repo_name
from .mapdata import _build_map_data
from .site_template import SITE_TEMPLATE


# implements: ARCH-SITE-026
SITE_REGIONS = ("nav", "stats")


def _region_markers(name):  # implements: ARCH-SITE-026
    key = name.upper()
    return ("<!--##REQMAP:{}##-->".format(key),
            "<!--##/REQMAP:{}##-->".format(key))


def _inject_region(html, name, inner, anchor="<body>"):
    # implements: ARCH-SITE-026  # implements: REQ-SITE-924
    """Replace the content between the paired markers for `name` with `inner`
    (idempotent). Markers absent -> insert a fresh marked block right after the
    first `anchor`; anchor absent too -> append. Only the marked block is
    written; surrounding (authored) bytes are untouched."""
    open_m, close_m = _region_markers(name)
    block = open_m + "\n" + inner + "\n" + close_m
    # the close that belongs to THIS open (searched after it): a stray close
    # before the open would otherwise append a duplicate block on every re-run
    i = html.find(open_m)
    j = html.find(close_m, i + len(open_m)) if i != -1 else -1
    if i != -1 and j != -1:
        return html[:i] + block + html[j + len(close_m):]
    # `<body class="...">` is still the body tag: a literal find appended the
    # block after `</html>` on any page whose body carries attributes
    m = None
    if anchor == "<body>":
        m = re.search(r"<body\b[^>]*>", html, re.I)
    a = m.end() if m else html.find(anchor)
    if a != -1:
        a += 0 if m else len(anchor)
        return html[:a] + "\n" + block + html[a:]
    return html + "\n" + block


def _extract_region(html, name):  # implements: ARCH-SITE-026
    """Inner text between the paired markers for `name`, or None when absent.
    Lets the freshness check diff only engine-owned regions."""
    open_m, close_m = _region_markers(name)
    i = html.find(open_m)
    if i == -1:
        return None
    i += len(open_m)
    j = html.find(close_m, i)
    return html[i:j].strip("\n") if j != -1 else None


def _html_escape(s):  # implements: ARCH-SITE-026
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _site_context_from_data(data, repo_url, map_ok):
    # implements: ARCH-SITE-026
    """Deterministic region inputs from the map graph plus already-resolved
    link facts. No clock and no filesystem here, so a re-run with no change
    reproduces byte-identically."""
    nodes = data.get("nodes", [])
    return {
        "repo_url": repo_url,
        "map_ok": map_ok,
        "counts": {
            "requirements": len(nodes),
            "confirmed": sum(1 for n in nodes
                             if n.get("status") == "confirmed"),
            "layers": len({n.get("layer", "feature") for n in nodes}),
            "edges": len(data.get("edges", [])),
        },
    }


_LINK = '<a href="{}" target="_blank" rel="noopener">{} ↗</a>'


def _render_region(name, ctx):
    # implements: ARCH-SITE-026  # implements: REQ-SITE-924
    """Inner HTML for an engine-owned region. NAV: one link per target that
    resolves (Live Map when a sibling map.html exists, GitHub when a remote
    resolves). STATS: stat cards from the graph counts + engine version."""
    if name == "nav":
        links = []
        if ctx.get("map_ok"):
            links.append(_LINK.format("map.html", "Live Map"))
        if ctx.get("repo_url"):
            links.append(_LINK.format(_html_escape(ctx["repo_url"]),
                                      "GitHub"))
        return '<nav class="nav-links">' + "".join(links) + '</nav>'
    if name == "stats":
        c = ctx["counts"]
        cells = [("requirements", c["requirements"]),
                 ("confirmed", c["confirmed"]), ("layers", c["layers"]),
                 ("edges", c["edges"]), ("engine", MAP_ENGINE_VERSION)]
        cell = '<div class="stat"><b>{}</b><span>{}</span></div>'
        return "".join(cell.format(v, k) for k, v in cells)
    return ""


_INDEX_REDIRECT = (
    '<!doctype html><meta charset="utf-8">'
    '<meta http-equiv="refresh" content="0; url=./architecture.html">'
    '<link rel="canonical" href="./architecture.html">'
    '<title>Project site</title>'
    '<p>Redirecting to <a href="./architecture.html">the project site</a>'
    '…</p>\n')


def _site_pages_bootstrap(docs_dir):
    # implements: ARCH-SITE-026  # implements: REQ-SITE-924
    """Give docs/ a GitHub Pages signal so the page is servable: write
    .nojekyll and an index.html redirect when absent. Idempotent: an existing
    index.html (a hand-written landing page) is never overwritten."""
    os.makedirs(docs_dir, exist_ok=True)
    nojekyll = os.path.join(docs_dir, ".nojekyll")
    if not os.path.exists(nojekyll):
        open(nojekyll, "w").close()
    index = os.path.join(docs_dir, "index.html")
    if not os.path.exists(index):
        with open(index, "w", encoding="utf-8") as f:
            f.write(_INDEX_REDIRECT)


def _site_default_target(root):  # implements: ARCH-SITE-026
    """docs/architecture.html under the scanned root (`--code`), or None when
    there is no docs/ there. Not the git root: a demo or fixture repo nested
    inside another would otherwise read and rewrite the outer repo's page.

    The site page is the one file the engine writes into docs/: the rendered
    map is built where it is published (ADR-0034), never copied here."""
    docs = os.path.join(root, "docs")
    if not os.path.isdir(docs):
        return None
    return os.path.join(docs, "architecture.html")


def site_stale(data, root="."):
    # implements: ARCH-SITE-026  # implements: REQ-SITE-924
    """The site page's file name when its on-disk `stats` region differs from
    a fresh render, else None. NAV is exempt (it embeds the fork-specific
    repo URL), and so is the `engine` cell (it moves on every engine bump). A
    page that is absent or carries no `stats` region is never stale."""
    target = _site_default_target(root)
    if not target or not os.path.isfile(target):
        return None
    try:
        with open(target, encoding="utf-8") as f:
            on_disk = _extract_region(f.read(), "stats")
    except (OSError, UnicodeDecodeError):
        return None
    if on_disk is None:
        return None
    ctx = _site_context_from_data(data, repo_url=None, map_ok=False)
    fresh = _render_region("stats", ctx)
    if _strip_engine_stat(on_disk) == _strip_engine_stat(fresh):
        return None
    return os.path.basename(target)


_ENGINE_STAT_RE = re.compile(
    r'<div class="stat"><b>[^<]*</b><span>engine</span></div>')


def _strip_engine_stat(html):  # implements: ARCH-SITE-026
    return _ENGINE_STAT_RE.sub("", html)


def cmd_site(ws, root=".", attach=None, regions=None, refresh_only=False):
    # implements: ARCH-SITE-026  # implements: REQ-SITE-924
    """Inject engine-owned regions into `attach`, or scaffold a default page
    there when it does not exist. With `refresh_only`, an existing page that
    carries no engine region is left alone: another tool may own it.
    Deterministic and headless-safe: never prompts, never raises on a
    missing git or remote."""
    if not attach:
        print("usage: reqmap sync --attach <page.html>")
        return 0
    regions = regions or ["nav"]
    data = _build_map_data(ws.reqs, ws.members)
    repo_url = _git_remote_web_url(root)
    page_dir = os.path.dirname(attach) or "."
    map_ok = os.path.isfile(os.path.join(page_dir, "map.html"))
    ctx = _site_context_from_data(data, repo_url=repo_url, map_ok=map_ok)
    if os.path.isfile(attach):
        with open(attach, encoding="utf-8") as f:
            html = f.read()
        if refresh_only and "<!--##REQMAP:" not in html:
            return 0
        mode = "refreshed"
    else:
        os.makedirs(page_dir, exist_ok=True)
        # escaped: a repo name or remote URL with < > " & would otherwise
        # break out of the template's title and href sinks
        name = _html_escape(_repo_name(root) or "this project")
        html = (SITE_TEMPLATE.replace("%%REPO_NAME%%", name)
                .replace("%%REPO_URL%%", _html_escape(repo_url or "#")))
        mode = "scaffolded"
    for name in regions:
        if name in SITE_REGIONS:
            html = _inject_region(html, name, _render_region(name, ctx))
    with open(attach, "w", encoding="utf-8") as f:
        f.write(html)
    print("{} {} (regions: {})".format(mode, attach, ",".join(regions)))
    return 0
