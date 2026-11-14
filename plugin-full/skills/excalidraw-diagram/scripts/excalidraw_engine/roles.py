"""roles.yml -> {table: role}: the override for a classification the user knows better.

The classifier is a heuristic and will be wrong on a real schema; this is how its answer
is corrected without touching the rules. The file is a deliberately small YAML subset, so
the standard library can read it: flat `table: role` lines, `#` comments, optional quotes.

    # roles.yml
    dim_product: dimension
    "stg_payments": fact        # really a fact, despite the prefix

Anything richer (nesting, lists, anchors) is an error naming the line, never a guess: a
config that is half understood changes a diagram without saying so.
"""

import re

ROLES = ("fact", "dimension", "bridge", "unknown")
_LINE = re.compile(r"""^\s*(?P<key>"[^"]+"|'[^']+'|[^\s:#\-"'][^:#]*?)\s*:\s*"""
                   r"""(?P<value>"[^"]*"|'[^']*'|[^\s#"']+)\s*(?:#.*)?$""")


def _unquote(text):
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    return text


def parse_roles(text):
    """{table name: role} from the text of a roles file.

    Raises ValueError, naming the line, for anything that is not a `table: role` line,
    a role other than fact, dimension, bridge or unknown, or a table listed twice."""
    # implements: REQ-DATAMODEL-906
    found = {}
    for number, raw in enumerate(text.splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        m = _LINE.match(raw)
        if not m:
            raise ValueError("roles line %d: expected `table: role`, got %r (only flat "
                             "`table: role` lines are supported)" % (number, raw.strip()))
        table, role = _unquote(m.group("key")), _unquote(m.group("value")).lower()
        if role not in ROLES:
            raise ValueError("roles line %d: %r is not a role (use %s)"
                             % (number, role, ", ".join(ROLES)))
        if table in found:
            raise ValueError("roles line %d: %s is listed twice" % (number, table))
        found[table] = role
    return found
