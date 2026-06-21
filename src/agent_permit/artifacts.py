from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TypeAlias

from agent_permit.models import (
    AgentBom,
    CodebaseMap,
    ControlReport,
    FileInventory,
    Finding,
    GraphPathReport,
    Permit,
    ScanRun,
)

JsonCompatible: TypeAlias = (
    str | int | float | bool | None | list["JsonCompatible"] | dict[str, "JsonCompatible"]
)
JsonObject: TypeAlias = dict[str, JsonCompatible]

ARTIFACT_ROOT = ".agent-permit"
RUNS_DIR = "runs"
SCAN_INPUT_FILE = "scan-input.json"
SCAN_RUN_FILE = "scan-run.json"

_SENSITIVE_KEY_MARKERS = (
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "password",
    "private_key",
    "secret",
    "token",
)
_SENSITIVE_VALUE_MARKERS = (
    "-----BEGIN PRIVATE KEY-----",
    "AKIA",
    "ghp_",
    "github_pat_",
    "sk-",
    "xoxb-",
)


def create_run_id(target_path: Path, now: datetime | None = None) -> str:
    timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    stamp = timestamp.strftime("%Y%m%dT%H%M%SZ")
    digest_input = f"{target_path.resolve()}|{stamp}".encode()
    digest = hashlib.sha256(digest_input).hexdigest()[:8]
    return f"{stamp}-{digest}"


def redact_secret_values(value: JsonCompatible) -> JsonCompatible:
    if isinstance(value, dict):
        redacted: JsonObject = {}
        for key, nested_value in value.items():
            if _is_sensitive_key(key):
                redacted[key] = (
                    nested_value
                    if isinstance(nested_value, int | float | bool | type(None))
                    else "<redacted>"
                )
            else:
                redacted[key] = redact_secret_values(nested_value)
        return redacted
    if isinstance(value, list):
        return [redact_secret_values(item) for item in value]
    if isinstance(value, str) and _looks_like_secret_value(value):
        return "<redacted>"
    return value


