"""`init --watch` and `init --propose`: drafts a person still has to confirm.

Neither command writes a requirement, and neither sets status: confirmed.
Issue trackers are not read. Imported only when one of these flags is
used, so a bare gate does not load this module.
"""
import fnmatch
import hashlib
import json
import os
import sys

from . import config as cfg
from .git import _git
from .scan import load_ignore
from .tags import TAG_RE

FILE_CAP = 40
COMMIT_CAP = 40
_READ_CAP = 200000


def _one_line(text):
    # implements: REQ-WATCH-1092  # implements: REQ-PROPOSE-1093
    return " ".join((text or "").split())


def _title_from(summary):
    # implements: REQ-WATCH-1092  # implements: REQ-PROPOSE-1093
    text = _one_line(summary)
    if len(text) <= 72:
        return text
    cut = text[:72].rsplit(" ", 1)[0]
    return cut or text[:72]


def _draft_md(req_id, title, summary, files):
    # implements: REQ-WATCH-1092  # implements: REQ-PROPOSE-1093
    """One unconfirmed requirement. The frontmatter status is draft."""
    named = ", ".join(files) if files else "(none named)"
    summary = _one_line(summary)
    title = _title_from(title)
    lines = [
        "---",
        "id: " + req_id,
        "status: draft",
        "layer: feature",
        "---",
        "",
        "# " + title,
        "",
        "## Description",
        "> " + summary,
        "",
        "Every bullet below is binding.",
        "- " + summary,
        "",
        "## Cases",
        "CASE-1 — the description holds",
        "  Given  the files named in Context",
        "  When   that behaviour is exercised",
        "  Then   it matches the description. A person sets",
        "         status: confirmed only after reading this",
        "",
        "## Context",
        "Files: " + named + ".",
        "Unconfirmed. The tool does not set status: confirmed.",
        "",
    ]
    return "\n".join(lines)


def _stem_token(path):
    # implements: REQ-WATCH-1092
    stem = os.path.splitext(os.path.basename(path))[0].upper()
    raw = "".join(ch if ch.isalnum() else "-" for ch in stem)
    token = "-".join(part for part in raw.split("-") if part)
    if not token or not token[0].isalpha():
        token = ("FILE-" + token) if token else "FILE"
    return token[:24].strip("-") or "FILE"


def _code_path(rel):
    # implements: REQ-WATCH-1092
    rel = rel.replace("\\", "/")
    while rel.startswith("./"):
        rel = rel[2:]
    rel = rel.lstrip("/")
    if not rel or rel.startswith("requirements/"):
        return False
    if any(part.startswith(".") for part in rel.split("/")):
        return False
    ext = os.path.splitext(rel)[1].lower()
    return ext in cfg.CODE_EXTS


def _tagged(path):
    # implements: REQ-WATCH-1092
    """True when the file already has an implements tag, or cannot be read."""
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            text = handle.read(_READ_CAP)
    except OSError:
        return True
    return any(role == "implements" for role, _id in TAG_RE.findall(text))


def _commit(code_root, ref):
    # implements: REQ-WATCH-1092
    """The commit sha for ref, or None.

    A ref that starts with '-' is refused before git sees it. Otherwise it
    would be an option (`--output=...`) on the diff that follows, and git
    would write a file while this command reports that it wrote nothing.
    """
    if not ref or ref.startswith("-"):
        return None
    out = _git(["rev-parse", "--verify", "--end-of-options",
                ref + "^{commit}"], cwd=code_root)
    if not out:
        return None
    sha = out.strip().splitlines()[0].strip()
    if not sha or sha.startswith("-"):
        return None
    return sha


def _ignored(code_root, rel):
    # implements: REQ-WATCH-1092
    """True when `.reqmapignore` would keep the scan off this path."""
    reqs = os.path.join(code_root, "requirements")
    pats = load_ignore(code_root, reqs)
    return any(fnmatch.fnmatch(rel, pat) for pat in pats)


def _paths_since(code_root, ref):
    # implements: REQ-WATCH-1092
    """Paths changed since ref, plus untracked files. None when ref fails."""
    named = _git(["diff", "--name-only", "--relative", "--end-of-options",
                  ref, "--"], cwd=code_root)
    if named is None:
        return None
    others = _git(["ls-files", "--others", "--exclude-standard"],
                  cwd=code_root) or ""
    seen, paths = set(), []
    for blob in (named, others):
        for line in blob.splitlines():
            rel = line.strip().replace("\\", "/")
            if rel and rel not in seen:
                seen.add(rel)
                paths.append(rel)
    paths.sort()
    return paths


