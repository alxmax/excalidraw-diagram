"""How an element is painted: the palette, and the value objects that carry a choice
of colour or type from the caller to the element.

Two layers on purpose. `Paint` and `Font` are what a generator writes — palette
names, role names, `None` for "the default". `Style` and `TextStyle` are what an
element is built from — every value resolved. Keeping them apart means a caller never
sees Excalidraw's fill-style or roundness knobs, and an element never sees a role.
"""

# ---------------------------------------------------------------------------
# Palette — Excalidraw's own swatches (stroke = strong, fill = light tint)
# ---------------------------------------------------------------------------
STROKE = {
    "grey":   "#343a40", "red":  "#e03131", "orange": "#e8590c",
    "yellow": "#f08c00", "green": "#2f9e44", "teal":   "#0c8599",
    "blue":   "#1971c2", "indigo": "#3b5bdb", "violet": "#6741d9",
    "pink":   "#c2255c", "black": "#1e1e1e",
}
FILL = {
    "grey":   "#e9ecef", "red":  "#ffc9c9", "orange": "#ffd8a8",
    "yellow": "#ffec99", "green": "#b2f2bb", "teal":   "#99e9f2",
    "blue":   "#a5d8ff", "indigo": "#bac8ff", "violet": "#d0bfff",
    "pink":   "#fcc2d7", "transparent": "transparent",
}

# Excalidraw fontFamily codes: 1 = hand-drawn (Excalifont/Virgil),
# 2 = normal (Helvetica), 3 = code (Cascadia).
TYPEFACES = {"hand": 1, "normal": 2, "code": 3}


def resolve(color, table, default):
    """A hex colour for `color`: a hex string passes through, a palette name is
    looked up in `table`, and `None` or an unknown name gives `default`."""
    if color is None:
        return default
    if isinstance(color, str) and color.startswith("#"):
        return color
    if color == "transparent":
        return "transparent"
    return table.get(color, default)


class Paint(object):  # implements: REQ-EXCALIDRAW-853
    """What a caller says about an element's colour and line: its fill, its
    stroke, whether the line is dashed, and the group it belongs to.

    Every drawing call takes one `paint=`. A bare colour string is accepted
    wherever a Paint is, and means the element's natural colour: a shape's fill,
    a connector's stroke."""

    __slots__ = ("fill", "stroke", "dashed", "group")

    def __init__(self, fill=None, stroke=None, dashed=False, group=None):
        self.fill, self.stroke = fill, stroke
        self.dashed, self.group = dashed, group

    @classmethod
    def coerce(cls, paint, natural="fill", default=None):
        """`paint` as a Paint. A string becomes the `natural` colour, `None`
        becomes `default` (or a blank Paint)."""
        if isinstance(paint, cls):
            return paint
        if paint is None:
            return default if default is not None else cls()
        if isinstance(paint, str):
            return cls(**{natural: paint})
        raise TypeError("paint must be a Paint, a colour string or None, not %r"
                        % type(paint).__name__)


class Font(object):  # implements: REQ-EXCALIDRAW-853
    """What a caller says about a run of text: its size, colour and alignment.
    A field left as None keeps the calling method's own default — a label stays
    grey and a title stays left-aligned when only the size is given. An int is
    accepted wherever a Font is, and means its size."""

    __slots__ = ("size", "color", "align")

    def __init__(self, size=None, color=None, align=None):
        self.size, self.color, self.align = size, color, align

    @classmethod
    def coerce(cls, font, default):
        """`font` as a complete Font: every field it leaves None comes from
        `default`, and an int is a size."""
        if font is None:
            return default
        if isinstance(font, (int, float)) and not isinstance(font, bool):
            font = cls(font)
        if not isinstance(font, cls):
            raise TypeError("font must be a Font, a size or None, not %r"
                            % type(font).__name__)
        return cls(default.size if font.size is None else font.size,
                   default.color if font.color is None else font.color,
                   default.align if font.align is None else font.align)


DASHED = Paint(dashed=True)


class Style(object):  # implements: REQ-EXCALIDRAW-844
    """How one element is painted once every choice is resolved: the stroke/fill
    pair, the line style, the corner roundness and the element's group. Fill style
    and stroke width are not here because nothing in the builder ever varies them."""

    __slots__ = ("stroke", "fill", "stroke_style", "roundness", "group")

    def __init__(self, stroke, fill="transparent", *, stroke_style="solid",
                 roundness=None, group=None):
        self.stroke, self.fill = stroke, fill
        self.stroke_style, self.roundness, self.group = stroke_style, roundness, group

    @property
    def groups(self):
        """The groupIds list Excalidraw expects — empty when ungrouped."""
        return [self.group] if self.group else []


class TextStyle(object):  # implements: REQ-EXCALIDRAW-844
    """How one run of text is drawn once resolved: size, hex colour and the two
    alignments."""

    __slots__ = ("size", "color", "align", "valign")

    def __init__(self, size, color, align="center", valign="middle"):
        self.size, self.color = size, color
        self.align, self.valign = align, valign
