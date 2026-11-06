"""`clarify`: the questions a requirement has not answered."""
import json, re

from . import MAP_ENGINE_VERSION, config as cfg
from .lintrules import _count_ac, _over_scoped
from .sections import ACCEPTANCE_LABELS, CONTRACT_LABELS, _from_any
from .text import _bullets, _ellipsis, _req_title, _section_raw


def blocking_question_rules(reqs):  # implements: REQ-CLARIFY-975
    """{rid: sorted [rule]} for EVERY requirement, empty list included.

    The RULE is the fingerprint, not the prose: two runs of the same
    defect are the same question, and rewording a clause does not
    invent a new one.

    Requirements with no questions are recorded too, on purpose.
    Otherwise "absent from the snapshot" would mean both "never seen"
    and "seen, and clean", so a requirement going from zero questions
    to one would be mistaken for a brand-new file and silenced — which
    is exactly the case this check exists to catch."""
    domain = _domain_heads(reqs)
    return {rid: sorted({q["rule"] for q in
                         _clarify_questions(rid, r, reqs, domain)
                         if q["severity"] == "blocking"})
            for rid, r in reqs.items()}


# ---------- clarify: the questions a requirement has not answered yet ---------
# Deterministic and read-only, like every other advisory surface here: it names
# a shape that is under-specified, never a defect, and never blocks. The point
# is the moment BEFORE code exists -- an author writes "the gate reports
# errors quickly", nobody asks what quickly means, and the ambiguity is
# discovered by the reader of the failing test three weeks later.
# The hedge and failure words are `cfg.CLARIFY_HEDGES` and
# `cfg.CLARIFY_FAILURE_WORDS`, which a repository replaces (ADR-0079).
# "several", "many", "various", "small" and "large" ask nothing: 23 of this
# corpus's 27 vague-term questions, none real in a sample (ADR-0078).
# A hedge counts only as a whole word outside a code span, so "fastest" is not
# "fast" and a quoted `appropriate` is an example. A code span leaves group 1
# empty. Built per call, since a config can change the list; `re` caches the
# compiled pattern itself.


def _hedge_re():
    # implements: REQ-CLARIFY-1102  # implements: REQ-CLARIFY-1115
    words = "|".join(map(re.escape, cfg.CLARIFY_HEDGES)) or "(?!)"
    return re.compile(r"`[^`]*`|(?<![\w-])(" + words + r")(?![\w-])", re.I)
# A clause that ends by naming another requirement (`... [[REQ-X-001]]`, or
# `[[REQ-X-001]] details the behaviour.`) hands its cases to that requirement.
_CLARIFY_DELEGATES_RE = re.compile(
    r"\]\](?:\s+details the behaviou?r)?\s*\.?\s*$")


# Every case of ARCH-SEARCH-036 described its input as prose to be matched:
# terms that match, terms that do not, terms that tokenize to nothing, more
# matches than --top. The author varied the QUALITY of one kind of input and
# never its KIND, so nobody asked what happens when the query is an id -- and
# the answer, for two years, was "the wrong requirement". A gate cannot catch
# that: the code did what the contract said. This asks.
CLARIFY_MONOCULTURE_MIN = 3     # cases needed before the shape means anything
CLARIFY_MONOCULTURE_SHARE = 0.75
# a Given-head this common across the corpus IS the domain
CLARIFY_DOMAIN_SHARE = 0.10
# ...but "common across the corpus" needs a corpus to be common in
CLARIFY_DOMAIN_MIN = 30
_GIVEN_RE = re.compile(r"^\s+Given\s+(.*)$", re.M)
_CLARIFY_ARTICLES = frozenset((
    "a", "an", "the", "one", "two", "three", "no", "any", "some", "its",
    "their", "new", "old", "same", "other", "first", "second", "empty",
    "valid", "invalid", "single", "confirmed", "draft", "deprecated",
    "stale", "fresh", "missing", "real",
))


