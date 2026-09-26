from collections.abc import Sequence

from exodus.application.ports import Document, DocumentRenderer, GraphRepository


def render_diagrams(
    repository: GraphRepository, renderers: Sequence[DocumentRenderer]
) -> list[Document]:
    graph = repository.load()
    return [doc for renderer in renderers for doc in renderer.render(graph)]
