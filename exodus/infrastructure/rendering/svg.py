"""A view drawn as inline SVG, from the same layout as the draw.io diagrams (same positions and
arrow routes), for the HTML report. Hovering an element or arrow shows its evidence (and, for
an inferred element, why), as the draw.io tooltips do."""

import html
import textwrap
from collections.abc import Iterable
from typing import Protocol

from exodus.domain.model import Evidence, Node, NodeKind
from exodus.domain.views import C4View
from exodus.infrastructure.rendering.aws_icons import (
    C4_COLOURS,
    COLOURS,
    EXTERNAL,
    INK,
    AwsIcon,
    aws_icon,
)
from exodus.infrastructure.rendering.common import evidence_summary
from exodus.infrastructure.rendering.layout import LABEL_FONT, Layout, Rect, label_lines, layout

_MARGIN = 20
_NAME_FONT, _DETAIL_FONT = 13, 10
_KINDS = {NodeKind.SYSTEM: "Software System", NodeKind.CONTAINER: "Container",
          NodeKind.COMPONENT: "Component", NodeKind.DATA_STORE: "Database",
          NodeKind.QUEUE: "Queue", NodeKind.EXTERNAL_SYSTEM: "External System",
          NodeKind.PLATFORM: "Platform service"}  # fmt: skip
_OUTSIDE = (NodeKind.SYSTEM, NodeKind.EXTERNAL_SYSTEM)


class SvgStyle(Protocol):
    def colours(self, node: Node) -> tuple[str, str, str]:
        """(fill, stroke, text) of an element."""
        ...

    def detail(self, node: Node) -> str:
        """The small line under the element's name."""
        ...

    def legend(self, nodes: Iterable[Node]) -> list[tuple[str, str, str]]:
        """(text, fill, stroke) of each kind of element shown."""
        ...


class C4Svg:
    def colours(self, node: Node) -> tuple[str, str, str]:
        return "#ffffff", C4_COLOURS[node.kind], INK

    def detail(self, node: Node) -> str:
        kind = _KINDS[node.kind]
        return f"[{kind}: {node.technology}]" if node.technology else f"[{kind}]"

    def legend(self, nodes: Iterable[Node]) -> list[tuple[str, str, str]]:
        shown = {n.kind for n in nodes}
        return [(_KINDS[k], "#ffffff", C4_COLOURS[k]) for k in _KINDS if k in shown]


class AwsSvg:
    def colours(self, node: Node) -> tuple[str, str, str]:
        return "#ffffff", COLOURS[_icon(node).category], "#232F3E"

    def detail(self, node: Node) -> str:
        return "Outside AWS" if node.kind in _OUTSIDE else node.technology or "No rule: evaluate"

    def legend(self, nodes: Iterable[Node]) -> list[tuple[str, str, str]]:
        shown = {_icon(n).category for n in nodes}
        return [(c, "#ffffff", colour) for c, colour in COLOURS.items() if c in shown]


def _icon(node: Node) -> AwsIcon:
    return EXTERNAL if node.kind in _OUTSIDE else aws_icon(node.technology)


def svg(view: C4View, style: SvgStyle, platform_title: str = "Platform") -> str:
    lay = layout(view)
    left, top, right, bottom = _extent(lay)
    legend = style.legend(box.node for box in [*lay.boxes.values(), *lay.platform_boxes.values()])
    legend_x = right + 3 * _MARGIN
    width = legend_x + 200 - left
    height = max(bottom, top + 40 + 36 * len(legend)) - top + _MARGIN
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{left - _MARGIN} {top - _MARGIN} '
        f'{width + _MARGIN} {height + _MARGIN}" width="{width + _MARGIN}" '
        f'height="{height + _MARGIN}" class="diagram" role="img" '
        f'aria-label="{_e(view.title)}">',
        '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" '
        'markerHeight="8" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" '
        'fill="#707070"/></marker></defs>',
    ]
    if lay.frame is not None and view.boundary is not None:
        parts.append(_frame(lay.frame, view.boundary.name, view.boundary.evidence))
    if lay.platform is not None and lay.frame is not None:
        parts.append(_group(lay.platform, platform_title, lay.platform_link))
    parts += [_box(box.node, box.rect, style) for box in lay.boxes.values()]
    parts += [_box(box.node, box.rect, style) for box in lay.platform_boxes.values()]
    for arrow in lay.arrows:
        r = arrow.relationship
        points = " ".join(f"{x},{y}" for x, y in arrow.points)
        start = "marker-start:url(#arrow);" if r.both_ways else ""
        (x, y), lines = arrow.points[0], label_lines(r.description)
        label = "".join(
            f'<tspan x="{x + 6}" dy="{0 if k == 0 else LABEL_FONT + 2}">{_e(line)}</tspan>'
            for k, line in enumerate(lines)
        )
        parts.append(
            f'<g class="arrow"><title>{_e(r.description)}\n{_evidence(r.evidence)}</title>'
            f'<polyline points="{points}" fill="none" stroke="#707070" stroke-dasharray="6 4" '
            f'style="marker-end:url(#arrow);{start}"/>'
            f'<text x="{x + 6}" y="{y - 6 - (LABEL_FONT + 2) * (len(lines) - 1)}" '
            f'font-size="{LABEL_FONT}" class="label">{label}</text></g>'
        )
    parts.append(_legend(legend, legend_x, top))
    parts.append("</svg>")
    return "\n".join(parts)