def _given_head(text):
    """The kind of thing a Given starts from: its first word that is not
    an article or a leading adjective. Crude on purpose -- it only has
    to be stable across cases. A letter is any script's letter, so
    "șablon" is not read as "ablon"."""
    # implements: REQ-CLARIFY-1115
    for w in re.findall(r"[^\W\d][\w`.-]*|`[\w`.-]*", text.lower()):
        w = w.strip("`")
        if len(w) < 3 or w in _CLARIFY_ARTICLES:
            continue
        return w
    return ""


def _given_heads(body):
    return [h for h in (_given_head(g) for g in
                        _GIVEN_RE.findall(
                            _from_any(_section_raw, body,
                                      ACCEPTANCE_LABELS) or ""))
            if h]


def _domain_heads(reqs):
    """Words that open Givens across the whole corpus are that corpus's
    subject, not a narrow focus: in this repository every other case
    starts "a requirement ...". Flagging those would fire on 18% of
    the corpus and say nothing."""
    counts = {}
    total = 0
    for r in (reqs or {}).values():
        for h in _given_heads(r["body"]):
            counts[h] = counts.get(h, 0) + 1
            total += 1
    # Below a real sample every word looks dominant: in a
    # two-requirement corpus the one noun under examination is 75% of
    # all Given heads and would exclude itself.
    if total < CLARIFY_DOMAIN_MIN:
        return frozenset()
    return frozenset(w for w, c in counts.items()
                     if c / float(total) >= CLARIFY_DOMAIN_SHARE)


# What each rule rests on, so a reader can tell a fact from a guess: a
# section that is absent, two numbers that disagree, or a guess from wording
# or a count that never reads a case. Sampled on this corpus, most `wording`
# questions were false positives ("every candidate", "how many releases"), and
# so were 9 of 20 `clause-without-case` ones, 7 real (ADR-0075).
# implements: REQ-CLARIFY-1100
CLARIFY_BASIS = {
    "no-contract": "structure", "no-cases": "structure",
    "clause-without-case": "wording", "over-scoped": "count",
    "vague-term": "wording", "ambiguous-actor": "wording",
    "no-failure-case": "wording", "case-monoculture": "wording",
}


def _clarify_item(rule, severity, where, quote, question, suggest):
    # implements: ARCH-CLARIFY-062  # implements: REQ-CLARIFY-956
    # implements: REQ-CLARIFY-1100
    """One open-question record, in the shape `_clarify_questions` emits."""
    return {"rule": rule, "severity": severity, "basis": CLARIFY_BASIS[rule],
            "where": where, "quote": quote, "question": question,
            "suggest": suggest}


def _clause_questions(clauses):
    # implements: ARCH-CLARIFY-062  # implements: REQ-CLARIFY-956
    # implements: REQ-CLARIFY-1102
    """Per-clause advisory questions: vague terms and ambiguous actors.
    "All", "every" and "any" ask nothing: in a requirement they nearly
    always range over a finite set the engine owns, and 19 of 20 such
    questions were not real (ADR-0072). A number asks nothing either: 0 of
    the 9 unit questions on this corpus were real (ADR-0075)."""
    out = []
    for i, c in enumerate(clauses, 1):
        low = c.lower()
        where = "clause {}".format(i)
        # one hedge per clause is enough to start the conversation
        h = next((x for x in _hedge_re().finditer(low) if x.group(1)),
                 None)
        if h:
            out.append(_clarify_item(
                "vague-term", "advisory", where, c,
                'What is the measurable threshold behind "{}"?'
                .format(h.group(1)),
                "Replace it with a number and a unit, or with the "
                "observable "
                "condition it stands for."))
        # the subject only: "the system placeholder" mid-clause is a noun,
        # and "The System Map" a name
        if re.match(r"(?:[Ii]t|[Tt]he system) [a-z]", c):
            out.append(_clarify_item(
                "ambiguous-actor", "advisory", where, c,
                "Who performs this -- which command or component?",
                "Name the subject the title names, so the clause reads "
                "on its own."))
    return out


