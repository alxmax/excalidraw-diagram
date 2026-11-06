"""An audit session (ADR-0076): a plan written once, the findings and the
decisions a person records in one file, and a report that gives every rate
as k/n with its interval.

`requirements/_audit.json` is the session. `sync --audit-plan` writes its plan
and nothing else ever writes it: a review run adds findings and a person adds
decisions by editing the file, as a person sets `status: confirmed`. Imported
only when that file exists or an audit flag is given, so a repository that
never audits never loads it.
"""
# implements: ARCH-AUDITRUN-076
import datetime
import json
import math
import os
import random

from . import config as cfg
from .clarify import _clarify_questions, _domain_heads
from .model import _impl_exempt
from .scan import scan_ac_verifies
from .testgaps import case_gaps

AUDIT_FILE = "_audit.json"
AUDIT_SCHEMA = 1
LABELS = ("bug", "not-implemented", "false-coverage", "ok")
COUNTERS = ("B", "F_copilot", "G", "A", "F_tool", "M", "U")
ORDER_KEY = ("untested cases, then clarify questions, then linked files, "
             "all descending; ties by id ascending")
PROMPT = (
    "For each clause of this requirement: show the line of code that does it "
    "and the test that proves it. Say where the code does something other "
    "than the clause, where there is no code for it, and where the test does "
    "not actually check the case. Give every finding exactly one label: bug, "
    "not-implemented, false-coverage, or ok when the clause holds. Record each "
    "finding in requirements/_audit.json as {id, run, label, clause, note}. "
    "Never edit a requirement or its status.")


def audit_path(reqs_dir):
    return os.path.join(reqs_dir, AUDIT_FILE)


# ---------- the plan --------------------------------------------------------

def _eligible(reqs):
    # implements: REQ-AUDITRUN-1105
    """Confirmed requirements that carry code: a `need` or an `aggregate`
    has none to compare a clause with."""
    return sorted(rid for rid, r in reqs.items()
                  if r["meta"].get("status") == "confirmed"
                  and not _impl_exempt(r["meta"]))


def ordering(ws):
    # implements: REQ-AUDITRUN-1105
    """(rid, untested, questions, files) for every eligible requirement, in
    the ranked order of ORDER_KEY."""
    reqs = ws.reqs
    cover = ws.ac_cover if getattr(ws, "ac_cover", None) is not None else (
        scan_ac_verifies(ws.code_root, ws.reqs_dir) if ws.code_root else {})
    untested = {rid: n for rid, n, _total in case_gaps(reqs, cover)}
    domain = _domain_heads(reqs)
    rows = []
    for rid in _eligible(reqs):
        asked = len(_clarify_questions(rid, reqs[rid], reqs, domain))
        files = len({fp for _role, fp, _line in ws.members.get(rid, [])})
        rows.append((rid, untested.get(rid, 0), asked, files))
    return sorted(rows, key=lambda x: (-x[1], -x[2], -x[3], x[0]))


def build_plan(ws, ranked_n, random_n, seed, today):
    # implements: REQ-AUDITRUN-1105
    """The plan document: the ranked head of the ordering and a seeded draw
    from the rest, sorted by id before the draw so one seed is one set."""
    order = ordering(ws)
    ranked = [rid for rid, _u, _q, _f in order[:max(ranked_n, 0)]]
    rest = sorted(rid for rid, _u, _q, _f in order[max(ranked_n, 0):])
    drawn = random.Random(seed).sample(rest, min(max(random_n, 0), len(rest)))
    return {"schema": AUDIT_SCHEMA,
            "plan": {"date": today, "seed": seed, "key": ORDER_KEY,
                     "ranked": ranked, "random": sorted(drawn),
                     "bands": dict(cfg.AUDIT_BANDS),
                     "min_positives": cfg.AUDIT_MIN_POSITIVES},
            "findings": [], "decisions": []}


