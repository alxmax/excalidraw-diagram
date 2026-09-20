#!/usr/bin/env python3
"""How a byte travels on a wire: SPI, I2C and UART timing diagrams, in README.md.

Nothing timing-specific exists in the builder: each trace is an unbound
path(heads="none") polyline, each bus value an adjacent box(), and the diagram
keeps the explainer shape (title, reading direction, legend, glossary). The gates
never inspect an unbound trace, so the script asserts its own geometry: clock
edges land on the bit grid and every trace stays inside its row.

Regenerate from the repo root (the .excalidraw + .html land where you say):
    python -X utf8 plugin/skills/excalidraw-diagram/examples/make_timing_diagrams.py out/
Then open out/timing_diagrams.html and use Excalidraw's menu > Export image to
refresh docs/timing_diagrams.png.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from excalidraw_builder import Font, Gates, Paint, Scene

X0, W = 220, 64            # where time starts, width of one bit slot
ROW_H, ROW_GAP = 36, 26    # height of one wire's band, gap between bands
GUIDE = Paint(stroke="grey", dashed=True)
NAME = Font(size=15, color="black", align="left")
NOTE = Font(size=14, align="left")

s = Scene(seed=7, roles={"controller": "blue", "target": "green",
                         "framing": "yellow", "idle": "grey"})


def trace(levels, top, step=W):
    """A stepped polyline: one 0/1 level per `step`-wide slot. Returns its points."""
    y = lambda v: top if v else top + ROW_H
    pts = [(X0, y(levels[0]))]
    for i in range(1, len(levels)):
        if levels[i] != levels[i - 1]:
            x = X0 + i * step
            pts += [(x, y(levels[i - 1])), (x, y(levels[i]))]
    pts.append((X0 + len(levels) * step, y(levels[-1])))
    s.path(pts, heads="none")
    # every point stays inside this wire's band
    assert all(top <= py <= top + ROW_H for _, py in pts), "trace left its band"
    return pts


def rising_edges(pts):
    return [x1 for (x1, y1), (x2, y2) in zip(pts, pts[1:]) if x1 == x2 and y2 < y1]


def bus(cells, top):
    """Adjacent value cells: (text, role) per slot; role None leaves the slot empty."""
    for i, (text, role) in enumerate(cells):
        if role:
            s.box(text, (X0 + i * W, top, W, ROW_H), paint=role, font=13)


def rows(y, names):
    """Signal-name column; returns the top y of each row."""
    tops = [y + i * (ROW_H + ROW_GAP) for i in range(len(names))]
    for name, top in zip(names, tops):
        s.label(name, (40, top + (ROW_H - 15) / 2), font=NAME)
    return tops


def guides(xs, tops):
    for x in xs:
        s.path([(x, tops[0] - 10), (x, tops[-1] + ROW_H + 10)], paint=GUIDE, heads="none")


def halves(slot_levels):
    return [v for pair in slot_levels for v in pair]


def quarters(slot_levels):
    return [v for quad in slot_levels for v in quad]


s.title("How a byte travels on a wire: SPI, I2C, UART", (40, -60), font=30)
s.label("Time runs left to right. Each row is one wire: high = 1, low = 0. "
        "Coloured cells show who drives the wire and what the bit means.",
        (40, -18), font=NOTE)

# ---- 1. SPI: controller sends 0xA5 while the target answers 0x3C -------------
y = s.section("1 · SPI (mode 0): four wires, one bit per clock tick")
s.label("Dashed lines = the moment both sides read a bit (rising SCLK edge). "
        "Data may only change while SCLK is low.", (40, y), font=NOTE)
t = rows(y + 40, ["SCLK", "CS (active low)", "MOSI", "MISO"])
tx, rx = [1, 0, 1, 0, 0, 1, 0, 1], [0, 0, 1, 1, 1, 1, 0, 0]
clk = trace(halves([(0, 0)] + [(0, 1)] * 8 + [(0, 0)]), t[0], step=W / 2)
trace(halves([(1, 1)] + [(0, 0)] * 8 + [(1, 1)]), t[1], step=W / 2)
edges = rising_edges(clk)
assert edges == [X0 + (k + 1.5) * W for k in range(8)], edges
guides(edges, t)
bus([("", None)] + [(str(b), "controller") for b in tx] + [("", None)], t[2])
bus([("Z", "idle")] + [(str(b), "target") for b in rx] + [("Z", "idle")], t[3])
s.label("= 0xA5, command (bit 7 first)", (X0 + 10 * W + 24, t[2] + 10), font=NOTE)
s.label("= 0x3C, reply at the same time", (X0 + 10 * W + 24, t[3] + 10), font=NOTE)

# ---- 2. I2C: controller addresses target 0x50 for a write, target ACKs -------
y = s.section("2 · I2C: two shared wires, a frame fenced by START and STOP")
s.label("SDA may only change while SCL is low; a change while SCL is high "
        "is START (falls) or STOP (rises).", (40, y), font=NOTE)
t = rows(y + 40, ["SCL", "SDA", "meaning"])
addr = [1, 0, 1, 0, 0, 0, 0]
bits = addr + [0, 0]                        # + write bit + ACK from the target
scl = [(1, 1, 1, 1), (1, 1, 1, 1)] + [(0, 0, 1, 1)] * 9 + [(0, 1, 1, 1)]
sda, prev = [(1, 1, 1, 1), (1, 1, 0, 0)], 0
for b in bits:
    sda.append((prev, b, b, b))
    prev = b
sda.append((prev, 0, 1, 1))
scl_pts = trace(quarters(scl), t[0], step=W / 4)
trace(quarters(sda), t[1], step=W / 4)
edges = rising_edges(scl_pts)
assert edges == [X0 + (k + 2.5) * W for k in range(9)] + [X0 + 11.25 * W], edges
guides(edges[:9], t[:2])
bus([("", None), ("START", "framing")]
    + [(f"A{6 - i}={b}", "controller") for i, b in enumerate(addr)]
    + [("W=0", "controller"), ("ACK", "target"), ("STOP", "framing")], t[2])
s.label("address 0x50, write", (X0 + 12 * W + 24, t[2] + 10), font=NOTE)

# ---- 3. UART: 8N1 frame carrying 'A' (0x41), no clock wire -------------------
y = s.section("3 · UART (8N1): one wire, no clock, both sides agree on the speed")
s.label("The receiver waits for the falling start bit, then reads the middle of "
        "each bit slot (dashed lines).", (40, y), font=NOTE)
t = rows(y + 40, ["TX", "meaning"])
data = [(0x41 >> i) & 1 for i in range(8)]  # LSB first
tx_pts = trace([1, 0] + data + [1, 1], t[0])
assert all((x - X0) % W == 0 for x, _ in tx_pts), "a UART edge fell off the bit grid"
guides([X0 + (k + 1.5) * W for k in range(10)], t)
bus([("", None), ("start", "framing")]
    + [(f"D{i}={b}", "controller") for i, b in enumerate(data)]
    + [("stop", "framing"), ("", None)], t[1])
s.label("= 0x41 = 'A', lowest bit first", (X0 + 12 * W + 24, t[1] + 10), font=NOTE)

# ---- key ----------------------------------------------------------------------
y = s.section("How to read the colours and terms")
s.legend([("controller drives the wire", "controller"),
          ("target (peripheral) drives it", "target"),
          ("frame marker: start / stop", "framing"),
          ("nobody drives it (Z)", "idle")], at=(40, y))
s.glossary([("active low", "the signal means 'on' when it is at 0"),
            ("SCLK / SCL", "the clock: one tick moves one bit"),
            ("MOSI / MISO", "SPI data: controller out / controller in"),
            ("SDA", "I2C's single shared data wire"),
            ("START / STOP", "SDA changing while SCL is high marks a frame edge"),
            ("ACK", "the target pulls SDA low to say 'received'"),
            ("Z", "high impedance: the wire floats, nobody drives it"),
            ("8N1", "8 data bits, no parity bit, 1 stop bit"),
            ("baud", "bits per second, agreed by both sides in advance")],
           at=(420, y))

out_dir = sys.argv[1] if len(sys.argv) > 1 else "out"
s.save("timing_diagrams", out_dir=out_dir, gates=Gates.strict())
print("wrote timing_diagrams.excalidraw + .html")
