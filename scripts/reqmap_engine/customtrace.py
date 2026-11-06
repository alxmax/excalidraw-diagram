"""A repository's own trace convention (ADR-0077): extra tag forms, test-file
globs, and requirements kept as text or HTML in folders of the repository's
choosing, all described in `requirements/_config.json`.

Imported only when one of those keys is set, so a repository that writes the
built-in forms never loads it. Every pattern comes from the config; this module
names no convention of its own.
"""
# implements: ARCH-CUSTOMTRACE-077
import fnmatch
import glob
import html
import os
import re

from . import config as cfg
from .parse import parse_frontmatter, split_requirement_blocks

TAG_ROLES = ("implements", "tested-by", "auto")
SOURCE_FORMATS = ("text", "html", "md")
SOURCE_STATUSES = ("confirmed", "draft")


# ---------- reading the config ---------------------------------------------

def _compiles(pattern):
    try:
        return re.compile(pattern)
    except (re.error, TypeError):
        return None


def validate_tags(value):
    # implements: REQ-CUSTOMTRACE-1110
    """(entries kept, problems) for a `TRACE_TAGS` value."""
    if not isinstance(value, list):
        return [], ["config: ignoring TRACE_TAGS (expected a list of objects)"]
    kept, problems = [], []
    for i, e in enumerate(value):
        rx = _compiles(e.get("pattern")) if isinstance(e, dict) else None
        if rx is None or rx.groups < 1:
            problems.append("config: ignoring TRACE_TAGS[{}] (pattern missing, not a "
                            "regex, or without a group for the id)".format(i))
        elif e.get("role") not in TAG_ROLES:
            problems.append("config: ignoring TRACE_TAGS[{}] (role must be one of "
                            "{})".format(i, ", ".join(TAG_ROLES)))
        else:
            kept.append({"pattern": e["pattern"], "role": e["role"]})
    return kept, problems


def validate_sources(value):
    # implements: REQ-CUSTOMTRACE-1113
    """(entries kept, problems) for a `REQUIREMENT_SOURCES` value."""
    if not isinstance(value, list):
        return [], ["config: ignoring REQUIREMENT_SOURCES (expected a list of "
                    "objects)"]
    kept, problems = [], []
    for i, e in enumerate(value):
        where = "config: ignoring REQUIREMENT_SOURCES[{}]".format(i)
        if not isinstance(e, dict) or not isinstance(e.get("glob"), str):
            problems.append(where + " (expected an object with a glob)")
            continue
        fmt = e.get("format", "text")
        status = e.get("status", "confirmed")
        rx = _compiles(e.get("start")) if fmt != "md" else re.compile("(x)")
        if fmt not in SOURCE_FORMATS:
            problems.append(where + " (format must be one of {})".format(
                ", ".join(SOURCE_FORMATS)))
        elif rx is None or rx.groups < 1:
            problems.append(where + " (start missing, not a regex, or without a "
                            "group for the id)")
        elif status not in SOURCE_STATUSES:
            problems.append(where + " (status must be one of {})".format(
                ", ".join(SOURCE_STATUSES)))
        else:
            kept.append({"glob": e["glob"], "format": fmt, "status": status,
                         "start": e.get("start"),
                         "owner": str(e.get("owner") or "external")})
    return kept, problems


# ---------- tags and test files --------------------------------------------

_FORMS = {}


def _forms():
    """The configured tag forms, compiled once per distinct config."""
    key = repr(cfg.TRACE_TAGS)
    if key not in _FORMS:
        _FORMS[key] = [(re.compile(e["pattern"]), e["role"])
                       for e in cfg.TRACE_TAGS]
    return _FORMS[key]


def custom_tags(fp, text):
    # implements: REQ-CUSTOMTRACE-1110
    """(role, id) for every configured tag on `text`, a line of `fp`. `auto`
    is tested-by in a test file and implements anywhere else."""
    out = []
    for rx, role in _forms():
        for m in rx.finditer(text):
            if role == "auto":
                from .tags import _is_test_path
                role_here = "tested-by" if _is_test_path(fp) else "implements"
            else:
                role_here = role
            out.append((role_here, m.group(1)))
    return out


def has_custom_tag(text):
    # implements: REQ-CUSTOMTRACE-1110
    return any(rx.search(text) for rx, _role in _forms())


