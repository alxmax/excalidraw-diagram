"""TF-IDF over contracts: `dupes` and `search`."""
import argparse, math, re

from . import config as cfg
from .i18n import _load_translations
from .model import _as_list
from .sections import ACCEPTANCE_LABELS, CONTRACT_LABELS, _from_any
from .text import _bullets, _req_title, _section_raw


_SIMILAR_STOP = frozenset((
    "the", "and", "for", "shall", "with", "that", "this", "from", "into", "its",
    "not", "are", "has", "have", "when", "then", "given", "each", "one", "any",
    "per", "via", "use", "used", "must", "code", "requirement", "requirements",
))


def _sim_tokens(text):  # implements: ARCH-SIMILAR-016  # implements: REQ-SIMILAR-921
    """Lowercase alphanumeric tokens of length >= 3, minus stopwords and pure
    numbers — the bag of words a requirement is compared on. Deterministic."""
    return [t for t in re.findall(r"[a-z0-9]+", text.lower())
            if len(t) >= 3 and not t.isdigit() and t not in _SIMILAR_STOP]


def _placeholder_contract(body):  # implements: ARCH-SIMILAR-016
    """True when every Contract bullet is still a `TODO:` scaffold line. Five evidence
    runs scored thousands of freshly-drafted stubs as near-duplicates of each other on
    template text alone (fabric: 6,340 pairs for 638 drafts) — nothing authored, nothing
    to compare."""
    bullets = _from_any(_bullets, body, CONTRACT_LABELS)
    return bool(bullets) and all(b.strip().upper().startswith("TODO") for b in bullets)


def _exemption_reason_recorded(body, check):
    # implements: ARCH-AUDIT-065  # implements: REQ-AUDIT-971
    """True when the requirement's own prose mentions the check it exempts itself from.

    Deliberately the crudest possible test: the check's name appearing anywhere in the
    body. It cannot judge whether the reason is a GOOD one — no mechanical test can —
    and it is not trying to. It only makes the exemption cost one sentence a reviewer
    can argue with, instead of one frontmatter token nobody ever reads."""
    return check.lower() in (body or "").lower()


def _exemptions_in_force(reqs):  # implements: ARCH-AUDIT-065  # implements: REQ-AUDIT-971
    """Every `lint_exempt:`/`gate_exempt:` entry in the corpus, as records carrying the
    requirement, the field, the silenced check and whether a reason is recorded.

    An exemption is a finding somebody decided not to see. Listing them is what keeps
    "silenced" from becoming "invisible": a corpus that exempted forty checks shows
    forty lines here, and the count is the debt."""
    out = []
    for rid in sorted(reqs):
        r = reqs[rid]
        meta, body = r["meta"], r["body"]
        for field in ("lint_exempt", "gate_exempt"):
            for check in _as_list(meta.get(field)):
                out.append({"id": rid, "field": field, "check": check,
                            "reason": _exemption_reason_recorded(body, check)})
    return out


def _corpus_shape(reqs):  # implements: ARCH-AUDIT-065  # implements: REQ-AUDIT-972
    """How the corpus sits on the V-model's left arm: how many requirements declare a
    `level:`, how they spread across the rungs, and how many `satisfies:` edges hold the
    pyramid together.

    `level:` is opt-in (the template ships it commented out) so an existing corpus keeps
    its behaviour, and the consequence is that a repo can run the engine for months with
    every requirement on one rung and nothing ever mentioning the other two. This says it
    once, in `audit`, and never in the gate: adopting a level axis is a decision, not a
    defect.

    `auto` counts the rungs the ENGINE wrote (`level_source: auto`, ADR-0030). Since
    `init` drafts a pyramid, a corpus can now be fully levelled and still be nothing but
    the engine's own guesses — every other number here would read as healthy. This is the
    number ADR-0030's revisit trigger asks for: a pyramid still made of proposals is
    untriaged, not done."""
    total = len(reqs)
    levels, edges, auto = {}, 0, 0
    for r in reqs.values():
        meta = r["meta"]
        lv = meta.get("level")
        if lv:
            levels[lv] = levels.get(lv, 0) + 1
            if meta.get("level_source") == "auto":
                auto += 1
        edges += len(_as_list(meta.get("satisfies")))
    levelled = sum(levels.values())
    return {"total": total, "levelled": levelled, "levels": levels,
            "satisfies_edges": edges, "auto": auto,
            "flat": bool(total) and levelled * 10 < total}


