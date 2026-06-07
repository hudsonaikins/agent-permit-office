from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from agent_permit.evidence_context import EvidenceContext
from agent_permit.models import (
    AgentBom,
    CodebaseMap,
    ControlReport,
    FileInventory,
    Finding,
    GraphPathReport,
    Permit,
    ScanRun,
    StrictModel,
)


RUN_METRICS_FILE = "run-metrics.json"
SEVERITIES = ("critical", "high", "medium", "low", "info")


class RunMetrics(StrictModel):
    version: int = 1
    run_id: str
    run_type: Literal["scan", "live_validation"]
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    target_hash: str
    status: str
    permit_status: str
    files_indexed: int | None = None
    high_signal_files: int | None = None
    skipped_files: int | None = None
    findings: int
    finding_severity_counts: dict[str, int]
    rule_counts: dict[str, int]
    graph_nodes: int | None = None
    graph_edges: int | None = None
    graph_paths: int
    controls: int
    credentials: int
    mcp_servers: int
    citation_check_status: str = "not_applicable"
    citation_supported: bool | None = None
    unsupported_citations: int = 0
    unsupported_rule_ids: int = 0
    missing_citation_rule_ids: int = 0
    aggregate_mismatches: int = 0
    model: str | None = None
    model_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int = 0
    cache_write_tokens: int = 0
    cache_hit_ratio: float | None = None
    duration_ms: int | None = None
    scan_exit_code: int | None = None
    investigation_exit_code: int | None = None
    phoenix: bool | None = None
    langsmith: bool | None = None
    available_artifacts: list[str] = Field(default_factory=list)


def build_scan_run_metrics(
    *,
    scan_run: ScanRun,
    target_path: Path,
    inventory: FileInventory,
    agent_bom: AgentBom,
    codebase_map: CodebaseMap,
    findings: list[Finding],
    graph_paths: GraphPathReport,
    controls: ControlReport,
    permit: Permit,
) -> RunMetrics:
    return RunMetrics(
        run_id=scan_run.id,
        run_type="scan",
        target_hash=target_fingerprint(target_path, inventory=inventory),
        status=_enum_value(scan_run.status),
        permit_status=_enum_value(permit.status),
        files_indexed=len(inventory.files),
        high_signal_files=sum(1 for entry in inventory.files if entry.high_signal),
        skipped_files=sum(inventory.skipped.values()),
        findings=len(findings),
        finding_severity_counts=finding_severity_counts(findings),
        rule_counts=finding_rule_counts(findings),
        graph_nodes=len(codebase_map.nodes),
        graph_edges=len(codebase_map.edges),
        graph_paths=len(graph_paths.paths),
        controls=len(controls.controls),
        credentials=len(agent_bom.credential_refs),
        mcp_servers=len(agent_bom.mcp_servers),
        duration_ms=duration_ms(scan_run.started_at, scan_run.completed_at),
        available_artifacts=_available_artifacts(scan_run.artifact_dir),
    )


def build_live_validation_metrics(
    *,
    context: EvidenceContext,
    target_path: Path,
    status: str,
    started_at: datetime,
    completed_at: datetime,
    model: str,
    citation_check: dict[str, Any],
    usage_summary: dict[str, Any] | None,
    scan_exit_code: int,
    investigation_exit_code: int,
    phoenix: bool,
    langsmith: bool,
) -> RunMetrics:
    artifact_counts = _read_artifact_counts(context.artifact_dir)
    citation_metrics = _citation_metrics(citation_check)
    usage_metrics = _usage_metrics(usage_summary)
    return RunMetrics(
        run_id=context.scan_run_id,
        run_type="live_validation",
        target_hash=target_fingerprint(
            target_path,
            inventory=artifact_counts.get("inventory"),
        ),
        status=status,
        permit_status=context.permit_status,
        files_indexed=artifact_counts.get("files_indexed"),
        high_signal_files=artifact_counts.get("high_signal_files"),
        skipped_files=artifact_counts.get("skipped_files"),
        findings=len(context.findings),
        finding_severity_counts=context.finding_severity_counts(),
        rule_counts=finding_rule_counts(list(context.findings)),
        graph_nodes=artifact_counts.get("graph_nodes"),
        graph_edges=artifact_counts.get("graph_edges"),
        graph_paths=len(context.graph_paths.paths),
        controls=len(context.controls.controls),
        credentials=len(context.agent_bom.credential_refs),
        mcp_servers=len(context.agent_bom.mcp_servers),
        model=model,
        duration_ms=duration_ms(started_at, completed_at),
        scan_exit_code=scan_exit_code,
        investigation_exit_code=investigation_exit_code,
        phoenix=phoenix,
        langsmith=langsmith,
        available_artifacts=list(context.summary().available_artifacts),
        **citation_metrics,
        **usage_metrics,
    )


