"""Plan drift: which planned items cite code that has moved on without them.

The failure mode this answers was measured by a consumer over four occasions: the code
gets fixed, the note stays written. On 2026-09-05 fourteen of sixteen candidate items in
one repo were already done; the reader found out by opening each file by hand.

What is decidable from a plan file is narrow, and this module is deliberate about the
edge of it. A cited path that resolves nowhere is a FACT. A file that changed after the
note was written is a REASON TO READ, not a verdict. And a fix that leaves the path, the
symbol and the line exactly where they were is invisible to any check of form - the
consumer's own words, after the case that taught it. A detector claiming more than this
would be worse than none, because it would make the list look self-verifying.

The four false-positive classes below were each paid for in that consumer's first run,
not theorised here.
"""
import re

from .git import _git
from .scan import _walk_code

# implements: REQ-PLANDRIFT-1002
# Trap 1, measured: with `ts` before `tsx` in the alternation, `EmployeeDocumentList.tsx`
# matches `.ts`, leaves an orphan `x`, and the file "does not exist". Nine false positives
# from one ordering. Sorting longest-first makes the alternation greedy by construction,
# so the list can be extended without re-learning this.
CITED_EXTS = tuple(sorted(
    ("py", "js", "jsx", "ts", "tsx", "mjs", "cjs", "mts", "cts", "vue", "svelte",
     "go", "rs", "java", "kt", "kts", "cs", "rb", "php", "swift", "scala", "ex", "exs",
     "c", "cc", "cpp", "h", "hpp", "sh", "sql", "css", "scss", "html", "md",
     "json", "yaml", "yml", "toml", "tf"),
    key=len, reverse=True))
_PATH_RE = re.compile(
    r"(?<![\w/.-])([\w.-]+(?:/[\w.-]+)*\.(?:" + "|".join(CITED_EXTS) + r"))(?::(\d+))?\b")
# A symbol worth checking is one a reader would recognise as code: snake_case with an
# underscore, or CamelCase with an inner capital. A one-word lowercase backtick is prose
# in this corpus (`gate`, `sync`, `map`), and checking those would report every command
# name in the plan as a missing symbol.
_SYMBOL_RE = re.compile(r"^(?:[A-Za-z_]\w*\.)?([A-Za-z_]\w*)(?:\(\))?$")
_TICKED_RE = re.compile(r"`([^`\n]{2,80})`")
# Trap 5, found on this repo's own plan the first time it ran: `\b\d{4}-\d{2}-\d{2}\b`
# matches the date half of an ENGINE VERSION (`2026-06-19.1`), because `.` is a word
# boundary. The item was then dated off a version string it merely quoted, and every file
# it cited looked "changed since". A date is a date only when a digit does not follow it.
_ISO_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b(?!\.\d)")
# Any identifier-shaped token, wherever it appears — a definition, a call, a dict key, a
# comment. Trap 3 says a symbol living somewhere other than the note claims is an
# IMPRECISION, not a drift; indexing only `def`/`class` made `roadmap_unmapped` (a payload
# key, never a definition) read as missing. The `sure` bucket has to be sure, so the
# existence test is deliberately the most generous one available.
_TOKEN_RE = re.compile(r"[A-Za-z_]\w{3,}")


def _looks_like_symbol(word):
    # implements: REQ-PLANDRIFT-1002
    """True for a backticked token that reads as an identifier rather than prose."""
    m = _SYMBOL_RE.match(word.strip())
    if not m:
        return False
    name = m.group(1)
    if len(name) < 4:
        return False
    if "_" in name:
        return True
    has_upper = any(c.isupper() for c in name[1:])
    return has_upper and not name.isupper()


def cited_refs(text):
    # implements: REQ-PLANDRIFT-1002
    """{"paths": [...], "symbols": [...]} cited by one item's text. Pure."""
    paths, symbols = [], []
    for m in _PATH_RE.finditer(text):
        if m.group(1) not in paths:
            paths.append(m.group(1))
    for m in _TICKED_RE.finditer(text):
        word = m.group(1).strip()
        if _PATH_RE.search(word):
            continue
        m2 = _SYMBOL_RE.match(word.strip())
        if not m2 or not _looks_like_symbol(word):
            continue
        name = m2.group(1)
        if name not in symbols:
            symbols.append(name)
    return {"paths": paths, "symbols": symbols}


def _resolves(cited, known):
    # implements: REQ-PLANDRIFT-1002
    """The real repo-relative path a cited one names, or None.

    Trap 2, measured: a SHORTENED path is not a wrong one. A note writing
    `app/common/errors.py` for `apps/api/app/common/errors.py` is benign - the cited
    segments are a suffix of the real ones. One writing `app/documents/x.py` for
    `apps/api/app/signing/x.py` is wrong, because the module differs. Matching on whole
    SEGMENTS is what separates them; a plain `endswith` would call `errors.py` a match for
    `my_errors.py` and quietly rehabilitate real typos."""
    want = cited.replace("\\", "/").strip("/")
    if want in known:
        return want
    tail = want.split("/")
    for real in sorted(known):
        parts = real.split("/")
        if len(parts) >= len(tail) and parts[len(parts) - len(tail):] == tail:
            return real
    return None


