"""Read the refactor catalog (exodus/catalog/refactor-catalog.json)."""

from pathlib import Path

from exodus.domain.refactor import Catalog

CATALOG_PATH = Path(__file__).parents[1] / "catalog" / "refactor-catalog.json"


def load_catalog(path: Path = CATALOG_PATH) -> Catalog:
    return Catalog.model_validate_json(path.read_text(encoding="utf-8"))