def _subjects(code_root, ref):
    # implements: REQ-WATCH-1092
    """Commit subjects since ref, without subjects that start with Merge."""
    log = _git(["log", "--format=%s", "--end-of-options", ref + "..HEAD"],
               cwd=code_root)
    if log is None:
        return []
    kept = []
    for line in log.splitlines():
        text = _one_line(line)
        if len(text) < 8 or text.lower().startswith("merge "):
            continue
        kept.append(text)
    return kept


def _suggestions(code_root, ref, paths):
    # implements: REQ-WATCH-1092
    used, out, over = {}, [], 0
    for rel in paths:
        if not _code_path(rel) or _ignored(code_root, rel):
            continue
        full = os.path.join(code_root, *rel.split("/"))
        if _tagged(full):
            continue
        if len(out) >= FILE_CAP:
            over += 1
            continue
        token = _stem_token(rel)
        n = used.get(token, 0) + 1
        used[token] = n
        req_id = "DRAFT-{}-{:03d}".format(token, n)
        summary = ("{} changed since {} and no requirement "
                   "claims it yet.".format(rel, ref))
        out.append({
            "path": rel,
            "status": "draft",
            "needs_confirmation": True,
            "suggested_id": req_id,
            "reason": "changed since {} and no implements: tag".format(ref),
            "draft": _draft_md(req_id, _stem_token(rel), summary, [rel]),
        })
    return out, over


def _unreadable(ref):
    # implements: REQ-WATCH-1092
    """The report for a ref git cannot read: said on stderr as well, so a
    person at a terminal sees it. The exit stays 0 (a pull request check
    must not fail on it)."""
    print("reqmap init: git could not read the ref {!r}".format(ref),
          file=sys.stderr)
    payload = {
        "ok": False, "ref": ref, "writes": False,
        "error": "git could not read that ref",
        "files": [], "commits": [], "issues": "not read",
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def cmd_watch(code_root, ref):
    # implements: REQ-WATCH-1092
    """Print suggestions for one ref. Writes nothing. Exits 0, or 2
    when the ref itself was omitted."""
    ref = (ref or "").strip()
    if not ref:
        print("reqmap init: --watch needs a git ref", file=sys.stderr)
        return 2
    sha = _commit(code_root, ref)
    if sha is None:
        return _unreadable(ref)
    paths = _paths_since(code_root, sha)
    if paths is None:
        return _unreadable(ref)
    files, over = _suggestions(code_root, ref, paths)
    subjects = _subjects(code_root, sha)
    commits = [{"source": "commit", "subject": text, "status": "draft",
                "needs_confirmation": True}
               for text in subjects[:COMMIT_CAP]]
    payload = {
        "ok": True, "ref": ref, "writes": False,
        "needs_confirmation": True, "issues": "not read",
        "truncated": over > 0 or len(subjects) > COMMIT_CAP,
        "files": files, "commits": commits,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def cmd_propose(summary, files=""):
    # implements: REQ-PROPOSE-1093
    """Print one draft requirement. Writes nothing."""
    text = _one_line(summary)
    if not text:
        print("reqmap init: --propose needs a description", file=sys.stderr)
        return 2
    named = [part.strip().replace("\\", "/")
             for part in (files or "").split(",") if part.strip()]
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:4].upper()
    sys.stdout.write(_draft_md(
        "DRAFT-NOTE-" + digest, _title_from(text), text, named))
    print("reqmap: draft only, not written. A person sets "
          "status: confirmed after reading it.", file=sys.stderr)
    return 0


def dispatch_adopt(args, code_root):
    # implements: ARCH-ADOPT-075
    # implements: REQ-WATCH-1092  # implements: REQ-PROPOSE-1093
    if args.propose_files and not args.propose:
        print("reqmap init: --propose-files needs --propose",
              file=sys.stderr)
        return 2
    if args.watch and args.propose:
        print("reqmap init: pass --watch or --propose, not both",
              file=sys.stderr)
        return 2
    if args.propose:
        return cmd_propose(args.propose, args.propose_files or "")
    return cmd_watch(code_root, args.watch)
