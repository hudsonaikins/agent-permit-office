from __future__ import annotations

from dataclasses import dataclass

from agent_permit.models import (
    AgentBom,
    CodebaseMap,
    EvidenceLocation,
    Fact,
    FactKind,
    FileInventory,
    FileInventoryEntry,
    Finding,
    FindingCategory,
    GraphEdge,
    GraphEdgeKind,
    GraphNode,
    GraphNodeKind,
)


@dataclass(frozen=True)
class GraphBuildResult:
    codebase_map: CodebaseMap
    findings: list[Finding]


class CapabilityGraphBuilder:
    def build(
        self,
        *,
        scan_run_id: str,
        inventory: FileInventory,
        agent_bom: AgentBom,
        findings: list[Finding],
    ) -> GraphBuildResult:
        state = _GraphState(scan_run_id)
        for entry in inventory.files:
            _add_file(state, entry)

        for server in agent_bom.mcp_servers:
            _add_mcp_server(state, server.id, server.name, server.transport, server.command, server.url)

        for credential_ref in agent_bom.credential_refs:
            _add_credential_ref(
                state,
                credential_ref.name,
                credential_ref.source,
                provider=credential_ref.provider,
                scope_hint=credential_ref.scope_hint,
                attached_to=credential_ref.attached_to,
            )

        enriched_findings = [
            _add_finding_context(state, finding) for finding in findings
        ]

        return GraphBuildResult(
            codebase_map=CodebaseMap(
                scan_run_id=scan_run_id,
                nodes=state.sorted_nodes(),
                edges=state.sorted_edges(),
                facts=state.sorted_facts(),
            ),
            findings=enriched_findings,
        )


class _GraphState:
    def __init__(self, scan_run_id: str) -> None:
        self.scan_run_id = scan_run_id
        self.facts: dict[str, Fact] = {}
        self.nodes: dict[str, GraphNode] = {}
        self.edges: dict[str, GraphEdge] = {}

    def add_fact(self, fact: Fact) -> None:
        self.facts[fact.id] = fact

    def add_node(self, node: GraphNode) -> None:
        existing = self.nodes.get(node.id)
        if existing is None:
            self.nodes[node.id] = node
            return
        self.nodes[node.id] = existing.model_copy(
            update={
                "source_fact_ids": sorted(
                    set(existing.source_fact_ids) | set(node.source_fact_ids)
                )
            }
        )

    def add_edge(self, edge: GraphEdge) -> None:
        self.edges[edge.id] = edge

    def sorted_nodes(self) -> list[GraphNode]:
        return [self.nodes[node_id] for node_id in sorted(self.nodes)]

    def sorted_edges(self) -> list[GraphEdge]:
        return [self.edges[edge_id] for edge_id in sorted(self.edges)]

    def sorted_facts(self) -> list[Fact]:
        return [self.facts[fact_id] for fact_id in sorted(self.facts)]


def _add_file(state: _GraphState, entry: FileInventoryEntry) -> None:
    fact_id = _file_fact_id(entry.path)
    state.add_fact(
        Fact(
            id=fact_id,
            kind=FactKind.FILE,
            name=entry.path,
            source=EvidenceLocation(path=entry.path),
            attributes={
                "file_kind": entry.kind,
                "high_signal": entry.high_signal,
                "language": entry.language,
                "sha256": entry.sha256,
                "size_bytes": entry.size_bytes,
            },
        )
    )
    state.add_node(
        GraphNode(
            id=_file_node_id(entry.path),
            kind=GraphNodeKind.FILE,
            label=entry.path,
            source_fact_ids=[fact_id],
            metadata={
                "file_kind": entry.kind,
                "high_signal": entry.high_signal,
            },
        )
    )


def _add_mcp_server(
    state: _GraphState,
    server_id: str,
    name: str,
    transport: str,
    command: str | None,
    url: str | None,
) -> None:
    rel_path = _path_from_prefixed_id(server_id, "mcp-server")
    state.add_fact(
        Fact(
            id=server_id,
            kind=FactKind.MCP_SERVER,
            name=name,
            source=EvidenceLocation(path=rel_path or "<unknown>"),
            attributes={
                "transport": transport,
                "command": command,
                "url": url,
            },
        )
    )
    state.add_node(
        GraphNode(
            id=server_id,
            kind=GraphNodeKind.MCP_SERVER,
            label=name,
            source_fact_ids=[server_id],
            metadata={"transport": transport},
        )
    )
    if rel_path:
        _add_edge(
            state,
            _file_node_id(rel_path),
            server_id,
            GraphEdgeKind.LAUNCHES,
            [server_id],
        )
    if url:
        endpoint_id = _network_endpoint_node_id(url)
        state.add_node(
            GraphNode(
                id=endpoint_id,
                kind=GraphNodeKind.NETWORK_ENDPOINT,
                label=url,
                source_fact_ids=[server_id],
                metadata={"url": url},
            )
        )
        _add_edge(
            state,
            server_id,
            endpoint_id,
            GraphEdgeKind.SENDS_TO,
            [server_id],
        )


