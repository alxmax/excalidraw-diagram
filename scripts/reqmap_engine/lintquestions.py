"""`lint`: the checks on a decision-form question in `## Verify intent`."""

import re

from . import config as cfg
from .lintprose import _clause_words, _clip, _sentences
from .sections import _section_lines
from .text import _verify_bullets

_Q_BOLD_RE = re.compile(r"^\*\*(.+?)\*\*")
_Q_OPTION_RE = re.compile(r"^[a-zA-Z]\)\s")
_Q_LABEL_RE = re.compile(r"^\*([^*]+?):\*\s*(.*)")
_Q_CODE_REF_RE = re.compile(r"[\w.-]+\.[A-Za-z]\w*:\d+")


def _decision_parts(q):
    # implements: ARCH-LINTCHECKS-025  # implements: REQ-LINTCHECKS-1089
    """(question, options, labels) of a question asked as a decision, else None."""
    lines = q.split("\n")
    head = _Q_BOLD_RE.match(lines[0])
    options = [x for x in lines[1:] if _Q_OPTION_RE.match(x)]
    if not head or not options:
        return None
    labels = {}
    for x in lines[1:]:
        m = _Q_LABEL_RE.match(x)
        if m:
            labels.setdefault(m.group(1).lower(), m.group(2))
    return head.group(1), options, labels


def _label(labels, names):
    # implements: ARCH-LINTCHECKS-025  # implements: REQ-LINTCHECKS-1089
    """The text of the first label spelled as one of `names`, else ''."""
    wanted = [n.lower() for n in names]
    return next((v for k, v in labels.items() if k in wanted), "")


def _overlap(question, context):
    # implements: ARCH-LINTCHECKS-025  # implements: REQ-LINTCHECKS-1089
    """Share of the question's words of 4+ letters that the context repeats."""
    words = set(re.findall(r"\w{4,}", question.lower()))
    if not words:
        return 0.0
    return len(words & set(re.findall(r"\w{4,}", context.lower()))) / len(words)


def _count(text, marks):
    # implements: ARCH-LINTCHECKS-025  # implements: REQ-LINTCHECKS-1089
    """How many times any of `marks` occurs in `text`, ignoring case."""
    return sum(text.lower().count(m.lower()) for m in marks)


def _question_checks(whole, question, options, labels):
    # implements: ARCH-LINTCHECKS-025  # implements: REQ-LINTCHECKS-1089
    """One finding per check the question fails."""
    found = []
    if (_clause_words(question) > cfg.LINT_QUESTION_WORDS
            or len(_sentences(question)) > cfg.LINT_QUESTION_SENTENCES):
        found.append(("question-too-long", "question is too long"))
    default = _label(labels, cfg.LINT_QUESTION_DEFAULT_LABELS)
    if _Q_CODE_REF_RE.search(default):
        found.append(("default-has-code", "default names a file and line"))
    context = _label(labels, cfg.LINT_QUESTION_CONTEXT_LABELS)
    if "**" in context or _overlap(question, context) > cfg.LINT_QUESTION_OVERLAP:
        found.append(("context-repeats-question", "context restates the question"))
    if (_count(whole, cfg.LINT_QUESTION_RECOMMENDED_MARKS)
            > _count(whole, cfg.LINT_QUESTION_SOURCE_LABELS)):
        found.append(("recommendation-without-source", "recommendation has no source"))
    words = cfg.LINT_QUESTION_DEFER_WORDS
    if words:
        pat = re.compile(r"\b(?:" + "|".join(map(re.escape, words)) + r")\b", re.I)
        found += [("option-defers-decision", "option hands the decision on")
                  for o in options if pat.search(o)]
    return [{"severity": "warn", "check": c, "detail": d + ": " + _clip(question)}
            for c, d in found]


def _question_lint(body):
    # implements: ARCH-LINTCHECKS-025  # implements: REQ-LINTCHECKS-1089
    """Findings for the decision-form questions in `## Verify intent`."""
    findings, seen = [], False
    for whole in _verify_bullets(body):
        parts = _decision_parts(whole)
        if parts:
            seen = True
            findings += _question_checks(whole, *parts)
    marks = cfg.LINT_QUESTION_AUDIENCE_MARKERS
    if seen and marks:
        pat = re.compile(r"<!--\s*(?:" + "|".join(map(re.escape, marks)) + r")\s*:", re.I)
        if not any(pat.search(x) for x in _section_lines(body, "verify intent")):
            findings.append({"severity": "warn", "check": "question-no-audience",
                             "detail": "no audience marker in Verify intent"})
    return findings
