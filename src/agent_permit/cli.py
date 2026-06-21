from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import datetime, timezone
from io import StringIO
import json
from pathlib import Path
import sys
from typing import Any, TextIO

from agent_permit import __version__
from agent_permit.artifacts import (
    ARTIFACT_ROOT,
    RUNS_DIR,
    RunArtifactWriter,
    create_run_id,
)
from agent_permit.analytics import (
    ANALYTICS_EVENTS_FILE,
    EVAL_TRENDS_JSON_FILE,
    EVAL_TRENDS_MARKDOWN_FILE,
    RUN_METRICS_FILE,
    analytics_events_path,
    analytics_events_path_for_output,
    append_analytics_event,
    build_analytics_event,
    build_analytics_summary,
    build_live_validation_metrics,
    build_scan_run_metrics,
    eval_trends_dir_for_output,
    event_from_metrics,
    write_run_metrics,
)
from agent_permit.baseline import (
    BASELINE_FILE,
    DIFF_JSON_FILE,
    DIFF_MARKDOWN_FILE,
    build_finding_baseline,
    build_finding_diff_markdown,
    diff_findings,
    load_finding_baseline,
    write_finding_baseline,
    write_finding_diff_artifacts,
)
from agent_permit.capability_graph import CapabilityGraphBuilder
from agent_permit.deep_agent import (
    DEFAULT_DEEP_AGENT_RECURSION_LIMIT,
    invoke_deep_agent_investigator_with_metadata,
)
from agent_permit.demo import (
    DEFAULT_OPEN_SOURCE_DEMO_ROOT,
    OPEN_SOURCE_DEMO_HTML_FILE,
    OPEN_SOURCE_DEMO_REPORT_FILE,
    OPEN_SOURCE_DEMO_RESULTS_FILE,
    run_open_source_demo,
)
from agent_permit.db import (
    load_ingest_records,
    optional_store_from_env,
    store_from_env,
)
from agent_permit.events import DatabaseEventSink, EventPublisher, JsonlEventSink
from agent_permit.evidence_context import EvidenceContext
from agent_permit.evals import (
    DEFAULT_PHOENIX_BASE_URL,
    DEFAULT_PHOENIX_DATASET_NAME,
    EVAL_REPORT_FILE,
    EVAL_RESULTS_FILE,
    LIVE_REPO_VALIDATION_REPORT_FILE,
    LIVE_REPO_VALIDATION_RESULTS_FILE,
    PHOENIX_DATASET_ROWS_FILE,
    REAL_REPO_EVAL_REPORT_FILE,
    REAL_REPO_EVAL_RESULTS_FILE,
    run_fixture_eval_suite,
    run_live_repo_validation_suite,
    run_real_repo_eval_suite,
    upload_phoenix_dataset_rows,
)
from agent_permit.investigation import (
    build_investigation_markdown,
    critique_investigation_report,
)
from agent_permit.model_provider import OPENROUTER_DEFAULT_MODEL
from agent_permit.models import ScanRunStatus
from agent_permit.path_finder import CapabilityPathFinder
from agent_permit.permit_engine import PermitEngine
from agent_permit.policy import (
    DEFAULT_POLICY_FILE,
    POLICY_EVALUATION_FILE,
    apply_policy,
    apply_policy_to_graph_paths,
    load_policy,
    write_policy_evaluation,
)
from agent_permit.reporting import build_summary_markdown
from agent_permit.rule_registry import RULE_DEFINITIONS
from agent_permit.sarif import (
    DEFAULT_SARIF_CATEGORY,
    SARIF_FILE,
    write_sarif_file,
)
from agent_permit.scanners.ci_workflows import CiWorkflowScanner
from agent_permit.scanners.credential_refs import CredentialReferenceScanner
from agent_permit.scanners.file_inventory import FileInventoryScanner
from agent_permit.scanners.mcp_config import McpConfigScanner
from agent_permit.scanners.prompt_instructions import PromptInstructionScanner


