from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_permit.analytics import (
    ANALYTICS_EVENTS_FILE,
    RUN_METRICS_FILE,
    read_analytics_events,
)
from agent_permit.artifacts import (
    ARTIFACT_ROOT,
    SCAN_INPUT_FILE,
    SCAN_RUN_FILE,
    redact_secret_values,
)
from agent_permit.evidence_context import EvidenceContext
from agent_permit.models import FileInventory


SCHEMA_VERSION = 1

MIGRATION_SQL = """
CREATE TABLE IF NOT EXISTS agent_permit_schema_migrations (
  version INTEGER PRIMARY KEY,
  applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS repositories (
  id TEXT PRIMARY KEY,
  label TEXT NOT NULL,
  local_path TEXT NOT NULL UNIQUE,
  branch TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS scan_jobs (
  id TEXT PRIMARY KEY,
  repository_id TEXT NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
  mode TEXT NOT NULL,
  status TEXT NOT NULL,
  requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  claimed_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  error TEXT
);

CREATE TABLE IF NOT EXISTS scan_runs (
  id TEXT PRIMARY KEY,
  job_id TEXT REFERENCES scan_jobs(id) ON DELETE SET NULL,
  repository_id TEXT NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
  run_id TEXT NOT NULL UNIQUE,
  permit_status TEXT NOT NULL,
  status TEXT NOT NULL,
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  files_indexed INTEGER,
  high_signal_files INTEGER,
  skipped_files INTEGER,
  findings_count INTEGER NOT NULL DEFAULT 0,
  graph_paths_count INTEGER NOT NULL DEFAULT 0,
  controls_count INTEGER NOT NULL DEFAULT 0,
  artifact_dir TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS findings (
  id TEXT PRIMARY KEY,
  scan_run_id TEXT NOT NULL REFERENCES scan_runs(id) ON DELETE CASCADE,
  finding_id TEXT NOT NULL,
  rule_id TEXT NOT NULL,
  title TEXT NOT NULL,
  severity TEXT NOT NULL,
  status TEXT NOT NULL,
  path TEXT,
  line_start INTEGER,
  recommendation TEXT NOT NULL,
  risk TEXT NOT NULL,
  UNIQUE (scan_run_id, finding_id)
);

CREATE TABLE IF NOT EXISTS run_events (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  job_id TEXT REFERENCES scan_jobs(id) ON DELETE SET NULL,
  scan_run_id TEXT,
  event_name TEXT NOT NULL,
  sequence INTEGER NOT NULL,
  occurred_at TIMESTAMPTZ NOT NULL,
  payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (scan_run_id, sequence)
);

CREATE TABLE IF NOT EXISTS run_artifacts (
  id TEXT PRIMARY KEY,
  scan_run_id TEXT NOT NULL REFERENCES scan_runs(id) ON DELETE CASCADE,
  artifact_type TEXT NOT NULL,
  local_path TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  byte_size BIGINT NOT NULL,
  UNIQUE (scan_run_id, local_path)
);

CREATE TABLE IF NOT EXISTS model_usage (
  id TEXT PRIMARY KEY,
  scan_run_id TEXT NOT NULL REFERENCES scan_runs(id) ON DELETE CASCADE,
  model TEXT,
  model_calls INTEGER NOT NULL DEFAULT 0,
  input_tokens INTEGER NOT NULL DEFAULT 0,
  output_tokens INTEGER NOT NULL DEFAULT 0,
  total_tokens INTEGER NOT NULL DEFAULT 0,
  cached_tokens INTEGER NOT NULL DEFAULT 0,
  cache_hit_ratio DOUBLE PRECISION,
  UNIQUE (scan_run_id)
);

INSERT INTO agent_permit_schema_migrations (version)
VALUES (1)
ON CONFLICT (version) DO NOTHING;
"""


@dataclass(frozen=True)
class RepositoryRecord:
    id: str
    label: str
    local_path: str
    branch: str | None = None


@dataclass(frozen=True)
class ScanJobRecord:
    id: str
    repository_id: str
    mode: str
    status: str
    requested_at: datetime
    claimed_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None


