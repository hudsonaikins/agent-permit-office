from io import StringIO
import shutil
from pathlib import Path

from agent_permit.cli import main


FIXTURES_DIR = Path(__file__).parents[1] / "fixtures"


def test_ci_mode_exits_zero_for_approved_fixture(tmp_path) -> None:
    target = tmp_path / "safe-agent"
    shutil.copytree(FIXTURES_DIR / "safe-agent", target)
    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(
        ["scan", str(target), "--run-id", "safe-ci", "--ci"],
        stdout=stdout,
        stderr=stderr,
    )

    artifact_dir = target / ".agent-permit" / "runs" / "safe-ci"
    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert "CI mode: on" in stdout.getvalue()
    assert "Permit status: approved" in stdout.getvalue()
    assert (artifact_dir / "summary.md").is_file()


def test_ci_mode_exits_one_for_blocked_fixture(tmp_path) -> None:
    target = tmp_path / "risky-ci-agent"
    shutil.copytree(FIXTURES_DIR / "risky-ci-agent", target)
    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(
        ["scan", str(target), "--run-id", "blocked-ci", "--ci"],
        stdout=stdout,
        stderr=stderr,
    )

    artifact_dir = target / ".agent-permit" / "runs" / "blocked-ci"
    summary_text = (artifact_dir / "summary.md").read_text()
    assert exit_code == 1
    assert stderr.getvalue() == ""
    assert "CI mode: on" in stdout.getvalue()
    assert "Permit status: blocked" in stdout.getvalue()
    assert "ci-pr-target-write-token" in summary_text


def test_ci_mode_exits_one_for_needs_review_fixture(tmp_path) -> None:
    target = tmp_path / "risky-mcp-agent"
    shutil.copytree(FIXTURES_DIR / "risky-mcp-agent", target)
    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(
        ["scan", str(target), "--run-id", "review-ci", "--ci"],
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 1
    assert stderr.getvalue() == ""
    assert "Permit status: needs_review" in stdout.getvalue()