def _clause_case_gap_question(clauses, n_cases):
    # implements: ARCH-CLARIFY-062  # implements: REQ-CLARIFY-956
    """ONE question about the gap when clauses outnumber cases, not one
    per tail clause. The count is all this check knows: it compares
    two numbers and never reads a case to see which clause it proves.
    Accusing clauses n_cases+1.. by position was therefore a guess
    dressed as a finding, and a wrong one whenever an early clause is
    the uncovered one — e.g. a clause that delegates its cases to
    another requirement, which the counter cannot see. It sent the
    reader to rewrite a clause that already had its case."""
    if not (clauses and n_cases and len(clauses) > n_cases):
        return []
    # the difference is not a number of uncovered clauses: in a sample only
    # 4 of 7 real gaps matched it (ADR-0075)
    return [_clarify_item(
        "clause-without-case", "advisory", "Cases", "",
        "There are {} clauses and {} cases. Does each clause have a case "
        "that proves it? This check compares counts, not coverage: one "
        "case may prove two clauses, so it cannot say which clause, if "
        "any, is unproven.".format(len(clauses), n_cases),
        "Read the clauses against the cases. If an obligation is "
        "unproven, add or extend a case, or move the clause to the "
        "requirement that already carries its cases.")]


def _monoculture_question(body, reqs, domain):
    # implements: ARCH-CLARIFY-062  # implements: REQ-CLARIFY-956
    """The one question about every case starting from the same kind
    of input, unless that input IS the corpus's domain (see
    `_domain_heads`)."""
    heads = _given_heads(body)
    if len(heads) < CLARIFY_MONOCULTURE_MIN:
        return []
    counts = {}
    for h in heads:
        counts[h] = counts.get(h, 0) + 1
    common = max(sorted(counts), key=lambda k: counts[k])
    share = counts[common] / float(len(heads))
    if domain is None:
        domain = _domain_heads(reqs)
    if share >= CLARIFY_MONOCULTURE_SHARE and common not in domain:
        return [_clarify_item(
            "case-monoculture", "advisory", "Cases", "",
            '{} of {} Given lines open on the same word ("{}"). Do the '
            'cases cover the other kinds of input a caller can supply?'
            .format(counts[common], len(heads), common),
            "Read the Givens in context: a repeated word need not be a "
            "repeated kind of input. Add a case from the caller's side "
            "only if a kind is missing.")]
    return []


def _clarify_questions(rid, r, reqs=None, domain=None):
    # implements: ARCH-CLARIFY-062  # implements: REQ-CLARIFY-956
    # implements: REQ-CLARIFY-1102
    """The open questions one requirement has not answered, as records:
    {rule, severity, where, quote, question, suggest}. Deterministic --
    the same requirement always yields the same list, in the same
    order. `blocking` means the requirement cannot be implemented as
    written; everything else is advice. `domain` is
    `_domain_heads(reqs)`, passed in by the corpus-wide callers so it
    is read once rather than recomputed per requirement (it was 90% of
    a `sync`'s question pass, and quadratic in the corpus). A deprecated
    requirement is retired, so nothing in it waits for an answer."""
    if r["meta"].get("status") == "deprecated":
        return []
    body = r["body"]
    clauses = _from_any(_bullets, body, CONTRACT_LABELS)
    cases_low = _from_any(_section_raw, body, ACCEPTANCE_LABELS).lower()
    n_cases = _count_ac(body)
    out = []

    if not clauses:
        out.append(_clarify_item(
            "no-contract", "blocking", "Description", "",
            "What is this requirement's binding obligation? The "
            "Description carries no clause.",
            "Write one statement per obligation, present tense, "
            "naming the subject."))
    # a requirement kept as text has no cases to ask for (REQ-CUSTOMTRACE-1113)
    if n_cases == 0 and r["meta"].get("source") not in ("text", "html"):
        out.append(_clarify_item(
            "no-cases", "blocking", "Cases", "",
            "What observable behaviour proves this requirement holds? "
            "No labelled case is present.",
            "Add `CASE-1` with Given / When / Then, one per clause."))

    out.extend(_clause_questions(clauses))
    # a clause that hands its cases to another requirement is proved there,
    # so neither count below holds it
    own = [c for c in clauses if not _CLARIFY_DELEGATES_RE.search(c)]
    out.extend(_clause_case_gap_question(own, n_cases))

    # a need is one story with one Scenario, so it has no failure path to name
    if (n_cases and r["meta"].get("layer") != "need"
            and not any(w.lower() in cases_low
                     for w in cfg.CLARIFY_FAILURE_WORDS)):
        out.append(_clarify_item(
            "no-failure-case", "advisory", "Cases", "",
            "What happens on the failure path -- missing input, "
            "invalid value, nothing to do?",
            "Add one case for the way this can go wrong; it is the "
            "case implementations skip."))

    out.extend(_monoculture_question(body, reqs, domain))

    # lint's own predicate, so clarify never asks a split lint does not raise
    # implements: REQ-CLARIFY-1102
    if _over_scoped(body) and len(own) > cfg.LINT_CONTRACT_MAX:
        out.append(_clarify_item(
            "over-scoped", "advisory", "Description", "",
            "This requirement carries {} clauses and {} cases (advisory "
            "limits {} and {}). Which of them is a separate "
            "requirement?".format(len(own), n_cases,
                                  cfg.LINT_CONTRACT_MAX, cfg.LINT_AC_MAX),
            "Split the ones that could change for a different reason."))
    return out


