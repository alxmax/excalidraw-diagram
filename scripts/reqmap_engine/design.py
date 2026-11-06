"""`ask --design`: the shared vocabulary — pillars, advice, the finding record
and the language-neutral shape, chain and writing-standard checks.
"""
import os
import re

from . import config as cfg
from .orphans import ORPHAN_CODE_EXTS


DESIGN_PILLARS = ("encapsulation", "abstraction", "inheritance",
                  "polymorphism", "standards")
# program-logic files; prose/config/styling are not reviewed
DESIGN_EXTS = ORPHAN_CODE_EXTS
DESIGN_BRACE_EXTS = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".mts",
                     ".cts", ".vue", ".svelte", ".c", ".cc", ".cpp", ".h",
                     ".hpp", ".java", ".cs", ".go", ".rs", ".kt", ".kts",
                     ".swift", ".scala", ".dart", ".php")
_DESIGN_ADVICE = {
    "global-state": "module state mutated from inside a function has no "
                    "owner: hold it in an object, or pass it in and return it",
    "long-parameter-list": "a parameter list this long is an object waiting "
                           "to be named: group the parameters that travel "
                           "together",
    "data-clump": "the same parameters travel through several functions: "
                  "make them one object with those functions as methods",
    "long-function": "a function this long hides several steps: extract "
                     "each step under a name that says what it does",
    "deep-nesting": "nesting this deep hides the main path: return early, "
                    "or extract the inner block",
    "prefix-family": "functions sharing a prefix are a namespace: a class "
                     "(or module) with that name makes the boundary explicit",
    "shared-methods": "unrelated classes with the same method names "
                      "describe one interface: name a base class or protocol",
    "duplicate-method": "the same method body in two classes is one method: "
                        "pull it up into a shared base",
    "isinstance-chain": "a chain of type tests dispatches by hand: give each "
                        "type the method and let the call dispatch",
    "type-switch": "a chain of equality tests on one value is a dispatch "
                   "table: a dict of handlers, or a method per case",
    "file-too-long": "a file this long is several modules sharing a name: "
                     "split it along the prefix families it already shows",
    "line-too-long": "lines wider than the limit hide their tail in every "
                     "diff and side-by-side view: wrap them",
}
_DESIGN_PILLAR_OF = {
    "global-state": "encapsulation", "long-parameter-list": "encapsulation",
    "data-clump": "encapsulation",
    "long-function": "abstraction", "deep-nesting": "abstraction",
    "prefix-family": "abstraction",
    "shared-methods": "inheritance", "duplicate-method": "inheritance",
    "isinstance-chain": "polymorphism", "type-switch": "polymorphism",
    "file-too-long": "standards", "line-too-long": "standards",
}


def finding_record(kind, rel, line, name, detail):
    # implements: ARCH-DESIGN-061
    return {"pillar": _DESIGN_PILLAR_OF[kind], "kind": kind, "file": rel,
            "line": line, "name": name, "detail": detail,
            "advice": _DESIGN_ADVICE[kind]}


def name_prefix(name):
    """The family token of a function name: `_scan_tags` -> `scan`,
    `scanTags` -> `scan`."""
    core = name.strip("_")
    if "_" in core:
        return core.split("_", 1)[0]
    m = re.match(r"[a-z]{3,}(?=[A-Z])", core)
    return m.group(0) if m else ""


# ---- shared shape checks over abstract "function" and "class" records, so
# the Python and the brace analyzers report the same kinds with the same
# thresholds.
# fn record: {name, line, n_lines, depth, params:[names], top:bool}
# class record: {name, line, bases:set, methods:{name: body_key}}
def function_sizes(rel, fns):
    # implements: REQ-DESIGN-950
    """Per-function sizes: parameters, length, nesting."""
    out = []
    for f in fns:
        for kind, value, limit, what in (
                ("long-parameter-list", len(f["params"]),
                 cfg.DESIGN_PARAMS_MAX, "takes {} parameters"),
                ("long-function", f["n_lines"],
                 cfg.DESIGN_FUNC_MAX_LINES, "is {} lines"),
                ("deep-nesting", f["depth"],
                 cfg.DESIGN_NESTING_MAX, "nests {} levels deep")):
            if value > limit:
                detail = "`{}` {} (over {})".format(
                    f["name"], what.format(value), limit)
                out.append(finding_record(kind, rel, f["line"], f["name"],
                                           detail))
    return out


