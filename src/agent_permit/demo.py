from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path
import subprocess
import time
from typing import Any

from agent_permit.artifacts import ARTIFACT_ROOT
from agent_permit.evals import (
    LiveRepoValidationResult,
    LiveRepoValidationRun,
    load_live_repo_validation_cases,
    run_live_repo_validation_suite,
)


OPEN_SOURCE_DEMOS_DIR = "open-source-demos"
OPEN_SOURCE_DEMO_RESULTS_FILE = "open-source-demo-results.json"
OPEN_SOURCE_DEMO_REPORT_FILE = "open-source-demo-report.md"
OPEN_SOURCE_DEMO_HTML_FILE = "open-source-demo-report.html"
DEFAULT_OPEN_SOURCE_DEMO_ROOT = Path("/tmp/agent-permit-open-source-validation")


@dataclass(frozen=True)
class RepoPreparationResult:
    repo_id: str
    source: str
    repo_path: Path
    status: str
    commit: str | None
    commit_date: str | None
    commit_message: str | None
    error_message: str


@dataclass(frozen=True)
class OpenSourceDemoRun:
    demo_run_id: str
    manifest_path: Path
    repo_root: Path
    output_dir: Path
    repo_results: tuple[RepoPreparationResult, ...]
    validation_run: LiveRepoValidationRun | None
    started_at: datetime
    completed_at: datetime

    @property
    def passed(self) -> bool:
        repos_ready = all(result.status != "failed" for result in self.repo_results)
        validation_ready = self.validation_run is None or self.validation_run.passed
        return repos_ready and validation_ready


def run_open_source_demo(
    manifest_path: Path,
    *,
    repo_root: Path = DEFAULT_OPEN_SOURCE_DEMO_ROOT,
    demo_run_id: str | None = None,
    output_dir: Path | None = None,
    prepare_repos: bool = True,
    refresh_repos: bool = True,
    run_live_validation: bool = True,
    model: str | None = None,
    agent_recursion_limit: int = 12,
    enable_phoenix: bool = False,
    enable_langsmith: bool = False,
    exclude_patterns: tuple[str, ...] = (),
) -> OpenSourceDemoRun:
    manifest_path = manifest_path.resolve()
    repo_root = repo_root.resolve()
    demo_run_id = demo_run_id or _create_demo_run_id()
    output_dir = (
        output_dir
        or (Path.cwd() / ARTIFACT_ROOT / OPEN_SOURCE_DEMOS_DIR / demo_run_id)
    ).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(timezone.utc)

    cases = load_live_repo_validation_cases(manifest_path, repo_root=repo_root)
    repo_results = tuple(
        _prepare_repo(
            repo_id=case.repo_id,
            source=case.source,
            repo_path=case.repo_path,
            prepare_repos=prepare_repos,
            refresh_repos=refresh_repos,
        )
        for case in cases
    )
    validation_run = None
    if run_live_validation and all(result.status != "failed" for result in repo_results):
        validation_run = run_live_repo_validation_suite(
            manifest_path,
            repo_root=repo_root,
            validation_run_id=demo_run_id,
            output_dir=output_dir / "live-validation",
            model=model,
            agent_recursion_limit=agent_recursion_limit,
            enable_phoenix=enable_phoenix,
            enable_langsmith=enable_langsmith,
            exclude_patterns=exclude_patterns,
        )

    completed_at = datetime.now(timezone.utc)
    demo_run = OpenSourceDemoRun(
        demo_run_id=demo_run_id,
        manifest_path=manifest_path,
        repo_root=repo_root,
        output_dir=output_dir,
        repo_results=repo_results,
        validation_run=validation_run,
        started_at=started_at,
        completed_at=completed_at,
    )
    _write_open_source_demo_artifacts(demo_run)
    return demo_run


