"""What happens to a known bug after it is listed (ADR-0082): one row leaves its
module's file for the register, by hand with `sync --fix` or from a commit's
`Fixes-bug:` trailer on `sync`. Imported at call time, like `bugs`."""
import datetime
import os
import re
import shutil
import tempfile

from . import config as cfg
from .bugs import (_cells, _escape, _is_separator, iso_date, load_bugs,
                   named_columns, register_name)
from .git import _git, _git_remote_web_url
from .versions import read_version_file, version_files

COLUMNS = ("ID", "Bug", "Module", "Priority", "Found", "Fixed", "Version",
           "Commit", "Note")
_KEYS = ("id", "title", "module", "prio", "date", "fixed", "version", "commit",
         "note")
NOT_A_BUG = "not a bug"
_NOTHING = "—"
_ID_RE = re.compile(r"(.+)[:\s]\s*(\S+)")


def bug_id(text):
    # implements: REQ-BUGS-1127
    """`FILE:REF` from either spelling, `FILE:REF` or `FILE REF`."""
    m = _ID_RE.fullmatch(" ".join((text or "").split()))
    return ("{}:{}".format(m.group(1).rstrip(": "), m.group(2).rstrip("*"))
            if m else "")


def _register_path(reqs_dir):
    # implements: REQ-BUGS-1127
    return os.path.join(reqs_dir, cfg.BUGS_DIR, register_name())


def _table(lines):
    # implements: REQ-BUGS-1127
    """(header line, one past the last row, {key: column}) of the register's
    table, or None."""
    for n, line in enumerate(lines[:-1]):
        if line.startswith("|") and _is_separator(lines[n + 1]):
            index = named_columns(_cells(line), _KEYS, COLUMNS,
                                  cfg.BUG_REGISTER_COLUMNS)
            if {"id", "title", "fixed"} <= set(index):
                end = n + 2
                while end < len(lines) and lines[end].startswith("|"):
                    end += 1
                return n, end, index
    return None


def parse_fixed(text):
    # implements: REQ-BUGS-1127
    """The register's rows, as dicts of `_KEYS`, in file order."""
    lines = text.lstrip("\ufeff").replace("\r\n", "\n").split("\n")
    table = _table(lines)
    if not table:
        return []
    start, end, index = table
    rows = []
    for line in lines[start + 2:end]:
        cells = _cells(line)
        row = {k: cells[c] if c < len(cells) else "" for k, c in index.items()}
        rows.append({k: row.get(k, "") for k in _KEYS})
    return rows


def _read(path):
    # implements: REQ-BUGS-1127
    if not os.path.isfile(path):
        return ""
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def fixed_rows(reqs_dir):
    # implements: REQ-BUGS-1127
    """The register, fail-open: one that is not UTF-8 reads as empty, and
    `_close` refuses to write over it."""
    try:
        return parse_fixed(_read(_register_path(reqs_dir)))
    except (OSError, UnicodeDecodeError):
        return []


def highest_closed(reqs_dir, stem):
    # implements: REQ-BUGS-1127
    """The highest `B<n>` a closed bug of file `stem` held, so a number is
    never given twice."""
    numbers = [0]
    for row in fixed_rows(reqs_dir):
        file_stem, _, ref = bug_id(row["id"]).rpartition(":")
        m = re.fullmatch(r"B(\d+)", ref)
        if m and file_stem == stem:
            numbers.append(int(m.group(1)))
    return max(numbers)


def close_bug(module_text, register_text, bug, meta):
    # implements: REQ-BUGS-1127
    """(module text, register text): the row on `bug["line"]` moved to the
    register, whose own columns decide the row's shape. Pure. A file that
    moved under the reader raises ValueError rather than lose another row."""
    kept = re.split(r"(?<=\n)", module_text)
    at = bug["line"] - 1
    if at >= len(kept) or bug["ref"] not in [
            c.rstrip("*").strip() for c in _cells(kept[at].rstrip("\r\n"))]:
        raise ValueError("{} is not on line {} of {}".format(
            bug["ref"], bug["line"], bug["file"]))
    del kept[at]
    values = dict(bug, **meta)
    text = register_text.lstrip("\ufeff").replace("\r\n", "\n")
    lines = text.rstrip("\n").split("\n") if text.strip() else ["# Fixed bugs"]
    table = _table(lines)
    if not table:
        lines += ["", "| " + " | ".join(COLUMNS) + " |",
                  "|" + "---|" * len(COLUMNS)]
        table = _table(lines)
    start, end, index = table
    cells = [""] * len(_cells(lines[start]))
    for key, column in index.items():
        cells[column] = _escape(values.get(key))
    lines.insert(end, "| " + " | ".join(cells) + " |")
    return "".join(kept), "\n".join(lines) + "\n"


def version_at(root, reqs_dir, sha=None):
    # implements: REQ-BUGS-1127  # implements: REQ-BUGS-1128
    """The version in the repository's version file, now or at commit `sha`,
    or "" when it keeps none. Teams without versions still have the commit."""
    found = version_files(reqs_dir, root)
    if not found or not sha:
        return found[0][1] if found else ""
    path = found[0][0]
    blob = _git(["-C", root, "show", "{}:./{}".format(sha, path)])
    if blob is None:
        return ""
    folder = tempfile.mkdtemp()
    try:
        copy = os.path.join(folder, os.path.basename(path))
        with open(copy, "w", encoding="utf-8") as f:
            f.write(blob)
        return read_version_file(copy) or ""
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def _writable(root, reqs_dir, bug):
    # implements: REQ-BUGS-1127
    """Whether `bug` lives in the bugs folder: `BUG_SOURCES` files stay the
    repository's own, read and never written."""
    folder = os.path.abspath(os.path.join(reqs_dir, cfg.BUGS_DIR))
    return (os.path.dirname(os.path.abspath(os.path.join(root, bug["file"])))
            == folder)


