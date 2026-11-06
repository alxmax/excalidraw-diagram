"""`clarify --decompose` along contract groups: plan, render and write the
code-rung children.
"""
import os, re

from . import config as cfg
from .acceptance import _AC_LABEL_RE, _acc_blocks
from .sections import ACCEPTANCE_LABELS, CONTRACT_LABELS, _section_lines
from .text import _is_label_line


# ---------- decompose on contract groups: the code rung for a tagged
# corpus ----------
# `init` mints the code rung only for files it extracts, and it extracts only
# untagged files; `clarify --levels` classifies a requirement but never
# creates one. So a corpus that adopted the tool at the architecture rung had
# no path to `level: code` at all — on one consumer, 40 of 42 architecture
# nodes with zero children and 160 group labels sitting in their contracts.
# This is the path. The seam is one the AUTHOR already drew: a bold group
# label in the Description is a heading the author wrote to say "these
# clauses belong together", and a behaviour group is what the code rung is
# defined as. It is not the engine inventing structure; it is the engine
# reading structure that is already in the file, which is the line ADR-0025
# had to refold 573 leaves back behind.

GROUP_CHILD_TEMPLATE = """---
id: {new_id}
status: draft
level: code
level_source: auto
layer: {layer}
owner: {owner}
satisfies: [{parent}]
---

# {title}

<!-- decomposed-from: {parent}#group:{slug} -->

## Description
> Split from {parent} along a contract group the author wrote: **{label}**. \
Rewrite this
> quote before confirming — say what this behaviour is for and what breaks \
without it.

Every bullet below is binding.
{bullets}

## Cases
{cases}

## Context
**Notes**
- SCAFFOLD, NOT A DECISION. The seam was the parent's own group label, not a \
guess, but
  whether this group is ONE behaviour or several is still yours to judge.
- No `implements:` tag was written. The gate checks that a tag exists, \
never that it
  points at the right code, so an auto-generated child citing the wrong \
function would
  pass every check. Expected members, found by searching for the group's \
subject —
  verify each, then tag by hand:
{members}
- {copied} case(s) copied here from {parent}; {unassigned} of the parent's \
cases went to no
  child because no group's subject appeared in their text, or more than one did.
- {parent} was not edited: its Description still holds this group's \
clauses, so deleting
  this file loses nothing. Once this child is confirmed, trimming the \
parent is yours to do.
"""


_LABEL_WITH_TAIL_RE = re.compile(r"\*\*([^*]+)\*\*\s+\S")


def _group_label(raw):  # implements: REQ-DECOMPOSE-994
    """The group label a flush-left line opens, or None. `**Label**` alone
    is one, and so is `**Label** (a note on it)`: a bold span opening a
    flush-left line that is not a bullet is a heading the author wrote.
    Reading only the bare form glued the second shape, label and all, onto
    the previous group's last clause — five groups became three children."""
    if _is_label_line(raw):
        return raw.strip().strip("*").strip()
    m = None if raw[:1].isspace() else _LABEL_WITH_TAIL_RE.match(raw)
    return m.group(1).strip() if m else None


def _contract_groups(body):
    # implements: ARCH-DECOMPOSE-050  # implements: REQ-DECOMPOSE-994
    """`[(label, [clause, ...]), ...]` — the bold group labels in the
    Description and the bullets under each, in order. A bullet before the
    first label belongs to no group and is not returned: it is the parent's
    own preamble, and it stays there."""
    out, cur = [], None
    for raw in _section_lines(body, CONTRACT_LABELS, raw=True):
        s = raw.strip()
        label = _group_label(raw)
        if label:
            cur = (label, [])
            out.append(cur)
        elif cur is not None and (s == "-" or s.startswith("- ")):
            cur[1].append(s[1:].strip())
        elif (cur is not None and cur[1] and s
              and not s.startswith(("|", ">", "#", "<!--"))):
            # hanging-indent continuation of the last clause
            cur[1][-1] += " " + s
    return [(label, clauses) for label, clauses in out if clauses]


def _group_subject(label):  # implements: REQ-DECOMPOSE-994
    """The identifier a case or a member would name:
    `load_json_stdin(script_name)` -> `load_json_stdin`; `Falsifiability
    anchor (Law 8)` -> `Falsifiability anchor`. Backticks and a
    parenthesised tail are presentation, not identity."""
    return re.sub(r"\s*\(.*$", "", label.replace("`", "").strip()).strip()