def cmd_audit_plan(ws, ranked_n=None, random_n=None, seed=None, today=None):
    # implements: REQ-AUDITRUN-1105
    """`sync --audit-plan`: write the plan once. An existing file is never
    replaced, readable or not; a new audit starts from a new file."""
    path = audit_path(ws.reqs_dir)
    if os.path.exists(path):
        print("audit: {} already exists; the plan is written once. Start a "
              "new audit from a new file.".format(path))
        return 1
    today = today or datetime.date.today().isoformat()
    seed = int(today.replace("-", "")) if seed is None else seed
    doc = build_plan(ws, 25 if ranked_n is None else ranked_n,
                     25 if random_n is None else random_n, seed, today)
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    plan = doc["plan"]
    print("audit plan written: {}".format(path))
    print("  seed {}  ·  {} ranked + {} random  ·  {}".format(
        seed, len(plan["ranked"]), len(plan["random"]), today))
    print("  ranked by: {}".format(ORDER_KEY))
    print("  next: review each id (reqmap_review / gate --show ID), record the "
          "findings in this file, then `gate --audit`.")
    return 0


# ---------- reading and checking the session --------------------------------

def load(reqs_dir):
    # implements: REQ-AUDITRUN-1106
    """(document, problems). The document is None when the file is absent or
    cannot be used; the problems say why when it exists."""
    path = audit_path(reqs_dir)
    if not os.path.exists(path):
        return None, []
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError) as e:
        return None, ["{} cannot be read: {}".format(AUDIT_FILE, e)]
    if not isinstance(doc, dict) or not isinstance(doc.get("plan"), dict):
        return None, ["{} holds no plan object".format(AUDIT_FILE)]
    if doc.get("schema") != AUDIT_SCHEMA:
        return None, ["{} has schema {!r}; this engine reads {}".format(
            AUDIT_FILE, doc.get("schema"), AUDIT_SCHEMA)]
    return doc, []


def _count_ok(x):
    return isinstance(x, int) and not isinstance(x, bool) and x >= 1


def _clause_ok(x):
    return x is None or _count_ok(x)


def _check_finding(i, f, planned):
    # implements: REQ-AUDITRUN-1106
    """Why finding `i` cannot be counted, or None."""
    where = "findings[{}]".format(i)
    if not isinstance(f, dict):
        return "{} is not an object".format(where)
    missing = [k for k in ("id", "run", "label", "clause", "note") if k not in f]
    if missing:
        return "{} misses {}".format(where, ", ".join(missing))
    if f["id"] not in planned:
        return "{} names {!r}, which is in neither set of the plan".format(
            where, f["id"])
    if not _count_ok(f["run"]):
        return "{} run {!r} is not a whole number from 1".format(where, f["run"])
    if f["label"] not in LABELS:
        return "{} label {!r} is not one of {}".format(
            where, f["label"], ", ".join(LABELS))
    if not _clause_ok(f["clause"]):
        return "{} clause {!r} is not a clause number or null".format(
            where, f["clause"])
    return None


def _check_decision(i, d, keys, decided):
    # implements: REQ-AUDITRUN-1106
    """Why decision `i` cannot be counted, or None."""
    where = "decisions[{}]".format(i)
    if not isinstance(d, dict):
        return "{} is not an object".format(where)
    missing = [k for k in ("id", "clause", "counter", "by") if k not in d]
    if missing:
        return "{} misses {}".format(where, ", ".join(missing))
    if d["counter"] not in COUNTERS:
        return "{} counter {!r} is not one of {}".format(
            where, d["counter"], ", ".join(COUNTERS))
    key = (d["id"], d["clause"]) if _clause_ok(d["clause"]) else None
    if key not in keys:
        return "{} names no recorded finding ({!r}, clause {!r})".format(
            where, d["id"], d["clause"])
    if key in decided:
        return "{} decides {!r} clause {!r} a second time; the first stands" \
            .format(where, d["id"], d["clause"])
    return None


