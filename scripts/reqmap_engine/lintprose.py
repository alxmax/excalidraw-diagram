"""The prose lint checks: readability of the normative clauses and the
words that make one untestable, with the clause readers they share.

"""
import re

from . import config as cfg
from .sections import ACCEPTANCE_LABELS, CONTRACT_LABELS, _section_lines

# Closed list of vague QUALITY words that make a normative bullet
# un-testable (IEEE 29148 "Unambiguous"). Deliberately excludes size
# words (high/low/small/many) and weak modals — they are too often
# legitimately precise in this domain, and a false positive trains
# authors to ignore lint. Only words with no testable meaning.
LINT_VAGUE_TERMS = frozenset({
    "appropriate", "appropriately", "adequate", "adequately", "sufficient",
    "sufficiently", "reasonable", "reasonably", "robust", "robustly",
    "flexible", "efficient", "efficiently", "optimal", "scalable",
    "performant", "fast", "slow", "quick", "quickly", "easy", "easily",
    "simple", "user-friendly", "seamless", "seamlessly", "intuitive",
    "various", "etc",
    # Temporal terms, added 2026-09-15. Same rule as the quality words
    # above: a deadline with no unit is not testable ("sent promptly",
    # "retried periodically"). The obvious candidates `immediately`,
    # `later` and `recent` are deliberately NOT here — measured over this
    # corpus they scored 12 hits and 12 false positives, every one of
    # them positional rather than temporal ("a block starts at a `---`
    # line immediately followed by `id:`", "a later block", "the most
    # recent commit"). The eight below scored zero hits: silent here,
    # firing on the shape that produced them, which is the same bargain
    # LINT_FANOUT_BANDS records above.
    "promptly", "timely", "periodically", "regularly", "frequently",
    "soon", "eventually", "shortly",
})
# Redundant normative modals: the Contract section opens with "Every
# line in this section is binding.", so "shall"/"must" on each clause is
# dead weight — and in a non-English requirement corpus "shall" is also
# a stray anglicism (see Audience & writing level, rule 3). Closed list,
# checked as a whole word, case-insensitive.
LINT_MODAL_WORDS = frozenset({"shall", "must"})
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z-]*")


def _prose_lint(body, name):
    # implements: ARCH-LINT-014  # implements: REQ-LINT-864
    """Yield the prose text lines under the FIRST `## ` heading whose text
    contains `name`, up to the next `## `. A bullet's leading `- ` is
    stripped so its text is linted as a sentence. Non-prose lines —
    headings, table rows, blockquotes, and anything inside a ``` fence —
    are skipped so the linter never flags code or markup as unreadable.
    Fence state is tracked BEFORE heading detection, so a `## ` comment
    inside a fenced block is treated as code, not a section boundary."""
    out = []
    for s in _section_lines(body, name):
        if not s or s.startswith(("|", ">", "#")):
            continue
        if s == "-" or s.startswith("- "):  # a real bullet marker (not
                                              # '--strict' / '-5')
            s = s[1:].strip()
        if s:
            out.append(s)
    return out


def _sentences(text):
    # implements: ARCH-LINTCHECKS-025  # implements: REQ-LINTCHECKS-865
    """Split a prose line into sentences on '.', '!', '?' boundaries.
    Crude but deterministic — enough to count words per sentence for the
    length check."""
    return [p.strip() for p in re.split(r"(?<=[.!?])\s+", text) if p.strip()]


def _clip(s, n=60):  # implements: ARCH-LINT-014  # implements: REQ-LINT-864
    """Shorten a snippet for one-line finding output."""
    return s if len(s) <= n else s[:n - 1] + "…"


def _clause_words(text):
    # implements: ARCH-ATOMICITY-049  # implements: REQ-ATOMICITY-824
    # implements: REQ-ATOMICITY-825
    """Word count for a Contract clause, counting each backticked span as
    one word. A clause carrying a long code sample is short prose, not a
    long statement. The span collapses to a bare token with no padding
    spaces: " x " would split trailing punctuation (`code`. -> "x" ".")
    into a second word and inflate every such clause by one."""
    return len(re.sub(r"`[^`]*`", "x", text).split())


def _contract_clauses(body):
    # implements: ARCH-ATOMICITY-049  # implements: REQ-ATOMICITY-824
    # implements: REQ-ATOMICITY-825
    """Yield (n, text) per clause of the Contract section, n 1-based.

    A clause is one bullet at ANY indent — a nested sub-bullet is its own
    clause because it states its own obligation — with its wrapped
    continuation lines joined back on. This is deliberately not
    `_prose_lint`, which yields physical LINES: these files are
    hard-wrapped near 95 columns, so a 90-word clause reaches
    `_prose_lint` as six ~15-word lines and no per-line ceiling can ever
    see it. Bold group labels, table rows, block quotes, fenced code and
    HTML comments are not clauses and are skipped."""
    out, cur, in_comment = [], None, False

    def flush():
        if cur is not None:
            out.append(cur)

    for s in _section_lines(body, CONTRACT_LABELS):
        if in_comment:            # glossary comments are guidance, not clauses
            if "-->" in s:
                in_comment = False
            continue
        if s.startswith("<!--"):
            if "-->" not in s:
                in_comment = True
            continue
        if (not s or s.startswith(("|", ">", "#"))
                or (s.startswith("**") and s.endswith("**"))):
            flush(); cur = None
            continue
        if s == "-" or s.startswith("- "):
            flush()
            cur = s[1:].strip()
        elif cur is not None:
            cur += " " + s
    flush()
    return list(enumerate([c for c in out if c], 1))