def build_open_source_demo_report_markdown(demo_run: OpenSourceDemoRun) -> str:
    validation = demo_run.validation_run
    passed = sum(1 for result in validation.results if result.passed) if validation else 0
    total = len(validation.results) if validation else 0
    summary = _validation_summary(validation)
    lines = [
        "# Agent Permit Office Open Source Demo",
        "",
        f"Demo run: `{demo_run.demo_run_id}`",
        f"Status: `{'passed' if demo_run.passed else 'failed'}`",
        f"Manifest: `{demo_run.manifest_path}`",
        f"Repo root: `{demo_run.repo_root}`",
        "",
        "## Repo Prep",
        "",
        "| Repo | Status | Commit | Commit date | Message |",
        "| --- | --- | --- | --- | --- |",
    ]
    for result in demo_run.repo_results:
        lines.append(
            "| "
            + " | ".join(
                [
                    result.repo_id,
                    result.status,
                    result.commit[:7] if result.commit else "none",
                    result.commit_date or "unknown",
                    _markdown_cell(result.commit_message or result.error_message or ""),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Live Validation",
            "",
        ]
    )
    if validation is None:
        lines.append("Live validation was skipped.")
    else:
        lines.extend(
            [
                f"- repos passed: `{passed}/{total}`",
                f"- total tokens: `{summary['total_tokens']}`",
                f"- input tokens: `{summary['input_tokens']}`",
                f"- cached tokens: `{summary['cached_tokens']}`",
                f"- cache hit ratio: `{summary['cache_hit_ratio']:.2%}`",
                f"- aggregate JSON: `{validation.output_dir / 'live-repo-validation-results.json'}`",
                f"- aggregate report: `{validation.output_dir / 'live-repo-validation-report.md'}`",
                "",
                "| Repo | Status | Permit | Findings | Paths | Controls | Citations | Expectations |",
                "| --- | --- | --- | ---: | ---: | ---: | --- | --- |",
            ]
        )
        for result in validation.results:
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
                    ]
                )
                + " |"
            )
        lines.extend(
            [
                "",
                "## Reviewer Decision Queue",
                "",
                "This is the product view: each repo becomes a reviewer decision before agent access is expanded.",
                "",
                "| Repo | Permit | Reviewer question | Recommended response |",
                "| --- | --- | --- | --- |",
            ]
        )
        for result in validation.results:
            decision = _reviewer_decision(result.actual_permit_status)
            lines.append(
                "| "
                + " | ".join(
                    [
                        result.repo_id,
                        _permit_label(result.actual_permit_status),
                        _markdown_cell(decision["question"]),
                        _markdown_cell(decision["response"]),
                    ]
                )
                + " |"
            )
    lines.extend(
        [
            "",
            "## Demo Talk Track",
            "",
            "1. The scanner creates deterministic repo evidence and permit status.",
            "2. The Deep Agent explains only bounded artifacts and must cite evidence.",
            "3. The citation critic blocks unsupported claims before a run passes.",
            "4. The manifest runner proves approved, needs-review, and blocked paths across current open-source repos.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def build_open_source_demo_report_html(demo_run: OpenSourceDemoRun) -> str:
    validation = demo_run.validation_run
    summary = _validation_summary(validation)
    repo_rows = "\n".join(
        "<tr>"
        f"<td>{escape(result.repo_id)}</td>"
        f"<td>{escape(result.status)}</td>"
        f"<td>{escape((result.commit or 'none')[:7])}</td>"
        f"<td>{escape(result.commit_date or 'unknown')}</td>"
        f"<td>{escape(result.commit_message or result.error_message or '')}</td>"
        "</tr>"
        for result in demo_run.repo_results
    )
    validation_rows = ""
    decision_cards = ""
    if validation is not None:
        validation_rows = "\n".join(
            "<tr>"
            f"<td>{escape(result.repo_id)}</td>"
            f"<td>{'pass' if result.passed else 'fail'}</td>"
            f"<td>{escape(result.actual_permit_status)}</td>"
            f"<td>{result.findings_count}</td>"
            f"<td>{result.graph_paths_count}</td>"
            f"<td>{result.controls_count}</td>"
            f"<td>{'pass' if result.citation_check_passed else 'fail'}</td>"
            f"<td>{'pass' if result.expectation_check_passed else 'fail'}</td>"
            "</tr>"
            for result in validation.results
        )
        decision_cards = "\n".join(
            _reviewer_decision_card(result)
            for result in validation.results
        )
    live_block = (
        "<p>Live validation was skipped.</p>"
        if validation is None
        else f"""
        <div class=\"metrics\">
          <div><strong>{sum(1 for result in validation.results if result.passed)}/{len(validation.results)}</strong><span>repos passed</span></div>
          <div><strong>{summary['total_tokens']}</strong><span>total tokens</span></div>
          <div><strong>{summary['cached_tokens']}</strong><span>cached tokens</span></div>
          <div><strong>{summary['cache_hit_ratio']:.2%}</strong><span>cache hit</span></div>
        </div>
        <table>
          <thead><tr><th>Repo</th><th>Status</th><th>Permit</th><th>Findings</th><th>Paths</th><th>Controls</th><th>Citations</th><th>Expectations</th></tr></thead>
          <tbody>{validation_rows}</tbody>
        </table>
        <h2>Reviewer Decision Queue</h2>
        <p>This is the product view: each repo becomes a reviewer decision before agent access is expanded.</p>
        <div class=\"decisions\">{decision_cards}</div>
        """
    )
    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <title>Agent Permit Office Open Source Demo</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 40px; color: #172033; background: #f7f8fb; }}
    main {{ max-width: 1120px; margin: 0 auto; background: white; border: 1px solid #d9deea; padding: 32px; }}
    h1, h2 {{ margin-top: 0; }}
    table {{ width: 100%; border-collapse: collapse; margin: 16px 0 28px; font-size: 14px; }}
    th, td {{ border-bottom: 1px solid #e4e8f0; padding: 10px; text-align: left; vertical-align: top; }}
    th {{ color: #4b5875; background: #f1f4f9; }}
    .status {{ display: inline-block; padding: 4px 8px; border: 1px solid #9cc7a8; background: #eef9f0; color: #1d6b34; }}
    .metrics {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin: 16px 0 24px; }}
    .metrics div {{ border: 1px solid #d9deea; padding: 14px; background: #fbfcff; }}
    .metrics strong {{ display: block; font-size: 20px; }}
    .metrics span {{ color: #59647d; font-size: 13px; }}
    .decisions {{ display: grid; gap: 12px; margin: 16px 0 28px; }}
    .decision {{ border: 1px solid #d9deea; background: #fbfcff; padding: 16px; }}
    .decision h3 {{ margin: 0 0 6px; font-size: 16px; }}
    .decision .permit {{ display: inline-block; margin-bottom: 10px; color: #4b5875; font-size: 13px; }}
    .decision p {{ margin: 8px 0 0; }}
    code {{ background: #eef1f6; padding: 2px 4px; }}
  </style>
</head>
<body>
<main>
  <h1>Agent Permit Office Open Source Demo</h1>
  <p><span class=\"status\">{escape('passed' if demo_run.passed else 'failed')}</span></p>
  <p>Demo run <code>{escape(demo_run.demo_run_id)}</code> validates recent open-source agent and MCP repositories with deterministic scanner evidence, a bounded Deep Agent report, and citation checks.</p>
  <h2>Repo Prep</h2>
  <table>
    <thead><tr><th>Repo</th><th>Status</th><th>Commit</th><th>Commit date</th><th>Message</th></tr></thead>
    <tbody>{repo_rows}</tbody>
  </table>
  <h2>Live Validation</h2>
  {live_block}
  <h2>Talk Track</h2>
  <ol>
    <li>The scanner creates deterministic repo evidence and permit status.</li>
    <li>The Deep Agent explains only bounded artifacts and must cite evidence.</li>
    <li>The citation critic blocks unsupported claims before a run passes.</li>
    <li>The manifest runner proves approved, needs-review, and blocked paths across current open-source repos.</li>
  </ol>
</main>
</body>
</html>
"""


def _prepare_repo(
    *,
    repo_id: str,
    source: str,
    repo_path: Path,
    prepare_repos: bool,
    refresh_repos: bool,
) -> RepoPreparationResult:
    if not prepare_repos:
        return _repo_result(repo_id, source, repo_path, "skipped")
    repo_path.parent.mkdir(parents=True, exist_ok=True)
    if not repo_path.exists():
        result = _run_command(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--filter=blob:none",
                source,
                str(repo_path),
            ],
            cwd=repo_path.parent,
        )
        if result.returncode != 0:
            return _repo_result(
                repo_id,
                source,
                repo_path,
                "failed",
                error_message=result.stderr.strip() or result.stdout.strip(),
            )
        return _repo_result(repo_id, source, repo_path, "cloned")
    if not (repo_path / ".git").is_dir():
        return _repo_result(
            repo_id,
            source,
            repo_path,
            "failed",
            error_message="path exists but is not a git checkout",
        )
    if not refresh_repos:
        return _repo_result(repo_id, source, repo_path, "exists")
    dirty = _run_command(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=repo_path,
    )
    if dirty.returncode != 0:
        return _repo_result(repo_id, source, repo_path, "failed", dirty.stderr.strip())
    if dirty.stdout.strip():
        return _repo_result(
            repo_id,
            source,
            repo_path,
            "failed",
            error_message="checkout has local changes; refusing to refresh",
        )
    pull = _run_command(["git", "pull", "--ff-only"], cwd=repo_path)
    if pull.returncode != 0:
        return _repo_result(
            repo_id,
            source,
            repo_path,
            "failed",
            error_message=pull.stderr.strip() or pull.stdout.strip(),
        )
    return _repo_result(repo_id, source, repo_path, "updated")


def _repo_result(
    repo_id: str,
    source: str,
    repo_path: Path,
    status: str,
    error_message: str = "",
) -> RepoPreparationResult:
    commit = commit_date = commit_message = None
    if (repo_path / ".git").is_dir():
        log = _run_command(["git", "log", "-1", "--format=%H%x09%cI%x09%s"], cwd=repo_path)
        if log.returncode == 0 and log.stdout.strip():
            parts = log.stdout.strip().split("\t", 2)
            if len(parts) == 3:
                commit, commit_date, commit_message = parts
    return RepoPreparationResult(
        repo_id=repo_id,
        source=source,
        repo_path=repo_path,
        status=status,
        commit=commit,
        commit_date=commit_date,
        commit_message=commit_message,
        error_message=error_message,
    )


def _write_open_source_demo_artifacts(demo_run: OpenSourceDemoRun) -> None:
    (demo_run.output_dir / OPEN_SOURCE_DEMO_RESULTS_FILE).write_text(
        json.dumps(_open_source_demo_payload(demo_run), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown = build_open_source_demo_report_markdown(demo_run)
    (demo_run.output_dir / OPEN_SOURCE_DEMO_REPORT_FILE).write_text(
        markdown,
        encoding="utf-8",
    )
    (demo_run.output_dir / OPEN_SOURCE_DEMO_HTML_FILE).write_text(
        build_open_source_demo_report_html(demo_run),
        encoding="utf-8",
    )


def _open_source_demo_payload(demo_run: OpenSourceDemoRun) -> dict[str, Any]:
    validation = demo_run.validation_run
    summary = _validation_summary(validation)
    return {
        "demo_run_id": demo_run.demo_run_id,
        "manifest_path": str(demo_run.manifest_path),
        "repo_root": str(demo_run.repo_root),
        "output_dir": str(demo_run.output_dir),
        "started_at": demo_run.started_at.isoformat(),
        "completed_at": demo_run.completed_at.isoformat(),
        "passed": demo_run.passed,
        "repo_prep": [
            {
                "repo_id": result.repo_id,
                "source": result.source,
                "repo_path": str(result.repo_path),
                "status": result.status,
                "commit": result.commit,
                "commit_date": result.commit_date,
                "commit_message": result.commit_message,
                "error_message": result.error_message,
            }
            for result in demo_run.repo_results
        ],
        "validation": None
        if validation is None
        else {
            "validation_run_id": validation.validation_run_id,
            "passed": validation.passed,
            "output_dir": str(validation.output_dir),
            "summary": summary,
        },
    }


def _validation_summary(validation: LiveRepoValidationRun | None) -> dict[str, Any]:
    if validation is None:
        return {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "total_tokens": 0,
            "input_tokens": 0,
            "cached_tokens": 0,
            "cache_hit_ratio": 0.0,
        }
    total_tokens = sum(result.total_tokens for result in validation.results)
    input_tokens = sum(result.input_tokens for result in validation.results)
    cached_tokens = sum(result.cached_tokens for result in validation.results)
    return {
        "total": len(validation.results),
        "passed": sum(1 for result in validation.results if result.passed),
        "failed": sum(1 for result in validation.results if not result.passed),
        "total_tokens": total_tokens,
        "input_tokens": input_tokens,
        "cached_tokens": cached_tokens,
        "cache_hit_ratio": (
            round(cached_tokens / input_tokens, 4)
            if input_tokens
            else 0.0
        ),
    }


def _create_demo_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _markdown_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").strip()


def _permit_label(status: str) -> str:
    return status.replace("_", " ").strip() or "unknown"


def _reviewer_decision(status: str) -> dict[str, str]:
    normalized = status.strip().lower()
    if normalized == "approved":
        return {
            "question": "Did this scanner find any configured policy reason to stop agent access?",
            "response": "Approve from this scanner. No configured agent-access risk matched.",
        }
    if normalized == "blocked":
        return {
            "question": (
                "Should unattended agent automation stay blocked until risky CI trust "
                "paths, write permissions, or MCP routes are fixed?"
            ),
            "response": (
                "Block unattended access. Require remediation or an explicit security "
                "exception before approval."
            ),
        }
    return {
        "question": (
            "Can this repo safely run agent or CI automation with the current workflow "
            "secrets, write permissions, and tool access?"
        ),
        "response": (
            "Review before approving. Confirm the access path is trusted and "
            "least-privilege."
        ),
    }


def _reviewer_decision_card(result: LiveRepoValidationResult) -> str:
    decision = _reviewer_decision(result.actual_permit_status)
    permit = _permit_label(result.actual_permit_status)
    return (
        '<section class="decision">'
        f"<h3>{escape(result.repo_id)}</h3>"
        f'<span class="permit">Permit: {escape(permit)}</span>'
        f"<p><strong>Reviewer question:</strong> {escape(decision['question'])}</p>"
        f"<p><strong>Recommended response:</strong> {escape(decision['response'])}</p>"
        "</section>"
    )


def _run_command(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
