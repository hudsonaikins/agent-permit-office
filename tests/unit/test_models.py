from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_permit.models import (
    AgentBom,
    AgentSummary,
    CodebaseMap,
    Confidence,
    CredentialRef,
    EvidenceLocation,
    EvidencePack,
    Fact,
    FactKind,
    Finding,
    FindingCategory,
    GraphEdge,
    GraphEdgeKind,
    GraphNode,
    GraphNodeKind,
    McpServerSummary,
    Permit,
    PermitStatus,
    ScanRun,
    ScanRunStatus,
    Severity,
    ToolSummary,
)


def test_safe_schema_examples_serialize_to_json() -> None:
    scan_run = ScanRun(
        id="run-safe",
        target_path=Path("/tmp/safe-agent"),
        artifact_dir=Path("/tmp/safe-agent/.agent-permit/runs/run-safe"),
        status=ScanRunStatus.COMPLETED,
        started_at=datetime(2026, 6, 6, tzinfo=UTC),
        completed_at=datetime(2026, 6, 6, tzinfo=UTC),
    )
    agent_bom = AgentBom(
        scan_run_id=scan_run.id,
        agents=[
            AgentSummary(
                id="agent:safe",
                name="safe-agent",
                framework="langchain",
                source_fact_ids=["fact:agent"],
            )
        ],
        tools=[
            ToolSummary(
                id="tool:read",
                name="read_docs",
                kind="filesystem_read",
                source_fact_ids=["fact:tool"],
            )
        ],
    )
    codebase_map = CodebaseMap(
        scan_run_id=scan_run.id,
        nodes=[
            GraphNode(
                id="agent:safe",
                kind=GraphNodeKind.AGENT,
                label="safe-agent",
                source_fact_ids=["fact:agent"],
            )
        ],
        facts=[
            Fact(
                id="fact:agent",
                kind=FactKind.AGENT,
                name="safe-agent",
                source=EvidenceLocation(path="agent.py", line_start=1, line_end=3),
            )
        ],
    )
    permit = Permit(
        scan_run_id=scan_run.id,
        status=PermitStatus.APPROVED,
        agent_name="safe-agent",
        discovered_tools=["read_docs"],
        findings_summary={Severity.INFO: 0},
        evidence_bundle_path=".agent-permit/runs/run-safe",
    )

    assert '"status":"completed"' in scan_run.model_dump_json()
    assert '"agents"' in agent_bom.model_dump_json()
    assert '"nodes"' in codebase_map.model_dump_json()
    assert '"status":"approved"' in permit.model_dump_json()


def test_risky_schema_examples_serialize_to_json() -> None:
    credential_source = EvidenceLocation(
        path=".mcp.json",
        line_start=10,
        line_end=10,
        redacted_snippet='"GITHUB_TOKEN": "<redacted>"',
    )
    credential_ref = CredentialRef(
        name="GITHUB_TOKEN",
        provider="github",
        scope_hint="unknown_or_broad",
        attached_to="mcp:github",
        source=credential_source,
    )
    finding = Finding(
        id="finding:unpinned-mcp-credential",
        rule_id="APO-MCP-001",
        title="Unpinned stdio MCP receives credential",
        severity=Severity.HIGH,
        category=FindingCategory.MCP_RISK,
        evidence=[credential_source],
        risk="Credential crosses into an unpinned local MCP process.",
        recommendation="Pin the MCP package and use a read-only token.",
        confidence=Confidence.HIGH,
        requires_human_review=True,
        source_fact_ids=["fact:mcp", "fact:credential"],
    )
    evidence_pack = EvidencePack(
        id="evidence:finding:unpinned-mcp-credential",
        finding_id=finding.id,
        summary="Credential ref is passed into an unpinned stdio MCP server.",
        evidence=[credential_source],
        related_fact_ids=finding.source_fact_ids,
    )
    codebase_map = CodebaseMap(
        scan_run_id="run-risky",
        nodes=[
            GraphNode(
                id="mcp:github",
                kind=GraphNodeKind.MCP_SERVER,
                label="github",
                source_fact_ids=["fact:mcp"],
            ),
            GraphNode(
                id="cred:GITHUB_TOKEN",
                kind=GraphNodeKind.CREDENTIAL_REF,
                label="GITHUB_TOKEN",
                source_fact_ids=["fact:credential"],
            ),
        ],
        edges=[
            GraphEdge(
                id="edge:mcp-receives-token",
                source_id="mcp:github",
                target_id="cred:GITHUB_TOKEN",
                kind=GraphEdgeKind.RECEIVES_CREDENTIAL,
                source_fact_ids=["fact:credential"],
            )
        ],
    )
    agent_bom = AgentBom(
        scan_run_id="run-risky",
        mcp_servers=[
            McpServerSummary(
                id="mcp:github",
                name="github",
                transport="stdio",
                command="npx -y github-mcp-server",
            )
        ],
        credential_refs=[credential_ref],
    )
    permit = Permit(
        scan_run_id="run-risky",
        status=PermitStatus.NEEDS_REVIEW,
        agent_name="repo-agent",
        discovered_credentials=["GITHUB_TOKEN"],
        required_approvals=["review MCP package pinning and token scope"],
        findings_summary={Severity.HIGH: 1},
    )

    assert '"severity":"high"' in finding.model_dump_json()
    assert '"redaction_applied":true' in evidence_pack.model_dump_json()
    assert '"receives_credential"' in codebase_map.model_dump_json()
    assert '"GITHUB_TOKEN"' in agent_bom.model_dump_json()
    assert '"needs_review"' in permit.model_dump_json()


def test_secret_values_are_not_representable_by_default() -> None:
    with pytest.raises(ValidationError):
        EvidenceLocation(
            path=".env",
            line_start=1,
            line_end=1,
            snippet="OPENAI_API_KEY=sk-live-secret",
        )

    with pytest.raises(ValidationError):
        CredentialRef(
            name="OPENAI_API_KEY",
            source=EvidenceLocation(path=".env.example", line_start=1),
            secret_value="sk-live-secret",
        )

    with pytest.raises(ValidationError):
        Fact(
            id="fact:bad",
            kind=FactKind.CREDENTIAL_REF,
            name="OPENAI_API_KEY",
            source=EvidenceLocation(path=".env", line_start=1),
            attributes={"secret_value": "sk-live-secret"},
        )

    with pytest.raises(ValidationError):
        GraphNode(
            id="node:bad",
            kind=GraphNodeKind.CREDENTIAL_REF,
            label="OPENAI_API_KEY",
            metadata={"token_value": "sk-live-secret"},
        )

    with pytest.raises(ValidationError):
        EvidencePack(
            id="evidence:bad",
            finding_id="finding:bad",
            summary="bad evidence",
            evidence=[EvidenceLocation(path=".env", line_start=1)],
            redaction_applied=False,
        )

    with pytest.raises(ValidationError):
        Permit(
            scan_run_id="run-bad",
            status=PermitStatus.BLOCKED,
            agent_name="bad-agent",
            discovered_credentials=["OPENAI_API_KEY=sk-live-secret"],
        )


def test_evidence_line_range_must_be_valid() -> None:
    with pytest.raises(ValidationError):
        EvidenceLocation(path="agent.py", line_start=10, line_end=3)