def cmd_clarify(reqs, cap_id, as_json=False):
    # implements: ARCH-CLARIFY-062  # implements: REQ-CLARIFY-957
    """Print the open questions for one requirement (or the whole
    corpus's blocking ones when no id is given). Advisory: always exit
    0, writes nothing, and is never a gate rule -- an unanswered
    question is a conversation, not a build failure."""
    if cap_id and cap_id not in reqs:
        print("no requirement with id {} (expected requirements/{}.md)"
              .format(cap_id, cap_id))
        return 1
    ids = [cap_id] if cap_id else sorted(reqs)
    items = []
    domain = _domain_heads(reqs)
    for rid in ids:
        qs = _clarify_questions(rid, reqs[rid], reqs, domain)
        if not cap_id:
            qs = [q for q in qs if q["severity"] == "blocking"]
        if qs:
            items.append({"id": rid,
                          "title": _req_title(reqs[rid]["body"], rid),
                          "questions": qs})
    if as_json:
        print(json.dumps({"engine_version": MAP_ENGINE_VERSION,
                          "advisory": ("Deterministic open questions. "
                                       "Answer them in "
                                       "the requirement, not in code; "
                                       "nothing here is "
                                       "a gate rule."),
                          "requirements": items}, indent=2,
                         ensure_ascii=False))
        return 0
    if not items:
        print("{}: nothing unclear that this check can see.".format(
            cap_id or "corpus"))
        print("  next: reqmap.py " + ("gate --show " + cap_id if cap_id
                                      else "gate --risk"))
        return 0
    for it in items:
        blocking = [q for q in it["questions"]
                    if q["severity"] == "blocking"]
        print("{} · {}".format(it["id"], it["title"]))
        print("{} open question(s){}".format(
            len(it["questions"]),
            " — {} blocking".format(len(blocking)) if blocking else ""))
        n = 0
        for sev in ("blocking", "advisory"):
            group = [q for q in it["questions"] if q["severity"] == sev]
            if not group:
                continue
            print("\n{}".format(sev.upper()))
            for q in group:
                n += 1
                print(" {:>2}. [{} · {}] {}".format(
                    n, q["rule"], q["basis"], q["where"]))
                if q["quote"]:
                    print("     \"{}\"".format(_ellipsis(q["quote"], 92)))
                print("     {}".format(q["question"]))
                print("     -> {}".format(q["suggest"]))
        print("")
    if cap_id:
        print("Answer them in {}.md, then: reqmap.py gate --show {}"
              .format(cap_id, cap_id))
    return 0
