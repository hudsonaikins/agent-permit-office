import json
from datetime import UTC, datetime

from agent_permit.artifacts import RunArtifactWriter, create_run_id
from agent_permit.models import (
    AgentBom,
    CodebaseMap,
    ControlReport,
    Confidence,
    EvidenceLocation,
    FileInventory,
    FileInventoryEntry,
    Finding,
    FindingCategory,
    GraphPathReport,
    McpServerSummary,
    GraphNode,
    GraphNodeKind,
    Permit,
    PermitStatus,
    Severity,
)


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
        "graph-paths.json",
        "controls.json",
        "agent-bom.json",
        "raw-findings.json",
        "permit.yaml",
        "risk-report.md",
        "summary.md",
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
            "credential_refs": 2,
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
    assert scan_input["options"]["credential_refs"] == 2
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


def test_write_codebase_map_replaces_placeholder(tmp_path) -> None:
    target = tmp_path / "safe-agent"
    target.mkdir()
    writer = RunArtifactWriter()
    scan_run = writer.create_run(target, run_id="run-map")
    codebase_map = CodebaseMap(
        scan_run_id=scan_run.id,
        nodes=[
            GraphNode(
                id="file:AGENTS.md",
                kind=GraphNodeKind.FILE,
                label="AGENTS.md",
                source_fact_ids=["file:AGENTS.md"],
            )
        ],
    )

    writer.write_codebase_map(scan_run, codebase_map)

    payload = json.loads((scan_run.artifact_dir / "codebase-map.json").read_text())
    assert payload["nodes"][0]["id"] == "file:AGENTS.md"


def test_write_graph_paths_replaces_placeholder(tmp_path) -> None:
    target = tmp_path / "safe-agent"
    target.mkdir()
    writer = RunArtifactWriter()
    scan_run = writer.create_run(target, run_id="run-paths")
    report = GraphPathReport(scan_run_id=scan_run.id)

    writer.write_graph_paths(scan_run, report)

    payload = json.loads((scan_run.artifact_dir / "graph-paths.json").read_text())
    assert payload["scan_run_id"] == scan_run.id
    assert payload["paths"] == []


def test_write_controls_permit_and_risk_report_replace_placeholders(tmp_path) -> None:
    target = tmp_path / "safe-agent"
    target.mkdir()
    writer = RunArtifactWriter()
    scan_run = writer.create_run(target, run_id="run-permit")
    permit = Permit(
        scan_run_id=scan_run.id,
        status=PermitStatus.APPROVED,
        agent_name="repo-agent",
        evidence_bundle_path=str(scan_run.artifact_dir),
    )

    writer.write_controls(scan_run, ControlReport(scan_run_id=scan_run.id))
    writer.write_permit(scan_run, permit)
    writer.write_risk_report(scan_run, "# Risk\n\nStatus: approved\n")
    writer.write_summary(scan_run, "# Summary\n\nStatus: approved\n")

    controls_payload = json.loads((scan_run.artifact_dir / "controls.json").read_text())
    permit_text = (scan_run.artifact_dir / "permit.yaml").read_text()
    report_text = (scan_run.artifact_dir / "risk-report.md").read_text()
    summary_text = (scan_run.artifact_dir / "summary.md").read_text()
    assert controls_payload["controls"] == []
    assert "status: approved" in permit_text
    assert "Status: approved" in report_text
    assert "Status: approved" in summary_text


def test_write_agent_bom_and_raw_findings_replace_placeholders(tmp_path) -> None:
    target = tmp_path / "risky-agent"
    target.mkdir()
    writer = RunArtifactWriter()
    scan_run = writer.create_run(target, run_id="run-mcp")
    agent_bom = AgentBom(
        scan_run_id=scan_run.id,
        mcp_servers=[
            McpServerSummary(
                id="mcp-server:.mcp.json:github-tools",
                name="github-tools",
                transport="stdio",
                command="npx",
            )
        ],
    )
    findings = [
        Finding(
            id="finding:mcp-stdio-credential-ref:.mcp.json:github-tools",
            rule_id="mcp-stdio-credential-ref",
            title="Stdio MCP server receives credential references",
            severity=Severity.HIGH,
            category=FindingCategory.CREDENTIAL_SCOPE,
            evidence=[
                EvidenceLocation(
                    path=".mcp.json",
                    line_start=3,
                    redacted_snippet='{"env": ["GITHUB_TOKEN"]}',
                )
            ],
            risk="Credential reference is passed to a local MCP server.",
            recommendation="Review package and credential scope.",
            confidence=Confidence.HIGH,
        )
    ]

    writer.write_agent_bom(scan_run, agent_bom)
    writer.write_raw_findings(scan_run, findings)

    bom_payload = json.loads((scan_run.artifact_dir / "agent-bom.json").read_text())
    findings_payload = json.loads(
        (scan_run.artifact_dir / "raw-findings.json").read_text()
    )
    assert bom_payload["mcp_servers"][0]["name"] == "github-tools"
    assert findings_payload["findings"][0]["rule_id"] == "mcp-stdio-credential-ref"