@dataclass(frozen=True)
class ScanRunRecord:
    id: str
    job_id: str | None
    repository_id: str
    run_id: str
    permit_status: str
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    files_indexed: int | None
    high_signal_files: int | None
    skipped_files: int | None
    findings_count: int
    graph_paths_count: int
    controls_count: int
    artifact_dir: str


@dataclass(frozen=True)
class FindingRecord:
    id: str
    scan_run_id: str
    finding_id: str
    rule_id: str
    title: str
    severity: str
    status: str
    path: str | None
    line_start: int | None
    recommendation: str
    risk: str


@dataclass(frozen=True)
class RunEventRecord:
    job_id: str | None
    scan_run_id: str | None
    event_name: str
    sequence: int
    occurred_at: datetime
    payload_json: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RunArtifactRecord:
    id: str
    scan_run_id: str
    artifact_type: str
    local_path: str
    sha256: str
    byte_size: int


@dataclass(frozen=True)
class ModelUsageRecord:
    id: str
    scan_run_id: str
    model: str | None
    model_calls: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cached_tokens: int
    cache_hit_ratio: float | None


@dataclass(frozen=True)
class IngestRecords:
    repository: RepositoryRecord
    job: ScanJobRecord
    run: ScanRunRecord
    findings: list[FindingRecord]
    events: list[RunEventRecord]
    artifacts: list[RunArtifactRecord]
    model_usage: ModelUsageRecord | None


class PostgresStore:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def migrate(self) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                for statement in _sql_statements(MIGRATION_SQL):
                    cursor.execute(statement)

    def write_ingest_records(self, records: IngestRecords) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                _upsert_repository(cursor, records.repository)
                _upsert_scan_job(cursor, records.job)
                _upsert_scan_run(cursor, records.run)
                for finding in records.findings:
                    _upsert_finding(cursor, finding)
                for artifact in records.artifacts:
                    _upsert_artifact(cursor, artifact)
                if records.model_usage is not None:
                    _upsert_model_usage(cursor, records.model_usage)
                for event in records.events:
                    _insert_event(cursor, event)

    def append_run_event(self, event: RunEventRecord) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                _insert_event(cursor, event)

    def _connect(self) -> Any:
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - exercised without db extra
            raise RuntimeError(
                "Postgres support requires the optional db extra: "
                "uv sync --extra db"
            ) from exc
        return psycopg.connect(self.database_url)


def store_from_env(database_url: str | None = None) -> PostgresStore:
    resolved_url = database_url or os.environ.get("DATABASE_URL")
    if not resolved_url:
        raise RuntimeError("DATABASE_URL is required")
    return PostgresStore(resolved_url)


def optional_store_from_env() -> PostgresStore | None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return None
    return PostgresStore(database_url)


def load_ingest_records(
    artifact_dir: Path,
    *,
    repository_label: str | None = None,
    local_path: Path | None = None,
    branch: str | None = None,
    mode: str = "scan",
) -> IngestRecords:
    artifact_dir = artifact_dir.resolve()
    context = EvidenceContext.load(artifact_dir)
    scan_run_payload = _read_json_if_exists(artifact_dir / SCAN_RUN_FILE)
    scan_input_payload = _read_json_if_exists(artifact_dir / SCAN_INPUT_FILE)
    metrics_payload = _read_json_if_exists(artifact_dir / RUN_METRICS_FILE)
    inventory_payload = _read_json_if_exists(artifact_dir / "file-inventory.json")

    target_path = _resolve_target_path(
        explicit_path=local_path,
        scan_run_payload=scan_run_payload,
        scan_input_payload=scan_input_payload,
        artifact_dir=artifact_dir,
    )
    label = repository_label or target_path.name
    repository = RepositoryRecord(
        id=_stable_id("repo", str(target_path)),
        label=label,
        local_path=str(target_path),
        branch=branch,
    )

    run_id = context.scan_run_id
    started_at = _parse_datetime(scan_run_payload.get("started_at"))
    completed_at = _parse_datetime(scan_run_payload.get("completed_at"))
    job = ScanJobRecord(
        id=_stable_id("job", run_id, str(target_path), mode),
        repository_id=repository.id,
        mode=mode,
        status="completed",
        requested_at=started_at or datetime.now(timezone.utc),
        completed_at=completed_at,
    )

    files_indexed, high_signal_files, skipped_files = _inventory_counts(
        inventory_payload,
        metrics_payload,
    )
    run = ScanRunRecord(
        id=run_id,
        job_id=job.id,
        repository_id=repository.id,
        run_id=run_id,
        permit_status=context.permit_status,
        status=str(scan_run_payload.get("status") or "completed"),
        started_at=started_at,
        completed_at=completed_at,
        files_indexed=files_indexed,
        high_signal_files=high_signal_files,
        skipped_files=skipped_files,
        findings_count=len(context.findings),
        graph_paths_count=len(context.graph_paths.paths),
        controls_count=len(context.controls.controls),
        artifact_dir=str(artifact_dir),
    )

    return IngestRecords(
        repository=repository,
        job=job,
        run=run,
        findings=_finding_records(context),
        events=_event_records(artifact_dir, run_id=run_id, job_id=job.id),
        artifacts=_artifact_records(artifact_dir, run_id=run_id),
        model_usage=_model_usage_record(run_id, metrics_payload),
    )