def _redundant_groups(reqs):  # implements: REQ-REDUNDANCY-058
    """Requirements whose Description clauses are IDENTICAL once case and whitespace are
    normalised, grouped, each group sorted and the groups ordered by their first id.

    This is the exact-match floor under `dupes`, not a second opinion on it: no threshold,
    no scoring, so a group is a duplicate by construction and never a judgement call. It
    exists because decomposing several architecture requirements can mint the same
    obligation twice — the same clause authored in two parents becomes two detailed-design
    requirements — and nothing else in the engine notices. `dupes` finds the near-matches
    this cannot; neither replaces the other.

    Draft placeholders are skipped: every freshly scaffolded requirement carries the same
    `TODO:` line, so counting those would report the scaffold as a duplicate of itself
    hundreds of times and drown the real finding."""
    groups = {}
    for rid, r in sorted(reqs.items()):
        body = r["body"]
        if _placeholder_contract(body):
            continue
        joined = " ".join(_from_any(_bullets, body, CONTRACT_LABELS))
        key = re.sub(r"\s+", " ", joined).strip().lower()
        if key:
            groups.setdefault(key, []).append(rid)
    return sorted((sorted(v) for v in groups.values() if len(v) > 1), key=lambda g: g[0])


def _sim_text(body):  # implements: ARCH-SIMILAR-016  # implements: REQ-SIMILAR-921
    """The text similarity is computed on: title, intent line, and Contract bullets.
    Notes & limitations is left out — it is dense and would only add noise."""
    parts = [_req_title(body, "")]
    for line in body.splitlines():
        if line.strip().startswith(">"):
            parts.append(line.strip().lstrip(">").strip())
            break
    parts += _from_any(_bullets, body, CONTRACT_LABELS)
    return " ".join(parts)


def _tfidf(docs):  # implements: ARCH-SIMILAR-016  # implements: REQ-SIMILAR-922
    """docs: {id: token_list}. Returns {id: {term: weight}} with smoothed idf =
    log((1 + N) / (1 + df)) + 1 — always positive (so a 2-doc corpus does not
    collapse to zero), while still down-weighting terms common across requirements."""
    N = len(docs)
    df = {}
    for toks in docs.values():
        for t in set(toks):
            df[t] = df.get(t, 0) + 1
    vecs = {}
    for rid, toks in docs.items():
        tf = {}
        for t in toks:
            tf[t] = tf.get(t, 0) + 1
        vecs[rid] = {t: c * (math.log((1 + N) / (1 + df[t])) + 1) for t, c in tf.items()}
    return vecs


def _cosine(a, b):  # implements: ARCH-SIMILAR-016  # implements: REQ-SIMILAR-922
    """Cosine similarity of two {term: weight} vectors, in [0, 1]. The result is
    clamped to 1.0 because floating-point rounding can push parallel vectors a hair
    over 1.0 (e.g. 1.0000000000000002), which would break the documented range."""
    if not a or not b:
        return 0.0
    dot = sum(a[t] * b[t] for t in set(a) & set(b))
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return min(1.0, dot / (na * nb)) if na and nb else 0.0


