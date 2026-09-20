#!/usr/bin/env python3
"""Debounce and ECU power states as timing diagrams, in README.md.

A button debounce, an AUTOSAR Dem counter-based debounce (the fault detection
counter drawn as a multi-level trace between its thresholds), and a simplified
EcuM-style ECU turn-on / turn-off. Same technique as make_timing_diagrams.py:
unbound path(heads="none") traces, box() state cells, no timing-specific builder
code, and asserts that check the logic the picture claims (the output follows
exactly t_deb after the last raw edge, testFailed flips only at +127 / -128,
reset is never released without supply).

Regenerate from the repo root (the .excalidraw + .html land where you say):
    python -X utf8 plugin/skills/excalidraw-diagram/examples/make_autosar_timing.py out/
Then open out/autosar_timing.html and use Excalidraw's menu > Export image to
refresh docs/autosar_timing.png.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from excalidraw_builder import Font, Gates, Paint, Scene

X0 = 240                   # where time starts
ROW_H, ROW_GAP = 36, 26    # a digital wire's band, gap between bands
GUIDE = Paint(stroke="grey", dashed=True)
NAME = Font(size=15, color="black", align="left")
NOTE = Font(size=14, align="left")
AXIS = Font(size=12, align="right")

s = Scene(seed=11, roles={"off": "grey", "transition": "yellow", "run": "blue",
                          "fail": "red", "pass": "green"})


def trace(values, top, step, h=ROW_H, vmin=0, vmax=1):
    """A stepped polyline, one value per `step`-wide slot, scaled into [top, top+h]."""
    y = lambda v: top + (vmax - v) / (vmax - vmin) * h
    pts = [(X0, y(values[0]))]
    for i in range(1, len(values)):
        if values[i] != values[i - 1]:
            x = X0 + i * step
            pts += [(x, y(values[i - 1])), (x, y(values[i]))]
    pts.append((X0 + len(values) * step, y(values[-1])))
    s.path(pts, heads="none")
    assert all(top <= py <= top + h for _, py in pts), "trace left its band"
    return pts


def edges(values):
    """Indices where the value changes."""
    return [i for i in range(1, len(values)) if values[i] != values[i - 1]]


def hline(y, x1, text):
    s.path([(X0, y), (x1, y)], paint=GUIDE, heads="none")
    s.label(text, (x1 + 16, y - 8), font=Font(size=12, align="left"))


def cells(spans, top, step):
    """Adjacent state cells: (text, role, slots) laid left to right from X0."""
    x = X0
    for text, role, n in spans:
        s.box(text, (x, top, n * step, ROW_H), paint=role, font=13)
        x += n * step


def rows(y, specs):
    """specs: (name, band height). Returns each band's top y."""
    tops, cur = [], y
    for name, h in specs:
        s.label(name, (40, cur + (h - 15) / 2), font=NAME)
        tops.append(cur)
        cur += h + ROW_GAP
    return tops


s.title("Debounce and ECU power states: three timing diagrams", (40, -60), font=30)
s.label("Time runs left to right. Each row is one signal; a taller row is a number "
        "that climbs and falls instead of a 0/1 wire.", (40, -18), font=NOTE)

# ---- 1. time-based debounce of a push button ---------------------------------
STEP, T = 16, 4            # one step = 5 ms, t_deb = 4 steps = 20 ms
y = s.section("1 · Button debounce: the output follows only an input that stayed still for t_deb")
s.label("A contact bounces for a few ms. Every raw edge restarts the timer; "
        "the output changes only when the timer reaches t_deb = 20 ms (1 step = 5 ms).",
        (40, y), font=NOTE)
t = rows(y + 40, [("raw input", ROW_H), ("stable timer", 64), ("debounced output", ROW_H)])
raw = [0] * 4 + [1, 0, 1, 1, 0] + [1] * 10 + [0, 1, 0, 1] + [0] * 9
timer, out = [], []
for i, v in enumerate(raw):
    timer.append(0 if i == 0 or v != raw[i - 1] else min(timer[-1] + 1, T))
    prev = out[-1] if out else raw[0]
    out.append(v if timer[-1] == T else prev)
trace(raw, t[0], STEP)
trace(timer, t[1], STEP, h=64, vmax=T)
trace(out, t[2], STEP)
raw_edges = edges(raw)
for e in edges(out):   # every output edge sits exactly t_deb after the last raw edge
    assert e - max(r for r in raw_edges if r < e) == T, (e, raw_edges)
end = X0 + len(raw) * STEP
hline(t[1], end, "t_deb reached: output may follow")
for e in edges(out):
    s.path([(X0 + e * STEP, t[0] - 8), (X0 + e * STEP, t[2] + ROW_H + 8)],
           paint=GUIDE, heads="none")

# ---- 2. AUTOSAR Dem counter-based debounce -----------------------------------
W2, INC, DEC = 56, 40, 40  # example config: increment / decrement step size
y = s.section("2 · AUTOSAR Dem counter-based debounce: reports move the fault detection counter")
s.label("Each monitor report nudges FDC by a configured step (here ±40). Reaching +127 "
        "sets testFailed; only reaching -128 clears it again.", (40, y), font=NOTE)
