from __future__ import annotations

from agent_permit.models import ControlReport, Finding, GraphPathReport, Permit


def build_summary_markdown(
    *,
    permit: Permit,
    findings: list[Finding],
    graph_paths: GraphPathReport,
    controls: ControlReport,
) -> str:
    lines = [
        "# Agent Permit Office Summary",
        "",
        f"Status: {permit.status}",
        f"Findings: {len(findings)}",
        f"Graph paths: {len(graph_paths.paths)}",
        f"Controls: {len(controls.controls)}",
        f"Credentials: {', '.join(permit.discovered_credentials) or 'none'}",
        "",
        "## Top Findings",
    ]
    if not findings:
        lines.append("No deterministic findings.")
    else:
        for finding in sorted(findings, key=lambda item: (item.severity, item.rule_id, item.id))[:5]:
            location = "no evidence"
            if finding.evidence:
                evidence = finding.evidence[0]
                location = evidence.path
                if evidence.line_start is not None:
                    location = f"{evidence.path}:{evidence.line_start}"
                context = _evidence_context(evidence)
                if context:
                    location = f"{location} ({context})"
            lines.append(f"- [{finding.severity}] {finding.rule_id} at {location}")

    lines.extend(["", "## Artifacts"])
    for artifact_name in (
        "permit.yaml",
        "risk-report.md",
        "raw-findings.json",
        "agent-bom.json",
        "codebase-map.json",
        "graph-paths.json",
        "controls.json",
    ):
        lines.append(f"- {artifact_name}")

    return "\n".join(lines) + "\n"


def _evidence_context(evidence: object) -> str:
    parts = []
    for label, attr in (
        ("event", "workflow_event"),
        ("job", "workflow_job"),
        ("scope", "permission_scope"),
        ("secret", "secret_name"),
    ):
        value = getattr(evidence, attr, None)
        if value:
            parts.append(f"{label}={value}")
    note = getattr(evidence, "context_note", None)
    if note and "maintenance-workflow heuristic" in note:
        parts.append("maintenance")
    return ", ".join(parts)
