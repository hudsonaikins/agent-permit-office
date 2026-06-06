import json
from datetime import UTC, datetime

from agent_permit.artifacts import RunArtifactWriter, create_run_id
from agent_permit.models import FileInventory, FileInventoryEntry


def test_create_run_writes_artifact_contract(tmp_path) -> None:
    target = tmp_path / "safe-agent"
    target.mkdir()
    now = datetime(2026, 6, 6, 5, 7, 5, tzinfo=UTC)

    scan_run = RunArtifactWriter().create_run(target, now=now)

    artifact_dir = target / ".agent-permit" / "runs" / scan_run.id
    assert scan_run.artifact_dir == artifact_dir
    assert artifact_dir.exists()
    assert (artifact_dir / "evidence-packs").is_dir()

    expected_files = {
        "scan-input.json",
        "scan-run.json",
        "file-inventory.json",
        "codebase-map.json",
        "agent-bom.json",
        "raw-findings.json",
        "permit.yaml",
        "risk-report.md",
    }
    assert expected_files == {
        path.name for path in artifact_dir.iterdir() if path.is_file()
    }

    scan_input = json.loads((artifact_dir / "scan-input.json").read_text())
    scan_metadata = json.loads((artifact_dir / "scan-run.json").read_text())
    assert scan_input["scan_run_id"] == scan_run.id
    assert scan_input["target_path"] == str(target.resolve())
    assert scan_metadata["id"] == scan_run.id
    assert scan_metadata["status"] == "created"


def test_run_id_is_traceable_with_timestamp(tmp_path) -> None:
    target = tmp_path / "repo"
    target.mkdir()
    now = datetime(2026, 6, 6, 5, 7, 5, tzinfo=UTC)

    run_id = create_run_id(target, now)

    assert run_id.startswith("20260606T050705Z-")
    assert len(run_id) == len("20260606T050705Z-00000000")


def test_create_run_redacts_secret_values_before_disk_write(tmp_path) -> None:
    target = tmp_path / "risky-agent"
    target.mkdir()

    scan_run = RunArtifactWriter().create_run(
        target,
        run_id="run-redaction",
        scan_options={
            "env": {
                "OPENAI_API_KEY": "sk-live-secret",
                "nested": [{"github_token": "ghp_secret"}],
            },
            "badly_named": "sk-live-secret-2",
            "safe_flag": True,
            "plain_value": "not redacted because key is not sensitive",
        },
    )

    scan_input_path = scan_run.artifact_dir / "scan-input.json"
    raw_disk_text = scan_input_path.read_text()
    scan_input = json.loads(raw_disk_text)

    assert "sk-live-secret" not in raw_disk_text
    assert "sk-live-secret-2" not in raw_disk_text
    assert "ghp_secret" not in raw_disk_text
    assert scan_input["options"]["env"]["OPENAI_API_KEY"] == "<redacted>"
    assert scan_input["options"]["env"]["nested"][0]["github_token"] == "<redacted>"
    assert scan_input["options"]["badly_named"] == "<redacted>"
    assert scan_input["options"]["plain_value"] == "not redacted because key is not sensitive"


def test_write_file_inventory_replaces_placeholder(tmp_path) -> None:
    target = tmp_path / "safe-agent"
    target.mkdir()
    writer = RunArtifactWriter()
    scan_run = writer.create_run(target, run_id="run-inventory")
    inventory = FileInventory(
        scan_run_id=scan_run.id,
        root_path=str(target.resolve()),
        files=[
            FileInventoryEntry(
                path="AGENTS.md",
                kind="agent_instruction",
                size_bytes=12,
                sha256="0" * 64,
                high_signal=True,
                language="markdown",
            )
        ],
        skipped={"junk_dir": 1},
    )

    writer.write_file_inventory(scan_run, inventory)

    payload = json.loads((scan_run.artifact_dir / "file-inventory.json").read_text())
    assert payload["files"][0]["path"] == "AGENTS.md"
    assert payload["files"][0]["kind"] == "agent_instruction"
    assert payload["skipped"] == {"junk_dir": 1}