def _group_slug(label):  # implements: REQ-DECOMPOSE-994
    slug = re.sub(r"[^A-Za-z0-9]+", "-", _group_subject(label))
    return slug.strip("-").upper() or "GROUP"


def _group_child_id(parent_id, label, reqs, reqs_dir):
    # implements: REQ-DECOMPOSE-994
    """`<parent>-<SLUG>`, with a trailing `-NNN` on the parent dropped
    first so the child reads `SCRIPTS-UTILS-LOAD-JSON-STDIN` rather than
    `REQ-FOO-012-LOAD-JSON-STDIN`. On collision a `-2`, `-3` suffix; the
    number sits last, where `_next_free_number` and
    `_warn_number_collision` expect one."""
    parts = parent_id.split("-")
    stem = ("-".join(parts[:-1])
            if len(parts) >= 3 and parts[-1].isdigit() else parent_id)
    base = "{}-{}".format(stem, _group_slug(label))
    taken = set(reqs or ())
    try:
        taken |= {fn[:-3] for fn in os.listdir(reqs_dir) if fn.endswith(".md")}
    except OSError:
        pass
    cand, k = base, 2
    while cand in taken:
        cand = "{}-{}".format(base, k); k += 1
    return cand


def _case_raw_blocks(body):  # implements: REQ-DECOMPOSE-994
    """`{label: [line, ...]}` — each labelled case's own lines, indentation
    kept, so a copied case reads in the child exactly as it read in the
    parent. `_acc_blocks` folds a case to one line for counting and search;
    a Given/When/Then block is worth more than that on the page."""
    out, cur = {}, None
    for raw in _section_lines(body, ACCEPTANCE_LABELS, raw=True):
        m = _AC_LABEL_RE.match(raw.strip())
        if m:
            cur = m.group(1)
            out[cur] = [raw.rstrip()]
        elif cur is not None and raw.strip():
            out[cur].append(raw.rstrip())
    return out


def _assign_cases(blocks, groups):  # implements: REQ-DECOMPOSE-994
    """Which child each parent case belongs to: `{case_index: group_index}`
    for the cases whose text names exactly ONE group's subject. Zero
    matches or two-plus is left on the parent — assigning by guess is the
    failure mode, and reporting the unassigned count is the feature."""
    # whole-word: `is_headless` must not claim a case about
    # `is_headless_mode`. A generic label such as **Module** still matches
    # "the module is imported" — that is the rule working, and the reason
    # every move is printed for a human to read.
    subjects = [
        re.compile(r"(?<![\w])" + re.escape(_group_subject(label).lower())
                   + r"(?![\w])") if _group_subject(label) else None
        for label, _ in groups]
    owner = {}
    for i, blk in enumerate(blocks):
        text = (blk.get("text", "") + " " + blk.get("label", "")).lower()
        hits = [g for g, rx in enumerate(subjects) if rx and rx.search(text)]
        if len(hits) == 1:
            owner[i] = hits[0]
    return owner


def _first_hit_line(code_root, rel, needle):
    # implements: REQ-DECOMPOSE-994
    """The first `file:line` in `rel` whose text matches `needle` on a
    def/class/function line, or None — one file's worth of
    `_expected_members`'s search."""
    fdef = r"\b(def|class|function|func|fn)\b"
    try:
        with open(os.path.join(code_root, rel), encoding="utf-8",
                  errors="ignore") as f:
            for n, line in enumerate(f, 1):
                if needle.search(line) and re.search(fdef, line):
                    return "{}:{}".format(rel, n)
    except OSError:
        return None
    return None


def _expected_members(code_root, members, label):
    # implements: REQ-DECOMPOSE-994
    """`file:line` hits for the group's subject inside the parent's
    `implements:` files — the code a child is EXPECTED to claim. Listed,
    never tagged."""
    subj = _group_subject(label)
    if not subj or not code_root:
        return []
    needle = re.compile(re.escape(subj))
    hits, seen = [], set()
    for role, rel, _ln in members or []:
        if role != "implements" or rel in seen:
            continue
        seen.add(rel)
        hit = _first_hit_line(code_root, rel, needle)
        if hit:
            hits.append(hit)
    return hits


