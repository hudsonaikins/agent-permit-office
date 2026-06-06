from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from agent_permit.models import (
    Confidence,
    EvidenceLocation,
    FileInventory,
    FileKind,
    Finding,
    FindingCategory,
    Severity,
)
from agent_permit.redaction import redact_secret_text


WRITE_PERMISSION_RE = re.compile(
    r"^\s*(?P<scope>[A-Za-z0-9_-]+)\s*:\s*write\s*(?:#.*)?$",
    re.IGNORECASE,
)
SECRETS_REF_RE = re.compile(r"\$\{\{\s*secrets\.(?P<name>[A-Za-z0-9_]+)\s*\}\}")
CHECKOUT_RE = re.compile(r"uses\s*:\s*actions/checkout@", re.IGNORECASE)
HEAD_REF_RE = re.compile(r"github\.event\.pull_request\.head", re.IGNORECASE)
MAINTENANCE_HINTS = frozenset(
    {
        "dependabot",
        "label",
        "release",
        "stale",
        "triage",
    }
)


@dataclass(frozen=True)
class PermissionSignal:
    line_number: int
    scope: str
    job_name: str | None = None


@dataclass(frozen=True)
class SecretRefSignal:
    line_number: int
    secret_name: str
    job_name: str | None = None


@dataclass(frozen=True)
class WorkflowLineSignal:
    line_number: int
    job_name: str | None = None


@dataclass(frozen=True)
class WorkflowSignals:
    events: tuple[str, ...] = ()
    pull_request_target_line: int | None = None
    write_all: PermissionSignal | None = None
    write_permissions: tuple[PermissionSignal, ...] = ()
    secret_refs: tuple[SecretRefSignal, ...] = ()
    checkout_lines: tuple[WorkflowLineSignal, ...] = ()
    head_ref_lines: tuple[WorkflowLineSignal, ...] = ()

    @property
    def has_write_permission(self) -> bool:
        return self.write_all is not None or bool(self.write_permissions)


class CiWorkflowScanner:
    def scan(
        self,
        root_path: Path,
        *,
        scan_run_id: str,
        inventory: FileInventory,
    ) -> list[Finding]:
        root_path = root_path.resolve()
        findings: list[Finding] = []

        for entry in inventory.files:
            if entry.kind != FileKind.CI_WORKFLOW:
                continue
            workflow_path = root_path / entry.path
            text = workflow_path.read_text(encoding="utf-8", errors="replace")
            findings.extend(_scan_workflow_text(entry.path, text))

        return findings


def _scan_workflow_text(rel_path: str, text: str) -> list[Finding]:
    lines = text.splitlines()
    signals = _workflow_signals(lines)
    findings: list[Finding] = []

    if signals.pull_request_target_line is not None:
        findings.append(_pull_request_target_finding(rel_path, signals, lines))
    if signals.write_all is not None:
        findings.append(_write_all_finding(rel_path, signals, lines))
    for permission in signals.write_permissions:
        findings.append(_write_permission_finding(rel_path, signals, permission, lines))
    for secret_ref in signals.secret_refs:
        findings.append(_secret_ref_finding(rel_path, signals, secret_ref, lines))
    if (
        signals.pull_request_target_line is not None
        and signals.has_write_permission
    ):
        findings.append(_pr_target_write_token_finding(rel_path, signals, lines))
    if (
        signals.pull_request_target_line is not None
        and signals.checkout_lines
        and signals.head_ref_lines
    ):
        findings.append(_untrusted_checkout_finding(rel_path, signals, lines))

    return findings


def _workflow_signals(lines: list[str]) -> WorkflowSignals:
    events: set[str] = set()
    pull_request_target_line: int | None = None
    write_all: PermissionSignal | None = None
    write_permissions: list[PermissionSignal] = []
    secret_refs: list[SecretRefSignal] = []
    checkout_lines: list[WorkflowLineSignal] = []
    head_ref_lines: list[WorkflowLineSignal] = []
    jobs_indent: int | None = None
    current_job: str | None = None

    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        indent = len(line) - len(line.lstrip(" "))
        inline_events = _inline_events(stripped)
        events.update(inline_events)
        if re.match(r"^jobs\s*:\s*(?:#.*)?$", stripped):
            jobs_indent = indent
            current_job = None
        elif jobs_indent is not None:
            if indent <= jobs_indent and stripped and not stripped.startswith("#"):
                current_job = None
            elif indent == jobs_indent + 2:
                job_match = re.match(r"^(?P<job>[A-Za-z0-9_-]+)\s*:\s*(?:#.*)?$", stripped)
                if job_match is not None:
                    current_job = job_match.group("job")

        if re.match(r"^pull_request_target\s*:", stripped):
            events.add("pull_request_target")
            pull_request_target_line = pull_request_target_line or line_number
        if re.match(r"^pull_request\s*:", stripped):
            events.add("pull_request")
        if re.match(r"^permissions\s*:\s*write-all\s*(?:#.*)?$", stripped):
            write_all = write_all or PermissionSignal(
                line_number=line_number,
                scope="write-all",
                job_name=current_job,
            )

        write_permission_match = WRITE_PERMISSION_RE.match(line)
        if write_permission_match is not None:
            scope = write_permission_match.group("scope")
            if scope != "permissions":
                write_permissions.append(
                    PermissionSignal(
                        line_number=line_number,
                        scope=scope,
                        job_name=current_job,
                    )
                )

        for secret_match in SECRETS_REF_RE.finditer(line):
            secret_refs.append(
                SecretRefSignal(
                    line_number=line_number,
                    secret_name=secret_match.group("name"),
                    job_name=current_job,
                )
            )
        if CHECKOUT_RE.search(line):
            checkout_lines.append(WorkflowLineSignal(line_number, current_job))
        if HEAD_REF_RE.search(line):
            head_ref_lines.append(WorkflowLineSignal(line_number, current_job))

    return WorkflowSignals(
        events=tuple(sorted(events)),
        pull_request_target_line=pull_request_target_line,
        write_all=write_all,
        write_permissions=tuple(write_permissions),
        secret_refs=tuple(secret_refs),
        checkout_lines=tuple(checkout_lines),
        head_ref_lines=tuple(head_ref_lines),
    )


