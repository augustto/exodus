"""C4 diagrams as one draw.io file with a page per view: L1 (context), L2 (containers of each
system) and L3 (components of each core container).

Elements and arrow routes come from `layout` (no arrow crosses an element); each arrow carries
its waypoints and exact exit/entry points, so draw.io only draws them. Every element and
relationship carries its evidence as data (Edit Data) and as tooltip. Each page also gets its
title on top and a legend, on the right, of the kinds of element it shows (presentation only:
they are not part of the graph, so they carry no evidence).
"""

import html
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Sequence
from typing import Protocol

from exodus.application.ports import Document
from exodus.domain.graph import ArchitectureGraph
from exodus.domain.model import Evidence, Node, NodeKind
from exodus.domain.views import C4View, component_views, container_views, system_context
from exodus.infrastructure.rendering.aws_icons import C4_COLOURS, INK
from exodus.infrastructure.rendering.common import evidence_summary
from exodus.infrastructure.rendering.layout import (
    LABEL_FONT,
    Arrow,
    Box,
    Layout,
    Rect,
    label_lines,
    label_width,
    layout,
)

_KINDS = {NodeKind.SYSTEM: "Software System", NodeKind.CONTAINER: "Container",
          NodeKind.COMPONENT: "Component", NodeKind.DATA_STORE: "Database",
          NodeKind.QUEUE: "Queue", NodeKind.EXTERNAL_SYSTEM: "External System",
          NodeKind.PLATFORM: "Platform service"}  # fmt: skip
_TEXT = "html=1;whiteSpace=wrap;"
_BOX = "rounded=1;arcSize=6;"
_CYLINDER = "shape=cylinder3;size=15;boundedLbl=1;"
_SHAPES = {NodeKind.DATA_STORE: _CYLINDER, NodeKind.QUEUE: _CYLINDER + "direction=south;"}
# the AWS look of the TO-BE: white element, border in its category colour
_STYLES = {
    kind: _SHAPES.get(kind, _BOX)
    + f"fillColor=#ffffff;strokeColor={colour};strokeWidth=2;fontColor={INK};"
    for kind, colour in C4_COLOURS.items()
}
_BOUNDARY = (
    "rounded=1;arcSize=2;dashed=1;dashPattern=8 4;strokeWidth=2;fillColor=none;"
    "strokeColor=#444444;fontColor=#444444;container=1;collapsible=0;align=left;verticalAlign=bottom;"
    "spacingLeft=10;spacingBottom=6;"
)
_EDGE = (
    "rounded=1;dashed=1;endArrow=blockThin;endFill=1;strokeColor=#707070;fontColor=#404040;"
    f"fontSize={LABEL_FONT};labelBackgroundColor=#ffffff;"
)
_PLATFORM_GROUP = (
    "rounded=1;arcSize=4;dashed=1;dashPattern=8 4;strokeWidth=2;fillColor=#f5f7fa;"
    "strokeColor=#5d6d7e;fontColor=#5d6d7e;fontStyle=1;container=1;collapsible=0;align=left;verticalAlign=top;"
    "spacingLeft=10;spacingTop=4;"
)
_TITLE = "text;html=1;fontSize=18;fontStyle=1;align=left;verticalAlign=middle;"
_LEGEND_TITLE = "text;html=1;fontSize=13;fontStyle=1;align=left;verticalAlign=middle;"
_SPACE = 60  # between the diagram and its title / legend
ICON, ICON_PAD = 48, 10  # an element's icon (TO-BE) and its distance to the element's border


class Look(Protocol):
    """How elements are drawn: C4 shapes (AS-IS) or AWS service icons (TO-BE)."""

    platform_title: str

    def style(self, node: Node) -> str: ...

    def label(self, node: Node) -> str: ...

    def icon(self, node: Node) -> str | None:
        """Style of an icon drawn at the left of the element, or None."""
        ...

    def legend(self, nodes: Iterable[Node]) -> list[tuple[str, str, str]]:
        """(key, text, style) of each kind of element shown, in display order."""
        ...


class C4Look:
    platform_title = "Platform"

    def style(self, node: Node) -> str:
        return _STYLES[node.kind]

    def label(self, node: Node) -> str:
        description = node.description.text if node.description else None
        return _label(node.name, node.kind, node.technology, description)

    def icon(self, node: Node) -> str | None:
        return None

    def legend(self, nodes: Iterable[Node]) -> list[tuple[str, str, str]]:
        shown = {node.kind for node in nodes}
        return [(kind.value, _KINDS[kind], _STYLES[kind]) for kind in _KINDS if kind in shown]


class DrawioRenderer:
    def render(self, graph: ArchitectureGraph) -> list[Document]:
        pages = [("context", system_context(graph))]
        pages += [(f"container-{v.key}", v) for v in container_views(graph)]
        pages += [(f"component-{v.key}", v) for v in component_views(graph)]
        return [Document(name="as-is/c4.drawio", content=drawio_file(pages, C4Look()))]