def write_run_metrics(path: Path, metrics: RunMetrics) -> None:
    path.write_text(
        json.dumps(metrics.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def target_fingerprint(
    target_path: Path,
    *,
    inventory: FileInventory | None = None,
) -> str:
    if inventory is None:
        digest_input = f"path:{target_path.resolve()}".encode()
    else:
        entries = [
            f"{entry.path}:{entry.sha256}"
            for entry in sorted(inventory.files, key=lambda item: item.path)
        ]
        digest_input = "\n".join(entries).encode()
    return "sha256:" + hashlib.sha256(digest_input).hexdigest()


def finding_severity_counts(findings: list[Finding]) -> dict[str, int]:
    counts: Counter[str] = Counter(_enum_value(finding.severity) for finding in findings)
    return {severity: counts.get(severity, 0) for severity in SEVERITIES}


def finding_rule_counts(findings: list[Finding]) -> dict[str, int]:
    counts: Counter[str] = Counter(finding.rule_id for finding in findings)
    return dict(sorted(counts.items()))


def duration_ms(
    started_at: datetime | None,
    completed_at: datetime | None,
) -> int | None:
    if started_at is None or completed_at is None:
        return None
    return max(0, int((completed_at - started_at).total_seconds() * 1000))


def _citation_metrics(citation_check: dict[str, Any]) -> dict[str, Any]:
    return {
        "citation_check_status": str(citation_check.get("status", "not_run")),
        "citation_supported": citation_check.get("supported"),
        "unsupported_citations": len(citation_check.get("unsupported_citations") or []),
        "unsupported_rule_ids": len(citation_check.get("unsupported_rule_ids") or []),
        "missing_citation_rule_ids": len(
            citation_check.get("missing_citation_rule_ids") or []
        ),
        "aggregate_mismatches": len(citation_check.get("aggregate_mismatches") or []),
    }


def _usage_metrics(usage_summary: dict[str, Any] | None) -> dict[str, Any]:
    usage_summary = usage_summary or {}
    return {
        "model_calls": int(usage_summary.get("model_calls") or 0),
        "input_tokens": int(usage_summary.get("input_tokens") or 0),
        "output_tokens": int(usage_summary.get("output_tokens") or 0),
        "total_tokens": int(usage_summary.get("total_tokens") or 0),
        "cached_tokens": int(usage_summary.get("cached_tokens") or 0),
        "cache_write_tokens": int(usage_summary.get("cache_write_tokens") or 0),
        "cache_hit_ratio": usage_summary.get("cache_hit_ratio"),
    }


def _read_artifact_counts(artifact_dir: Path) -> dict[str, Any]:
    counts: dict[str, Any] = {}
    inventory_path = artifact_dir / "file-inventory.json"
    if inventory_path.is_file():
        inventory = FileInventory.model_validate(_read_json(inventory_path))
        counts["inventory"] = inventory
        counts["files_indexed"] = len(inventory.files)
        counts["high_signal_files"] = sum(
            1 for entry in inventory.files if entry.high_signal
        )
        counts["skipped_files"] = sum(inventory.skipped.values())
    codebase_map_path = artifact_dir / "codebase-map.json"
    if codebase_map_path.is_file():
        codebase_map = CodebaseMap.model_validate(_read_json(codebase_map_path))
        counts["graph_nodes"] = len(codebase_map.nodes)
        counts["graph_edges"] = len(codebase_map.edges)
    return counts


def _available_artifacts(artifact_dir: Path) -> list[str]:
    return sorted(path.name for path in artifact_dir.iterdir() if path.is_file())


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"artifact must contain a JSON object: {path.name}")
    return payload


def _enum_value(value: object) -> str:
    raw_value = getattr(value, "value", value)
    return str(raw_value)
