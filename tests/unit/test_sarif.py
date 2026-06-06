from io import StringIO
import json
from pathlib import Path
import shutil

from agent_permit.cli import main
from agent_permit.evidence_context import EvidenceContext
from agent_permit.sarif import SARIF_FILE, SARIF_VERSION, build_sarif_log


FIXTURES_DIR = Path(__file__).parents[1] / "fixtures"


def test_build_sarif_log_maps_findings_to_results(tmp_path) -> None:
    artifact_dir = _scan_fixture(tmp_path, "risky-ci-agent", "sarif-ci")
    context = EvidenceContext.load(artifact_dir)

    sarif_log = build_sarif_log(context, category="agent-permit-test")

    assert sarif_log["version"] == SARIF_VERSION
    run = sarif_log["runs"][0]
    assert run["automationDetails"]["id"] == "agent-permit-test"
    rules = run["tool"]["driver"]["rules"]
    results = run["results"]
    rule_ids = {rule["id"] for rule in rules}
    assert rule_ids == {
        "ci-pr-target-write-token",
        "ci-pull-request-target",
        "ci-secret-reference",
        "ci-write-all-permissions",
    }
    assert len(results) == 4
    assert all("partialFingerprints" in result for result in results)
    assert all(result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] for result in results)
    assert {
        result["level"]
        for result in results
    } == {"error", "warning"}
    assert "secrets.GITHUB_TOKEN" not in json.dumps(sarif_log)


def test_sarif_cli_writes_existing_artifact_run(tmp_path) -> None:
    artifact_dir = _scan_fixture(tmp_path, "risky-mcp-agent", "sarif-mcp")
    output_path = tmp_path / "results.sarif"
    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(
        [
            "sarif",
            str(artifact_dir),
            "--output",
            str(output_path),
            "--category",
            "agent-permit-test",
        ],
        stdout=stdout,
        stderr=stderr,
    )

    payload = json.loads(output_path.read_text())
    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert output_path.is_file()
    assert "Status: sarif_complete" in stdout.getvalue()
    assert "Category: agent-permit-test" in stdout.getvalue()
    assert payload["runs"][0]["automationDetails"]["id"] == "agent-permit-test"


def test_scan_cli_can_write_sarif_artifact(tmp_path) -> None:
    target = tmp_path / "risky-mcp-agent"
    shutil.copytree(FIXTURES_DIR / "risky-mcp-agent", target)
    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(
        ["scan", str(target), "--run-id", "scan-sarif", "--sarif"],
        stdout=stdout,
        stderr=stderr,
    )

    sarif_path = target / ".agent-permit" / "runs" / "scan-sarif" / SARIF_FILE
    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert sarif_path.is_file()
    assert f"SARIF: {sarif_path}" in stdout.getvalue()


def test_sarif_cli_rejects_missing_artifact_dir(tmp_path) -> None:
    stdout = StringIO()
    stderr = StringIO()
    missing = tmp_path / "missing"

    exit_code = main(["sarif", str(missing)], stdout=stdout, stderr=stderr)

    assert exit_code == 2
    assert stdout.getvalue() == ""
    assert "failed to load scan artifacts" in stderr.getvalue()


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
