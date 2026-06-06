from io import StringIO
import json

from agent_permit import __version__
from agent_permit.cli import build_parser, main


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
    (tmp_path / "AGENTS.md").write_text("# Agent instructions\n")

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
    scan_run = json.loads((artifact_dir / "scan-run.json").read_text())
    assert inventory["files"][0]["path"] == "AGENTS.md"
    assert inventory["files"][0]["kind"] == "agent_instruction"
    assert scan_run["status"] == "completed"
    assert f"Artifacts: {artifact_dir}" in stdout.getvalue()
    assert "Files indexed: 1" in stdout.getvalue()
    assert "High signal files: 1" in stdout.getvalue()


def test_scan_command_rejects_missing_path(tmp_path) -> None:
    stdout = StringIO()
    stderr = StringIO()
    missing_path = tmp_path / "missing"

    exit_code = main(["scan", str(missing_path)], stdout=stdout, stderr=stderr)

    assert exit_code == 2
    assert stdout.getvalue() == ""
    assert f"target path does not exist: {missing_path}" in stderr.getvalue()
