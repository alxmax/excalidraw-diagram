#!/usr/bin/env python3
"""A sequence diagram: what happens between clicking "Sign in" and seeing a page.

The builder has no sequence primitive and needs none: a participant is a box(), a
lifeline an unbound path(heads="none"), a message a horizontal path() between two
lifelines, a reply the same path dashed, and an alt fragment a frame() with its
guard labels. The gates never inspect an unbound path, so the script asserts its
own geometry: every message starts and ends on a lifeline, messages run strictly
downwards (time order), and every message label fits between two lifelines.

Regenerate from the repo root (the .excalidraw + .html land where you say):
    python -X utf8 plugin/skills/excalidraw-diagram/examples/make_sequence_diagram.py out/
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from excalidraw_builder import Font, Gates, Paint, Scene
from excalidraw_engine.geometry import text_extent

X0, SPACING = 60, 250          # left edge of the first participant, lifeline spacing
BOX_W, BOX_H = 170, 54         # a participant's header box
STEP = 58                      # vertical distance between two messages
MSG_FONT = 13
LIFELINE = Paint(stroke="grey", dashed=True)
REPLY = Paint(dashed=True)
NOTE = Font(size=14, align="left")
GUARD = Font(size=13, color="black", align="left")

s = Scene(seed=7, roles={"client": "grey", "service": "blue", "data": "green",
                         "fragment": "yellow"})

s.title("Signing in: who talks to whom, in what order", (40, -80), font=30)
s.label("Time runs top to bottom. Each column is one participant; each arrow is one "
        "message. Solid = a request, dashed = the reply to it.", (40, -36), font=NOTE)

# ---- participants and their lifelines -----------------------------------------
PARTS = [("browser", "Browser", "client"), ("api", "API gateway", "service"),
         ("auth", "Auth service", "service"), ("db", "User database", "data")]
x_of = {}
for i, (key, name, role) in enumerate(PARTS):
    left = X0 + i * SPACING
    s.box(name, (left, 0, BOX_W, BOX_H), paint=role, font=15)
    x_of[key] = left + BOX_W / 2

y = BOX_H + 40                 # the first message's height
msgs = []                      # (y, x_from, x_to) — checked at the end


def message(src, dst, text, reply=False):
    """One horizontal message at the next time step, its label above the line,
    centred between the source lifeline and its neighbour towards the target."""
    global y
    a, b = x_of[src], x_of[dst]
    s.path([(a, y), (b, y)], paint=REPLY if reply else None)
    step = SPACING if b > a else -SPACING
    tw, _ = text_extent(text, MSG_FONT)
    assert tw < SPACING - 24, "message label wider than a lifeline gap: %r" % text
    s.label(text, (a + step / 2, y - 20), font=Font(MSG_FONT, "black", "center"))
    msgs.append((y, a, b))
    y += STEP


def self_call(who, text):
    """A message a participant sends itself: a small loop right of its lifeline."""
    global y
    x = x_of[who]
    s.path([(x, y), (x + 44, y), (x + 44, y + 26), (x, y + 26)])
    s.label(text, (x + 54, y + 4), font=Font(MSG_FONT, "black", "left"))
    msgs.append((y, x, x))
    y += STEP + 16


message("browser", "api", "POST /login")
message("api", "auth", "verify(email, pw)")
message("auth", "db", "find user by email")
message("db", "auth", "user row + pw hash", reply=True)
self_call("auth", "hash pw, compare")

# ---- the alt fragment: two outcomes, one of which happens ------------------------
top = y - 30
# guards sit right of the first lifeline, clear of it and of every label
guard_x = x_of["browser"] + 12
s.label("[password matches]", (guard_x, top + 8), font=GUARD)
y += 14
message("auth", "api", "session token", reply=True)
message("api", "browser", "200 + cookie", reply=True)
split = y - 26
s.path([(X0 - 20, split), (X0 + 3 * SPACING + BOX_W + 20, split)],
       paint=Paint(stroke="grey", dashed=True), heads="none")
s.label("[else]", (guard_x, split + 8), font=GUARD)
y += 14
message("auth", "api", "invalid credentials", reply=True)
message("api", "browser", "401, show error", reply=True)
bottom = y - 20
s.frame((X0 - 20, top, 3 * SPACING + BOX_W + 40, bottom - top),
        paint=Paint(fill="fragment"))
s.label("alt", (X0 - 8, top - 22), font=Font(14, "black", "left"))

# lifelines last, so they run the full height of the conversation
end = bottom + 30
for key in x_of:
    s.path([(x_of[key], BOX_H), (x_of[key], end)], paint=LIFELINE, heads="none")

# the diagram's own geometry, which no gate sees
ys = [m[0] for m in msgs]
assert ys == sorted(ys) and len(set(ys)) == len(ys), "messages out of time order"
assert all(a in x_of.values() and b in x_of.values() for _, a, b in msgs), \
    "a message end is off every lifeline"

# ---- key ------------------------------------------------------------------------
key_y = end + 60
s.legend([("the person's side", "client"), ("a backend service", "service"),
          ("where data is stored", "data"), ("alt: exactly one branch runs", "fragment")],
         at=(40, key_y), title="What the colours mean")
s.glossary([("lifeline", "the dashed line: one participant, through time"),
            ("reply", "a dashed arrow answering the request above it"),
            ("alt fragment", "a box of alternatives; its [guard] says when each runs"),
            ("hash", "a one-way scramble; the stored password is never readable"),
            ("session token", "proof of login the browser sends from now on")],
           at=(420, key_y))

out_dir = sys.argv[1] if len(sys.argv) > 1 else "out"
s.save("sequence_diagram", out_dir=out_dir, gates=Gates.strict())
print("wrote sequence_diagram.excalidraw + .html")