def validate(doc):
    # implements: REQ-AUDITRUN-1106
    """(findings, decisions, problems): the entries that count, and one line
    per entry that does not. Nothing is fixed or rewritten."""
    plan = doc["plan"]
    planned = set(plan.get("ranked") or []) | set(plan.get("random") or [])
    findings, decisions, problems = [], {}, []
    for i, f in enumerate(doc.get("findings") or []):
        why = _check_finding(i, f, planned)
        if why:
            problems.append(why)
        else:
            findings.append(f)
    keys = {(f["id"], f["clause"]) for f in findings}
    for i, d in enumerate(doc.get("decisions") or []):
        why = _check_decision(i, d, keys, decisions)
        if why:
            problems.append(why)
        else:
            decisions[(d["id"], d["clause"])] = d["counter"]
    return findings, decisions, problems


def input_problems(reqs_dir):
    # implements: REQ-AUDITRUN-1106
    """The lines the gate reports as `INPUT:audit`."""
    doc, problems = load(reqs_dir)
    if doc is None:
        return problems
    return validate(doc)[2]


# ---------- the report -------------------------------------------------------

def wilson(k, n, z=1.96):
    # implements: REQ-AUDITRUN-1107
    """The Wilson score interval for k of n, or None when n is 0."""
    if n <= 0:
        return None
    p, zz = k / n, z * z
    d = 1 + zz / n
    centre = (p + zz / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + zz / (4 * n * n)) / d
    return max(0.0, centre - half), min(1.0, centre + half)


def _rate(k, n, min_positives):
    # implements: REQ-AUDITRUN-1107
    ci = wilson(k, n)
    return {"k": k, "n": n,
            "lo": round(ci[0], 3) if ci else None,
            "hi": round(ci[1], 3) if ci else None,
            "judged": n >= min_positives}


def _tally(findings, decisions):
    # implements: REQ-AUDITRUN-1107
    """Per finding key: its labels, its runs and the counter it lands in. A
    finding whose runs disagree is U whatever was decided. An `ok` nobody
    contradicted needs no decision: it is settled as "ok"; a person who
    finds a bug behind it decides M."""
    keys = {}
    for f in findings:
        rec = keys.setdefault((f["id"], f["clause"]),
                              {"labels": set(), "runs": set()})
        rec["labels"].add(f["label"])
        rec["runs"].add(f["run"])
    for key, rec in keys.items():
        rec["counter"] = ("U" if len(rec["labels"]) > 1
                          else decisions.get(key)
                          or ("ok" if rec["labels"] == {"ok"} else None))
    return keys


def _band(bands, reviewed, real, precision):
    # implements: REQ-AUDITRUN-1107
    """Which decision band the result is in, from the plan's own bands."""
    if reviewed >= bands.get("stop_after", 20) and real == 0:
        return "stop"
    if not precision["judged"]:
        return "not judged yet"
    if precision["lo"] < bands.get("precision_lower_bound", 0.5):
        return "change the method"
    if real * 10 >= bands.get("findings_per_10", 1) * reviewed:
        return "continue"
    return "not judged yet"


def _requirement_rows(plan, findings, keys):
    # implements: REQ-AUDITRUN-1108
    """One row per planned id: its set, its state and its findings."""
    rows = []
    for which in ("ranked", "random"):
        for rid in plan.get(which) or []:
            mine = [(k, v) for k, v in keys.items() if k[0] == rid]
            runs = {f["run"] for f in findings if f["id"] == rid}
            if not mine:
                state = "not reviewed"
            elif all(v["counter"] for _k, v in mine):
                state = "decided"
            else:
                state = "reviewed twice" if len(runs) >= 2 else "reviewed once"
            rows.append({"id": rid, "set": which, "state": state,
                         "runs": len(runs),
                         "findings": [{"clause": k[1],
                                       "labels": sorted(v["labels"]),
                                       "counter": v["counter"]}
                                      for k, v in sorted(
                                          mine, key=lambda kv: (
                                              kv[0][1] is None, kv[0][1] or 0))]})
    return rows


