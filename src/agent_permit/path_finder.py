from __future__ import annotations

import hashlib
from collections import deque
from dataclasses import dataclass

from agent_permit.models import (
    CodebaseMap,
    Fact,
    GraphEdge,
    GraphEdgeKind,
    GraphNode,
    GraphNodeKind,
    GraphPath,
    GraphPathReport,
    Severity,
    TaxonomyEntry,
    TaxonomyRole,
)


@dataclass(frozen=True)
class _TaxonomyContext:
    entries: dict[str, TaxonomyEntry]
    sources: list[TaxonomyEntry]
    sinks: list[TaxonomyEntry]
    facts_by_id: dict[str, Fact]


class CapabilityPathFinder:
    def find_paths(
        self,
        codebase_map: CodebaseMap,
        *,
        max_depth: int = 4,
    ) -> GraphPathReport:
        context = _classify_taxonomy(codebase_map)
        adjacency = _risk_adjacency(codebase_map.edges)
        paths: list[GraphPath] = []

        for source in context.sources:
            for sink in context.sinks:
                if not _allowed_path(source, sink):
                    continue
                found = _bounded_path(
                    source.node_id,
                    sink.node_id,
                    adjacency,
                    max_depth=max_depth,
                )
                if found is None:
                    continue
                node_ids, edge_ids = found
                paths.append(
                    GraphPath(
                        id=_path_id(source.node_id, sink.node_id, edge_ids),
                        source_id=source.node_id,
                        sink_id=sink.node_id,
                        source_category=source.category,
                        sink_category=sink.category,
                        node_ids=node_ids,
                        edge_ids=edge_ids,
                        severity=_path_severity(source, sink),
                        rationale=_path_rationale(source, sink),
                    )
                )

        paths.sort(key=lambda path: path.id)
        return GraphPathReport(
            scan_run_id=codebase_map.scan_run_id,
            taxonomy=sorted(context.entries.values(), key=lambda entry: entry.node_id),
            paths=paths,
        )


def _classify_taxonomy(codebase_map: CodebaseMap) -> _TaxonomyContext:
    facts_by_id = {fact.id: fact for fact in codebase_map.facts}
    entries: dict[str, TaxonomyEntry] = {}
    sources: list[TaxonomyEntry] = []
    sinks: list[TaxonomyEntry] = []

    for node in codebase_map.nodes:
        node_entries = _classify_node(node, facts_by_id)
        for entry in node_entries:
            entries[f"{entry.node_id}:{entry.role}:{entry.category}"] = entry
            if entry.role == TaxonomyRole.SOURCE:
                sources.append(entry)
            if entry.role == TaxonomyRole.SINK:
                sinks.append(entry)

    sources.sort(key=lambda entry: (entry.category, entry.node_id))
    sinks.sort(key=lambda entry: (entry.category, entry.node_id))
    return _TaxonomyContext(entries, sources, sinks, facts_by_id)


def _classify_node(
    node: GraphNode,
    facts_by_id: dict[str, Fact],
) -> list[TaxonomyEntry]:
    entries: list[TaxonomyEntry] = []

    if node.kind == GraphNodeKind.CREDENTIAL_REF:
        entries.append(
            _entry(
                node,
                TaxonomyRole.SOURCE,
                "credential",
                "Credential variable can grant external or privileged access.",
            )
        )

    if node.kind == GraphNodeKind.FILE:
        file_kind = str(node.metadata.get("file_kind") or "")
        if file_kind == "mcp_config":
            entries.append(
                _entry(
                    node,
                    TaxonomyRole.SOURCE,
                    "repo_config",
                    "MCP config controls external tool/runtime wiring.",
                )
            )
        if file_kind == "ci_workflow":
            entries.append(
                _entry(
                    node,
                    TaxonomyRole.SOURCE,
                    "workflow_file",
                    "Workflow file controls CI execution context.",
                )
            )
        if file_kind == "agent_instruction":
            entries.append(
                _entry(
                    node,
                    TaxonomyRole.SOURCE,
                    "instruction_file",
                    "Agent instruction file can influence agent behavior.",
                )
            )

    if node.kind == GraphNodeKind.MCP_SERVER:
        transport = str(node.metadata.get("transport") or "unknown")
        entries.append(
            _entry(
                node,
                TaxonomyRole.SINK,
                "mcp_server",
                f"MCP server is a tool runtime sink using {transport} transport.",
            )
        )

    if node.kind == GraphNodeKind.NETWORK_ENDPOINT:
        entries.append(
            _entry(
                node,
                TaxonomyRole.SINK,
                "network_endpoint",
                "Network endpoint can receive tool traffic or data.",
            )
        )

    if node.kind == GraphNodeKind.INSTRUCTION:
        entries.append(
            _entry(
                node,
                TaxonomyRole.SINK,
                "risky_instruction",
                "Risky instruction can influence agent behavior.",
            )
        )

    if node.kind == GraphNodeKind.CI_WORKFLOW and _is_privileged_workflow(node, facts_by_id):
        entries.append(
            _entry(
                node,
                TaxonomyRole.SINK,
                "privileged_ci_workflow",
                "Workflow has privileged trigger, write, secret, or checkout risk.",
            )
        )

    return entries


