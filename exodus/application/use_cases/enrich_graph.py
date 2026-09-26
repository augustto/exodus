"""Apply an optional inference adapter after deterministic graph construction."""

from collections.abc import Callable

from exodus.application.ports import Enricher
from exodus.domain.graph import ArchitectureGraph


def enrich_graph(
    graph: ArchitectureGraph,
    enricher: Enricher | None,
    progress: Callable[[str], None] | None = None,
    thinking: Callable[[str], None] | None = None,
) -> ArchitectureGraph:
    return enricher.enrich(graph, progress, thinking) if enricher is not None else graph
