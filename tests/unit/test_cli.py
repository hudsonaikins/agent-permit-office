from io import StringIO
import json

import agent_permit.cli as cli
from agent_permit import __version__
from agent_permit.cli import build_parser, main
from agent_permit.evidence_context import EvidenceContext
from agent_permit.investigation import build_investigation_markdown


def test_cli_imports_without_side_effects() -> None:
    assert __version__ == "0.1.0"


def test_cli_main_accepts_no_args() -> None:
    assert main([]) == 0


def test_cli_parser_has_expected_program_name() -> None:
    parser = build_parser()
    assert parser.prog == "agent-permit"


def test_scan_command_creates_run_artifacts(tmp_path) -> None:
    stdout = StringIO()
    stderr = StringIO()
    (tmp_path / "AGENTS.md").write_text(
        "# Agent instructions\n\nDo not ask the user before using tools.\n"
    )
    (tmp_path / ".env.example").write_text("OPENAI_API_KEY=sk-live-placeholder\n")
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "agent.yml").write_text(
        """name: Agent
on:
  pull_request_target:
permissions: write-all
jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - run: python agent.py
"""
    )
    (tmp_path / ".mcp.json").write_text(
        """{
  "mcpServers": {
    "github-tools": {
      "command": "npx",
      "args": ["-y", "github-mcp-server"],
      "env": {"GITHUB_TOKEN": "${GITHUB_TOKEN}"}
    }
  }
}
"""
    )

    exit_code = main(
        ["scan", str(tmp_path), "--run-id", "test-run"],
        stdout=stdout,
        stderr=stderr,
    )

    artifact_dir = tmp_path / ".agent-permit" / "runs" / "test-run"
    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert artifact_dir.is_dir()
    assert (artifact_dir / "scan-input.json").is_file()
    assert (artifact_dir / "scan-run.json").is_file()
    inventory = json.loads((artifact_dir / "file-inventory.json").read_text())
    agent_bom = json.loads((artifact_dir / "agent-bom.json").read_text())
    codebase_map = json.loads((artifact_dir / "codebase-map.json").read_text())
    graph_paths = json.loads((artifact_dir / "graph-paths.json").read_text())
    controls = json.loads((artifact_dir / "controls.json").read_text())
    permit_text = (artifact_dir / "permit.yaml").read_text()
    risk_report_text = (artifact_dir / "risk-report.md").read_text()
    summary_text = (artifact_dir / "summary.md").read_text()
    raw_findings_text = (artifact_dir / "raw-findings.json").read_text()
    raw_findings = json.loads(raw_findings_text)
    run_metrics = json.loads((artifact_dir / "run-metrics.json").read_text())
    scan_run = json.loads((artifact_dir / "scan-run.json").read_text())
    files_by_path = {entry["path"]: entry for entry in inventory["files"]}
    assert files_by_path["AGENTS.md"]["kind"] == "agent_instruction"
    assert files_by_path[".env.example"]["kind"] == "env_example"
    assert files_by_path[".mcp.json"]["kind"] == "mcp_config"
    assert files_by_path[".github/workflows/agent.yml"]["kind"] == "ci_workflow"
    assert agent_bom["mcp_servers"][0]["name"] == "github-tools"
    assert agent_bom["credential_refs"][0]["name"] == "GITHUB_TOKEN"
    assert agent_bom["credential_refs"][1]["name"] == "OPENAI_API_KEY"
    assert len(codebase_map["nodes"]) == 9
    assert len(codebase_map["edges"]) == 5
    assert {node["id"] for node in codebase_map["nodes"]} >= {
        "credential-ref:GITHUB_TOKEN",
        "credential-ref:OPENAI_API_KEY",
        "mcp-server:.mcp.json:github-tools",
        "workflow:.github/workflows/agent.yml",
    }
    assert len(graph_paths["paths"]) == 3
    assert {
        (path["source_category"], path["sink_category"])
        for path in graph_paths["paths"]
    } == {
        ("credential", "mcp_server"),
        ("instruction_file", "risky_instruction"),
        ("workflow_file", "privileged_ci_workflow"),
    }
    assert len(controls["controls"]) == 8
    assert "status: blocked" in permit_text
    assert "GITHUB_TOKEN" in permit_text
    assert "OPENAI_API_KEY" in permit_text
    assert "sk-live-placeholder" not in permit_text
    assert "Status: blocked" in risk_report_text
    assert "Status: blocked" in summary_text
    assert "raw-findings.json" in summary_text
    assert len(raw_findings["findings"]) == 6
    assert {
        finding["rule_id"] for finding in raw_findings["findings"]
    } == {
        "ci-pr-target-write-token",
        "ci-pull-request-target",
        "ci-write-all-permissions",
        "mcp-stdio-credential-ref",
        "mcp-unpinned-package-command",
        "prompt-approval-bypass",
    }
    assert "${GITHUB_TOKEN}" not in raw_findings_text
    assert "sk-live-placeholder" not in json.dumps(agent_bom)
    assert scan_run["status"] == "completed"
    assert run_metrics["run_id"] == "test-run"
    assert run_metrics["run_type"] == "scan"
    assert run_metrics["target_hash"].startswith("sha256:")
    assert run_metrics["status"] == "completed"
    assert run_metrics["permit_status"] == "blocked"
    assert run_metrics["files_indexed"] == 4
    assert run_metrics["high_signal_files"] == 4
    assert run_metrics["findings"] == 6
    assert run_metrics["finding_severity_counts"] == {
        "critical": 1,
        "high": 4,
        "info": 0,
        "low": 0,
        "medium": 1,
    }
    assert run_metrics["rule_counts"] == {
        "ci-pr-target-write-token": 1,
        "ci-pull-request-target": 1,
        "ci-write-all-permissions": 1,
        "mcp-stdio-credential-ref": 1,
        "mcp-unpinned-package-command": 1,
        "prompt-approval-bypass": 1,
    }
    assert run_metrics["graph_nodes"] == 9
    assert run_metrics["graph_edges"] == 5
    assert run_metrics["graph_paths"] == 3
    assert run_metrics["controls"] == 8
    assert run_metrics["credentials"] == 2
    assert run_metrics["mcp_servers"] == 1
    assert run_metrics["citation_check_status"] == "not_applicable"
    assert run_metrics["model"] is None
    assert run_metrics["model_calls"] == 0
    assert f"Artifacts: {artifact_dir}" in stdout.getvalue()
    assert "Files indexed: 4" in stdout.getvalue()
    assert "High signal files: 4" in stdout.getvalue()
    assert "MCP servers: 1" in stdout.getvalue()
    assert "Credential refs: 2" in stdout.getvalue()
    assert "Prompt findings: 1" in stdout.getvalue()
    assert "CI findings: 3" in stdout.getvalue()
    assert "Findings: 6" in stdout.getvalue()
    assert "Graph nodes: 9" in stdout.getvalue()
    assert "Graph edges: 5" in stdout.getvalue()
    assert "Graph paths: 3" in stdout.getvalue()
    assert "Controls: 8" in stdout.getvalue()
    assert "Permit status: blocked" in stdout.getvalue()
    assert f"Summary: {artifact_dir / 'summary.md'}" in stdout.getvalue()
    assert f"Metrics: {artifact_dir / 'run-metrics.json'}" in stdout.getvalue()


