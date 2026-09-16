"""Scaffolding a requirement (`new`, `--from-todo`) and rewriting a frontmatter status."""
import os, re

from .model import VALID_LAYER
from .parse import split_requirement_blocks
from .tags import _ID_PAT


# Built-in scaffold so `new` needs no separate templates/ dir — the engine is
# self-contained (one file). An on-disk templates/requirement.md still overrides
# it when cmd_new is given a tmpl_path that exists.
REQUIREMENT_TEMPLATE = """\
---
id: AREA-NAME-NNN
status: draft        # draft | baseline | in-progress | implemented | confirmed | deprecated
layer: feature       # bus | feature | need | aggregate
owner: Alex
priority:            # must-have | should-have | could-have | wont-have (optional)
depends_on: []       # ids of bus/other capabilities this builds on
superseded_by:       # <ID>, if replaced
# level:             # optional: system | architecture | code — the V-model left arm.
#                    #   Adopting it turns on the level-fit and rung checks; a corpus
#                    #   that never sets it keeps the pre-V-model behaviour exactly.
# satisfies: []      # optional: the level above this one (system <- architecture <- code)
# area:              # optional: System Map grouping label (else the id prefix is used)
---

# Short name

## Description
> 1–3 plain sentences anyone can follow — what this is, why it exists, and what
> breaks without it. No jargon; this is the angle a non-expert reads first. The
> quote is rationale, not an obligation: it is not hashed and never trips drift.

Every bullet below is binding.
<!-- Audience: a developer new to this project. Six rules:
     1. Name the subject: "`init` creates the folder", never "It creates the folder".
     2. Present tense — no "shall", no "must". The line above already binds every clause.
     3. One binding statement per bullet, in at most three sentences; the extra
        sentences state the first's consequence, never a second obligation.
     4. Define project-specific terms inline on first use; programming terms need none.
     5. Group clauses past five, with bold labels (see below).
     6. Keep a clause to at most 3 sentences and 150 words — `lint` enforces both.
     Scope: one capability = one behavior that fails independently. Many clauses AND
     many acceptance criteria together mean several capabilities — split them
     (`lint` flags this as 'over-scoped'). -->

**What it does**
- `<subject>` does one thing, stated so a test could check it. No function names; true
  regardless of how the code is implemented.
  <!-- Rationale: why this specific behavior, one clause, only when not self-evident -->

**What it produces**
- `<subject>` returns <output shape and allowed values>.
- `<subject>` handles a missing or invalid optional input by <behavior>.

## Verify intent (open questions for the human)
- Observed: <a behavior that may be an AI accident — swallowed error, empty-string
  fallback, magic constant, unreachable branch>. Intended, or a bug to fix?

## Cases (= tests)
<!-- Write at least one case from the CALLER's side, not the implementation's: the
     cases an author reaches for first vary the quality of one kind of input and
     never its kind. `clarify` names that shape (case-monoculture).
     Keep Given/When/Then concrete and self-explanatory; spell out any term the
     Description introduced. -->
CASE-1  <!-- verifiable by: automated test | manual | inspection | load test -->
  Given  <precondition>
  When   <action>
  Then   <observable, pass/fail result>   (one test per case; each maps to tested-by)

## Context (non-binding)
<!-- Everything here is commentary: not hashed, not linted, never trips drift. On
     any conflict with the Description + Cases above, they win. Bold sub-labels
     are the same clause-group convention the Description uses (ADR-0017) — keep
     only the ones you need. -->
**Notes**
- A known fragility/footgun the implementer should know but which is NOT enforced.

**Example**
- e.g. Ana marks AUTH-001 confirmed, later edits its contract text; at commit
  `check` tells her "DRIFT — contract changed since lock" so she re-reviews.

**Current implementation**
- How the code does it today (the volatile narrative — may drift from the contract).

"""


_REQ_ID_RE = re.compile(r"\A" + _ID_PAT + r"\Z")


