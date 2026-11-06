"""Known bugs, one Markdown file per module (ADR-0080).

`requirements/bugs/<module>.md` holds what `sync --bug` and the viewer add.
`BUG_SOURCES` names other files a repository already keeps; those are read and
never written. Imported at call time, so a repository with no bugs never loads
it. Bugs are not the corpus: nothing here reaches the drift lock, and an open
bug never fails the gate."""
import datetime
import difflib
import glob
import json
import os
import re
import unicodedata

from . import config as cfg

COLUMNS = ("ID", "Bug", "Priority", "Date", "Where", "Why it matters", "Source")
_KEYS = ("id", "title", "prio", "date", "where", "why", "source")
_PRIO_RE = re.compile(r"\bP([0-4])\b")
_ISO_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DOTTED_RE = re.compile(r"\b(\d{2})\.(\d{2})\.(\d{4})\b")
_REF_RE = re.compile(r"^\|\s*B(\d+)\*?\s*\|", re.M)
_SPLIT_RE = re.compile(r"(?<!\\)\|")
_SECTION_RE = re.compile(r"\bP([0-4])(?:\s*[-–—]\s*P([0-4]))?\b")
SIMILAR_TITLE = 0.8


def _cells(line):
    # implements: REQ-BUGS-1116
    """The cells of one Markdown table row; `\\|` stays inside a cell."""
    parts = _SPLIT_RE.split(line.strip())[1:-1]
    return [p.strip().replace("\\|", "|") for p in parts]


def _is_separator(line):
    # implements: REQ-BUGS-1116
    return bool(line.startswith("|")
                and re.match(r"^[\s|:-]+$", line) and "-" in line)


def named_columns(header, keys, own, extras):
    # implements: REQ-BUGS-1116
    """{key: column} for the `keys` a table header names, in English or in
    the repository's own `extras`."""
    names = [c.lower() for c in header]
    index = {}
    for key, canonical in zip(keys, own):
        extra = extras.get(key, ())
        wanted = [canonical] + ([extra] if isinstance(extra, str)
                                else list(extra))
        for name in wanted:
            if str(name).lower() in names:
                index[key] = names.index(str(name).lower())
                break
    return index


def _column_index(header, columns=None):
    # implements: REQ-BUGS-1116
    """{key: column} for a table header, or None when it is not a bug table:
    an id, a title and a priority are what makes one. A repository's own
    names come from `BUG_COLUMNS` and add to the canonical ones."""
    index = named_columns(header, _KEYS, COLUMNS,
                          cfg.BUG_COLUMNS if columns is None else columns)
    return index if {"id", "title", "prio"} <= set(index) else None


def iso_date(text):
    # implements: REQ-BUGS-1116
    """`text`'s date as YYYY-MM-DD, or "" when it holds no real one."""
    m, parts = _ISO_RE.search(text or ""), None
    if m:
        parts = (m.group(1), m.group(2), m.group(3))
    else:
        m = _DOTTED_RE.search(text or "")
        parts = (m.group(3), m.group(2), m.group(1)) if m else None
    try:
        return datetime.date(*map(int, parts)).isoformat() if parts else ""
    except ValueError:
        return ""


def _file_heading(text, stem):
    # implements: REQ-BUGS-1116
    """(module, date) from `# <anything> — <module> (<date>)`. The file's
    name is the module when there is no heading."""
    m = re.search(r"^#\s+(.+?)\s*$", text, re.M)
    if not m:
        return stem, ""
    title, date = m.group(1), ""
    tail = re.search(r"\(([^()]*)\)\s*$", title)
    if tail and iso_date(tail.group(1)):
        title, date = title[:tail.start()].strip(), iso_date(tail.group(1))
    return re.split(r"\s[—–-]\s", title)[-1].strip() or stem, date


def _row(cells, index, ctx, line_no, problems):
    # implements: REQ-BUGS-1116
    """One bug from one table row, or None with a line in `problems`."""
    cell = lambda key: (cells[index[key]] if key in index
                        and index[key] < len(cells) else "")
    ref = cell("id").rstrip("*").strip()
    where = "{}:{}".format(ctx["file"], line_no)
    prio = _PRIO_RE.search(cell("prio"))
    if not ref or not prio or not cell("title"):
        problems.append("{}: a bug needs an id, a title and a priority P0-P4"
                        .format(where))
        return None
    date = iso_date(cell("date"))
    if cell("date") and not date:
        problems.append("{}: {} has no real date in {!r}".format(
            where, ref, cell("date")))
    bug = {"id": "{}:{}".format(ctx["stem"], ref), "ref": ref,
           "module": ctx["module"], "title": cell("title"),
           "prio": "P" + prio.group(1),
           "estimated": "*" in cell("prio") or cell("id").endswith("*"),
           "date": date or ctx["date"], "where": cell("where"),
           "why": cell("why"), "source": cell("source"), "file": ctx["file"],
           "line": line_no}
    return bug