def _extent(lay: Layout) -> tuple[int, int, int, int]:
    rects = [b.rect for b in [*lay.boxes.values(), *lay.platform_boxes.values()]]
    rects += [r for r in (lay.frame, lay.platform) if r is not None]
    points = [p for arrow in lay.arrows for p in arrow.points]
    xs = [r.x for r in rects] + [x for x, _ in points]
    ys = [r.y for r in rects] + [y for _, y in points]
    right = max([r.x + r.width for r in rects] + [x for x, _ in points], default=0)
    bottom = max([r.y + r.height for r in rects] + [y for _, y in points], default=0)
    return min(xs, default=0), min(ys, default=0), right, bottom


def _box(node: Node, rect: Rect, style: SvgStyle) -> str:
    fill, stroke, text = style.colours(node)
    why = f"Inferred ({node.description.confidence:.0%}): {node.description.text}\n" if (
        node.description) else ""  # fmt: skip
    x, y, w, h = rect.x, rect.y, rect.width, rect.height
    if node.kind in (NodeKind.DATA_STORE, NodeKind.QUEUE):
        shape = (
            f'<path d="M{x},{y + 8} a{w / 2},8 0 0,0 {w},0 v{h - 16} a{w / 2},8 0 0,1 {-w},0 z" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="2"/>'
            f'<ellipse cx="{x + w / 2}" cy="{y + 8}" rx="{w / 2}" ry="8" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="2"/>'
        )
    else:
        shape = (
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="2"/>'
        )
    name = textwrap.wrap(node.name, width=max(8, w // 8), max_lines=2, placeholder="…")
    detail = textwrap.wrap(style.detail(node), width=max(8, w // 6), max_lines=2, placeholder="…")
    total = len(name) * (_NAME_FONT + 3) + len(detail) * (_DETAIL_FONT + 3)
    line_y = y + (h - total) / 2 + _NAME_FONT
    spans = []
    for line in name:
        spans.append(f'<tspan x="{x + w / 2}" y="{line_y:.0f}" font-weight="bold" '
                     f'font-size="{_NAME_FONT}">{_e(line)}</tspan>')  # fmt: skip
        line_y += _NAME_FONT + 3
    for line in detail:
        spans.append(f'<tspan x="{x + w / 2}" y="{line_y:.0f}" '
                     f'font-size="{_DETAIL_FONT}">{_e(line)}</tspan>')  # fmt: skip
        line_y += _DETAIL_FONT + 3
    return (
        f'<g class="element"><title>{_e(why)}{_evidence(node.evidence)}</title>{shape}'
        f'<text text-anchor="middle" fill="{text}">{"".join(spans)}</text></g>'
    )


def _frame(rect: Rect, name: str, evidence: tuple[Evidence, ...]) -> str:
    return (
        f'<g class="boundary"><title>{_evidence(evidence)}</title>'
        f'<rect x="{rect.x}" y="{rect.y}" width="{rect.width}" height="{rect.height}" rx="6" '
        f'fill="none" stroke="#444444" stroke-dasharray="8 4"/>'
        f'<text x="{rect.x + 10}" y="{rect.y + rect.height - 12}" font-weight="bold" '
        f'class="muted">{_e(name)}</text></g>'
    )


def _group(rect: Rect, title: str, link: tuple[tuple[int, int], ...]) -> str:
    points = " ".join(f"{x},{y}" for x, y in link)
    return (
        f'<rect x="{rect.x}" y="{rect.y}" width="{rect.width}" height="{rect.height}" rx="6" '
        f'fill="none" stroke="#5d6d7e" stroke-dasharray="8 4"/>'
        f'<text x="{rect.x + 10}" y="{rect.y + 20}" font-weight="bold" class="muted">'
        f"{_e(title)}</text>"
        f'<polyline points="{points}" fill="none" stroke="#707070" stroke-dasharray="6 4" '
        f'style="marker-end:url(#arrow)"/>'
    )


def _legend(entries: list[tuple[str, str, str]], x: int, y: int) -> str:
    parts = [f'<text x="{x}" y="{y + 14}" font-weight="bold" class="muted">Legend</text>']
    for k, (text, fill, stroke) in enumerate(entries):
        top = y + 28 + 36 * k
        parts.append(
            f'<rect x="{x}" y="{top}" width="28" height="22" rx="4" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="2"/><text x="{x + 36}" y="{top + 16}" '
            f'font-size="12" class="muted">{_e(text)}</text>'
        )
    return "".join(parts)


def _evidence(evidence: Iterable[Evidence]) -> str:
    return _e(f"Evidence: {evidence_summary(tuple(evidence))}")


def _e(text: str) -> str:
    return html.escape(text, quote=True)
