#!/usr/bin/env python3
"""A state machine: the life of an online order, from checkout to refund.

A state diagram is a graph whose nodes are states and whose edges are the events
that move between them, so pack() lays it out with no coordinates: it layers the
states by how far they sit from the start, routes the transitions that go back
(a parcel returned to the warehouse) around the diagram, and frames the states a
group names. Start and end states are ellipses, as in UML; everything else is a
rounded box. The script asserts what no gate can: every state is reachable from
the start, and every non-final state has a way out.

Regenerate from the repo root (the .excalidraw + .html land where you say):
    python -X utf8 plugin/skills/excalidraw-diagram/examples/make_state_machine.py out/
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from excalidraw_builder import Font, Gates, PackOptions, Scene

s = Scene(seed=7, roles={"endpoint": "grey", "normal": "blue", "money": "green",
                         "failure": "red"})

STATES = [
    ("new", "order placed", "endpoint", "ellipse"),
    ("pending", "awaiting payment", "normal", "rectangle"),
    ("paid", "paid", "money", "rectangle"),
    ("packed", "packed", "normal", "rectangle"),
    ("shipped", "shipped", "normal", "rectangle"),
    ("delivered", "delivered", "endpoint", "ellipse"),
    ("cancelled", "cancelled", "failure", "ellipse"),
    ("refunded", "refunded", "money", "ellipse"),
]
FINAL = {"delivered", "cancelled", "refunded"}
EVENTS = [
    ("new", "pending", "checkout"),
    ("pending", "paid", "payment ok"),
    ("pending", "cancelled", "payment fails"),
    ("paid", "packed", "pick and pack"),
    ("paid", "refunded", "customer cancels"),
    ("packed", "shipped", "courier collects"),
    ("shipped", "packed", "bad address"),
    ("shipped", "delivered", "signed for"),
]

nodes = [{"id": i, "label": lab, "fill": role, "kind": kind}
         for i, lab, role, kind in STATES]
edges = [{"src": a, "dst": b, "label": ev} for a, b, ev in EVENTS]

# what no gate checks: a state nobody can reach, or a dead end that is not final
succ = {i: [b for a, b, _ in EVENTS if a == i] for i, *_ in STATES}
seen, todo = set(), ["new"]
while todo:
    cur = todo.pop()
    if cur not in seen:
        seen.add(cur)
        todo += succ[cur]
assert seen == set(succ), "unreachable state(s): %s" % sorted(set(succ) - seen)
assert all(succ[i] for i in succ if i not in FINAL), "a non-final state has no way out"

s.title("The life of an order", (40, -150), font=30)
s.label("Left to right. Each box is a state the order can be in; each arrow is the event "
        "that moves it on. Ellipses are where it starts and where it can end.",
        (40, -108), font=Font(14, align="left"))
s.pack(nodes, edges,
       groups=[{"label": "in the warehouse's hands", "members": ["packed", "shipped"]}],
       at=(40, 0), options=PackOptions(direction="LR"))

key_y = s.bounds()[3] + 70
s.legend([("start or end state", "endpoint"), ("a normal state", "normal"),
          ("money has moved", "money"), ("the order failed", "failure")],
         at=(40, key_y), title="What the colours mean")
s.glossary([("state", "where the order is right now; exactly one at a time"),
            ("event", "what happened to move it on, written on the arrow"),
            ("dashed arrow", "an event that sends it back to an earlier state"),
            ("final state", "no arrow leaves it: the story of this order is over")],
           at=(420, key_y))

out_dir = sys.argv[1] if len(sys.argv) > 1 else "out"
s.save("state_machine", out_dir=out_dir, gates=Gates.strict())
print("wrote state_machine.excalidraw + .html")
