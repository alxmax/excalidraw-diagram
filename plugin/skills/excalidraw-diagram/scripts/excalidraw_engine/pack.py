"""Graph auto-layout: a directed graph described by ids and edges alone, placed
with no coordinates from the caller.

Three passes — longest-path layering, barycenter ordering, placement — plus the
thing that matters more here than the ordering does: an edge becomes a straight
arrow ONLY when its centre-to-centre line clears every other box. Every other edge
(a feedback edge, one that skips layers, one whose line would cut a third box) is
routed through the empty channels between layers and along its own lane past the
diagram. Barycenter ordering minimises edge-EDGE crossings; the builder's gate
measures edges cutting through BOXES, so the routing is what keeps
check_arrow_crossings() empty.
"""

from .geometry import as_point, fit_text, text_extent
from .style import Paint

ROUTED = Paint(stroke="grey", dashed=True)


class PackOptions(object):
    """How pack() spaces a graph.

    direction: "LR" (layers become columns) or "TB" (layers become rows).
    gap_major: space between layers. gap_minor: space between siblings in a layer.
    lane_gap:  space between routed lanes. font_size: the node label size."""

    __slots__ = ("direction", "gap_major", "gap_minor", "lane_gap", "font_size")

    def __init__(self, direction="LR", gap_major=140, gap_minor=46, lane_gap=54,
                 font_size=13):
        if direction not in ("LR", "TB"):
            raise ValueError("pack(): direction must be 'LR' or 'TB'")
        self.direction, self.font_size = direction, font_size
        self.gap_major, self.gap_minor, self.lane_gap = gap_major, gap_minor, lane_gap


# ---------------------------------------------------------------------------
# graph algorithms — pure functions of ids and links
# ---------------------------------------------------------------------------
def _successors(ids, links):
    succ = {i: [] for i in ids}
    for k, link in enumerate(links):
        succ[str(link["src"])].append((str(link["dst"]), k))
    return succ


def back_edges(ids, links):
    """Indices of the links that close a cycle, by an iterative DFS.

    Layering needs a DAG; removing exactly these edges leaves one. They are also
    the edges pack() must route around the diagram rather than draw straight."""
    succ = _successors(ids, links)
    colour = dict.fromkeys(ids, "white")
    back = set()
    for root in ids:
        if colour[root] == "white":
            _walk(root, succ, colour, back)
    return back


def _walk(root, succ, colour, back):
    """DFS from `root` on an explicit stack: a 200-node chain must not depend on
    the recursion limit. A link into a node still on the path is a back edge."""
    colour[root] = "grey"
    stack = [(root, iter(succ[root]))]
    while stack:
        node, walk = stack[-1]
        nxt = _next_white(walk, colour, back)
        if nxt is None:
            colour[node] = "black"
            stack.pop()
        else:
            colour[nxt] = "grey"
            stack.append((nxt, iter(succ[nxt])))


def _next_white(walk, colour, back):
    """Advance `walk` to the next unvisited child, recording back edges passed."""
    for nxt, k in walk:
        if colour[nxt] == "grey":
            back.add(k)
        elif colour[nxt] == "white":
            return nxt
    return None


def layer_of(ids, links):
    """Longest-path layering over a DAG: a node sits one layer after the deepest
    node that reaches it. Kahn's algorithm, so no recursion."""
    succ = {i: [] for i in ids}
    indeg = dict.fromkeys(ids, 0)
    for link in links:
        succ[str(link["src"])].append(str(link["dst"]))
        indeg[str(link["dst"])] += 1
    layer = dict.fromkeys(ids, 0)
    queue = [i for i in ids if indeg[i] == 0]
    while queue:
        nxt = []
        for node in queue:
            for child in succ[node]:
                layer[child] = max(layer[child], layer[node] + 1)
                indeg[child] -= 1
                if indeg[child] == 0:
                    nxt.append(child)
        queue = nxt
    return layer