def _add_credential_ref(
    state: _GraphState,
    name: str,
    source: EvidenceLocation,
    *,
    provider: str | None,
    scope_hint: str | None,
    attached_to: str | None,
) -> None:
    line = source.line_start or 0
    fact_id = f"credential-ref:{source.path}:{line}:{name}"
    credential_node_id = _credential_node_id(name)
    state.add_fact(
        Fact(
            id=fact_id,
            kind=FactKind.CREDENTIAL_REF,
            name=name,
            source=source,
            attributes={
                "provider": provider,
                "scope_hint": scope_hint,
                "attached_to": attached_to,
            },
        )
    )
    state.add_node(
        GraphNode(
            id=credential_node_id,
            kind=GraphNodeKind.CREDENTIAL_REF,
            label=name,
            source_fact_ids=[fact_id],
            metadata={
                "provider": provider,
                "scope_hint": scope_hint,
            },
        )
    )

    if attached_to and attached_to.startswith("mcp-server:"):
        _add_edge(
            state,
            attached_to,
            credential_node_id,
            GraphEdgeKind.RECEIVES_CREDENTIAL,
            [fact_id],
        )
    else:
        _add_edge(
            state,
            _file_node_id(source.path),
            credential_node_id,
            GraphEdgeKind.USES,
            [fact_id],
        )


def _add_finding_context(state: _GraphState, finding: Finding) -> Finding:
    if not finding.evidence:
        return finding

    if finding.category == FindingCategory.PROMPT_RISK:
        fact_id = _add_prompt_finding(state, finding)
        return _finding_with_fact(finding, fact_id)

    if finding.rule_id.startswith("ci-"):
        fact_id = _add_ci_finding(state, finding)
        return _finding_with_fact(finding, fact_id)

    return finding


def _add_prompt_finding(state: _GraphState, finding: Finding) -> str:
    evidence = finding.evidence[0]
    line = evidence.line_start or 0
    fact_id = f"prompt-instruction:{evidence.path}:{line}:{finding.rule_id}"
    instruction_node_id = f"instruction:{evidence.path}:{line}:{finding.rule_id}"
    state.add_fact(
        Fact(
            id=fact_id,
            kind=FactKind.PROMPT_INSTRUCTION,
            name=finding.title,
            source=evidence,
            attributes={
                "rule_id": finding.rule_id,
                "severity": finding.severity,
            },
        )
    )
    state.add_node(
        GraphNode(
            id=instruction_node_id,
            kind=GraphNodeKind.INSTRUCTION,
            label=finding.title,
            source_fact_ids=[fact_id],
            metadata={
                "rule_id": finding.rule_id,
                "severity": finding.severity,
            },
        )
    )
    _add_edge(
        state,
        _file_node_id(evidence.path),
        instruction_node_id,
        GraphEdgeKind.INFLUENCED_BY,
        [fact_id],
    )
    return fact_id


def _add_ci_finding(state: _GraphState, finding: Finding) -> str:
    evidence = finding.evidence[0]
    line = evidence.line_start or 0
    fact_id = f"workflow:{evidence.path}:{line}:{finding.rule_id}"
    workflow_node_id = _workflow_node_id(evidence.path)
    state.add_fact(
        Fact(
            id=fact_id,
            kind=FactKind.WORKFLOW,
            name=finding.title,
            source=evidence,
            attributes={
                "rule_id": finding.rule_id,
                "severity": finding.severity,
                "workflow_event": evidence.workflow_event,
                "workflow_job": evidence.workflow_job,
                "permission_scope": evidence.permission_scope,
                "secret_name": evidence.secret_name,
                "context_note": evidence.context_note,
            },
        )
    )
    state.add_node(
        GraphNode(
            id=workflow_node_id,
            kind=GraphNodeKind.CI_WORKFLOW,
            label=evidence.path,
            source_fact_ids=[fact_id],
            metadata={"workflow_path": evidence.path},
        )
    )
    _add_edge(
        state,
        _file_node_id(evidence.path),
        workflow_node_id,
        GraphEdgeKind.RUNS_IN,
        [fact_id],
    )
    return fact_id


def _finding_with_fact(finding: Finding, fact_id: str) -> Finding:
    return finding.model_copy(
        update={
            "source_fact_ids": sorted(set(finding.source_fact_ids) | {fact_id})
        }
    )


def _add_edge(
    state: _GraphState,
    source_id: str,
    target_id: str,
    kind: GraphEdgeKind,
    source_fact_ids: list[str],
) -> None:
    edge_id = f"edge:{source_id}:{kind.value}:{target_id}"
    state.add_edge(
        GraphEdge(
            id=edge_id,
            source_id=source_id,
            target_id=target_id,
            kind=kind,
            source_fact_ids=sorted(source_fact_ids),
        )
    )


def _file_fact_id(path: str) -> str:
    return f"file:{path}"


def _file_node_id(path: str) -> str:
    return f"file:{path}"


def _credential_node_id(name: str) -> str:
    return f"credential-ref:{name}"


def _workflow_node_id(path: str) -> str:
    return f"workflow:{path}"


def _network_endpoint_node_id(url: str) -> str:
    return f"network-endpoint:{url}"


def _path_from_prefixed_id(value: str, prefix: str) -> str | None:
    expected = f"{prefix}:"
    if not value.startswith(expected):
        return None
    remainder = value.removeprefix(expected)
    if ":" not in remainder:
        return None
    path, _name = remainder.rsplit(":", 1)
    return path or None
