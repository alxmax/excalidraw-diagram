"""SQL DDL -> tables: the first half of the data-model module.

Reads `CREATE TABLE` (columns, primary keys, foreign keys, inline or table-level) and
`ALTER TABLE ... ADD [CONSTRAINT n] PRIMARY|FOREIGN KEY` for PostgreSQL and generic
SQL, with the standard library only. Every other statement (indexes, inserts, comments,
schemas) is ignored; a `CREATE TABLE` this parser cannot read raises ValueError naming
the statement, because a table silently dropped would draw a confident, wrong diagram.

Names are folded the way SQL folds them: unquoted -> lower case, quoted kept as written,
and a schema prefix (`public.orders`) dropped, so two schemas holding a same-named
table would collide; that is rejected as a duplicate rather than merged.
"""

import re

_Q = r'(?:"[^"]+"|`[^`]+`|\[[^\]]+\]|[A-Za-z_][\w$]*)'
_QNAME = r"%s(?:\s*\.\s*%s)*" % (_Q, _Q)
_OPT = re.I | re.S

_CREATE = re.compile(
    r"^\s*CREATE\s+(?:OR\s+REPLACE\s+)?(?:(?:GLOBAL\s+|LOCAL\s+)?(?:TEMP|TEMPORARY)\s+"
    r"|UNLOGGED\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?P<name>%s)\s*(?=\()" % _QNAME, _OPT)
_ALTER = re.compile(
    r"^\s*ALTER\s+TABLE\s+(?:ONLY\s+)?(?:IF\s+EXISTS\s+)?(?P<name>%s)\s+ADD\s+(?P<item>.+)$"
    % _QNAME, _OPT)
_CONSTRAINT = r"(?:CONSTRAINT\s+%s\s+)?" % _Q
_PK = re.compile(r"^%sPRIMARY\s+KEY\s*\((?P<cols>[^)]*)\)" % _CONSTRAINT, _OPT)
_FK = re.compile(
    r"^%sFOREIGN\s+KEY\s*\((?P<cols>[^)]*)\)\s*REFERENCES\s+(?P<ref>%s)\s*(?:\((?P<rcols>[^)]*)\))?"
    % (_CONSTRAINT, _QNAME), _OPT)
# MySQL's `KEY idx (col)` is an index; `key varchar(20)` is a column, told apart by the
# identifier (not a number) that opens the parenthesis
_IGNORED_ITEM = re.compile(r"^(?:%s(?:UNIQUE|CHECK|EXCLUDE)\b|LIKE\b|(?:UNIQUE\s+)?(?:KEY|INDEX)"
                           r"\s*(?:%s\s*)?\(\s*[A-Za-z_`\"\[])" % (_CONSTRAINT, _Q), _OPT)
_COLUMN = re.compile(r"^(?P<name>%s)\s*(?P<rest>.*)$" % _Q, _OPT)
_TYPE_END = re.compile(r"\s+(?:NOT|NULL|DEFAULT|PRIMARY|REFERENCES|UNIQUE|CHECK|CONSTRAINT|"
                       r"GENERATED|COLLATE|AUTO_INCREMENT|IDENTITY)\b", _OPT)
_INLINE_REF = re.compile(r"\bREFERENCES\s+(?P<ref>%s)\s*(?:\((?P<rcols>[^)]*)\))?" % _QNAME, _OPT)


class Column(object):
    """One column: its name, declared type text, and whether NULL is allowed."""

    __slots__ = ("name", "type", "nullable")

    def __init__(self, name, type_, nullable=True):
        self.name, self.type, self.nullable = name, type_, nullable


class ForeignKey(object):
    """`columns` of the owning table reference `ref_columns` of `ref_table`.
    `ref_columns` is empty when the DDL left it implicit (REFERENCES t)."""

    __slots__ = ("columns", "ref_table", "ref_columns")

    def __init__(self, columns, ref_table, ref_columns=()):
        self.columns, self.ref_table = list(columns), ref_table
        self.ref_columns = list(ref_columns)


class Table(object):
    """A parsed table: ordered columns, the primary key's column names, its FKs."""

    __slots__ = ("name", "columns", "primary_key", "foreign_keys")

    def __init__(self, name):
        self.name, self.columns = name, []
        self.primary_key, self.foreign_keys = [], []

    def column(self, name):
        """The Column called `name`, or None."""
        return next((c for c in self.columns if c.name == name), None)


def _ident(text):
    """One identifier folded the SQL way; a dotted name keeps only its last part."""
    parts = re.findall(_Q, text)
    if not parts:
        raise ValueError("not an identifier: %r" % text)
    last = parts[-1]
    if last[0] in '"`[':
        return last[1:-1]
    return last.lower()


def _names(text):
    return [_ident(p) for p in _split(text, ",") if p.strip()]


