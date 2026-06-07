from contextlib import contextmanager
from io import StringIO
import shutil
import sys
import types
from pathlib import Path

import pytest

from agent_permit import observability
from agent_permit.cli import main
from agent_permit.deep_agent import (
    DEEP_AGENT_SYSTEM_PROMPT,
    build_evidence_tools,
    build_subagent_specs,
    invoke_deep_agent_investigator_with_metadata,
    summarize_openrouter_usage,
    _strip_final_report_sentinel,
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
    assert critic.aggregate_mismatches == ()
    assert "[rule:mcp-stdio-credential-ref]" in report
    assert "Permit status: `needs_review`" in report
    assert "Finding severity counts: critical=0, high=1, medium=1, low=0, info=0" in report


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


def test_critic_rejects_wrong_aggregate_severity_counts(tmp_path) -> None:
    artifact_dir = _scan_fixture(tmp_path, "risky-ci-agent", "aggregate-mismatch")
    context = EvidenceContext.load(artifact_dir)
    report = (
        "# Bad Aggregate Report\n\n"
        "Scan produced 4 findings: 1 critical, 3 high, 1 medium. "
        "[artifact:raw-findings.json]\n\n"
        "The critical rule is ci-pr-target-write-token. "
        "[rule:ci-pr-target-write-token]\n"
    )

    critic = critique_investigation_report(context, report)

    assert critic.supported is False
    assert critic.aggregate_mismatches == ("high: claimed 3, expected 2",)


def test_investigate_cli_requires_openrouter_for_default_product_path(
    tmp_path,
    monkeypatch,
) -> None:
    artifact_dir = _scan_fixture(tmp_path, "risky-ci-agent", "cli-investigate-live")
    stdout = StringIO()
    stderr = StringIO()
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    exit_code = main(
        ["investigate", str(artifact_dir)],
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 2
    assert stdout.getvalue() == ""
    assert "OPENROUTER_API_KEY" in stderr.getvalue()


def test_investigate_cli_writes_deterministic_report_when_explicit(tmp_path) -> None:
    artifact_dir = _scan_fixture(tmp_path, "risky-ci-agent", "cli-investigate")
    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(
        ["investigate", str(artifact_dir), "--deterministic-only"],
        stdout=stdout,
        stderr=stderr,
    )

    report_path = artifact_dir / "agent-investigation.md"
    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert report_path.is_file()
    assert "Citation check: passed" in stdout.getvalue()
    assert "ci-pr-target-write-token" in report_path.read_text()


def test_investigate_cli_skips_phoenix_for_deterministic_report(tmp_path) -> None:
    artifact_dir = _scan_fixture(tmp_path, "risky-ci-agent", "cli-phoenix-skip")
    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(
        ["investigate", str(artifact_dir), "--deterministic-only", "--phoenix"],
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert "Phoenix tracing: skipped in deterministic mode" in stdout.getvalue()


def test_phoenix_collector_endpoint_normalizes_ui_base_url() -> None:
    assert observability.normalize_phoenix_collector_endpoint(
        "http://localhost:6006"
    ) == "http://localhost:6006/v1/traces"
    assert observability.normalize_phoenix_collector_endpoint(
        "http://localhost:6006/v1/traces"
    ) == "http://localhost:6006/v1/traces"


def test_phoenix_tracing_config_is_idempotent(monkeypatch) -> None:
    calls = []
    phoenix_module = types.ModuleType("phoenix")
    otel_module = types.ModuleType("phoenix.otel")

    def fake_register(**kwargs):
        calls.append(kwargs)

    otel_module.register = fake_register
    monkeypatch.setitem(sys.modules, "phoenix", phoenix_module)
    monkeypatch.setitem(sys.modules, "phoenix.otel", otel_module)
    monkeypatch.setattr(observability, "_PHOENIX_TRACING_CONFIG", None)

    first = observability.configure_phoenix_tracing(endpoint="http://localhost:6006")
    second = observability.configure_phoenix_tracing(
        endpoint="http://localhost:6006/v1/traces"
    )

    assert first == second
    assert len(calls) == 1
    assert calls[0]["endpoint"] == "http://localhost:6006/v1/traces"


def test_deep_agent_tools_and_subagents_are_artifact_bounded(tmp_path) -> None:
    artifact_dir = _scan_fixture(tmp_path, "risky-mcp-agent", "deep-agent-spec")
    context = EvidenceContext.load(artifact_dir)

    tools = build_evidence_tools(context)
    subagents = build_subagent_specs(context)
    tool_names = {tool.__name__ for tool in tools}

    assert "execute shell commands" in DEEP_AGENT_SYSTEM_PROMPT
    assert "Every mention of a scanner rule ID" in DEEP_AGENT_SYSTEM_PROMPT
    assert "aggregate finding severity counts" in DEEP_AGENT_SYSTEM_PROMPT
    assert "Do not write preamble" in DEEP_AGENT_SYSTEM_PROMPT
    assert "Never write literal citation templates" in DEEP_AGENT_SYSTEM_PROMPT
    assert tool_names >= {
        "list_evidence_artifacts",
        "read_evidence_artifact",
        "summarize_evidence_context",
        "list_citation_ids",
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


def test_live_deep_agent_rejects_too_low_recursion_limit(tmp_path) -> None:
    artifact_dir = _scan_fixture(tmp_path, "safe-agent", "low-recursion")
    context = EvidenceContext.load(artifact_dir)

    with pytest.raises(RuntimeError, match="recursion limit"):
        invoke_deep_agent_investigator_with_metadata(
            context,
            model="openrouter:sonnet-4.6",
            recursion_limit=1,
        )


def test_evidence_tools_emit_observability_metadata(tmp_path, monkeypatch) -> None:
    artifact_dir = _scan_fixture(tmp_path, "risky-mcp-agent", "tool-tracing")
    context = EvidenceContext.load(artifact_dir)
    events: list[tuple[str, dict[str, object]] | tuple[str, int]] = []

    @contextmanager
    def fake_trace_evidence_tool_call(**kwargs):
        events.append(("start", kwargs))
        yield object()

    def fake_record_result(_span: object, result: object) -> None:
        events.append(("result", len(str(result))))

    monkeypatch.setattr(
        observability,
        "trace_evidence_tool_call",
        fake_trace_evidence_tool_call,
    )
    monkeypatch.setattr(
        observability,
        "record_evidence_tool_result",
        fake_record_result,
    )
    tools = build_evidence_tools(context)
    summarize = next(
        tool
        for tool in tools
        if tool.__name__ == "summarize_evidence_context"
    )

    result = summarize()

    assert "permit_status: needs_review" in result
    assert events[0][0] == "start"
    assert events[0][1]["tool_name"] == "summarize_evidence_context"
    assert events[0][1]["scan_run_id"] == "tool-tracing"
    assert events[0][1]["permit_status"] == "needs_review"
    assert events[0][1]["input_metadata"] == {
        "arg_count": 0,
        "kwarg_keys": "none",
    }
    assert events[1][0] == "result"
    assert events[1][1] > 0


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


def test_openrouter_usage_summary_tracks_cache_metrics() -> None:
    class FakeMessage:
        usage_metadata = {
            "input_tokens": 1000,
            "output_tokens": 200,
            "total_tokens": 1200,
            "input_token_details": {
                "cached_tokens": 750,
                "cache_write_tokens": 100,
            },
        }
        response_metadata = {"id": "gen-test"}

    summary = summarize_openrouter_usage({"messages": [FakeMessage()]})

    assert summary == {
        "model_calls": 1,
        "input_tokens": 1000,
        "output_tokens": 200,
        "total_tokens": 1200,
        "cached_tokens": 750,
        "cache_write_tokens": 100,
        "generation_ids": ["gen-test"],
        "cache_hit_ratio": 0.75,
    }


def test_final_report_sentinel_is_required_and_stripped() -> None:
    assert _strip_final_report_sentinel("# Report\n\nEND_OF_REPORT") == "# Report\n"
    with pytest.raises(RuntimeError, match="END_OF_REPORT"):
        _strip_final_report_sentinel("# Report")


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