def _parse(text, ctx, problems):
    # implements: REQ-BUGS-1116
    """The bugs of every bug table in `text`. A table with other columns is
    somebody else's: a contents page, a list of questions. So is every table
    under a `##` heading `BUG_SKIP_SECTIONS` matches."""
    bugs, seen = [], set()
    lines = re.split(r"\r?\n", text)
    index, skip, skipped = None, ctx.get("skip"), False
    for n, line in enumerate(lines):
        section = re.match(r"##\s+(.+)", line)
        if section:
            skipped = bool(skip and skip.search(section.group(1)))
        if not line.startswith("|"):
            index = None
        elif skipped:
            continue
        elif index is None:
            if n + 1 < len(lines) and _is_separator(lines[n + 1]):
                index = _column_index(_cells(line)) or False
        elif index and not _is_separator(line):
            bug = _row(_cells(line), index, ctx, n + 1, problems)
            if bug and bug["id"] in seen:
                problems.append("{}:{}: {} appears twice".format(
                    ctx["file"], n + 1, bug["ref"]))
            elif bug:
                seen.add(bug["id"])
                bugs.append(bug)
    return bugs


def _read_file(path, root, problems, skip=None):
    # implements: REQ-BUGS-1116
    """The bugs of one file. Fail-open: an unreadable file is one problem."""
    rel = os.path.relpath(path, root).replace(os.sep, "/")
    try:
        with open(path, encoding="utf-8-sig", newline="") as f:
            text = f.read()
    except (OSError, UnicodeDecodeError) as exc:
        problems.append("{}: unreadable: {}".format(rel, exc))
        return []
    stem = os.path.splitext(os.path.basename(path))[0]
    module, date = _file_heading(text, stem)
    return _parse(text, {"file": rel, "stem": stem, "module": module,
                         "date": date, "skip": skip}, problems)


def register_name():
    # implements: REQ-BUGS-1127
    """The register's file name, which can never leave the bugs folder."""
    return os.path.basename(cfg.BUG_REGISTER) or "_fixed.md"


def _bug_paths(root, reqs_dir, problems):
    # implements: REQ-BUGS-1117
    """Every bug file, this repository's own folder first, each path once.
    A declared source that matches nothing is a typo worth a line."""
    folder = os.path.join(reqs_dir, cfg.BUGS_DIR)
    register = os.path.abspath(os.path.join(folder, register_name()))
    paths = sorted(os.path.abspath(p) for p in glob.glob(os.path.join(
        glob.escape(folder), "*.md")))
    for pattern in cfg.BUG_SOURCES:
        found = sorted(glob.glob(os.path.join(glob.escape(root), pattern),
                                 recursive=True))
        if not found:
            problems.append("BUG_SOURCES: {!r} matches no file".format(pattern))
        paths += [p for p in map(os.path.abspath, found) if p not in paths]
    return [p for p in paths if p != register]


def _skip_pattern(problems):
    # implements: REQ-BUGS-1116
    """`BUG_SKIP_SECTIONS` compiled, or None. A bad one is one problem line,
    and every table is then read."""
    try:
        return re.compile(cfg.BUG_SKIP_SECTIONS) if cfg.BUG_SKIP_SECTIONS else None
    except re.error as exc:
        problems.append("BUG_SKIP_SECTIONS: {}".format(exc))
        return None


def module_key(name):
    # implements: REQ-BUGS-1117
    """What two spellings of one module share: its words, without case,
    diacritics or punctuation."""
    text = unicodedata.normalize("NFKD", name)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(re.findall(r"[^\W_]+", text.casefold())) or name


def load_bugs(root, reqs_dir):
    # implements: ARCH-BUGS-078  # implements: REQ-BUGS-1117
    """(bugs, problems): every known bug of this repository, by file. Spellings
    of one module become the first one read, so every surface shows one group."""
    problems, bugs, spelling = [], [], {}
    root = root or "."
    skip = _skip_pattern(problems)
    for path in _bug_paths(root, reqs_dir, problems):
        bugs += _read_file(path, root, problems, skip)
    first = {}
    for bug in bugs:
        bug["module"] = spelling.setdefault(module_key(bug["module"]), bug["module"])
        if first.setdefault(bug["id"], bug["file"]) != bug["file"]:
            problems.append("{}: {} is also in {}; rename one file".format(
                bug["file"], bug["id"], first[bug["id"]]))
    return bugs, problems


def map_block(root, reqs_dir):
    # implements: REQ-BUGS-1117
    """The `bugs` list `_map.json` carries."""
    return load_bugs(root, reqs_dir)[0]


