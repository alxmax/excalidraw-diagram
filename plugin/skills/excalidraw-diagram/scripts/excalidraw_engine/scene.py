"""`Scene`: the one class a generator uses, assembled from focused parts.

Each mixin owns one family of calls and reaches the shared state only through
`Canvas`. Reading one of them never requires reading the others, and a check can be
tested against a scene built by any of them."""

from .annotate import AnnotateMixin
from .arrange import ArrangeMixin
from .canvas import Canvas
from .checks import ChecksMixin
from .connectors import ConnectorsMixin
from .gates import GatesMixin
from .pack import PackMixin
from .shapes import ShapesMixin


class Scene(Canvas, ShapesMixin, ConnectorsMixin, ArrangeMixin, AnnotateMixin,
            PackMixin, ChecksMixin, GatesMixin):
    # implements: REQ-EXCALIDRAW-844
    """A drawing surface that accumulates elements and saves them as an
    .excalidraw scene plus a self-contained HTML viewer.

        s = Scene(seed=7)
        a = s.box("Client", (40, 60), paint="grey")
        b = s.box("API", (320, 60), paint="blue")
        s.arrow(a, b, label="request")
        s.save("auth_flow", out_dir="docs", gates=Gates.strict())
    """