def _is_new_ground(cited, known):
    # implements: REQ-PLANDRIFT-1002
    """True when the cited path is a plan TARGET rather than a stale reference.

    Trap 6, found on this repo's own plan the first time it ran:
    `TODO.md -> docs/history/TODO-archive.md` cites a file the item exists in order to
    CREATE. Reporting that as a broken reference is backwards.

    A plan target and a stale reference are identical as strings, so the neighbourhood
    decides, and ONE signal is not enough — it collides head-on with trap 2's wrong-module
    case, where the directory is equally absent and the report is wanted. Two signals
    separate all three:

      basename exists elsewhere        -> a real file under a wrong path   (report)
      basename gone, parent dir there  -> the file moved or was deleted    (report)
      neither                          -> nothing like it exists yet       (silent)
    """
    want = cited.replace("\\", "/").strip("/")
    base = want.rsplit("/", 1)[-1]
    if any(real.rsplit("/", 1)[-1] == base for real in known):
        return False
    if "/" not in want:
        return True
    prefix = want.rsplit("/", 1)[0] + "/"
    return not any(real.startswith(prefix) or ("/" + prefix) in real for real in known)


def _index_repo(code_root, reqs_dir=None):
    # implements: REQ-PLANDRIFT-1002
    """(paths, symbols) for the whole scanned tree.

    Trap 3, measured: the symbol search scope must be the WHOLE repo, not the files the
    note happens to cite. Notes cite ambiguous paths (`employees/service.py`, with dozens
    of namesakes), and confronting a symbol only with the resolved files reported
    `to_response`, `decrypt_cnp` and `EmployeeDosar` as missing when all three exist. A
    symbol living somewhere other than the note says is an imprecision, not a drift."""
    paths, symbols = set(), set()
    for fp, rel in _walk_code(code_root, reqs_dir):
        rel = rel.replace("\\", "/")
        paths.add(rel)
        # Prose is indexed for PATHS and not for SYMBOLS. A changelog is a record of what
        # a name used to be: `cmd_implement` is written all over this repo's history and
        # exists in none of its code, and counting that as "the symbol exists" makes the
        # check permanently silent. Code is where a cited identifier has to still live.
        if rel.endswith(".md"):
            continue
        try:
            with open(fp, encoding="utf-8", errors="replace") as f:
                body = f.read()
        except OSError:
            continue
        symbols.update(_TOKEN_RE.findall(body))
    return paths, symbols


def _last_touched(code_root, rel):
    # implements: REQ-PLANDRIFT-1002
    """ISO date of the last commit touching `rel`, or None when git cannot say."""
    out = (_git(["log", "-1", "--format=%cs", "--", rel], cwd=code_root) or "").strip()
    return out if _ISO_RE.fullmatch(out) else None


def item_dates(items):
    # implements: REQ-PLANDRIFT-1002
    """Each item's effective date, inheriting its section's when it carries none.

    Trap 4, measured, and the one that mattered most: items in an audit batch carry their
    date ONCE, in the section's opening paragraph, not on every line. Without inheritance
    the freshness check skipped exactly the items it was written for - the three already
    fixed in code - because none of them carried a date of its own."""
    out, inherited = [], None
    for item in items:
        if item.get("section_date"):
            inherited = item["section_date"]
        here = _ISO_RE.search(item.get("name") or "") or _ISO_RE.search(item.get("context") or "")
        out.append(here.group(1) if here else inherited)
    return out


def plan_drift(items, code_root, reqs_dir=None):
    # implements: ARCH-PLANDRIFT-069  # implements: REQ-PLANDRIFT-1002
    """Two buckets over the OPEN plan items: `sure` and `rederive`.

    `sure` - a path the item cites resolves to no file, or a symbol it cites exists
    nowhere in the tree. Mechanically checkable; a human still decides what it means.

    `rederive` - everything the item cites resolves, but a cited file was committed after
    the item's date. A reason to re-read the item, never a reason to close it: in the case
    that motivated this module the path, the symbol AND the line were all still correct,
    and the code had been fixed underneath them. Nothing here closes anything."""
    known, symbols = _index_repo(code_root, reqs_dir)
    dates = item_dates(items)
    sure, rederive = [], []
    for item, when in zip(items, dates):
        if item.get("done"):
            continue
        refs = cited_refs("{}\n{}".format(item.get("name", ""), item.get("context") or ""))
        if not refs["paths"] and not refs["symbols"]:
            continue
        gone = [p for p in refs["paths"]
                if _resolves(p, known) is None and not _is_new_ground(p, known)]
        missing = [s for s in refs["symbols"] if s not in symbols]
        if gone or missing:
            sure.append({"name": item.get("name", ""), "paths": gone, "symbols": missing})
            continue
        if not when:
            continue
        moved = []
        for cited in refs["paths"]:
            real = _resolves(cited, known)
            touched = _last_touched(code_root, real) if real else None
            if touched and touched > when:
                moved.append({"path": real, "changed": touched})
        if moved:
            rederive.append({"name": item.get("name", ""), "since": when, "files": moved})
    return {"sure": sure, "rederive": rederive}


def plan_drift_lines(result):
    # implements: ARCH-PLANDRIFT-069  # implements: REQ-PLANDRIFT-1002
    """Zero, one or two report lines. Silent when nothing is found, like every other
    advisory line in the audit."""
    lines = []
    if result["sure"]:
        first = result["sure"][0]
        what = (first["paths"] or first["symbols"] or ["?"])[0]
        lines.append("{} open plan item(s) cite code that is not there ({}{}) - the item "
                     "may already be done, or the reference may be stale"
                     .format(len(result["sure"]), what,
                             ", ..." if len(result["sure"]) > 1 else ""))
    if result["rederive"]:
        lines.append("{} open plan item(s) cite a file committed after the item's own date "
                     "- worth re-reading, not closing".format(len(result["rederive"])))
    return lines
