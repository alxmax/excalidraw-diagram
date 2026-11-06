"""Tables -> a dimensional role for each: fact, dimension, bridge or unknown.

The rule from the brief, made explicit: a table with several foreign keys out and
additive numeric columns is a fact candidate; a table other tables reference, holding
descriptive columns, is a dimension candidate. Each piece of evidence has a weight and a
sentence, so a classification is never a bare label: `reason` lists exactly what was
seen, and `confidence` says how far the winner is ahead AND how much it rests on.

    confidence = (winner - runner-up) / winner  x  min(1, winner / STRONG)
                 how far ahead                      how much evidence
                                                    unknown when the winner scores < 3
                                                    or two roles tie

So 100% needs a clear lead over the runner-up and STRONG (8) points of evidence; a table
with a lead but only a few points, or plenty of points but a close rival, reads lower.

The name prefix (fact_, dim_, bridge_ ...) is one piece of evidence, not the verdict: a
schema without prefixes classifies from its structure alone. A table whose columns are
all keys is a bridge by structure but could equally be a factless fact; the reason says so.
"""

import re

THRESHOLD = 3
_GUESS = " (guessed from the names: no data types declared)"
STRONG = 8              # evidence at which a clear lead reads as full confidence
_SCORED = ("fact", "dimension", "bridge")
_STAGING = re.compile(r"^(stg|staging|raw|tmp|temp|src)_", re.I)
_PREFIX = {"fact": re.compile(r"^(fact|fct|f)_", re.I),
           "dimension": re.compile(r"^(dim|dimension|d)_", re.I),
           "bridge": re.compile(r"^(bridge|brg|bdg)_", re.I)}
_NUMERIC = re.compile(r"^(?:small|big|tiny|medium)?(?:int|integer|serial|numeric|decimal|"
                      r"number|float\d*|double|real|money)\b", re.I)
_DESCRIPTIVE = re.compile(r"^(?:n?var)?char|^character|^n?text|^citext|^string|^date|^time|"
                          r"^bool", re.I)
_KEYLIKE = re.compile(r"(^id$|_id$|_key$|_sk$|_fk$|_no$|_num$|_number$|_code$)", re.I)
_CALENDAR = re.compile(r"^(year|month|day|week|quarter|hour|minute|fiscal_\w+|day_of_\w+)$", re.I)
# Only for a column with NO declared type (a dbt schema.yml usually has none): the name is all
# there is to read, so it is read, and the reason says the call was a guess.
_MEASURE_NAME = re.compile(r"(^|_)(amount|total|count|qty|quantity|price|cost|revenue|sum|"
                           r"balance|fee|tax|discount)(_|$)|^number_of_", re.I)
_DESCRIPTIVE_NAME = re.compile(r"(^|_)(name|city|country|region|address|email|phone|status|"
                               r"type|category|method|description|title|label|segment|"
                               r"channel|brand)(_|$)", re.I)


class Classification(object):
    """A table's role ('fact' | 'dimension' | 'bridge' | 'unknown'), a 0..1 confidence,
    and the sentence listing the evidence behind both."""

    __slots__ = ("role", "confidence", "reason", "overridden")

    def __init__(self, role, confidence, reason, overridden=False):
        self.role, self.confidence, self.reason = role, confidence, reason
        self.overridden = overridden        # True when roles.yml, not the rules, chose it


def _fk_columns(table):
    return {c for fk in table.foreign_keys for c in fk.columns}


def _judge_columns(plain):
    """(measures, descriptive, guessed): the non-key columns read as additive numbers and as
    descriptive text, from their declared types; `guessed` names the lists (a subset of
    'measures', 'descriptive') that had to rest on a column's name because it has no type."""
    measures, descriptive, guessed = [], [], set()
    for c in plain:
        if c.type:
            if _NUMERIC.match(c.type) and not _CALENDAR.match(c.name):
                measures.append(c.name)
            elif _DESCRIPTIVE.match(c.type):
                descriptive.append(c.name)
        elif _MEASURE_NAME.search(c.name) and not _CALENDAR.match(c.name):
            measures.append(c.name)
            guessed.add("measures")
        elif _DESCRIPTIVE_NAME.search(c.name):
            descriptive.append(c.name)
            guessed.add("descriptive")
    return measures, descriptive, guessed


