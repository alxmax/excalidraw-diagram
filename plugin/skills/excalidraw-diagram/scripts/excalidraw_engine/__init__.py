"""The excalidraw-diagram builder, one module per responsibility.

Import it through `excalidraw_builder` — that facade is the stable name the skill,
the examples and every generated stub use; this package is how it is organised.

    style       Paint, Font — what a caller says about colour and type
    geometry    Rect and the pure layout maths
    canvas      the shared element and geometry state
    shapes      box(), the ISO 5807 set, frame()
    connectors  arrow(), path(), route_under()
    arrange     arrange()/row()/column()/grid(), pipeline(), enclose(), lane()
    annotate    title(), label(), section(), legend(), glossary()
    pack        pack() — coordinate-free graph layout
    checks      the seven inspection checks
    gates       Gates and save()
    scene       Scene, assembled from the above
    viewer      the HTML viewer and render_html()
    discover    discover_stub()
    spec        scene_from_spec() / scene_from_json()
    cli         the command line
"""

from .discover import discover_components, discover_stub, render_stub
from .gates import Gates
from .geometry import Rect, fit_text
from .pack import PackOptions
from .scene import Scene
from .spec import scene_from_json, scene_from_spec
from .style import DASHED, FILL, STROKE, Font, Paint
from .viewer import html_page, render_html

__all__ = [
    "DASHED", "FILL", "Font", "Gates", "PackOptions", "Paint", "Rect", "STROKE", "Scene",
    "discover_components", "discover_stub", "fit_text", "html_page", "render_html",
    "render_stub", "scene_from_json", "scene_from_spec",
]
