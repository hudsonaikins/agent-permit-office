from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from agent_permit.models import (
    AgentBom,
    ControlReport,
    ControlSignal,
    ControlStatus,
    EvidenceLocation,
    Finding,
    GraphPathReport,
    Permit,
    PermitStatus,
    Severity,
)


@dataclass(frozen=True)
class PermitEvaluation:
    permit: Permit
    controls: ControlReport
    risk_report_markdown: str


class PermitEngine:
    def evaluate(
        self,
        *,
        scan_run_id: str,
        artifact_dir: Path,
        agent_bom: AgentBom,
        findings: list[Finding],
        graph_paths: GraphPathReport,
    ) -> PermitEvaluation:
        controls = _control_report(scan_run_id, findings, graph_paths)
        status = _permit_status(findings, graph_paths, controls)
        permit = Permit(
            scan_run_id=scan_run_id,
            status=status,
            agent_name="repo-agent",
            discovered_tools=sorted(server.name for server in agent_bom.mcp_servers),
            discovered_credentials=sorted(
                {credential.name for credential in agent_bom.credential_refs}
            ),
            allowed_actions=_allowed_actions(status),
            forbidden_actions=_forbidden_actions(status, findings),
            required_approvals=_required_approvals(controls),
            conditions=_conditions(status, findings, graph_paths, controls),
            findings_summary=_finding_summary(findings, graph_paths),
            evidence_bundle_path=str(artifact_dir),
        )
        return PermitEvaluation(
            permit=permit,
            controls=controls,
            risk_report_markdown=_risk_report(permit, findings, graph_paths, controls),
        )


def _control_report(
    scan_run_id: str,
    findings: list[Finding],
    graph_paths: GraphPathReport,
) -> ControlReport:
    controls: list[ControlSignal] = []
    controls.extend(_finding_controls(findings))
    controls.extend(_path_controls(graph_paths))
    controls.sort(key=lambda control: control.id)
    return ControlReport(scan_run_id=scan_run_id, controls=controls)


def _finding_controls(findings: list[Finding]) -> list[ControlSignal]:
    controls: list[ControlSignal] = []
    for finding in findings:
        if not _finding_requires_control(finding):
            continue
        if finding.rule_id == "mcp-unpinned-package-command":
            controls.append(
                _missing_control(
                    "mcp-package-pinning",
                    "MCP package version pinning",
                    finding,
                    "MCP server package is not pinned.",
                    "Pin MCP package versions before granting credentials.",
                )
            )
        if finding.rule_id == "mcp-stdio-credential-ref":
            controls.append(
                _missing_control(
                    "mcp-credential-approval",
                    "MCP credential approval gate",
                    finding,
                    "Credential reference is passed to a local MCP runtime.",
                    "Require human approval and least-privilege credential scope.",
                )
            )
        if finding.rule_id.startswith("prompt-"):
            controls.append(
                _missing_control(
                    "prompt-instruction-review",
                    "Prompt instruction review",
                    finding,
                    "Agent instructions contain risky behavior guidance.",
                    "Remove risky instruction text before approving the agent.",
                )
            )
        if finding.rule_id in {
            "ci-pr-target-head-checkout",
            "ci-pr-target-write-token",
            "ci-pull-request-target",
            "ci-secret-reference",
            "ci-write-all-permissions",
            "ci-write-permission",
        }:
            controls.append(
                _missing_control(
                    "ci-least-privilege",
                    "CI least-privilege workflow control",
                    finding,
                    "Workflow trigger, token, or secret use is privileged.",
                    "Use trusted PR context and least-privilege workflow permissions.",
                )
            )
    return controls