def _finding_records(context: EvidenceContext) -> list[FindingRecord]:
    records: list[FindingRecord] = []
    for finding in context.findings:
        first_evidence = finding.evidence[0] if finding.evidence else None
        records.append(
            FindingRecord(
                id=_stable_id("finding", context.scan_run_id, finding.id),
                scan_run_id=context.scan_run_id,
                finding_id=finding.id,
                rule_id=finding.rule_id,
                title=finding.title,
                severity=str(finding.severity),
                status=(
                    "needs_review" if finding.requires_human_review else "detected"
                ),
                path=first_evidence.path if first_evidence is not None else None,
                line_start=(
                    first_evidence.line_start if first_evidence is not None else None
                ),
                recommendation=finding.recommendation,
                risk=finding.risk,
            )
        )
    return records


def _event_records(
    artifact_dir: Path,
    *,
    run_id: str,
    job_id: str,
) -> list[RunEventRecord]:
    artifact_root = _nearest_agent_permit_root(artifact_dir)
    analytics_path = (
        artifact_root / ANALYTICS_EVENTS_FILE
        if artifact_root is not None
        else artifact_dir / ANALYTICS_EVENTS_FILE
    )
    events = [
        event
        for event in read_analytics_events(analytics_path)
        if event.run_id == run_id
    ]
    if not events:
        return [
            RunEventRecord(
                job_id=job_id,
                scan_run_id=run_id,
                event_name="run_ingested",
                sequence=1,
                occurred_at=datetime.now(timezone.utc),
                payload_json={"artifact_dir": str(artifact_dir)},
            )
        ]
    return [
        RunEventRecord(
            job_id=job_id,
            scan_run_id=run_id,
            event_name=event.event_name,
            sequence=index,
            occurred_at=event.occurred_at,
            payload_json=_safe_json_object(event.payload),
        )
        for index, event in enumerate(events, start=1)
    ]


def _artifact_records(artifact_dir: Path, *, run_id: str) -> list[RunArtifactRecord]:
    records: list[RunArtifactRecord] = []
    for path in sorted(path for path in artifact_dir.iterdir() if path.is_file()):
        records.append(
            RunArtifactRecord(
                id=_stable_id("artifact", run_id, str(path)),
                scan_run_id=run_id,
                artifact_type=path.name,
                local_path=str(path),
                sha256=_sha256_file(path),
                byte_size=path.stat().st_size,
            )
        )
    return records


def _model_usage_record(
    run_id: str,
    metrics_payload: dict[str, Any],
) -> ModelUsageRecord | None:
    if not metrics_payload:
        return None
    return ModelUsageRecord(
        id=_stable_id("model-usage", run_id),
        scan_run_id=run_id,
        model=_string_or_none(metrics_payload.get("model")),
        model_calls=int(metrics_payload.get("model_calls") or 0),
        input_tokens=int(metrics_payload.get("input_tokens") or 0),
        output_tokens=int(metrics_payload.get("output_tokens") or 0),
        total_tokens=int(metrics_payload.get("total_tokens") or 0),
        cached_tokens=int(metrics_payload.get("cached_tokens") or 0),
        cache_hit_ratio=_float_or_none(metrics_payload.get("cache_hit_ratio")),
    )