def _reject_bad_id(cap_id):  # implements: ARCH-NEW-004  # implements: REQ-NEW-881
    """Print why `cap_id` cannot be a requirement id and return True, or return False.

    The id is not decoration: it is the string a `# implements:` tag has to spell, and
    `TAG_RE` only ever matches `_ID_PAT`. Scaffolding `my req.md` therefore minted a
    requirement no tag could ever name — a permanent RM006 error with no legal fix but
    deleting the file — and a `../` or `A/B` id wrote outside the requirements
    directory entirely. Both are refused at the door instead."""
    if _REQ_ID_RE.match(cap_id or ""):
        return False
    print("invalid id {!r}: a requirement id is what a `# implements:` tag must spell — "
          "two or more UPPERCASE parts joined by '-' (AREA-NAME-NNN), letters and digits "
          "only. Nothing else can ever be tagged in code.".format(cap_id))
    return True


def _warn_number_collision(reqs_dir, cap_id):  # implements: ARCH-NEW-004
    """Advisory: another requirement in the same area already uses this NNN. Ids are
    unique by their full text, so nothing breaks — but ARCH-MAP-007 beside
    ARCH-VIEWER-007 is the kind of pair people talk past each other about."""
    parts = cap_id.split("-")
    if len(parts) < 3:
        return
    area, num = parts[0], parts[-1]
    try:
        names = sorted(os.listdir(reqs_dir))
    except OSError:
        return
    for fn in names:
        if not fn.endswith(".md") or fn.startswith("_"):
            continue
        other = fn[:-3]
        op = other.split("-")
        if other != cap_id and len(op) >= 3 and op[0] == area and op[-1] == num:
            print("WARN  {} already uses number {} in area {} — ids stay unique by their "
                  "full text, but a distinct NNN keeps the two from being confused.".format(
                      other, num, area))