def _threshold_arg(v):  # implements: ARCH-SIMILAR-016
    """argparse type for `--threshold`: a finite number in (0, 1]. Rejects nan/inf
    (which silently swallow or admit every pair under `>=`) and out-of-range cutoffs."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError("threshold must be a number")
    if not math.isfinite(f) or not (0.0 < f <= 1.0):
        raise argparse.ArgumentTypeError("threshold must be a finite number in (0, 1]")
    return f


def _add_test_suite_links(rid, f, impl_of, linked):
    # implements: REQ-SIMILAR-921
    """Link `rid` with every requirement `f` implements, other than itself."""
    for other in impl_of.get(f, ()):
        if other != rid:
            linked.add(frozenset((rid, other)))


def _test_suite_pairs(members):  # implements: REQ-SIMILAR-921
    """Pairs (A, B) where a `tested-by` member file of A is an `implements` member of B —
    i.e. B is the requirement that IS A's test suite. Such a pair shares vocabulary by
    construction and is a known link, not a duplicate. Empty when no member map is given."""
    impl_of = {}   # file -> set of requirement ids implemented in it
    for rid, mem in (members or {}).items():
        for role, f, _ in mem:
            if role == "implements":
                impl_of.setdefault(f, set()).add(rid)
    linked = set()
    for rid, mem in (members or {}).items():
        for role, f, _ in mem:
            if role == "tested-by":
                _add_test_suite_links(rid, f, impl_of, linked)
    return linked


def _hierarchy_pairs(reqs):
    # implements: ARCH-SIMILAR-016  # implements: REQ-SIMILAR-921
    """Pairs the level axis already explains: a child with its parent (the parent's
    summary clause names it) and two children of one parent (both restate that parent's
    clauses). 25 of the 40 pairs `dupes` reported on this corpus were siblings; a known
    link is not a duplicate finding."""
    linked, kids_of = set(), {}
    for rid, r in reqs.items():
        for up in _as_list((r.get("meta") or {}).get("satisfies")):
            linked.add(frozenset((rid, up)))
            kids_of.setdefault(up, []).append(rid)
    for kids in kids_of.values():
        for i in range(len(kids)):
            for j in range(i + 1, len(kids)):
                linked.add(frozenset((kids[i], kids[j])))
    return linked


def cmd_similar(reqs, threshold=cfg.SIMILAR_THRESHOLD, members=None, top=None):
    # implements: ARCH-SIMILAR-016  # implements: REQ-SIMILAR-920  # implements: REQ-SIMILAR-923
    """Report requirement pairs whose contracts overlap at or above `threshold`
    (cosine over TF-IDF of title + intent + Contract), most-similar-first, so a human
    can spot a probable duplicate or a capability that should be merged. Read-only and
    always exit 0 (advisory). Smoothed idf down-weights shared boilerplate so it
    does not inflate the score. Callers pass a validated threshold in (0, 1].
    With `members`, a pair linked by `tested-by` (one requirement is the other's test
    suite) is skipped and counted instead of reported."""
    linked = set(_test_suite_pairs(members)) | _hierarchy_pairs(reqs)
    placeholder = sorted(rid for rid, r in reqs.items() if _placeholder_contract(r["body"]))
    docs = {rid: _sim_tokens(_sim_text(r["body"])) for rid, r in reqs.items()
            if rid not in placeholder}
    docs = {rid: toks for rid, toks in docs.items() if toks}   # skip empty contracts
    if placeholder:
        print("skipped {} requirement(s) whose Contract is still the draft placeholder — "
              "dupes compares authored contracts only.\n".format(len(placeholder)))
    if len(docs) < 2:
        print("Need at least two requirements with contract text to compare.")
        return 0
    vecs = _tfidf(docs)
    ids = sorted(vecs)
    pairs = []
    skipped_linked = 0
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            s = _cosine(vecs[ids[i]], vecs[ids[j]])
            if s >= threshold:
                if frozenset((ids[i], ids[j])) in linked:
                    skipped_linked += 1
                    continue
                shared = sorted(set(vecs[ids[i]]) & set(vecs[ids[j]]),
                                key=lambda t: (-(vecs[ids[i]][t] + vecs[ids[j]][t]), t))[:5]
                pairs.append((s, ids[i], ids[j], shared))
    pairs.sort(key=lambda x: (-x[0], x[1], x[2]))
    if skipped_linked:
        print(("skipped {} pair(s) linked by tested-by or satisfies, or siblings under one "
               "parent (a requirement and its own test suite, a parent and its child, and two "
               "children of one parent share vocabulary by construction).\n")
              .format(skipped_linked))
    if not pairs:
        print("No overlapping requirement pairs at or above {:.2f}. {} requirement(s) compared."
              .format(threshold, len(docs)))
        return 0
    print("{} probable-duplicate pair(s) at or above {:.2f} (of {} requirement(s)):\n".format(
        len(pairs), threshold, len(docs)))
    shown = pairs if top is None else pairs[:top]
    for s, a, b, shared in shown:
        print("  {:.2f}  {}  <->  {}".format(s, a, b))
        print("        shared terms: {}".format(", ".join(shared) or "(none)"))
    if len(shown) < len(pairs):
        print("  ... {} more pair(s) — raise --top to see them".format(len(pairs) - len(shown)))
    print("\nThese contracts overlap — check they are not the same capability "
          "implemented twice. Merge or differentiate, then re-run.")
    return 0


# ---------- search (free-text requirement lookup) ----------
# Ranks requirements against a free-text query with the SAME lexical TF-IDF/cosine
# used by `dupes` — reused, not re-implemented. The floor is NOT the dupes 0.35
# pair-threshold: a short query is a sparse vector, so query-vs-doc cosine runs far
# lower than doc-vs-doc. Calibrated on the 39-requirement corpus, a correct top hit
# scores ~0.13-0.67 while a no-lexical-overlap query tops out ~0.00-0.04, so 0.05
# cleanly separates a real match from noise. Below it, `search` says so rather than
# presenting a spurious top result with the same authority as a real one.
SEARCH_FLOOR = 0.05
SEARCH_TOP = 5


# Searching a requirement browser for `ARCH-CHECK-006` used to return
# REQ-ORPHANCODE-888 and not the requirement itself: the bag of words is title +
# intent + clauses, and an id is in none of them, so "arch" and "check" were matched
# as ordinary prose. An id is the primary key of this corpus; a query that names one
# is not asking to be ranked.
SEARCH_ID_MAX = 3          # substring id hits shown before the lexical ranking


def _id_matches(reqs, query):  # implements: ARCH-SEARCH-036  # implements: REQ-SEARCH-965
    """Requirement ids the query names, best first: an exact id, then ids it prefixes,
    then ids that contain it. An exact hit is alone and unconditional; the looser two
    are capped so a common word like `map` cannot crowd out the lexical ranking."""
    q = (query or "").strip().upper()
    if len(q) < 3:
        return []
    if q in reqs:
        return [q]
    prefix = sorted(rid for rid in reqs if rid.upper().startswith(q))
    inner = sorted(rid for rid in reqs if q in rid.upper() and rid not in prefix)
    return (prefix + inner)[:SEARCH_ID_MAX]


def _text_matches(reqs, query, translations=None, skip=()):  # implements: REQ-SEARCH-965
    """Requirements whose title, description or cases plainly contain the query, plus any
    cached translation of them.

    Scoped to exactly what the reader is asking about: the normative text and the cases
    that prove it. `## Context` is deliberately excluded, for the same reason the ranking
    bag excludes it — a word that appears only in commentary is not what the requirement
    is about, and REQ-SEARCH-912 already decided that.

    This is also the layer that answers a query in the language the reader is being
    shown: the ranking model weights one language's tokens, so a translated requirement
    is invisible to it. Substring, not ranked, and it only fills the slots the model
    left empty."""
    q = (query or "").strip().lower()
    if len(q) < 3:
        return []
    out = []
    for rid in sorted(reqs):
        if rid in skip:
            continue
        body = reqs[rid]["body"]
        hay = "\n".join([
            _req_title(body, rid),
            _from_any(_section_raw, body, CONTRACT_LABELS) or "",
            _from_any(_section_raw, body, ACCEPTANCE_LABELS) or "",
        ]).lower()
        for entry in ((translations or {}).get(rid) or {}).values():
            if isinstance(entry, dict):
                hay += "\n" + "\n".join(str(v).lower() for v in entry.values())
        if q in hay:
            out.append(rid)
    return out


def cmd_search(reqs, query, top=SEARCH_TOP, floor=SEARCH_FLOOR, reqs_dir=None):
    # implements: ARCH-SEARCH-036  # implements: REQ-SEARCH-912  # implements: REQ-SEARCH-913
    # implements: REQ-SEARCH-914  # implements: REQ-SEARCH-915
    """Rank requirements by lexical relevance to `query` (cosine over TF-IDF of the
    same title + intent + Contract text `dupes` compares on). Read-only, always exit
    zero. Prints each hit's cosine score so a weak match is visible as weak, and emits
    an explicit no-strong-match line when the best score is below `floor` — so a
    lexical near-miss is never dressed up as an answer."""
    ids = _id_matches(reqs, query)
    qtok = _sim_tokens(query or "")
    if not qtok and not ids:
        print("No searchable terms in {!r} (need a word of 3+ letters that is not a "
              "stopword). Nothing to rank.".format(query or ""))
        return 0
    docs = {rid: _sim_tokens(_sim_text(r["body"])) for rid, r in reqs.items()}
    docs = {rid: toks for rid, toks in docs.items() if toks}   # skip empty contracts
    if not docs:
        print("No requirements with contract text to search.")
        return 0
    top = max(1, top)
    corpus = dict(docs)
    corpus["\x00query"] = qtok        # fold the query into the corpus so idf spans docs+query
    vecs = _tfidf(corpus)
    qv = vecs["\x00query"]
    scored = sorted(((_cosine(qv, vecs[rid]), rid) for rid in docs),
                    key=lambda x: (-x[0], x[1]))
    # Order: id, then literal text, then the ranked model. A document that CONTAINS the
    # query is stronger evidence than a partial token overlap with it -- a phrase that
    # appears verbatim inside a case used to lose to a 0.10 cosine somewhere else.
    translations = _load_translations(reqs, reqs_dir) if reqs_dir else {}
    text = _text_matches(reqs, query, translations, skip=set(ids))[:max(0, top - len(ids))]
    seen = set(ids) | set(text)
    lexical = [(s, rid) for s, rid in scored
               if s >= floor and rid not in seen][:max(0, top - len(seen))]
    if not (ids or lexical or text):
        print("No match for {!r}: no id, no literal text, and the best lexical (cosine) "
              "score {:.3f} is below the {:.2f} floor. Try different words, or "
              "`dupes`/grep.".format(
                  query, scored[0][0] if scored else 0.0, floor))
        return 0
    print("{} match(es) for {!r} — id, then literal text, then cosine score (lexical, "
          "not synonym-aware):\n".format(len(ids) + len(lexical) + len(text), query))
    for rid in ids:
        print("  {:>6}  {}  {}".format("id", rid, _req_title(reqs[rid]["body"], rid)))
    for rid in text:
        print("  {:>6}  {}  {}".format("text", rid, _req_title(reqs[rid]["body"], rid)))
    for s, rid in lexical:
        print("  {:.3f}  {}  {}".format(s, rid, _req_title(reqs[rid]["body"], rid)))
    return 0
