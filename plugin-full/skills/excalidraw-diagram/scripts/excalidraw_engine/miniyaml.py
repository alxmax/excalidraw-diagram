"""A YAML subset reader, enough for a dbt schema.yml, with the standard library alone.

The plugin installs nothing from PyPI, so there is no YAML library to lean on. This reads
what a dbt project actually writes and refuses the rest, naming the line:

    block maps and block lists, nested by indentation; a list item that opens a map
    (`- name: x` followed by more keys); scalars (quoted or plain, int, float, bool,
    null); flow lists `[a, b]` and flow maps `{a: b}`; `|` and `>` block scalars;
    `#` comments; a leading `---`.

Not supported, and an error rather than a guess: anchors and aliases (`&a`, `*a`), tags
(`!!str`), tab indentation, several documents in one file, and a plain scalar that runs
over more than one line. A ` #` inside a block scalar is read as a comment.
"""

import re

_NUMBER = re.compile(r"^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$")
_BLOCK = re.compile(r"^[|>][-+]?$")
_KEY = re.compile(r"""^("(?:[^"\\]|\\.)*"|'[^']*'|[^\s'"\[\]{},&*!|>#-][^:]*?|-[^\s:][^:]*?)\s*:(?:\s+(.*))?$""")


def _strip_comment(text):
    """`text` without a trailing ` # comment`; quoted text is left alone."""
    quote = None
    for i, ch in enumerate(text):
        if quote:
            quote = None if ch == quote else quote
        elif ch in "\"'":
            quote = ch
        elif ch == "#" and (i == 0 or text[i - 1] in " \t"):
            return text[:i].rstrip()
    return text.rstrip()


def _lines(text):
    """[(indent, content, line number)] for every line that holds something."""
    out = []
    for number, raw in enumerate(text.splitlines(), 1):
        body = _strip_comment(raw)
        if not body.strip():
            continue
        lead = body[:len(body) - len(body.lstrip())]
        if "\t" in lead:
            raise ValueError("yaml line %d: tab indentation is not supported" % number)
        if not out and body.strip() == "---":
            continue
        if body.strip() in ("---", "..."):
            raise ValueError("yaml line %d: several documents in one file are not supported"
                             % number)
        out.append((len(lead), body.strip(), number))
    return out


_BRACKET = {"[": 1, "{": 1, "]": -1, "}": -1}


def _top_level_commas(text):
    """The index of every comma in `text` that sits outside quotes and brackets."""
    depth, quote = 0, None
    for i, ch in enumerate(text):
        if quote:
            quote = None if ch == quote else quote
            continue
        if ch in "\"'":
            quote = ch
            continue
        depth += _BRACKET.get(ch, 0)
        if ch == "," and depth == 0:
            yield i


def _split_flow(text):
    """`text` cut at top-level commas, outside quotes and brackets."""
    cuts = [-1] + list(_top_level_commas(text)) + [len(text)]
    parts = [text[a + 1:b] for a, b in zip(cuts, cuts[1:])]
    return [p.strip() for p in parts if p.strip()]


def _scalar(text, number):
    """One scalar or flow collection, from its source text."""
    if text[:1] in "&*!" and text[:2] != "{{":
        raise ValueError("yaml line %d: anchors, aliases and tags are not supported: %s"
                         % (number, text))
    if text[0] in "\"'":
        if len(text) < 2 or text[-1] != text[0]:
            raise ValueError("yaml line %d: unterminated quoted string: %s" % (number, text))
        body = text[1:-1]
        if text[0] == "'":
            return body.replace("''", "'")
        return re.sub(r"\\(.)", lambda m: {"n": "\n", "t": "\t"}.get(m.group(1), m.group(1)), body)
    if text.startswith("[") and text.endswith("]"):
        return [_scalar(p, number) for p in _split_flow(text[1:-1])]
    if text.startswith("{") and text.endswith("}") and not text.startswith("{{"):
        out = {}
        for part in _split_flow(text[1:-1]):
            m = _KEY.match(part)
            if not m:
                raise ValueError("yaml line %d: cannot read the flow map entry %r" % (number, part))
            out[_unquote(m.group(1), number)] = _scalar(m.group(2), number) if m.group(2) else None
        return out
    low = text.lower()
    if low in ("~", "null"):
        return None
    if low in ("true", "false"):
        return low == "true"
    if _NUMBER.match(text):
        return float(text) if re.search(r"[.eE]", text) else int(text)
    return text


def _unquote(key, number):
    return _scalar(key, number) if key[0] in "\"'" else key


class _Reader(object):
    def __init__(self, lines):
        self.lines, self.i = lines, 0

    def peek(self):
        return self.lines[self.i] if self.i < len(self.lines) else None

    def block(self, indent):
        indent_, content, number = self.peek()
        if content == "-" or content.startswith("- "):
            return self.list(indent)
        if _KEY.match(content):
            return self.map(indent)
        self.i += 1
        return _scalar(content, number)

    def list(self, indent):
        out = []
        while self.peek() and self.peek()[0] == indent and (
                self.peek()[1] == "-" or self.peek()[1].startswith("- ")):
            _, content, number = self.peek()
            item = content[1:].strip()
            if not item:
                self.i += 1
                nxt = self.peek()
                out.append(self.block(nxt[0]) if nxt and nxt[0] > indent else None)
            elif _KEY.match(item):
                # `- key: value` opens a map whose later keys sit under `key`
                self.lines[self.i] = (indent + len(content) - len(item), item, number)
                out.append(self.map(self.lines[self.i][0]))
            else:
                self.i += 1
                out.append(_scalar(item, number))
        return out

    def map(self, indent):
        out = {}
        while self.peek() and self.peek()[0] == indent:
            _, content, number = self.peek()
            m = _KEY.match(content)
            if not m:
                raise ValueError("yaml line %d: expected `key: value`, got %r" % (number, content))
            key, rest = _unquote(m.group(1), number), m.group(2)
            if key in out:
                raise ValueError("yaml line %d: key %r appears twice" % (number, key))
            self.i += 1
            out[key] = self._map_value(indent, rest, number)
        nxt = self.peek()
        if nxt and nxt[0] > indent:
            raise ValueError("yaml line %d: unexpected indentation" % nxt[2])
        return out

    def _map_value(self, indent, rest, number):
        """The value of a map key whose line held `rest` after the colon, the line itself
        already consumed: a block scalar, a scalar, a nested block, a list at the key's own
        indent, or nothing."""
        nxt = self.peek()
        if rest and _BLOCK.match(rest):
            return self.block_scalar(indent, rest)
        if rest:
            return _scalar(rest, number)
        if nxt and nxt[0] > indent:
            return self.block(nxt[0])
        if nxt and nxt[0] == indent and (nxt[1] == "-" or nxt[1].startswith("- ")):
            return self.list(indent)
        return None

    def block_scalar(self, indent, style):
        rows = []
        while self.peek() and self.peek()[0] > indent:
            rows.append(self.peek()[1])
            self.i += 1
        return ("\n" if style[0] == "|" else " ").join(rows)


def parse_yaml(text):
    """The Python value (dict, list, scalar or None) a YAML document holds.

    Raises ValueError, naming the line, for anything outside the subset in the module
    docstring."""
    # implements: REQ-DATAMODEL-908
    lines = _lines(text)
    if not lines:
        return None
    reader = _Reader(lines)
    value = reader.block(lines[0][0])
    if reader.peek():
        raise ValueError("yaml line %d: unexpected content: %r"
                         % (reader.peek()[2], reader.peek()[1]))
    return value
