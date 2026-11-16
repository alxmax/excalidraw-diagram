# implements: REQ-EXCALIDRAW-848
"""The builder's own smoke run: `python excalidraw_builder.py` with no command.

It renders every family of shape, runs the layout helpers, and asserts nothing
overlaps and no connector crosses a box. It exits non-zero on a layout regression —
the failure a unit test does not catch, because the JSON stays perfectly valid while
the diagram becomes unreadable."""

import os
import tempfile

from .gates import Gates
from .geometry import polyline_midpoint
from .scene import Scene


def _expect_refusal(scene, name, out, gates=None):
    """save() must raise ValueError; anything else fails the smoke run."""
    try:
        scene.save(name, out_dir=out, gates=gates)
    except ValueError:
        return
    raise SystemExit("FAIL: %s was not refused" % name)


def _poster(out):
    """A small poster using roles, a grid, a routed label, a legend and
    align/distribute — clean under every check."""
    s = Scene(seed=1, roles={"source": "blue", "worker": "violet"})
    s.title("demo", (0, -40), font=24)
    stages = s.row(["ingest", "process", "store"], (0, 0), cell={"paint": "source"},
                   connect=True)
    workers = s.grid([f"n{i}" for i in range(6)], (0, 150), 3,
                     cell={"size": (120, 60), "paint": "worker"})
    s.enclose(workers, label="parallel workers")
    done = s.box("done", (720, 0), paint="green")
    s.arrow(stages[-1], done)
    s.path([(0, 460), (620, 460)], label="feedback")
    s.legend([("source", "blue"), ("worker", "violet"), ("done", "green")], (760, 150))
    movers = s.column(["a", "b"], (760, 360), cell={"size": (80, 40)})
    s.align(movers, "left")
    s.distribute(movers, "y", gap=20)
    for check in (s.check_overlaps, s.check_arrow_crossings, s.check_legend_coverage,
                  s.check_short_arrows):
        assert not check(), (check.__name__, check())
    return s.save("smoke", out_dir=out)


def _refusals(out):
    """The gates must refuse what they exist to refuse."""
    iso = Scene(seed=7)          # an ISO polygon's fill is still a legend fill
    iso.data("input", (0, 0), paint="blue")
    iso.legend([("worker", "violet")], (0, 200))
    assert iso.check_legend_coverage(), "unexplained ISO polygon fill must be flagged"
    sa = Scene(seed=4)           # 4px apart: a degenerate, invisible connector
    sa.arrow(sa.box("A", (0, 0, 120, 60)), sa.box("B", (124, 0, 120, 60)), label="x")
    assert sa.check_overlaps() == [], "close-but-not-touching boxes don't overlap"
    assert len(sa.check_short_arrows()) == 1, sa.check_short_arrows()
    _expect_refusal(sa, "smoke_short", out)
    sa.save("smoke_short", out_dir=out, gates=Gates(short_arrows="off"))   # the escape
    s2 = Scene(seed=2)           # a straight line through the middle box
    left = s2.box("L", (0, 0, 80, 40))
    s2.box("M", (200, 0, 80, 40))
    s2.arrow(left, s2.box("R", (400, 0, 80, 40)))
    _expect_refusal(s2, "smoke_err", out, Gates(crossing="error"))
    s3 = Scene(seed=5)           # the design gates: a rainbow, a crowd, a diagonal
    boxes = [s3.box(c, (i * 200, 0), paint=c)
             for i, c in enumerate(("blue", "green", "violet", "teal", "pink"))]
    s3.grid([f"m{i}" for i in range(8)], (0, 200), 4)
    s3.arrow(boxes[0], s3.box("low", (-400, 150)))
    assert [k for k, _n, _x in s3.check_focus()] == ["roles"], s3.check_focus()
    assert s3.check_node_budget() == [("the scene", 14)], s3.check_node_budget()
    assert s3.check_orthogonal_arrows() == [("blue", "low")], s3.check_orthogonal_arrows()
    _expect_refusal(s3, "smoke_design", out, Gates(focus="error"))


def _geometry():
    """Edge cases the examples never reach."""
    assert Scene(seed=8).pipeline([], (0, 0)) == [], "empty pipeline must return []"
    sc = Scene(seed=9)           # a curved arrow's bbox spans its control point
    aid = sc.arrow(sc.box("A", (0, 0, 80, 40)), sc.box("B", (300, 0, 80, 40)), curve=True)
    assert sc._element(aid)["height"] >= 29, "curved arrow bbox must span the control point"
    mid = polyline_midpoint([(0, 0), (0, 100), (200, 100), (200, 0)])
    assert abs(mid[0] - 100) < 1 and abs(mid[1] - 100) < 1, mid
    se = Scene(seed=6)           # an elbow arrow is square and clear of the box between
    a, b = se.box("a", (0, 0)), se.box("b", (500, 300))
    se.box("between", (240, 0))
    se.arrow(a, b, label="square", elbow=True)
    assert not se.check_orthogonal_arrows() and not se.check_arrow_crossings()
    sb = Scene(seed=3)           # bounds() includes a routed connector's dip
    sb.route_under(sb.box("a", (0, 0, 80, 40)), sb.box("b", (200, 0, 80, 40)), drop=60)
    assert sb.bounds()[3] >= 100, sb.bounds()


def run():
    """Run the smoke test; raises (or exits non-zero) on any regression."""
    # verifies: REQ-EXCALIDRAW-844#CASE-4  # verifies: REQ-EXCALIDRAW-845#CASE-1
    # verifies: REQ-EXCALIDRAW-845#CASE-2
    out = os.path.join(tempfile.gettempdir(), "excd")
    pj, ph = _poster(out)
    _refusals(out)
    _geometry()
    print("wrote", pj, ph)
    print("OK smoke test (legend/role/align/distribute/path-bg/crossing-gate/"
          "design-gates/elbow)")
