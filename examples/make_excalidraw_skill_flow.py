#!/usr/bin/env python3
"""Diagram: excalidraw-diagram skill — end-to-end workflow.

Shows the 8-step flow from a system description to finished files, with
detail panels for the two variable steps (Explore branching, save() gates).

Run from the repo root:
    python plugin/skills/excalidraw-diagram/examples/make_excalidraw_skill_flow.py
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from excalidraw_builder import Scene

ROLES = {
    "input":    "blue",      # user-provided system description
    "agent":    "violet",    # Claude / skill reasoning steps
    "engine":   "teal",      # excalidraw_builder.py
    "gate":     "orange",    # save() validation checks
    "output":   "indigo",    # produced files
    "parallel": "green",     # parallel Explore subagents (large repos)
}

s = Scene(seed=42, roles=ROLES)

# ── Title & subtitle ──────────────────────────────────────────────────────
s.title("excalidraw-diagram skill — end-to-end workflow", 40, -70, size=30)
s.label(
    "Top → bottom: from a system description to .excalidraw + .html.  "
    "Right panels detail the two variable steps (Explore branching, Validate).",
    40, -28, size=14, color="grey", align="left"
)

# ── Pipeline (centre column, x=300–700) ───────────────────────────────────
PX, PW, BH = 300, 400, 70

def Y(n):
    return 80 + n * 150      # 70px box + 80px vertical gap

inp   = s.box("System description",     PX, Y(0), PW, BH, fill="input",  font_size=14)
expl  = s.box("Explore the system",     PX, Y(1), PW, BH, fill="agent",  font_size=14)
plan  = s.box("Plan the layout",        PX, Y(2), PW, BH, fill="agent",  font_size=14)
code  = s.box("Write generator script", PX, Y(3), PW, BH, fill="agent",  font_size=14)
run   = s.box("python make_*.py",       PX, Y(4), PW, BH, fill="engine", font_size=14)
valid = s.box("save()  validates",      PX, Y(5), PW, BH, fill="gate",   font_size=14)
out   = s.box(".excalidraw  +  .html",  PX, Y(6), PW, BH, fill="output", font_size=14)
deliv = s.box("3-point delivery",       PX, Y(7), PW, BH, fill="agent",  font_size=14)

for a, b in zip(
    [inp, expl, plan, code, run, valid, out],
    [expl, plan, code, run, valid, out, deliv],
):
    s.arrow(a, b)

# Feedback: if save() fails → fix layout → back to PLAN (left-side bypass)
s.path(
    [(PX, Y(5) + BH // 2),
     (210, Y(5) + BH // 2),
     (210, Y(2) + BH // 2),
     (PX, Y(2) + BH // 2)],
    color="orange", dashed=True, end="arrow", label="fix → retry",
)

# Step annotations (text labels, below each box; exempt from overlap check)
s.label("reads README, counts source files, maps components + edges",
        PX, Y(1) + BH + 6, size=12, color="grey", align="left")
s.label("columns · ≥80px gaps · no arrow crosses an unrelated box",
        PX, Y(2) + BH + 6, size=12, color="grey", align="left")
s.label("imports excalidraw_builder.py; declares shapes + arrows; calls save()",
        PX, Y(3) + BH + 6, size=12, color="grey", align="left")
s.label("save() runs 3 gates; pass → both files written",
        PX, Y(5) + BH + 6, size=12, color="grey", align="left")
s.label("what it shows · how to read it · colour legend",
        PX, Y(7) + BH + 6, size=12, color="grey", align="left")

# ── Right panel A: Exploration alternatives (aligned with EXPLORE) ─────────
RX = PX + PW + 200   # = 900  (wide enough that the side-panel labels clear)

# Small repo: Claude reads directly — same y as EXPLORE
seq = s.box(
    "≤ 80 source files:\nClaude reads README + sources directly",
    RX, Y(1), 340, BH, fill="agent", font_size=12,
)
s.arrow(expl, seq, label="small repo", dashed=True)

# Large repo: 3 parallel subagents (50px below seq)
PAR_Y = Y(1) + BH + 50   # = 350
par_boxes = s.grid(
    [("structure +\nentry-points\n(haiku)", "parallel"),
     ("data-flow +\nintegration\n(sonnet)", "parallel"),
     ("distribution +\npackaging\n(haiku)", "parallel")],
    RX, PAR_Y, cols=3, w=140, h=84, gap_x=12, font_size=11,
)
par_frame = s.enclose(
    par_boxes, pad=14,
    label="> 80 source files: 3 parallel Explore subagents",
)
s.arrow(expl, par_frame, dashed=True)

# ── Right panel B: Builder API (aligned with CODE) ────────────────────────
api = s.box(
    "excalidraw_builder.py\n"
    "  box()  ellipse()  diamond()\n"
    "  arrow()  route_under()  frame()\n"
    "  row()  grid()  enclose()\n"
    "  legend()  glossary()  save()",
    RX, Y(3), 360, 130, fill="engine", font_size=11,
)
s.arrow(code, api, label="imports", dashed=True)

# ── Right panel C: Validation gates (aligned with VALIDATE) ───────────────
gate_boxes = s.row(
    [("Overlap check\n→ error if fails", "gate"),
     ("Crossing check\n→ warn / error",  "gate"),
     ("Legend coverage\n→ warn / error", "gate")],
    RX, Y(5), gap=12, w=150, h=BH, font_size=11,
)
gate_frame = s.enclose(gate_boxes, pad=12, label="save() checks")
s.arrow(valid, gate_frame, dashed=True)

# ── Colour legend ─────────────────────────────────────────────────────────
s.legend(
    [("User input",          "input"),
     ("Skill / Claude step", "agent"),
     ("Builder engine",      "engine"),
     ("Validation gate",     "gate"),
     ("Output file",         "output"),
     ("Parallel subagent",   "parallel")],
    1440, 300, title="What the colours mean",
)

# ── Save ──────────────────────────────────────────────────────────────────
out_dir = sys.argv[1] if len(sys.argv) > 1 else "docs"
pj, ph = s.save(
    "excalidraw_skill_flow", out_dir=out_dir,
    crossing_check="error", legend_check="error",
)
print("elements:", len(s.elements))
print("overlaps:", s.check_overlaps())
print("crossings:", s.check_arrow_crossings())
print("legend coverage gaps:", s.check_legend_coverage())
print("wrote:", pj, ph)