def _clean(sql):
    """`sql` without -- and /* */ comments; quoted text is left alone."""
    out, i, n = [], 0, len(sql)
    while i < n:
        two, ch = sql[i:i + 2], sql[i]
        if two == "--":
            j = sql.find("\n", i)
            i = n if j < 0 else j
        elif two == "/*":
            j = sql.find("*/", i + 2)
            i = n if j < 0 else j + 2
            out.append(" ")
        elif ch in "'\"`":
            j = _skip_quote(sql, i)
            out.append(sql[i:j])
            i = j
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def _skip_quote(text, i):
    """Index just past the quoted run opening at `i`; '' inside '...' is an escape."""
    q, j = text[i], i + 1
    while j < len(text):
        if text[j] == q:
            if q == "'" and text[j + 1:j + 2] == "'":
                j += 2
                continue
            return j + 1
        j += 1
    return len(text)


def _split(text, sep):
    """`text` cut at every top-level `sep`: outside quotes and outside parentheses."""
    parts, depth, start, i = [], 0, 0, 0
    while i < len(text):
        ch = text[i]
        if ch in "'\"`":
            i = _skip_quote(text, i)
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == sep and depth == 0:
            parts.append(text[start:i])
            start = i + 1
        i += 1
    parts.append(text[start:])
    return parts


def _body(statement, start):
    """The text between the parenthesis opening at `start` and its match."""
    depth, i = 0, start
    while i < len(statement):
        ch = statement[i]
        if ch in "'\"`":
            i = _skip_quote(statement, i)
            continue
        depth += ch == "("
        depth -= ch == ")"
        if depth == 0:
            return statement[start + 1:i]
        i += 1
    raise ValueError("unbalanced parenthesis in: %s" % _head(statement))


def _head(statement):
    return " ".join(statement.split())[:70]


def _constraint(item, table):
    """Apply a table-level PRIMARY KEY / FOREIGN KEY `item` to `table`; True when it was
    one, False when it is anything else (the caller decides if that is a column)."""
    pk, fk = _PK.match(item), _FK.match(item)
    if pk:
        table.primary_key = _names(pk.group("cols"))
    elif fk:
        table.foreign_keys.append(ForeignKey(
            _names(fk.group("cols")), _ident(fk.group("ref")),
            _names(fk.group("rcols") or "")))
    return bool(pk or fk)


def _column(item, table):
    m = _COLUMN.match(item)
    if not m:
        raise ValueError("table %s: cannot read column definition %r" % (table.name, item.strip()))
    name, rest = _ident(m.group("name")), m.group("rest")
    end = _TYPE_END.search(" " + rest)
    type_ = " ".join((" " + rest)[:end.start()].split()) if end else " ".join(rest.split())
    table.columns.append(Column(name, type_, nullable=not re.search(r"\bNOT\s+NULL\b", rest, _OPT)))
    if re.search(r"\bPRIMARY\s+KEY\b", rest, _OPT):
        table.primary_key = [name]
        table.columns[-1].nullable = False
    ref = _INLINE_REF.search(rest)
    if ref:
        table.foreign_keys.append(ForeignKey(
            [name], _ident(ref.group("ref")), _names(ref.group("rcols") or "")))


def _create(statement, found):
    m = _CREATE.match(statement)
    if not m:
        raise ValueError("cannot read this CREATE TABLE (a column list is required): %s"
                         % _head(statement))
    table = Table(_ident(m.group("name")))
    if table.name in found:
        raise ValueError("table %s is defined twice" % table.name)
    for item in _split(_body(statement, m.end()), ","):
        item = item.strip()
        if not item or _IGNORED_ITEM.match(item) or _constraint(item, table):
            continue
        _column(item, table)
    if not table.columns:
        raise ValueError("table %s has no columns" % table.name)
    found[table.name] = table


def _alter(statement, found):
    m = _ALTER.match(statement)
    if not m:
        return
    name = _ident(m.group("name"))
    if name not in found:
        raise ValueError("ALTER TABLE names %s, which no CREATE TABLE defines: %s"
                         % (name, _head(statement)))
    _constraint(m.group("item").strip(), found[name])


def parse_ddl(sql):
    """The tables a DDL script defines, in order of appearance, as a list of Table.

    Raises ValueError when a CREATE TABLE cannot be read, a table is defined twice, an
    ALTER TABLE names an unknown table, or the script defines no table at all."""
    # implements: REQ-DATAMODEL-900
    found = {}
    for statement in _split(_clean(sql), ";"):
        head = statement.lstrip()[:12].upper()
        if head.startswith("CREATE"):
            if re.match(r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:(?:GLOBAL\s+|LOCAL\s+)?"
                        r"(?:TEMP|TEMPORARY)\s+|UNLOGGED\s+)?TABLE\b", statement.lstrip(), _OPT):
                _create(statement, found)
        elif head.startswith("ALTER"):
            _alter(statement, found)
    if not found:
        raise ValueError("no CREATE TABLE statement found")
    return list(found.values())
