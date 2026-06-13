from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import time
from typing import Any

from agent_permit.analytics import (
    analytics_events_path_for_output,
    append_analytics_event,
    build_analytics_event,
    write_eval_trends,
)
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
REAL_REPO_EVALS_DIR = "real-repo-evals"
REAL_REPO_EVAL_RESULTS_FILE = "real-repo-eval-results.json"
REAL_REPO_EVAL_REPORT_FILE = "real-repo-eval-report.md"
LIVE_REPO_VALIDATIONS_DIR = "live-repo-validations"
LIVE_REPO_VALIDATION_RESULTS_FILE = "live-repo-validation-results.json"
LIVE_REPO_VALIDATION_REPORT_FILE = "live-repo-validation-report.md"
LIVE_REPO_VALIDATION_REPOS_DIR = "repos"
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


@dataclass(frozen=True)
class RealRepoEvalCase:
    repo_id: str
    repo_path: Path
    source: str
    expected_permit_status: str
    expected_rule_ids_present: tuple[str, ...]
    expected_rule_ids_absent: tuple[str, ...]
    notes: str


@dataclass(frozen=True)
class RealRepoEvalResult:
    repo_id: str
    passed: bool
    source: str
    repo_path: Path
    expected_permit_status: str
    actual_permit_status: str
    expected_rule_ids_present: tuple[str, ...]
    expected_rule_ids_absent: tuple[str, ...]
    actual_rule_ids: tuple[str, ...]
    missing_rule_ids: tuple[str, ...]
    forbidden_rule_ids: tuple[str, ...]
    status_check_passed: bool
    expected_rule_check_passed: bool
    forbidden_rule_check_passed: bool
    citation_check_passed: bool
    secret_leak_check_passed: bool
    quality_score: float
    findings_count: int
    artifact_dir: Path
    investigation_report: Path
    duration_seconds: float


@dataclass(frozen=True)
class RealRepoEvalRun:
    eval_run_id: str
    output_dir: Path
    manifest_path: Path
    repo_root: Path | None
    results: tuple[RealRepoEvalResult, ...]
    started_at: datetime
    completed_at: datetime

    @property
    def passed(self) -> bool:
        return all(result.passed for result in self.results)


@dataclass(frozen=True)
class LiveRepoValidationCase:
    repo_id: str
    repo_path: Path
    source: str
    expected_permit_status: str | None
    expected_rule_ids_present: tuple[str, ...]
    expected_rule_ids_absent: tuple[str, ...]
    run_id: str | None
    notes: str


@dataclass(frozen=True)
class LiveRepoValidationResult:
    repo_id: str
    passed: bool
    live_validation_passed: bool
    expectation_check_passed: bool
    source: str
    repo_path: Path
    run_id: str
    expected_permit_status: str | None
    actual_permit_status: str
    expected_rule_ids_present: tuple[str, ...]
    expected_rule_ids_absent: tuple[str, ...]
    actual_rule_ids: tuple[str, ...]
    missing_rule_ids: tuple[str, ...]
    forbidden_rule_ids: tuple[str, ...]
    status_check_passed: bool
    expected_rule_check_passed: bool
    forbidden_rule_check_passed: bool
    citation_check_passed: bool
    findings_count: int
    graph_paths_count: int
    controls_count: int
    model_calls: int
    input_tokens: int
    total_tokens: int
    cached_tokens: int
    cache_hit_ratio: float
    artifact_dir: Path
    report_path: Path | None
    usage_path: Path | None
    validation_path: Path | None
    error_message: str
    duration_seconds: float


@dataclass(frozen=True)
class LiveRepoValidationRun:
    validation_run_id: str
    output_dir: Path
    manifest_path: Path
    repo_root: Path | None
    results: tuple[LiveRepoValidationResult, ...]
    started_at: datetime
    completed_at: datetime

    @property
    def passed(self) -> bool:
        return all(result.passed for result in self.results)


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


