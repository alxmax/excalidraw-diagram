#!/usr/bin/env python3
"""What save() refuses, next to what it writes — the fail/pass picture in README.md.

Left: the same six boxes placed by eye. Two overlap, one arrow cuts through a box
it is not connected to, and a fill has no legend entry. Right: the same content
laid out with row()/column(), routed with route_under(), and decoded by a legend.

The left half only exists because this script opts out of the hard gates
(allow_overlap=True, crossing_check="warn"). A generator that does not opt out
never gets to write the left half: save() raises and names the offenders.

Regenerate from the repo root:
    python -X utf8 docs/make_gate_demo.py out/
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "plugin",
                                "skills", "excalidraw-diagram", "scripts"))
from excalidraw_builder import Scene

s = Scene(seed=3, roles={"step": "blue", "gate": "orange", "out": "green"})

s.title("save() refuses the left half. Only the right half ships.", 40, -80, size=28)
s.label("Same six boxes, same four arrows. Left: coordinates guessed by hand. "
        "Right: row() + route_under() + legend(), all gates on.",
        40, -40, size=14, align="left")

# ── left: what the gates catch ───────────────────────────────────────────
s.label("WHAT save() REFUSES", 60, 20, size=18, color="red", align="left")
a = s.box("ingest", 60, 70, fill="step")
b = s.box("parse", 190, 100, fill="step")            # overlaps `ingest`
c = s.box("validate", 60, 260, fill="gate")
d = s.box("store", 420, 260, fill="out")
e = s.box("report", 240, 420, fill="pink")           # a fill no legend explains
s.arrow(a, c)
s.arrow(c, d)                                        # passes under nothing - fine
s.arrow(a, d, dashed=True)                           # cuts through `parse`
s.arrow(d, e)
s.label("x  overlap: ingest / parse", 60, 540, size=13, color="red", align="left")
s.label("x  crossing: ingest -> store cuts through parse", 60, 562, size=13, color="red", align="left")
s.label("x  unlegended fill: pink on `report`", 60, 584, size=13, color="red", align="left")

# ── right: the same thing, laid out ──────────────────────────────────────
RX = 760
s.label("WHAT IT WRITES", RX, 20, size=18, color="green", align="left")
top = s.row([("ingest", "step"), ("parse", "step"), ("validate", "gate"), ("store", "out")],
            RX, 70, gap=90, connect=True)
rep = s.box("report", RX + 4 * 250, 70, fill="out")
s.arrow(top[3], rep, label="writes")
s.route_under(top[3], top[0], label="retry on failure", drop=70)
s.legend(x=RX, y=300, title="What the colours mean")
s.label("ok  zero overlaps, zero crossings, every colour in the key",
        RX, 540, size=13, color="green", align="left")

out_dir = sys.argv[1] if len(sys.argv) > 1 else "out"
# The opt-outs below are the point: they let the refused half be drawn at all.
s.save("gate_demo", out_dir=out_dir, allow_overlap=True,
       crossing_check="warn", legend_check="warn")
print("wrote gate_demo.excalidraw + .html")