def _close(root, reqs_dir, bug, meta):
    # implements: REQ-BUGS-1127
    """Move one row. The register is written first: a crash between the two
    writes leaves a row open and recorded, never lost."""
    path = os.path.join(root, bug["file"])
    module_text, register = close_bug(
        _read(path), _read(_register_path(reqs_dir)), bug, meta)
    with open(_register_path(reqs_dir), "w", encoding="utf-8",
              newline="\n") as f:
        f.write(register)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(module_text)


def cmd_bug_fix(root, reqs_dir, target, a):
    # implements: ARCH-BUGS-078  # implements: REQ-BUGS-1127
    """`sync --fix ID`: one row to the register. Exit 2, writing nothing, for
    an id that is unknown, closed already, or in a file this never writes."""
    wanted = bug_id(target)
    if wanted in {bug_id(r["id"]) for r in fixed_rows(reqs_dir)}:
        print("sync --fix: {} is already in the register".format(wanted))
        return 2
    bug = next((b for b in load_bugs(root, reqs_dir)[0]
                if b["id"] == wanted), None)
    if bug is None:
        print("sync --fix: no open bug {!r}; `ask --bugs --json` lists the "
              "ids".format(target))
        return 2
    if not _writable(root, reqs_dir, bug):
        print("sync --fix: {} is in {}, which `BUG_SOURCES` names and nothing "
              "here writes; remove the row there".format(wanted, bug["file"]))
        return 2
    head = _git(["-C", root, "rev-parse", "--short", "HEAD"])
    meta = {"id": wanted, "fixed": datetime.date.today().isoformat(),
            "version": a.bug_version or version_at(root, reqs_dir) or _NOTHING,
            "commit": a.commit or (head or "").strip() or _NOTHING}
    if a.note:
        meta.update(version=NOT_A_BUG, commit=_NOTHING, note=a.note)
    try:
        _close(root, reqs_dir, bug, meta)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        print("sync --fix: nothing written: {}".format(exc))
        return 2
    print("bug {} closed in {}. Run `sync` to update the map.".format(
        wanted, os.path.relpath(_register_path(reqs_dir)).replace(os.sep, "/")))
    return 0


def fix_trailers(root):
    # implements: REQ-BUGS-1128
    """[(sha, short sha, date, id)] for every trailer on the history of HEAD,
    oldest first. No git, or no such commit: an empty list."""
    names = [re.escape(str(n)) for n in cfg.BUG_FIX_TRAILERS]
    if not names:
        return []
    args = ["-C", root, "log", "HEAD", "--reverse", "-i", "--extended-regexp",
            "--format=%H%x1f%h%x1f%cs%x1f%B%x1e"]
    out = _git(args + ["--grep=^({}):".format("|".join(names))], timeout=30)
    line_re = re.compile(r"^(?:{}):\s*(.+?)\s*$".format("|".join(names)),
                         re.I | re.M)
    found = []
    for record in (out or "").split("\x1e"):
        parts = record.strip().split("\x1f")
        if len(parts) == 4:
            found += [(parts[0], parts[1], parts[2], bug_id(m))
                      for m in line_re.findall(parts[3])]
    return found


def close_from_commits(root, reqs_dir):
    # implements: ARCH-BUGS-078  # implements: REQ-BUGS-1128
    """Close what the history says is fixed. A bug in the register is left
    alone, so a second run changes nothing, and the register is the only
    state: no lock to conflict on every merge. A trailer that names nothing
    is a printed line, not a gate warning, because a commit cannot be edited
    to clear it."""
    trailers = fix_trailers(root)
    if not trailers:
        return 0
    closed = {bug_id(r["id"]) for r in fixed_rows(reqs_dir)}
    count = 0
    for sha, short, date, wanted in trailers:
        if wanted in closed:
            continue
        bug = next((b for b in load_bugs(root, reqs_dir)[0]
                    if b["id"] == wanted), None)
        if bug is None or not _writable(root, reqs_dir, bug):
            print("! INPUT:bugs commit {} names {}, {}".format(
                short, wanted or "no id",
                "which is in a file nothing here writes" if bug
                else "which is not an open bug"))
            continue
        try:
            _close(root, reqs_dir, bug, {
                "id": wanted, "fixed": date, "commit": short,
                "version": version_at(root, reqs_dir, sha) or _NOTHING})
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            print("! INPUT:bugs commit {}: {}".format(short, exc))
            continue
        closed.add(wanted)
        count += 1
        print("bug {} closed by commit {}".format(wanted, short))
    return count


def fixed_block(reqs_dir):
    # implements: REQ-BUGS-1129
    """The `bugs_fixed` list `_map.json` carries."""
    rows = []
    for row in fixed_rows(reqs_dir):
        row.update(date=iso_date(row["date"]), fixed=iso_date(row["fixed"]))
        rows.append({k: v for k, v in row.items() if v and v != _NOTHING})
    return rows


def forge_of(root):
    # implements: REQ-BUGS-1129
    """The forge a commit links to, only GitHub's URLs being known here. It
    differs between a clone and a fork, so it reaches `_map.html` only."""
    url = _git_remote_web_url(root) or ""
    return url.rstrip("/") if "github." in url else ""
