"""Text that explains a diagram rather than belonging to it: titles, captions,
section headings, and the two decoders — the colour legend and the term glossary."""

from .geometry import Rect, as_point, fit_text, overlap_2d, seg_rect_overlap, text_extent
from .style import FILL, STROKE, Font, Paint, TextStyle, resolve

TITLE_FONT = Font(28, None, "left")
LABEL_FONT = Font(12, "grey", "center")
SECTION_FONT = Font(18, "black", "left")
KEY_FONT = Font(13, "black", "left")
TAKEAWAY_FONT = Font(15, "black", "left")
NOTE_FONT = Font(13, "grey", "left")

# A teaching diagram explains at most two "why"s in its margin; a third is a
# paragraph that belongs in the text around the diagram, not on it.
MAX_NOTES = 2
_NOTE_GAP = 60     # clear space between a margin note and the element it explains
_CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"


def numbered_text(n, text):
    """`text` opened by the step number `n` as a circled digit (①, ②, ...)."""
    # implements: REQ-EXCALIDRAW-862
    mark = _CIRCLED[n - 1] if 1 <= n <= len(_CIRCLED) else "(%d)" % n
    return "%s %s" % (mark, text)

_PAD = 14          # inner margin of a legend / glossary panel
_SWATCH = 18       # side of a legend colour swatch


