from __future__ import annotations

from collections import Counter
import hashlib
import os
from pathlib import Path

from pathspec import PathSpec

from agent_permit.models import FileInventory, FileInventoryEntry, FileKind


DEFAULT_IGNORED_DIR_NAMES = frozenset(
    {
        ".agent-permit",
        ".git",
        ".mypy_cache",
        ".next",
        ".pytest_cache",
        ".ruff_cache",
        ".turbo",
        ".venv",
        "__pycache__",
        "build",
        "coverage",
        "dist",
        "node_modules",
        "venv",
    }
)
ENV_EXAMPLE_NAMES = frozenset(
    {
        ".env.example",
        ".env.sample",
        ".env.template",
        "env.example",
    }
)
MCP_CONFIG_NAMES = frozenset(
    {
        ".mcp.json",
        "claude_desktop_config.json",
        "mcp.json",
    }
)
PACKAGE_MANIFEST_NAMES = frozenset(
    {
        "Cargo.toml",
        "composer.json",
        "go.mod",
        "package.json",
        "pyproject.toml",
        "requirements.txt",
        "setup.cfg",
        "setup.py",
    }
)
LOCKFILE_NAMES = frozenset(
    {
        "Cargo.lock",
        "bun.lock",
        "bun.lockb",
        "go.sum",
        "package-lock.json",
        "pnpm-lock.yaml",
        "poetry.lock",
        "uv.lock",
        "yarn.lock",
    }
)
HIGH_SIGNAL_KINDS = frozenset(
    {
        FileKind.AGENT_INSTRUCTION,
        FileKind.CI_WORKFLOW,
        FileKind.ENV_EXAMPLE,
        FileKind.LOCKFILE,
        FileKind.MCP_CONFIG,
        FileKind.PACKAGE_MANIFEST,
    }
)


class FileInventoryScanner:
    def __init__(
        self,
        *,
        ignored_dir_names: frozenset[str] = DEFAULT_IGNORED_DIR_NAMES,
        max_file_bytes: int = 1_048_576,
    ) -> None:
        self.ignored_dir_names = ignored_dir_names
        self.max_file_bytes = max_file_bytes

    def scan(self, root_path: Path, *, scan_run_id: str) -> FileInventory:
        root_path = root_path.resolve()
        gitignore_spec = self._load_root_gitignore(root_path)
        skipped: Counter[str] = Counter()
        entries: list[FileInventoryEntry] = []

        for dirpath, dirnames, filenames in os.walk(root_path):
            current_dir = Path(dirpath)
            dirnames[:] = self._filter_dirnames(
                root_path,
                current_dir,
                dirnames,
                gitignore_spec,
                skipped,
            )

            for filename in sorted(filenames):
                file_path = current_dir / filename
                rel_path = _relative_posix(root_path, file_path)
                if self._is_ignored_by_gitignore(rel_path, gitignore_spec):
                    skipped["gitignore"] += 1
                    continue
                if _is_sensitive_env_file(filename):
                    skipped["sensitive_env_file"] += 1
                    continue

                entry = self._build_entry(file_path, rel_path, skipped)
                if entry is not None:
                    entries.append(entry)

        entries.sort(key=lambda entry: entry.path)
        return FileInventory(
            scan_run_id=scan_run_id,
            root_path=str(root_path),
            files=entries,
            skipped=dict(sorted(skipped.items())),
        )

    def _filter_dirnames(
        self,
        root_path: Path,
        current_dir: Path,
        dirnames: list[str],
        gitignore_spec: PathSpec | None,
        skipped: Counter[str],
    ) -> list[str]:
        kept_dirnames: list[str] = []
        for dirname in sorted(dirnames):
            if dirname in self.ignored_dir_names:
                skipped["junk_dir"] += 1
                continue

            rel_path = _relative_posix(root_path, current_dir / dirname)
            if self._is_ignored_by_gitignore(f"{rel_path}/", gitignore_spec):
                skipped["gitignore"] += 1
                continue

            kept_dirnames.append(dirname)
        return kept_dirnames

    def _build_entry(
        self,
        file_path: Path,
        rel_path: str,
        skipped: Counter[str],
    ) -> FileInventoryEntry | None:
        try:
            size_bytes = file_path.stat().st_size
        except OSError:
            skipped["stat_error"] += 1
            return None

        if size_bytes > self.max_file_bytes:
            skipped["too_large"] += 1
            return None

        try:
            data = file_path.read_bytes()
        except OSError:
            skipped["read_error"] += 1
            return None

        if _is_binary(data):
            skipped["binary"] += 1
            return None

        kind = _classify_file(rel_path, file_path.name)
        return FileInventoryEntry(
            path=rel_path,
            kind=kind,
            size_bytes=size_bytes,
            sha256=hashlib.sha256(data).hexdigest(),
            high_signal=kind in HIGH_SIGNAL_KINDS,
            language=_language_for_file(rel_path, kind),
        )

    def _load_root_gitignore(self, root_path: Path) -> PathSpec | None:
        gitignore_path = root_path / ".gitignore"
        if not gitignore_path.is_file():
            return None
        return PathSpec.from_lines(
            "gitignore",
            gitignore_path.read_text(encoding="utf-8").splitlines(),
        )

    def _is_ignored_by_gitignore(
        self,
        rel_path: str,
        gitignore_spec: PathSpec | None,
    ) -> bool:
        if gitignore_spec is None:
            return False
        return gitignore_spec.match_file(rel_path)