def load_real_repo_cases(
    manifest_path: Path,
    *,
    repo_root: Path | None = None,
) -> list[RealRepoEvalCase]:
    manifest_path = manifest_path.resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    repos = manifest.get("repos", [])
    if not repos:
        raise ValueError(f"no repos found in manifest {manifest_path}")
    cases: list[RealRepoEvalCase] = []
    for entry in repos:
        repo_path = Path(str(entry["local_path"]))
        if not repo_path.is_absolute():
            repo_path = (repo_root or manifest_path.parent) / repo_path
        cases.append(
            RealRepoEvalCase(
                repo_id=str(entry["id"]),
                repo_path=repo_path.resolve(),
                source=str(entry.get("source", "")),
                expected_permit_status=str(entry["expected_permit_status"]),
                expected_rule_ids_present=tuple(
                    sorted(entry.get("expected_rule_ids_present", []))
                ),
                expected_rule_ids_absent=tuple(
                    sorted(entry.get("expected_rule_ids_absent", []))
                ),
                notes=str(entry.get("notes", "")),
            )
        )
    return cases


def load_live_repo_validation_cases(
    manifest_path: Path,
    *,
    repo_root: Path | None = None,
) -> list[LiveRepoValidationCase]:
    manifest_path = manifest_path.resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    repos = manifest.get("repos", [])
    if not repos:
        raise ValueError(f"no repos found in manifest {manifest_path}")
    cases: list[LiveRepoValidationCase] = []
    for entry in repos:
        repo_path = Path(str(entry["local_path"]))
        if not repo_path.is_absolute():
            repo_path = (repo_root or manifest_path.parent) / repo_path
        expected_status = entry.get("expected_permit_status")
        cases.append(
            LiveRepoValidationCase(
                repo_id=str(entry["id"]),
                repo_path=repo_path.resolve(),
                source=str(entry.get("source", "")),
                expected_permit_status=(
                    str(expected_status) if expected_status is not None else None
                ),
                expected_rule_ids_present=tuple(
                    sorted(entry.get("expected_rule_ids_present", []))
                ),
                expected_rule_ids_absent=tuple(
                    sorted(entry.get("expected_rule_ids_absent", []))
                ),
                run_id=str(entry["run_id"]) if entry.get("run_id") else None,
                notes=str(entry.get("notes", "")),
            )
        )
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


def run_real_repo_eval_suite(
    manifest_path: Path,
    *,
    repo_root: Path | None = None,
    eval_run_id: str | None = None,
    output_dir: Path | None = None,
    exclude_patterns: tuple[str, ...] = (),
) -> RealRepoEvalRun:
    manifest_path = manifest_path.resolve()
    repo_root = repo_root.resolve() if repo_root is not None else None
    eval_run_id = eval_run_id or create_eval_run_id()
    output_dir = (
        output_dir or (Path.cwd() / ARTIFACT_ROOT / REAL_REPO_EVALS_DIR / eval_run_id)
    ).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(timezone.utc)

    cases = load_real_repo_cases(manifest_path, repo_root=repo_root)
    results = [
        _run_real_repo_case(
            case,
            eval_run_id,
            exclude_patterns=exclude_patterns,
        )
        for case in cases
    ]
    completed_at = datetime.now(timezone.utc)
    eval_run = RealRepoEvalRun(
        eval_run_id=eval_run_id,
        output_dir=output_dir,
        manifest_path=manifest_path,
        repo_root=repo_root,
        results=tuple(results),
        started_at=started_at,
        completed_at=completed_at,
    )
    _write_real_repo_eval_artifacts(eval_run)
    return eval_run


def run_live_repo_validation_suite(
    manifest_path: Path,
    *,
    repo_root: Path | None = None,
    validation_run_id: str | None = None,
    output_dir: Path | None = None,
    model: str | None = None,
    agent_recursion_limit: int = 12,
    enable_phoenix: bool = False,
    enable_langsmith: bool = False,
    exclude_patterns: tuple[str, ...] = (),
) -> LiveRepoValidationRun:
    manifest_path = manifest_path.resolve()
    repo_root = repo_root.resolve() if repo_root is not None else None
    validation_run_id = validation_run_id or create_eval_run_id()
    output_dir = (
        output_dir
        or (Path.cwd() / ARTIFACT_ROOT / LIVE_REPO_VALIDATIONS_DIR / validation_run_id)
    ).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(timezone.utc)

    cases = load_live_repo_validation_cases(manifest_path, repo_root=repo_root)
    results = [
        _run_live_repo_validation_case(
            case,
            validation_run_id,
            model=model,
            agent_recursion_limit=agent_recursion_limit,
            enable_phoenix=enable_phoenix,
            enable_langsmith=enable_langsmith,
            exclude_patterns=exclude_patterns,
        )
        for case in cases
    ]
    completed_at = datetime.now(timezone.utc)
    validation_run = LiveRepoValidationRun(
        validation_run_id=validation_run_id,
        output_dir=output_dir,
        manifest_path=manifest_path,
        repo_root=repo_root,
        results=tuple(results),
        started_at=started_at,
        completed_at=completed_at,
    )
    validation_run = _preserve_live_repo_artifacts(validation_run)
    _write_live_repo_validation_artifacts(validation_run)
    return validation_run


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


