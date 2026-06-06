from io import StringIO
import json

from agent_permit.cli import main


def test_scan_auto_loads_default_policy_for_trusted_workflow_permission(tmp_path) -> None:
    _write_workflow(
        tmp_path,
        """name: Review
on:
  pull_request:
permissions:
  contents: write
jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - run: python agent.py
""",
    )
    (tmp_path / "agent-permit-policy.json").write_text(
        json.dumps(
            {
                "trusted_workflow_permissions": [
                    {
                        "path": ".github/workflows/agent.yml",
                        "event": "pull_request",
                        "scope": "contents",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(
        ["scan", str(tmp_path), "--run-id", "policy-ci", "--ci"],
        stdout=stdout,
        stderr=stderr,
    )

    artifact_dir = tmp_path / ".agent-permit" / "runs" / "policy-ci"
    raw_findings = json.loads((artifact_dir / "raw-findings.json").read_text())
    policy_eval = json.loads((artifact_dir / "policy-evaluation.json").read_text())
    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert "Permit status: approved_with_conditions" in stdout.getvalue()
    assert "Policy adjustments: 1" in stdout.getvalue()
    assert raw_findings["findings"][0]["severity"] == "low"
    assert raw_findings["findings"][0]["requires_human_review"] is False
    assert policy_eval["adjustments"][0]["action"] == "trusted_workflow_permission"


def test_scan_policy_allows_named_mcp_server_but_keeps_condition(tmp_path) -> None:
    (tmp_path / ".mcp.json").write_text(
        """{
  "mcpServers": {
    "github-tools": {
      "command": "node",
      "args": ["server.js"],
      "env": {
        "GITHUB_TOKEN": "${GITHUB_TOKEN}"
      }
    }
  }
}
""",
        encoding="utf-8",
    )
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(
        json.dumps({"allowed_mcp_servers": ["github-tools"]}),
        encoding="utf-8",
    )
    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(
        [
            "scan",
            str(tmp_path),
            "--run-id",
            "policy-mcp",
            "--ci",
            "--policy",
            str(policy_path),
        ],
        stdout=stdout,
        stderr=stderr,
    )

    artifact_dir = tmp_path / ".agent-permit" / "runs" / "policy-mcp"
    raw_findings = json.loads((artifact_dir / "raw-findings.json").read_text())
    graph_paths = json.loads((artifact_dir / "graph-paths.json").read_text())
    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert "Permit status: approved_with_conditions" in stdout.getvalue()
    assert raw_findings["findings"][0]["rule_id"] == "mcp-stdio-credential-ref"
    assert raw_findings["findings"][0]["severity"] == "low"
    assert graph_paths["paths"][0]["severity"] == "low"
    assert "${GITHUB_TOKEN}" not in json.dumps(raw_findings)


def test_scan_policy_approves_secret_reference_outside_pr_target(tmp_path) -> None:
    _write_workflow(
        tmp_path,
        """name: Review
on:
  pull_request:
jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - run: echo "${{ secrets.REVIEW_TOKEN }}"
""",
    )
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(
        json.dumps({"approved_credential_refs": ["REVIEW_TOKEN"]}),
        encoding="utf-8",
    )
    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(
        [
            "scan",
            str(tmp_path),
            "--run-id",
            "policy-secret",
            "--ci",
            "--policy",
            str(policy_path),
        ],
        stdout=stdout,
        stderr=stderr,
    )

    artifact_dir = tmp_path / ".agent-permit" / "runs" / "policy-secret"
    raw_findings = json.loads((artifact_dir / "raw-findings.json").read_text())
    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert "Permit status: approved_with_conditions" in stdout.getvalue()
    assert raw_findings["findings"][0]["severity"] == "low"
    assert raw_findings["findings"][0]["requires_human_review"] is False


def test_scan_policy_rejects_invalid_file(tmp_path) -> None:
    (tmp_path / "agent.py").write_text("print('safe')\n", encoding="utf-8")
    policy_path = tmp_path / "policy.json"
    policy_path.write_text("{bad json\n", encoding="utf-8")
    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(
        ["scan", str(tmp_path), "--policy", str(policy_path)],
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 2
    assert stdout.getvalue() == ""
    assert "failed to load policy" in stderr.getvalue()


def _write_workflow(tmp_path, text: str) -> None:
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "agent.yml").write_text(text, encoding="utf-8")