def input_problems(root, reqs_dir):
    # implements: REQ-BUGS-1118
    """The lines the gate reports as `INPUT:bugs`."""
    return load_bugs(root, reqs_dir)[1]


def _escape(value):
    # implements: REQ-BUGS-1119
    return " ".join(str(value or "").split()).replace("|", "\\|")


def module_file(module):
    # implements: REQ-BUGS-1119
    """A module's file name: its words joined by `-`, or "" when it has
    none. The result can never leave the bugs folder."""
    stem = re.sub(r"[^\w]+", "-", module or "", flags=re.U).strip("-")
    return stem + ".md" if stem else ""


def format_block():
    # implements: REQ-BUGS-1126
    """What the page needs to write a repository's own tables, when it has
    any: the page cannot read `_config.json`."""
    if (cfg.BUG_COLUMNS == {"id": ["#"]} and not cfg.BUG_SKIP_SECTIONS
            and cfg.BUG_REGISTER == "_fixed.md"):
        return {}
    return {"columns": cfg.BUG_COLUMNS, "skip": cfg.BUG_SKIP_SECTIONS,
            "register": cfg.BUG_REGISTER}


def _section_prios(heading):
    # implements: REQ-BUGS-1126
    """The priorities a `##` heading names, as digits: `P0-P1` is two."""
    m = _SECTION_RE.search(heading)
    if not m:
        return ""
    low, high = int(m.group(1)), int(m.group(2) or m.group(1))
    return "".join(str(n) for n in range(low, high + 1))


def _tables(lines, columns, skip):
    # implements: REQ-BUGS-1126
    """[(header line, one past its last row, column index, section's
    priorities)] for each bug table a row can go into."""
    tables, prios, skipped, n = [], "", False, 0
    while n < len(lines):
        section = re.match(r"##\s+(.+)", lines[n])
        if section:
            prios = _section_prios(section.group(1))
            skipped = bool(skip and skip.search(section.group(1)))
        if (lines[n].startswith("|") and n + 1 < len(lines)
                and _is_separator(lines[n + 1])):
            end = n + 2
            while end < len(lines) and lines[end].startswith("|"):
                end += 1
            index = _column_index(_cells(lines[n]), columns)
            if index and not skipped:
                tables.append((n, end, index, prios))
            n = end
        else:
            n += 1
    return tables


def append_bug(text, bug, floor=0, fmt=None):
    # implements: REQ-BUGS-1119  # implements: REQ-BUGS-1126
    """(new text, ref): `bug` added with the next free `B<n>`, past `floor`, as
    the last row of the table under its priority's `##` section, else of the
    file's first bug table, in that table's own columns. Pure.
    `app/src/lib/bugFile.js` is the same function for the viewer, and one
    fixture pins both."""
    fmt = fmt or {"columns": cfg.BUG_COLUMNS, "skip": cfg.BUG_SKIP_SECTIONS}
    text = text.replace("\r\n", "\n")
    if not text.strip():
        text = "# Bugs — {}\n".format(bug["module"])
    ref = "B{}".format(1 + max(
        [int(n) for n in _REF_RE.findall(text)] + [floor]))
    values = dict(bug, id=ref)
    lines = text.rstrip("\n").split("\n")
    skip = re.compile(fmt["skip"]) if fmt.get("skip") else None
    tables = _tables(lines, fmt.get("columns"), skip)
    digit = (_PRIO_RE.search(bug.get("prio") or "") or [""] * 2)[1]
    table = next((t for t in tables if digit and digit in t[3]),
                 tables[0] if tables else None)
    if table:
        _, end, index, _ = table
        cells = [""] * len(_cells(lines[table[0]]))
        for key, column in index.items():
            cells[column] = _escape(values.get(key))
        lines.insert(end, "| " + " | ".join(cells) + " |")
    else:
        lines += ["", "| " + " | ".join(COLUMNS) + " |",
                  "|" + "---|" * len(COLUMNS),
                  "| " + " | ".join(_escape(values.get(k)) for k in _KEYS) + " |"]
    return "\n".join(lines) + "\n", ref


def bug_file(files, module):
    # implements: REQ-BUGS-1126
    """The file a module's bug goes to, from [(name, text)]: the one whose
    heading or stem, without an `NN_` prefix, names the module. A new module
    is numbered when the files are. `bugFile` in the viewer is the same."""
    key = module_key(module)
    numbers = []
    for name, text in files:
        stem = name[:-len(".md")]
        bare = re.match(r"(\d+)[_-](.+)", stem)
        numbers += [bare.group(1)] if bare else []
        if key in (module_key(_file_heading(text, stem)[0]),
                   module_key(bare.group(2) if bare else stem)):
            return name
    fresh = module_file(module)
    if not numbers or not fresh:
        return fresh
    return "{}_{}".format(str(1 + max(map(int, numbers))).zfill(
        len(numbers[0])), fresh)