def _classify_file(rel_path: str, filename: str) -> FileKind:
    suffix = Path(filename).suffix.lower()
    lower_name = filename.lower()

    if filename in {"AGENTS.md", "CLAUDE.md"}:
        return FileKind.AGENT_INSTRUCTION
    if rel_path.startswith(".codex/skills/") and filename == "SKILL.md":
        return FileKind.AGENT_INSTRUCTION
    if filename in MCP_CONFIG_NAMES:
        return FileKind.MCP_CONFIG
    if rel_path.startswith(".github/workflows/") and suffix in {".yaml", ".yml"}:
        return FileKind.CI_WORKFLOW
    if _is_env_example_file(filename):
        return FileKind.ENV_EXAMPLE
    if filename in PACKAGE_MANIFEST_NAMES:
        return FileKind.PACKAGE_MANIFEST
    if filename in LOCKFILE_NAMES:
        return FileKind.LOCKFILE
    if suffix == ".py":
        return FileKind.PYTHON
    if suffix in {".js", ".jsx", ".mjs", ".cjs"}:
        return FileKind.JAVASCRIPT
    if suffix in {".ts", ".tsx", ".mts", ".cts"}:
        return FileKind.TYPESCRIPT
    if suffix == ".md":
        return FileKind.MARKDOWN
    if suffix in {".yaml", ".yml"}:
        return FileKind.YAML
    if suffix == ".json":
        return FileKind.JSON
    if suffix == ".toml":
        return FileKind.TOML
    if lower_name.endswith(".lock"):
        return FileKind.LOCKFILE
    return FileKind.OTHER


def _is_binary(data: bytes) -> bool:
    return b"\x00" in data[:4096]


def _is_sensitive_env_file(filename: str) -> bool:
    return filename == ".env" or (
        filename.startswith(".env.") and not _is_env_example_file(filename)
    )


def _is_env_example_file(filename: str) -> bool:
    return filename in ENV_EXAMPLE_NAMES or (
        filename.startswith(".env.")
        and filename.endswith((".example", ".sample", ".template"))
    )


def _language_for_file(rel_path: str, kind: FileKind) -> str | None:
    if kind in {FileKind.AGENT_INSTRUCTION, FileKind.MARKDOWN}:
        return "markdown"
    if kind == FileKind.PYTHON:
        return "python"
    if kind == FileKind.JAVASCRIPT:
        return "javascript"
    if kind == FileKind.TYPESCRIPT:
        return "typescript"
    if kind in {FileKind.CI_WORKFLOW, FileKind.YAML}:
        return "yaml"
    if kind in {FileKind.JSON, FileKind.MCP_CONFIG}:
        return "json"
    if kind == FileKind.TOML or rel_path.endswith(".toml"):
        return "toml"
    return None


def _relative_posix(root_path: Path, path: Path) -> str:
    return path.relative_to(root_path).as_posix()