def _path_controls(graph_paths: GraphPathReport) -> list[ControlSignal]:
    controls: list[ControlSignal] = []
    for path in graph_paths.paths:
        if path.source_category == "credential" and path.sink_category == "mcp_server":
            controls.append(
                ControlSignal(
                    id=f"control:path-mcp-credential-boundary:{path.id}",
                    name="Credential-to-MCP boundary control",
                    status=ControlStatus.WEAK,
                    target_id=path.sink_id,
                    rationale="Credential can reach an MCP runtime through the graph.",
                    recommendation=(
                        "Require package pinning, allowlist the MCP server, and use "
                        "least-privilege credentials."
                    ),
                    related_path_ids=[path.id],
                )
            )
        if (
            path.source_category == "workflow_file"
            and path.sink_category == "privileged_ci_workflow"
        ):
            controls.append(
                ControlSignal(
                    id=f"control:path-ci-privilege-boundary:{path.id}",
                    name="Privileged CI boundary control",
                    status=ControlStatus.MISSING,
                    target_id=path.sink_id,
                    rationale="Workflow file defines a privileged CI execution path.",
                    recommendation=(
                        "Remove write permissions or privileged PR context before "
                        "running agent workflows."
                    ),
                    related_path_ids=[path.id],
                )
            )
    return controls


def _missing_control(
    control_id: str,
    name: str,
    finding: Finding,
    rationale: str,
    recommendation: str,
) -> ControlSignal:
    return ControlSignal(
        id=f"control:{control_id}:{finding.id}",
        name=name,
        status=ControlStatus.MISSING,
        target_id=finding.source_fact_ids[0] if finding.source_fact_ids else None,
        evidence=finding.evidence,
        rationale=rationale,
        recommendation=recommendation,
        related_finding_ids=[finding.id],
    )


def _permit_status(
    findings: list[Finding],
    graph_paths: GraphPathReport,
    controls: ControlReport,
) -> PermitStatus:
    if any(_severity_value(finding.severity) == "critical" for finding in findings):
        return PermitStatus.BLOCKED
    if any(_severity_value(path.severity) == "critical" for path in graph_paths.paths):
        return PermitStatus.BLOCKED
    if any(_control_status_value(control.status) == "missing" for control in controls.controls):
        return PermitStatus.NEEDS_REVIEW
    if any(_severity_value(finding.severity) == "high" for finding in findings):
        return PermitStatus.NEEDS_REVIEW
    if any(_severity_value(path.severity) == "high" for path in graph_paths.paths):
        return PermitStatus.NEEDS_REVIEW
    if findings or graph_paths.paths or controls.controls:
        return PermitStatus.APPROVED_WITH_CONDITIONS
    return PermitStatus.APPROVED


def _allowed_actions(status: PermitStatus | str) -> list[str]:
    if _permit_status_value(status) == "approved":
        return ["read repository files", "generate local report"]
    if _permit_status_value(status) == "approved_with_conditions":
        return ["read repository files", "generate local report after conditions"]
    return ["read repository files", "generate local report"]


def _forbidden_actions(status: PermitStatus | str, findings: list[Finding]) -> list[str]:
    forbidden: set[str] = set()
    active_findings = [finding for finding in findings if _finding_requires_control(finding)]
    if _permit_status_value(status) == "blocked":
        forbidden.add("enable agent tool execution")
        forbidden.add("grant credentials to agent or MCP runtime")
    if any(finding.rule_id.startswith("ci-") for finding in active_findings):
        forbidden.add("run agent workflow in privileged CI context")
    if any(finding.rule_id.startswith("prompt-") for finding in active_findings):
        forbidden.add("run agent with poisoned instruction file")
    return sorted(forbidden)


def _required_approvals(controls: ControlReport) -> list[str]:
    return sorted(
        {
            f"{control.name}: {control.recommendation}"
            for control in controls.controls
            if _control_status_value(control.status) in {"missing", "weak"}
        }
    )