def by_barycenter(lay, neighbours, pos):
    """One ordering sweep: every node moves to the mean position of its
    neighbours in the reference layer; one with none keeps its place."""
    def key(item):
        idx, node = item
        seen = [pos[m] for m in neighbours[node] if m in pos]
        return sum(seen) / len(seen) if seen else float(idx)
    return [node for _, node in sorted(enumerate(lay), key=key)]


def validate(nodes, edges):
    """The node specs by id, the ids in order, and the edges — or ValueError."""
    specs, ids = {}, []
    for node in nodes:
        nid = str(node.get("id", "") or "")
        if not nid:
            raise ValueError("pack(): every node needs a non-empty 'id'")
        if nid in specs:
            raise ValueError("pack(): duplicate node id %r" % nid)
        specs[nid] = node
        ids.append(nid)
    if not ids:
        raise ValueError("pack() needs at least one node")
    links = []
    for edge in edges:
        src, dst = str(edge.get("src", "")), str(edge.get("dst", ""))
        if src not in specs or dst not in specs:
            raise ValueError("pack(): edge %r -> %r names a node that does not exist"
                             % (src, dst))
        if src == dst:
            raise ValueError("pack(): self-edge on %r — a loop has no layer to route "
                             "through" % src)
        links.append(edge)
    return specs, ids, links


