"""What a check's hits mean at save(): which gates refuse the file, which only
warn, and the one moment the scene becomes two files on disk."""

import collections
import json
import os
import sys

from .viewer import html_page

_MODES = ("error", "warn", "off")

_Gate = collections.namedtuple("_Gate", "name check detail problem remedy")

# One row per gate, in the order save() runs them. `detail` renders the check's
# hits into the text both the raised error and the printed warning embed. A new
# gate is a row here, not another block in save().
_GATES = (
    _Gate("overlap", "check_overlaps",
          lambda hits: "; ".join(f"'{a}' overlaps '{b}'" for a, b in hits),
          "overlapping shape(s): ",
          ". Move the coordinates apart, wrap a grouping shape with container=True, "
          "or pass Gates(overlap='off') if intentional."),
    _Gate("short_arrows", "check_short_arrows",
          lambda hits: "; ".join(f"'{a}'->'{b}' ({ln:g}px)" for a, b, ln in hits),
          "arrow(s) too short to render as a visible line (only the label would "
          "show): ",
          ". Move the shapes farther apart (~60px+ of clear space), or pass "
          "Gates(short_arrows='off') if intentional."),
    _Gate("crossing", "check_arrow_crossings",
          lambda hits: "; ".join(sorted({f"{a}->{b} crosses '{c}'" for a, b, c in hits})),
          "arrow(s) run through an unrelated box: ",
          ". Reroute with route_under()/path(), or move the box."),
    _Gate("legend", "check_legend_coverage",
          lambda hits: ", ".join(hits),
          "fill colour(s) used but missing from the legend: ",
          ". Add a legend() entry for each, or recolour the box to a legended colour."),
    _Gate("overflow", "check_text_overflow",
          lambda hits: "; ".join(f"'{lab}' (text {tw}px in {cw}px box)"
                                 for lab, tw, cw, _th, _ch in hits),
          "bound text overflows its box: ",
          ". Widen the box, or wrap the label with fit_text()."),
    _Gate("text_overlap", "check_text_overlaps",
          lambda hits: "; ".join(f"'{a}' overlaps '{b}'" for a, b in hits),
          "free text label(s) overlap: ",
          ". Move the caption or heading apart."),
    _Gate("label_fit", "check_arrow_label_fit",
          lambda hits: "; ".join(f"'{lab}' ({stub:g}px line each side)"
                                 for lab, stub in hits),
          "arrow label(s) too wide for their connector (the label crowds the "
          "arrowheads or spills onto the boxes): ",
          ". Widen the gap between the shapes, or shorten or wrap the label."),
)
_NAMES = tuple(g.name for g in _GATES)
_HARD = ("overlap", "short_arrows")


class Gates(object):
    """How save() treats each check's hits: "error" raises, "warn" prints to
    stderr, "off" ignores.

    The two hard gates — overlap and short_arrows — are real defects and default
    to "error". The five advisory gates default to "warn". Name any gate to set it
    alone: Gates(crossing="error"), Gates(overlap="off")."""

    def __init__(self, advisory="warn", hard="error", **per_gate):
        unknown = set(per_gate) - set(_NAMES)
        if unknown:
            raise ValueError("unknown gate(s) %s; the gates are %s"
                             % (sorted(unknown), ", ".join(_NAMES)))
        self.modes = {n: hard if n in _HARD else advisory for n in _NAMES}
        self.modes.update(per_gate)
        for name, mode in self.modes.items():
            if mode not in _MODES:
                raise ValueError("gate %s must be one of %s, not %r"
                                 % (name, ", ".join(_MODES), mode))

    @classmethod
    def strict(cls):
        """Every gate at "error" — a ship-quality diagram."""
        return cls(advisory="error")


class GatesMixin(object):
    """The save() contract."""

    def save(self, basename, out_dir=".", gates=None, offline=None):
        """Run the gates, then write <basename>.excalidraw + <basename>.html into
        `out_dir` and return both paths. Refuses a second call: one scene, one
        save() — stack more views as regions of the same scene instead. The viewer
        carries its own renderer unless `offline=False` asks for the CDN one."""
        # implements: REQ-EXCALIDRAW-845  # implements: REQ-EXCALIDRAW-846
        # implements: REQ-EXCALIDRAW-847
        if self._saved:
            raise RuntimeError(
                "save() already called on this Scene — one scene, one save(). "
                "Stack additional views as labelled regions in the same scene "
                "(use bounds() to start the next region below the previous one).")
        modes = (gates or Gates()).modes
        for gate in _GATES:
            mode = modes[gate.name]
            hits = getattr(self, gate.check)() if mode != "off" else []
            if not hits:
                continue
            if mode == "error":
                raise ValueError(f"{len(hits)} {gate.problem}{gate.detail(hits)}"
                                 f"{gate.remedy}")
            print(f"WARNING [{gate.name}]: {gate.problem}{gate.detail(hits)}",
                  file=sys.stderr)
        return self._write(basename, out_dir, offline)

    def _write(self, basename, out_dir, offline=None):
        """Write <basename>.excalidraw + .html and return both paths."""
        os.makedirs(out_dir, exist_ok=True)
        scene = self.to_dict()
        p_json = os.path.join(out_dir, basename + ".excalidraw")
        # newline="\n" on every write: the default translates "\n" to os.linesep,
        # and the same seeded scene must be the same bytes on every platform.
        with open(p_json, "w", encoding="utf-8", newline="\n") as f:
            json.dump(scene, f, ensure_ascii=False, indent=2)
        p_html = os.path.join(out_dir, basename + ".html")
        with open(p_html, "w", encoding="utf-8", newline="\n") as f:
            f.write(html_page(basename, scene, offline))
        self._saved = True
        return p_json, p_html
