"""Geometry of a C4 view, shared by the diagram renderers (pure and deterministic).

Where each element goes (classic C4, the same at every level):
- systems, containers and components flow in columns by a layered layout, callers to the left;
  in a zoomed-in view they are inside the boundary;
- in a zoomed-in view, outer elements that only call into the boundary go in a column to its
  left, the other outer elements in a column to its right; at L1, external systems go in the
  rightmost column;
- data stores and queues go in a row at the bottom, each under the column of the elements using
  it: inside the boundary when they belong to the zoomed-in system, below it otherwise. Columns
  holding several of them get wider, so the row never reaches the corridors.

Arrows are routed so that none crosses an element or runs over another arrow:
- every arrow leaves the right side of its source and enters the left side of its target (the
  top side of a data store or queue), each on its own point of that side, at least _PORT_GAP
  apart (an element with many arrows on a side gets taller);
- elements are pulled to the height of the elements they link to, so arrows run straight
  whenever the order of the columns allows;
- a corridor is as wide as the labels of the arrows starting there need (long labels wrap);
- vertical runs happen only in the corridors between columns, each on its own track;
- an arrow skipping columns goes through a slot reserved for it in each column in between;
- an arrow to a data store or queue goes down its corridor to its own lane in the band above
  the row, then drops into the element;
- an arrow pointing back (to its own column or one on the left) runs along its own lane below
  everything.

Platform services of a zoomed-in view form a group of their own below everything, linked once
to the boundary by a straight line down the boundary's left margin, where no element sits.
"""

import textwrap
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from itertools import pairwise

from exodus.domain.model import Node, NodeKind
from exodus.domain.views import C4View, ViewRelationship

WIDTH, HEIGHT = 240, 120  # of an element (taller when it has many arrows on a side)
LABEL_FONT = 11  # arrow labels, in px
_CHAR = 6.5  # estimated width of a label character, in px
_LABEL_MAX = 220  # longer labels wrap
_LABEL_GAP = 12  # between a label and the first turn of its arrow
_MIN_LABEL_ROOM = 60  # corridor space before the first track, even without labels
_PORT_GAP = 28  # minimum distance between arrow ends on a side (fits a 2-line label)
_NEAR = 8  # parallel lines of different arrows closer than this would look like one
_V_GAP = 60  # between the elements of a column
_SLOT = 20  # height reserved in a column for an arrow passing through it
_TRACK = 16  # between the vertical runs of a corridor
_MARGIN = 40  # corridor space after the last track
_MIN_CORRIDOR = 160
_PAD, _PAD_BOTTOM = 40, 70  # inside the boundary; its label sits at the bottom
_LANE = 20  # between the lanes of a band
_SIDE_BY_SIDE = 60  # between data stores/queues under the same column
_PLATFORM_WIDTH, _PLATFORM_HEIGHT, _PLATFORM_GAP = 160, 60, 30  # platform services, in a row
_PLATFORM_TITLE = 30  # room for the group's name, on top

_INFRA = (NodeKind.DATA_STORE, NodeKind.QUEUE)

Point = tuple[int, int]
_Item = str | tuple[int, int]  # an element id, or the slot of arrow i in column c


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class Box:
    node: Node
    rect: Rect


@dataclass(frozen=True)
class Arrow:
    relationship: ViewRelationship
    # first on the source's right side (or bottom, going down to a data store or queue), last
    # on the target's left side (or top, for a data store or queue)
    points: tuple[Point, ...]


@dataclass(frozen=True)
class Layout:
    boxes: dict[str, Box]  # by node id, in view order
    frame: Rect | None  # the boundary of a zoomed-in view
    arrows: list[Arrow]
    platform: Rect | None = None  # the group of platform services
    platform_boxes: dict[str, Box] = field(default_factory=dict)
    platform_link: tuple[Point, ...] = ()  # from the boundary's bottom down to the group's top


@dataclass(frozen=True)
class _Run:
    """Vertical run of an arrow in a corridor, joined by horizontals to the column on its left
    and/or on its right (None: the run turns into a lane instead)."""

    arrow: int
    step: int
    top: int
    bottom: int
    left: int | None
    right: int | None


