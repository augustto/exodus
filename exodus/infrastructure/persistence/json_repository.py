import json
from pathlib import Path

from exodus.domain.graph import ArchitectureGraph, GraphDocument

GRAPH_FILE = "graph.json"
SCHEMA_FILE = "graph.schema.json"


class JsonGraphRepository:
    """Stores the graph as <output>/graph.json plus its JSON Schema."""

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir

    @property
    def graph_path(self) -> Path:
        return self.output_dir / GRAPH_FILE

    def save(self, graph: ArchitectureGraph) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.graph_path.write_text(graph.to_document().model_dump_json(indent=2), encoding="utf-8")
        schema = GraphDocument.model_json_schema()
        (self.output_dir / SCHEMA_FILE).write_text(json.dumps(schema, indent=2), encoding="utf-8")

    def load(self) -> ArchitectureGraph:
        text = self.graph_path.read_text(encoding="utf-8")
        return ArchitectureGraph.from_document(GraphDocument.model_validate_json(text))
