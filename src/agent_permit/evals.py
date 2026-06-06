from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import time
from typing import Any

from agent_permit.artifacts import ARTIFACT_ROOT
from agent_permit.evidence_context import EvidenceContext
from agent_permit.investigation import (
    build_investigation_markdown,
    critique_investigation_report,
)


EVALS_DIR = "evals"
EVAL_RESULTS_FILE = "eval-results.json"
EVAL_REPORT_FILE = "eval-report.md"
PHOENIX_DATASET_ROWS_FILE = "phoenix-dataset-rows.jsonl"
DEFAULT_PHOENIX_DATASET_NAME = "agent-permit-fixture-evals"
DEFAULT_PHOENIX_BASE_URL = "http://localhost:6006"

SECRET_LEAK_MARKERS = (
    "-----BEGIN PRIVATE KEY-----",
    "AKIA",
    "ghp_",
    "github_pat_",
    "sk-live",
    "sk-proj-",
    "xoxb-",
)


@dataclass(frozen=True)
class FixtureEvalCase:
    fixture_id: str
    fixture_path: Path
    expected_permit_status: str
    expected_rule_ids: tuple[str, ...]


@dataclass(frozen=True)
class FixtureEvalResult:
    fixture_id: str
    passed: bool
    expected_permit_status: str
    actual_permit_status: str
    expected_rule_ids: tuple[str, ...]
    actual_rule_ids: tuple[str, ...]
    missing_rule_ids: tuple[str, ...]
    unexpected_rule_ids: tuple[str, ...]
    status_check_passed: bool
    rule_id_check_passed: bool
    citation_check_passed: bool
    secret_leak_check_passed: bool
    quality_score: float
    artifact_dir: Path
    duration_seconds: float


@dataclass(frozen=True)
class FixtureEvalRun:
    eval_run_id: str
    output_dir: Path
    fixture_root: Path
    results: tuple[FixtureEvalResult, ...]
    started_at: datetime
    completed_at: datetime

    @property
    def passed(self) -> bool:
        return all(result.passed for result in self.results)


@dataclass(frozen=True)
class PhoenixDatasetUploadResult:
    dataset_name: str
    example_count: int
    base_url: str
    dataset_id: str | None = None
    version_id: str | None = None


def create_eval_run_id(now: datetime | None = None) -> str:
    timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return timestamp.strftime("%Y%m%dT%H%M%SZ")