def _entry(
    node: GraphNode,
    role: TaxonomyRole,
    category: str,
    rationale: str,
) -> TaxonomyEntry:
    return TaxonomyEntry(
        node_id=node.id,
        role=role,
        category=category,
        label=node.label,
        rationale=rationale,
    )


def _is_privileged_workflow(
    node: GraphNode,
    facts_by_id: dict[str, Fact],
) -> bool:
    risky_rules = {
        "ci-pr-target-head-checkout",
        "ci-pr-target-write-token",
        "ci-pull-request-target",
        "ci-secret-reference",
        "ci-write-all-permissions",
        "ci-write-permission",
    }
    for fact_id in node.source_fact_ids:
        fact = facts_by_id.get(fact_id)
        if fact is None:
            continue
        if str(fact.attributes.get("rule_id") or "") in risky_rules:
            return True
    return False


def _risk_adjacency(edges: list[GraphEdge]) -> dict[str, list[tuple[str, str]]]:
    adjacency: dict[str, list[tuple[str, str]]] = {}
    for edge in edges:
        adjacency.setdefault(edge.source_id, []).append((edge.target_id, edge.id))
        if edge.kind == GraphEdgeKind.RECEIVES_CREDENTIAL:
            adjacency.setdefault(edge.target_id, []).append((edge.source_id, edge.id))

    for node_id in list(adjacency):
        adjacency[node_id].sort(key=lambda item: (item[0], item[1]))
    return adjacency


def _bounded_path(
    source_id: str,
    sink_id: str,
    adjacency: dict[str, list[tuple[str, str]]],
    *,
    max_depth: int,
) -> tuple[list[str], list[str]] | None:
    queue: deque[tuple[str, list[str], list[str]]] = deque(
        [(source_id, [source_id], [])]
    )
    visited: set[tuple[str, int]] = {(source_id, 0)}

    while queue:
        node_id, node_path, edge_path = queue.popleft()
        if node_id == sink_id and edge_path:
            return node_path, edge_path
        if len(edge_path) >= max_depth:
            continue

        for next_node_id, edge_id in adjacency.get(node_id, []):
            if next_node_id in node_path:
                continue
            state_key = (next_node_id, len(edge_path) + 1)
            if state_key in visited:
                continue
            visited.add(state_key)
            queue.append(
                (
                    next_node_id,
                    [*node_path, next_node_id],
                    [*edge_path, edge_id],
                )
            )

    return None


def _allowed_path(source: TaxonomyEntry, sink: TaxonomyEntry) -> bool:
    return (
        (source.category == "credential" and sink.category == "mcp_server")
        or (
            source.category == "repo_config"
            and sink.category == "network_endpoint"
        )
        or (
            source.category == "workflow_file"
            and sink.category == "privileged_ci_workflow"
        )
        or (
            source.category == "instruction_file"
            and sink.category == "risky_instruction"
        )
    )


def _path_severity(source: TaxonomyEntry, sink: TaxonomyEntry) -> Severity:
    if source.category == "workflow_file" and sink.category == "privileged_ci_workflow":
        return Severity.HIGH
    if source.category == "credential" and sink.category == "mcp_server":
        return Severity.HIGH
    if source.category == "instruction_file" and sink.category == "risky_instruction":
        return Severity.HIGH
    return Severity.MEDIUM


def _path_rationale(source: TaxonomyEntry, sink: TaxonomyEntry) -> str:
    if source.category == "credential" and sink.category == "mcp_server":
        return "Credential reference can reach an MCP tool runtime."
    if source.category == "repo_config" and sink.category == "network_endpoint":
        return "Repository MCP config can route tool traffic to a network endpoint."
    if source.category == "workflow_file" and sink.category == "privileged_ci_workflow":
        return "Workflow file defines a privileged CI execution context."
    if source.category == "instruction_file" and sink.category == "risky_instruction":
        return "Instruction file contains risky agent behavior guidance."
    return "Source can reach sink through capability graph edges."


def _path_id(source_id: str, sink_id: str, edge_ids: list[str]) -> str:
    digest = hashlib.sha256(
        "|".join([source_id, sink_id, *edge_ids]).encode()
    ).hexdigest()[:12]
    return f"path:{digest}"
