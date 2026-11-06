"""What the planning sidecar's reader dropped, repaired or never read.

`load_targets` is fail-open by design: a bar with a mistyped date leaves
the chart, an `end` it cannot read becomes the `start`, a file that is not
JSON reads as an empty plan. Each is right for a renderer and wrong for
the author, who saw nothing. This module says each one out loud.

It re-runs no parsing of its own. Each check hands the raw value to the
same `_parse_*` function `load_targets` uses and compares what comes back,
so the list and the chart cannot disagree about what was lost. It is
loaded only for a repository that has a planning file (ADR-0057).
"""
import os

from .targets import (PLANNING_FILES, _parse_bar, _parse_cadence,
                      _parse_milestone_entry, _read_planning_file,
                      load_targets)

# The keys `load_targets` reads. Anything else is carried in the file and
# read by nobody; `_comment` is where the file's own prose belongs.
_READ_KEYS = {
    "top": ("_comment", "lanes", "cadence", "bars", "milestones"),
    "bar": ("title", "name", "start", "end", "due", "lane", "milestone",
            "req", "reqId", "id", "progress", "roadmap"),
    "milestone": ("due", "label", "note"),
}


def plan_input_findings(reqs_dir, reqs, code_root=None):
    # implements: REQ-PLANINPUT-1086
    """Every RM037 message: the file's own problems, then each bar whose
    `req:` names no requirement or a deprecated one, or whose `roadmap:`
    names no ROADMAP item. Fail-open: a plan never breaks the verdict."""
    try:
        return _plan_input_findings(reqs_dir, reqs, code_root)
    except Exception:
        return []


def _plan_input_findings(reqs_dir, reqs, code_root):
    # implements: REQ-PLANINPUT-1086
    out = plan_input_problems(reqs_dir)
    bars = load_targets(reqs_dir).get("bars", [])
    if any(b.get("roadmap") for b in bars):
        from .mapdata import _read_roadmap
        names = {it["name"].strip().lower()
                 for it in _read_roadmap(code_root or reqs_dir) or []}
        out.extend(
            "_planning.json: bar {!r} links ROADMAP item {!r} - no such "
            "item".format(b["title"][:60], b["roadmap"][:60])
            for b in bars
            if b.get("roadmap") and b["roadmap"].lower() not in names)
    for bar in bars:
        rid = bar.get("req")
        r = reqs.get(rid) if rid else None
        if rid and (r is None or r["meta"].get("status") == "deprecated"):
            out.append("_planning.json: bar {!r} names {} - {}".format(
                bar["title"][:60], rid, "no such requirement"
                if r is None else "a deprecated requirement"))
    return out


def plan_input_problems(reqs_dir):
    # implements: REQ-PLANINPUT-1086
    """One message per value in the planning sidecar that `load_targets`
    drops, repairs, or reads but can never use. An unreadable file is one
    message, never an exception."""
    out = []
    for name in PLANNING_FILES:
        path = os.path.join(reqs_dir or ".", name)
        if not os.path.isfile(path):
            continue
        raw = _read_planning_file(path)
        if raw is None:
            out.append("{}: not valid JSON - read as an empty plan".format(
                name))
            continue
        if not isinstance(raw, dict):
            out.append("{}: the top level is not an object - read as an "
                       "empty plan".format(name))
            continue
        out.extend(_raw_plan_problems(name, raw))
        break
    return out


def _raw_plan_problems(name, raw):
    # implements: REQ-PLANINPUT-1086
    lanes = [s.strip() for s in raw.get("lanes") or []
             if isinstance(s, str) and s.strip()]
    out = []
    for i, bar in enumerate(raw.get("bars") or []):
        out.extend("{}: bars[{}]{}".format(name, i, msg)
                   for msg in _bar_problems(bar, lanes))
    # A milestone NAME that is not a version is not reported: a repo that
    # plans phases ("Deciziile luate", measured 2026-09-28) and never cuts a
    # release loses nothing from the chart, and five warnings on every
    # commit would be the noise ADR-0049 removed.
    milestones = raw.get("milestones")
    for key, entry in (milestones.items()
                       if isinstance(milestones, dict) else ()):
        if _parse_milestone_entry(entry) is None:
            out.append("{}: milestone {!r} has no YYYY-MM-DD `due` and no "
                       "label - dropped".format(name, key))
    if raw.get("cadence") is not None and \
            _parse_cadence(raw["cadence"]) is None:
        out.append("{}: `cadence` is not understood (every: week or "
                   "month) - no release dates are drawn".format(name))
    return out


def _bar_problems(bar, lanes):
    # implements: REQ-PLANINPUT-1086
    """Suffixes for one bar's messages: ` 'title': what went wrong`."""
    parsed = _parse_bar(bar)
    title = (bar.get("title") or bar.get("name")) \
        if isinstance(bar, dict) else None
    label = " {!r}".format(title[:60]) if isinstance(title, str) else ""
    if parsed is None:
        return [label + ": dropped - it needs a title and a YYYY-MM-DD "
                "`start`"]
    out = []
    raw_end = bar.get("end") or bar.get("due")
    if raw_end is not None and str(raw_end).strip() != parsed["end"]:
        out.append(label + ": `end` {!r} is not YYYY-MM-DD - `start` is "
                   "used instead".format(raw_end))
    if parsed["end"] < parsed["start"]:
        out.append(label + ": ends {} before it starts {}".format(
            parsed["end"], parsed["start"]))
    if lanes and parsed.get("lane") and parsed["lane"] not in lanes:
        out.append(label + ": lane {!r} is not in `lanes`".format(
            parsed["lane"]))
    return out


def plan_ignored_key_lines(reqs_dir):
    # implements: REQ-PLANINPUT-1086
    """One advisory line per key the planning sidecar carries and the
    engine never reads, naming where it appears. Never a gate rule: an
    ignored key changes nothing the engine computes, it only means the
    author wrote something the chart will not show."""
    for name in PLANNING_FILES:
        raw = _read_planning_file(os.path.join(reqs_dir or ".", name))
        if isinstance(raw, dict):
            break
    else:
        return []
    found = {}
    where = [("top", "", raw)]
    where += [("bar", "bars[{}]".format(i), b)
              for i, b in enumerate(raw.get("bars") or [])]
    milestones = raw.get("milestones")
    where += [("milestone", str(k), v) for k, v in (
        milestones.items() if isinstance(milestones, dict) else ())]
    for kind, label, obj in where:
        for key in (obj if isinstance(obj, dict) else ()):
            if key not in _READ_KEYS[kind]:
                found.setdefault((kind, key), []).append(label)
    return ["{}: key {!r} is read by nothing ({} {}{}) - move it to "
            "ROADMAP.md or `_comment`".format(
                name, key, kind, ", ".join(labels[:3]) or "top level",
                ", ..." if len(labels) > 3 else "")
            for (kind, key), labels in found.items()]
