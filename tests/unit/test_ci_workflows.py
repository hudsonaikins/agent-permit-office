from pathlib import Path

from agent_permit.scanners.ci_workflows import CiWorkflowScanner
from agent_permit.scanners.file_inventory import FileInventoryScanner


FIXTURES_DIR = Path(__file__).parents[1] / "fixtures"


def test_ci_scanner_flags_risky_pull_request_target_fixture() -> None:
    target = FIXTURES_DIR / "risky-ci-agent"
    inventory = FileInventoryScanner().scan(target, scan_run_id="run-ci")

    findings = CiWorkflowScanner().scan(
        target,
        scan_run_id="run-ci",
        inventory=inventory,
    )

    assert [finding.rule_id for finding in findings] == [
        "ci-pull-request-target",
        "ci-write-all-permissions",
        "ci-secret-reference",
        "ci-pr-target-write-token",
    ]
    assert [finding.severity for finding in findings] == [
        "high",
        "high",
        "medium",
        "critical",
    ]
    assert findings[0].evidence[0].line_start == 4
    assert findings[1].evidence[0].line_start == 7
    assert findings[2].evidence[0].line_start == 16
    assert findings[2].evidence[0].workflow_event == "pull_request_target"
    assert findings[2].evidence[0].workflow_job == "agent-review"
    assert findings[2].evidence[0].secret_name == "GITHUB_TOKEN"
    assert findings[3].evidence[1].permission_scope == "write-all"


def test_ci_scanner_flags_explicit_write_permissions(tmp_path) -> None:
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "agent.yml").write_text(
        """name: Agent
on:
  pull_request:

permissions:
  contents: write
  pull-requests: write
jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - run: python agent.py
"""
    )
    inventory = FileInventoryScanner().scan(tmp_path, scan_run_id="run-write")

    findings = CiWorkflowScanner().scan(
        tmp_path,
        scan_run_id="run-write",
        inventory=inventory,
    )

    assert [finding.rule_id for finding in findings] == [
        "ci-write-permission",
        "ci-write-permission",
    ]
    assert {finding.evidence[0].line_start for finding in findings} == {6, 7}
    assert {finding.evidence[0].workflow_job for finding in findings} == {None}
    assert {finding.evidence[0].permission_scope for finding in findings} == {
        "contents",
        "pull-requests",
    }


def test_ci_scanner_flags_pr_target_head_checkout(tmp_path) -> None:
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "agent.yml").write_text(
        """name: Agent
on:
  pull_request_target:
jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.event.pull_request.head.sha }}
      - run: python agent.py
"""
    )
    inventory = FileInventoryScanner().scan(tmp_path, scan_run_id="run-checkout")

    findings = CiWorkflowScanner().scan(
        tmp_path,
        scan_run_id="run-checkout",
        inventory=inventory,
    )

    assert [finding.rule_id for finding in findings] == [
        "ci-pull-request-target",
        "ci-pr-target-head-checkout",
    ]
    assert findings[1].evidence[2].line_start == 10
    assert findings[1].evidence[1].workflow_job == "review"
    assert findings[1].evidence[2].workflow_job == "review"


def test_ci_scanner_marks_maintenance_workflow_context(tmp_path) -> None:
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "stale.yml").write_text(
        """name: Stale
on:
  schedule:
    - cron: "0 0 * * *"
permissions:
  issues: write
jobs:
  stale:
    runs-on: ubuntu-latest
    steps:
      - run: echo "${{ secrets.STALE_TOKEN }}"
"""
    )
    inventory = FileInventoryScanner().scan(tmp_path, scan_run_id="run-stale")

    findings = CiWorkflowScanner().scan(
        tmp_path,
        scan_run_id="run-stale",
        inventory=inventory,
    )

    assert [finding.rule_id for finding in findings] == [
        "ci-write-permission",
        "ci-secret-reference",
    ]
    assert {finding.confidence for finding in findings} == {"medium"}
    assert all(
        "maintenance-workflow heuristic" in (finding.evidence[0].context_note or "")
        for finding in findings
    )


def test_ci_scanner_leaves_safe_pull_request_workflow_clean(tmp_path) -> None:
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "agent.yml").write_text(
        """name: Safe Review
on:
  pull_request:

permissions:
  contents: read
jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - run: python agent.py
"""
    )
    inventory = FileInventoryScanner().scan(tmp_path, scan_run_id="run-safe")

    findings = CiWorkflowScanner().scan(
        tmp_path,
        scan_run_id="run-safe",
        inventory=inventory,
    )

    assert findings == []
