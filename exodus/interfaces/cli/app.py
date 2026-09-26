"""Typer commands. They orchestrate use cases and do the IO of writing output documents."""

import shutil
import sys
import threading
import time
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Annotated

import typer

from exodus.application.ports import (
    Document,
    DocumentRenderer,
    EmbeddingModel,
    Enricher,
    FactExtractor,
    FileSource,
    GraphRepository,
    Language,
    ProjectWriter,
    RefactorAdvisor,
    UseCaseWriter,
    VectorStore,
)
from exodus.application.use_cases.build_graph import build_graph
from exodus.application.use_cases.diagnose import diagnose, diagnose_graph
from exodus.application.use_cases.enrich_graph import enrich_graph
from exodus.application.use_cases.propose_refactor import propose_refactor
from exodus.application.use_cases.rag import DocumentRetriever, IndexResult, index_documents
from exodus.application.use_cases.render_diagrams import render_diagrams
from exodus.application.use_cases.scan_projects import scan_projects
from exodus.application.use_cases.write_project_context import (
    RetrievalTrace,
    write_project_context,
)
from exodus.application.use_cases.write_use_cases import write_use_cases
from exodus.domain.graph import ArchitectureGraph
from exodus.domain.identity import slug
from exodus.domain.model import NodeKind
from exodus.domain.refactor import Catalog

DEFAULT_INPUT = Path("exodus-input")
RagTraceRenderer = Callable[
    [Sequence[RetrievalTrace], ArchitectureGraph, IndexResult, str, Language], Document
]
Renderers = Callable[[Language], Sequence[DocumentRenderer]]  # for the documents' language
DEFAULT_OUTPUT = Path("exodus-output")


CLEAR_LINE = "\r\x1b[K"  # back to the line start and erase it (ANSI): no leftover characters


def status_line(frame: str, message: str, elapsed: float, width: int) -> str:
    """The live progress line, cut to the terminal width: a longer line would wrap, and the
    next redraw (which only goes back to the start of the last line) would pile up lines."""
    line = f"{frame} {message} ({elapsed:.1f}s)"
    return line if len(line) <= width else line[: max(1, width - 1)] + "…"


class TerminalProgress(AbstractContextManager["TerminalProgress"]):
    """A quiet log in redirected output and a live timer on an interactive terminal."""

    def __init__(self, message: str) -> None:
        self.message = message
        self.started = time.monotonic()
        self.done = threading.Event()
        self.thread: threading.Thread | None = None
        self.lock = threading.Lock()
        self.thinking = False

    def __enter__(self) -> "TerminalProgress":
        typer.echo(f"→ {self.message}", err=True)
        if sys.stderr.isatty():
            self.thread = threading.Thread(target=self._render, daemon=True)
            self.thread.start()
        return self

    def update(self, message: str) -> None:
        with self.lock:
            self._end_thinking()
            self.message = message

    def think(self, fragment: str) -> None:
        """Stream model reasoning as running text (like `ollama run`), pausing the spinner."""
        with self.lock:
            if not self.thinking:
                self._clear_line()
                typer.secho("Thinking...", dim=True, err=True)
                self.thinking = True
            typer.secho(fragment, nl=False, dim=True, err=True)

    def _end_thinking(self) -> None:
        if self.thinking:
            typer.secho("\n...done thinking.\n", dim=True, err=True)
            self.thinking = False

    def _clear_line(self) -> None:
        if self.thread is not None:
            typer.echo(CLEAR_LINE, nl=False, err=True)

    def __exit__(self, *_: object) -> None:
        self.done.set()
        if self.thread is not None:
            self.thread.join()
        with self.lock:
            self._end_thinking()
            self._clear_line()
        elapsed = time.monotonic() - self.started
        typer.echo(f"✓ {self.message} ({elapsed:.1f}s)", err=True)

    def _render(self) -> None:
        frames = "◐◓◑◒"
        index = 0
        while not self.done.wait(0.15):
            with self.lock:
                if self.thinking:
                    continue
                elapsed = time.monotonic() - self.started
                width = shutil.get_terminal_size((80, 24)).columns - 1
                line = status_line(frames[index % len(frames)], self.message, elapsed, width)
                typer.echo(CLEAR_LINE + line, nl=False, err=True)
            index += 1


OutputOption = Annotated[Path, typer.Option("--output", "-o", help="Output directory.")]
LanguageOption = Annotated[
    Language,
    typer.Option(
        "--lang", help="Language of the report, documentation.md, rag-trace.md and AI texts."
    ),
]


def write_documents(output: Path, documents: Sequence[Document]) -> None:
    for document in documents:
        target = output / document.name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(document.content, encoding="utf-8")
        typer.echo(f"  wrote {target}")


