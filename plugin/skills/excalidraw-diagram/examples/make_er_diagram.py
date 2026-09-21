#!/usr/bin/env python3
"""An entity-relationship diagram: the tables behind a small online shop.

The builder has no table shape and needs none: an entity is two stacked boxes, a
coloured header with its name and a white body listing its columns.
A relationship is a bound arrow with no heads, its cardinality written on it. The
gates judge the boxes and the lines like any other diagram; the script asserts
what they cannot: every foreign key names a table that exists, and every
relationship joins two tables through a column one of them actually has.

Regenerate from the repo root (the .excalidraw + .html land where you say):
    python -X utf8 plugin/skills/excalidraw-diagram/examples/make_er_diagram.py out/
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from excalidraw_builder import Font, Gates, Scene

W, HEAD_H, ROW_H = 230, 40, 21
COLUMNS = Font(13, "black")

s = Scene(seed=7, roles={"people": "violet", "sales": "blue", "catalogue": "green"})

# name -> (role, top-left, columns). "(PK)" is the key; "-> table" a foreign key.
TABLES = {
    "customer":   ("people", (40, 0), ["id (PK)", "email", "name", "created_at"]),
    "address":    ("people", (40, 330), ["id (PK)", "customer_id -> customer",
                                         "street", "city", "postcode"]),
    "order":      ("sales", (540, 0), ["id (PK)", "customer_id -> customer",
                                       "address_id -> address", "status", "placed_at"]),
    "order_line": ("sales", (540, 330), ["id (PK)", "order_id -> order",
                                         "product_id -> product", "quantity",
                                         "unit_price"]),
    "product":    ("catalogue", (1040, 330), ["id (PK)", "sku", "title", "price",
                                             "stock"]),
}
# (one side, many side, how the many side reads): the many side holds the key
RELATIONS = [
    ("customer", "order", "orders"),
    ("customer", "address", "addresses"),
    ("address", "order", "orders"),
    ("order", "order_line", "lines"),
    ("product", "order_line", "lines"),
]

# what no gate checks: a foreign key to a table that is not drawn, or a
# relationship with no column behind it
fks = {(t, c.split("-> ")[1]) for t, (_, _, cols) in TABLES.items()
       for c in cols if "->" in c}
assert all(ref in TABLES for _, ref in fks), "a foreign key names a missing table"
assert {(many, one) for one, many, _ in RELATIONS} == fks, \
    "relationships and foreign keys disagree"

s.title("The tables behind a small shop", (40, -110), font=30)
s.label("Each block is one table: its name on top, its columns below. A line joins two "
        "tables and says how many rows of each belong together.",
        (40, -68), font=Font(14, align="left"))

head, body = {}, {}
for name, (role, (x, y), cols) in TABLES.items():
    head[name] = s.box(name, (x, y, W, HEAD_H), paint=role, font=15)
    body[name] = s.box("\n".join(cols), (x, y + HEAD_H, W, ROW_H * len(cols) + 18),
                       paint="transparent", font=COLUMNS)

for one, many, rows in RELATIONS:
    # a line leaves and enters each table on the side facing the other one: a
    # table lower down is met at its header, a table higher up leaves from its
    # header — a line from a body upwards would cut that table's own header,
    # which the crossing gate refuses
    dy = TABLES[many][1][1] - TABLES[one][1][1]
    src = head[one] if dy < 0 else body[one]
    dst = head[many] if dy > 0 else body[many]
    s.arrow(src, dst, label="1 %s : N %s" % (one, rows), heads="none")

key_y = s.bounds()[3] + 70
s.legend([("who buys", "people"), ("what they buy", "sales"),
          ("what is for sale", "catalogue")], at=(40, key_y), title="What the colours mean")
s.glossary([("PK", "primary key: the column that names one row"),
            ("-> table", "foreign key: this column holds that table's id"),
            ("1 x : N y", "one row of x goes with any number of rows of y"),
            ("order_line", "one product in one order, with how many")],
           at=(420, key_y))

out_dir = sys.argv[1] if len(sys.argv) > 1 else "out"
s.save("er_diagram", out_dir=out_dir, gates=Gates.strict())
print("wrote er_diagram.excalidraw + .html")
