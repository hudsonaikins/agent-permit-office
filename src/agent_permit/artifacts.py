from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TypeAlias

from agent_permit.models import AgentBom, CodebaseMap, FileInventory, ScanRun

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
                redacted[key] = "<redacted>"
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
        (artifact_dir / "permit.yaml").write_text(
            f"scan_run_id: {run_id}\nstatus: pending\n",
            encoding="utf-8",
        )
        (artifact_dir / "risk-report.md").write_text(
            "# Agent Permit Office Risk Report\n\n"
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
