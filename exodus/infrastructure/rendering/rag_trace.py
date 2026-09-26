"""`rag-trace.md`: what the RAG example did, to learn and to check it — for each fixed
question, the pieces of written documentation the search brought (score, source, beginning of
the text), and what the model then wrote with them in `documentation.md`."""

from collections.abc import Sequence

from exodus.application.ports import Document, Language
from exodus.application.use_cases.rag import MIN_SCORE, IndexResult
from exodus.application.use_cases.write_project_context import RetrievalTrace
from exodus.domain.graph import ArchitectureGraph
from exodus.domain.model import NodeKind
from exodus.infrastructure.rendering.common import pick

PREVIEW = 140  # characters of each piece shown


def render_rag_trace(
    traces: Sequence[RetrievalTrace],
    graph: ArchitectureGraph,
    index: IndexResult,
    collection: str,
    language: Language = Language.PT_BR,
) -> Document:
    def t(pt_br: str, en: str) -> str:
        return pick(language, pt_br, en)

    lines = [
        "# Exodus — RAG trace",
        "",
        t(
            f"> Base: coleção `{collection}` no Qdrant (painel: http://localhost:6333/dashboard). "
            f"Indexação: {index.pieces} trecho(s) da documentação escrita, {index.embedded} "
            f"com embedding novo nesta execução, {index.removed} removido(s). Trechos com "
            f"semelhança abaixo de {MIN_SCORE} são descartados.",
            f"> Store: collection `{collection}` in Qdrant (dashboard: "
            f"http://localhost:6333/dashboard). Indexing: {index.pieces} piece(s) of written "
            f"documentation, {index.embedded} newly embedded in this run, {index.removed} "
            f"removed. Pieces with similarity below {MIN_SCORE} are discarded.",
        ),
        "",
    ]
    for system in graph.nodes(NodeKind.SYSTEM):
        found = [tr for tr in traces if tr.system == system.name]
        if not found:
            continue
        lines += [f"## {system.name}", ""]
        for trace in found:
            lines += [f"### {t('Pergunta', 'Question')}: {trace.question}", ""]
            if not trace.hits:
                none = t(
                    "Nenhum trecho acima da semelhança mínima.",
                    "No piece above the minimum similarity.",
                )
                lines += [none, ""]
                continue
            lines += [
                t(
                    "| Semelhança | Fonte | Título | Início do trecho |",
                    "| Similarity | Source | Title | Start of the piece |",
                ),
                "|---|---|---|---|",
            ]
            for hit in trace.hits:
                preview = " ".join(hit.piece.text.split())[:PREVIEW]
                lines.append(
                    f"| {hit.score:.3f} | `{hit.piece.source}` | {hit.piece.title} | "
                    f"{preview.replace('|', '/')}… |"
                )
            lines.append("")
        context = graph.project_context(system.id)
        lines += [
            t(
                "### O que a IA escreveu com esses trechos",
                "### What the AI wrote with these pieces",
            ),
            "",
        ]
        if context is None:
            lines += [
                t(
                    "Nada (IA indisponível ou resposta inválida).",
                    "Nothing (AI unavailable or invalid answer).",
                ),
                "",
            ]
            continue
        cited = [p for p in context.principles if ":" in p.basis and "(" in p.basis]
        sent = t("Trechos enviados à IA", "Pieces sent to the AI")
        principle = t("Princípio citando documento", "Principle citing a document")
        basis = t("base", "basis")
        lines += [
            f"- **{sent} ({len(context.sources)}):** "
            + (", ".join(f"`{s}`" for s in context.sources) or t("nenhum", "none")),
            f"- **{t('Problema', 'Problem')}:** {context.problem or '—'}",
            *[f"- **{principle}:** {p.text} ({basis}: {p.basis})" for p in cited],
            "",
        ]
    return Document(name="rag-trace.md", content="\n".join(lines))