def _run_real_repo_case(
    case: RealRepoEvalCase,
    eval_run_id: str,
    *,
    exclude_patterns: tuple[str, ...],
) -> RealRepoEvalResult:
    from agent_permit.cli import run_investigate, run_scan

    if not case.repo_path.exists():
        raise RuntimeError(f"repo path does not exist for {case.repo_id}: {case.repo_path}")
    if not case.repo_path.is_dir():
        raise RuntimeError(f"repo path must be a directory for {case.repo_id}: {case.repo_path}")

    start = time.perf_counter()
    scan_run_id = f"{eval_run_id}-{case.repo_id}"
    with _NullWriter() as stdout, _NullWriter() as stderr:
        scan_exit_code = run_scan(
            case.repo_path,
            run_id=scan_run_id,
            ci=False,
            exclude_patterns=exclude_patterns,
            stdout=stdout,
            stderr=stderr,
        )
        stderr_text = stderr.text
    if scan_exit_code != 0:
        raise RuntimeError(f"real repo scan failed for {case.repo_id}: {stderr_text}")

    artifact_dir = case.repo_path / ARTIFACT_ROOT / "runs" / scan_run_id
    with _NullWriter() as stdout, _NullWriter() as stderr:
        investigate_exit_code = run_investigate(
            artifact_dir,
            deterministic_only=True,
            stdout=stdout,
            stderr=stderr,
        )
        stderr_text = stderr.text
    if investigate_exit_code != 0:
        raise RuntimeError(
            f"real repo investigation failed for {case.repo_id}: {stderr_text}"
        )

    context = EvidenceContext.load(artifact_dir)
    actual_rule_ids = tuple(sorted({finding.rule_id for finding in context.findings}))
    expected_present = tuple(sorted(case.expected_rule_ids_present))
    expected_absent = tuple(sorted(case.expected_rule_ids_absent))
    missing_rule_ids = tuple(sorted(set(expected_present) - set(actual_rule_ids)))
    forbidden_rule_ids = tuple(sorted(set(expected_absent) & set(actual_rule_ids)))
    report_path = artifact_dir / "agent-investigation.md"
    report_markdown = report_path.read_text(encoding="utf-8")
    citation_result = critique_investigation_report(context, report_markdown)
    secret_leak_check_passed = not _artifact_tree_contains_secret_marker(artifact_dir)
    status_check_passed = case.expected_permit_status == context.permit_status
    expected_rule_check_passed = not missing_rule_ids
    forbidden_rule_check_passed = not forbidden_rule_ids
    check_results = (
        status_check_passed,
        expected_rule_check_passed,
        forbidden_rule_check_passed,
        citation_result.supported,
        secret_leak_check_passed,
    )
    passed = all(check_results)
    return RealRepoEvalResult(
        repo_id=case.repo_id,
        passed=passed,
        source=case.source,
        repo_path=case.repo_path,
        expected_permit_status=case.expected_permit_status,
        actual_permit_status=context.permit_status,
        expected_rule_ids_present=expected_present,
        expected_rule_ids_absent=expected_absent,
        actual_rule_ids=actual_rule_ids,
        missing_rule_ids=missing_rule_ids,
        forbidden_rule_ids=forbidden_rule_ids,
        status_check_passed=status_check_passed,
        expected_rule_check_passed=expected_rule_check_passed,
        forbidden_rule_check_passed=forbidden_rule_check_passed,
        citation_check_passed=citation_result.supported,
        secret_leak_check_passed=secret_leak_check_passed,
        quality_score=round(sum(check_results) / len(check_results), 4),
        findings_count=len(context.findings),
        artifact_dir=artifact_dir,
        investigation_report=report_path,
        duration_seconds=round(time.perf_counter() - start, 4),
    )


