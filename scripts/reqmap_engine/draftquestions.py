"""The open questions a code draft asks: one per signal the scan can point at."""
import ast, io, re, tokenize

# A draft used to ask every file the same thing ("anything that looks like an
# accident ... intended, or a bug to fix?"), so `_findings.md` held N copies
# of one sentence and named nothing. Each question below names the line it
# is about. The scan reads; only the author knows whether the shape is meant.
DRAFT_QUESTION_MAX = 8
# A marker counts only inside a comment: the word in a string literal is data,
# and `TODO.md` is a file name.
_MARKER_RE = re.compile(
    r"(?:#|//|/\*|<!--|--|^\s*\*)[^\n]*?\b(TODO|FIXME|HACK|XXX)\b(?!\.\w)")
_SUPPRESS_RE = re.compile(
    r"#\s*noqa\b|#\s*type:\s*ignore\b|pylint:\s*disable|eslint-disable"
    r"|@ts-(?:ignore|expect-error)\b|\bNOLINT\b")
_EMPTY_CATCH_RE = re.compile(r"\bcatch\s*(?:\([^)]*\))?\s*\{\s*\}")
# A string literal on one line: a marker or a `catch {}` quoted in it is data.
# Crude on purpose: a lone quote (`don't`) closes nothing and is kept.
_STRING_RE = re.compile(
    r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|`(?:\\.|[^`\\])*`')
# A comment on one line, after strings are blanked: a `catch {}` in it is prose.
_COMMENT_RE = re.compile(r"//.*|/\*.*?(?:\*/|$)|^\s*\*.*")
# Numbers too common to mean anything on their own.
_PLAIN_NUMBERS = frozenset((0, 1, 2, -1))
_EXIT = (ast.Return, ast.Raise, ast.Continue, ast.Break)

_ASK = {
    "marker": "left in the code. Part of the contract, or out of scope?",
    "suppress": "silences a check. Intended, or a bug the check found?",
    "swallow": "swallows the error. Intended fail-open, or a bug to fix?",
    "magic": "is an unnamed number. What does it stand for, and in what "
             "unit?",
    "dead": "can never run: it follows a return/raise. Delete it, or is "
            "the exit the bug?",
}
# A scan that could not parse the file says so, rather than reading as clean.
_PARTIAL = "\nIn `{}`, {} were not looked for, because {}.\n"
_UNPARSED = "swallowed errors, unnamed numbers and dead code"


def _py_comments(src):
    # implements: ARCH-EXTRACT-008  # implements: REQ-EXTRACT-1099
    """{line: comment} from Python's own tokenizer, else None when it
    cannot tokenize the file. Before 3.12 an unclosed string is an
    ERRORTOKEN, not an exception, and what follows it reads as a comment."""
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    except (tokenize.TokenError, SyntaxError, ValueError):
        return None
    if any(t.type == tokenize.ERRORTOKEN for t in toks):
        return None
    return {t.start[0]: t.string for t in toks if t.type == tokenize.COMMENT}


def _snippet(line):
    # implements: ARCH-EXTRACT-008  # implements: REQ-EXTRACT-1099
    s = " ".join(line.strip().replace("`", "'").split())
    return s if len(s) <= 60 else s[:57] + "..."


def _swallows(handler):
    # implements: ARCH-EXTRACT-008  # implements: REQ-EXTRACT-1099
    """True when an except body only passes, continues or returns nothing."""
    for st in handler.body:
        if isinstance(st, (ast.Pass, ast.Continue)):
            continue
        if isinstance(st, ast.Return) and (
                st.value is None or (isinstance(st.value, ast.Constant)
                                     and st.value.value is None)):
            continue
        if isinstance(st, ast.Expr) and isinstance(st.value, ast.Constant):
            continue                     # a docstring-like string or `...`
        return False
    return True


