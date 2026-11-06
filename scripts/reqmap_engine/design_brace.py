"""`ask --design`, brace-language side: masking and heuristics for
JS/TS/Java/C-family sources.
"""
import re

from .design import chain_findings, shape_findings

_BRACE_KEYWORDS = frozenset((
    "if", "for", "while", "switch", "catch", "else", "return", "do", "try",
    "sizeof", "typeof", "new", "throw", "await", "yield", "defer", "match",
    "elif", "unless", "until", "foreach", "using", "lock", "synchronized"))
_BRACE_FUNC_RE = re.compile(
    r"(?<![\w.])(?:(?:async|static|public|private|protected|export|default|"
    r"override|virtual|inline|constexpr|extern|final|abstract|unsafe|"
    r"pub(?:\([^)]*\))?|func|fn|fun|function|def)\s+)*"
    r"(?:[A-Za-z_][\w:<>\[\],*&?]*\s+[*&]*)?([A-Za-z_]\w*)\s*"
    r"(?:<[^>()]*>)?\s*"
    r"\(([^()]*(?:\([^()]*\)[^()]*)*)\)"
    r"\s*(?:->\s*[\w:<>\[\],*&?.]+|:\s*[\w:<>\[\],*&?.|]+|"
    r"const|override|noexcept|throws\s+[\w, ]+)?\s*\{")
_BRACE_ARROW_RE = re.compile(
    r"(?<![\w.])(?:const|let|var|val)\s+([A-Za-z_]\w*)\s*(?::[^=]+)?=\s*"
    r"(?:async\s*)?\(([^()]*)\)\s*(?::\s*[^=]+)?=>\s*\{")
_BRACE_CLASS_RE = re.compile(
    r"(?<![\w.])(?:class|struct|interface)\s+([A-Za-z_]\w*)"
    r"(?:\s*<[^>{]*>)?\s*([^{;]*)\{")
_BRACE_IF_RE = re.compile(r"(?<![\w.])(else\s+)?if\s*\(")
_BRACE_SWITCH_RE = re.compile(
    r"(?<![\w.])switch\s*\(\s*([A-Za-z_][\w.]*)\s*\)\s*\{")
_BRACE_CASE_RE = re.compile(r"(?<![\w.])case\s+[^:]{1,60}:")
_BRACE_TYPE_TEST_RE = re.compile(
    r"(?:([A-Za-z_]\w*)\s+instanceof\b|typeof\s+([A-Za-z_]\w*)\s*[!=]==?|"
    r"dynamic_cast\s*<[^>]*>\s*\(\s*([A-Za-z_]\w*)|"
    r"([A-Za-z_]\w*)\s+is\s+[A-Z]\w*)")
_BRACE_EQ_TEST_RE = re.compile(
    r"(?<![\w.])([A-Za-z_][\w.]*)\s*[!=]==?\s*"
    r"(?:\d+|[A-Z_][A-Z0-9_]{2,}|\w+::\w+)")
_BASE_NOISE_RE = re.compile(
    r"\b(?:extends|implements|public|private|protected|virtual|final|with)\b")


def _blank(text):
    return "".join("\n" if ch == "\n" else " " for ch in text)


def _mask_quote_end(src, q, j, n):
    """Index of the closing quote `q` (or a terminating bare newline)."""
    while j < n and src[j] != q:
        j += 2 if src[j] == "\\" else 1
        if j < n and src[j] == "\n" and q != "`":
            break
    return j


def _design_mask(src):  # implements: REQ-DESIGN-955
    """The source with comments and string/char literals replaced by spaces
    (newlines kept), so brace matching and keyword searches never see text.
    """
    out, i, n = [], 0, len(src)
    while i < n:
        c, two = src[i], src[i:i + 2]
        if two == "//":
            j = src.find("\n", i)
            j = n if j == -1 else j
        elif two == "/*":
            j = src.find("*/", i + 2)
            j = n if j == -1 else j + 2
        elif c in "\"'`":
            j = min(_mask_quote_end(src, c, i + 1, n) + 1, n)
        else:
            out.append(c)
            i += 1
            continue
        out.append(_blank(src[i:j]))
        i = j
    return "".join(out)


