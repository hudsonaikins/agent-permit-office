import json
from pathlib import Path

from agent_permit.capability_graph import CapabilityGraphBuilder
from agent_permit.path_finder import CapabilityPathFinder
from agent_permit.permit_engine import PermitEngine
from agent_permit.scanners.ci_workflows import CiWorkflowScanner
from agent_permit.scanners.credential_refs import CredentialReferenceScanner
from agent_permit.scanners.file_inventory import FileInventoryScanner
from agent_permit.scanners.mcp_config import McpConfigScanner
from agent_permit.scanners.prompt_instructions import PromptInstructionScanner


FIXTURES_DIR = Path(__file__).parents[1] / "fixtures"


def test_permit_engine_maps_fixture_statuses(tmp_path) -> None:
    expected_status_by_fixture = {
        fixture_path.name: json.loads((fixture_path / "fixture.json").read_text())[
            "expected_permit_status"
        ]
        for fixture_path in FIXTURES_DIR.iterdir()
        if fixture_path.is_dir()
    }

    for fixture_name, expected_status in expected_status_by_fixture.items():
        target = FIXTURES_DIR / fixture_name
        evaluation = _evaluate_repo(target, tmp_path / fixture_name)

        assert evaluation.permit.status == expected_status


def test_permit_engine_records_credentials_and_controls_without_values(tmp_path) -> None:
    target = FIXTURES_DIR / "risky-mcp-agent"
    evaluation = _evaluate_repo(target, tmp_path / "risky-mcp")
    payload = (
        evaluation.permit.model_dump_json()
        + evaluation.controls.model_dump_json()
        + evaluation.risk_report_markdown
    )

    assert evaluation.permit.status == "needs_review"
    assert evaluation.permit.discovered_credentials == ["GITHUB_TOKEN"]
    assert evaluation.permit.required_approvals
    assert {control.status for control in evaluation.controls.controls} >= {
        "missing",
        "weak",
    }
    assert "${GITHUB_TOKEN}" not in payload


def test_permit_engine_blocks_critical_prompt_and_ci_risks(tmp_path) -> None:
    poisoned = _evaluate_repo(FIXTURES_DIR / "poisoned-instructions", tmp_path / "poisoned")
    risky_ci = _evaluate_repo(FIXTURES_DIR / "risky-ci-agent", tmp_path / "risky-ci")

    assert poisoned.permit.status == "blocked"
    assert "run agent with poisoned instruction file" in poisoned.permit.forbidden_actions
    assert risky_ci.permit.status == "blocked"
    assert "run agent workflow in privileged CI context" in risky_ci.permit.forbidden_actions


def test_permit_finding_summary_counts_findings_only(tmp_path) -> None:
    evaluation = _evaluate_repo(FIXTURES_DIR / "risky-ci-agent", tmp_path / "risky-ci")

    assert len(evaluation.controls.controls) == 5
    assert len(evaluation.permit.findings_summary) == 3
    assert evaluation.permit.findings_summary == {
        "critical": 1,
        "high": 2,
        "medium": 1,
    }


def test_permit_engine_approves_medium_only_remote_mcp_with_conditions(tmp_path) -> None:
    target = tmp_path / "remote-mcp"
    target.mkdir()
    (target / "mcp.json").write_text(
        """{
  "servers": {
    "docs": {
      "url": "https://example.com/mcp"
    }
  }
}
"""
    )

    evaluation = _evaluate_repo(target, tmp_path / "remote-artifacts")

    assert evaluation.permit.status == "approved_with_conditions"
    assert evaluation.permit.conditions == [
        "Repository MCP config can route tool traffic to a network endpoint."
    ]


def test_permit_engine_needs_review_for_ci_secret_without_pr_target(tmp_path) -> None:
    target = tmp_path / "ci-secret"
    workflow_dir = target / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "agent.yml").write_text(
        """name: Agent
on:
  pull_request:
permissions:
  contents: write
jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - run: echo "${{ secrets.AGENT_TOKEN }}"
"""
    )

    evaluation = _evaluate_repo(target, tmp_path / "ci-secret-artifacts")

    assert evaluation.permit.status == "needs_review"
    assert "run agent workflow in privileged CI context" in (
        evaluation.permit.forbidden_actions
    )


def _evaluate_repo(target: Path, artifact_dir: Path):
    scan_run_id = f"run-{target.name}"
    inventory = FileInventoryScanner().scan(target, scan_run_id=scan_run_id)
    mcp_result = McpConfigScanner().scan(
        target,
        scan_run_id=scan_run_id,
        inventory=inventory,
    )
    credential_refs = CredentialReferenceScanner().scan(
        target,
        scan_run_id=scan_run_id,
        inventory=inventory,
    )
    mcp_result.agent_bom.credential_refs.extend(credential_refs)
    findings = [
        *mcp_result.findings,
        *PromptInstructionScanner().scan(
            target,
            scan_run_id=scan_run_id,
            inventory=inventory,
        ),
        *CiWorkflowScanner().scan(
            target,
            scan_run_id=scan_run_id,
            inventory=inventory,
        ),
    ]
    graph_result = CapabilityGraphBuilder().build(
        scan_run_id=scan_run_id,
        inventory=inventory,
        agent_bom=mcp_result.agent_bom,
        findings=findings,
    )
    graph_path_report = CapabilityPathFinder().find_paths(graph_result.codebase_map)
    return PermitEngine().evaluate(
        scan_run_id=scan_run_id,
        artifact_dir=artifact_dir,
        agent_bom=mcp_result.agent_bom,
        findings=graph_result.findings,
        graph_paths=graph_path_report,
    )
