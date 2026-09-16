"""Text that explains a diagram rather than belonging to it: titles, captions,
section headings, and the two decoders — the colour legend and the term glossary."""

from .geometry import Rect, as_point, text_extent
from .style import FILL, STROKE, Font, Paint, TextStyle, resolve

TITLE_FONT = Font(28, None, "left")
LABEL_FONT = Font(12, "grey", "center")
SECTION_FONT = Font(18, "black", "left")
KEY_FONT = Font(13, "black", "left")

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

    def section(self, heading, *, x=40, gap=70, font=None):
        """Open a stacked region: place a heading `gap` px below ALL existing
        content and return the y at which to place this region's shapes."""
        font = Font.coerce(font, SECTION_FONT)
        bottom = max((e.get("y", 0) + e.get("height", 0) for e in self.elements),
                     default=0)
        top = bottom + gap
        self.label(heading, (x, top), font=font)
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
            self._legend_colours.add(resolve(self.roles.get(col, col), FILL, "transparent"))
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