# ---------------------------------------------------------------------------
# one layout run
# ---------------------------------------------------------------------------
class _PackRun(object):
    """The state of laying out one graph on one scene, one step per method."""

    def __init__(self, scene, graph, at, opts):
        self.scene, self.opts = scene, opts
        self.specs, self.ids, self.links = graph
        self.origin = as_point(at)
        self.lr = opts.direction == "LR"
        self.back = back_edges(self.ids, self.links)
        self.forward = [link for k, link in enumerate(self.links) if k not in self.back]
        self.layer = layer_of(self.ids, self.forward)
        self.placed, self.size, self.at, self.extent = {}, {}, [], []

    def layers(self, groups):
        """The ids per layer, ordered by four barycenter sweeps each way, with
        each group's members kept adjacent so its frame holds only them."""
        layers = [[] for _ in range(max(self.layer.values()) + 1)]
        for nid in self.ids:
            layers[self.layer[nid]].append(nid)
        pred = {i: [] for i in self.ids}
        succ = {i: [] for i in self.ids}
        for link in self.forward:
            succ[str(link["src"])].append(str(link["dst"]))
            pred[str(link["dst"])].append(str(link["src"]))
        for _ in range(4):
            for k in range(1, len(layers)):
                pos = {n: p for p, n in enumerate(layers[k - 1])}
                layers[k] = by_barycenter(layers[k], pred, pos)
            for k in range(len(layers) - 2, -1, -1):
                pos = {n: p for p, n in enumerate(layers[k + 1])}
                layers[k] = by_barycenter(layers[k], succ, pos)
        gkey = {str(m): gi for gi, g in enumerate(groups) for m in g.get("members", ())}
        if gkey:
            layers = [sorted(lay, key=lambda n: gkey.get(n, -1)) for lay in layers]
        return layers

    def measure(self, layers):
        """Each node's size, and each layer's start coordinate and extent. A gap
        carrying a labelled arrow widens so the label keeps line on both sides."""
        for nid in self.ids:
            text, w, h = fit_text(str(self.specs[nid].get("label", nid)),
                                  size=self.opts.font_size, max_chars=22, min_size=(150, 58))
            spec = self.specs[nid]
            self.size[nid] = (float(spec.get("w", w)), float(spec.get("h", h)), text)
        gaps = [float(self.opts.gap_major)] * max(1, len(layers) - 1)
        for link in self.forward:
            a, b = self.layer[str(link["src"])], self.layer[str(link["dst"])]
            if b == a + 1 and link.get("label"):
                gaps[a] = max(gaps[a], text_extent(str(link["label"]), 14)[0] + 96.0)
        self.extent = [max(self._major(n) for n in lay) for lay in layers]
        cur = float(self.origin[0] if self.lr else self.origin[1])
        for k in range(len(layers)):
            self.at.append(cur)
            cur += self.extent[k] + (gaps[k] if k < len(gaps) else 0.0)

    def _major(self, nid):
        return self.size[nid][0] if self.lr else self.size[nid][1]

    def _minor(self, nid):
        return self.size[nid][1] if self.lr else self.size[nid][0]

    def place(self, layers, groups=()):
        """Draw every node, each layer centred on the widest one, then pushed
        along its layer out of any group frame it does not belong to."""
        gap = self.opts.gap_minor
        runs = [sum(self._minor(n) for n in lay) + gap * (len(lay) - 1) for lay in layers]
        widest = max(runs)
        origin = float(self.origin[1] if self.lr else self.origin[0])
        start = {}
        for k, lay in enumerate(layers):
            cur = origin + (widest - runs[k]) / 2.0
            for nid in lay:
                start[nid] = cur
                cur += self._minor(nid) + gap
        self._clear_frames(layers, groups, start)
        for k, lay in enumerate(layers):
            for nid in lay:
                w, h, text = self.size[nid]
                x, y = (self.at[k], start[nid]) if self.lr else (start[nid], self.at[k])
                spec = self.specs[nid]
                self.placed[nid] = self.scene.box(
                    text, (x, y, w, h), paint=spec.get("fill"),
                    shape=spec.get("kind", "rectangle"), font=self.opts.font_size)

    def _clear_frames(self, layers, groups, start):
        """Move non-members out of each group's frame, in `start` (node -> its
        minor-axis coordinate). A frame spans every layer its members reach and
        the minor range they cover, so a node centred in a narrower layer can
        fall inside it. The node — and every node beyond it on that side of its
        layer — moves out past the frame. A few passes settle groups that push
        one another; whatever still intrudes, check_overlaps() reports."""
        pad, clear = 24.0, self.opts.gap_minor / 2.0
        caption = 30.0 if self.lr else 0.0     # LR: the caption sits on the minor axis
        for _ in range(8):
            moved = False
            for group in groups:
                members = {str(m) for m in group.get("members", ()) if str(m) in start}
                if not members:
                    continue
                lo = min(start[m] for m in members) - pad - caption - clear
                hi = max(start[m] + self._minor(m) for m in members) + pad + clear
                reach = {self.layer[m] for m in members}
                for k in range(min(reach), max(reach) + 1):
                    moved |= self._push_out(layers[k], members, start, (lo, hi))
            if not moved:
                return

    def _push_out(self, lay, members, start, span):
        """Push the non-members of one layer out of `span`; True if one moved."""
        lo, hi = span
        for i, nid in enumerate(lay):
            a, b = start[nid], start[nid] + self._minor(nid)
            if nid in members or b <= lo or a >= hi:
                continue
            if a + b < lo + hi:                 # nearer the low edge: go lower
                shift, side = lo - b, lay[:i + 1]
            else:
                shift, side = hi - a, lay[i:]
            for n in side:
                if n not in members:
                    start[n] += shift
            return True
        return False

    def enclose(self, groups):
        """A frame around each group's placed members."""
        for group in groups:
            members = [self.placed[str(m)] for m in group.get("members", ())
                       if str(m) in self.placed]
            if members:
                self.scene.enclose(members, label=group.get("label"))

    def connect(self, margin=0.0):
        """Every edge: a straight arrow where its line is clear, routed otherwise.
        `margin` keeps the lanes clear of frames not drawn yet."""
        # channel[k] is the empty strip just before layer k, where a routed
        # connector crosses the diagram. 34px clears three things at once: no box
        # sits in a layer gap, enclose() draws its frame 24px out so the line never
        # traces a frame border, and an arrow's label is centred in the gap with
        # >=48px free at each end, so the line misses the text too.
        channel = [self.at[0] - 60.0] + [a - 34.0 for a in self.at[1:]]
        channel.append(self.at[-1] + self.extent[-1] + 60.0)
        _, _, far_x, far_y = self.scene.bounds()
        far = (far_y if self.lr else far_x) + margin
        lane = 0
        for k, link in enumerate(self.links):
            src, dst = str(link["src"]), str(link["dst"])
            a, b = self.placed[src], self.placed[dst]
            if (k not in self.back and self.layer[dst] - self.layer[src] == 1
                    and not self.scene._straight_hits(a, b)):
                self.scene.arrow(a, b, label=link.get("label"),
                                 paint=Paint(dashed=bool(link.get("dashed"))))
                continue
            self._route((a, b), (self.layer[src], self.layer[dst]), channel,
                        (far + self.opts.lane_gap * (lane + 1), min(lane * 5.0, 10.0),
                         link.get("label")))
            lane += 1

    def _route(self, ends, spans, channel, lane):
        """Route a connector out of one box, along a lane past the diagram, and
        back into the other. Eight points, and every leg is in empty space:

          out of the box on its far side -> `stub` px into the gap between rows
          -> across to the layer channel -> down (LR) or right (TB) to the lane
          -> along the lane -> and the mirror of all that back into the target.

        Leaving through the row gap rather than out of the box's side is the part
        that matters: a bound arrow carries its label at its own mid-height, the
        height of a box's side, and no gate would see a line through that text.
        The lane's nudge offsets connectors that share a channel."""
        lane_at, nudge, label = lane
        sx, sy, sw, sh, _ = self.scene._geom[ends[0]]
        dx, dy, dw, dh, _ = self.scene._geom[ends[1]]
        ls, ld = spans
        out_i, in_i = (ls, ld + 1) if ld <= ls else (ls + 1, ld)
        if out_i == in_i:       # neighbouring layers: both legs would share one
            out_i, in_i = (ls + 1, ld) if ld <= ls else (ls, ld + 1)   # channel
        out_c, in_c = channel[out_i] - nudge, channel[in_i] - nudge
        # clear of enclose()'s 24px frame, inside the row gap
        gap = self.opts.gap_minor
        stub = min(max(gap * 0.75, 30.0), gap - 6.0)
        if self.lr:                                 # lanes run below the diagram
            s_out, d_out = sy + sh + stub, dy + dh + stub
            pts = [(sx + sw / 2, sy + sh), (sx + sw / 2, s_out), (out_c, s_out),
                   (out_c, lane_at), (in_c, lane_at),
                   (in_c, d_out), (dx + dw / 2, d_out), (dx + dw / 2, dy + dh)]
        else:                                       # lanes run right of it
            s_out, d_out = sx + sw + stub, dx + dw + stub
            pts = [(sx + sw, sy + sh / 2), (s_out, sy + sh / 2), (s_out, out_c),
                   (lane_at, out_c), (lane_at, in_c),
                   (d_out, in_c), (d_out, dy + dh / 2), (dx + dw, dy + dh / 2)]
        return self.scene.path(pts, label=label, paint=ROUTED)


class PackMixin(object):
    """Coordinate-free layout of a whole graph."""

    def pack(self, nodes, edges=(), *, groups=(), at=(40, 0), options=None):
        """Lay out a directed graph from ids and edges alone — no coordinates.

        nodes:   dicts {id, label, fill, kind, w, h}; only `id` is required and
                 `kind` is any box() shape name.
        edges:   dicts {src, dst, label, dashed}.
        groups:  dicts {label, members: [id, ...]}, each drawn as an enclose() frame.
        options: a PackOptions (direction, spacing, font size).
        Returns {node id: scene id} so the caller can keep annotating."""
        # implements: REQ-EXCALIDRAW-851
        run = _PackRun(self, validate(nodes, edges), at, options or PackOptions())
        layers = run.layers(groups)
        run.measure(layers)
        run.place(layers, groups)
        run.connect(margin=24.0 if groups else 0.0)
        run.enclose(groups)     # after the arrows, so a caption can dodge them
        return run.placed