def _plan_group_split(rid, r, reqs, reqs_dir, code_root, members):
    # implements: REQ-DECOMPOSE-994
    """Everything a run would do to ONE requirement, computed without
    writing: the children, each child's clauses and cases, the expected
    members, what stays on the parent, and why the run refuses if it does.
    Dry-run prints this; --apply executes it."""
    body = r["body"]
    groups = _contract_groups(body)
    plan = {"id": rid, "groups": groups, "children": [], "refuse": None}
    if len(groups) < 2:
        plan["refuse"] = ("fewer than two contract groups — nothing to "
                          "split along")
        return plan
    if len(groups) > cfg.LINT_AC_MAX:
        plan["refuse"] = (
            "{} groups is {} children for one capability, which is the "
            "shape ADR-0025 had to refold. Merge the labels down to {} "
            "or fewer, then re-run.".format(
                len(groups), len(groups), cfg.LINT_AC_MAX))
        return plan
    blocks = _acc_blocks(body)
    raw_by_label = _case_raw_blocks(body)
    owner = _assign_cases(blocks, groups)
    used = set()
    for g, (label, clauses) in enumerate(groups):
        cases = [
            {"label": blocks[i]["label"],
             "lines": raw_by_label.get(blocks[i]["label"], [blocks[i]["text"]])}
            for i, og in sorted(owner.items()) if og == g]
        cid = _group_child_id(rid, label, set(reqs) | used, reqs_dir)
        used.add(cid)
        plan["children"].append({
            "id": cid, "label": label, "subject": _group_subject(label),
            "clauses": clauses, "cases": cases,
            "members": _expected_members(code_root, members, label),
        })
    plan["copied_cases"] = len(owner)
    plan["unassigned_cases"] = len(blocks) - len(owner)
    plan["unassigned_case_labels"] = [
        b.get("label", "") for i, b in enumerate(blocks) if i not in owner]
    return plan


def _render_group_child(plan_child, parent_id, meta, unassigned):
    # implements: REQ-DECOMPOSE-994
    c = plan_child
    bullets = "\n".join("- " + cl for cl in c["clauses"])
    if c["cases"]:
        parts = []
        for n, blk in enumerate(c["cases"], 1):
            lines = list(blk["lines"])
            first = lines[0].strip() if lines else ""
            m = _AC_LABEL_RE.match(first)
            title = first[m.end():].strip(" —-–:") if m else ""
            head = "CASE-{}".format(n) + (" — " + title if title else "")
            body_lines = [l for l in lines[1:]]
            parts.append("\n".join([head] + body_lines))
        cases = "\n\n".join(parts)
    else:
        cases = ("CASE-1\n  Given  <precondition>\n  When   <action>\n"
                 "  Then   <observable, pass/fail result>")
    members = "\n".join("  - `{}`".format(m) for m in c["members"]) or (
        "  - (none found — search the parent's members for `{}` "
        "yourself)".format(c["subject"]))
    return GROUP_CHILD_TEMPLATE.format(
        new_id=c["id"], parent=parent_id, slug=_group_slug(c["label"]),
        label=c["label"],
        title=c["subject"] or c["label"], bullets=bullets, cases=cases,
        members=members,
        layer=meta.get("layer", "feature") or "feature",
        owner=meta.get("owner", "") or "",
        copied=len(c["cases"]), unassigned=unassigned)


def _plan_and_report(targets, reqs, reqs_dir, code_root, members):
    # implements: ARCH-DECOMPOSE-050  # implements: REQ-DECOMPOSE-994
    """Plan every target's split and print each one's summary as it is
    computed. Returns (plans, total_children, total_copied,
    total_unassigned)."""
    total_children = total_copied = total_unassigned = 0
    plans = []
    for rid in targets:
        plan = _plan_group_split(
            rid, reqs[rid], reqs, reqs_dir, code_root, members.get(rid))
        plans.append(plan)
        print("{}  ({} contract groups, {} cases)".format(
            rid, len(plan["groups"]), len(_acc_blocks(reqs[rid]["body"]))))
        if plan["refuse"]:
            print("  refused: {}".format(plan["refuse"]))
            for label, clauses in plan["groups"]:
                print("    **{}**  {} clause(s)".format(label, len(clauses)))
            continue
        for c in plan["children"]:
            print(
                "  -> {:<40} {} clause(s), {} case(s), "
                "{} expected member(s)".format(
                    c["id"], len(c["clauses"]), len(c["cases"]),
                    len(c["members"])))
        print("  {} case(s) go to no child{}".format(
            plan["unassigned_cases"],
            ": " + ", ".join(l for l in plan["unassigned_case_labels"] if l)
            if plan["unassigned_cases"] else ""))
        total_children += len(plan["children"])
        total_copied += plan["copied_cases"]
        total_unassigned += plan["unassigned_cases"]
    return plans, total_children, total_copied, total_unassigned