def _resolve_target_path(
    *,
    explicit_path: Path | None,
    scan_run_payload: dict[str, Any],
    scan_input_payload: dict[str, Any],
    artifact_dir: Path,
) -> Path:
    if explicit_path is not None:
        return explicit_path.resolve()
    raw_path = scan_run_payload.get("target_path") or scan_input_payload.get("target_path")
    if raw_path:
        return Path(str(raw_path)).resolve()
    try:
        return artifact_dir.parents[2].resolve()
    except IndexError:
        return artifact_dir.resolve()


def _inventory_counts(
    inventory_payload: dict[str, Any],
    metrics_payload: dict[str, Any],
) -> tuple[int | None, int | None, int | None]:
    if metrics_payload:
        return (
            _int_or_none(metrics_payload.get("files_indexed")),
            _int_or_none(metrics_payload.get("high_signal_files")),
            _int_or_none(metrics_payload.get("skipped_files")),
        )
    if inventory_payload:
        inventory = FileInventory.model_validate(inventory_payload)
        return (
            len(inventory.files),
            sum(1 for entry in inventory.files if entry.high_signal),
            sum(inventory.skipped.values()),
        )
    return None, None, None


def _nearest_agent_permit_root(path: Path) -> Path | None:
    for candidate in [path, *path.parents]:
        if candidate.name == ARTIFACT_ROOT:
            return candidate
    return None


def _read_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"artifact must contain a JSON object: {path.name}")
    return payload


def _safe_json_object(payload: dict[str, Any]) -> dict[str, Any]:
    redacted = redact_secret_values(payload)
    return redacted if isinstance(redacted, dict) else {}


def _sql_statements(sql: str) -> list[str]:
    return [statement.strip() for statement in sql.split(";") if statement.strip()]


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    return None


def _stable_id(*parts: str) -> str:
    digest = hashlib.sha256("\0".join(parts).encode()).hexdigest()
    return digest[:32]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _execute_json(cursor: Any, sql: str, values: tuple[Any, ...]) -> None:
    cursor.execute(sql, values)


def _upsert_repository(cursor: Any, record: RepositoryRecord) -> None:
    cursor.execute(
        """
        INSERT INTO repositories (id, label, local_path, branch)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
          label = EXCLUDED.label,
          local_path = EXCLUDED.local_path,
          branch = EXCLUDED.branch,
          updated_at = now()
        """,
        (record.id, record.label, record.local_path, record.branch),
    )


def _upsert_scan_job(cursor: Any, record: ScanJobRecord) -> None:
    cursor.execute(
        """
        INSERT INTO scan_jobs (
          id, repository_id, mode, status, requested_at, claimed_at, completed_at, error
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
          repository_id = EXCLUDED.repository_id,
          mode = EXCLUDED.mode,
          status = EXCLUDED.status,
          claimed_at = EXCLUDED.claimed_at,
          completed_at = EXCLUDED.completed_at,
          error = EXCLUDED.error
        """,
        (
            record.id,
            record.repository_id,
            record.mode,
            record.status,
            record.requested_at,
            record.claimed_at,
            record.completed_at,
            record.error,
        ),
    )


