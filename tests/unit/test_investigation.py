from io import StringIO
import shutil
from pathlib import Path

import pytest

from agent_permit.cli import main
from agent_permit.deep_agent import (
    DEEP_AGENT_SYSTEM_PROMPT,
    build_evidence_tools,
    build_subagent_specs,
)
from agent_permit.evidence_context import EvidenceContext
from agent_permit.investigation import (
    build_investigation_markdown,
    critique_investigation_report,
)


FIXTURES_DIR = Path(__file__).parents[1] / "fixtures"


def test_evidence_context_loads_bounded_artifacts(tmp_path) -> None:
    artifact_dir = _scan_fixture(tmp_path, "risky-ci-agent", "evidence-ci")

    context = EvidenceContext.load(artifact_dir)

    assert context.permit_status == "blocked"
    assert len(context.findings) == 4
    assert "summary.md" in context.list_artifacts()
    assert "codebase-map.json" not in context.list_artifacts()
    assert "ci-pr-target-write-token" in context.read_artifact("raw-findings.json")
    with pytest.raises(PermissionError):
        context.read_artifact("codebase-map.json")


def test_investigation_report_uses_supported_citations(tmp_path) -> None:
    artifact_dir = _scan_fixture(tmp_path, "risky-mcp-agent", "evidence-mcp")
    context = EvidenceContext.load(artifact_dir)

    report = build_investigation_markdown(context)
    critic = critique_investigation_report(context, report)

    assert critic.supported is True
    assert "[rule:mcp-stdio-credential-ref]" in report
    assert "Permit status: `needs_review`" in report


def test_critic_rejects_invented_claims(tmp_path) -> None:
    artifact_dir = _scan_fixture(tmp_path, "safe-agent", "evidence-safe")
    context = EvidenceContext.load(artifact_dir)
    report = (
        "# Bad Report\n\n"
        "The repo has ci-secret-reference and should be blocked. "
        "[finding:not-real]\n"
    )

    critic = critique_investigation_report(context, report)

    assert critic.supported is False
    assert critic.unsupported_citations == ("finding:not-real",)
    assert critic.unsupported_rule_ids == ("ci-secret-reference",)


def test_investigate_cli_writes_report_without_live_model(tmp_path) -> None:
    artifact_dir = _scan_fixture(tmp_path, "risky-ci-agent", "cli-investigate")
    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(
        ["investigate", str(artifact_dir)],
        stdout=stdout,
        stderr=stderr,
    )

    report_path = artifact_dir / "agent-investigation.md"
    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert report_path.is_file()
    assert "Citation check: passed" in stdout.getvalue()
    assert "ci-pr-target-write-token" in report_path.read_text()


def test_deep_agent_tools_and_subagents_are_artifact_bounded(tmp_path) -> None:
    artifact_dir = _scan_fixture(tmp_path, "risky-mcp-agent", "deep-agent-spec")
    context = EvidenceContext.load(artifact_dir)

    tools = build_evidence_tools(context)
    subagents = build_subagent_specs(context)
    tool_names = {tool.__name__ for tool in tools}

    assert "execute shell commands" in DEEP_AGENT_SYSTEM_PROMPT
    assert tool_names >= {
        "list_evidence_artifacts",
        "read_evidence_artifact",
        "summarize_evidence_context",
        "list_citation_ids",
        "validate_report_citations",
        "get_finding",
        "find_paths",
        "get_agent_bom",
        "get_mcp_servers",
        "get_credential_refs",
        "explain_rule",
    }
    assert {subagent["name"] for subagent in subagents} == {
        "mcp-risk-specialist",
        "prompt-risk-specialist",
        "policy-specialist",
        "citation-critic",
    }
    assert "codebase-map.json" not in tools[0]()


def test_typed_evidence_tools_return_bounded_json(tmp_path) -> None:
    artifact_dir = _scan_fixture(tmp_path, "risky-mcp-agent", "typed-tools")
    context = EvidenceContext.load(artifact_dir)

    assert context.get_finding("mcp-stdio-credential-ref")[0]["rule_id"] == (
        "mcp-stdio-credential-ref"
    )
    assert context.find_paths(
        source_category="credential",
        sink_category="mcp_server",
    )[0]["sink_category"] == "mcp_server"
    assert context.get_agent_bom()["mcp_servers"][0]["name"] == "github-tools"
    assert context.get_mcp_servers()[0]["transport"] == "stdio"
    assert context.get_credential_refs()[0]["name"] == "GITHUB_TOKEN"
    assert context.explain_rule("mcp-stdio-credential-ref") == {
        "rule_id": "mcp-stdio-credential-ref",
        "scanner": "mcp_config",
        "title": "Stdio MCP server receives credential references",
        "default_severity": "high",
        "category": "credential_scope",
    }


def test_evidence_context_parses_json_before_redacting_text(tmp_path) -> None:
    artifact_dir = _scan_fixture(tmp_path, "risky-ci-agent", "json-redaction")
    raw_findings_path = artifact_dir / "raw-findings.json"
    raw_text = raw_findings_path.read_text()
    raw_findings_path.write_text(
        raw_text.replace(
            "permissions: write-all",
            "echo ${{ secrets.CREWAI_TRACING_PROJECT_NAME }}",
        )
    )

    context = EvidenceContext.load(artifact_dir)

    assert len(context.findings) == 4


def _scan_fixture(tmp_path: Path, fixture_name: str, run_id: str) -> Path:
    target = tmp_path / fixture_name
    shutil.copytree(FIXTURES_DIR / fixture_name, target)
    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(
        ["scan", str(target), "--run-id", run_id],
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert stderr.getvalue() == ""
    return target / ".agent-permit" / "runs" / run_id