def elapsed(seconds: float) -> str:
    """A duration for people: 4.2s, 3m 05s, 1h 02m 03s."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, secs = divmod(round(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02}m {secs:02}s" if hours else f"{minutes}m {secs:02}s"


def total_time(start: float) -> None:
    """The time the whole processing took, since `start` (a time.monotonic() value)."""
    typer.echo(f"Total processing time: {elapsed(time.monotonic() - start)}")


def project_name(paths: Sequence[Path]) -> str:
    """Output folder of a scan: the scanned folder's name (several folders: sorted, joined by +)."""
    return "+".join(sorted(p.name for p in paths))


def choose_projects(projects: Sequence[Path]) -> list[Path]:
    """Ask which projects to analyze together: numbers separated by commas, empty = all."""
    typer.echo(f"Projects in {DEFAULT_INPUT}/:")
    for number, project in enumerate(projects, start=1):
        typer.echo(f"  {number}) {project.name}")
    while True:
        answer = typer.prompt(
            "Choose (numbers separated by commas, Enter = all together)",
            default="",
            show_default=False,
        )
        numbers = [n.strip() for n in answer.split(",") if n.strip()]
        if not numbers:
            return list(projects)
        if all(n.isdigit() and 1 <= int(n) <= len(projects) for n in numbers):
            return [projects[int(n) - 1] for n in dict.fromkeys(numbers)]
        typer.echo(f"Invalid choice: {answer}", err=True)


