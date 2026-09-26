"""TO-BE diagrams: the L2 view of each system drawn with AWS service icons, grouped by AWS
category (colour and legend). Same layout and routing as the AS-IS."""

import html
from collections.abc import Iterable

from exodus.application.ports import Document
from exodus.domain.graph import ArchitectureGraph
from exodus.domain.model import Node, NodeKind
from exodus.domain.refactor import refactor_view
from exodus.domain.to_be import replatform_views
from exodus.infrastructure.rendering.aws_icons import COLOURS, EXTERNAL, AwsIcon, aws_icon
from exodus.infrastructure.rendering.drawio import ICON, ICON_PAD, drawio_file

_ICON_STYLE = (
    "sketch=0;outlineConnect=0;fontColor=#232F3E;gradientColor=none;strokeColor=#ffffff;"
    "dashed=0;html=1;aspect=fixed;shape=mxgraph.aws4.resourceIcon;"
)


_OUTSIDE = (NodeKind.SYSTEM, NodeKind.EXTERNAL_SYSTEM)  # not migrated: they stay where they are


def _icon(node: Node) -> AwsIcon:
    return EXTERNAL if node.kind in _OUTSIDE else aws_icon(node.technology)


class AwsLook:
    platform_title = "Security · Observability · Platform"

    def style(self, node: Node) -> str:
        colour = COLOURS[_icon(node).category]
        return (
            f"rounded=1;arcSize=6;fillColor=#ffffff;strokeColor={colour};strokeWidth=2;"
            f"fontColor=#232F3E;align=left;spacingLeft={ICON + 2 * ICON_PAD};"
        )

    def label(self, node: Node) -> str:
        small = '<font style="font-size: 10px">'
        target = html.escape(
            "Outside AWS" if node.kind in _OUTSIDE else node.technology or "No rule: evaluate"
        )
        return f"<b>{html.escape(node.name)}</b><br>{small}{target}</font>"

    def icon(self, node: Node) -> str:
        found = _icon(node)
        return (
            f"{_ICON_STYLE}fillColor={COLOURS[found.category]};resIcon=mxgraph.aws4.{found.icon};"
        )

    def legend(self, nodes: Iterable[Node]) -> list[tuple[str, str, str]]:
        shown = {_icon(node).category for node in nodes}
        return [
            (category, category, f"rounded=1;fillColor=#ffffff;strokeColor={colour};strokeWidth=2;")
            for category, colour in COLOURS.items()
            if category in shown
        ]


class ReplatformRenderer:
    def render(self, graph: ArchitectureGraph) -> list[Document]:
        pages = [(f"replatform-{v.key}", v) for v in replatform_views(graph)]
        if not pages:
            return []
        return [Document(name="to-be/replatform.drawio", content=drawio_file(pages, AwsLook()))]


class RefactorRenderer:
    """The refactor proposal (see `domain.refactor`); nothing when no proposal was made."""

    def render(self, graph: ArchitectureGraph) -> list[Document]:
        if graph.refactor is None:
            return []
        pages = [
            (f"refactor-{s.id.removeprefix('system:')}", refactor_view(graph, s))
            for s in graph.nodes(NodeKind.SYSTEM)
        ]
        if not pages:
            return []
        return [Document(name="to-be/refactor.drawio", content=drawio_file(pages, AwsLook()))]