def _run_live_repo_validation_case(
    case: LiveRepoValidationCase,
    validation_run_id: str,
    *,
    model: str | None,
    agent_recursion_limit: int,
    enable_phoenix: bool,
    enable_langsmith: bool,
    exclude_patterns: tuple[str, ...],
) -> LiveRepoValidationResult:
    from agent_permit.cli import run_live_validate

    if not case.repo_path.exists():
        raise RuntimeError(f"repo path does not exist for {case.repo_id}: {case.repo_path}")
    if not case.repo_path.is_dir():
        raise RuntimeError(f"repo path must be a directory for {case.repo_id}: {case.repo_path}")

    start = time.perf_counter()
    run_id = case.run_id or f"{validation_run_id}-{case.repo_id}"
    artifact_dir = case.repo_path / ARTIFACT_ROOT / "runs" / run_id
    with _NullWriter() as stdout, _NullWriter() as stderr:
        exit_code = run_live_validate(
            case.repo_path,
            run_id=run_id,
            model=model,
            agent_recursion_limit=agent_recursion_limit,
            enable_phoenix=enable_phoenix,
            enable_langsmith=enable_langsmith,
            exclude_patterns=exclude_patterns,
            stdout=stdout,
            stderr=stderr,
        )
        stdout_text = stdout.text
        stderr_text = stderr.text

    validation_path = artifact_dir / "live-validation.json"
    validation_payload = _read_json_file(validation_path)
    actual_status = str(validation_payload.get("permit_status", "unknown"))
    findings_count = int(validation_payload.get("findings") or 0)
    graph_paths_count = int(validation_payload.get("graph_paths") or 0)
    controls_count = int(validation_payload.get("controls") or 0)
    citation_payload = validation_payload.get("citation_check", {})
    citation_check_passed = (
        isinstance(citation_payload, dict)
        and citation_payload.get("supported") is True
    )
    usage_payload = validation_payload.get("usage_summary", {})
    usage = usage_payload if isinstance(usage_payload, dict) else {}
    live_validation_passed = (
        exit_code == 0
        and validation_payload.get("status") == "passed"
        and citation_check_passed
    )
    actual_rule_ids = _load_artifact_rule_ids(artifact_dir)
    expected_present = tuple(sorted(case.expected_rule_ids_present))
    expected_absent = tuple(sorted(case.expected_rule_ids_absent))
    missing_rule_ids = tuple(sorted(set(expected_present) - set(actual_rule_ids)))
    forbidden_rule_ids = tuple(sorted(set(expected_absent) & set(actual_rule_ids)))
    status_check_passed = (
        case.expected_permit_status is None
        or case.expected_permit_status == actual_status
    )
    expected_rule_check_passed = not missing_rule_ids
    forbidden_rule_check_passed = not forbidden_rule_ids
    expectation_check_passed = (
        status_check_passed
        and expected_rule_check_passed
        and forbidden_rule_check_passed
    )
    report_path = _optional_path(validation_payload.get("report_path"))
    usage_path = _optional_path(validation_payload.get("usage_path"))
    error_message = "\n".join(
        text for text in (stderr_text.strip(), stdout_text.strip()) if text
    )
    return LiveRepoValidationResult(
        repo_id=case.repo_id,
        passed=live_validation_passed and expectation_check_passed,
        live_validation_passed=live_validation_passed,
        expectation_check_passed=expectation_check_passed,
        source=case.source,
        repo_path=case.repo_path,
        run_id=run_id,
        expected_permit_status=case.expected_permit_status,
        actual_permit_status=actual_status,
        expected_rule_ids_present=expected_present,
        expected_rule_ids_absent=expected_absent,
        actual_rule_ids=actual_rule_ids,
        missing_rule_ids=missing_rule_ids,
        forbidden_rule_ids=forbidden_rule_ids,
        status_check_passed=status_check_passed,
        expected_rule_check_passed=expected_rule_check_passed,
        forbidden_rule_check_passed=forbidden_rule_check_passed,
        citation_check_passed=citation_check_passed,
        findings_count=findings_count,
        graph_paths_count=graph_paths_count,
        controls_count=controls_count,
        model_calls=int(usage.get("model_calls") or 0),
        input_tokens=int(usage.get("input_tokens") or 0),
        total_tokens=int(usage.get("total_tokens") or 0),
        cached_tokens=int(usage.get("cached_tokens") or 0),
        cache_hit_ratio=float(usage.get("cache_hit_ratio") or 0.0),
        artifact_dir=artifact_dir,
        report_path=report_path,
        usage_path=usage_path,
        validation_path=validation_path if validation_path.is_file() else None,
        error_message=error_message if not live_validation_passed else "",
        duration_seconds=round(time.perf_counter() - start, 4),
    )