def data_clumps(rel, fns):
    # implements: REQ-DESIGN-950
    """Parameter sets shared by several functions, once per set."""
    out, seen = [], set()
    plist = [(f, frozenset(f["params"])) for f in fns]
    for i in range(len(plist)):
        for j in range(i + 1, len(plist)):
            common = plist[i][1] & plist[j][1]
            if len(common) < cfg.DESIGN_CLUMP_MIN or common in seen:
                continue
            carriers = [f for f, ps in plist if common <= ps]
            if len(carriers) < cfg.DESIGN_CLUMP_FUNCS:
                continue
            seen.add(common)
            first = min(carriers, key=lambda f: f["line"])
            names = ", ".join(sorted(f["name"] for f in carriers)[:6])
            detail = "{} travel together through {} functions: {}".format(
                ", ".join(sorted(common)), len(carriers), names)
            out.append(finding_record("data-clump", rel, first["line"],
                                       first["name"], detail))
    return out


def prefix_families(rel, fns):
    # implements: REQ-DESIGN-950
    """Top-level functions sharing a name prefix, once per prefix."""
    out, families = [], {}
    for f in fns:
        p = name_prefix(f["name"]) if f["top"] else ""
        if p:
            families.setdefault(p, []).append(f)
    for prefix, group in sorted(families.items()):
        if len(group) >= cfg.DESIGN_PREFIX_GROUP:
            first = min(group, key=lambda f: f["line"])
            names = ", ".join(sorted(f["name"] for f in group)[:6])
            detail = "{} top-level functions start with `{}`: {}".format(
                len(group), prefix, names)
            out.append(finding_record("prefix-family", rel, first["line"],
                                       prefix, detail))
    return out


def class_shapes(rel, classes):
    # implements: REQ-DESIGN-951
    """Unrelated classes sharing method names, and identical bodies."""
    out = []
    for i in range(len(classes)):
        for j in range(i + 1, len(classes)):
            a, b = classes[i], classes[j]
            if (a["bases"] & b["bases"] or a["name"] in b["bases"]
                    or b["name"] in a["bases"]):
                continue
            shared = sorted(n for n in a["methods"]
                            if n in b["methods"] and not n.startswith("__"))
            if len(shared) >= cfg.DESIGN_SHARED_METHODS:
                pair = "{}/{}".format(a["name"], b["name"])
                detail = ("`{}` and `{}` share {} method names with no "
                          "common base: {}").format(
                              a["name"], b["name"], len(shared),
                              ", ".join(shared[:6]))
                out.append(finding_record("shared-methods", rel, a["line"],
                                           pair, detail))
            for n in shared:
                if a["methods"][n] == b["methods"][n]:
                    dup = "{}.{}".format(b["name"], n)
                    detail = "`{}` is byte-for-byte `{}.{}`".format(
                        dup, a["name"], n)
                    out.append(finding_record("duplicate-method", rel,
                                               b["line"], dup, detail))
    return out


def shape_findings(rel, fns, classes):
    # implements: REQ-DESIGN-950  # implements: REQ-DESIGN-951
    return (function_sizes(rel, fns) + data_clumps(rel, fns)
            + prefix_families(rel, fns)
            + class_shapes(rel, classes))


def chain_findings(rel, chains):  # implements: REQ-DESIGN-951
    """chains: [(line, [(kind, name), ...])] where kind is 'type' or 'eq'."""
    out = []
    for line, tests in chains:
        for kind, floor, label in (
                ("type", cfg.DESIGN_ISINSTANCE_CHAIN, "isinstance-chain"),
                ("eq", cfg.DESIGN_BRANCH_CHAIN, "type-switch")):
            names = [n for k, n in tests if k == kind]
            for name in sorted(set(names)):
                if names.count(name) >= floor:
                    detail = "{} branches test `{}` in one chain".format(
                        names.count(name), name)
                    out.append(finding_record(label, rel, line, name,
                                               detail))
    return out


def writing_standards(rel, src):  # implements: REQ-DESIGN-953
    """The two writing rules: file length and line width, once per file."""
    out = []
    lines = src.split("\n")
    base = os.path.basename(rel)
    if len(lines) > cfg.DESIGN_FILE_MAX_LINES:
        detail = "{} lines (over {})".format(len(lines),
                                             cfg.DESIGN_FILE_MAX_LINES)
        out.append(finding_record("file-too-long", rel, 1, base, detail))
    wide = [i for i, ln in enumerate(lines, 1)
            if len(ln.rstrip("\r")) > cfg.DESIGN_LINE_MAX]
    if wide:
        detail = ("{} line(s) wider than {} columns, first at line {}"
                  .format(len(wide), cfg.DESIGN_LINE_MAX, wide[0]))
        out.append(finding_record("line-too-long", rel, wide[0], base,
                                   detail))
    return out