DEFAULT_DEEP_AGENT_MODEL = f"openrouter:{OPENROUTER_DEFAULT_MODEL}"
LIVE_VALIDATION_FILE = "live-validation.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-permit",
        description=(
            "Issue evidence-backed permits before AI agents receive tools, "
            "credentials, memory, or production access."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command")

    scan_parser = subparsers.add_parser(
        "scan",
        help="create a local permit scan run for a repo path",
    )
    scan_parser.add_argument("path", type=Path, help="repo path to scan")
    scan_parser.add_argument(
        "--run-id",
        help="explicit run ID for deterministic tests or replay",
    )
    scan_parser.add_argument(
        "--ci",
        action="store_true",
        help="exit non-zero when permit status requires review or is blocked",
    )
    scan_parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help=(
            "gitignore-style pattern to skip during inventory; repeat for "
            "multiple patterns"
        ),
    )
    scan_parser.add_argument(
        "--sarif",
        action="store_true",
        help=f"write {SARIF_FILE} in the scan artifact directory",
    )
    scan_parser.add_argument(
        "--sarif-category",
        default=DEFAULT_SARIF_CATEGORY,
        help=f"SARIF automation category; default {DEFAULT_SARIF_CATEGORY}",
    )
    scan_parser.add_argument(
        "--baseline",
        type=Path,
        help="finding baseline JSON to compare against during scan",
    )
    scan_parser.add_argument(
        "--ci-new-findings-only",
        action="store_true",
        help=(
            "with --ci and --baseline, exit non-zero only when the scan "
            "introduces new baseline diff findings"
        ),
    )
    scan_parser.add_argument(
        "--policy",
        type=Path,
        help=(
            f"policy JSON path; defaults to {DEFAULT_POLICY_FILE} when present "
            "in the scanned repo"
        ),
    )
    investigate_parser = subparsers.add_parser(
        "investigate",
        help="write a cited investigation report from existing scan artifacts",
    )
    investigate_parser.add_argument(
        "artifact_dir",
        type=Path,
        help=".agent-permit/runs/<run_id> artifact directory",
    )
    investigate_parser.add_argument(
        "--output",
        type=Path,
        help="report output path; defaults to artifact_dir/agent-investigation.md",
    )
    investigate_parser.add_argument(
        "--model",
        help=(
            "Deep Agents model string; defaults to "
            f"{DEFAULT_DEEP_AGENT_MODEL}"
        ),
    )
    investigate_parser.add_argument(
        "--deterministic-only",
        action="store_true",
        help=(
            "write the offline deterministic citation report without invoking "
            "the required live Deep Agent path"
        ),
    )
    investigate_parser.add_argument(
        "--agent-recursion-limit",
        type=int,
        default=DEFAULT_DEEP_AGENT_RECURSION_LIMIT,
        help=(
            "max LangGraph recursion steps for live Deep Agent runs; default "
            f"{DEFAULT_DEEP_AGENT_RECURSION_LIMIT}"
        ),
    )
    investigate_parser.add_argument(
        "--langsmith",
        action="store_true",
        help="enable LangSmith tracing for a live Deep Agent run",
    )
    investigate_parser.add_argument(
        "--phoenix",
        action="store_true",
        help="enable Phoenix/OpenTelemetry tracing for a live Deep Agent run",
    )
    live_validate_parser = subparsers.add_parser(
        "live-validate",
        help="scan a repo and run the live Deep Agent validation harness",
    )
    live_validate_parser.add_argument("path", type=Path, help="repo path to validate")
    live_validate_parser.add_argument(
        "--run-id",
        help="explicit run ID for repeatable live validation",
    )
    live_validate_parser.add_argument(
        "--model",
        help=(
            "Deep Agents model string; defaults to "
            f"{DEFAULT_DEEP_AGENT_MODEL}"
        ),
    )
    live_validate_parser.add_argument(
        "--agent-recursion-limit",
        type=int,
        default=DEFAULT_DEEP_AGENT_RECURSION_LIMIT,
        help=(
            "max LangGraph recursion steps for live Deep Agent runs; default "
            f"{DEFAULT_DEEP_AGENT_RECURSION_LIMIT}"
        ),
    )
    live_validate_parser.add_argument(
        "--phoenix",
        action="store_true",
        help="enable Phoenix/OpenTelemetry tracing for the live investigation",
    )
    live_validate_parser.add_argument(
        "--langsmith",
        action="store_true",
        help="enable LangSmith tracing for the live investigation",
    )
    live_validate_parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help=(
            "gitignore-style pattern to skip during inventory; repeat for "
            "multiple patterns"
        ),
    )
    live_validate_parser.add_argument(
        "--policy",
        type=Path,
        help=(
            f"policy JSON path; defaults to {DEFAULT_POLICY_FILE} when present "
            "in the validated repo"
        ),
    )
    live_validate_parser.add_argument(
        "--output",
        type=Path,
        help=(
            "live validation JSON output path; defaults to "
            f"artifact_dir/{LIVE_VALIDATION_FILE}"
        ),
    )
    eval_parser = subparsers.add_parser(
        "eval",
        help="run deterministic fixture evals and write local eval artifacts",
    )
    eval_parser.add_argument(
        "fixture_root",
        nargs="?",
        type=Path,
        default=Path("tests/fixtures"),
        help="fixture root containing */fixture.json manifests",
    )
    eval_parser.add_argument(
        "--run-id",
        help="explicit eval run ID for deterministic tests or replay",
    )
    eval_parser.add_argument(
        "--output",
        type=Path,
        help="output directory; defaults to .agent-permit/evals/<run_id>",
    )
    eval_parser.add_argument(
        "--upload-phoenix",
        action="store_true",
        help="upload eval rows to a running Phoenix dataset server",
    )
    eval_parser.add_argument(
        "--phoenix-base-url",
        help=(
            "Phoenix base URL for dataset upload; default PHOENIX_BASE_URL "
            f"or {DEFAULT_PHOENIX_BASE_URL}"
        ),
    )
    eval_parser.add_argument(
        "--phoenix-dataset-name",
        default=DEFAULT_PHOENIX_DATASET_NAME,
        help=(
            "Phoenix dataset name for upload; default "
            f"{DEFAULT_PHOENIX_DATASET_NAME}"
        ),
    )
    real_eval_parser = subparsers.add_parser(
        "eval-real",
        help="run deterministic evals against local real-repo checkouts",
    )
    real_eval_parser.add_argument(
        "manifest",
        type=Path,
        help="JSON manifest with repo paths and expected scanner outcomes",
    )
    real_eval_parser.add_argument(
        "--repo-root",
        type=Path,
        help="base directory used to resolve relative manifest local_path values",
    )
    real_eval_parser.add_argument(
        "--run-id",
        help="explicit eval run ID for deterministic tests or replay",
    )
    real_eval_parser.add_argument(
        "--output",
        type=Path,
        help="output directory; defaults to .agent-permit/real-repo-evals/<run_id>",
    )
    real_eval_parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help=(
            "gitignore-style pattern to skip during inventory; repeat for "
            "multiple patterns"
        ),
    )
    live_real_parser = subparsers.add_parser(
        "live-validate-real",
        help="run live validation against local real-repo checkouts from a manifest",
    )
    live_real_parser.add_argument(
        "manifest",
        type=Path,
        help="JSON manifest with repo paths and live validation expectations",
    )
    live_real_parser.add_argument(
        "--repo-root",
        type=Path,
        help="base directory used to resolve relative manifest local_path values",
    )
    live_real_parser.add_argument(
        "--run-id",
        help="explicit validation run ID for repeatable live validation",
    )
    live_real_parser.add_argument(
        "--output",
        type=Path,
        help=(
            "output directory; defaults to "
            ".agent-permit/live-repo-validations/<run_id>"
        ),
    )
    live_real_parser.add_argument(
        "--model",
        help=(
            "Deep Agents model string; defaults to "
            f"{DEFAULT_DEEP_AGENT_MODEL}"
        ),
    )
    live_real_parser.add_argument(
        "--agent-recursion-limit",
        type=int,
        default=DEFAULT_DEEP_AGENT_RECURSION_LIMIT,
        help=(
            "max LangGraph recursion steps for live Deep Agent runs; default "
            f"{DEFAULT_DEEP_AGENT_RECURSION_LIMIT}"
        ),
    )
    live_real_parser.add_argument(
        "--phoenix",
        action="store_true",
        help="enable Phoenix/OpenTelemetry tracing for each live investigation",
    )
    live_real_parser.add_argument(
        "--langsmith",
        action="store_true",
        help="enable LangSmith tracing for each live investigation",
    )
    live_real_parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help=(
            "gitignore-style pattern to skip during inventory; repeat for "
            "multiple patterns"
        ),
    )
    analytics_parser = subparsers.add_parser(
        "analytics",
        help="inspect local analytics event artifacts",
    )
    analytics_subparsers = analytics_parser.add_subparsers(dest="analytics_command")
    analytics_summary_parser = analytics_subparsers.add_parser(
        "summarize",
        help="summarize a local analytics-events.jsonl stream",
    )
    analytics_summary_parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=Path("."),
        help=(
            "repo path containing .agent-permit/analytics-events.jsonl, "
            "or an analytics-events.jsonl file"
        ),
    )
    db_parser = subparsers.add_parser(
        "db",
        help="manage optional local Postgres runtime state",
    )
    db_subparsers = db_parser.add_subparsers(dest="db_command")
    db_subparsers.add_parser(
        "migrate",
        help="apply local runtime schema to DATABASE_URL",
    )
    ingest_parser = subparsers.add_parser(
        "ingest",
        help="load existing .agent-permit/runs/<run_id> artifacts into Postgres",
    )
    ingest_parser.add_argument(
        "artifact_dir",
        type=Path,
        help=".agent-permit/runs/<run_id> artifact directory",
    )
    ingest_parser.add_argument(
        "--repo-label",
        help="repository label to store; defaults to scanned directory name",
    )
    ingest_parser.add_argument(
        "--local-path",
        type=Path,
        help="repository path to store; defaults to scan metadata target path",
    )
    ingest_parser.add_argument(
        "--branch",
        help="branch name to store with the repository record",
    )
    runner_parser = subparsers.add_parser(
        "runner",
        help="claim queued scan jobs from DATABASE_URL and run them locally",
    )
    runner_parser.add_argument(
        "--once",
        action="store_true",
        help="claim at most one queued job and exit",
    )
    open_source_demo_parser = subparsers.add_parser(
        "open-source-demo",
        help="prepare recent open-source repos and run the live validation demo",
    )
    open_source_demo_parser.add_argument(
        "manifest",
        type=Path,
        help="JSON manifest with source URLs, local paths, and expectations",
    )
    open_source_demo_parser.add_argument(
        "--repo-root",
        type=Path,
        default=DEFAULT_OPEN_SOURCE_DEMO_ROOT,
        help=f"clone/refresh root; default {DEFAULT_OPEN_SOURCE_DEMO_ROOT}",
    )
    open_source_demo_parser.add_argument(
        "--run-id",
        help="explicit demo run ID for repeatable output paths",
    )
    open_source_demo_parser.add_argument(
        "--output",
        type=Path,
        help="output directory; defaults to .agent-permit/open-source-demos/<run_id>",
    )
    open_source_demo_parser.add_argument(
        "--skip-refresh",
        action="store_true",
        help="do not pull existing local checkouts before validation",
    )
    open_source_demo_parser.add_argument(
        "--skip-live",
        action="store_true",
        help="prepare/refresh repos and write demo report without live LLM validation",
    )
    open_source_demo_parser.add_argument(
        "--model",
        help=(
            "Deep Agents model string; defaults to "
            f"{DEFAULT_DEEP_AGENT_MODEL}"
        ),
    )
    open_source_demo_parser.add_argument(
        "--agent-recursion-limit",
        type=int,
        default=DEFAULT_DEEP_AGENT_RECURSION_LIMIT,
        help=(
            "max LangGraph recursion steps for live Deep Agent runs; default "
            f"{DEFAULT_DEEP_AGENT_RECURSION_LIMIT}"
        ),
    )
    open_source_demo_parser.add_argument(
        "--phoenix",
        action="store_true",
        help="enable Phoenix/OpenTelemetry tracing for each live investigation",
    )
    open_source_demo_parser.add_argument(
        "--langsmith",
        action="store_true",
        help="enable LangSmith tracing for each live investigation",
    )
    open_source_demo_parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help=(
            "gitignore-style pattern to skip during inventory; repeat for "
            "multiple patterns"
        ),
    )
    rules_parser = subparsers.add_parser(
        "rules",
        help="list deterministic scanner rules",
    )
    rules_parser.add_argument(
        "--scanner",
        help="filter rules by scanner name, for example ci_workflows",
    )
    baseline_parser = subparsers.add_parser(
        "baseline",
        help="write a finding baseline from existing scan artifacts",
    )
    baseline_parser.add_argument(
        "artifact_dir",
        type=Path,
        help=".agent-permit/runs/<run_id> artifact directory",
    )
    baseline_parser.add_argument(
        "--output",
        type=Path,
        help=f"baseline output path; defaults to artifact_dir/{BASELINE_FILE}",
    )
    diff_parser = subparsers.add_parser(
        "diff",
        help="compare existing scan artifacts against a finding baseline",
    )
    diff_parser.add_argument(
        "artifact_dir",
        type=Path,
        help=".agent-permit/runs/<run_id> artifact directory",
    )
    diff_parser.add_argument(
        "--baseline",
        required=True,
        type=Path,
        help="finding baseline JSON to compare against",
    )
    diff_parser.add_argument(
        "--output-dir",
        type=Path,
        help=(
            f"diff output directory; defaults to artifact_dir with "
            f"{DIFF_JSON_FILE} and {DIFF_MARKDOWN_FILE}"
        ),
    )
    sarif_parser = subparsers.add_parser(
        "sarif",
        help="write SARIF output from existing scan artifacts",
    )
    sarif_parser.add_argument(
        "artifact_dir",
        type=Path,
        help=".agent-permit/runs/<run_id> artifact directory",
    )
    sarif_parser.add_argument(
        "--output",
        type=Path,
        help=f"SARIF output path; defaults to artifact_dir/{SARIF_FILE}",
    )
    sarif_parser.add_argument(
        "--category",
        default=DEFAULT_SARIF_CATEGORY,
        help=f"SARIF automation category; default {DEFAULT_SARIF_CATEGORY}",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "scan":
        return run_scan(
            args.path,
            args.run_id,
            ci=args.ci,
            exclude_patterns=args.exclude,
            write_sarif=args.sarif,
            sarif_category=args.sarif_category,
            baseline_path=args.baseline,
            ci_new_findings_only=args.ci_new_findings_only,
            policy_path=args.policy,
            stdout=stdout,
            stderr=stderr,
        )
    if args.command == "investigate":
        return run_investigate(
            args.artifact_dir,
            output_path=args.output,
            model=args.model,
            deterministic_only=args.deterministic_only,
            agent_recursion_limit=args.agent_recursion_limit,
            enable_langsmith=args.langsmith,
            enable_phoenix=args.phoenix,
            stdout=stdout,
            stderr=stderr,
        )
    if args.command == "live-validate":
        return run_live_validate(
            args.path,
            run_id=args.run_id,
            model=args.model,
            agent_recursion_limit=args.agent_recursion_limit,
            enable_phoenix=args.phoenix,
            enable_langsmith=args.langsmith,
            exclude_patterns=args.exclude,
            policy_path=args.policy,
            output_path=args.output,
            stdout=stdout,
            stderr=stderr,
        )
    if args.command == "eval":
        return run_eval(
            args.fixture_root,
            eval_run_id=args.run_id,
            output_dir=args.output,
            upload_phoenix=args.upload_phoenix,
            phoenix_base_url=args.phoenix_base_url,
            phoenix_dataset_name=args.phoenix_dataset_name,
            stdout=stdout,
            stderr=stderr,
        )
    if args.command == "eval-real":
        return run_real_eval(
            args.manifest,
            repo_root=args.repo_root,
            eval_run_id=args.run_id,
            output_dir=args.output,
            exclude_patterns=args.exclude,
            stdout=stdout,
            stderr=stderr,
        )
    if args.command == "live-validate-real":
        return run_live_validate_real(
            args.manifest,
            repo_root=args.repo_root,
            validation_run_id=args.run_id,
            output_dir=args.output,
            model=args.model,
            agent_recursion_limit=args.agent_recursion_limit,
            enable_phoenix=args.phoenix,
            enable_langsmith=args.langsmith,
            exclude_patterns=args.exclude,
            stdout=stdout,
            stderr=stderr,
        )
    if args.command == "open-source-demo":
        return run_open_source_demo_cli(
            args.manifest,
            repo_root=args.repo_root,
            demo_run_id=args.run_id,
            output_dir=args.output,
            refresh_repos=not args.skip_refresh,
            run_live_validation=not args.skip_live,
            model=args.model,
            agent_recursion_limit=args.agent_recursion_limit,
            enable_phoenix=args.phoenix,
            enable_langsmith=args.langsmith,
            exclude_patterns=args.exclude,
            stdout=stdout,
            stderr=stderr,
        )
    if args.command == "rules":
        return run_rules(args.scanner, stdout=stdout)
    if args.command == "analytics":
        if args.analytics_command == "summarize":
            return run_analytics_summarize(args.path, stdout=stdout, stderr=stderr)
        parser.print_help(file=stdout)
        return 0
    if args.command == "db":
        if args.db_command == "migrate":
            return run_db_migrate(stdout=stdout, stderr=stderr)
        parser.print_help(file=stdout)
        return 0
    if args.command == "ingest":
        return run_ingest(
            args.artifact_dir,
            repository_label=args.repo_label,
            local_path=args.local_path,
            branch=args.branch,
            stdout=stdout,
            stderr=stderr,
        )
    if args.command == "runner":
        return run_runner(once=args.once, stdout=stdout, stderr=stderr)
    if args.command == "baseline":
        return run_baseline(
            args.artifact_dir,
            output_path=args.output,
            stdout=stdout,
            stderr=stderr,
        )
    if args.command == "diff":
        return run_diff(
            args.artifact_dir,
            baseline_path=args.baseline,
            output_dir=args.output_dir,
            stdout=stdout,
            stderr=stderr,
        )
    if args.command == "sarif":
        return run_sarif(
            args.artifact_dir,
            output_path=args.output,
            category=args.category,
            stdout=stdout,
            stderr=stderr,
        )

    parser.print_help(file=stdout)
    return 0


def run_scan(
    target_path: Path,
    run_id: str | None = None,
    *,
    ci: bool = False,
    exclude_patterns: Sequence[str] | None = None,
    write_sarif: bool = False,
    sarif_category: str = DEFAULT_SARIF_CATEGORY,
    baseline_path: Path | None = None,
    ci_new_findings_only: bool = False,
    policy_path: Path | None = None,
    db_job_id: str | None = None,
    db_repository_label: str | None = None,
    db_local_path: Path | None = None,
    db_branch: str | None = None,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    if not target_path.exists():
        print(f"error: target path does not exist: {target_path}", file=stderr)
        return 2
    if not target_path.is_dir():
        print(f"error: target path must be a directory: {target_path}", file=stderr)
        return 2
    if ci_new_findings_only and baseline_path is None:
        print("error: --ci-new-findings-only requires --baseline", file=stderr)
        return 2

    baseline = None
    if baseline_path is not None:
        try:
            baseline = load_finding_baseline(baseline_path)
        except (FileNotFoundError, ValueError, PermissionError) as exc:
            print(f"error: failed to load baseline: {exc}", file=stderr)
            return 2
    try:
        policy, resolved_policy_path = load_policy(target_path, policy_path)
    except (FileNotFoundError, ValueError, PermissionError) as exc:
        print(f"error: failed to load policy: {exc}", file=stderr)
        return 2

    event_publisher: EventPublisher | None = None
    scan_run_id: str | None = None
    try:
        finding_diff = None
        policy_evaluation = None
        sarif_path = None
        artifact_writer = RunArtifactWriter()
        scan_run = artifact_writer.create_run(
            target_path,
            run_id=run_id,
            scan_options={
                "mode": "deterministic-scanners",
                "exclude_patterns": list(exclude_patterns or []),
                "policy_path": str(resolved_policy_path) if resolved_policy_path else None,
            },
        )
        scan_run_id = scan_run.id
        event_path = analytics_events_path(target_path)
        db_store = optional_store_from_env()
        event_sinks = [JsonlEventSink(event_path)]
        if db_store is not None:
            event_sinks.append(
                DatabaseEventSink(
                    db_store,
                    scan_run_id=scan_run.id,
                    job_id=db_job_id,
                )
            )
        event_publisher = EventPublisher(event_sinks)

        def publish_scan_phase(
            event_name: str,
            *,
            status: str = "completed",
            payload: dict[str, Any] | None = None,
        ) -> None:
            event_publisher.publish(
                build_analytics_event(
                    event_name,
                    run_id=scan_run.id,
                    run_type="scan",
                    status=status,
                    payload=payload,
                )
            )

        event_publisher.publish(
            build_analytics_event(
                "scan_started",
                run_id=scan_run.id,
                run_type="scan",
                status="started",
            ),
        )
        inventory = FileInventoryScanner(
            exclude_patterns=exclude_patterns,
        ).scan(target_path, scan_run_id=scan_run.id)
        artifact_writer.write_file_inventory(scan_run, inventory)
        publish_scan_phase(
            "inventory_indexed",
            payload={
                "files_indexed": len(inventory.files),
                "high_signal_files": sum(
                    1 for entry in inventory.files if entry.high_signal
                ),
                "skipped_files": sum(inventory.skipped.values()),
            },
        )
        mcp_result = McpConfigScanner().scan(
            target_path,
            scan_run_id=scan_run.id,
            inventory=inventory,
        )
        publish_scan_phase(
            "mcp_scanned",
            payload={"mcp_servers": len(mcp_result.agent_bom.mcp_servers)},
        )
        credential_refs = CredentialReferenceScanner().scan(
            target_path,
            scan_run_id=scan_run.id,
            inventory=inventory,
        )
        mcp_result.agent_bom.credential_refs.extend(credential_refs)
        publish_scan_phase(
            "credentials_scanned",
            payload={"credential_refs": len(credential_refs)},
        )
        prompt_findings = PromptInstructionScanner().scan(
            target_path,
            scan_run_id=scan_run.id,
            inventory=inventory,
        )
        publish_scan_phase(
            "prompts_scanned",
            payload={"findings": len(prompt_findings)},
        )
        ci_findings = CiWorkflowScanner().scan(
            target_path,
            scan_run_id=scan_run.id,
            inventory=inventory,
        )
        publish_scan_phase(
            "ci_scanned",
            payload={"findings": len(ci_findings)},
        )
        findings = [*mcp_result.findings, *prompt_findings, *ci_findings]
        if policy is not None and resolved_policy_path is not None:
            findings, policy_evaluation = apply_policy(
                findings,
                policy=policy,
                policy_path=resolved_policy_path,
                scan_run_id=scan_run.id,
            )
        graph_result = CapabilityGraphBuilder().build(
            scan_run_id=scan_run.id,
            inventory=inventory,
            agent_bom=mcp_result.agent_bom,
            findings=findings,
        )
        graph_path_report = CapabilityPathFinder().find_paths(
            graph_result.codebase_map,
        )
        if policy is not None:
            graph_path_report = apply_policy_to_graph_paths(
                graph_path_report,
                policy=policy,
            )
        publish_scan_phase(
            "capability_graph_built",
            payload={
                "graph_nodes": len(graph_result.codebase_map.nodes),
                "graph_edges": len(graph_result.codebase_map.edges),
                "graph_paths": len(graph_path_report.paths),
            },
        )
        permit_evaluation = PermitEngine().evaluate(
            scan_run_id=scan_run.id,
            artifact_dir=scan_run.artifact_dir,
            agent_bom=mcp_result.agent_bom,
            findings=graph_result.findings,
            graph_paths=graph_path_report,
        )
        if baseline is not None and baseline_path is not None:
            finding_diff = diff_findings(
                baseline=baseline,
                current_findings=graph_result.findings,
                scan_run_id=scan_run.id,
                baseline_path=baseline_path,
            )
        summary_markdown = build_summary_markdown(
            permit=permit_evaluation.permit,
            findings=graph_result.findings,
            graph_paths=graph_path_report,
            controls=permit_evaluation.controls,
        )
        if finding_diff is not None:
            summary_markdown += "\n" + build_finding_diff_markdown(
                finding_diff,
                heading_level=2,
            )
        artifact_writer.write_agent_bom(scan_run, mcp_result.agent_bom)
        artifact_writer.write_codebase_map(scan_run, graph_result.codebase_map)
        artifact_writer.write_graph_paths(scan_run, graph_path_report)
        artifact_writer.write_raw_findings(scan_run, graph_result.findings)
        artifact_writer.write_controls(scan_run, permit_evaluation.controls)
        artifact_writer.write_permit(scan_run, permit_evaluation.permit)
        artifact_writer.write_summary(scan_run, summary_markdown)
        artifact_writer.write_risk_report(
            scan_run,
            permit_evaluation.risk_report_markdown,
        )
        if policy_evaluation is not None:
            write_policy_evaluation(policy_evaluation, scan_run.artifact_dir)
        if finding_diff is not None:
            write_finding_diff_artifacts(
                finding_diff,
                scan_run.artifact_dir,
            )
        if write_sarif:
            sarif_path = write_sarif_file(
                EvidenceContext.load(scan_run.artifact_dir),
                category=sarif_category,
            )
        scan_run.status = ScanRunStatus.COMPLETED
        scan_run.completed_at = datetime.now(timezone.utc)
        artifact_writer.write_scan_run(scan_run)
        run_metrics = build_scan_run_metrics(
            scan_run=scan_run,
            target_path=target_path,
            inventory=inventory,
            agent_bom=mcp_result.agent_bom,
            codebase_map=graph_result.codebase_map,
            findings=graph_result.findings,
            graph_paths=graph_path_report,
            controls=permit_evaluation.controls,
            permit=permit_evaluation.permit,
        )
        write_run_metrics(
            scan_run.artifact_dir / RUN_METRICS_FILE,
            run_metrics,
        )
        event_publisher.publish(
            event_from_metrics(
                "permit_decided",
                run_metrics,
                payload={"permit_status": run_metrics.permit_status},
            ),
        )
        event_publisher.publish(event_from_metrics("scan_completed", run_metrics))
        if db_store is not None:
            db_store.write_ingest_records(
                load_ingest_records(
                    scan_run.artifact_dir,
                    repository_label=db_repository_label,
                    local_path=db_local_path,
                    branch=db_branch,
                    job_id=db_job_id,
                )
            )
    except (OSError, RuntimeError, ValueError) as exc:
        if event_publisher is not None and scan_run_id is not None:
            try:
                event_publisher.publish(
                    build_analytics_event(
                        "scan_failed",
                        run_id=scan_run_id,
                        run_type="scan",
                        status="failed",
                        payload={"error_type": type(exc).__name__},
                    )
                )
            except (OSError, RuntimeError, ValueError):
                pass
        print(f"error: failed to create scan state: {exc}", file=stderr)
        return 1

    print("Agent Permit Office", file=stdout)
    print("Status: scan_complete", file=stdout)
    print(f"Target: {scan_run.target_path}", file=stdout)
    print(f"Run ID: {scan_run.id}", file=stdout)
    print(f"Artifacts: {scan_run.artifact_dir}", file=stdout)
    print(f"Files indexed: {len(inventory.files)}", file=stdout)
    print(
        f"High signal files: {sum(1 for entry in inventory.files if entry.high_signal)}",
        file=stdout,
    )
    print(f"Skipped files/dirs: {sum(inventory.skipped.values())}", file=stdout)
    print(f"MCP servers: {len(mcp_result.agent_bom.mcp_servers)}", file=stdout)
    print(
        f"Credential refs: {len(mcp_result.agent_bom.credential_refs)}",
        file=stdout,
    )
    print(f"Prompt findings: {len(prompt_findings)}", file=stdout)
    print(f"CI findings: {len(ci_findings)}", file=stdout)
    print(f"Findings: {len(graph_result.findings)}", file=stdout)
    print(f"Graph nodes: {len(graph_result.codebase_map.nodes)}", file=stdout)
    print(f"Graph edges: {len(graph_result.codebase_map.edges)}", file=stdout)
    print(f"Graph paths: {len(graph_path_report.paths)}", file=stdout)
    print(f"Controls: {len(permit_evaluation.controls.controls)}", file=stdout)
    print(f"Permit status: {permit_evaluation.permit.status}", file=stdout)
    print(f"Summary: {scan_run.artifact_dir / 'summary.md'}", file=stdout)
    print(f"Metrics: {scan_run.artifact_dir / RUN_METRICS_FILE}", file=stdout)
    print(f"Events: {analytics_events_path(target_path)}", file=stdout)
    if policy_evaluation is not None:
        print(f"Policy: {resolved_policy_path}", file=stdout)
        print(f"Policy adjustments: {len(policy_evaluation.adjustments)}", file=stdout)
        print(
            f"Policy evaluation: {scan_run.artifact_dir / POLICY_EVALUATION_FILE}",
            file=stdout,
        )
    if finding_diff is not None:
        print(f"Baseline: {baseline_path}", file=stdout)
        print(f"New findings: {len(finding_diff.new_findings)}", file=stdout)
        print(f"Resolved findings: {len(finding_diff.resolved_findings)}", file=stdout)
        print(f"Unchanged findings: {len(finding_diff.unchanged_findings)}", file=stdout)
        print(f"Diff: {scan_run.artifact_dir / DIFF_JSON_FILE}", file=stdout)
    if sarif_path is not None:
        print(f"SARIF: {sarif_path}", file=stdout)
    if ci:
        print("CI mode: on", file=stdout)
    print("Next: review summary.md and risk-report.md", file=stdout)
    if ci and ci_new_findings_only:
        return 1 if finding_diff is not None and finding_diff.new_findings else 0
    if ci and permit_evaluation.permit.status in {"blocked", "needs_review"}:
        return 1
    return 0


def run_investigate(
    artifact_dir: Path,
    *,
    output_path: Path | None = None,
    model: str | None = None,
    deterministic_only: bool = False,
    agent_recursion_limit: int = DEFAULT_DEEP_AGENT_RECURSION_LIMIT,
    enable_langsmith: bool = False,
    enable_phoenix: bool = False,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    try:
        context = EvidenceContext.load(artifact_dir)
    except (FileNotFoundError, PermissionError, ValueError) as exc:
        print(f"error: failed to load scan artifacts: {exc}", file=stderr)
        return 2

    if deterministic_only and model:
        print(
            "error: --model cannot be used with --deterministic-only",
            file=stderr,
        )
        return 2
    selected_model = None if deterministic_only else (model or DEFAULT_DEEP_AGENT_MODEL)

    try:
        if selected_model:
            investigation_result = invoke_deep_agent_investigator_with_metadata(
                context,
                model=selected_model,
                enable_langsmith=enable_langsmith,
                enable_phoenix=enable_phoenix,
                recursion_limit=agent_recursion_limit,
            )
            report_markdown = investigation_result.report_markdown
            usage_summary = investigation_result.usage_summary
        else:
            report_markdown = build_investigation_markdown(context)
            usage_summary = None
    except RuntimeError as exc:
        print(f"error: {exc}", file=stderr)
        return 2
    except Exception as exc:
        print(f"error: Deep Agent investigation failed: {exc}", file=stderr)
        return 1

    critic_result = critique_investigation_report(context, report_markdown)
    output_path = output_path or (context.artifact_dir / "agent-investigation.md")
    try:
        output_path.write_text(report_markdown, encoding="utf-8")
        usage_path = None
        if usage_summary is not None:
            usage_path = context.artifact_dir / "openrouter-usage.json"
            usage_path.write_text(
                json.dumps(usage_summary, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
    except OSError as exc:
        print(f"error: failed to write investigation artifacts: {exc}", file=stderr)
        return 1

    print("Agent Permit Office", file=stdout)
    print("Status: investigation_complete", file=stdout)
    print(f"Artifacts: {context.artifact_dir}", file=stdout)
    print(f"Report: {output_path}", file=stdout)
    print(f"Permit status: {context.permit_status}", file=stdout)
    print(f"Findings: {len(context.findings)}", file=stdout)
    print(f"Citation check: {'passed' if critic_result.supported else 'failed'}", file=stdout)
    if selected_model:
        print(f"Deep Agent model: {selected_model}", file=stdout)
        print(f"Deep Agent recursion limit: {agent_recursion_limit}", file=stdout)
    if usage_summary is not None and usage_path is not None:
        print(f"OpenRouter usage: {usage_path}", file=stdout)
        print(
            "OpenRouter cached tokens: "
            f"{usage_summary.get('cached_tokens', 0)}",
            file=stdout,
        )
    if enable_langsmith:
        print("LangSmith tracing: requested", file=stdout)
    if enable_phoenix and selected_model:
        print("Phoenix tracing: requested", file=stdout)
    elif enable_phoenix:
        print("Phoenix tracing: skipped in deterministic mode", file=stdout)
    if not critic_result.supported:
        for citation in critic_result.unsupported_citations:
            print(f"Unsupported citation: {citation}", file=stderr)
        for rule_id in critic_result.unsupported_rule_ids:
            print(f"Unsupported rule id: {rule_id}", file=stderr)
        for rule_id in critic_result.missing_citation_rule_ids:
            print(f"Missing rule citation: {rule_id}", file=stderr)
        for mismatch in critic_result.aggregate_mismatches:
            print(f"Aggregate mismatch: {mismatch}", file=stderr)
        return 1
    return 0


def run_live_validate(
    target_path: Path,
    *,
    run_id: str | None = None,
    model: str | None = None,
    agent_recursion_limit: int = DEFAULT_DEEP_AGENT_RECURSION_LIMIT,
    enable_phoenix: bool = False,
    enable_langsmith: bool = False,
    exclude_patterns: Sequence[str] | None = None,
    policy_path: Path | None = None,
    output_path: Path | None = None,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    validation_started_at = datetime.now(timezone.utc)
    selected_model = model or DEFAULT_DEEP_AGENT_MODEL
    validation_run_id = run_id or create_run_id(target_path)
    artifact_dir = (
        target_path.resolve()
        / ARTIFACT_ROOT
        / RUNS_DIR
        / validation_run_id
    )

    scan_stdout = StringIO()
    scan_stderr = StringIO()
    scan_exit_code = run_scan(
        target_path,
        validation_run_id,
        ci=False,
        exclude_patterns=exclude_patterns,
        policy_path=policy_path,
        stdout=scan_stdout,
        stderr=scan_stderr,
    )
    if scan_exit_code != 0:
        _write_prefixed_output(scan_stdout.getvalue(), stdout)
        _write_prefixed_output(scan_stderr.getvalue(), stderr)
        return scan_exit_code

    investigation_stdout = StringIO()
    investigation_stderr = StringIO()
    investigation_exit_code = run_investigate(
        artifact_dir,
        output_path=None,
        model=selected_model,
        deterministic_only=False,
        agent_recursion_limit=agent_recursion_limit,
        enable_langsmith=enable_langsmith,
        enable_phoenix=enable_phoenix,
        stdout=investigation_stdout,
        stderr=investigation_stderr,
    )

    try:
        context = EvidenceContext.load(artifact_dir)
    except (FileNotFoundError, PermissionError, ValueError) as exc:
        _write_prefixed_output(investigation_stderr.getvalue(), stderr)
        print(f"error: failed to load validation artifacts: {exc}", file=stderr)
        return 1

    report_path = artifact_dir / "agent-investigation.md"
    usage_path = artifact_dir / "openrouter-usage.json"
    validation_path = output_path or (artifact_dir / LIVE_VALIDATION_FILE)
    citation_check: dict[str, Any] = {
        "supported": False,
        "unsupported_citations": [],
        "unsupported_rule_ids": [],
        "missing_citation_rule_ids": [],
        "aggregate_mismatches": [],
        "status": "not_run",
    }
    if report_path.is_file():
        critic_result = critique_investigation_report(
            context,
            report_path.read_text(encoding="utf-8"),
        )
        citation_check = {
            "supported": critic_result.supported,
            "unsupported_citations": list(critic_result.unsupported_citations),
            "unsupported_rule_ids": list(critic_result.unsupported_rule_ids),
            "missing_citation_rule_ids": list(
                critic_result.missing_citation_rule_ids
            ),
            "aggregate_mismatches": list(critic_result.aggregate_mismatches),
            "status": "passed" if critic_result.supported else "failed",
        }

    summary = context.summary()
    passed = investigation_exit_code == 0 and citation_check["supported"] is True
    usage_summary = _read_json_file_if_exists(usage_path)
    validation_completed_at = datetime.now(timezone.utc)
    validation_payload = {
        "status": "passed" if passed else "failed",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": validation_run_id,
        "target": str(target_path.resolve()),
        "artifact_dir": str(artifact_dir),
        "report_path": str(report_path) if report_path.is_file() else None,
        "usage_path": str(usage_path) if usage_path.is_file() else None,
        "validation_path": str(validation_path),
        "scan_exit_code": scan_exit_code,
        "investigation_exit_code": investigation_exit_code,
        "permit_status": summary.permit_status,
        "findings": summary.findings_count,
        "graph_paths": summary.graph_paths_count,
        "controls": summary.controls_count,
        "credentials": len(summary.credential_names),
        "available_artifacts": list(summary.available_artifacts),
        "model": selected_model,
        "agent_recursion_limit": agent_recursion_limit,
        "phoenix": enable_phoenix,
        "langsmith": enable_langsmith,
        "citation_check": citation_check,
        "usage_summary": usage_summary,
    }
    try:
        validation_path.parent.mkdir(parents=True, exist_ok=True)
        validation_path.write_text(
            json.dumps(validation_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        run_metrics = build_live_validation_metrics(
            context=context,
            target_path=target_path,
            status=validation_payload["status"],
            started_at=validation_started_at,
            completed_at=validation_completed_at,
            model=selected_model,
            citation_check=citation_check,
            usage_summary=usage_summary,
            scan_exit_code=scan_exit_code,
            investigation_exit_code=investigation_exit_code,
            phoenix=enable_phoenix,
            langsmith=enable_langsmith,
        )
        write_run_metrics(
            artifact_dir / RUN_METRICS_FILE,
            run_metrics,
        )
        event_path = analytics_events_path(target_path)
        append_analytics_event(
            event_path,
            event_from_metrics(
                "investigation_completed",
                run_metrics,
                status="passed" if investigation_exit_code == 0 else "failed",
                payload={"investigation_exit_code": investigation_exit_code},
            ),
        )
        append_analytics_event(
            event_path,
            event_from_metrics(
                (
                    "citation_check_passed"
                    if citation_check["supported"] is True
                    else "citation_check_failed"
                ),
                run_metrics,
                status=str(citation_check["status"]),
                payload={
                    "aggregate_mismatches": len(
                        citation_check.get("aggregate_mismatches") or []
                    ),
                    "unsupported_citations": len(
                        citation_check.get("unsupported_citations") or []
                    ),
                },
            ),
        )
        append_analytics_event(
            event_path,
            event_from_metrics("live_validation_completed", run_metrics),
        )
    except OSError as exc:
        print(f"error: failed to write live validation: {exc}", file=stderr)
        return 1

    _write_prefixed_output(investigation_stderr.getvalue(), stderr)
    print("Agent Permit Office", file=stdout)
    print(
        f"Status: {'live_validation_complete' if passed else 'live_validation_failed'}",
        file=stdout,
    )
    print(f"Target: {target_path.resolve()}", file=stdout)
    print(f"Run ID: {validation_run_id}", file=stdout)
    print(f"Artifacts: {artifact_dir}", file=stdout)
    print(f"Permit status: {summary.permit_status}", file=stdout)
    print(f"Findings: {summary.findings_count}", file=stdout)
    print(f"Graph paths: {summary.graph_paths_count}", file=stdout)
    print(f"Controls: {summary.controls_count}", file=stdout)
    print(f"Citation check: {citation_check['status']}", file=stdout)
    print(f"Deep Agent model: {selected_model}", file=stdout)
    print(f"Deep Agent recursion limit: {agent_recursion_limit}", file=stdout)
    print(
        f"Phoenix tracing: {'requested' if enable_phoenix else 'not_requested'}",
        file=stdout,
    )
    print(
        f"LangSmith tracing: {'requested' if enable_langsmith else 'not_requested'}",
        file=stdout,
    )
    if report_path.is_file():
        print(f"Report: {report_path}", file=stdout)
    if usage_path.is_file():
        print(f"OpenRouter usage: {usage_path}", file=stdout)
    print(f"Validation: {validation_path}", file=stdout)
    print(f"Metrics: {artifact_dir / RUN_METRICS_FILE}", file=stdout)
    print(f"Events: {analytics_events_path(target_path)}", file=stdout)
    return 0 if passed else (investigation_exit_code or 1)


def run_eval(
    fixture_root: Path,
    *,
    eval_run_id: str | None = None,
    output_dir: Path | None = None,
    upload_phoenix: bool = False,
    phoenix_base_url: str | None = None,
    phoenix_dataset_name: str = DEFAULT_PHOENIX_DATASET_NAME,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    if not fixture_root.exists():
        print(f"error: fixture root does not exist: {fixture_root}", file=stderr)
        return 2
    if not fixture_root.is_dir():
        print(f"error: fixture root must be a directory: {fixture_root}", file=stderr)
        return 2

    try:
        eval_run = run_fixture_eval_suite(
            fixture_root,
            eval_run_id=eval_run_id,
            output_dir=output_dir,
        )
    except (OSError, ValueError, RuntimeError, KeyError, json.JSONDecodeError) as exc:
        print(f"error: eval failed: {exc}", file=stderr)
        return 1

    phoenix_upload_result = None
    if upload_phoenix:
        try:
            phoenix_upload_result = upload_phoenix_dataset_rows(
                eval_run,
                dataset_name=phoenix_dataset_name,
                base_url=phoenix_base_url,
            )
        except Exception as exc:
            print(f"error: Phoenix upload failed: {exc}", file=stderr)
            return 1

    passed = sum(1 for result in eval_run.results if result.passed)
    total = len(eval_run.results)
    print("Agent Permit Office", file=stdout)
    print("Status: eval_complete", file=stdout)
    print(f"Eval run: {eval_run.eval_run_id}", file=stdout)
    print(f"Fixture root: {eval_run.fixture_root}", file=stdout)
    print(f"Output: {eval_run.output_dir}", file=stdout)
    print(f"Cases: {passed}/{total} passed", file=stdout)
    print(f"Results: {eval_run.output_dir / EVAL_RESULTS_FILE}", file=stdout)
    print(f"Report: {eval_run.output_dir / EVAL_REPORT_FILE}", file=stdout)
    print(
        f"Phoenix dataset rows: {eval_run.output_dir / PHOENIX_DATASET_ROWS_FILE}",
        file=stdout,
    )
    trend_dir = eval_trends_dir_for_output(eval_run.output_dir, eval_run.eval_run_id)
    print(f"Eval trends: {trend_dir / EVAL_TRENDS_JSON_FILE}", file=stdout)
    print(f"Eval trend report: {trend_dir / EVAL_TRENDS_MARKDOWN_FILE}", file=stdout)
    print(f"Events: {analytics_events_path_for_output(eval_run.output_dir)}", file=stdout)
    if phoenix_upload_result is not None:
        print("Phoenix upload: complete", file=stdout)
        print(f"Phoenix base URL: {phoenix_upload_result.base_url}", file=stdout)
        print(f"Phoenix dataset: {phoenix_upload_result.dataset_name}", file=stdout)
        print(
            f"Phoenix examples: {phoenix_upload_result.example_count}",
            file=stdout,
        )
        if phoenix_upload_result.dataset_id:
            print(f"Phoenix dataset ID: {phoenix_upload_result.dataset_id}", file=stdout)
    return 0 if eval_run.passed else 1


def run_analytics_summarize(
    path: Path,
    *,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    if path.name == ANALYTICS_EVENTS_FILE:
        event_path = path
    else:
        event_path = analytics_events_path(path)
    if not event_path.is_file():
        print(f"error: analytics event stream not found: {event_path}", file=stderr)
        return 2
    try:
        summary = build_analytics_summary(event_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: failed to summarize analytics events: {exc}", file=stderr)
        return 1

    print("Agent Permit Office", file=stdout)
    print("Status: analytics_summary_complete", file=stdout)
    print(f"Events: {summary['events_path']}", file=stdout)
    print(f"Total events: {summary['total_events']}", file=stdout)
    print("Event counts:", file=stdout)
    for event_name, count in summary["event_counts"].items():
        print(f"- {event_name}: {count}", file=stdout)
    latest_event = summary.get("latest_event")
    if latest_event:
        print(f"Latest event: {latest_event['event_name']}", file=stdout)
        print(f"Latest run: {latest_event.get('run_id') or 'none'}", file=stdout)
    return 0


def run_db_migrate(
    *,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    try:
        store = store_from_env()
        store.migrate()
    except RuntimeError as exc:
        print(f"error: {exc}", file=stderr)
        return 2
    except Exception as exc:
        print(f"error: database migration failed: {exc}", file=stderr)
        return 1

    print("Agent Permit Office", file=stdout)
    print("Status: db_migrate_complete", file=stdout)
    print("Schema: local_live_stack_v1", file=stdout)
    return 0


def run_ingest(
    artifact_dir: Path,
    *,
    repository_label: str | None = None,
    local_path: Path | None = None,
    branch: str | None = None,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    try:
        records = load_ingest_records(
            artifact_dir,
            repository_label=repository_label,
            local_path=local_path,
            branch=branch,
        )
        store = store_from_env()
        store.write_ingest_records(records)
    except RuntimeError as exc:
        print(f"error: {exc}", file=stderr)
        return 2
    except (FileNotFoundError, PermissionError, ValueError, OSError) as exc:
        print(f"error: ingest failed: {exc}", file=stderr)
        return 1
    except Exception as exc:
        print(f"error: database ingest failed: {exc}", file=stderr)
        return 1

    print("Agent Permit Office", file=stdout)
    print("Status: ingest_complete", file=stdout)
    print(f"Run ID: {records.run.run_id}", file=stdout)
    print(f"Repository: {records.repository.label}", file=stdout)
    print(f"Findings: {len(records.findings)}", file=stdout)
    print(f"Artifacts: {len(records.artifacts)}", file=stdout)
    print(f"Events: {len(records.events)}", file=stdout)
    print(
        f"Model usage: {'stored' if records.model_usage is not None else 'not_available'}",
        file=stdout,
    )
    return 0


def run_runner(
    *,
    once: bool,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    if not once:
        print("error: runner currently requires --once", file=stderr)
        return 2
    try:
        store = store_from_env()
        claimed = store.claim_next_scan_job()
    except RuntimeError as exc:
        print(f"error: {exc}", file=stderr)
        return 2
    except Exception as exc:
        print(f"error: failed to claim queued job: {exc}", file=stderr)
        return 1

    if claimed is None:
        print("Agent Permit Office", file=stdout)
        print("Status: runner_idle", file=stdout)
        print("Queued jobs: 0", file=stdout)
        return 0

    target_path = Path(claimed.repository.local_path)
    if not target_path.exists() or not target_path.is_dir():
        error = f"repository path is not a directory: {target_path}"
        try:
            store.fail_scan_job(claimed.job.id, error)
        except Exception as exc:
            print(f"error: failed to mark job failed: {exc}", file=stderr)
            return 1
        print(f"error: {error}", file=stderr)
        return 1

    scan_stdout = StringIO()
    scan_stderr = StringIO()
    scan_exit = run_scan(
        target_path,
        run_id=claimed.job.id,
        db_job_id=claimed.job.id,
        db_repository_label=claimed.repository.label,
        db_local_path=Path(claimed.repository.local_path),
        db_branch=claimed.repository.branch,
        stdout=scan_stdout,
        stderr=scan_stderr,
    )
    if scan_exit != 0:
        error = scan_stderr.getvalue().strip() or f"scan exited {scan_exit}"
        try:
            store.fail_scan_job(claimed.job.id, error)
        except Exception as exc:
            print(f"error: failed to mark job failed: {exc}", file=stderr)
            return 1
        print(error, file=stderr)
        return scan_exit

    try:
        store.complete_scan_job(claimed.job.id)
    except Exception as exc:
        print(f"error: failed to mark job complete: {exc}", file=stderr)
        return 1

    print("Agent Permit Office", file=stdout)
    print("Status: runner_job_complete", file=stdout)
    print(f"Job ID: {claimed.job.id}", file=stdout)
    print(f"Repository: {claimed.repository.label}", file=stdout)
    print(f"Target: {claimed.repository.local_path}", file=stdout)
    return 0


def run_real_eval(
    manifest_path: Path,
    *,
    repo_root: Path | None = None,
    eval_run_id: str | None = None,
    output_dir: Path | None = None,
    exclude_patterns: Sequence[str] | None = None,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    if not manifest_path.exists():
        print(f"error: manifest does not exist: {manifest_path}", file=stderr)
        return 2
    if not manifest_path.is_file():
        print(f"error: manifest must be a file: {manifest_path}", file=stderr)
        return 2
    if repo_root is not None and not repo_root.is_dir():
        print(f"error: repo root must be a directory: {repo_root}", file=stderr)
        return 2

    try:
        eval_run = run_real_repo_eval_suite(
            manifest_path,
            repo_root=repo_root,
            eval_run_id=eval_run_id,
            output_dir=output_dir,
            exclude_patterns=tuple(exclude_patterns or ()),
        )
    except (OSError, ValueError, RuntimeError, KeyError, json.JSONDecodeError) as exc:
        print(f"error: real repo eval failed: {exc}", file=stderr)
        return 1

    passed = sum(1 for result in eval_run.results if result.passed)
    total = len(eval_run.results)
    print("Agent Permit Office", file=stdout)
    print("Status: real_repo_eval_complete", file=stdout)
    print(f"Eval run: {eval_run.eval_run_id}", file=stdout)
    print(f"Manifest: {eval_run.manifest_path}", file=stdout)
    if eval_run.repo_root is not None:
        print(f"Repo root: {eval_run.repo_root}", file=stdout)
    print(f"Output: {eval_run.output_dir}", file=stdout)
    print(f"Repos: {passed}/{total} passed", file=stdout)
    print(
        f"Results: {eval_run.output_dir / REAL_REPO_EVAL_RESULTS_FILE}",
        file=stdout,
    )
    print(
        f"Report: {eval_run.output_dir / REAL_REPO_EVAL_REPORT_FILE}",
        file=stdout,
    )
    return 0 if eval_run.passed else 1


def run_live_validate_real(
    manifest_path: Path,
    *,
    repo_root: Path | None = None,
    validation_run_id: str | None = None,
    output_dir: Path | None = None,
    model: str | None = None,
    agent_recursion_limit: int = DEFAULT_DEEP_AGENT_RECURSION_LIMIT,
    enable_phoenix: bool = False,
    enable_langsmith: bool = False,
    exclude_patterns: Sequence[str] | None = None,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    if not manifest_path.exists():
        print(f"error: manifest does not exist: {manifest_path}", file=stderr)
        return 2
    if not manifest_path.is_file():
        print(f"error: manifest must be a file: {manifest_path}", file=stderr)
        return 2
    if repo_root is not None and not repo_root.is_dir():
        print(f"error: repo root must be a directory: {repo_root}", file=stderr)
        return 2

    try:
        validation_run = run_live_repo_validation_suite(
            manifest_path,
            repo_root=repo_root,
            validation_run_id=validation_run_id,
            output_dir=output_dir,
            model=model,
            agent_recursion_limit=agent_recursion_limit,
            enable_phoenix=enable_phoenix,
            enable_langsmith=enable_langsmith,
            exclude_patterns=tuple(exclude_patterns or ()),
        )
    except (OSError, ValueError, RuntimeError, KeyError, json.JSONDecodeError) as exc:
        print(f"error: live repo validation failed: {exc}", file=stderr)
        return 1

    passed = sum(1 for result in validation_run.results if result.passed)
    total = len(validation_run.results)
    total_tokens = sum(result.total_tokens for result in validation_run.results)
    cached_tokens = sum(result.cached_tokens for result in validation_run.results)
    input_tokens = sum(result.input_tokens for result in validation_run.results)
    cache_hit_ratio = (
        round(cached_tokens / input_tokens, 4)
        if input_tokens
        else 0.0
    )
    print("Agent Permit Office", file=stdout)
    print("Status: live_repo_validation_complete", file=stdout)
    print(f"Validation run: {validation_run.validation_run_id}", file=stdout)
    print(f"Manifest: {validation_run.manifest_path}", file=stdout)
    if validation_run.repo_root is not None:
        print(f"Repo root: {validation_run.repo_root}", file=stdout)
    print(f"Output: {validation_run.output_dir}", file=stdout)
    print(f"Repos: {passed}/{total} passed", file=stdout)
    print(f"Total tokens: {total_tokens}", file=stdout)
    print(f"Cached tokens: {cached_tokens}", file=stdout)
    print(f"Cache hit ratio: {cache_hit_ratio:.2%}", file=stdout)
    print(
        f"Results: {validation_run.output_dir / LIVE_REPO_VALIDATION_RESULTS_FILE}",
        file=stdout,
    )
    print(
        f"Report: {validation_run.output_dir / LIVE_REPO_VALIDATION_REPORT_FILE}",
        file=stdout,
    )
    if enable_phoenix:
        print("Phoenix tracing: requested", file=stdout)
    if enable_langsmith:
        print("LangSmith tracing: requested", file=stdout)
    return 0 if validation_run.passed else 1


def run_open_source_demo_cli(
    manifest_path: Path,
    *,
    repo_root: Path,
    demo_run_id: str | None = None,
    output_dir: Path | None = None,
    refresh_repos: bool = True,
    run_live_validation: bool = True,
    model: str | None = None,
    agent_recursion_limit: int = DEFAULT_DEEP_AGENT_RECURSION_LIMIT,
    enable_phoenix: bool = False,
    enable_langsmith: bool = False,
    exclude_patterns: Sequence[str] | None = None,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    if not manifest_path.exists():
        print(f"error: manifest does not exist: {manifest_path}", file=stderr)
        return 2
    if not manifest_path.is_file():
        print(f"error: manifest must be a file: {manifest_path}", file=stderr)
        return 2

    try:
        demo_run = run_open_source_demo(
            manifest_path,
            repo_root=repo_root,
            demo_run_id=demo_run_id,
            output_dir=output_dir,
            prepare_repos=True,
            refresh_repos=refresh_repos,
            run_live_validation=run_live_validation,
            model=model,
            agent_recursion_limit=agent_recursion_limit,
            enable_phoenix=enable_phoenix,
            enable_langsmith=enable_langsmith,
            exclude_patterns=tuple(exclude_patterns or ()),
        )
    except (OSError, ValueError, RuntimeError, KeyError, json.JSONDecodeError) as exc:
        print(f"error: open source demo failed: {exc}", file=stderr)
        return 1

    repos_ready = sum(1 for result in demo_run.repo_results if result.status != "failed")
    total_repos = len(demo_run.repo_results)
    validation = demo_run.validation_run
    print("Agent Permit Office", file=stdout)
    print("Status: open_source_demo_complete", file=stdout)
    print(f"Demo run: {demo_run.demo_run_id}", file=stdout)
    print(f"Manifest: {demo_run.manifest_path}", file=stdout)
    print(f"Repo root: {demo_run.repo_root}", file=stdout)
    print(f"Output: {demo_run.output_dir}", file=stdout)
    print(f"Repos ready: {repos_ready}/{total_repos}", file=stdout)
    if validation is None:
        print("Live validation: skipped", file=stdout)
    else:
        passed = sum(1 for result in validation.results if result.passed)
        total = len(validation.results)
        total_tokens = sum(result.total_tokens for result in validation.results)
        cached_tokens = sum(result.cached_tokens for result in validation.results)
        input_tokens = sum(result.input_tokens for result in validation.results)
        cache_hit_ratio = (
            round(cached_tokens / input_tokens, 4)
            if input_tokens
            else 0.0
        )
        print(f"Live validation: {passed}/{total} passed", file=stdout)
        print(f"Total tokens: {total_tokens}", file=stdout)
        print(f"Cached tokens: {cached_tokens}", file=stdout)
        print(f"Cache hit ratio: {cache_hit_ratio:.2%}", file=stdout)
    print(
        f"Results: {demo_run.output_dir / OPEN_SOURCE_DEMO_RESULTS_FILE}",
        file=stdout,
    )
    print(
        f"Report: {demo_run.output_dir / OPEN_SOURCE_DEMO_REPORT_FILE}",
        file=stdout,
    )
    print(
        f"HTML: {demo_run.output_dir / OPEN_SOURCE_DEMO_HTML_FILE}",
        file=stdout,
    )
    return 0 if demo_run.passed else 1


def run_rules(scanner: str | None, *, stdout: TextIO) -> int:
    rules = [
        rule
        for rule in RULE_DEFINITIONS
        if scanner is None or rule.scanner == scanner
    ]
    print("Agent Permit Office", file=stdout)
    print("Status: rules_listed", file=stdout)
    print(f"Rules: {len(rules)}", file=stdout)
    if scanner is not None:
        print(f"Scanner: {scanner}", file=stdout)
    for rule in rules:
        print(
            f"- {rule.rule_id} [{rule.default_severity.value}] "
            f"{rule.scanner}: {rule.title}",
            file=stdout,
        )
    return 0


def run_baseline(
    artifact_dir: Path,
    *,
    output_path: Path | None = None,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    try:
        context = EvidenceContext.load(artifact_dir)
    except (FileNotFoundError, PermissionError, ValueError) as exc:
        print(f"error: failed to load scan artifacts: {exc}", file=stderr)
        return 2

    output_path = output_path or (context.artifact_dir / BASELINE_FILE)
    baseline = build_finding_baseline(
        context.findings,
        scan_run_id=context.scan_run_id,
    )
    try:
        baseline_path = write_finding_baseline(baseline, output_path)
    except OSError as exc:
        print(f"error: failed to write baseline: {exc}", file=stderr)
        return 1

    print("Agent Permit Office", file=stdout)
    print("Status: baseline_complete", file=stdout)
    print(f"Artifacts: {context.artifact_dir}", file=stdout)
    print(f"Baseline: {baseline_path}", file=stdout)
    print(f"Findings: {len(baseline.findings)}", file=stdout)
    return 0


def run_diff(
    artifact_dir: Path,
    *,
    baseline_path: Path,
    output_dir: Path | None = None,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    try:
        context = EvidenceContext.load(artifact_dir)
    except (FileNotFoundError, PermissionError, ValueError) as exc:
        print(f"error: failed to load scan artifacts: {exc}", file=stderr)
        return 2
    try:
        baseline = load_finding_baseline(baseline_path)
    except (FileNotFoundError, ValueError, PermissionError) as exc:
        print(f"error: failed to load baseline: {exc}", file=stderr)
        return 2

    diff_report = diff_findings(
        baseline=baseline,
        current_findings=context.findings,
        scan_run_id=context.scan_run_id,
        baseline_path=baseline_path,
    )
    try:
        json_path, markdown_path = write_finding_diff_artifacts(
            diff_report,
            output_dir or context.artifact_dir,
        )
    except OSError as exc:
        print(f"error: failed to write diff artifacts: {exc}", file=stderr)
        return 1

    print("Agent Permit Office", file=stdout)
    print("Status: diff_complete", file=stdout)
    print(f"Artifacts: {context.artifact_dir}", file=stdout)
    print(f"Baseline: {baseline_path}", file=stdout)
    print(f"New findings: {len(diff_report.new_findings)}", file=stdout)
    print(f"Resolved findings: {len(diff_report.resolved_findings)}", file=stdout)
    print(f"Unchanged findings: {len(diff_report.unchanged_findings)}", file=stdout)
    print(f"Diff: {json_path}", file=stdout)
    print(f"Diff report: {markdown_path}", file=stdout)
    return 0


def run_sarif(
    artifact_dir: Path,
    *,
    output_path: Path | None = None,
    category: str = DEFAULT_SARIF_CATEGORY,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    try:
        context = EvidenceContext.load(artifact_dir)
    except (FileNotFoundError, PermissionError, ValueError) as exc:
        print(f"error: failed to load scan artifacts: {exc}", file=stderr)
        return 2

    try:
        sarif_path = write_sarif_file(
            context,
            output_path,
            category=category,
        )
    except OSError as exc:
        print(f"error: failed to write SARIF: {exc}", file=stderr)
        return 1

    print("Agent Permit Office", file=stdout)
    print("Status: sarif_complete", file=stdout)
    print(f"Artifacts: {context.artifact_dir}", file=stdout)
    print(f"SARIF: {sarif_path}", file=stdout)
    print(f"Findings: {len(context.findings)}", file=stdout)
    print(f"Category: {category}", file=stdout)
    return 0


def _read_json_file_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _write_prefixed_output(text: str, stream: TextIO) -> None:
    if text.strip():
        print(text.rstrip(), file=stream)