def _magic(node):
    # implements: ARCH-EXTRACT-008  # implements: REQ-EXTRACT-1099
    """The number a comparison or a keyword argument hard-codes, else None."""
    vals = []
    if isinstance(node, ast.Compare):
        vals = [node.left] + list(node.comparators)
    elif isinstance(node, ast.keyword):
        vals = [node.value]
    for v in vals:
        if isinstance(v, ast.UnaryOp) and isinstance(v.op, ast.USub):
            v = v.operand
        if (isinstance(v, ast.Constant) and type(v.value) in (int, float)
                and v.value not in _PLAIN_NUMBERS):
            return v
    return None


def _py_signals(src):
    # implements: ARCH-EXTRACT-008  # implements: REQ-EXTRACT-1099
    """(line, kind) for every swallowed error, magic number inside a
    function, and statement after an unconditional exit. None for an
    unparseable file: the regex signals still apply."""
    try:
        tree = ast.parse(src)
    except (SyntaxError, ValueError):
        return None
    out = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(fn):
            if isinstance(node, ast.ExceptHandler) and _swallows(node):
                out.append((node.lineno, "swallow"))
            v = _magic(node)
            if v is not None:
                out.append((v.lineno, "magic"))
            for body in (getattr(node, f, None)
                         for f in ("body", "orelse", "finalbody")):
                if not isinstance(body, list):
                    continue
                for a, b in zip(body, body[1:]):
                    if isinstance(a, _EXIT) and isinstance(b, ast.stmt):
                        out.append((b.lineno, "dead"))
                        break
    return out


def draft_questions(rel, src):
    # implements: ARCH-EXTRACT-008  # implements: REQ-EXTRACT-1099
    """The Verify-intent bullets for one code draft, ordered by line, at
    most DRAFT_QUESTION_MAX of them, the number left out, and why the
    parsed signals were not looked for ('' when they were). Each bullet
    reads `Observed at `rel:N`: `code` <question>`. Empty when the scan
    finds nothing: the caller then keeps the generic question. A Python
    marker counts only in a comment token, and none when the file does
    not tokenize; elsewhere string literals are blanked first, and comments
    too before looking for an empty `catch`."""
    lines = src.splitlines()
    is_py = rel.endswith(".py")
    comments = _py_comments(src) if is_py else None
    found = []
    for n, line in enumerate(lines, 1):
        bare = _STRING_RE.sub('""', line)
        text = (comments or {}).get(n, "") if is_py else bare
        if _MARKER_RE.search(text):
            found.append((n, "marker"))
        elif _SUPPRESS_RE.search(text):
            found.append((n, "suppress"))
        if _EMPTY_CATCH_RE.search(_COMMENT_RE.sub("", bare)):
            found.append((n, "swallow"))
    parsed = _py_signals(src) if is_py else None
    found += parsed or []
    partial = "" if parsed is not None else (
        (_UNPARSED, "no parser reads this language") if not is_py else
        (_UNPARSED, "it does not parse as Python") if comments is not None
        else ("comment markers, suppressions, " + _UNPARSED,
              "it does not tokenize as Python"))
    seen, items = set(), []
    for n, kind in sorted(set(found)):
        if n in seen or not 0 < n <= len(lines):
            continue                     # one question per line is enough
        seen.add(n)
        items.append("Observed at `{}:{}`: `{}` {}".format(
            rel, n, _snippet(lines[n - 1]), _ASK[kind]))
    return (items[:DRAFT_QUESTION_MAX],
            max(0, len(items) - DRAFT_QUESTION_MAX), partial)


def verify_section(rel, src):
    # implements: ARCH-EXTRACT-008  # implements: REQ-EXTRACT-1099
    """(the Verify-intent bullets, a Context note on what the cap left out
    and what the scan could not look for) for one code draft. A file with
    no signal keeps the generic question."""
    asks, more, partial = draft_questions(rel, src)
    text = "".join("- {}\n".format(q) for q in asks) or (
        "- TODO: anything that looks like an accident (swallowed error, "
        "magic constant, dead branch) — intended, or a bug to fix?\n")
    note = "\n{} more signal(s) past the first {} — read the file.\n".format(
        more, DRAFT_QUESTION_MAX) if more else ""
    if partial:
        note += _PARTIAL.format(rel, *partial)
    return text, note