def _write_group_split(plans, reqs, reqs_dir):
    # implements: ARCH-DECOMPOSE-050  # implements: REQ-DECOMPOSE-994
    """Write every plan's children; the parent is never opened for
    writing. Returns files written."""
    written = 0
    for plan in plans:
        if plan["refuse"]:
            continue
        rid = plan["id"]; r = reqs[rid]
        for c in plan["children"]:
            dest = os.path.join(reqs_dir, c["id"] + ".md")
            if os.path.exists(dest):
                print("  SKIP  {} exists".format(dest)); continue
            with open(dest, "w", encoding="utf-8") as f:
                f.write(_render_group_child(
                    c, rid, r["meta"], plan["unassigned_cases"]))
            print("  wrote  requirements/{}.md".format(c["id"]))
            written += 1
    return written


def decomposable(r):
    # implements: ARCH-DECOMPOSE-050  # implements: REQ-DECOMPOSE-994
    """True when a requirement's own group labels can be split into
    code-rung children: two or more groups, and not already at
    `level: code`. A code requirement's children would sit below the
    lowest rung there is, so its groups are its own structure, not
    seams to split along."""
    return (r["meta"].get("level") != "code"
            and len(_contract_groups(r["body"])) >= 2)


def cmd_decompose_groups(ws, only=None, apply_it=False, code_root=None):
    # implements: ARCH-DECOMPOSE-050  # implements: REQ-DECOMPOSE-994
    """Split a requirement into code-rung children along its own contract
    group labels.

    Returns None when nothing in scope carries a group, so the caller can
    fall through to the older clause-level path. Otherwise prints the plan
    and — with `apply_it` — writes the children, returning 0.

    The parent is NEVER edited: each child is a copy of its group's
    clauses and cases. Moving the text instead once left 33 parents
    holding nothing but `see [[child]]` pointers, so rejecting a split —
    deleting its children — silently destroyed the contracts they had
    taken with a green gate. A copy makes every split undoable by
    deleting files. Trimming the parent once a child is confirmed is the
    author's edit, and RM036 reports any `[[ID]]` the trimmed Description
    is then left pointing at in vain."""
    reqs, reqs_dir = ws.reqs, ws.reqs_dir
    members = ws.members or {}
    if only and reqs[only]["meta"].get("level") == "code":
        print("{} is at `level: code`: its groups are its own structure, "
              "and a child would sit below the code rung. Nothing to "
              "split.".format(only))
        return 0
    targets = ([only] if only
               else [rid for rid in sorted(reqs) if decomposable(reqs[rid])])
    if only and len(_contract_groups(reqs[only]["body"])) < 2:
        return None
    if not targets:
        return None
    plans, total_children, total_copied, total_unassigned = _plan_and_report(
        targets, reqs, reqs_dir, code_root, members)
    n_planned = sum(1 for p in plans if not p["refuse"])
    print("\n{} child requirement(s) from {} parent(s); {} case(s) copied "
          "to a child, {} "
          "to none.".format(
              total_children, n_planned, total_copied, total_unassigned))
    print("Children carry `level: code`, `level_source: auto`, "
          "`satisfies: <parent>`, "
          "`status: draft`.")
    print("No member tags are written — each child lists the members it "
          "is expected to claim.")
    print("The parent is not edited: its clauses and cases are copied, "
          "never moved.")
    if not apply_it:
        print("\nNothing written. Re-run with --apply; delete the "
              "children to undo.")
        return 0
    written = _write_group_split(plans, reqs, reqs_dir)
    print("\n{} file(s) written. Next: review each child, tag its "
          "members, then `reqmap.py "
          "sync`.".format(written))
    return 0