def _pull_request_target_finding(
    rel_path: str,
    signals: WorkflowSignals,
    lines: list[str],
) -> Finding:
    line_number = signals.pull_request_target_line or 1
    return Finding(
        id=f"finding:ci-pull-request-target:{rel_path}:{line_number}",
        rule_id="ci-pull-request-target",
        title="Workflow uses pull_request_target",
        severity=Severity.HIGH,
        category=FindingCategory.RUNTIME_POLICY,
        evidence=[
            _evidence(
                rel_path,
                line_number,
                lines,
                workflow_event="pull_request_target",
                context_note=_event_context(signals),
            )
        ],
        risk=(
            "pull_request_target runs in the base repository context and can "
            "expose privileged tokens or secrets to automation that handles PRs."
        ),
        recommendation=(
            "Use pull_request for untrusted code, or tightly gate all jobs that "
            "run under pull_request_target."
        ),
        confidence=Confidence.HIGH,
        requires_human_review=True,
    )


def _write_all_finding(
    rel_path: str,
    signals: WorkflowSignals,
    lines: list[str],
) -> Finding:
    permission = signals.write_all or PermissionSignal(line_number=1, scope="write-all")
    line_number = permission.line_number
    context_note = _context_note(rel_path, permission.job_name, signals)
    return Finding(
        id=f"finding:ci-write-all-permissions:{rel_path}:{line_number}",
        rule_id="ci-write-all-permissions",
        title="Workflow grants write-all permissions",
        severity=Severity.HIGH,
        category=FindingCategory.RUNTIME_POLICY,
        evidence=[
            _evidence(
                rel_path,
                line_number,
                lines,
                workflow_event=_event_context(signals),
                workflow_job=permission.job_name,
                permission_scope=permission.scope,
                context_note=context_note,
            )
        ],
        risk="write-all grants broad repository mutation capability to workflow jobs.",
        recommendation=(
            "Replace write-all with least-privilege permissions scoped to the "
            "job that needs them."
        ),
        confidence=_confidence_for_context(context_note),
        requires_human_review=True,
    )


def _write_permission_finding(
    rel_path: str,
    signals: WorkflowSignals,
    permission: PermissionSignal,
    lines: list[str],
) -> Finding:
    context_note = _context_note(rel_path, permission.job_name, signals)
    return Finding(
        id=(
            f"finding:ci-write-permission:{rel_path}:"
            f"{permission.line_number}:{permission.scope}"
        ),
        rule_id="ci-write-permission",
        title="Workflow grants write permission",
        severity=Severity.MEDIUM,
        category=FindingCategory.RUNTIME_POLICY,
        evidence=[
            _evidence(
                rel_path,
                permission.line_number,
                lines,
                workflow_event=_event_context(signals),
                workflow_job=permission.job_name,
                permission_scope=permission.scope,
                context_note=context_note,
            )
        ],
        risk=(
            f"The workflow grants {permission.scope}: write"
            f"{_job_phrase(permission.job_name)}, enabling repository mutation."
        ),
        recommendation=(
            "Confirm this permission is required and restrict it to the "
            "smallest job scope."
        ),
        confidence=_confidence_for_context(context_note),
        requires_human_review=True,
    )


def _secret_ref_finding(
    rel_path: str,
    signals: WorkflowSignals,
    secret_ref: SecretRefSignal,
    lines: list[str],
) -> Finding:
    context_note = _context_note(rel_path, secret_ref.job_name, signals)
    return Finding(
        id=f"finding:ci-secret-reference:{rel_path}:{secret_ref.line_number}",
        rule_id="ci-secret-reference",
        title="Workflow references repository secrets",
        severity=Severity.MEDIUM,
        category=FindingCategory.CREDENTIAL_SCOPE,
        evidence=[
            _evidence(
                rel_path,
                secret_ref.line_number,
                lines,
                workflow_event=_event_context(signals),
                workflow_job=secret_ref.job_name,
                secret_name=secret_ref.secret_name,
                context_note=context_note,
            )
        ],
        risk=(
            f"Workflow job references repository secret {secret_ref.secret_name}, "
            "so event and permission controls determine whether automation can use it."
        ),
        recommendation=(
            "Verify the workflow only exposes secrets to trusted events and "
            "least-privilege jobs."
        ),
        confidence=_confidence_for_context(context_note),
        requires_human_review=True,
    )