def _upsert_scan_run(cursor: Any, record: ScanRunRecord) -> None:
    cursor.execute(
        """
        INSERT INTO scan_runs (
          id, job_id, repository_id, run_id, permit_status, status, started_at,
          completed_at, files_indexed, high_signal_files, skipped_files,
          findings_count, graph_paths_count, controls_count, artifact_dir
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
          job_id = EXCLUDED.job_id,
          repository_id = EXCLUDED.repository_id,
          permit_status = EXCLUDED.permit_status,
          status = EXCLUDED.status,
          started_at = EXCLUDED.started_at,
          completed_at = EXCLUDED.completed_at,
          files_indexed = EXCLUDED.files_indexed,
          high_signal_files = EXCLUDED.high_signal_files,
          skipped_files = EXCLUDED.skipped_files,
          findings_count = EXCLUDED.findings_count,
          graph_paths_count = EXCLUDED.graph_paths_count,
          controls_count = EXCLUDED.controls_count,
          artifact_dir = EXCLUDED.artifact_dir
        """,
        (
            record.id,
            record.job_id,
            record.repository_id,
            record.run_id,
            record.permit_status,
            record.status,
            record.started_at,
            record.completed_at,
            record.files_indexed,
            record.high_signal_files,
            record.skipped_files,
            record.findings_count,
            record.graph_paths_count,
            record.controls_count,
            record.artifact_dir,
        ),
    )


def _upsert_finding(cursor: Any, record: FindingRecord) -> None:
    cursor.execute(
        """
        INSERT INTO findings (
          id, scan_run_id, finding_id, rule_id, title, severity, status, path,
          line_start, recommendation, risk
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (scan_run_id, finding_id) DO UPDATE SET
          rule_id = EXCLUDED.rule_id,
          title = EXCLUDED.title,
          severity = EXCLUDED.severity,
          status = EXCLUDED.status,
          path = EXCLUDED.path,
          line_start = EXCLUDED.line_start,
          recommendation = EXCLUDED.recommendation,
          risk = EXCLUDED.risk
        """,
        (
            record.id,
            record.scan_run_id,
            record.finding_id,
            record.rule_id,
            record.title,
            record.severity,
            record.status,
            record.path,
            record.line_start,
            record.recommendation,
            record.risk,
        ),
    )


def _insert_event(cursor: Any, record: RunEventRecord) -> None:
    _execute_json(
        cursor,
        """
        INSERT INTO run_events (
          job_id, scan_run_id, event_name, sequence, occurred_at, payload_json
        )
        VALUES (%s, %s, %s, %s, %s, %s::jsonb)
        ON CONFLICT (scan_run_id, sequence) DO UPDATE SET
          job_id = EXCLUDED.job_id,
          event_name = EXCLUDED.event_name,
          occurred_at = EXCLUDED.occurred_at,
          payload_json = EXCLUDED.payload_json
        """,
        (
            record.job_id,
            record.scan_run_id,
            record.event_name,
            record.sequence,
            record.occurred_at,
            json.dumps(_safe_json_object(record.payload_json), sort_keys=True),
        ),
    )


def _upsert_artifact(cursor: Any, record: RunArtifactRecord) -> None:
    cursor.execute(
        """
        INSERT INTO run_artifacts (
          id, scan_run_id, artifact_type, local_path, sha256, byte_size
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (scan_run_id, local_path) DO UPDATE SET
          artifact_type = EXCLUDED.artifact_type,
          sha256 = EXCLUDED.sha256,
          byte_size = EXCLUDED.byte_size
        """,
        (
            record.id,
            record.scan_run_id,
            record.artifact_type,
            record.local_path,
            record.sha256,
            record.byte_size,
        ),
    )


def _upsert_model_usage(cursor: Any, record: ModelUsageRecord) -> None:
    cursor.execute(
        """
        INSERT INTO model_usage (
          id, scan_run_id, model, model_calls, input_tokens, output_tokens,
          total_tokens, cached_tokens, cache_hit_ratio
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (scan_run_id) DO UPDATE SET
          model = EXCLUDED.model,
          model_calls = EXCLUDED.model_calls,
          input_tokens = EXCLUDED.input_tokens,
          output_tokens = EXCLUDED.output_tokens,
          total_tokens = EXCLUDED.total_tokens,
          cached_tokens = EXCLUDED.cached_tokens,
          cache_hit_ratio = EXCLUDED.cache_hit_ratio
        """,
        (
            record.id,
            record.scan_run_id,
            record.model,
            record.model_calls,
            record.input_tokens,
            record.output_tokens,
            record.total_tokens,
            record.cached_tokens,
            record.cache_hit_ratio,
        ),
    )