def _profile(table, referrers):
    """The facts about `table` the rules read: measures, descriptive columns, FK counts."""
    keys = set(table.primary_key) | _fk_columns(table)
    plain = [c for c in table.columns if c.name not in keys and not _KEYLIKE.search(c.name)]
    measures, descriptive, guessed = _judge_columns(plain)
    return {
        "measures": measures,
        "descriptive": descriptive,
        "guessed": guessed,
        "fk_out": len({fk.ref_table for fk in table.foreign_keys} - {table.name}),
        "fk_in": len(referrers.get(table.name, ())),
        "all_keys": all(c.name in keys for c in table.columns),
    }


def _evidence(table, p):
    """{role: [(weight, sentence)]} for the three scored roles."""
    ev = {role: [] for role in _SCORED}
    for role in _SCORED:
        m = _PREFIX[role].match(table.name)
        if m:
            ev[role].append((3, "name prefix %s_" % m.group(1).lower()))
    if p["fk_out"] >= 2:
        ev["fact"].append((2, "%d foreign keys to other tables" % p["fk_out"]))
    if p["measures"]:
        shown = p["measures"][:3]
        ev["fact"].append((len(shown), "numeric measures " + ", ".join(shown)
                           + _GUESS * ("measures" in p["guessed"])))
    if p["fk_out"] and not p["fk_in"]:
        ev["fact"].append((1, "no table references it"))
    if p["fk_in"]:
        ev["dimension"].append((2, "referenced by %d table%s"
                                % (p["fk_in"], "s" if p["fk_in"] > 1 else "")))
    if p["descriptive"]:
        shown = p["descriptive"][:3]
        ev["dimension"].append((len(shown), "descriptive columns " + ", ".join(shown)
                                + _GUESS * ("descriptive" in p["guessed"])))
    if not p["fk_out"]:
        ev["dimension"].append((1, "no foreign keys out"))
    if p["fk_out"] >= 2 and p["all_keys"] and not p["measures"]:
        ev["bridge"].append((4, "every column is a key (a factless fact is the alternative)"))
    return ev


def _decide(name, ev):
    scores = {role: sum(w for w, _ in ev[role]) for role in _SCORED}
    ranked = sorted(_SCORED, key=lambda r: -scores[r])
    top, second = ranked[0], ranked[1]
    summary = ", ".join("%s %d" % (r, scores[r]) for r in _SCORED)
    if scores[top] < THRESHOLD:
        return Classification("unknown", 0.0, "not enough evidence (%s)" % summary)
    if scores[top] == scores[second]:
        return Classification("unknown", 0.0, "%s and %s tie (%s)" % (top, second, summary))
    lead = (scores[top] - scores[second]) / float(scores[top])
    conf = lead * min(1.0, scores[top] / float(STRONG))
    return Classification(top, round(conf, 2), "; ".join(s for _, s in ev[top]))


def classify_tables(tables, overrides=None):
    """{table name: Classification} for every table, from names and structure alone.

    `overrides` is a {table name: role} map (see roles.parse_roles) that replaces the
    rules' answer for the tables it names, at confidence 1 and flagged `overridden`; the
    reason keeps what the rules had said. A name the schema does not define raises
    ValueError, because a typo would otherwise be silently ignored."""
    # implements: REQ-DATAMODEL-902
    # implements: REQ-DATAMODEL-906
    referrers = {}
    for t in tables:
        for fk in t.foreign_keys:
            if fk.ref_table != t.name:
                referrers.setdefault(fk.ref_table, set()).add(t.name)
    out = {}
    for t in tables:
        m = _STAGING.match(t.name)
        if m:
            out[t.name] = Classification(
                "unknown", 0.0, "staging table (prefix %s_): outside the star schema"
                % m.group(1).lower())
        else:
            out[t.name] = _decide(t.name, _evidence(t, _profile(t, referrers)))
    for name, role in (overrides or {}).items():
        if name not in out:
            raise ValueError("roles file names %s, which the schema does not define "
                             "(tables: %s)" % (name, ", ".join(out)))
        found = out[name]
        said = ("unknown" if found.role == "unknown"
                else "%s (%d%%)" % (found.role, round(found.confidence * 100)))
        out[name] = Classification(role, 1.0, "set in the roles file; the rules had said %s"
                                   % said, overridden=True)
    return out