def create_app(
    *,
    file_source: FileSource,
    extractors: Sequence[FactExtractor],
    repository_factory: Callable[[Path], GraphRepository],
    inventory_renderers: Renderers,
    diagram_renderers: Sequence[DocumentRenderer],
    to_be_renderers: Sequence[DocumentRenderer] = (),
    report_renderers: Renderers | None = None,
    enricher_factory: Callable[[Path, Language], Enricher] | None = None,
    use_case_writer_factory: Callable[[Path, Language], UseCaseWriter] | None = None,
    catalog: Catalog | None = None,
    refactor_advisor_factory: Callable[[Path, Language], RefactorAdvisor] | None = None,
    project_writer_factory: Callable[[Path, Language], ProjectWriter] | None = None,
    embedder: EmbeddingModel | None = None,
    vector_store: VectorStore | None = None,
    rag_trace_renderer: RagTraceRenderer | None = None,
) -> typer.Typer:
    def scan_to(
        paths: Sequence[Path],
        output: Path,
        think: bool = False,
        language: Language = Language.PT_BR,
    ) -> Path:
        """Scan the projects into <output>/<project>/ and return that folder."""
        target = output / project_name(paths)
        with TerminalProgress("Reading source and configuration"):
            scans = scan_projects(paths, file_source, extractors)
        for warning in diagnose(scans):
            typer.echo(f"warning: {warning}", err=True)
        with TerminalProgress("Building dependency graph"):
            graph = build_graph(scans)
        with TerminalProgress("Preparing inferred descriptions") as progress:
            graph = enrich_graph(
                graph,
                enricher_factory(target, language) if enricher_factory else None,
                progress.update,
                progress.think if think else None,
            )
        with TerminalProgress("Preparing inferred use cases") as progress:
            graph = write_use_cases(
                graph,
                paths,
                file_source,
                use_case_writer_factory(target, language) if use_case_writer_factory else None,
                progress.update,
                progress.think if think else None,
            )
        collection = f"exodus-{slug(target.name)}"
        index, retriever = None, None
        if embedder is not None and vector_store is not None:
            with TerminalProgress("Indexing legacy documentation (RAG)") as progress:
                index = index_documents(scans, collection, embedder, vector_store)
                if index.available and index.pieces:
                    progress.update(
                        f"{index.pieces} pieces in {collection} ({index.embedded} embedded, "
                        f"{index.removed} removed)"
                    )
            if not index.available:
                typer.echo(
                    "warning: RAG unavailable (Qdrant at localhost:6333 or the Ollama model "
                    "bge-m3): business sections inferred from the code only",
                    err=True,
                )
            elif index.pieces:
                retriever = DocumentRetriever(embedder, vector_store, collection)
        with TerminalProgress("Preparing inferred project context") as progress:
            traces = write_project_context(
                graph,
                project_writer_factory(target, language) if project_writer_factory else None,
                progress.update,
                progress.think if think else None,
                retriever,
                language,
            )
        if catalog is not None:
            with TerminalProgress("Preparing refactor proposal") as progress:
                graph = propose_refactor(
                    graph,
                    catalog,
                    refactor_advisor_factory(target, language)
                    if refactor_advisor_factory
                    else None,
                    progress.update,
                    progress.think if think else None,
                )
        for warning in diagnose_graph(graph):
            typer.echo(f"warning: {warning}", err=True)
        if not graph.nodes():
            typer.echo(f"Nothing to write for {target.name}.", err=True)
            raise typer.Exit(code=1)
        with TerminalProgress("Writing documentation"):
            repository_factory(target).save(graph)
            documents = [d for r in inventory_renderers(language) for d in r.render(graph)]
            if traces and index is not None and rag_trace_renderer is not None:
                documents.append(rag_trace_renderer(traces, graph, index, collection, language))
            write_documents(target, documents)
        typer.echo(f"  wrote {target / 'graph.json'}")
        counts = ", ".join(f"{len(graph.nodes(kind))} {kind.value}" for kind in NodeKind)
        typer.echo(f"Graph: {counts}, {len(graph.relationships())} relationships")
        return target

    def render_to(
        project: Path,
        as_is: bool = True,
        to_be: bool = True,
        language: Language = Language.PT_BR,
    ) -> bool:
        """Render the diagrams of a scanned project; False if it has no graph."""
        views = [("AS-IS diagrams", diagram_renderers)] if as_is else []
        views += [("TO-BE diagrams", to_be_renderers)] if to_be and to_be_renderers else []
        views += [("HTML report", report_renderers(language))] if report_renderers else []
        try:
            for name, renderers in views:
                with TerminalProgress(f"Rendering {name} for {project.name}"):
                    documents = render_diagrams(repository_factory(project), renderers)
                    if (
                        name == "TO-BE diagrams"
                    ):  # ADRs are regenerated: drop the ones of a past render
                        for old in (project / "to-be" / "adr").glob("*.md"):
                            old.unlink()
                    write_documents(project, documents)
        except FileNotFoundError:
            return False
        return True

    app = typer.Typer(
        help="Exodus: reads legacy projects and documents their architecture for AWS migration.",
        add_completion=False,
    )

    @app.callback(invoke_without_command=True)
    def default(ctx: typer.Context, language: LanguageOption = Language.PT_BR) -> None:
        """Without a command: list the projects in ./exodus-input/, scan the chosen ones together
        and render everything (AS-IS, TO-BE, report) into ./exodus-output/<project>/."""
        if ctx.invoked_subcommand is not None:
            return
        DEFAULT_INPUT.mkdir(exist_ok=True)
        projects = sorted(
            p.resolve()
            for p in DEFAULT_INPUT.iterdir()
            if p.is_dir() and not p.name.startswith(".")
        )
        if not projects:
            typer.echo(
                f"Put the legacy projects in {DEFAULT_INPUT.resolve()}/ (one folder each) "
                "and run again.",
                err=True,
            )
            raise typer.Exit(code=1)
        paths = choose_projects(projects) if len(projects) > 1 else projects
        start = time.monotonic()  # after the choice: waiting for the user is not processing
        render_to(scan_to(paths, DEFAULT_OUTPUT, language=language), language=language)
        total_time(start)

    @app.command()
    def scan(
        paths: Annotated[
            list[Path],
            typer.Argument(
                help="Project folders to analyze together.",
                exists=True,
                file_okay=False,
                resolve_path=True,
            ),
        ],
        output: OutputOption = DEFAULT_OUTPUT,
        think: Annotated[
            bool,
            typer.Option(help="Let the model reason first and stream its reasoning (slow)."),
        ] = False,
        language: LanguageOption = Language.PT_BR,
    ) -> None:
        """Scan projects and write graph.json and inventory.md to <output>/<project>/."""
        start = time.monotonic()
        scan_to(paths, output, think, language)
        total_time(start)

    @app.command()
    def render(
        as_is: Annotated[
            bool, typer.Option("--as-is", help="C4 L1/L2/L3 of the current state.")
        ] = False,
        to_be: Annotated[
            bool, typer.Option("--to-be", help="L2 on AWS: replatform (and refactor) paths.")
        ] = False,
        output: OutputOption = DEFAULT_OUTPUT,
        language: LanguageOption = Language.PT_BR,
    ) -> None:
        """Render diagrams for every project previously scanned into <output>/<project>/."""
        if not as_is and not to_be:
            raise typer.BadParameter("choose a view to render: --as-is and/or --to-be")
        start = time.monotonic()
        projects = sorted(p for p in output.iterdir() if p.is_dir()) if output.is_dir() else []
        if not [p for p in projects if render_to(p, as_is, to_be, language)]:
            typer.echo(f"No graph found in {output}. Run `python -m exodus scan` first.", err=True)
            raise typer.Exit(code=1)
        total_time(start)

    return app