class AnnotateMixin(object):
    """Free-standing text. Legend and glossary return their frame's id."""

    def title(self, text, at, *, font=None, group=None):
        """A large free-standing heading. `at` is the anchor point: the left
        edge, the centre or the right edge, per the font's alignment."""
        font = Font.coerce(font, TITLE_FONT)
        x, y = as_point(at)
        tw, th = text_extent(text, font.size)
        # Excalidraw aligns text only within the element's own width, so a
        # centred or right-aligned anchor shifts the element's left edge.
        if font.align == "center":
            x = x - tw / 2
        elif font.align == "right":
            x = x - tw
        color = resolve(font.color, STROKE, STROKE["black"])
        el = self._text_el(text, Rect(x, y, tw, th),
                           TextStyle(font.size, color, font.align, "top"), group=group)
        self.elements.append(el)
        return el["id"]

    def label(self, text, at, *, font=None, group=None):
        """A small caption — grey, 12px and centred on `at` unless `font` says
        otherwise."""
        return self.title(text, at, font=Font.coerce(font, LABEL_FONT), group=group)

    def takeaway(self, text, at, *, font=None):
        """The one line a reader should leave with, set under the subtitle in
        black at 15px and opened by "Takeaway:". Returns the text id."""
        # implements: REQ-EXCALIDRAW-862
        if not text.startswith("Takeaway"):
            text = "Takeaway: " + text
        return self.title(text, at, font=Font.coerce(font, TAKEAWAY_FONT))

    def note(self, text, target, at=None, *, font=None):
        """A margin note explaining WHY `target` is the way it is, joined to it by
        a dashed grey leader that turns only at right angles. `at` is the note's
        top-left; omitted, the note goes in the margin right of, left of, below or
        above the diagram, the first of those whose leader cuts no other shape.
        The note is overlap-checked like a box and its leader like an arrow. A
        scene takes at most MAX_NOTES (2); a third raises ValueError, and so does a
        note with no clear margin. Returns the note's text id."""
        # implements: REQ-EXCALIDRAW-862
        if len(self._leaders) >= MAX_NOTES:
            raise ValueError("note(): at most %d margin notes; say the rest in the "
                             "text around the diagram" % MAX_NOTES)
        font = Font.coerce(font, NOTE_FONT)
        wrapped, _w, _h = fit_text(text, size=font.size, max_chars=34)
        tw, th = text_extent(wrapped, font.size)
        options = [as_point(at)] if at is not None else self._margins(target, tw, th)
        for x, y in options:
            legs = self._leader((x, y, tw, th), target)
            if at is not None or not self._leader_blocked(legs, target, (x, y, tw, th)):
                break
        else:
            raise ValueError("note(): no clear margin for a note on %r; attach it to a "
                             "node on the diagram's edge, or pass at=" % target)
        color = resolve(font.color, STROKE, STROKE["grey"])
        el = self._text_el(wrapped, Rect(x, y, tw, th), TextStyle(font.size, color, "left", "top"))
        self.elements.append(el)
        self._nodes.append((el["id"] + "-note", x, y, tw, th,
                            'note "%s"' % wrapped.split("\n")[0][:24]))
        self._path_extents.append((x, y, x + tw, y + th))
        aid = self.path(legs, paint=Paint(stroke="grey", dashed=True), heads="end")
        self._leaders[aid] = target
        return el["id"]

    def _margins(self, target, tw, th):
        """Candidate top-left points for a note on `target`: in the margin right
        of and left of everything level with it, then below and above everything
        drawn."""
        x0, y0, x1, y1 = self.bounds()
        tx, ty, tW, tH, _ = self._geom[target]
        top = ty + tH / 2 - th / 2
        level = [g for g in self._geom.values()
                 if g[1] < top + th + _NOTE_GAP / 2 and g[1] + g[3] > top - _NOTE_GAP / 2]
        right = max(g[0] + g[2] for g in level)
        left = min(g[0] for g in level)
        return [(right + _NOTE_GAP, top),
                (left - _NOTE_GAP - tw, top),
                (tx + tW / 2 - tw / 2, y1 + _NOTE_GAP),
                (tx + tW / 2 - tw / 2, y0 - _NOTE_GAP - th)]

    def _leader(self, note, target):
        """The right-angle points from a note's facing side to `target`: one leg
        where they share a row or column, else across then into its top or bottom."""
        nx, ny, nw, nh = note
        tx, ty, tw, th, _ = self._geom[target]
        lo_y, hi_y = max(ny, ty), min(ny + nh, ty + th)
        lo_x, hi_x = max(nx, tx), min(nx + nw, tx + tw)
        if hi_y - lo_y > 4:                       # side by side: one level leg
            y = (lo_y + hi_y) / 2
            return [(nx - 6, y), (tx + tw + 8, y)] if nx >= tx + tw else \
                [(nx + nw + 6, y), (tx - 8, y)]
        if hi_x - lo_x > 4:                       # stacked: one upright leg
            x = (lo_x + hi_x) / 2
            return [(x, ny - 6), (x, ty + th + 8)] if ny >= ty + th else \
                [(x, ny + nh + 6), (x, ty - 8)]
        sx = nx - 6 if nx >= tx + tw / 2 else nx + nw + 6
        sy = ny + nh / 2
        cx = tx + tw / 2
        ey = ty - 8 if sy < ty else ty + th + 8
        return [(sx, sy), (cx, sy), (cx, ey)]

    def _leader_blocked(self, legs, target, note):
        """True when a leg cuts a shape other than `target`, or the note itself
        lands on one."""
        for nid, (x, y, w, h, _s) in self._geom.items():
            if nid == target or nid in self._containers:
                continue
            if any(seg_rect_overlap(a, b, (x, y, w, h)) > 0 for a, b in zip(legs, legs[1:])):
                return True
            if min(overlap_2d(note, (x, y, w, h))) > 0:
                return True
        return False

    def section(self, heading, *, x=40, gap=70, font=None):
        """Open a stacked region: place a heading `gap` px below ALL existing
        content and return the y at which to place this region's shapes."""
        font = Font.coerce(font, SECTION_FONT)
        bottom = max((e.get("y", 0) + e.get("height", 0) for e in self.elements),
                     default=0)
        top = bottom + gap
        self.label(heading, (x, top), font=font)
        self._sections.append((top, heading))
        return top + font.size * 1.6 + 10

    def role(self, name, color):
        """Declare a semantic role -> palette colour alias, usable as a paint
        (role('agent', 'violet') then box(..., paint='agent')) and as the source
        for legend()."""
        self.roles[name] = color
        return self

    def _key_panel(self, rect, title, font):
        """The white framed panel legend and glossary share. `rect` is its top-left
        and the size its rows need; a title widens and heightens it. Returns
        (frame id, first row y, the panel's (x, y, w, h))."""
        title_h = (font.size + 1) * 1.5 if title else 0
        w = rect.w
        if title:
            w = max(w, _PAD * 2 + int(len(title) * (font.size + 1) * 0.62))
        box = (rect.x, rect.y, w, rect.h + title_h)
        fid = self.frame(box, paint=Paint(fill="#ffffff"))
        cy = rect.y + _PAD
        if title:
            self.label(title, (rect.x + _PAD, cy),
                       font=Font(font.size + 1, font.color, font.align))
            cy += title_h
        return fid, cy, box

    def legend(self, entries=None, at=(0, 0), *, title="Legend", font=None):
        """A colour key mapping each fill to its meaning, so a reader with no
        context can decode the diagram. `entries` is a list of (label, colour);
        omitted, the Scene's declared roles are used. Returns the frame id.
        Use it whenever colour encodes a role."""
        # implements: REQ-EXCALIDRAW-849
        font = Font.coerce(font, KEY_FONT)
        if entries is None:
            entries = list(self.roles.items())
        if not entries:
            raise ValueError("legend() needs entries or Scene(roles=...)")
        row_h = max(_SWATCH, font.size * 1.25) + 10
        longest = max((len(str(lbl)) for lbl, _ in entries), default=1)
        x, y = as_point(at)
        fid, cy, box = self._key_panel(
            Rect(x, y, _PAD * 2 + _SWATCH + 8 + int(longest * font.size * 0.62) + 6,
                 _PAD * 2 + row_h * len(entries)), title, font)
        for lbl, col in entries:
            self.box("", (box[0] + _PAD, cy, _SWATCH, _SWATCH), paint=col, container=True)
            # the resolved hex lets check_legend_coverage() assert every
            # semantic fill in the scene is explained by this key
            self._legend_colours.add(resolve(self._colour_of(col), FILL, "transparent"))
            self.label(str(lbl), (box[0] + _PAD + _SWATCH + 8,
                                  cy + (_SWATCH - font.size) / 2), font=font)
            cy += row_h
        return fid

    def glossary(self, entries, at, *, title="Glossary", font=None):
        """A term -> meaning key so a reader can decode jargon on the canvas.
        `entries` is a list of (term, meaning); each renders as one "TERM — meaning"
        line. The panel is overlap-checked like real content. Returns the frame id."""
        # implements: REQ-EXCALIDRAW-849
        font = Font.coerce(font, KEY_FONT)
        if not entries:
            raise ValueError("glossary() needs at least one (term, meaning)")
        rows = [f"{t} — {m}" for t, m in entries]
        row_h = font.size * 1.25 + 8
        x, y = as_point(at)
        fid, cy, box = self._key_panel(
            Rect(x, y, _PAD * 2 + int(max(len(r) for r in rows) * font.size * 0.58),
                 _PAD * 2 + row_h * len(entries)), title, font)
        # frame() is container-exempt, so register the panel as overlap-checked
        # content explicitly; it stays out of the geometry registry, so it is not
        # an arrow-crossing obstacle.
        self._nodes.append((fid + "-box",) + box + (f'glossary "{title}"',))
        for r in rows:
            self.label(r, (box[0] + _PAD, cy), font=font)
            cy += row_h
        return fid
