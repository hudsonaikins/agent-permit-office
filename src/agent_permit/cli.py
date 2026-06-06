from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import TextIO

from agent_permit import __version__
from agent_permit.artifacts import RunArtifactWriter
from agent_permit.capability_graph import CapabilityGraphBuilder
from agent_permit.deep_agent import invoke_deep_agent_investigator
from agent_permit.evidence_context import EvidenceContext
from agent_permit.evals import (
    DEFAULT_PHOENIX_BASE_URL,
    DEFAULT_PHOENIX_DATASET_NAME,
    EVAL_REPORT_FILE,
    EVAL_RESULTS_FILE,
    PHOENIX_DATASET_ROWS_FILE,
    REAL_REPO_EVAL_REPORT_FILE,
    REAL_REPO_EVAL_RESULTS_FILE,
    run_fixture_eval_suite,
    run_real_repo_eval_suite,
    upload_phoenix_dataset_rows,
)
from agent_permit.investigation import (
    build_investigation_markdown,
    critique_investigation_report,
)
from agent_permit.models import ScanRunStatus
from agent_permit.path_finder import CapabilityPathFinder
from agent_permit.permit_engine import PermitEngine
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
            "optional Deep Agents model string, for example openai:gpt-5.4; "
            "without this flag the command writes deterministic report markdown"
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
    rules_parser = subparsers.add_parser(
        "rules",
        help="list deterministic scanner rules",
    )
    rules_parser.add_argument(
        "--scanner",
        help="filter rules by scanner name, for example ci_workflows",
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
            stdout=stdout,
            stderr=stderr,
        )
    if args.command == "investigate":
        return run_investigate(
            args.artifact_dir,
            output_path=args.output,
            model=args.model,
            enable_langsmith=args.langsmith,
            enable_phoenix=args.phoenix,
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
    if args.command == "rules":
        return run_rules(args.scanner, stdout=stdout)
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
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    if not target_path.exists():
        print(f"error: target path does not exist: {target_path}", file=stderr)
        return 2
    if not target_path.is_dir():
        print(f"error: target path must be a directory: {target_path}", file=stderr)
        return 2

    try:
        artifact_writer = RunArtifactWriter()
        scan_run = artifact_writer.create_run(
            target_path,
            run_id=run_id,
            scan_options={
                "mode": "deterministic-scanners",
                "exclude_patterns": list(exclude_patterns or []),
            },
        )
        inventory = FileInventoryScanner(
            exclude_patterns=exclude_patterns,
        ).scan(target_path, scan_run_id=scan_run.id)
        artifact_writer.write_file_inventory(scan_run, inventory)
        mcp_result = McpConfigScanner().scan(
            target_path,
            scan_run_id=scan_run.id,
            inventory=inventory,
        )
        credential_refs = CredentialReferenceScanner().scan(
            target_path,
            scan_run_id=scan_run.id,
            inventory=inventory,
        )
        mcp_result.agent_bom.credential_refs.extend(credential_refs)
        prompt_findings = PromptInstructionScanner().scan(
            target_path,
            scan_run_id=scan_run.id,
            inventory=inventory,
        )
        ci_findings = CiWorkflowScanner().scan(
            target_path,
            scan_run_id=scan_run.id,
            inventory=inventory,
        )
        findings = [*mcp_result.findings, *prompt_findings, *ci_findings]
        graph_result = CapabilityGraphBuilder().build(
            scan_run_id=scan_run.id,
            inventory=inventory,
            agent_bom=mcp_result.agent_bom,
            findings=findings,
        )
        graph_path_report = CapabilityPathFinder().find_paths(
            graph_result.codebase_map,
        )
        permit_evaluation = PermitEngine().evaluate(
            scan_run_id=scan_run.id,
            artifact_dir=scan_run.artifact_dir,
            agent_bom=mcp_result.agent_bom,
            findings=graph_result.findings,
            graph_paths=graph_path_report,
        )
        summary_markdown = build_summary_markdown(
            permit=permit_evaluation.permit,
            findings=graph_result.findings,
            graph_paths=graph_path_report,
            controls=permit_evaluation.controls,
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
        sarif_path = None
        if write_sarif:
            sarif_path = write_sarif_file(
                EvidenceContext.load(scan_run.artifact_dir),
                category=sarif_category,
            )
        scan_run.status = ScanRunStatus.COMPLETED
        scan_run.completed_at = datetime.now(timezone.utc)
        artifact_writer.write_scan_run(scan_run)
    except OSError as exc:
        print(f"error: failed to create scan artifacts: {exc}", file=stderr)
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
    if sarif_path is not None:
        print(f"SARIF: {sarif_path}", file=stdout)
    if ci:
        print("CI mode: on", file=stdout)
    print("Next: review summary.md and risk-report.md", file=stdout)
    if ci and permit_evaluation.permit.status in {"blocked", "needs_review"}:
        return 1
    return 0


def run_investigate(
    artifact_dir: Path,
    *,
    output_path: Path | None = None,
    model: str | None = None,
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

    try:
        if model:
            report_markdown = invoke_deep_agent_investigator(
                context,
                model=model,
                enable_langsmith=enable_langsmith,
                enable_phoenix=enable_phoenix,
            )
        else:
            report_markdown = build_investigation_markdown(context)
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
    except OSError as exc:
        print(f"error: failed to write investigation report: {exc}", file=stderr)
        return 1

    print("Agent Permit Office", file=stdout)
    print("Status: investigation_complete", file=stdout)
    print(f"Artifacts: {context.artifact_dir}", file=stdout)
    print(f"Report: {output_path}", file=stdout)
    print(f"Permit status: {context.permit_status}", file=stdout)
    print(f"Findings: {len(context.findings)}", file=stdout)
    print(f"Citation check: {'passed' if critic_result.supported else 'failed'}", file=stdout)
    if model:
        print(f"Deep Agent model: {model}", file=stdout)
    if enable_langsmith:
        print("LangSmith tracing: requested", file=stdout)
    if enable_phoenix and model:
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
        return 1
    return 0


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
