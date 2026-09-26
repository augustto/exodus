from itertools import combinations, pairwise

import pytest

from exodus.domain.model import Node, NodeKind
from exodus.domain.views import (
    C4View,
    ViewRelationship,
)
from exodus.infrastructure.rendering.layout import (
    Layout,
    Point,
    label_lines,
    label_width,
    layers,
    layout,
)
from tests.unit.infrastructure.helpers import ev

Segment = tuple[Point, Point]


def node(name: str, kind: NodeKind = NodeKind.SYSTEM) -> Node:
    return Node(id=name, kind=kind, name=name, evidence=(ev(1),))


def rel(source: str, target: str, description: str = "calls") -> ViewRelationship:
    return ViewRelationship(
        source_id=source, target_id=target, description=description, evidence=(ev(9),)
    )


def context(edges: list[tuple[str, str]], names: str) -> C4View:
    return C4View(
        key="context",
        title="t",
        boundary=None,
        inner=[],
        outer=[node(n) for n in names],
        relationships=[rel(s, t) for s, t in edges],
    )


INFRA = (NodeKind.DATA_STORE, NodeKind.QUEUE)


def tangled_context() -> C4View:
    """Long arrows skipping columns, a cycle, a fan-out, a fan-in, an external system called
    from several columns and shared data stores/queues, two of them under the same column."""
    outer = [node(n) for n in "abcdef"]
    outer += [node("x", NodeKind.EXTERNAL_SYSTEM), node("db1", NodeKind.DATA_STORE),
              node("db2", NodeKind.DATA_STORE), node("q", NodeKind.QUEUE)]  # fmt: skip
    edges = [("a", "b"), ("b", "c"), ("c", "d"), ("a", "d"), ("a", "c"), ("d", "a"),
             ("e", "b"), ("e", "d"), ("b", "f"), ("f", "d"), ("c", "b"), ("a", "x"),
             ("d", "x"), ("b", "db1"), ("c", "db1"), ("b", "db2"), ("a", "q"),
             ("d", "q")]  # fmt: skip
    return C4View(
        key="context",
        title="t",
        boundary=None,
        inner=[],
        outer=outer,
        relationships=[rel(s, t) for s, t in edges],
    )


def tangled_container_view() -> C4View:
    """A caller, inner containers in several columns, own data stores/queues (two under the
    same column), a shared data store and outer elements that are both called and calling
    back into the boundary."""
    inner = [node(n, NodeKind.CONTAINER) for n in ("web", "api", "worker", "core")]
    inner += [node("own", NodeKind.DATA_STORE), node("cache", NodeKind.DATA_STORE),
              node("jobs", NodeKind.QUEUE)]  # fmt: skip
    outer = [node("caller"), node("db", NodeKind.DATA_STORE), node("peer"),
             node("ext", NodeKind.EXTERNAL_SYSTEM)]  # fmt: skip
    edges = [("caller", "web"), ("web", "api"), ("api", "worker"), ("worker", "core"),
             ("web", "core"), ("web", "db"), ("core", "db"), ("api", "peer"),
             ("peer", "api"), ("peer", "worker"), ("web", "ext"), ("api", "own"),
             ("worker", "own"), ("api", "cache"), ("api", "jobs"), ("worker", "jobs")]  # fmt: skip
    return C4View(
        key="s",
        title="t",
        boundary=node("system"),
        inner=inner,
        outer=outer,
        relationships=[rel(s, t) for s, t in edges],
    )


def all_views() -> list[C4View]:
    return [tangled_context(), tangled_container_view()]


def segments(points: tuple[Point, ...]) -> list[Segment]:
    return list(pairwise(points))


def crosses_interior(segment: Segment, lay: Layout, box_id: str) -> bool:
    r = lay.boxes[box_id].rect
    (x1, y1), (x2, y2) = segment
    return (
        min(x1, x2) < r.x + r.width
        and max(x1, x2) > r.x
        and min(y1, y2) < r.y + r.height
        and max(y1, y2) > r.y
    )


def overlap(a: Segment, b: Segment, apart: int = 8) -> bool:
    """Parallel segments closer than `apart` along a common stretch: they would look like one
    line (collinear ones sharing more than a point included)."""
    (ax1, ay1), (ax2, ay2) = a
    (bx1, by1), (bx2, by2) = b
    if ax1 == ax2 and bx1 == bx2 and abs(ax1 - bx1) < apart:
        return min(max(ay1, ay2), max(by1, by2)) > max(min(ay1, ay2), min(by1, by2))
    if ay1 == ay2 and by1 == by2 and abs(ay1 - by1) < apart:
        return min(max(ax1, ax2), max(bx1, bx2)) > max(min(ax1, ax2), min(bx1, bx2))
    return False


def test_layers_put_callers_first_and_ignore_edges_closing_a_cycle() -> None:
    edges = [("a", "b"), ("b", "c"), ("a", "c"), ("c", "a"), ("d", "d"), ("x", "outside")]
    assert layers(["a", "b", "c", "d"], edges) == {"a": 0, "b": 1, "c": 2, "d": 0}


