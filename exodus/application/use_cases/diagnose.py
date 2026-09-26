"""Warnings about a scan that would otherwise go unnoticed (pure): a project where nothing was
recognized, solutions listing projects that are not in the scanned folder (e.g. a solution
aggregating repositories that were not cloned next to it), and systems whose containers show no
communication at all (their diagrams would suggest isolated pieces)."""

from collections.abc import Sequence

from exodus.application.use_cases.scan_projects import ProjectScan
from exodus.domain.facts import ProjectDeclared, SolutionEntry
from exodus.domain.graph import ArchitectureGraph
from exodus.domain.model import NodeKind

SHOWN = 3  # missing projects named in a warning; the rest are counted


def diagnose(scans: Sequence[ProjectScan]) -> list[str]:
    warnings: list[str] = []
    for scan in scans:
        if all(isinstance(f, SolutionEntry) for f in scan.facts):
            warnings.append(
                f"nothing recognized in {scan.name}: no source code or configuration of a "
                "supported kind"
            )
        declared = {f.name for f in scan.facts if isinstance(f, ProjectDeclared)}
        missing: dict[str, list[SolutionEntry]] = {}
        for fact in scan.facts:
            if isinstance(fact, SolutionEntry) and fact.name not in declared:
                missing.setdefault(fact.evidence.file, []).append(fact)
        for solution, entries in missing.items():
            listed = ", ".join(
                f"{e.name} ({e.path}, line {e.evidence.line})" for e in entries[:SHOWN]
            )
            more = f" and {len(entries) - SHOWN} more" if len(entries) > SHOWN else ""
            warnings.append(
                f"{solution} lists {len(entries)} projects not found in {scan.name}: {listed}"
                f"{more}. Put their folders inside {scan.name} to analyze them."
            )
    return warnings


def diagnose_graph(graph: ArchitectureGraph) -> list[str]:
    warnings: list[str] = []
    for system in graph.nodes(NodeKind.SYSTEM):
        containers = {c.id for c in graph.children(system.id, NodeKind.CONTAINER)}
        talking = any({r.source_id, r.target_id} & containers for r in graph.relationships())
        if len(containers) > 1 and not talking:
            warnings.append(
                f"{system.name}: {len(containers)} containers but no communication detected "
                "between them or with databases, queues or external systems; integrations "
                "through message brokers, service discovery or gateways may not be supported yet"
            )
    return warnings
