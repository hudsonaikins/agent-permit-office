from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import TextIO

from agent_permit import __version__
from agent_permit.artifacts import RunArtifactWriter
from agent_permit.capability_graph import CapabilityGraphBuilder
from agent_permit.models import ScanRunStatus
from agent_permit.path_finder import CapabilityPathFinder
from agent_permit.permit_engine import PermitEngine
from agent_permit.reporting import build_summary_markdown
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
        return run_scan(args.path, args.run_id, ci=args.ci, stdout=stdout, stderr=stderr)

    parser.print_help(file=stdout)
    return 0


def run_scan(
    target_path: Path,
    run_id: str | None = None,
    *,
    ci: bool = False,
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
            scan_options={"mode": "deterministic-scanners"},
        )
        inventory = FileInventoryScanner().scan(target_path, scan_run_id=scan_run.id)
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
    if ci:
        print("CI mode: on", file=stdout)
    print("Next: GitHub Action packaging and SARIF decision", file=stdout)
    if ci and permit_evaluation.permit.status in {"blocked", "needs_review"}:
        return 1
    return 0