def _pr_target_write_token_finding(
    rel_path: str,
    signals: WorkflowSignals,
    lines: list[str],
) -> Finding:
    permission = signals.write_all or signals.write_permissions[0]
    line_number = permission.line_number
    return Finding(
        id=f"finding:ci-pr-target-write-token:{rel_path}:{line_number}",
        rule_id="ci-pr-target-write-token",
        title="PR-target workflow has write token permissions",
        severity=Severity.CRITICAL,
        category=FindingCategory.RUNTIME_POLICY,
        evidence=[
            _evidence(rel_path, signals.pull_request_target_line or 1, lines),
            _evidence(
                rel_path,
                line_number,
                lines,
                workflow_event="pull_request_target",
                workflow_job=permission.job_name,
                permission_scope=permission.scope,
                context_note=_event_context(signals),
            ),
        ],
        risk=(
            "A pull_request_target workflow with write permissions can run "
            "automation in a privileged repository context while processing PRs."
        ),
        recommendation=(
            "Block agent execution until the workflow uses least-privilege "
            "permissions and trusted-code checkout semantics."
        ),
        confidence=Confidence.HIGH,
        requires_human_review=True,
    )


def _untrusted_checkout_finding(
    rel_path: str,
    signals: WorkflowSignals,
    lines: list[str],
) -> Finding:
    checkout = signals.checkout_lines[0]
    head_ref = signals.head_ref_lines[0]
    return Finding(
        id=f"finding:ci-pr-target-head-checkout:{rel_path}:{head_ref.line_number}",
        rule_id="ci-pr-target-head-checkout",
        title="PR-target workflow checks out pull request head code",
        severity=Severity.CRITICAL,
        category=FindingCategory.RUNTIME_POLICY,
        evidence=[
            _evidence(rel_path, signals.pull_request_target_line or 1, lines),
            _evidence(
                rel_path,
                checkout.line_number,
                lines,
                workflow_event="pull_request_target",
                workflow_job=checkout.job_name,
            ),
            _evidence(
                rel_path,
                head_ref.line_number,
                lines,
                workflow_event="pull_request_target",
                workflow_job=head_ref.job_name,
            ),
        ],
        risk=(
            "Checking out PR head code inside pull_request_target can execute "
            "untrusted code with privileged workflow context."
        ),
        recommendation=(
            "Do not check out untrusted PR head code in pull_request_target jobs "
            "that have secrets or write permissions."
        ),
        confidence=Confidence.HIGH,
        requires_human_review=True,
    )


def _evidence(
    rel_path: str,
    line_number: int,
    lines: list[str],
    *,
    workflow_event: str | None = None,
    workflow_job: str | None = None,
    permission_scope: str | None = None,
    secret_name: str | None = None,
    context_note: str | None = None,
) -> EvidenceLocation:
    line = lines[line_number - 1] if 0 <= line_number - 1 < len(lines) else ""
    return EvidenceLocation(
        path=rel_path,
        line_start=line_number,
        line_end=line_number,
        redacted_snippet=redact_secret_text(line.strip()),
        workflow_event=workflow_event,
        workflow_job=workflow_job,
        permission_scope=permission_scope,
        secret_name=secret_name,
        context_note=context_note,
    )


def _inline_events(stripped_line: str) -> set[str]:
    match = re.match(r"^on\s*:\s*(?P<value>.+?)\s*(?:#.*)?$", stripped_line)
    if match is None:
        return set()
    value = match.group("value").strip()
    if value.startswith("[") and value.endswith("]"):
        return {
            item.strip()
            for item in value.removeprefix("[").removesuffix("]").split(",")
            if item.strip()
        }
    return {value} if value else set()


def _event_context(signals: WorkflowSignals) -> str | None:
    if not signals.events:
        return None
    return ",".join(signals.events)


def _job_phrase(job_name: str | None) -> str:
    return f" in job {job_name}" if job_name else ""


def _context_note(
    rel_path: str,
    job_name: str | None,
    signals: WorkflowSignals,
) -> str | None:
    parts: list[str] = []
    event_context = _event_context(signals)
    if event_context:
        parts.append(f"events={event_context}")
    if job_name:
        parts.append(f"job={job_name}")
    if _is_maintenance_context(rel_path, job_name):
        parts.append("maintenance-workflow heuristic")
    return "; ".join(parts) or None


def _is_maintenance_context(rel_path: str, job_name: str | None) -> bool:
    value = f"{rel_path} {job_name or ''}".lower()
    return any(hint in value for hint in MAINTENANCE_HINTS)


def _confidence_for_context(context_note: str | None) -> Confidence:
    if context_note and "maintenance-workflow heuristic" in context_note:
        return Confidence.MEDIUM
    return Confidence.HIGH