def _conditions(
    status: PermitStatus,
    findings: list[Finding],
    graph_paths: GraphPathReport,
    controls: ControlReport,
) -> list[str]:
    if _permit_status_value(status) == "approved":
        return []
    conditions: set[str] = set()
    for finding in findings:
        conditions.add(finding.recommendation)
    for path in graph_paths.paths:
        conditions.add(path.rationale)
    for control in controls.controls:
        conditions.add(control.recommendation)
    return sorted(conditions)


def _finding_summary(
    findings: list[Finding],
    graph_paths: GraphPathReport,
) -> dict[Severity, int]:
    counts: Counter[Severity] = Counter()
    for finding in findings:
        counts[finding.severity] += 1
    for path in graph_paths.paths:
        counts[path.severity] += 1
    return dict(sorted(counts.items(), key=lambda item: _severity_rank(item[0])))


def _risk_report(
    permit: Permit,
    findings: list[Finding],
    graph_paths: GraphPathReport,
    controls: ControlReport,
) -> str:
    lines = [
        "# Agent Permit Office Risk Report",
        "",
        f"Status: {permit.status}",
        f"Credentials: {', '.join(permit.discovered_credentials) or 'none'}",
        f"Findings: {len(findings)}",
        f"Graph paths: {len(graph_paths.paths)}",
        f"Controls: {len(controls.controls)}",
        "",
        "## Top Findings",
    ]
    if not findings:
        lines.append("")
        lines.append("No deterministic findings.")
    else:
        for finding in sorted(
            findings,
            key=lambda item: (_severity_rank(item.severity), item.rule_id, item.id),
        )[:10]:
            evidence = finding.evidence[0] if finding.evidence else None
            location = _format_location(evidence)
            lines.append(
                f"- [{finding.severity}] {finding.rule_id}: {finding.title} ({location})"
            )

    lines.extend(["", "## Required Approvals"])
    if not permit.required_approvals:
        lines.append("")
        lines.append("None.")
    else:
        for approval in permit.required_approvals:
            lines.append(f"- {approval}")

    lines.extend(["", "## Top Paths"])
    if not graph_paths.paths:
        lines.append("")
        lines.append("No risky graph paths.")
    else:
        for path in sorted(
            graph_paths.paths,
            key=lambda item: (_severity_rank(item.severity), item.id),
        )[:10]:
            lines.append(
                f"- [{path.severity}] {path.source_category} -> "
                f"{path.sink_category}: {path.rationale}"
            )

    return "\n".join(lines) + "\n"


def _severity_rank(severity: Severity | str) -> int:
    return {
        "critical": 0,
        "high": 1,
        "medium": 2,
        "low": 3,
        "info": 4,
    }[_severity_value(severity)]


def _severity_value(severity: Severity | str) -> str:
    return severity.value if isinstance(severity, Severity) else severity


def _permit_status_value(status: PermitStatus | str) -> str:
    return status.value if isinstance(status, PermitStatus) else status


def _control_status_value(status: ControlStatus | str) -> str:
    return status.value if isinstance(status, ControlStatus) else status


def _finding_requires_control(finding: Finding) -> bool:
    if finding.requires_human_review:
        return True
    return _severity_value(finding.severity) in {"critical", "high", "medium"}


def _format_location(evidence: EvidenceLocation | None) -> str:
    if evidence is None:
        return "no evidence"
    context = _evidence_context(evidence)
    if evidence.line_start is None:
        location = evidence.path
    else:
        location = f"{evidence.path}:{evidence.line_start}"
    if context:
        return f"{location} ({context})"
    return location


def _evidence_context(evidence: EvidenceLocation) -> str:
    parts = []
    for label, value in (
        ("event", evidence.workflow_event),
        ("job", evidence.workflow_job),
        ("scope", evidence.permission_scope),
        ("secret", evidence.secret_name),
    ):
        if value:
            parts.append(f"{label}={value}")
    if evidence.context_note and "maintenance-workflow heuristic" in evidence.context_note:
        parts.append("maintenance")
    return ", ".join(parts)