def report(doc):
    # implements: REQ-AUDITRUN-1107
    """The audit section: counters, rates as k/n with intervals, the band."""
    plan = doc["plan"]
    findings, decisions, problems = validate(doc)
    keys = _tally(findings, decisions)
    min_pos = plan.get("min_positives", cfg.AUDIT_MIN_POSITIVES)
    bands = plan.get("bands") or dict(cfg.AUDIT_BANDS)
    counters = {c: 0 for c in COUNTERS + ("ok",)}
    for rec in keys.values():
        if rec["counter"]:
            counters[rec["counter"]] += 1
    counters["undecided"] = sum(1 for r in keys.values() if not r["counter"])
    seen = {f["id"] for f in findings}
    rnd = set(plan.get("random") or [])
    missed = {k[0] for k, v in keys.items() if v["counter"] == "M"}
    repeated = [v for v in keys.values() if len(v["runs"]) >= 2]
    rates = {
        "precision": _rate(counters["B"], counters["B"] + counters["F_copilot"],
                           min_pos),
        "miss_rate": _rate(len(missed & rnd), len(seen & rnd), min_pos),
        "agreement": _rate(sum(1 for v in repeated if len(v["labels"]) == 1),
                           len(repeated), min_pos)}
    real = counters["B"] + counters["A"]
    return {"plan": {"date": plan.get("date"), "seed": plan.get("seed"),
                     "key": plan.get("key"),
                     "ranked": len(plan.get("ranked") or []),
                     "random": len(rnd), "bands": bands,
                     "min_positives": min_pos},
            "reviewed": {"total": len(seen),
                         "ranked": len(seen - rnd), "random": len(seen & rnd)},
            "counters": counters, "rates": rates,
            "band": _band(bands, len(seen), real, rates["precision"]),
            "problems": problems,
            "requirements": _requirement_rows(plan, findings, keys)}


def _rate_line(name, r):
    # implements: REQ-AUDITRUN-1107
    if r["n"] == 0:
        return "  {:<12} 0/0  (nothing to count yet)".format(name)
    return "  {:<12} {}/{}  (95% {:.2f}-{:.2f}){}".format(
        name, r["k"], r["n"], r["lo"], r["hi"],
        "" if r["judged"] else "  not judged: fewer than the minimum")


def report_lines(rep):
    # implements: REQ-AUDITRUN-1107
    """The audit section as printable lines."""
    p, c = rep["plan"], rep["counters"]
    out = ["Audit session - plan {} (seed {}): {} ranked + {} random".format(
               p["date"], p["seed"], p["ranked"], p["random"]),
           "  reviewed     {} of {} (ranked {}, random {})".format(
               rep["reviewed"]["total"], p["ranked"] + p["random"],
               rep["reviewed"]["ranked"], rep["reviewed"]["random"]),
           "  counters     " + " · ".join("{} {}".format(k, c[k]) for k in
                                         COUNTERS + ("ok", "undecided")),
           _rate_line("precision", rep["rates"]["precision"]),
           _rate_line("miss rate", rep["rates"]["miss_rate"]),
           _rate_line("agreement", rep["rates"]["agreement"]),
           "  band         {}".format(rep["band"])]
    out += ["  ! INPUT:audit {}".format(m) for m in rep["problems"]]
    return out


def session_report(reqs_dir):
    # implements: REQ-AUDITRUN-1107
    """The report for `gate --audit` and the map, or None with no session."""
    doc, problems = load(reqs_dir)
    if doc is None:
        return {"problems": problems} if problems else None
    return report(doc)


def map_block(reqs_dir):
    # implements: REQ-AUDITRUN-1108
    """What `sync` writes under `audit` in `_map.json`."""
    return session_report(reqs_dir)


def review_context(reqs_dir):
    # implements: REQ-AUDITRUN-1109
    """(top-level audit block, in_plan(rid)) for `ask --review`, or None."""
    doc, _problems = load(reqs_dir)
    if doc is None:
        return None
    plan = doc["plan"]
    ranked, rnd = set(plan.get("ranked") or []), set(plan.get("random") or [])
    def in_plan(rid):
        return "ranked" if rid in ranked else "random" if rid in rnd else "no"
    return {"prompt": PROMPT, "labels": list(LABELS)}, in_plan