def layers(ids: Sequence[str], edges: Iterable[tuple[str, str]]) -> dict[str, int]:
    """Column of each element: its longest path from the elements nothing points to. Edges that
    close a cycle (back edges of a depth-first search in the given order) are ignored."""
    targets: dict[str, list[str]] = {i: [] for i in ids}
    for source, target in edges:
        if source in targets and target in targets and source != target:
            targets[source].append(target)
    forward: dict[str, list[str]] = {i: [] for i in ids}
    done: dict[str, bool] = {}  # False while the element is on the search path
    finished: list[str] = []

    def visit(node: str) -> None:
        done[node] = False
        for target in targets[node]:
            if target not in done:
                visit(target)
            if done[target]:
                forward[node].append(target)
        done[node] = True
        finished.append(node)

    for i in ids:
        if i not in done:
            visit(i)
    layer = dict.fromkeys(ids, 0)
    for node in reversed(finished):  # topological order
        for target in forward[node]:
            layer[target] = max(layer[target], layer[node] + 1)
    return layer


def label_lines(text: str) -> list[str]:
    """An arrow label wrapped to _LABEL_MAX wide lines, at most two (what fits between two
    arrow ends); a longer one is cut with an ellipsis."""
    lines = textwrap.wrap(text, width=int(_LABEL_MAX / _CHAR), max_lines=2, placeholder=" …")
    return lines or [text]


def label_width(text: str) -> int:
    """Estimated width of an arrow label, in px."""
    return round(max(len(line) for line in label_lines(text)) * _CHAR)


