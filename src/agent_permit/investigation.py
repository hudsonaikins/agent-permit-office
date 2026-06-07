from __future__ import annotations

from dataclasses import dataclass
import re

from agent_permit.evidence_context import EvidenceContext
from agent_permit.rule_registry import DETERMINISTIC_RULE_IDS


_CITATION_RE = re.compile(r"\[(?P<citation>(?:finding|rule|path|control|artifact):[^\]]+|permit|summary|risk-report)\]")
_RULE_ID_RE = re.compile(r"\b(?:ci|mcp|prompt)-[a-z0-9-]+\b")
_SEVERITY_COUNT_RE = re.compile(
    r"\b(?P<count>\d+)\s+"
    r"(?P<severity>critical|high|medium|low|info)"
    r"(?=\s|[,.)])",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CitationCriticResult:
    supported: bool
    unsupported_citations: tuple[str, ...]
    unsupported_rule_ids: tuple[str, ...]
    missing_citation_rule_ids: tuple[str, ...]
    aggregate_mismatches: tuple[str, ...]


def build_investigation_markdown(context: EvidenceContext) -> str:
    summary = context.summary()
    lines = [
        "# Agent Permit Office Investigation",
        "",
        f"Scan run: `{summary.scan_run_id}` [permit]",
        f"Permit status: `{summary.permit_status}` [permit]",
        f"Findings: {summary.findings_count} [artifact:raw-findings.json]",
        "Finding severity counts: "
        + ", ".join(
            f"{severity}={count}"
            for severity, count in summary.finding_severity_counts.items()
        )
        + " [artifact:raw-findings.json]",
        f"Graph paths: {summary.graph_paths_count} [artifact:graph-paths.json]",
        f"Controls: {summary.controls_count} [artifact:controls.json]",
        f"Credentials: {', '.join(summary.credential_names) or 'none'} [artifact:agent-bom.json]",
        "",
        "## Deterministic Findings",
    ]
    if not context.findings:
        lines.append("No deterministic findings. [artifact:raw-findings.json]")
    else:
        for finding in sorted(
            context.findings,
            key=lambda item: (item.severity, item.rule_id, item.id),
        ):
            location = _finding_location(finding)
            lines.append(
                f"- `{finding.rule_id}` severity `{finding.severity}` at {location}: "
                f"{finding.title} [finding:{finding.id}] [rule:{finding.rule_id}]"
            )

    lines.extend(["", "## Graph Paths"])
    if not context.graph_paths.paths:
        lines.append("No risky graph paths. [artifact:graph-paths.json]")
    else:
        for graph_path in sorted(context.graph_paths.paths, key=lambda item: item.id):
            lines.append(
                f"- `{graph_path.source_category}` to `{graph_path.sink_category}`: "
                f"{graph_path.rationale} [path:{graph_path.id}]"
            )

    lines.extend(["", "## Controls"])
    if not context.controls.controls:
        lines.append("No missing or weak controls. [artifact:controls.json]")
    else:
        for control in sorted(context.controls.controls, key=lambda item: item.id):
            lines.append(
                f"- `{control.status}` control `{control.name}`: "
                f"{control.recommendation} [control:{control.id}]"
            )

    lines.extend(
        [
            "",
            "## Deep Agent Boundary",
            "The Deep Agent investigator may explain and critique this evidence, "
            "but it must not invent findings, execute repo code, launch MCP servers, "
            "read raw secrets, or modify repository files. [summary]",
        ]
    )
    return "\n".join(lines) + "\n"


def critique_investigation_report(
    context: EvidenceContext,
    report_markdown: str,
) -> CitationCriticResult:
    supported_citations = context.citation_ids()
    citations = {
        match.group("citation").strip()
        for match in _CITATION_RE.finditer(report_markdown)
    }
    unsupported_citations = tuple(
        sorted(citation for citation in citations if citation not in supported_citations)
    )

    known_rules = context.finding_rule_ids()
    mentioned_rules = {
        rule_id
        for rule_id in _RULE_ID_RE.findall(report_markdown)
        if rule_id in DETERMINISTIC_RULE_IDS
    }
    unsupported_rule_ids = tuple(sorted(mentioned_rules - known_rules))
    missing_citation_rule_ids = tuple(
        sorted(
            rule_id
            for rule_id in mentioned_rules & known_rules
            if f"rule:{rule_id}" not in citations
        )
    )
    aggregate_mismatches = _aggregate_mismatches(context, report_markdown)

    return CitationCriticResult(
        supported=not (
            unsupported_citations
            or unsupported_rule_ids
            or missing_citation_rule_ids
            or aggregate_mismatches
        ),
        unsupported_citations=unsupported_citations,
        unsupported_rule_ids=unsupported_rule_ids,
        missing_citation_rule_ids=missing_citation_rule_ids,
        aggregate_mismatches=aggregate_mismatches,
    )


def _aggregate_mismatches(
    context: EvidenceContext,
    report_markdown: str,
) -> tuple[str, ...]:
    expected = context.finding_severity_counts()
    mismatches: set[str] = set()
    for match in _SEVERITY_COUNT_RE.finditer(report_markdown):
        severity = match.group("severity").lower()
        claimed = int(match.group("count"))
        actual = expected.get(severity, 0)
        if claimed != actual:
            mismatches.add(
                f"{severity}: claimed {claimed}, expected {actual}"
            )
    return tuple(sorted(mismatches))


def _finding_location(finding: object) -> str:
    evidence = finding.evidence[0] if finding.evidence else None
    if evidence is None:
        return "no evidence"
    if evidence.line_start is None:
        return evidence.path
    return f"{evidence.path}:{evidence.line_start}"
