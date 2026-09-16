#!/usr/bin/env python3
# implements: ARCH-EXCALIDRAW-030
# implements: ARCH-EXCALIDRAW-031
# implements: ARCH-EXCALIDRAW-032
# implements: ARCH-EXCALIDRAW-033
# implements: ARCH-EXCALIDRAW-034
"""
excalidraw_builder.py — build valid .excalidraw scenes (and a self-contained HTML
viewer) from a small declarative API. Python standard library only.

Why this exists
---------------
The Excalidraw file format is a flat list of elements, each carrying a lot of
boilerplate (random seeds, version nonces, two-way arrow bindings, bound-text
back-references). Hand-writing that JSON is error-prone. The builder hides it behind a
handful of calls so the *diagram* is the only thing you describe:

    from excalidraw_builder import Gates, Scene

    s = Scene(seed=7)
    a = s.box("User prompt", (120, 40), paint="blue")
    b = s.box("Skill", (120, 180), paint="indigo")
    s.arrow(a, b, label="activates")
    s.title("FLOW", (120, -40), font=36)
    s.save("flow", gates=Gates.strict())      # -> flow.excalidraw + flow.html

This file is the stable import name and the command line. The code lives in the
`excalidraw_engine` package beside it, one module per responsibility; see its
__init__ for the map. `references/builder_api.md` documents every call.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from excalidraw_engine import (  # noqa: E402
    DASHED, FILL, STROKE, Font, Gates, PackOptions, Paint, Rect, Scene,
    discover_components, discover_stub, fit_text, render_html, scene_from_json,
    scene_from_spec,
)
from excalidraw_engine.cli import main  # noqa: E402

__all__ = [
    "DASHED", "FILL", "Font", "Gates", "PackOptions", "Paint", "Rect", "STROKE", "Scene",
    "discover_components", "discover_stub", "fit_text", "render_html", "scene_from_json",
    "scene_from_spec",
]

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
