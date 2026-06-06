from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import TextIO

from agent_permit import __version__
from agent_permit.artifacts import RunArtifactWriter
from agent_permit.models import ScanRunStatus
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
        return run_scan(args.path, args.run_id, stdout=stdout, stderr=stderr)

    parser.print_help(file=stdout)
    return 0


def run_scan(
    target_path: Path,
    run_id: str | None = None,
    *,
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
        prompt_findings = PromptInstructionScanner().scan(
            target_path,
            scan_run_id=scan_run.id,
            inventory=inventory,
        )
        findings = [*mcp_result.findings, *prompt_findings]
        artifact_writer.write_agent_bom(scan_run, mcp_result.agent_bom)
        artifact_writer.write_raw_findings(scan_run, findings)
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
    print(f"Findings: {len(findings)}", file=stdout)
    print("Next: credential and CI scanners", file=stdout)
    return 0