def _folder_files(folder):
    # implements: REQ-BUGS-1126
    """[(name, text)] of the bug files `sync --bug` may write."""
    if not os.path.isdir(folder):
        return []
    files = []
    for name in sorted(os.listdir(folder)):
        if name.endswith(".md") and name != register_name():
            with open(os.path.join(folder, name), encoding="utf-8-sig") as f:
                files.append((name, f.read()))
    return files


def _lookalikes(text, title):
    # implements: REQ-BUGS-1126
    """The rows of one module whose title reads like `title`."""
    wanted = " ".join(title.casefold().split())
    return [b for b in _parse(text, {"file": "", "stem": "", "module": "",
                                     "date": ""}, [])
            if difflib.SequenceMatcher(None, wanted, " ".join(
                b["title"].casefold().split())).ratio() >= SIMILAR_TITLE]


def cmd_bug_add(reqs_dir, title, a):
    # implements: ARCH-BUGS-078  # implements: REQ-BUGS-1119
    # implements: REQ-BUGS-1126
    """`sync --bug TITLE`: one row in the module's file. Exit 2 on input that
    would not read back as a bug, or on a title the module already holds
    without `--force`, and nothing is written."""
    prio = (a.prio or "P2").upper()
    date = iso_date(a.date) if a.date else datetime.date.today().isoformat()
    if not " ".join((title or "").split()) or not module_file(a.module):
        print("usage: reqmap sync --bug \"TITLE\" --module MODULE "
              "[--prio P0-P4[*]] [--date YYYY-MM-DD] [--where FILE:LINE] "
              "[--why TEXT] [--source TEXT] [--force]")
        return 2
    if not re.fullmatch(r"P[0-4]\*?", prio):
        print("sync --bug: --prio is P0 to P4, with `*` for an estimate, not "
              "{!r}".format(a.prio))
        return 2
    if not date:
        print("sync --bug: --date is YYYY-MM-DD, not {!r}".format(a.date))
        return 2
    folder = os.path.join(reqs_dir, cfg.BUGS_DIR)
    try:
        files = _folder_files(folder)
    except (OSError, UnicodeDecodeError) as exc:
        print("sync --bug: a file in {} cannot be read: {}".format(folder, exc))
        return 2
    name = bug_file(files, a.module)
    path = os.path.join(folder, name)
    text = dict(files).get(name, "")
    close = _lookalikes(text, title)
    if close and not getattr(a, "force", False):
        print("sync --bug: {} already reads like this; pass --force to add it "
              "anyway:".format(name))
        for b in close:
            print("  {}  {}".format(b["ref"], b["title"]))
        return 2
    from .bugclose import highest_closed
    text, ref = append_bug(text, {
        "module": a.module, "title": title, "prio": prio, "date": date,
        "where": a.where, "why": a.why, "source": a.source},
        highest_closed(reqs_dir, name[:-len(".md")]))
    os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print("bug {} added to {}. Run `sync` to show it on the map.".format(
        ref, os.path.relpath(path).replace(os.sep, "/")))
    return 0


def _matches(bug, module, prios):
    # implements: REQ-BUGS-1120
    return ((not module or module_key(module) in module_key(bug["module"]))
            and (not prios or bug["prio"] in prios))


def _total_line(bugs):
    # implements: REQ-BUGS-1120
    found = sorted(b["prio"] for b in bugs)
    mix = ["{} {}".format(p, found.count(p)) for p in sorted(set(found))]
    return "{} bug{}: {}".format(len(bugs), "" if len(bugs) == 1 else "s",
                                 ", ".join(mix))


def cmd_bugs(root, reqs_dir, module=None, prio=None, as_json=False):
    # implements: ARCH-BUGS-078  # implements: REQ-BUGS-1120
    """`ask --bugs`: the known bugs by module, highest priority first.
    Read-only, exit 0."""
    bugs, problems = load_bugs(root, reqs_dir)
    prios = [p.strip().upper() for p in (prio or "").split(",") if p.strip()]
    shown = [b for b in bugs if _matches(b, module, prios)]
    if as_json:
        print(json.dumps({"bugs": shown, "problems": problems},
                         ensure_ascii=False, indent=2))
        return 0
    if not shown:
        print("no known bugs" + (" match" if module or prio else ""))
    groups = {}
    for bug in shown:
        groups.setdefault(bug["module"], []).append(bug)
    for name in sorted(groups):
        print("{} ({})".format(name, len(groups[name])))
        for b in sorted(groups[name], key=lambda x: x["prio"]):
            print("  {}  {:<6} {:<10}  {}".format(
                b["prio"] + ("*" if b["estimated"] else " "), b["ref"],
                b["date"], b["title"]))
    if shown:
        print(_total_line(shown))
    for line in problems:
        print("! INPUT:bugs " + line)
    return 0