def _preserve_live_repo_artifacts(
    validation_run: LiveRepoValidationRun,
) -> LiveRepoValidationRun:
    preserved_results = []
    for result in validation_run.results:
        if not result.artifact_dir.is_dir():
            preserved_results.append(result)
            continue

        repo_dir = (
            validation_run.output_dir
            / LIVE_REPO_VALIDATION_REPOS_DIR
            / _safe_artifact_segment(result.repo_id)
            / result.run_id
        )
        if repo_dir.exists():
            shutil.rmtree(repo_dir)
        repo_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(result.artifact_dir, repo_dir)

        preserved_results.append(
            replace(
                result,
                artifact_dir=repo_dir,
                report_path=_preserved_artifact_path(
                    result.report_path,
                    original_dir=result.artifact_dir,
                    preserved_dir=repo_dir,
                ),
                usage_path=_preserved_artifact_path(
                    result.usage_path,
                    original_dir=result.artifact_dir,
                    preserved_dir=repo_dir,
                ),
                validation_path=_preserved_artifact_path(
                    result.validation_path,
                    original_dir=result.artifact_dir,
                    preserved_dir=repo_dir,
                ),
            )
        )

    return replace(validation_run, results=tuple(preserved_results))


def _preserved_artifact_path(
    path: Path | None,
    *,
    original_dir: Path,
    preserved_dir: Path,
) -> Path | None:
    if path is None:
        return None
    try:
        relative = path.resolve().relative_to(original_dir.resolve())
    except ValueError:
        relative = Path(path.name)
    candidate = preserved_dir / relative
    return candidate if candidate.is_file() else None


def _safe_artifact_segment(value: str) -> str:
    safe = "".join(
        character if character.isalnum() or character in {"-", "_", "."} else "-"
        for character in value
    ).strip(".")
    return safe or "repo"


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
    write_eval_trends(eval_run.output_dir, eval_run.eval_run_id)
    append_analytics_event(
        analytics_events_path_for_output(eval_run.output_dir),
        build_analytics_event(
            "eval_completed",
            run_id=eval_run.eval_run_id,
            run_type="fixture_eval",
            status="passed" if eval_run.passed else "failed",
            payload={
                "total_cases": len(eval_run.results),
                "passed_cases": sum(1 for result in eval_run.results if result.passed),
                "failed_cases": sum(
                    1 for result in eval_run.results if not result.passed
                ),
                "citation_failures": sum(
                    1
                    for result in eval_run.results
                    if not result.citation_check_passed
                ),
                "secret_leak_failures": sum(
                    1
                    for result in eval_run.results
                    if not result.secret_leak_check_passed
                ),
            },
        ),
    )


