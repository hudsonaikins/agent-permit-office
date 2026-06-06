from pathlib import Path


REPO_ROOT = Path(__file__).parents[2]


def test_root_composite_action_packages_ci_scan() -> None:
    action_text = (REPO_ROOT / "action.yml").read_text()

    assert "using: composite" in action_text
    assert "astral-sh/setup-uv@v6" in action_text
    assert "actions/upload-artifact@v7" in action_text
    assert "uv run --frozen --directory" in action_text
    assert "agent-permit" in action_text
    assert "--ci" in action_text
    assert "--exclude" in action_text
    assert "--sarif" in action_text
    assert "github/codeql-action/upload-sarif@v4" in action_text
    assert "continue-on-error: true" in action_text
    assert "security-events: write" in action_text
    assert "GITHUB_STEP_SUMMARY" in action_text


def test_dogfood_workflow_uses_safe_pr_event_and_fixture_exclude() -> None:
    workflow_text = (REPO_ROOT / ".github" / "workflows" / "agent-permit.yml").read_text()

    assert "pull_request:" in workflow_text
    assert "pull_request_target" not in workflow_text
    assert "contents: read" in workflow_text
    assert "persist-credentials: false" in workflow_text
    assert "actions/checkout@v6" in workflow_text
    assert "uses: ./" in workflow_text
    assert "tests/fixtures/**" in workflow_text
    assert 'sarif: "true"' in workflow_text
    assert "upload-sarif" not in workflow_text