@pytest.mark.parametrize("view", all_views(), ids=lambda v: f"{v.key}-{len(v.relationships)}")
def test_arrows_are_orthogonal_and_use_the_right_sides_of_their_ends(
    view: C4View,
) -> None:
    lay = layout(view)
    assert len(lay.arrows) == len(view.relationships)
    for arrow in lay.arrows:
        source = lay.boxes[arrow.relationship.source_id].rect
        target = lay.boxes[arrow.relationship.target_id].rect
        (sx, sy), (tx, ty) = arrow.points[0], arrow.points[-1]
        if lay.boxes[arrow.relationship.target_id].node.kind in INFRA:
            # enters from the top; may leave from the bottom, going straight down
            assert ty == target.y and target.x < tx < target.x + target.width
            on_bottom = sy == source.y + source.height and source.x < sx < source.x + source.width
        else:
            assert tx == target.x and target.y < ty < target.y + target.height
            on_bottom = False
        on_right = sx == source.x + source.width and source.y < sy < source.y + source.height
        assert on_right or on_bottom, arrow.points
        for (x1, y1), (x2, y2) in segments(arrow.points):
            assert x1 == x2 or y1 == y2, arrow.points


@pytest.mark.parametrize("view", all_views(), ids=lambda v: f"{v.key}-{len(v.relationships)}")
def test_no_arrow_crosses_a_box_or_runs_over_another_arrow(view: C4View) -> None:
    lay = layout(view)
    for arrow in lay.arrows:
        for segment in segments(arrow.points):
            for box_id in lay.boxes:
                assert not crosses_interior(segment, lay, box_id), (arrow, box_id)
    for a, b in combinations(lay.arrows, 2):
        for sa in segments(a.points):
            for sb in segments(b.points):
                assert not overlap(sa, sb), (a.relationship, b.relationship, sa, sb)


@pytest.mark.parametrize("view", all_views(), ids=lambda v: f"{v.key}-{len(v.relationships)}")
def test_boxes_do_not_overlap(view: C4View) -> None:
    lay = layout(view)
    for a, b in combinations(lay.boxes.values(), 2):
        ra, rb = a.rect, b.rect
        apart = ra.x + ra.width <= rb.x or rb.x + rb.width <= ra.x
        apart = apart or ra.y + ra.height <= rb.y or rb.y + rb.height <= ra.y
        assert apart, (a.node.id, b.node.id)


def test_context_zones_externals_right_and_data_stores_and_queues_below() -> None:
    lay = layout(tangled_context())
    flow = [b.rect for b in lay.boxes.values() if b.node.kind is NodeKind.SYSTEM]
    external = lay.boxes["x"].rect
    assert all(external.x > r.x + r.width for r in flow)
    lowest = max(r.y + r.height for r in flow)
    for infra in ("db1", "db2", "q"):
        assert lay.boxes[infra].rect.y > lowest
    assert lay.boxes["db1"].rect.y == lay.boxes["db2"].rect.y  # one row, side by side


def test_boundary_frames_inner_elements_with_callers_left_and_the_rest_right() -> None:
    lay = layout(tangled_container_view())
    frame = lay.frame
    assert frame is not None
    view = tangled_container_view()
    inner_ids = {n.id for n in view.inner}
    for box in lay.boxes.values():
        r = box.rect
        inside = frame.x < r.x and r.x + r.width < frame.x + frame.width
        inside = inside and frame.y < r.y and r.y + r.height < frame.y + frame.height
        assert inside == (box.node.id in inner_ids), box.node.id
    assert lay.boxes["caller"].rect.x + lay.boxes["caller"].rect.width < frame.x
    for right in ("peer", "ext"):
        assert lay.boxes[right].rect.x > frame.x + frame.width
    # own data stores/queues: bottom row inside the boundary; shared one: below the boundary
    containers = [lay.boxes[n].rect for n in ("web", "api", "worker", "core")]
    lowest = max(r.y + r.height for r in containers)
    own = [lay.boxes[n].rect for n in ("own", "cache", "jobs")]
    assert all(r.y > lowest for r in own) and len({r.y for r in own}) == 1
    assert lay.boxes["db"].rect.y > frame.y + frame.height


def test_ports_keep_a_minimum_distance_and_the_box_grows_to_fit_them() -> None:
    fan_out = context([("a", t) for t in "bcdefgh"], "abcdefgh")
    lay = layout(fan_out)
    starts = sorted(a.points[0][1] for a in lay.arrows)
    assert all(b - a >= 28 for a, b in pairwise(starts))
    assert lay.boxes["a"].rect.height > lay.boxes["b"].rect.height == 120


def test_corridors_fit_the_labels_and_long_labels_wrap() -> None:
    long = "project reference, calls (SOAP), publishes, reads/writes and more"
    view = C4View(
        key="context", title="t", boundary=None, inner=[], outer=[node("a"), node("b"), node("c")],
        relationships=[rel("a", "b", long), rel("a", "c", "calls (SOAP)")],
    )  # fmt: skip
    lay = layout(view)
    assert len(label_lines(long)) == 2
    assert len(label_lines(long * 3)) == 2 and label_lines(long * 3)[-1].endswith("…")
    for arrow in lay.arrows:
        start_x = arrow.points[0][0]
        first_turn = next((x for x, _ in arrow.points[1:] if x != start_x), arrow.points[-1][0])
        assert first_turn - start_x >= label_width(arrow.relationship.description)