def _write_real_repo_eval_artifacts(eval_run: RealRepoEvalRun) -> None:
    (eval_run.output_dir / REAL_REPO_EVAL_RESULTS_FILE).write_text(
        json.dumps(_real_repo_eval_run_payload(eval_run), indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    (eval_run.output_dir / REAL_REPO_EVAL_REPORT_FILE).write_text(
        build_real_repo_eval_report_markdown(eval_run),
        encoding="utf-8",
    )


def _write_live_repo_validation_artifacts(
    validation_run: LiveRepoValidationRun,
) -> None:
    (validation_run.output_dir / LIVE_REPO_VALIDATION_RESULTS_FILE).write_text(
        json.dumps(
            _live_repo_validation_run_payload(validation_run),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (validation_run.output_dir / LIVE_REPO_VALIDATION_REPORT_FILE).write_text(
        build_live_repo_validation_report_markdown(validation_run),
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


def build_real_repo_eval_report_markdown(eval_run: RealRepoEvalRun) -> str:
    passed = sum(1 for result in eval_run.results if result.passed)
    total = len(eval_run.results)
    lines = [
        "# Agent Permit Office Real Repo Eval Report",
        "",
        f"Eval run: `{eval_run.eval_run_id}`",
        f"Status: `{'passed' if eval_run.passed else 'failed'}`",
        f"Cases: `{passed}/{total}`",
        f"Manifest: `{eval_run.manifest_path}`",
        "",
        "## Cases",
        "",
        "| Repo | Status | Expected Rules | Forbidden Rules | Citations | Secret Leak | Quality |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for result in eval_run.results:
        lines.append(
            "| "
            + " | ".join(
                [
                    result.repo_id,
                    "pass" if result.passed else "fail",
                    "pass" if result.expected_rule_check_passed else "fail",
                    "pass" if result.forbidden_rule_check_passed else "fail",
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
                f"### {result.repo_id}",
                "",
                f"- expected status: `{result.expected_permit_status}`",
                f"- actual status: `{result.actual_permit_status}`",
                f"- missing rules: `{', '.join(result.missing_rule_ids) or 'none'}`",
                f"- forbidden rules found: `{', '.join(result.forbidden_rule_ids) or 'none'}`",
                f"- artifacts: `{result.artifact_dir}`",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def build_live_repo_validation_report_markdown(
    validation_run: LiveRepoValidationRun,
) -> str:
    passed = sum(1 for result in validation_run.results if result.passed)
    total = len(validation_run.results)
    total_tokens = sum(result.total_tokens for result in validation_run.results)
    input_tokens = sum(result.input_tokens for result in validation_run.results)
    cached_tokens = sum(result.cached_tokens for result in validation_run.results)
    cache_hit_ratio = (
        round(cached_tokens / input_tokens, 4)
        if input_tokens
        else 0.0
    )
    lines = [
        "# Agent Permit Office Live Repo Validation Report",
        "",
        f"Validation run: `{validation_run.validation_run_id}`",
        f"Status: `{'passed' if validation_run.passed else 'failed'}`",
        f"Repos: `{passed}/{total}`",
        f"Manifest: `{validation_run.manifest_path}`",
        f"Total tokens: `{total_tokens}`",
        f"Cached tokens: `{cached_tokens}`",
        f"Cache hit ratio: `{cache_hit_ratio:.2%}`",
        "",
        "## Repos",
        "",
        "| Repo | Status | Permit | Findings | Paths | Controls | Citations | Expectations | Tokens | Cached |",
        "| --- | --- | --- | ---: | ---: | ---: | --- | --- | ---: | ---: |",
    ]
    for result in validation_run.results:
        lines.append(
            "| "
            + " | ".join(
                [
                    result.repo_id,
                    "pass" if result.passed else "fail",
                    result.actual_permit_status,
                    str(result.findings_count),
                    str(result.graph_paths_count),
                    str(result.controls_count),
                    "pass" if result.citation_check_passed else "fail",
                    "pass" if result.expectation_check_passed else "fail",
                    str(result.total_tokens),
                    str(result.cached_tokens),
                ]
            )
            + " |"
        )
    lines.append("")
    lines.append("## Failures")
    lines.append("")
    failures = [result for result in validation_run.results if not result.passed]
    if not failures:
        lines.append("No failures.")
    for result in failures:
        lines.extend(
            [
                f"### {result.repo_id}",
                "",
                f"- live validation: `{'pass' if result.live_validation_passed else 'fail'}`",
                f"- expectation check: `{'pass' if result.expectation_check_passed else 'fail'}`",
                f"- expected status: `{result.expected_permit_status or 'not set'}`",
                f"- actual status: `{result.actual_permit_status}`",
                f"- missing rules: `{', '.join(result.missing_rule_ids) or 'none'}`",
                f"- forbidden rules found: `{', '.join(result.forbidden_rule_ids) or 'none'}`",
                f"- validation: `{result.validation_path or 'not written'}`",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


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


def _real_repo_eval_run_payload(eval_run: RealRepoEvalRun) -> dict[str, Any]:
    return {
        "eval_run_id": eval_run.eval_run_id,
        "manifest_path": str(eval_run.manifest_path),
        "repo_root": str(eval_run.repo_root) if eval_run.repo_root is not None else None,
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
                "repo_id": result.repo_id,
                "passed": result.passed,
                "source": result.source,
                "repo_path": str(result.repo_path),
                "expected_permit_status": result.expected_permit_status,
                "actual_permit_status": result.actual_permit_status,
                "expected_rule_ids_present": list(result.expected_rule_ids_present),
                "expected_rule_ids_absent": list(result.expected_rule_ids_absent),
                "actual_rule_ids": list(result.actual_rule_ids),
                "missing_rule_ids": list(result.missing_rule_ids),
                "forbidden_rule_ids": list(result.forbidden_rule_ids),
                "status_check_passed": result.status_check_passed,
                "expected_rule_check_passed": result.expected_rule_check_passed,
                "forbidden_rule_check_passed": result.forbidden_rule_check_passed,
                "citation_check_passed": result.citation_check_passed,
                "secret_leak_check_passed": result.secret_leak_check_passed,
                "quality_score": result.quality_score,
                "findings_count": result.findings_count,
                "artifact_dir": str(result.artifact_dir),
                "investigation_report": str(result.investigation_report),
                "duration_seconds": result.duration_seconds,
            }
            for result in eval_run.results
        ],
    }


def _live_repo_validation_run_payload(
    validation_run: LiveRepoValidationRun,
) -> dict[str, Any]:
    total_tokens = sum(result.total_tokens for result in validation_run.results)
    input_tokens = sum(result.input_tokens for result in validation_run.results)
    cached_tokens = sum(result.cached_tokens for result in validation_run.results)
    return {
        "validation_run_id": validation_run.validation_run_id,
        "manifest_path": str(validation_run.manifest_path),
        "repo_root": (
            str(validation_run.repo_root)
            if validation_run.repo_root is not None
            else None
        ),
        "output_dir": str(validation_run.output_dir),
        "started_at": validation_run.started_at.isoformat(),
        "completed_at": validation_run.completed_at.isoformat(),
        "passed": validation_run.passed,
        "summary": {
            "total": len(validation_run.results),
            "passed": sum(1 for result in validation_run.results if result.passed),
            "failed": sum(1 for result in validation_run.results if not result.passed),
            "total_tokens": total_tokens,
            "input_tokens": input_tokens,
            "cached_tokens": cached_tokens,
            "cache_hit_ratio": (
                round(cached_tokens / input_tokens, 4)
                if input_tokens
                else 0.0
            ),
        },
        "results": [
            {
                "repo_id": result.repo_id,
                "passed": result.passed,
                "live_validation_passed": result.live_validation_passed,
                "expectation_check_passed": result.expectation_check_passed,
                "source": result.source,
                "repo_path": str(result.repo_path),
                "run_id": result.run_id,
                "expected_permit_status": result.expected_permit_status,
                "actual_permit_status": result.actual_permit_status,
                "expected_rule_ids_present": list(result.expected_rule_ids_present),
                "expected_rule_ids_absent": list(result.expected_rule_ids_absent),
                "actual_rule_ids": list(result.actual_rule_ids),
                "missing_rule_ids": list(result.missing_rule_ids),
                "forbidden_rule_ids": list(result.forbidden_rule_ids),
                "status_check_passed": result.status_check_passed,
                "expected_rule_check_passed": result.expected_rule_check_passed,
                "forbidden_rule_check_passed": result.forbidden_rule_check_passed,
                "citation_check_passed": result.citation_check_passed,
                "findings_count": result.findings_count,
                "graph_paths_count": result.graph_paths_count,
                "controls_count": result.controls_count,
                "model_calls": result.model_calls,
                "input_tokens": result.input_tokens,
                "total_tokens": result.total_tokens,
                "cached_tokens": result.cached_tokens,
                "cache_hit_ratio": result.cache_hit_ratio,
                "artifact_dir": str(result.artifact_dir),
                "report_path": str(result.report_path) if result.report_path else None,
                "usage_path": str(result.usage_path) if result.usage_path else None,
                "validation_path": (
                    str(result.validation_path) if result.validation_path else None
                ),
                "error_message": result.error_message,
                "duration_seconds": result.duration_seconds,
            }
            for result in validation_run.results
        ],
    }


def _read_json_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _load_artifact_rule_ids(artifact_dir: Path) -> tuple[str, ...]:
    payload = _read_json_file(artifact_dir / "raw-findings.json")
    findings = payload.get("findings", [])
    if not isinstance(findings, list):
        return ()
    rule_ids = {
        str(finding.get("rule_id"))
        for finding in findings
        if isinstance(finding, dict) and finding.get("rule_id")
    }
    return tuple(sorted(rule_ids))


def _optional_path(value: object) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    return Path(value)


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
