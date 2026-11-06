"""The words and pictograms that let a stranger read a data-model diagram.

Someone who has never met a star schema, or this repository, should not need to look
anything up: every colour has an icon and a plain sentence in the legend, every term the
picture uses is defined in the glossary in everyday words, and every table says why it was
given its role. Only the terms that actually appear on the diagram are defined, so a small
schema gets a small glossary.

Nothing here decides anything. data_model.py decides what is drawn; this module only says
what it means.
"""

ICON = {"fact": "\U0001F4CA", "dimension": "\U0001F50D", "bridge": "\U0001F309",
        "unknown": "❓", "note": "\U0001F4DD", "pk": "\U0001F511", "fk": "\U0001F517",
        "grain": "\U0001F3AF", "surrogate-key": "\U0001F194", "scd2": "\U0001F553",
        "orphan-fk": "\U0001F47B", "snowflake": "\U0001F9CA"}

ROLE_MEANING = {
    "fact": "events and measurements: what happened and how much",
    "dimension": "the context of an event: who, what, when, where",
    "bridge": "links two tables that relate many-to-many",
    "unknown": "the rules could not decide this one",
}
NOTE_MEANING = "a modelling problem found on the table it touches"

ROLE_PHRASE = {"fact": "a fact table", "dimension": "a dimension", "bridge": "a bridge",
               "unknown": "unknown"}

SUBTITLE = ("How to read: every box is a table; an arrow from A to B means A holds a key "
            "that points at B. Colour and icon show each table's role.")
SUBTITLE_NO_COLUMNS = " Add --columns to see which column joins each pair."
SUBTITLE_NOTES = " Yellow notes are modelling problems, joined by a dashed line to their table."
SUBTITLE_LINEAGE = " Dashed lines labelled ref: the model reads from the one they point to."

_ROLE_TERM = {
    "fact": ("Fact table", "records events and measurements: one row per thing that happened, "
                           "with the numbers worth adding up"),
    "dimension": ("Dimension", "describes the context of events (who, what, when, where); "
                               "fact tables point at it"),
    "bridge": ("Bridge table", "sits between two tables that relate many-to-many, holding "
                               "only their keys"),
    "unknown": ("Unknown", "the rules found too little evidence to call it a fact or a "
                           "dimension; a roles file can settle it"),
}
_RULE_TERM = {
    "grain": ("Grain", "what one row of a fact table stands for; every other choice follows "
                       "from it, so it must be clear"),
    "surrogate-key": ("Surrogate key", "an artificial key (a *_key column) that never changes, "
                                       "instead of an id borrowed from the source system"),
    "scd2": ("SCD type 2", "keeping every old version of a row, with valid_from and valid_to, "
                           "instead of overwriting it, so history is not lost"),
    "orphan-fk": ("Orphan key", "a foreign key that points at a table or column that does "
                                "not exist"),
    "snowflake": ("Snowflake", "a dimension split into sub-tables; usually simpler folded "
                               "back into one table"),
}


def role_key(role):
    """The legend text, which is also the colour alias, for a role: icon, name, meaning."""
    # implements: REQ-DATAMODEL-911
    return "%s %s — %s" % (ICON[role], role, ROLE_MEANING[role])


NOTE_KEY = "%s review note — %s" % (ICON["note"], NOTE_MEANING)


def note_text(rule, message):
    """The text of a review note: the rule's icon, its name, then the reason."""
    return "%s %s: %s" % (ICON[rule], rule, message)


def column_line(name, primary, foreign):
    """One column of a node: icons and PK / FK words ahead of a key column's name."""
    marks = []
    if primary:
        marks.append("%s PK" % ICON["pk"])
    if foreign:
        marks.append("%s FK" % ICON["fk"])
    return " ".join(marks + [name])


def glossary(tables, roles, issues, columns, lineage_drawn):
    """[[term, meaning]] for everything the diagram shows, then why each table has its role.

    `roles` is classify_tables()'s map; `issues` the review's findings. Plain words: no
    term is explained with another one that is not defined here."""
    # implements: REQ-DATAMODEL-911
    used = [r for r in ("fact", "dimension", "bridge", "unknown")
            if any(c.role == r for c in roles.values())]
    rows = [["Arrow", "an arrow from table A to table B means A holds a key that points at "
                      "a row of B"]]
    rows += [list(_ROLE_TERM[r]) for r in used]
    if columns:
        rows += [["PK (primary key)", "the column that identifies one row of its own table"],
                 ["FK (foreign key)", "a column holding another table's key: it is what the "
                                      "arrows follow"]]
    if any(c.role != "unknown" and not c.overridden for c in roles.values()):
        rows.append(["NN%", "how sure the role is: the lead over the next-best role, times how "
                            "much evidence there is"])
    if any(c.overridden for c in roles.values()):
        rows.append(["set by you", "the role came from your roles file, not from the rules"])
    seen = []
    for issue in issues:
        if issue.rule not in seen:
            seen.append(issue.rule)
    rows += [list(_RULE_TERM[r]) for r in seen]
    if lineage_drawn:
        rows.append(["ref", "a dbt model reads from the model the dashed line points to"])
    rows += [["Why %s is %s" % (t.name, ROLE_PHRASE[roles[t.name].role]), roles[t.name].reason]
             for t in tables]
    return rows