def cmd_new(reqs_dir, tmpl_path, cap_id):
    # implements: ARCH-NEW-004  # implements: REQ-NEW-881  # implements: REQ-NEW-882
    """Scaffold one blank requirement from the template and return an exit code;
    refuses rather than overwriting a file that already exists."""
    if _reject_bad_id(cap_id):
        return 2
    dest = os.path.join(reqs_dir, cap_id + ".md")
    if os.path.exists(dest):
        print(f"exists: {dest}"); return 1
    t = None
    if tmpl_path:                      # an on-disk template, if supplied, wins
        try:
            with open(tmpl_path, encoding="utf-8") as f:
                t = f.read()
        except OSError:
            t = None
    if t is None:                      # otherwise use the built-in scaffold
        t = REQUIREMENT_TEMPLATE
    t = t.replace("AREA-NAME-NNN", cap_id)
    os.makedirs(reqs_dir, exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        f.write(t)
    print(f"created {dest}")
    _warn_number_collision(reqs_dir, cap_id)
    return 0


def cmd_promote_todo(reqs_dir, tmpl_path, name, cap_id, mark_done=False, root="."):
    # implements: ARCH-PROMOTE-TODO-001  # implements: REQ-PROMOTE-TODO-897
    # implements: REQ-PROMOTE-TODO-898  # implements: REQ-PROMOTE-TODO-899
    """Scaffold a requirement draft from an unfinished TODO.md item (matched by name),
    seeding title / layer / milestone from the item. Requires an explicit cap_id — the
    engine runs headless (CI, pre-commit hook), so there is no interactive prompt. With
    mark_done it flips the matched TODO line to [x]; otherwise TODO.md is never touched."""
    if not cap_id:
        print('usage: reqmap new --from-todo "<todo name>" --id AREA-NAME-NNN [--mark-done]')
        return 2
    if _reject_bad_id(cap_id):
        return 2
    key = name.strip().casefold()
    open_todos = [t for t in _parse_todos(root) if not t["done"]]
    matches = [t for t in open_todos if t["name"].strip().casefold() == key]
    if not matches:
        avail = "; ".join(t["name"] for t in open_todos) or "(none)"
        print(f"no open TODO named {name!r}. Open items: {avail}"); return 1
    if len(matches) > 1:
        where = ", ".join(t["milestone"] for t in matches)
        print(f"ambiguous: {len(matches)} open TODOs named {name!r} (milestones {where}) "
              f"— rename to disambiguate")
        return 1
    todo = matches[0]
    dest = os.path.join(reqs_dir, cap_id + ".md")
    if os.path.exists(dest):
        print(f"exists: {dest}"); return 1
    t = None
    if tmpl_path:
        try:
            with open(tmpl_path, encoding="utf-8") as f:
                t = f.read()
        except OSError:
            t = None
    if t is None:
        t = REQUIREMENT_TEMPLATE
    # 'ops' is a TODO lane, not a layer
    layer = todo["lane"] if todo["lane"] in VALID_LAYER else "feature"
    t = t.replace("AREA-NAME-NNN", cap_id)
    t, _layer_n = re.subn(r"(?m)^layer:\s*feature\b", f"layer: {layer}", t, count=1)
    if _layer_n == 0:
        print(f"warning: template has no 'layer: feature' anchor; layer {layer!r} not recorded")
    # inject milestone at the template's anchor; if a custom template lacks it,
    # fall back to the frontmatter fence, else warn rather than silently drop it
    if "superseded_by:" in t:
        t = t.replace("superseded_by:", f"milestone: {todo['milestone']}\nsuperseded_by:", 1)
    elif t.startswith("---\n"):
        t = t.replace("---\n", f"---\nmilestone: {todo['milestone']}\n", 1)
    else:
        print(f"warning: template has no frontmatter anchor; milestone "
              f"{todo['milestone']} not recorded")
    if "# Short name" in t:
        t = t.replace("# Short name", "# " + todo["name"], 1)
    else:
        print(f"warning: template has no '# Short name' title anchor; TODO title "
              f"{todo['name']!r} not inserted")
    os.makedirs(reqs_dir, exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        f.write(t)
    print(f"created {dest} (draft, milestone {todo['milestone']}, layer {layer}) "
          f"from TODO {todo['name']!r}")
    _warn_number_collision(reqs_dir, cap_id)
    if mark_done:
        n = _mark_todo_done(root, todo["name"])
        print(f"marked TODO {todo['name']!r} done in TODO.md" if n
              else "warning: could not mark the TODO done (TODO.md not writable or line not found)")
    return 0


def _mark_todo_done(root, name):
    # implements: ARCH-PROMOTE-TODO-001  # implements: REQ-PROMOTE-TODO-899
    """Flip the first unfinished TODO.md line whose name matches to [x]. Best-effort:
    returns 1 if a line was rewritten, 0 if TODO.md is absent/unwritable or no line matched."""
    key = name.strip().casefold()
    for base in dict.fromkeys([root, os.path.dirname(os.path.abspath(root))]):
        path = os.path.join(base, "TODO.md")
        if not os.path.exists(path):
            continue
        try:
            with open(path, encoding="utf-8", newline="") as f:
                lines = f.readlines()
        except OSError:
            # unreadable here -> try the next candidate (parent), like _parse_todos
            continue
        changed = 0
        for i, line in enumerate(lines):
            m = re.match(r"^(\s*-\s+\[)[ ](\]\s+)(.+?)(\r?\n?)$", line)
            # rsplit on the LAST '|' to mirror _parse_todos_from_text's name
            # derivation — else a TODO whose name contains a '|' never matches
            if m and m.group(3).rsplit("|", 1)[0].strip().casefold() == key:
                lines[i] = m.group(1) + "x" + m.group(2) + m.group(3) + m.group(4)
                changed = 1
                break
        if changed:
            try:
                with open(path, "w", encoding="utf-8", newline="") as f:
                    f.writelines(lines)
            except OSError:
                return 0
        return changed
    return 0


def _set_frontmatter_status(text, value):
    # implements: ARCH-PROMOTE-011  # implements: REQ-PROMOTE-894
    """Replace the value of the first `status:` line inside the leading frontmatter
    block, preserving its indentation and any trailing inline comment. Returns
    (new_text, n_replaced); n=0 when there is no frontmatter or no status line."""
    body = text.lstrip("﻿")            # drop a BOM if present (rewritten without it)
    if not body.startswith("---"):
        return text, 0
    end = body.find("\n---", 3)
    if end == -1:
        return text, 0
    head, rest = body[:end], body[end:]     # only the frontmatter block, never the body
    # Replace only the VALUE, keeping any trailing inline comment (and its spacing).
    # The value group excludes '#' so a blank `status:  # hint` line is filled in
    # place instead of swallowing the '#' as the value (which glued the leftover
    # comment text onto the status, corrupting the YAML).
    def _repl(m):
        comment = m.group(3)
        if comment:
            return m.group(1) + " " + value + (m.group(2) or "  ") + comment
        return m.group(1) + " " + value
    new_head, n = re.subn(
        r"(?m)^([ \t]*status[ \t]*:)[ \t]*[^#\r\n]*?([ \t]*)(#[^\r\n]*)?$",
        _repl, head, count=1)
    return new_head + rest, n


def _write_frontmatter_status(r, new_status):  # implements: ARCH-PROMOTE-011
    """Set one requirement's `status:` in its own file, in place. Returns True on a
    write, False when the block has no `status:` line to change.

    newline="" on both ends: read/write the file's own line endings verbatim so a
    CRLF-committed requirement file isn't silently flipped to LF on a POSIX host
    (universal-newline translation on read + os.linesep on write would do exactly
    that). Per-line EOL, so a file with MIXED line endings keeps every untouched
    bare-LF line bare-LF — only the substituted VALUE changes."""
    with open(r["path"], encoding="utf-8-sig", newline="") as f:
        raw = f.read()
    orig_lines = raw.splitlines(keepends=True)
    line_eols = [ln[len(ln.rstrip("\r\n")):] for ln in orig_lines]
    eol = "\r\n" if "\r\n" in raw else "\n"
    text = raw.replace("\r\n", "\n") if eol == "\r\n" else raw
    # A module file holds several requirements; flip the status of THIS one, not of
    # the first block in the file.  # implements: REQ-MODULEFILE-056
    blocks = split_requirement_blocks(text)
    if len(blocks) > 1:
        idx = r.get("block", 0)
        blocks[idx], n = _set_frontmatter_status(blocks[idx], new_status)
        new_text = "".join(blocks)
    else:
        new_text, n = _set_frontmatter_status(text, new_status)
    if n == 0:
        return False
    new_lines = new_text.splitlines()
    if len(new_lines) == len(line_eols):
        new_text = "".join(nl + le for nl, le in zip(new_lines, line_eols))
    elif eol == "\r\n":
        new_text = new_text.replace("\n", "\r\n")
    with open(r["path"], "w", encoding="utf-8", newline="") as f:
        f.write(new_text)
    return True


def _parse_todos_from_text(text):
    """Parse TODO.md content → list of {name, lane, milestone, done} dicts. Pure.
    Items before the first ## vX.Y heading are silently ignored (milestone is required)."""
    todos, current_ms = [], None
    for line in text.splitlines():
        # match the version token at the heading start; a trailing annotation
        # like `## v2.8 (deferred — demand-gated)` is harmless (the capture group
        # isolates the version) and must not drop the milestone's items.
        ms_m = re.match(r"^##\s+(v\d[\d.]*)\b", line.strip())
        if ms_m:
            current_ms = ms_m.group(1)
            continue
        item_m = re.match(r"^-\s+\[([ xX])\]\s+(.+)$", line.strip())
        if item_m and current_ms:
            done = item_m.group(1).lower() == "x"
            rest = item_m.group(2)
            if "|" in rest:
                name_part, meta = rest.rsplit("|", 1)
                name = name_part.strip()
                # one word: bug|feature (bus|ops still parse; the roadmap files them as features)
                lane_m = re.search(r"lane:\s*(\w+)", meta)
                lane = lane_m.group(1) if lane_m else "feature"
            else:
                name, lane = rest.strip(), "feature"
            todos.append({"name": name, "lane": lane, "milestone": current_ms, "done": done})
    return todos


def _parse_todos(root):  # implements: REQ-MAP-871
    """Read TODO.md; tries root first, then one level up (covers plugin/ dogfood layout).
    Returns list of todo dicts; empty list if absent in both locations."""
    for base in dict.fromkeys([root, os.path.dirname(os.path.abspath(root))]):
        path = os.path.join(base, "TODO.md")
        try:
            with open(path, encoding="utf-8") as f:
                return _parse_todos_from_text(f.read())
        except OSError:
            continue
    return []