def layout(view: C4View) -> Layout:
    column, bounds = _zones(view)
    count = max([*column.values(), *(bounds or ())], default=-1) + 1
    first, last = bounds or (0, 0)
    rels = view.relationships
    nodes = [*view.inner, *view.outer]
    infra = {n.id for n in nodes if n.kind in _INFRA}
    inner_ids = {n.id for n in view.inner}

    # data stores and queues: bottom rows (inside the boundary, and outside it) by column
    inner_row: list[list[str]] = [[] for _ in range(count)]
    outer_row: list[list[str]] = [[] for _ in range(count)]
    for n in nodes:
        if n.id in infra:
            bottom_row = inner_row if bounds and n.id in inner_ids else outer_row
            bottom_row[column[n.id]].append(n.id)

    # flow columns: elements and slots for the arrows skipping columns
    columns: list[list[_Item]] = [[] for _ in range(count)]
    for n in nodes:
        if n.id not in infra:
            columns[column[n.id]].append(n.id)
    chains: dict[int, list[_Item]] = {}  # forward arrow -> the items it goes through
    for i, r in enumerate(rels):
        source_col, target_col = column[r.source_id], column[r.target_id]
        if target_col > source_col and not {r.source_id, r.target_id} & infra:
            slots = [(i, c) for c in range(source_col + 1, target_col)]
            for slot in slots:
                columns[slot[1]].append(slot)
            chains[i] = [r.source_id, *slots, r.target_id]
    links = [pair for chain in chains.values() for pair in pairwise(chain)]
    _order(columns, links)
    descents = [i for i, r in enumerate(rels) if r.target_id in infra]
    back = [i for i in range(len(rels)) if i not in chains and i not in descents]

    # an arrow to a data store/queue goes straight down from the bottom of its source when no
    # element is below the source in its column (arrows passing through slots are only
    # crossed) and no bottom row inside the boundary is in the way; the others go through the
    # corridor on the right
    def straight_down(i: int) -> bool:
        source, target = rels[i].source_id, rels[i].target_id
        if source in infra:
            return False
        col = columns[column[source]]
        below = col[col.index(source) + 1 :]
        in_the_way = bool(inner_row[column[source]]) and target not in inner_ids
        return not in_the_way and not any(isinstance(item, str) for item in below)

    straight = [i for i in descents if straight_down(i)]

    # element heights: room for the arrow ends of its busiest side
    on_right = Counter(r.source_id for i, r in enumerate(rels) if i not in straight)
    on_left = Counter(r.target_id for i, r in enumerate(rels) if i not in descents)
    busiest = {n.id: max(on_right[n.id], on_left[n.id]) for n in nodes}
    height = {n.id: max(HEIGHT, (busiest[n.id] + 1) * _PORT_GAP) for n in nodes}

    # vertical placement: flow columns aligned with their links, then the bands and rows
    def size(item: _Item) -> int:
        return height[item] if isinstance(item, str) else _SLOT

    top = _place(columns, size, links)
    tallest = max((top[i] + size(i) for i in top), default=0)
    inside = [i for c in range(first, last + 1) for i in columns[c]] if bounds else []
    frame_y = min((top[i] for i in inside), default=0) - _PAD

    lane: dict[int, int] = {}
    into_inner = [i for i in descents if rels[i].target_id in inner_ids and bounds]
    into_outer = [i for i in descents if i not in into_inner]
    y = _band(into_inner, tallest, lane, rels, column)
    y = _row(inner_row, y, top, height)
    frame_bottom = max(y, max((top[i] + size(i) for i in inside), default=0)) + _PAD_BOTTOM
    y = _band(into_outer, max(y, frame_bottom if bounds else y), lane, rels, column)
    y = _row(outer_row, y, top, height)
    y = _band(back, y, lane, rels, column)

    def center(item: _Item) -> int:
        return top[item] + size(item) // 2

    # ports on the sides: each arrow end on its own point, ordered by where the arrow goes
    outs: dict[str, list[tuple[int, int]]] = {}
    ins: dict[str, list[tuple[int, int]]] = {}
    for i, r in enumerate(rels):
        chain = chains.get(i)
        if i not in straight:
            outs.setdefault(r.source_id, []).append((center(chain[1]) if chain else lane[i], i))
        if i not in descents:
            ins.setdefault(r.target_id, []).append((center(chain[-2]) if chain else lane[i], i))
    start_y = _spread(outs, top, height)
    end_y = _spread(ins, top, height)

    # vertical runs in each corridor (corridor g is left of column g)
    runs: list[list[_Run]] = [[] for _ in range(count + 1)]
    ys: dict[int, list[int]] = {}
    for i, chain in chains.items():
        ys[i] = [start_y[i], *(center(item) for item in chain[1:-1]), end_y[i]]
        for step, (y1, y2) in enumerate(pairwise(ys[i])):
            if y1 != y2:
                g = column[rels[i].source_id] + step + 1
                runs[g].append(_Run(i, step, min(y1, y2), max(y1, y2), y1, y2))
    for i in [*descents, *back]:
        if i in straight:
            continue
        r, y1, y2 = rels[i], start_y[i], lane[i]
        runs[column[r.source_id] + 1].append(_Run(i, 0, min(y1, y2), max(y1, y2), y1, None))
        if i in back:
            runs[column[r.target_id]].append(_Run(i, 1, end_y[i], lane[i], None, end_y[i]))

    # horizontal placement: columns as wide as their rows, corridors as their tracks need
    def border(g: int) -> int:
        """Room for the boundary line when it lies in corridor g."""
        return _PAD if bounds is not None and g in (first, last + 1) else 0

    # labels start right after the source, in the corridor on its right
    label_room = [_MIN_LABEL_ROOM] * (count + 1)
    for i, r in enumerate(rels):
        if i not in straight:
            g = column[r.source_id] + 1
            label_room[g] = max(label_room[g], label_width(r.description) + _LABEL_GAP)
    col_w = [max(WIDTH, _row_width(len(inner_row[c])), _row_width(len(outer_row[c])))
             for c in range(count)]  # fmt: skip
    col_x: list[int] = []
    x = 0
    for g in range(count):
        tracks = len(runs[g])
        extra = label_room[g] + (tracks - 1) * _TRACK + _MARGIN if tracks else 0
        if g and not tracks:
            extra = max(_MIN_CORRIDOR, label_room[g] + _MARGIN)
        x += border(g) + extra
        col_x.append(x)
        x += col_w[g]
    track: dict[tuple[int, int], int] = {}
    for g, corridor in enumerate(runs):
        start = col_x[g - 1] + col_w[g - 1] if g else 0
        start += _PAD if border(g) and g != first else 0
        for k, run in enumerate(_tracks(corridor)):
            track[(run.arrow, run.step)] = start + label_room[g] + k * _TRACK

    rects: dict[str, Rect] = {}
    for c in range(count):
        for n_id in columns[c]:
            if isinstance(n_id, str):
                x = col_x[c] + (col_w[c] - WIDTH) // 2
                rects[n_id] = Rect(x, top[n_id], WIDTH, height[n_id])
        for ids in (inner_row[c], outer_row[c]):
            left = col_x[c] + (col_w[c] - _row_width(len(ids))) // 2
            for k, n_id in enumerate(ids):
                x = left + k * (WIDTH + _SIDE_BY_SIDE)
                rects[n_id] = Rect(x, top[n_id], WIDTH, height[n_id])

    # ports on the bottom of sources going straight down, ordered by where they go, and on the
    # top of data stores/queues, ordered by where the arrow comes from; a drop steps aside from
    # the exits (and other drops) so their vertical lines never look like one
    exits: dict[str, list[tuple[int, int]]] = {}
    for i in straight:
        target = rects[rels[i].target_id]
        exits.setdefault(rels[i].source_id, []).append((target.x + target.width // 2, i))
    exit_x = _along(exits, rects)
    drops: dict[str, list[tuple[int, int]]] = {}
    for i in descents:
        arrival = exit_x[i] if i in straight else track[(i, 0)]
        drops.setdefault(rels[i].target_id, []).append((arrival, i))
    drop_x: dict[int, int] = {}
    for i, x in _along(drops, rects).items():
        store = rects[rels[i].target_id]
        taken = [e for j, e in exit_x.items() if j != i] + list(drop_x.values())
        wanted = exit_x.get(i, x)  # straight below its own exit, when there is room
        low, high = store.x + _NEAR, store.x + store.width - _NEAR
        drop_x[i] = _clear(wanted if low <= wanted <= high else x, taken, low, high)

    arrows = []
    for i, r in enumerate(rels):
        source, target = rects[r.source_id], rects[r.target_id]
        if i in straight:
            points = [(exit_x[i], source.y + source.height), (exit_x[i], lane[i])]
            points += [(drop_x[i], lane[i]), (drop_x[i], target.y)]
            arrows.append(Arrow(relationship=r, points=_simplify(points)))
            continue
        points = [(source.x + source.width, start_y[i])]
        if i in chains:
            for step, (y1, y2) in enumerate(pairwise(ys[i])):
                if y1 != y2:
                    points += [(track[(i, step)], y1), (track[(i, step)], y2)]
            points.append((target.x, end_y[i]))
        elif i in descents:
            down = track[(i, 0)]
            points += [(down, start_y[i]), (down, lane[i]), (drop_x[i], lane[i])]
            points.append((drop_x[i], target.y))
        else:
            down, up = track[(i, 0)], track[(i, 1)]
            points += [(down, start_y[i]), (down, lane[i]), (up, lane[i]), (up, end_y[i])]
            points.append((target.x, end_y[i]))
        arrows.append(Arrow(relationship=r, points=_simplify(points)))

    boxes = {n.id: Box(node=n, rect=rects[n.id]) for n in nodes}
    frame = None
    if bounds is not None:
        left, right = col_x[first] - _PAD, col_x[last] + col_w[last] + _PAD
        frame = Rect(left, frame_y, right - left, frame_bottom - frame_y)
    if frame is None or not view.platform:
        return Layout(boxes=boxes, frame=frame, arrows=arrows)
    return _with_platform(Layout(boxes=boxes, frame=frame, arrows=arrows), view.platform, y)


def _with_platform(lay: Layout, platform: list[Node], below: int) -> Layout:
    """The group of platform services below everything (y >= below), in a row starting at the
    boundary's left edge, and the straight link down the boundary's left margin."""
    assert lay.frame is not None
    frame, top = lay.frame, below + _PAD
    row = len(platform) * (_PLATFORM_WIDTH + _PLATFORM_GAP) - _PLATFORM_GAP
    group = Rect(frame.x, top, row + 2 * _PAD, _PLATFORM_TITLE + _PLATFORM_HEIGHT + _PAD)
    boxes = {
        n.id: Box(node=n, rect=Rect(frame.x + _PAD + k * (_PLATFORM_WIDTH + _PLATFORM_GAP),
                                    top + _PLATFORM_TITLE, _PLATFORM_WIDTH, _PLATFORM_HEIGHT))
        for k, n in enumerate(platform)
    }  # fmt: skip
    x = frame.x + _PAD // 2
    link = ((x, frame.y + frame.height), (x, top))
    return Layout(boxes=lay.boxes, frame=frame, arrows=lay.arrows, platform=group,
                  platform_boxes=boxes, platform_link=link)  # fmt: skip


def _zones(view: C4View) -> tuple[dict[str, int], tuple[int, int] | None]:
    """Column of each element (for a data store or queue: the column it sits under) and, in a
    zoomed-in view, the first and last columns inside the boundary."""
    edges = [(r.source_id, r.target_id) for r in view.relationships]
    infra = {n.id for n in [*view.inner, *view.outer] if n.kind in _INFRA}
    bounds: tuple[int, int] | None = None
    if view.boundary is None:
        flow = [n.id for n in view.outer if n.id not in infra]
        externals = {n.id for n in view.outer if n.kind is NodeKind.EXTERNAL_SYSTEM}
        column = layers([i for i in flow if i not in externals], edges)
        rightmost = max(column.values(), default=-1) + 1
        column |= dict.fromkeys(sorted(externals, key=flow.index), rightmost)
    else:
        inside = {n.id for n in view.inner}
        inner = layers([n.id for n in view.inner if n.id not in infra], edges)
        called = {t for s, t in edges if s in inside}
        callers = {s for s, t in edges if t in inside} - called - inside - infra
        offset = 1 if callers else 0
        bounds = (offset, offset + max(inner.values(), default=0))
        column = {i: offset + c for i, c in inner.items()}
        column |= {
            n.id: 0 if n.id in callers else bounds[1] + 1 for n in view.outer if n.id not in infra
        }
    # a data store/queue goes under one of the columns of its users: the one with the fewest
    # data stores/queues so far, then the closest to the middle of the users
    taken: Counter[int] = Counter()
    for n in [*view.inner, *view.outer]:
        if n.id in infra:
            users = sorted(column[o] for s, t in edges for o, end in ((s, t), (t, s))
                           if end == n.id and o in column)  # fmt: skip
            if bounds and n in view.inner:
                users = [min(max(c, bounds[0]), bounds[1]) for c in users]
            if not users:
                users = [(bounds or (0, 0))[0]]
            middle = users[(len(users) - 1) // 2]
            home = min(set(users), key=lambda c: (taken[c], abs(c - middle), c))
            taken[home] += 1
            column[n.id] = home
    return column, bounds


def _band(arrows: list[int], y: int, lane: dict[int, int], rels: Sequence[ViewRelationship],
          column: dict[str, int]) -> int:  # fmt: skip
    """Give each arrow its own lane in a band starting at y; returns where the band ends."""
    ordered = sorted(
        arrows, key=lambda i: (column[rels[i].target_id], column[rels[i].source_id], i)
    )
    for k, i in enumerate(ordered):
        lane[i] = y + _PAD + k * _LANE
    return y + 2 * _PAD + (len(arrows) - 1) * _LANE if arrows else y


def _row(row: list[list[str]], y: int, top: dict[_Item, int], height: dict[str, int]) -> int:
    """Place a row of data stores/queues at y (below a gap); returns where it ends."""
    if not any(row):
        return y
    for ids in row:
        for i in ids:
            top[i] = y + _V_GAP
    return y + _V_GAP + max(height[i] for ids in row for i in ids)


def _row_width(count: int) -> int:
    return count * WIDTH + (count - 1) * _SIDE_BY_SIDE if count else 0


def _order(columns: list[list[_Item]], links: list[tuple[_Item, _Item]]) -> None:
    """Reorder each column by the mean position of its neighbours in the adjacent column
    (barycenter heuristic), sweeping right then left, to reduce crossings."""
    before: dict[_Item, list[_Item]] = {}
    after: dict[_Item, list[_Item]] = {}
    for a, b in links:
        after.setdefault(a, []).append(b)
        before.setdefault(b, []).append(a)
    for _ in range(4):
        for c in range(1, len(columns)):
            _sort_by_neighbours(columns[c], columns[c - 1], before)
        for c in range(len(columns) - 2, -1, -1):
            _sort_by_neighbours(columns[c], columns[c + 1], after)


def _place(
    columns: list[list[_Item]], size: Callable[[_Item], int], links: list[tuple[_Item, _Item]]
) -> dict[_Item, int]:
    """Top of each item: each one pulled to the mean height of the items it links to (so the
    arrows between them run straight), keeping the order and gaps of its column; a last sweep
    aligns each item with what comes from its left, so those arrows end up exactly straight."""
    neighbours: dict[_Item, list[_Item]] = {}
    before: dict[_Item, list[_Item]] = {}
    for a, b in links:
        neighbours.setdefault(a, []).append(b)
        neighbours.setdefault(b, []).append(a)
        before.setdefault(b, []).append(a)
    top: dict[_Item, int] = {}
    for col in columns:  # start stacked
        y = 0
        for item in col:
            top[item] = y
            y += size(item) + _V_GAP
    sweeps = [(col, neighbours) for _ in range(4) for col in [*columns, *reversed(columns)]]
    for col, pulls in [*sweeps, *((col, before) for col in columns)]:
        want = []
        for item in col:
            found = pulls.get(item, [])
            middle = [top[n] + size(n) / 2 for n in found] or [top[item] + size(item) / 2]
            want.append(round(sum(middle) / len(middle) - size(item) / 2))
        top.update(zip(col, _fit(col, want, size), strict=True))
    shift = min(top.values(), default=0)
    return {item: y - shift for item, y in top.items()}


def _fit(col: list[_Item], want: list[int], size: Callable[[_Item], int]) -> list[int]:
    """Tops as close to the wanted ones as the order and gaps of the column allow: the mean of
    the placement packed from the top and the one packed from the bottom (both keep the gaps,
    so their mean does too)."""
    down, up = list(want), list(want)
    for k in range(1, len(col)):
        down[k] = max(want[k], down[k - 1] + size(col[k - 1]) + _V_GAP)
    for k in range(len(col) - 2, -1, -1):
        up[k] = min(want[k], up[k + 1] - size(col[k]) - _V_GAP)
    return [(d + u) // 2 for d, u in zip(down, up, strict=True)]


def _sort_by_neighbours(
    column: list[_Item], other: list[_Item], neighbours: dict[_Item, list[_Item]]
) -> None:
    index = {item: i for i, item in enumerate(other)}

    def key(position: int, item: _Item) -> float:
        found = [index[n] for n in neighbours.get(item, []) if n in index]
        return sum(found) / len(found) if found else position

    ranked = sorted(enumerate(column), key=lambda p: (key(*p), p[0]))
    column[:] = [item for _, item in ranked]


def _spread(
    ends: dict[str, list[tuple[int, int]]], top: dict[_Item, int], height: dict[str, int]
) -> dict[int, int]:
    """Height of each arrow end on its element's side, evenly spread in the given order."""
    heights: dict[int, int] = {}
    for node_id, arrows in ends.items():
        for k, (_, i) in enumerate(sorted(arrows)):
            heights[i] = top[node_id] + height[node_id] * (k + 1) // (len(arrows) + 1)
    return heights


def _along(ends: dict[str, list[tuple[int, int]]], rects: dict[str, Rect]) -> dict[int, int]:
    """x of each arrow end along its element's top or bottom, evenly spread in the given
    order."""
    xs: dict[int, int] = {}
    for node_id, arrows in ends.items():
        r = rects[node_id]
        for k, (_, i) in enumerate(sorted(arrows)):
            xs[i] = r.x + r.width * (k + 1) // (len(arrows) + 1)
    return xs


def _clear(x: int, taken: list[int], low: int, high: int) -> int:
    """The x closest to the given one, within [low, high], at least _TRACK from the taken ones
    (the given one if there is none)."""
    for step in range(high - low):
        for candidate in (x + step, x - step):
            if low <= candidate <= high and all(abs(candidate - t) >= _TRACK for t in taken):
                return candidate
    return x


def _near(a: int | None, b: int | None) -> bool:
    return a is not None and b is not None and abs(a - b) < _NEAR


def _tracks(runs: list[_Run]) -> list[_Run]:
    """Left-to-right order of the runs of a corridor. A run whose horizontal from the left
    column is at (about) the height of another's horizontal into the right column must come
    first, or those horizontals would run over each other."""
    pending = sorted(runs, key=lambda r: (r.top, r.bottom, r.arrow, r.step))
    ordered: list[_Run] = []
    while pending:
        free = [
            r for r in pending if not any(o is not r and _near(o.left, r.right) for o in pending)
        ]
        run = (free or pending)[0]  # a cycle of such constraints is broken arbitrarily
        ordered.append(run)
        pending.remove(run)
    return ordered


def _simplify(points: list[Point]) -> tuple[Point, ...]:
    """Drop repeated points and the middle one of three aligned points."""
    kept: list[Point] = []
    for point in points:
        if kept and kept[-1] == point:
            continue
        if len(kept) >= 2 and (
            kept[-2][0] == kept[-1][0] == point[0] or kept[-2][1] == kept[-1][1] == point[1]
        ):
            kept[-1] = point
        else:
            kept.append(point)
    return tuple(kept)