def _match_end(masked, idx, open_ch, close_ch):
    """Index just past the `close_ch` matching `open_ch` at idx."""
    depth, n = 0, len(masked)
    while idx < n:
        if masked[idx] == open_ch:
            depth += 1
        elif masked[idx] == close_ch:
            depth -= 1
            if depth == 0:
                return idx + 1
        idx += 1
    return n


def _design_param_names(params):
    names = []
    for p in params.split(","):
        p = p.strip()
        if not p or p in ("...", "void"):
            continue
        p = p.split("=", 1)[0]
        p = p.split(":", 1)[0]        # TS / Kotlin / Swift: name: Type
        toks = re.findall(r"[A-Za-z_]\w*", p)
        if toks:
            names.append(toks[-1])
    return names


def _line_of(masked, idx):
    return masked.count("\n", 0, idx) + 1


def _brace_fns(masked):  # implements: REQ-DESIGN-955
    """Function records (plus `end`) for every head the regexes find."""
    fns = []
    heads = [(m.group(1), m.group(2), m)
             for m in _BRACE_FUNC_RE.finditer(masked)
             if m.group(1) not in _BRACE_KEYWORDS]
    heads += [(m.group(1), m.group(2), m)
              for m in _BRACE_ARROW_RE.finditer(masked)]
    for name, params, m in heads:
        brace = m.end() - 1
        end = _match_end(masked, brace, "{", "}")
        depth = best = 0
        for ch in masked[brace:end]:
            if ch == "{":
                depth += 1
                best = max(best, depth)
            elif ch == "}":
                depth -= 1
        top = masked.count("{", 0, brace) == masked.count("}", 0, brace)
        fns.append({"name": name, "line": _line_of(masked, m.start()),
                    "n_lines": masked[brace:end].count("\n") + 1,
                    "depth": max(best - 1, 0),
                    "params": _design_param_names(params),
                    "top": top, "end": end})
    return sorted(fns, key=lambda f: f["line"])


def _brace_classes(src, masked, fns):  # implements: REQ-DESIGN-955
    """Class records: methods are the functions whose body ends inside."""
    classes = []
    for m in _BRACE_CLASS_RE.finditer(masked):
        start = m.end() - 1
        end = _match_end(masked, start, "{", "}")
        bases = set(re.findall(r"[A-Za-z_]\w*",
                               _BASE_NOISE_RE.sub(" ", m.group(2))))
        methods = {}
        for f in fns:
            if start < f["end"] <= end:
                fstart = masked.rfind(f["name"], start, f["end"])
                body = src[fstart:f["end"]]
                methods[f["name"]] = re.sub(r"\s+", " ", body).strip()
        classes.append({"name": m.group(1),
                        "line": _line_of(masked, m.start()),
                        "bases": bases, "methods": methods})
    return classes


def _brace_chains(masked):  # implements: REQ-DESIGN-955
    """if/else-if chains and switches as (line, tests)."""
    chains, cur = [], None
    for m in _BRACE_IF_RE.finditer(masked):
        paren = m.end() - 1
        cond = masked[paren:_match_end(masked, paren, "(", ")")]
        tests = [("type", next(g for g in t if g))
                 for t in _BRACE_TYPE_TEST_RE.findall(cond)]
        tests += [("eq", n) for n in _BRACE_EQ_TEST_RE.findall(cond)]
        if m.group(1) and cur is not None:
            cur[1].extend(tests)
        else:
            cur = (_line_of(masked, m.start()), tests)
            chains.append(cur)
    for m in _BRACE_SWITCH_RE.finditer(masked):
        brace = m.end() - 1
        body = masked[brace:_match_end(masked, brace, "{", "}")]
        n_cases = len(_BRACE_CASE_RE.findall(body))
        chains.append((_line_of(masked, m.start()),
                       [("eq", m.group(1))] * n_cases))
    return chains


def _design_brace(rel, src):  # implements: REQ-DESIGN-955
    """The four pillars for one brace-language file, from masked text."""
    masked = _design_mask(src)
    fns = _brace_fns(masked)
    classes = _brace_classes(src, masked, fns)
    return (shape_findings(rel, fns, classes)
            + chain_findings(rel, _brace_chains(masked)))
