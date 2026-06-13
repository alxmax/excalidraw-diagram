#!/usr/bin/env python3
"""Build a clear, plain-language Consilium architecture + modes diagram.

Design choices for readability:
  - normal font, clean (non-sketchy) outlines
  - no abbreviations anywhere; full words in every box
  - a legend explains the three voices and the colour code
  - every stage carries a short plain-language caption
  - arrows start/end outside the boxes (handled by the builder)
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from excalidraw_builder import Scene

s = Scene(font="normal", sketch=False)

# Colour convention, used everywhere and explained in the legend
GEN = "violet"   # Generator   — creative
CON = "blue"     # Control     — analytical
CNS = "green"    # Conservator — prudent / risk

VOICES = [("Generator", GEN), ("Control", CON), ("Conservator", CNS)]


def agent(scene, x, y, w, h, voices, *, caption=None, vw=150, vh=56,
          gap=16, arrows=False, fontv=14):
    """An 'agent' ellipse with full-name voice boxes in a row.
    Returns (ellipse_id, [voice_ids])."""
    if caption:
        scene.label(caption, x + w / 2, y - 28, size=13, color="grey",
                    align="center")
    eid = scene.ellipse("", x, y, w, h)
    n = len(voices)
    total = n * vw + (n - 1) * gap
    sx = x + (w - total) / 2
    cy = y + (h - vh) / 2
    ids = []
    for i, (lbl, col) in enumerate(voices):
        bx = sx + i * (vw + gap)
        ids.append(scene.box(lbl, bx, cy, vw, vh, fill=col, font_size=fontv))
    if arrows:
        for a, b in zip(ids, ids[1:]):
            scene.arrow(a, b)
    return eid, ids


# ===========================================================================
# TITLE + LEGEND
# ===========================================================================
s.title("Consilium", 40, -170, size=46, color="black")
s.title("A panel of three AI reviewers that debate a code change, "
        "then vote on the safest good option.", 46, -110, size=18,
        color="grey")

s.label("The three voices on the panel", 40, -56, size=14, color="grey",
        align="left")
s.box("Generator\nproposes new ideas and alternatives",
      40, -28, 340, 60, fill=GEN, font_size=13)
s.box("Control\nchecks that the solution is correct",
      410, -28, 340, 60, fill=CON, font_size=13)
s.box("Conservator\nweighs the risk and how reversible it is",
      780, -28, 360, 60, fill=CNS, font_size=13)

# ===========================================================================
# REGION A — HOW A REVIEW FLOWS
# ===========================================================================
s.title("How a review flows", 40, 110, size=26, color="black")

prompt = s.box("A request comes in\n(review a pull request,\n"
               "plan a refactor, or\nassess a risky change)",
               40, 210, 250, 110, fill="grey", font_size=13)
skill = s.box("The Consilium skill\nopens the panel",
              340, 225, 200, 80, fill="yellow", font_size=14)
gate = s.diamond("Is the change\nbig enough\nto review?",
                 600, 205, 200, 120, fill="orange", font_size=13)
s.label("Small, trivial changes are skipped automatically.",
        700, 335, size=12, color="grey", align="center")

# the three voices, in parallel, inside a frame
vfx, vfy, vfw, vfh = 880, 120, 350, 300
vframe = s.frame(vfx, vfy, vfw, vfh, dashed=True)
s.label("The three voices review in parallel", vfx + vfw / 2, vfy - 24,
        size=13, color="grey", align="center")
gv = s.box("Generator\nproposes ideas", vfx + 30, vfy + 30, 290, 66,
           fill=GEN, font_size=14)
cv = s.box("Control\nchecks correctness", vfx + 30, vfy + 116, 290, 66,
           fill=CON, font_size=14)
kv = s.box("Conservator\nweighs the risk", vfx + 30, vfy + 202, 290, 66,
           fill=CNS, font_size=14)

aggreg = s.box("The votes are combined\n(the Conservator voice\n"
               "can veto the others)",
               1320, 200, 230, 110, fill="teal", font_size=13)
conf = s.box("A confidence score is set\nfrom how much the\nvoices agreed",
             1620, 208, 220, 94, fill="pink", font_size=13)
out = s.box("Final decision, saved as a report\n"
            "the chosen approach\nthe alternatives considered\n"
            "each voice's score and the confidence\n"
            "the full record of the discussion",
            1920, 185, 330, 140, fill="indigo", font_size=13)

# one clean arrow into the group, one out of it (no crossing fan of arrows)
s.arrow(prompt, skill)
s.arrow(skill, gate)
s.arrow(gate, vframe)
s.arrow(vframe, aggreg)
s.arrow(aggreg, conf)
s.arrow(conf, out)

# feedback loop — a real routed connector from the report back to the
# aggregator, so it visibly connects the two boxes
s.route_under(out, aggreg, drop=70,
              label="Feedback loop: past decisions and their real outcomes "
                    "adjust the weighting next time")

# ===========================================================================
# REGION B — FOUR WAYS TO RUN THE PANEL
# ===========================================================================
s.title("Four ways to run the panel", 40, 600, size=26, color="black")
s.title("The same three voices, arranged differently depending on the stakes.",
        46, 640, size=16, color="grey")

# --- top row: three simpler modes ---
ty = 740
fh = 320

# Parallel
s.title("Parallel  —  the default", 80, ty - 36, size=20, color="black")
s.frame(40, ty, 620, fh)
agent(s, 130, ty + 70, 440, 150, VOICES)
s.label("All three voices review at the same time, independently.",
        350, ty + 250, size=13, color="grey", align="center")
s.label("Used for most pull-request reviews.",
        350, ty + 274, size=13, color="grey", align="center")

# Dialectic
s.title("Dialectic", 740, ty - 36, size=20, color="black")
s.frame(700, ty, 620, fh)
_, did = agent(s, 790, ty + 70, 440, 150, VOICES, arrows=True)
s.label("Two rounds. In the second round, each voice can",
        1010, ty + 250, size=13, color="grey", align="center")
s.label("see what the others said. Used for multi-file refactors.",
        1010, ty + 274, size=13, color="grey", align="center")

# Sequential — blind
s.title("Sequential  —  blind", 1400, ty - 36, size=20, color="black")
s.frame(1360, ty, 620, fh)
agent(s, 1450, ty + 70, 440, 150, VOICES, arrows=True)
s.label("The voices run one after another, but each starts fresh",
        1670, ty + 250, size=13, color="grey", align="center")
s.label("so it is not swayed by the previous one. For high-risk calls.",
        1670, ty + 274, size=13, color="grey", align="center")

# --- bottom: Trias, full width and expanded ---
tby = 1130
s.title("Trias  —  for the highest-stakes changes", 40, tby - 40, size=22,
        color="black")
s.frame(40, tby, 2210, 600)
s.label("Nine reviewers in total: three different personalities, each "
        "running all three voices. They take a majority vote.",
        1145, tby + 30, size=14, color="grey", align="center")

personalities = [("Personality: Pioneer", 120),
                 ("Personality: Architect", 770),
                 ("Personality: Skeptic", 1420)]
ellipses = []
for caption, px in personalities:
    eid, _ = agent(s, px, tby + 180, 560, 160, VOICES,
                   caption=caption, vw=160, vh=56, gap=14, fontv=14)
    ellipses.append(eid)

# majority vote, centred below the three personalities -> short, clean arrows
vote = s.box("Majority\nvote", 1065, tby + 430, 160, 120, fill="teal",
             shape="ellipse", font_size=16)
for eid in ellipses:
    s.arrow(eid, vote, color="grey")

s.label("Used for migrations, security-sensitive work, and large refactors.",
        1145, tby + 565, size=13, color="grey", align="center")

# ===========================================================================
out_dir = sys.argv[1] if len(sys.argv) > 1 else "docs"
pj, ph = s.save("consilium_architecture", out_dir=out_dir)
print("elements:", len(s.elements))
print("wrote:", pj)
print("wrote:", ph)
