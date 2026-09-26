"""Composition root: the only place that knows every concrete adapter.

Adding a language or a config format = add its extractor to EXTRACTORS.
"""

from exodus.application.ports import DocumentRenderer, FactExtractor, Language
from exodus.infrastructure.catalog import load_catalog
from exodus.infrastructure.config.aspnetcore import AppSettingsExtractor
from exodus.infrastructure.config.docker import ComposeExtractor, DockerfileExtractor
from exodus.infrastructure.config.dotnet import (
    AspNetEndpointExtractor,
    CsprojExtractor,
    PackagesConfigExtractor,
    SolutionExtractor,
    WebConfigExtractor,
)
from exodus.infrastructure.config.gateways import NtradaExtractor, OcelotExtractor
from exodus.infrastructure.config.java import (
    GradleExtractor,
    JavaConfigExtractor,
    JavaEndpointExtractor,
    MavenExtractor,
)
from exodus.infrastructure.config.python import (
    PythonConfigExtractor,
    PythonEndpointExtractor,
    PythonProjectExtractor,
    RequirementsExtractor,
)
from exodus.infrastructure.config.risk_signals import RiskSignalExtractor
from exodus.infrastructure.enrichment.ollama import OllamaEnricher
from exodus.infrastructure.enrichment.project import OllamaProjectWriter
from exodus.infrastructure.enrichment.refactor import OllamaRefactorAdvisor
from exodus.infrastructure.enrichment.use_cases import OllamaUseCaseWriter
from exodus.infrastructure.filesystem import LocalFileSource
from exodus.infrastructure.parsing.csharp import csharp_extractor
from exodus.infrastructure.parsing.data_access import DataAccessExtractor
from exodus.infrastructure.parsing.documents import DocumentExtractor
from exodus.infrastructure.parsing.dotnet_entry_points import DotNetEntryPointExtractor
from exodus.infrastructure.parsing.java import java_extractor
from exodus.infrastructure.parsing.java_entry_points import (
    JavaEntryPointExtractor,
    WebXmlEntryPointExtractor,
)
from exodus.infrastructure.parsing.python import PythonExtractor
from exodus.infrastructure.parsing.python_entry_points import PythonEntryPointExtractor
from exodus.infrastructure.parsing.url_literals import UrlLiteralExtractor
from exodus.infrastructure.persistence.json_repository import JsonGraphRepository
from exodus.infrastructure.rag import OllamaEmbedder, QdrantStore
from exodus.infrastructure.rendering.adr import AdrRenderer
from exodus.infrastructure.rendering.documentation import DocumentationRenderer
from exodus.infrastructure.rendering.drawio import DrawioRenderer
from exodus.infrastructure.rendering.inventory import InventoryRenderer
from exodus.infrastructure.rendering.migration import MigrationRenderer
from exodus.infrastructure.rendering.overview import OverviewRenderer
from exodus.infrastructure.rendering.rag_trace import render_rag_trace
from exodus.infrastructure.rendering.report import ReportRenderer
from exodus.infrastructure.rendering.risks import RisksRenderer
from exodus.infrastructure.rendering.to_be import RefactorRenderer, ReplatformRenderer
from exodus.infrastructure.rendering.use_cases import UseCasesRenderer
from exodus.interfaces.cli.app import create_app

SOURCE_EXTENSIONS = (".cs", ".java", ".py")
CATALOG = load_catalog()

EXTRACTORS: list[FactExtractor] = [
    # .NET
    SolutionExtractor(),
    CsprojExtractor(),
    PackagesConfigExtractor(),
    WebConfigExtractor(),
    AspNetEndpointExtractor(),
    AppSettingsExtractor(),
    NtradaExtractor(),
    OcelotExtractor(),
    DockerfileExtractor(),
    ComposeExtractor(),
    csharp_extractor(),
    DotNetEntryPointExtractor(),
    # Java
    MavenExtractor(),
    GradleExtractor(),
    JavaConfigExtractor(),
    JavaEndpointExtractor(),
    java_extractor(),
    JavaEntryPointExtractor(),
    WebXmlEntryPointExtractor(),
    # Python
    PythonProjectExtractor(),
    RequirementsExtractor(),
    PythonConfigExtractor(),
    PythonEndpointExtractor(),
    PythonExtractor(),
    PythonEntryPointExtractor(),
    RiskSignalExtractor(),
    # language-agnostic
    UrlLiteralExtractor(SOURCE_EXTENSIONS),
    DataAccessExtractor(SOURCE_EXTENSIONS),
    DocumentExtractor(),  # written documentation, for retrieval (RAG)
]


def inventory_renderers(language: Language) -> list[DocumentRenderer]:
    return [
        InventoryRenderer(),
        RisksRenderer(),
        MigrationRenderer(),
        OverviewRenderer(),
        UseCasesRenderer(),
        DocumentationRenderer(language),
    ]


app = create_app(
    file_source=LocalFileSource(),
    extractors=EXTRACTORS,
    repository_factory=JsonGraphRepository,
    inventory_renderers=inventory_renderers,
    diagram_renderers=[DrawioRenderer()],
    to_be_renderers=[ReplatformRenderer(), RefactorRenderer(), AdrRenderer(CATALOG)],
    report_renderers=lambda language: [ReportRenderer(CATALOG, language)],
    enricher_factory=lambda target, language: OllamaEnricher(
        target / "enrichment-cache.json", language
    ),
    use_case_writer_factory=lambda target, language: OllamaUseCaseWriter(
        target / "use-cases-cache.json", language
    ),
    catalog=CATALOG,
    refactor_advisor_factory=lambda target, language: OllamaRefactorAdvisor(
        target / "refactor-cache.json", language
    ),
    project_writer_factory=lambda target, language: OllamaProjectWriter(
        target / "project-cache.json", language
    ),
    embedder=OllamaEmbedder(),
    vector_store=QdrantStore(),
    rag_trace_renderer=render_rag_trace,
)