t = rows(y + 40, [("monitor report", ROW_H), ("FDC", 128), ("testFailed bit", ROW_H)])
reports = [None, "F", "F", "P", "F", "F", "F", "P", "P", "P", "P", "P", "P", "P"]
fdc, status = [0], [0]
for r in reports[1:]:
    v = min(fdc[-1] + INC, 127) if r == "F" else max(fdc[-1] - DEC, -128)
    fdc.append(v)
    status.append(1 if v == 127 else 0 if v == -128 else status[-1])
cells([("", "off", 1)] + [(r, "fail" if r == "F" else "pass", 1) for r in reports[1:]],
      t[0], W2)
trace(fdc, t[1], W2, h=128, vmin=-128, vmax=127)
trace(status, t[2], W2)
assert [fdc[i] for i in edges(status)] == [127, -128], "status flipped off-threshold"
end = X0 + len(reports) * W2
for v, text in [(127, "FAILED threshold (+127)"), (0, "0"), (-128, "PASSED threshold (-128)")]:
    yy = t[1] + (127 - v) / 255 * 128
    s.label(f"{v:+d}" if v else "0", (X0 - 10, yy - 7), font=AXIS)
    hline(yy, end, text)

# ---- 3. ECU power-up / shutdown (EcuM-style, simplified) ---------------------
W3, Q = 72, 18             # slot width, quarter-slot resolution for the wires
y = s.section("3 · ECU turn-on / turn-off: ignition, supply, reset, watchdog, EcuM state")
s.label("Ignition (KL15) on powers the ECU; reset is released once the supply is stable. "
        "After KL15 off the ECU keeps itself powered to save data, then lets go.",
        (40, y), font=NOTE)
t = rows(y + 70, [("KL15 (ignition)", ROW_H), ("VCC supply", ROW_H),
                  ("RESET (active low)", ROW_H), ("watchdog trigger", ROW_H),
                  ("EcuM state", ROW_H)])
N = 15 * 4                 # 15 slots in quarter steps
kl15 = [1 if 4 <= q < 38 else 0 for q in range(N)]
vcc = [1 if 5 <= q < 56 else 0 for q in range(N)]
rst = [1 if 8 <= q < 56 else 0 for q in range(N)]
wdg = [1 if 12 <= q < 52 and (q // 2) % 2 == 0 else 0 for q in range(N)]
for sig, top in zip([kl15, vcc, rst, wdg], t):
    trace(sig, top, Q)
assert all(v for r, v in zip(rst, vcc) if r), "reset released without supply"
assert not any(w and not r for w, r in zip(wdg, rst)), "watchdog triggered in reset"
for q, text in [(4, "KL15 on"), (38, "KL15 off")]:   # before the cells: they sit on top
    s.path([(X0 + q * Q, t[0] - 8), (X0 + q * Q, t[4] + ROW_H + 8)], paint=GUIDE,
           heads="none")
    s.label(text, (X0 + q * Q, t[0] - 26), font=12)
cells([("OFF", "off", 1), ("reset", "transition", 1), ("STARTUP", "transition", 3),
       ("RUN", "run", 5), ("POST RUN", "transition", 2), ("SHUTDOWN", "transition", 2),
       ("OFF", "off", 1)], t[4], W3)
below = t[4] + ROW_H + 14
for text, mid in [("init + self-check", 3.5), ("application runs", 7.5),
                  ("save NvM data", 11), ("release power latch", 13)]:
    s.label(text, (X0 + mid * W3, below), font=13)

# ---- key ----------------------------------------------------------------------
y = s.section("How to read the colours and terms")
s.legend([("ECU off / no report", "off"), ("starting up or shutting down", "transition"),
          ("ECU running normally", "run"), ("PREFAILED report (F)", "fail"),
          ("PREPASSED report (P)", "pass")], at=(40, y))
s.glossary([("debounce", "ignore short glitches; accept a change only once it is stable"),
            ("t_deb", "how long the input must stay unchanged"),
            ("Dem", "AUTOSAR Diagnostic Event Manager: stores faults (DTCs)"),
            ("FDC", "fault detection counter, -128 (passed) to +127 (failed)"),
            ("PREFAILED / PREPASSED", "a monitor's 'looks bad' / 'looks fine' report"),
            ("testFailed", "UDS status bit 0: the last test result was a failure"),
            ("KL15", "terminal 15: the ignition-switched supply line"),
            ("EcuM", "AUTOSAR ECU State Manager: drives startup and shutdown"),
            ("NvM", "non-volatile memory manager: saves data before power-off"),
            ("power latch", "the ECU holds its own supply on after KL15 off"),
            ("watchdog trigger", "periodic 'alive' pulse; if it stops, the ECU resets")],
           at=(400, y))

out_dir = sys.argv[1] if len(sys.argv) > 1 else "out"
s.save("autosar_timing", out_dir=out_dir, gates=Gates.strict())
print("wrote autosar_timing.excalidraw + .html")