def drawio_file(pages: Sequence[tuple[str, C4View]], look: Look) -> str:
    """A draw.io file with one page per (page id, view)."""
    mxfile = ET.Element("mxfile", host="Exodus")
    for page_id, view in pages:
        diagram = ET.SubElement(mxfile, "diagram", id=page_id, name=view.title)
        diagram.append(_page(layout(view), view, look))
    ET.indent(mxfile)
    return ET.tostring(mxfile, "unicode") + "\n"


def _page(lay: Layout, view: C4View, look: Look) -> ET.Element:
    boundary = view.boundary
    model = ET.Element(
        "mxGraphModel", grid="1", gridSize="10", guides="1", arrows="1", connect="1", page="0"
    )
    root = ET.SubElement(model, "root")
    ET.SubElement(root, "mxCell", id="0")
    ET.SubElement(root, "mxCell", {"id": "1", "parent": "0"})
    frame_id, origin = "1", (0, 0)
    if boundary is not None and lay.frame is not None:
        frame_id, origin = "boundary:" + boundary.id, (lay.frame.x, lay.frame.y)
        frame = _object(root, frame_id, _label(boundary.name, boundary.kind), boundary.evidence)
        cell = ET.SubElement(frame, "mxCell", {"parent": "1"}, style=_BOUNDARY + _TEXT, vertex="1")
        _geometry(cell, lay.frame)
    for box in lay.boxes.values():
        inside = lay.frame is not None and _contains(lay.frame, box.rect)
        _vertex(root, box, frame_id if inside else "1", origin if inside else (0, 0), look)
    for arrow in lay.arrows:
        _edge(root, arrow, lay)
    if lay.platform is not None and lay.frame is not None:
        _platform(root, lay, frame_id, view, look)
    bounds = _bounds(lay)
    title = Rect(bounds.x, bounds.y - _SPACE, max(400, bounds.width), 30)
    _text(root, "title", view.title, _TITLE, title)
    _legend(root, lay, bounds.x + bounds.width + _SPACE, bounds.y, look)
    return model


def _platform(root: ET.Element, lay: Layout, frame_id: str, view: C4View, look: Look) -> None:
    """The group of platform services and its single link from the boundary."""
    assert lay.platform is not None and lay.frame is not None
    group, frame = lay.platform, lay.frame
    cell = ET.SubElement(
        root, "mxCell", {"id": "platform", "parent": "1"}, value=html.escape(look.platform_title),
        style=_PLATFORM_GROUP + _TEXT, vertex="1",
    )  # fmt: skip
    _geometry(cell, group)
    for box in lay.platform_boxes.values():
        _vertex(root, box, "platform", (group.x, group.y), look)
    (x, _), _ = lay.platform_link
    link = _object(root, f"{frame_id}->platform", "uses", view.platform_evidence)
    ends = (
        f"exitX={(x - frame.x) / frame.width:.4g};exitY=1;exitPerimeter=0;"
        f"entryX={(x - group.x) / group.width:.4g};entryY=0;entryPerimeter=0;"
    )
    edge = ET.SubElement(
        link, "mxCell", {"parent": "1"}, style=_EDGE + ends + _TEXT, edge="1",
        source=frame_id, target="platform",
    )  # fmt: skip
    ET.SubElement(edge, "mxGeometry", relative="1", attrib={"as": "geometry"})


def _legend(root: ET.Element, lay: Layout, x: int, y: int, look: Look) -> None:
    """The kinds of element on the page and the relationship line."""
    _text(root, "legend", "Legend", _LEGEND_TITLE, Rect(x, y, 160, 24))
    shown = [box.node for box in [*lay.boxes.values(), *lay.platform_boxes.values()]]
    y += 34
    for key, text, style in look.legend(shown):
        cell = ET.SubElement(
            root, "mxCell", {"id": f"legend:{key}", "parent": "1"},
            value=html.escape(text), style=style + _TEXT + "fontSize=11;", vertex="1",
        )  # fmt: skip
        _geometry(cell, Rect(x, y, 160, 44))
        y += 56
    if lay.arrows:
        cell = ET.SubElement(
            root, "mxCell", {"id": "legend:relationship", "parent": "1"},
            value="relationship", style=_EDGE + _TEXT, edge="1",
        )  # fmt: skip
        geometry = ET.SubElement(cell, "mxGeometry", relative="1", attrib={"as": "geometry"})
        middle = y + 16
        ET.SubElement(geometry, "mxPoint", x=str(x), y=str(middle), attrib={"as": "sourcePoint"})
        target = {"as": "targetPoint"}
        ET.SubElement(geometry, "mxPoint", x=str(x + 160), y=str(middle), attrib=target)


def _text(root: ET.Element, cell_id: str, text: str, style: str, rect: Rect) -> None:
    cell = ET.SubElement(
        root, "mxCell", {"id": cell_id, "parent": "1"}, value=html.escape(text), style=style,
        vertex="1",
    )  # fmt: skip
    _geometry(cell, rect)