def matches_test_glob(path):
    # implements: REQ-CUSTOMTRACE-1112
    """True when `path` matches a `TEST_FILE_PATTERNS` glob, read relative to
    any directory, so an absolute and a relative path answer the same."""
    posix = path.replace(os.sep, "/")
    return any(fnmatch.fnmatch(posix, pat) or fnmatch.fnmatch(posix, "*/" + pat)
               for pat in cfg.TEST_FILE_PATTERNS)


# ---------- requirements kept as text ---------------------------------------

def is_source_path(rel):
    # implements: REQ-CUSTOMTRACE-1113
    """True when `rel` is a file one of the requirement sources reads."""
    posix = rel.replace(os.sep, "/")
    return any(fnmatch.fnmatch(posix, src["glob"]) for src in cfg.REQUIREMENT_SOURCES)


_BLOCK_TAGS = re.compile(r"(?i)<\s*(br|/p|/div|/li|/tr|/h[1-6]|/table|/ul|/ol)\b[^>]*>")
_CELL_TAGS = re.compile(r"(?i)<\s*/(td|th)\s*>")
_DROP = re.compile(r"(?is)<(script|style)\b.*?</\1\s*>")
_ANY_TAG = re.compile(r"(?s)<[^>]+>")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def html_to_text(text):
    # implements: REQ-CUSTOMTRACE-1113
    """HTML as lines of text: a block ends a line, a table cell is a space, so
    a table row reads as one line."""
    text = _DROP.sub("", text)
    text = _BLOCK_TAGS.sub("\n", text)
    text = _CELL_TAGS.sub(" ", text)
    return html.unescape(_ANY_TAG.sub("", text))


def _body(text):
    """A requirement body the engine reads: one clause per sentence."""
    flat = " ".join(text.split())
    sentences = [s for s in _SENTENCE.split(flat) if s.strip()]
    title = (sentences[0] if sentences else "")[:80]
    clauses = "\n".join("- " + s for s in sentences)
    return "# {}\n\n## Description\nEvery bullet below is binding.\n{}\n".format(
        title, clauses)


def split_text(text, start):
    # implements: REQ-CUSTOMTRACE-1113
    """[(id, text)] for every requirement in `text`: one starts on a line the
    `start` regex matches, and runs to the next such line or the end."""
    rx = re.compile(start)
    out = []
    for line in text.splitlines():
        m = rx.match(line)
        if m:
            out.append([m.group(1), line[m.end():]])
        elif out:
            out[-1][1] += "\n" + line
    return [(rid, body.strip()) for rid, body in out]


def _read(path):
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        return f.read()


def _source_blocks(path, src):
    """[(id, meta, body)] for one file of one source."""
    if src["format"] == "md":
        out = []
        for blk in split_requirement_blocks(_read(path)):
            meta, body = parse_frontmatter(blk)
            if isinstance(meta.get("id"), str):
                out.append((meta["id"], meta, body))
        return out
    text = _read(path)
    if src["format"] == "html":
        text = html_to_text(text)
    return [(rid, {"id": rid, "status": src["status"], "layer": "feature",
                   "owner": src["owner"], "source": src["format"]}, _body(body))
            for rid, body in split_text(text, src["start"])]


def load_sources(reqs, code_root):
    # implements: REQ-CUSTOMTRACE-1113
    """Add every requirement the configured sources hold to `reqs`. A source
    that matches no file, an unreadable file and a duplicate id are each a
    problem on `reqs`, as they are for `requirements/`."""
    from .model import Requirement
    for i, src in enumerate(cfg.REQUIREMENT_SOURCES):
        paths = sorted(p for p in glob.glob(os.path.join(code_root or ".", src["glob"]),
                                            recursive=True) if os.path.isfile(p))
        if not paths:
            reqs.problem("REQUIREMENT_SOURCES[{}] matches no file: {}".format(
                i, src["glob"]))
            continue
        for path in paths:
            try:
                blocks = _source_blocks(path, src)
            except OSError as e:
                reqs.problem("skipping unreadable requirement source {!r}: {}"
                             .format(path, e))
                continue
            for n, (rid, meta, body) in enumerate(blocks):
                if rid in reqs:
                    reqs.problem("duplicate requirement id {!r} in {!r}".format(
                        rid, path))
                    continue
                reqs[rid] = Requirement(meta=meta, body=body, path=path, block=n)
    return reqs