def load_fixture_cases(fixture_root: Path) -> list[FixtureEvalCase]:
    cases: list[FixtureEvalCase] = []
    for manifest_path in sorted(fixture_root.glob("*/fixture.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        cases.append(
            FixtureEvalCase(
                fixture_id=str(manifest["id"]),
                fixture_path=manifest_path.parent,
                expected_permit_status=str(manifest["expected_permit_status"]),
                expected_rule_ids=tuple(sorted(manifest["expected_findings"])),
            )
        )
    if not cases:
        raise ValueError(f"no fixture manifests found under {fixture_root}")
    return cases


def run_fixture_eval_suite(
    fixture_root: Path,
    *,
    eval_run_id: str | None = None,
    output_dir: Path | None = None,
) -> FixtureEvalRun:
    fixture_root = fixture_root.resolve()
    eval_run_id = eval_run_id or create_eval_run_id()
    output_dir = (
        output_dir or (Path.cwd() / ARTIFACT_ROOT / EVALS_DIR / eval_run_id)
    ).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(timezone.utc)

    cases = load_fixture_cases(fixture_root)
    results: list[FixtureEvalResult] = []
    for case in cases:
        results.append(_run_fixture_case(case, eval_run_id, output_dir))

    completed_at = datetime.now(timezone.utc)
    eval_run = FixtureEvalRun(
        eval_run_id=eval_run_id,
        output_dir=output_dir,
        fixture_root=fixture_root,
        results=tuple(results),
        started_at=started_at,
        completed_at=completed_at,
    )
    _write_eval_artifacts(eval_run)
    return eval_run


def _run_fixture_case(
    case: FixtureEvalCase,
    eval_run_id: str,
    output_dir: Path,
) -> FixtureEvalResult:
    from agent_permit.cli import run_scan

    start = time.perf_counter()
    scan_target = output_dir / "cases" / case.fixture_id
    if scan_target.exists():
        shutil.rmtree(scan_target)
    scan_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(case.fixture_path, scan_target)
    scan_run_id = f"{eval_run_id}-{case.fixture_id}"
    with _NullWriter() as stdout, _NullWriter() as stderr:
        exit_code = run_scan(
            scan_target,
            run_id=scan_run_id,
            ci=False,
            exclude_patterns=(),
            stdout=stdout,
            stderr=stderr,
        )
        stderr_text = stderr.text
    if exit_code != 0:
        raise RuntimeError(f"fixture scan failed for {case.fixture_id}: {stderr_text}")

    artifact_dir = scan_target / ARTIFACT_ROOT / "runs" / scan_run_id
    context = EvidenceContext.load(artifact_dir)
    actual_rule_ids = tuple(sorted({finding.rule_id for finding in context.findings}))
    expected_rule_ids = tuple(sorted(case.expected_rule_ids))
    missing_rule_ids = tuple(sorted(set(expected_rule_ids) - set(actual_rule_ids)))
    unexpected_rule_ids = tuple(sorted(set(actual_rule_ids) - set(expected_rule_ids)))
    report_markdown = build_investigation_markdown(context)
    citation_result = critique_investigation_report(context, report_markdown)
    secret_leak_check_passed = not _artifact_tree_contains_secret_marker(artifact_dir)
    status_check_passed = case.expected_permit_status == context.permit_status
    rule_id_check_passed = not missing_rule_ids and not unexpected_rule_ids
    check_results = (
        status_check_passed,
        rule_id_check_passed,
        citation_result.supported,
        secret_leak_check_passed,
    )

    passed = all(check_results)
    return FixtureEvalResult(
        fixture_id=case.fixture_id,
        passed=passed,
        expected_permit_status=case.expected_permit_status,
        actual_permit_status=context.permit_status,
        expected_rule_ids=expected_rule_ids,
        actual_rule_ids=actual_rule_ids,
        missing_rule_ids=missing_rule_ids,
        unexpected_rule_ids=unexpected_rule_ids,
        status_check_passed=status_check_passed,
        rule_id_check_passed=rule_id_check_passed,
        citation_check_passed=citation_result.supported,
        secret_leak_check_passed=secret_leak_check_passed,
        quality_score=round(sum(check_results) / len(check_results), 4),
        artifact_dir=artifact_dir,
        duration_seconds=round(time.perf_counter() - start, 4),
    )


def _write_eval_artifacts(eval_run: FixtureEvalRun) -> None:
    (eval_run.output_dir / EVAL_RESULTS_FILE).write_text(
        json.dumps(_eval_run_payload(eval_run), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (eval_run.output_dir / EVAL_REPORT_FILE).write_text(
        build_eval_report_markdown(eval_run),
        encoding="utf-8",
    )
    (eval_run.output_dir / PHOENIX_DATASET_ROWS_FILE).write_text(
        "\n".join(
            json.dumps(row, sort_keys=True)
            for row in build_phoenix_dataset_rows(eval_run)
        )
        + "\n",
        encoding="utf-8",
    )


def build_phoenix_dataset_rows(eval_run: FixtureEvalRun) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result in eval_run.results:
        rows.append(
            {
                "id": f"agent-permit-fixture-{result.fixture_id}",
                "inputs": {
                    "fixture_id": result.fixture_id,
                    "artifact_dir": str(result.artifact_dir),
                },
                "outputs": {
                    "expected_permit_status": result.expected_permit_status,
                    "expected_rule_ids": list(result.expected_rule_ids),
                },
                "metadata": {
                    "eval_run_id": eval_run.eval_run_id,
                    "actual_permit_status": result.actual_permit_status,
                    "actual_rule_ids": list(result.actual_rule_ids),
                    "status_check_passed": result.status_check_passed,
                    "rule_id_check_passed": result.rule_id_check_passed,
                    "citation_check_passed": result.citation_check_passed,
                    "secret_leak_check_passed": result.secret_leak_check_passed,
                    "quality_score": result.quality_score,
                    "passed": result.passed,
                    "duration_seconds": result.duration_seconds,
                },
            }
        )
    return rows


def upload_phoenix_dataset_rows(
    eval_run: FixtureEvalRun,
    *,
    dataset_name: str = DEFAULT_PHOENIX_DATASET_NAME,
    base_url: str | None = None,
) -> PhoenixDatasetUploadResult:
    try:
        from phoenix.client import Client
    except ImportError as exc:
        raise RuntimeError(
            "Phoenix dataset upload requires the optional extra: "
            "uv run --extra phoenix agent-permit eval --upload-phoenix ..."
        ) from exc

    rows = build_phoenix_dataset_rows(eval_run)
    examples = [
        {
            "id": row["id"],
            "input": row["inputs"],
            "output": row["outputs"],
            "metadata": row["metadata"],
        }
        for row in rows
    ]
    resolved_base_url = base_url or os.environ.get(
        "PHOENIX_BASE_URL",
        DEFAULT_PHOENIX_BASE_URL,
    )
    client = Client(base_url=resolved_base_url)
    dataset = client.datasets.create_dataset(
        name=dataset_name,
        dataset_description=(
            "Agent Permit Office deterministic fixture evals. "
            "Permit status remains scanner-owned source of truth."
        ),
        examples=examples,
    )
    return PhoenixDatasetUploadResult(
        dataset_name=_read_attr(dataset, "name", dataset_name),
        example_count=int(_read_attr(dataset, "example_count", len(examples))),
        base_url=resolved_base_url,
        dataset_id=_optional_str_attr(dataset, "id"),
        version_id=_optional_str_attr(dataset, "version_id"),
    )


def build_eval_report_markdown(eval_run: FixtureEvalRun) -> str:
    passed = sum(1 for result in eval_run.results if result.passed)
    total = len(eval_run.results)
    lines = [
        "# Agent Permit Office Eval Report",
        "",
        f"Eval run: `{eval_run.eval_run_id}`",
        f"Status: `{'passed' if eval_run.passed else 'failed'}`",
        f"Cases: `{passed}/{total}`",
        f"Fixture root: `{eval_run.fixture_root}`",
        "",
        "## Cases",
        "",
        "| Fixture | Status | Rules | Citations | Secret Leak | Quality |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for result in eval_run.results:
        status = "pass" if result.passed else "fail"
        rule_status = "pass"
        if result.missing_rule_ids or result.unexpected_rule_ids:
            rule_status = "fail"
        lines.append(
            "| "
            + " | ".join(
                [
                    result.fixture_id,
                    status,
                    rule_status,
                    "pass" if result.citation_check_passed else "fail",
                    "pass" if result.secret_leak_check_passed else "fail",
                    f"{result.quality_score:.2f}",
                ]
            )
            + " |"
        )
    lines.append("")
    lines.append("## Failures")
    lines.append("")
    failures = [result for result in eval_run.results if not result.passed]
    if not failures:
        lines.append("No failures.")
    for result in failures:
        lines.extend(
            [
                f"### {result.fixture_id}",
                "",
                f"- expected status: `{result.expected_permit_status}`",
                f"- actual status: `{result.actual_permit_status}`",
                f"- missing rules: `{', '.join(result.missing_rule_ids) or 'none'}`",
                f"- unexpected rules: `{', '.join(result.unexpected_rule_ids) or 'none'}`",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _eval_run_payload(eval_run: FixtureEvalRun) -> dict[str, Any]:
    return {
        "eval_run_id": eval_run.eval_run_id,
        "fixture_root": str(eval_run.fixture_root),
        "output_dir": str(eval_run.output_dir),
        "started_at": eval_run.started_at.isoformat(),
        "completed_at": eval_run.completed_at.isoformat(),
        "passed": eval_run.passed,
        "summary": {
            "total": len(eval_run.results),
            "passed": sum(1 for result in eval_run.results if result.passed),
            "failed": sum(1 for result in eval_run.results if not result.passed),
        },
        "results": [
            {
                "fixture_id": result.fixture_id,
                "passed": result.passed,
                "expected_permit_status": result.expected_permit_status,
                "actual_permit_status": result.actual_permit_status,
                "expected_rule_ids": list(result.expected_rule_ids),
                "actual_rule_ids": list(result.actual_rule_ids),
                "missing_rule_ids": list(result.missing_rule_ids),
                "unexpected_rule_ids": list(result.unexpected_rule_ids),
                "status_check_passed": result.status_check_passed,
                "rule_id_check_passed": result.rule_id_check_passed,
                "citation_check_passed": result.citation_check_passed,
                "secret_leak_check_passed": result.secret_leak_check_passed,
                "quality_score": result.quality_score,
                "artifact_dir": str(result.artifact_dir),
                "duration_seconds": result.duration_seconds,
            }
            for result in eval_run.results
        ],
    }


def _artifact_tree_contains_secret_marker(artifact_dir: Path) -> bool:
    for path in artifact_dir.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if any(marker in text for marker in SECRET_LEAK_MARKERS):
            return True
    return False


def _read_attr(target: object, name: str, default: object) -> object:
    if isinstance(target, dict):
        return target.get(name, default)
    return getattr(target, name, default)


def _optional_str_attr(target: object, name: str) -> str | None:
    value = _read_attr(target, name, None)
    if value is None:
        return None
    return str(value)


class _NullWriter:
    def __init__(self) -> None:
        self.text = ""

    def __enter__(self) -> "_NullWriter":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def write(self, text: str) -> int:
        self.text += text
        return len(text)

    def flush(self) -> None:
        return None
