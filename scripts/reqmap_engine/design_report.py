"""`ask --design`: per-file dispatch, the summary record and the
grouped report."""
import json

from .design import (
    DESIGN_BRACE_EXTS, DESIGN_EXTS, DESIGN_PILLARS, _DESIGN_ADVICE,
    writing_standards
)
from .design_brace import _design_brace
from .design_python import _python_findings
from .scan import _walk_code
from .tags import _is_test_path


def _design_file(rel, src):
    # implements: ARCH-DESIGN-061  # implements: REQ-DESIGN-952
    # implements: REQ-DESIGN-953  # implements: REQ-DESIGN-955
    """All findings for one source file, in source order: Python through
    `ast`, a brace language through masked text, anything else the writing
    standards only. None for a Python file that does not parse: the
    review did not read it, so it is neither clean nor a finding."""
    low = rel.lower()
    try:
        if low.endswith(".py"):
            out = _python_findings(rel, src)
            if out is None:
                return None
        elif low.endswith(DESIGN_BRACE_EXTS):
            out = _design_brace(rel, src)
        else:
            out = []
    except RecursionError:
        # `ast.dump` on a pathological class body is recursive too. This
        # review is advisory; a file it cannot measure has no candidates.
        return []
    out = out + writing_standards(rel, src)
    out.sort(key=lambda f: (f["line"], f["kind"]))
    return out


def _design_findings(code_root, reqs_dir=None):  # implements: REQ-DESIGN-952
    """(file count, findings, unparsed paths) over every non-test
    program-logic file the scanner would walk. A file that does not parse
    is named, and left out of the count."""
    n_files, findings, unparsed = 0, [], []
    for fp, rel in _walk_code(code_root, reqs_dir):
        if not rel.lower().endswith(DESIGN_EXTS) or _is_test_path(rel):
            continue
        try:
            with open(fp, encoding="utf-8", errors="ignore") as f:
                src = f.read()
        except OSError:
            continue
        found = _design_file(rel, src)
        if found is None:
            unparsed.append(rel)
            continue
        n_files += 1
        findings.extend(found)
    return n_files, findings, unparsed


def _design_summary(code_root, reqs_dir=None, with_findings=False):
    # implements: ARCH-DESIGN-061  # implements: REQ-DESIGN-954
    # implements: REQ-DESIGN-976
    """The design health of the code as one small record, or None when the
    tree holds no non-test program-logic file: `files`, `clean_files` (no
    candidate at all), `score` (clean files as a percentage) and
    `candidates` (count per pillar).

    `with_findings` adds the rows and the advice once per kind, for `map`,
    whose viewer lists them. It is off by default so `health --json`, a
    badge payload, stays one small object."""
    files, found, unparsed = _design_findings(code_root, reqs_dir)
    if not files:
        return None
    clean = files - len({f["file"] for f in found})
    per = {p: 0 for p in DESIGN_PILLARS}
    for f in found:
        per[f["pillar"]] += 1
    out = {"files": files, "clean_files": clean,
           "score": round(100 * clean / files), "candidates": per}
    if unparsed:     # absent otherwise, so a badge payload keeps its shape
        out["unparsed"] = unparsed
    if with_findings:
        keys = ("pillar", "kind", "file", "line", "name", "detail")
        out["findings"] = [{k: f[k] for k in keys} for f in found]
        out["advice"] = {k: _DESIGN_ADVICE[k]
                         for k in sorted({f["kind"] for f in found})}
    return out


def cmd_design(code_root, reqs_dir=None, as_json=False):
    # implements: ARCH-DESIGN-061  # implements: REQ-DESIGN-952
    """Print (or emit as JSON) the design candidates, grouped by pillar.
    Read-only, always exit 0: advice a reader weighs, never a gate."""
    n_files, findings, unparsed = _design_findings(code_root, reqs_dir)
    if as_json:
        print(json.dumps({"files": n_files, "unparsed": unparsed,
                          "findings": findings}, indent=2, ensure_ascii=False))
        return 0
    if unparsed:
        print("{} file(s) did not parse as Python and are left out: {}\n"
              .format(len(unparsed), ", ".join(unparsed)))
    if not findings:
        print("No design candidates in {} source file(s) at the current "
              "thresholds.".format(n_files))
        return 0
    for pillar in DESIGN_PILLARS:
        mine = [f for f in findings if f["pillar"] == pillar]
        if not mine:
            continue
        print("{} ({})".format(pillar.capitalize(), len(mine)))
        for f in mine:
            print("  {}:{}  {:<20} {}".format(f["file"], f["line"],
                                              f["kind"], f["detail"]))
        advice = dict.fromkeys(_DESIGN_ADVICE[f["kind"]] for f in mine)
        print("  -> " + "; ".join(advice))
        print("")
    print("{} candidate(s) in {} source file(s). Advisory only: a candidate "
          "is a shape worth a look, never a defect, and this never enters "
          "the gate.".format(len(findings), n_files))
    return 0