def _readability_lint(body):
    # implements: ARCH-LINTCHECKS-025  # implements: REQ-LINT-863
    """Readability of the normative prose: joins per line, anonymous
    subjects, sentence and clause length, and one obligation per clause."""
    findings = []
    # prose readability (warn): only on the Contract + Acceptance sections
    for name in CONTRACT_LABELS + ACCEPTANCE_LABELS:
        for ln in _prose_lint(body, name):
            low = ln.lower()
            # Every line in a Contract/Acceptance section is normative by
            # virtue of the section it sits in, so the join count applies
            # to all of them. This used to be gated on `"shall" in low or
            # "must" in low`, which made the check silent for the plain
            # present-tense voice — a clarity rule keyed on a magic word
            # misses clauses.
            joins = len(re.findall(r"\b(?:and|or)\b", low))
            if joins >= cfg.LINT_STACKED_CONNECTORS:
                findings.append({
                    "severity": "warn", "check": "stacked-conditions",
                    "detail": "{} 'and'/'or' joins in one normative "
                              "line: {}".format(joins, _clip(ln))})
            # Contract only: a clause whose subject is a bare "It" forces the
            # reader to hold the requirement's title in their head to know what
            # is being promised. Name it. Acceptance prose is exempt — a Then
            # clause saying "it returns …" reads fine.
            if name in CONTRACT_LABELS and re.match(r"^It\s+[a-z]", ln):
                findings.append({
                    "severity": "warn", "check": "anonymous-subject",
                    "detail": "clause opens with an unnamed 'It' — name "
                              "the subject: {}".format(_clip(ln))})
    # statement atomicity (warn): a Contract bullet spanning more than
    # LINT_CLAUSE_SENTENCES sentences packs several statements into one
    # clause (split it). Sentence COUNT is the only dimension here —
    # `long-sentence` owns words per sentence and `statement-size` owns
    # words per clause — so the three checks never flag the same line
    # for the same reason, and a correct two- or three-sentence clause
    # stays silent. Read whole CLAUSES, not the physical lines
    # `_prose_lint` yields. These files wrap near 95 columns, so a
    # line-based count can never see a clause that spans several lines —
    # which is why this check reported 0 corpus-wide while measuring the
    # wrong unit. Measured before the switch: 0 of 625 non-draft clauses
    # hold more than three sentences, so widening the unit changes
    # nothing the check says today.
    clauses = _contract_clauses(body)
    for _cn, ln in clauses:
        sents = _sentences(ln)
        if len(sents) > cfg.LINT_CLAUSE_SENTENCES:
            findings.append({
                "severity": "warn", "check": "statement-too-long",
                "detail": "statement spans {} sentences (>{}): {}".format(
                    len(sents), cfg.LINT_CLAUSE_SENTENCES, _clip(ln))})
    # statement-size (warn, advisory): a Contract clause well past the
    # length a single obligation normally needs. Measured per CLAUSE, not
    # per line — see _contract_clauses. Advisory by contract: exceeding
    # the threshold never makes a clause invalid and never asserts that
    # it holds two obligations, which the engine cannot observe
    # (ARCH-ATOMICITY-049). The finding carries clause_n/clause_text so
    # `--decompose` can scaffold from the same clause without re-parsing.
    for _n, _clause in clauses:
        _cw = _clause_words(_clause)
        if _cw > cfg.LINT_STATEMENT_WORDS:
            findings.append({
                "severity": "warn", "check": "statement-size",
                "clause_n": _n, "clause_text": _clause,
                "detail": "clause {} is {} words (>{}) \u2014 re-read it for "
                          "decomposition: {}".format(
                              _n, _cw, cfg.LINT_STATEMENT_WORDS,
                              _clip(_clause))})
    return findings


def _terms_lint(body):
    # implements: ARCH-LINTCHECKS-025  # implements: REQ-LINT-863
    """Words that make a clause untestable: vague quality terms, and a
    modal the section header already supplies."""
    findings = []
    # vague terms (warn): a Contract bullet using a non-testable quality word is
    # ambiguous (IEEE 29148). Code spans (`backticked`) are stripped first so a
    # backticked identifier is never flagged. One finding per distinct term.
    # Iterates CONTRACT_LABELS (current `## Description` first, legacy `##
    # Contract` still honoured) rather than the literal string "contract" — a
    # hardcoded legacy label here left this check dead on every requirement
    # using the current heading.
    seen_vague = set()
    for name in CONTRACT_LABELS:
        for ln in _prose_lint(body, name):
            bare = re.sub(r"`[^`]*`", " ", ln)
            for w in _WORD_RE.findall(bare):
                lw = w.lower()
                if lw in LINT_VAGUE_TERMS and lw not in seen_vague:
                    seen_vague.add(lw)
                    findings.append({
                        "severity": "warn", "check": "vague-term",
                        "detail": "vague word '{}' (no testable "
                                  "meaning): {}".format(w, _clip(ln))})
    # redundant modal (warn): "shall"/"must" on a Contract clause is either dead
    # weight (the section header already binds every line) or a stray English
    # modal dropped into a non-English clause. Same
    # one-finding-per-distinct-term shape as vague-term, above. Same
    # CONTRACT_LABELS iteration as vague-term, above, for the same reason.
    seen_modal = set()
    for name in CONTRACT_LABELS:
        for ln in _prose_lint(body, name):
            bare = re.sub(r"`[^`]*`", " ", ln)
            for w in _WORD_RE.findall(bare):
                lw = w.lower()
                if lw in LINT_MODAL_WORDS and lw not in seen_modal:
                    seen_modal.add(lw)
                    findings.append({
                        "severity": "warn", "check": "redundant-modal",
                        "detail": "redundant modal '{}' (the Contract "
                                  "header already binds "
                                  "every line — use plain present "
                                  "tense): {}".format(w, _clip(ln))})
    return findings
