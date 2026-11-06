"""TODO.md items: the checkbox line, the indented lines under it and the
`| key: value` suffix. Imported at call time by `author._parse_todos_from_text`,
so only a repository that keeps a TODO.md ever loads it."""
import re
import textwrap

_META_RE = re.compile(r"^\s*\w+:")


def split_meta(rest):
    """(name, meta) of an item line. Only trailing `| key: value` segments
    are metadata, so a `|` inside the title (`a|b` in code) stays in it."""
    # implements: REQ-ROADMAP-907
    # implements: REQ-TODODETAIL-1096
    name, meta = rest, ""
    while True:
        head, sep, tail = name.rpartition("|")
        if not sep or not _META_RE.match(tail):
            return name.strip(), meta
        name, meta = head, tail + " " + meta


def parse_todos(text, not_milestone_re):
    """list of {name, lane, milestone, done[, detail]} from TODO.md text.
    `detail` is the item's indented non-item lines, dedented, and is absent
    when the item has none. Pure."""
    # implements: REQ-ROADMAP-907
    # implements: REQ-TODODETAIL-1096
    todos, current_ms, last = [], None, None
    for line in text.splitlines():
        stripped = line.strip()
        # the version token at the heading start; a trailing annotation like
        # `## v2.8 (deferred — demand-gated)` is harmless
        ms_m = re.match(r"^##\s+(v\d[\d.]*)\b", stripped)
        if ms_m or (stripped.startswith("## ") and not_milestone_re.search(line)):
            current_ms, last = (ms_m.group(1) if ms_m else None), None
            continue
        item_m = re.match(r"^-\s+\[([ xX])\]\s+(.+)$", stripped)
        if item_m and current_ms:
            name, meta = split_meta(item_m.group(2))
            # one word: bug|feature (bus|ops still parse; the roadmap files
            # them as features)
            lane_m = re.search(r"lane:\s*(\w+)", meta)
            last = {"name": name, "lane": lane_m.group(1) if lane_m else "feature",
                    "milestone": current_ms,
                    "done": item_m.group(1).lower() == "x"}
            todos.append(last)
        elif stripped and line[0] in " \t" and last is not None:
            last["detail"] = last.get("detail", "") + line.rstrip() + "\n"
        elif stripped:
            last = None
    for item in todos:
        if "detail" in item:
            item["detail"] = textwrap.dedent(item["detail"]).strip("\n")
    return todos