class RunArtifactWriter:
    def __init__(self, artifact_root_name: str = ARTIFACT_ROOT) -> None:
        self.artifact_root_name = artifact_root_name

    def create_run(
        self,
        target_path: Path,
        *,
        run_id: str | None = None,
        scan_options: JsonObject | None = None,
        now: datetime | None = None,
    ) -> ScanRun:
        target_path = target_path.resolve()
        run_id = run_id or create_run_id(target_path, now)
        artifact_dir = target_path / self.artifact_root_name / RUNS_DIR / run_id
        evidence_dir = artifact_dir / "evidence-packs"
        evidence_dir.mkdir(parents=True, exist_ok=False)

        scan_run = ScanRun(
            id=run_id,
            target_path=target_path,
            artifact_dir=artifact_dir,
            started_at=(now or datetime.now(timezone.utc)).astimezone(timezone.utc),
        )

        redacted_options = redact_secret_values(scan_options or {})
        self._write_json(
            artifact_dir / SCAN_INPUT_FILE,
            {
                "scan_run_id": run_id,
                "target_path": str(target_path),
                "options": redacted_options,
            },
        )
        self._write_json(artifact_dir / SCAN_RUN_FILE, scan_run.model_dump(mode="json"))
        self._write_placeholder_artifacts(artifact_dir, run_id)
        return scan_run

    def write_scan_run(self, scan_run: ScanRun) -> None:
        self._write_json(
            scan_run.artifact_dir / SCAN_RUN_FILE,
            scan_run.model_dump(mode="json"),
        )

    def write_file_inventory(self, scan_run: ScanRun, inventory: FileInventory) -> None:
        self._write_json(
            scan_run.artifact_dir / "file-inventory.json",
            inventory.model_dump(mode="json"),
        )

    def write_agent_bom(self, scan_run: ScanRun, agent_bom: AgentBom) -> None:
        self._write_json(
            scan_run.artifact_dir / "agent-bom.json",
            agent_bom.model_dump(mode="json"),
        )

    def write_codebase_map(self, scan_run: ScanRun, codebase_map: CodebaseMap) -> None:
        self._write_json(
            scan_run.artifact_dir / "codebase-map.json",
            codebase_map.model_dump(mode="json"),
        )

    def write_graph_paths(
        self,
        scan_run: ScanRun,
        graph_path_report: GraphPathReport,
    ) -> None:
        self._write_json(
            scan_run.artifact_dir / "graph-paths.json",
            graph_path_report.model_dump(mode="json"),
        )

    def write_controls(self, scan_run: ScanRun, control_report: ControlReport) -> None:
        self._write_json(
            scan_run.artifact_dir / "controls.json",
            control_report.model_dump(mode="json"),
        )

    def write_permit(self, scan_run: ScanRun, permit: Permit) -> None:
        (scan_run.artifact_dir / "permit.yaml").write_text(
            _permit_yaml(permit),
            encoding="utf-8",
        )

    def write_risk_report(self, scan_run: ScanRun, markdown: str) -> None:
        (scan_run.artifact_dir / "risk-report.md").write_text(
            markdown,
            encoding="utf-8",
        )

    def write_summary(self, scan_run: ScanRun, markdown: str) -> None:
        (scan_run.artifact_dir / "summary.md").write_text(
            markdown,
            encoding="utf-8",
        )

    def write_raw_findings(
        self,
        scan_run: ScanRun,
        findings: list[Finding],
    ) -> None:
        self._write_json(
            scan_run.artifact_dir / "raw-findings.json",
            {
                "scan_run_id": scan_run.id,
                "findings": [
                    finding.model_dump(mode="json") for finding in findings
                ],
            },
        )

    def _write_placeholder_artifacts(self, artifact_dir: Path, run_id: str) -> None:
        self._write_json(artifact_dir / "file-inventory.json", {"files": []})
        self._write_json(
            artifact_dir / "codebase-map.json",
            CodebaseMap(scan_run_id=run_id).model_dump(mode="json"),
        )
        self._write_json(
            artifact_dir / "agent-bom.json",
            AgentBom(scan_run_id=run_id).model_dump(mode="json"),
        )
        self._write_json(
            artifact_dir / "raw-findings.json",
            {"scan_run_id": run_id, "findings": []},
        )
        self._write_json(
            artifact_dir / "graph-paths.json",
            GraphPathReport(scan_run_id=run_id).model_dump(mode="json"),
        )
        self._write_json(
            artifact_dir / "controls.json",
            ControlReport(scan_run_id=run_id).model_dump(mode="json"),
        )
        (artifact_dir / "permit.yaml").write_text(
            f"scan_run_id: {run_id}\nstatus: pending\n",
            encoding="utf-8",
        )
        (artifact_dir / "risk-report.md").write_text(
            "# Agent Permit Office Risk Report\n\n"
            "Status: pending scanner implementation.\n",
            encoding="utf-8",
        )
        (artifact_dir / "summary.md").write_text(
            "# Agent Permit Office Summary\n\n"
            "Status: pending scanner implementation.\n",
            encoding="utf-8",
        )

    def _write_json(self, path: Path, payload: object) -> None:
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(marker in normalized for marker in _SENSITIVE_KEY_MARKERS)


def _looks_like_secret_value(value: str) -> bool:
    stripped = value.strip()
    return any(stripped.startswith(marker) for marker in _SENSITIVE_VALUE_MARKERS)


def _permit_yaml(permit: Permit) -> str:
    payload = permit.model_dump(mode="json")
    lines = [
        f"scan_run_id: {payload['scan_run_id']}",
        f"status: {payload['status']}",
        f"agent_name: {payload['agent_name']}",
    ]
    _append_yaml_list(lines, "discovered_tools", payload["discovered_tools"])
    _append_yaml_list(
        lines,
        "discovered_credentials",
        payload["discovered_credentials"],
    )
    _append_yaml_list(lines, "allowed_actions", payload["allowed_actions"])
    _append_yaml_list(lines, "forbidden_actions", payload["forbidden_actions"])
    _append_yaml_list(lines, "required_approvals", payload["required_approvals"])
    _append_yaml_list(lines, "conditions", payload["conditions"])
    lines.append("findings_summary:")
    if payload["findings_summary"]:
        for severity, count in sorted(payload["findings_summary"].items()):
            lines.append(f"  {severity}: {count}")
    else:
        lines.append("  {}")
    if payload["evidence_bundle_path"]:
        lines.append(f"evidence_bundle_path: {payload['evidence_bundle_path']}")
    return "\n".join(lines) + "\n"


def _append_yaml_list(lines: list[str], key: str, values: list[str]) -> None:
    lines.append(f"{key}:")
    if not values:
        lines.append("  []")
        return
    for value in values:
        lines.append(f"  - {_quote_yaml_string(value)}")


def _quote_yaml_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