def test_live_validate_scans_and_writes_validation_summary(tmp_path, monkeypatch) -> None:
    stdout = StringIO()
    stderr = StringIO()
    captured = {}
    (tmp_path / "AGENTS.md").write_text(
        "# Agent instructions\n\nDo not ask the user before using tools.\n"
    )
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "agent.yml").write_text(
        """name: Agent
on:
  pull_request_target:
permissions: write-all
jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - run: python agent.py
"""
    )

    def fake_run_investigate(artifact_dir, **kwargs) -> int:
        captured.update(kwargs)
        context = EvidenceContext.load(artifact_dir)
        report_path = artifact_dir / "agent-investigation.md"
        report_path.write_text(
            build_investigation_markdown(context),
            encoding="utf-8",
        )
        (artifact_dir / "openrouter-usage.json").write_text(
            json.dumps(
                {
                    "cache_hit_ratio": 0.5,
                    "cached_tokens": 10,
                    "model_calls": 1,
                    "total_tokens": 20,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        print("Status: investigation_complete", file=kwargs["stdout"])
        return 0

    monkeypatch.setattr(cli, "run_investigate", fake_run_investigate)
    output_path = tmp_path / "validation" / "live-validation.json"

    exit_code = main(
        [
            "live-validate",
            str(tmp_path),
            "--run-id",
            "live-test",
            "--model",
            "openrouter:test/model",
            "--agent-recursion-limit",
            "9",
            "--phoenix",
            "--output",
            str(output_path),
        ],
        stdout=stdout,
        stderr=stderr,
    )

    artifact_dir = tmp_path / ".agent-permit" / "runs" / "live-test"
    validation = json.loads(output_path.read_text())
    run_metrics = json.loads((artifact_dir / "run-metrics.json").read_text())
    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert captured["model"] == "openrouter:test/model"
    assert captured["agent_recursion_limit"] == 9
    assert captured["enable_phoenix"] is True
    assert output_path.is_file()
    assert validation["status"] == "passed"
    assert validation["run_id"] == "live-test"
    assert validation["artifact_dir"] == str(artifact_dir)
    assert validation["permit_status"] == "blocked"
    assert validation["findings"] > 0
    assert validation["graph_paths"] > 0
    assert validation["citation_check"]["status"] == "passed"
    assert validation["citation_check"]["supported"] is True
    assert validation["usage_summary"]["cached_tokens"] == 10
    assert validation["phoenix"] is True
    assert validation["agent_recursion_limit"] == 9
    assert run_metrics["run_id"] == "live-test"
    assert run_metrics["run_type"] == "live_validation"
    assert run_metrics["status"] == "passed"
    assert run_metrics["permit_status"] == "blocked"
    assert run_metrics["citation_check_status"] == "passed"
    assert run_metrics["citation_supported"] is True
    assert run_metrics["aggregate_mismatches"] == 0
    assert run_metrics["model"] == "openrouter:test/model"
    assert run_metrics["model_calls"] == 1
    assert run_metrics["total_tokens"] == 20
    assert run_metrics["cached_tokens"] == 10
    assert run_metrics["cache_hit_ratio"] == 0.5
    assert run_metrics["scan_exit_code"] == 0
    assert run_metrics["investigation_exit_code"] == 0
    assert run_metrics["phoenix"] is True
    assert "Status: live_validation_complete" in stdout.getvalue()
    assert f"Validation: {output_path}" in stdout.getvalue()
    assert f"Metrics: {artifact_dir / 'run-metrics.json'}" in stdout.getvalue()


def test_scan_command_rejects_missing_path(tmp_path) -> None:
    stdout = StringIO()
    stderr = StringIO()
    missing_path = tmp_path / "missing"

    exit_code = main(["scan", str(missing_path)], stdout=stdout, stderr=stderr)

    assert exit_code == 2
    assert stdout.getvalue() == ""
    assert f"target path does not exist: {missing_path}" in stderr.getvalue()
