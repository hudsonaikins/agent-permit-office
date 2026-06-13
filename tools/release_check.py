#!/usr/bin/env python3
"""Run local release-candidate checks without pushing or deploying."""

from __future__ import annotations

import argparse
import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse


REPO_ROOT = Path(__file__).resolve().parents[1]
LINK_PATTERN = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


@dataclass(frozen=True)
class Check:
    name: str
    command: list[str]
    cwd: Path = REPO_ROOT


def run_check(check: Check) -> int:
    print(f"\n==> {check.name}")
    print(f"$ {format_command(check.command)}")
    completed = subprocess.run(check.command, cwd=check.cwd, env=os.environ.copy())
    if completed.returncode:
        print(f"FAIL: {check.name} exited {completed.returncode}")
    else:
        print(f"PASS: {check.name}")
    return completed.returncode


def format_command(command: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in command)


def require_executable(name: str) -> None:
    if shutil.which(name):
        return
    raise SystemExit(f"Missing required executable: {name}")


def tracked_markdown_files() -> list[Path]:
    completed = subprocess.run(
        ["git", "ls-files", "*.md"],
        cwd=REPO_ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    return [REPO_ROOT / line for line in completed.stdout.splitlines() if line]


def is_external_link(target: str) -> bool:
    parsed = urlparse(target)
    return parsed.scheme in {"http", "https", "mailto", "tel"}


def normalize_link_target(target: str) -> str:
    target = target.strip()
    if not target:
        return target
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    return target.split("#", 1)[0].strip()


def check_markdown_links() -> int:
    print("\n==> Markdown local links")
    failures: list[str] = []
    for markdown_file in tracked_markdown_files():
        text = markdown_file.read_text(encoding="utf-8")
        for match in LINK_PATTERN.finditer(text):
            raw_target = match.group(1)
            target = normalize_link_target(raw_target)
            if not target or is_external_link(target):
                continue
            if target.startswith("#"):
                continue
            if target.startswith("app://"):
                continue
            clean_target = unquote(target)
            target_path = (markdown_file.parent / clean_target).resolve()
            try:
                target_path.relative_to(REPO_ROOT)
            except ValueError:
                failures.append(f"{markdown_file.relative_to(REPO_ROOT)} -> {raw_target} leaves repo")
                continue
            if not target_path.exists():
                failures.append(f"{markdown_file.relative_to(REPO_ROOT)} -> {raw_target}")
    if failures:
        print("FAIL: missing local Markdown links")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("PASS: Markdown local links")
    return 0


def build_checks(args: argparse.Namespace) -> list[Check]:
    checks = [
        Check(
            name="Python tests",
            command=["uv", "run", "--frozen", "--all-extras", "pytest"],
        ),
        Check(
            name="Repository self-scan",
            command=[
                "uv",
                "run",
                "--frozen",
                "agent-permit",
                "scan",
                ".",
                "--ci",
                "--exclude",
                "tests/fixtures/**",
            ],
        ),
    ]
    if not args.skip_package:
        checks.append(Check(name="Python package build", command=["uv", "build"]))
    if not args.skip_dashboard:
        dashboard_dir = REPO_ROOT / "dashboard"
        checks.extend(
            [
                Check(name="Dashboard lint", command=["bun", "run", "lint"], cwd=dashboard_dir),
                Check(name="Dashboard build", command=["bun", "run", "build"], cwd=dashboard_dir),
            ]
        )
    return checks


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-dashboard",
        action="store_true",
        help="Skip Bun dashboard lint/build checks.",
    )
    parser.add_argument(
        "--skip-package",
        action="store_true",
        help="Skip Python wheel/sdist build.",
    )
    parser.add_argument(
        "--skip-markdown",
        action="store_true",
        help="Skip local Markdown link checks.",
    )
    return parser.parse_args()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    args = parse_args()
    require_executable("git")
    require_executable("uv")
    if not args.skip_dashboard:
        require_executable("bun")

    failures = 0
    if not args.skip_markdown:
        failures += check_markdown_links()
    for check in build_checks(args):
        failures += 1 if run_check(check) else 0

    print("\n==> Release check summary")
    if failures:
        print(f"FAILED: {failures} check(s) failed.")
        return 1
    print("PASSED: release candidate checks completed locally.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
