"""What has already shipped, read from CHANGELOG.md.

The plan answers "what is next". This answers "what happened", and it needs no new file
to do it: a repo that follows the release discipline already writes one dated heading per
release, with a headline under it. Deriving the history from that instead of from a
sidecar means it cannot drift from what was actually released — the same reason `health`
and `design` are read from the engine rather than recomputed in the viewer.

Deliberately NOT from `git log`. Tags record every commit, including the ones that fixed
the previous commit; a CHANGELOG heading is the author's own statement that something
shipped, which is what "in broad strokes" asks for.
"""
import os
import re

# `## plugin `vX.Y.Z` — YYYY-MM-DD`, the shape `check_versions.py` and the release job
# already depend on. Both dash characters, because the file uses an em dash and a
# consumer writing a hyphen means the same thing.
_ENTRY_RE = re.compile(
    r"^##\s+plugin\s+`(v[0-9][0-9A-Za-z.\-]*)`\s*[—–-]+\s*(\d{4}-\d{2}-\d{2})\s*$",
    re.M)
_HEADING_RE = re.compile(r"^##\s+plugin\s+", re.M)
_BOLD_RE = re.compile(r"^\*\*(.+?)\*\*", re.S)
HISTORY_FILES = ("CHANGELOG.md",)
# A headline is a label on a timeline, not the entry itself. Past this the chart shows a
# paragraph where it wanted a caption.
HEADLINE_MAX = 120


def _headline(body):  # implements: REQ-HISTORY-1003
    """The entry's first bold run, flattened to one line, or its first prose line.

    Every entry in this repo opens with a bold sentence naming what shipped; a consumer
    who does not write one still gets something, because a heading with no summary at all
    reads on the chart as a version that did nothing."""
    for raw in body.split("\n"):
        line = raw.strip()
        # `* ` with the space is a bullet; `**` is the bold headline every entry opens
        # with. Skipping on a bare `*` threw away the headline of every entry and left
        # the chart labelled with the second line of the paragraph.
        if not line or line.startswith(("-", "* ", ">", "|", "#", "```")):
            continue
        m = _BOLD_RE.match(line)
        text = (m.group(1) if m else line).strip()
        text = re.sub(r"\s+", " ", text).strip(" .")
        # A bold run ending in a colon is a LEAD-IN to the list under it, not a summary
        # ("First feature release since `v1.0.0`. Highlights:"). Taking it leaves the
        # chart labelled with half a sentence, so keep reading for one that stands alone.
        if not text or text.endswith(":"):
            continue
        return text[:HEADLINE_MAX].rstrip() + ("…" if len(text) > HEADLINE_MAX else "")
    return ""


def _weight(version):  # implements: REQ-HISTORY-1003
    """Sort key picking a month's landmark release: a major beats a minor beats a patch,
    and among equals the newer version wins.

    The month's FIRST release is not it — it is whatever happened to land first, often a
    patch on the month before. The month's LAST is not it either, for the same reason at
    the other end. What a reader means by "what happened in August" is its biggest step."""
    parts = [int(p) if p.isdigit() else 0 for p in version.lstrip("v").split(".")]
    parts += [0] * (3 - len(parts))
    rank = 2 if parts[1:] == [0, 0] else (1 if parts[2] == 0 else 0)
    return (rank, parts)


def parse_changelog(text):  # implements: REQ-HISTORY-1003
    """[{version, date, headline}] newest first. Pure.

    An entry with no date is SKIPPED, not dated by guesswork: this repo carries
    `## plugin `v3.5.0` — superseded, never released`, and a version that never shipped
    has no place on a timeline of what shipped."""
    out, marks = [], list(_ENTRY_RE.finditer(text))
    # Body runs to the next heading of ANY kind, dated or not, so an undated entry's prose
    # is never absorbed into the dated one above it.
    stops = [m.start() for m in _HEADING_RE.finditer(text)] + [len(text)]
    for m in marks:
        end = next(s for s in stops if s > m.start())
        out.append({"version": m.group(1), "date": m.group(2),
                    "headline": _headline(text[m.end():end])})
    return out


def read_history(root):  # implements: REQ-HISTORY-1003
    """Parsed CHANGELOG entries for `root` or its parent, or [] when there is none."""
    for base in dict.fromkeys([root, os.path.dirname(os.path.abspath(root))]):
        for name in HISTORY_FILES:
            path = os.path.join(base, name)
            if not os.path.isfile(path):
                continue
            try:
                with open(path, encoding="utf-8") as f:
                    return parse_changelog(f.read())
            except OSError:
                return []
    return []


def by_month(entries):  # implements: REQ-HISTORY-1003
    """[{month, count, first, last, versions, headline}] oldest first — the broad-strokes
    view.

    One row per calendar month, because 100 releases across four months is a wall of ticks
    and the question it answers is "what happened since we started", not "when exactly did
    v5.12.1 land". `landmark` and `headline` come from the month's biggest step, not its
    first or last release — see `_weight`. `versions` keeps every version in it, so the
    detail is one hover away and nothing is lost by grouping."""
    months = {}
    for e in sorted(entries, key=lambda x: (x["date"], x["version"])):
        key = e["date"][:7]
        row = months.setdefault(key, {"month": key, "count": 0, "first": e["date"],
                                      "last": e["date"], "versions": [],
                                      "landmark": "", "headline": ""})
        row["count"] += 1
        row["last"] = e["date"]
        row["versions"].append(e["version"])
        if not row["landmark"] or _weight(e["version"]) > _weight(row["landmark"]):
            row["landmark"] = e["version"]
            row["headline"] = e["headline"]
    return [months[k] for k in sorted(months)]