def _bounds(lay: Layout) -> Rect:
    """What the diagram takes on the page: elements, boundary and arrows."""
    rects = [box.rect for box in lay.boxes.values()] + ([lay.frame] if lay.frame else [])
    rects += [lay.platform] if lay.platform else []
    points = [p for arrow in lay.arrows for p in arrow.points]
    xs = [r.x for r in rects] + [x for x, _ in points]
    ys = [r.y for r in rects] + [y for _, y in points]
    right = max([r.x + r.width for r in rects] + [x for x, _ in points], default=0)
    bottom = max([r.y + r.height for r in rects] + [y for _, y in points], default=0)
    left, top = min(xs, default=0), min(ys, default=0)
    return Rect(left, top, right - left, bottom - top)


def _vertex(root: ET.Element, box: Box, parent: str, origin: tuple[int, int], look: Look) -> None:
    node = box.node
    obj = _object(root, node.id, look.label(node), node.evidence)
    if node.description:  # inferred: why, with its confidence, before the evidence
        why = f"Inferred ({node.description.confidence:.0%}): {node.description.text}"
        obj.set("tooltip", f"{why}\n{obj.attrib['tooltip']}")
    cell = ET.SubElement(obj, "mxCell", {"parent": parent}, style=look.style(node) + _TEXT,
                         vertex="1")  # fmt: skip
    r = box.rect
    _geometry(cell, Rect(r.x - origin[0], r.y - origin[1], r.width, r.height))
    icon = look.icon(node)
    if icon is not None:  # inside the element, vertically centred on its left side
        size = min(ICON, r.height - 2 * ICON_PAD)
        cell = ET.SubElement(
            root, "mxCell", {"id": f"{node.id}:icon", "parent": node.id}, style=icon,
            vertex="1",
        )  # fmt: skip
        _geometry(cell, Rect(ICON_PAD, (r.height - size) // 2, size, size))


def _edge(root: ET.Element, arrow: Arrow, lay: Layout) -> None:
    r = arrow.relationship
    source, target = lay.boxes[r.source_id].rect, lay.boxes[r.target_id].rect
    (start_x, start_y), (end_x, end_y) = arrow.points[0], arrow.points[-1]
    exit_x, exit_y = (start_x - source.x) / source.width, (start_y - source.y) / source.height
    entry_x, entry_y = (end_x - target.x) / target.width, (end_y - target.y) / target.height
    ends = (
        f"exitX={exit_x:.4g};exitY={exit_y:.4g};exitPerimeter=0;"
        f"entryX={entry_x:.4g};entryY={entry_y:.4g};entryPerimeter=0;"
    )
    lines = label_lines(r.description)
    label = "<br>".join(html.escape(line) for line in lines)
    edge = _object(root, f"{r.source_id}->{r.target_id}", label, r.evidence)
    both = "startArrow=blockThin;startFill=1;" if r.both_ways else ""
    edge.set("tooltip", f"{r.description}\n{edge.attrib['tooltip']}")  # full text on hover
    cell = ET.SubElement(
        edge, "mxCell", {"parent": "1"}, style=_EDGE + ends + _TEXT + both, edge="1",
        source=r.source_id, target=r.target_id,
    )  # fmt: skip
    # label just after the source (x=-1 is the source end): above an arrow leaving from the
    # side, beside one leaving from the bottom
    geometry = ET.SubElement(cell, "mxGeometry", x="-1", relative="1", attrib={"as": "geometry"})
    half, extra = label_width(r.description) // 2, 7 * (len(lines) - 1)
    offset = (half + 6, 14 + extra) if exit_y == 1 else (half + 8, -10 - extra)
    ET.SubElement(geometry, "mxPoint", x=str(offset[0]), y=str(offset[1]), attrib={"as": "offset"})
    waypoints = ET.SubElement(geometry, "Array", attrib={"as": "points"})
    for x, y in arrow.points[1:-1]:
        ET.SubElement(waypoints, "mxPoint", x=str(x), y=str(y))


def _contains(frame: Rect, rect: Rect) -> bool:
    inside_x = frame.x < rect.x and rect.x + rect.width < frame.x + frame.width
    return inside_x and frame.y < rect.y and rect.y + rect.height < frame.y + frame.height


def _geometry(cell: ET.Element, rect: Rect) -> None:
    ET.SubElement(
        cell, "mxGeometry", x=str(rect.x), y=str(rect.y), width=str(rect.width),
        height=str(rect.height), attrib={"as": "geometry"},
    )  # fmt: skip


def _object(root: ET.Element, cell_id: str, label: str, evidence: Sequence[Evidence]) -> ET.Element:
    return ET.SubElement(
        root, "object", id=cell_id, label=label,
        tooltip=f"Evidence: {evidence_summary(evidence)}",
        evidence="\n".join(str(e) for e in evidence),
    )  # fmt: skip


def _label(
    name: str, kind: NodeKind, technology: str | None = None, description: str | None = None
) -> str:
    """HTML label (draw.io html=1): bold name and the C4 '[Kind: technology]' line."""
    detail = f"{_KINDS[kind]}: {technology}" if technology else _KINDS[kind]
    small = '<font style="font-size: 10px">'
    inferred = f"<br>{small}{html.escape(description)}</font>" if description else ""
    return f"<b>{html.escape(name)}</b><br>{small}[{html.escape(detail)}]</font>{inferred}"
