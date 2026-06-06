from __future__ import annotations

import os
from collections.abc import Callable
import json
from typing import Any

from agent_permit.evidence_context import EvidenceContext
from agent_permit.investigation import critique_investigation_report


DEEP_AGENT_SYSTEM_PROMPT = """You are Agent Permit Office's evidence-bound investigator.

You may only use the provided evidence tools and the bounded scan artifacts they expose.
Do not claim a finding exists unless it appears in raw-findings.json or graph-paths.json.
Do not execute shell commands, launch MCP servers, read repository files, read secrets, or
modify files. Every security claim must cite one of the citation IDs returned by the tools.
If evidence is insufficient, say what artifact is missing instead of guessing.
"""


def build_investigation_prompt(context: EvidenceContext) -> str:
    summary = context.summary()
    return "\n".join(
        [
            "Write a cited permit investigation for this scan run.",
            f"Scan run: {summary.scan_run_id}",
            f"Permit status: {summary.permit_status}",
            f"Findings: {summary.findings_count}",
            f"Graph paths: {summary.graph_paths_count}",
            f"Controls: {summary.controls_count}",
            "Use only citations from list_citation_ids.",
            "Return Markdown.",
        ]
    )


def build_subagent_specs(context: EvidenceContext) -> list[dict[str, Any]]:
    tools = build_evidence_tools(context)
    return [
        {
            "name": "mcp-risk-specialist",
            "description": "Reviews MCP server and credential evidence only.",
            "system_prompt": (
                "Inspect MCP and credential evidence. Cite findings and controls. "
                "Do not infer server behavior beyond artifacts."
            ),
            "tools": tools,
        },
        {
            "name": "prompt-risk-specialist",
            "description": "Reviews risky prompt instruction evidence only.",
            "system_prompt": (
                "Inspect prompt instruction findings. Cite exact finding IDs. "
                "Do not quote uncited repo instruction text."
            ),
            "tools": tools,
        },
        {
            "name": "policy-specialist",
            "description": "Maps permit status to controls and required approvals.",
            "system_prompt": (
                "Explain permit status using permit.yaml, controls.json, and "
                "graph-paths.json only."
            ),
            "tools": tools,
        },
        {
            "name": "citation-critic",
            "description": "Checks whether the final report cites supported evidence.",
            "system_prompt": (
                "Reject unsupported citations, invented rule IDs, and known rule IDs "
                "mentioned without rule citations."
            ),
            "tools": tools,
        },
    ]


def build_evidence_tools(context: EvidenceContext) -> list[Callable[..., str]]:
    def list_evidence_artifacts() -> str:
        """List evidence artifact names that the investigator may read."""
        return "\n".join(context.list_artifacts())

    def read_evidence_artifact(name: str) -> str:
        """Read one bounded evidence artifact by exact artifact name."""
        return context.read_artifact(name)

    def summarize_evidence_context() -> str:
        """Summarize permit status, counts, credentials, and available artifacts."""
        summary = context.summary()
        return "\n".join(
            [
                f"scan_run_id: {summary.scan_run_id}",
                f"permit_status: {summary.permit_status}",
                f"findings_count: {summary.findings_count}",
                f"graph_paths_count: {summary.graph_paths_count}",
                f"controls_count: {summary.controls_count}",
                "credential_names: "
                + (", ".join(summary.credential_names) or "none"),
                "available_artifacts: "
                + ", ".join(summary.available_artifacts),
            ]
        )

    def list_citation_ids() -> str:
        """List all citation IDs that are valid in the final investigation."""
        return "\n".join(sorted(context.citation_ids()))

    def validate_report_citations(report_markdown: str) -> str:
        """Validate final Markdown report citations against scan artifacts."""
        result = critique_investigation_report(context, report_markdown)
        lines = [f"supported: {str(result.supported).lower()}"]
        if result.unsupported_citations:
            lines.append(
                "unsupported_citations: "
                + ", ".join(result.unsupported_citations)
            )
        if result.unsupported_rule_ids:
            lines.append(
                "unsupported_rule_ids: " + ", ".join(result.unsupported_rule_ids)
            )
        if result.missing_citation_rule_ids:
            lines.append(
                "missing_citation_rule_ids: "
                + ", ".join(result.missing_citation_rule_ids)
            )
        return "\n".join(lines)

    def get_finding(identifier: str) -> str:
        """Return finding JSON by exact finding ID or rule ID."""
        return _json_text(context.get_finding(identifier))

    def find_paths(
        source_category: str | None = None,
        sink_category: str | None = None,
    ) -> str:
        """Return graph path JSON filtered by optional source and sink category."""
        return _json_text(
            context.find_paths(
                source_category=source_category,
                sink_category=sink_category,
            )
        )

    def get_agent_bom() -> str:
        """Return agent bill of materials JSON."""
        return _json_text(context.get_agent_bom())

    def get_mcp_servers() -> str:
        """Return MCP server summaries JSON."""
        return _json_text(context.get_mcp_servers())

    def get_credential_refs() -> str:
        """Return credential reference summaries JSON."""
        return _json_text(context.get_credential_refs())

    def explain_rule(rule_id: str) -> str:
        """Return deterministic rule metadata JSON for a rule ID."""
        rule = context.explain_rule(rule_id)
        if rule is None:
            return _json_text({"error": "unknown_rule_id", "rule_id": rule_id})
        return _json_text(rule)

    return [
        list_evidence_artifacts,
        read_evidence_artifact,
        summarize_evidence_context,
        list_citation_ids,
        validate_report_citations,
        get_finding,
        find_paths,
        get_agent_bom,
        get_mcp_servers,
        get_credential_refs,
        explain_rule,
    ]


def create_deep_agent_investigator(
    context: EvidenceContext,
    *,
    model: str,
    enable_langsmith: bool = False,
) -> Any:
    try:
        from deepagents import FilesystemPermission, create_deep_agent
        from deepagents.backends import StateBackend
    except ImportError as exc:
        raise RuntimeError(
            "Deep Agent investigator requires the optional extra: "
            "uv run --extra deep-agent agent-permit investigate ..."
        ) from exc

    if enable_langsmith:
        os.environ.setdefault("LANGSMITH_TRACING", "true")
        os.environ.setdefault("LANGSMITH_PROJECT", "agent-permit-office")

    return create_deep_agent(
        model=model,
        tools=build_evidence_tools(context),
        system_prompt=DEEP_AGENT_SYSTEM_PROMPT,
        subagents=build_subagent_specs(context),
        backend=StateBackend(),
        permissions=[
            FilesystemPermission(
                operations=["read", "write"],
                paths=["/**"],
                mode="deny",
            )
        ],
    )


def invoke_deep_agent_investigator(
    context: EvidenceContext,
    *,
    model: str,
    enable_langsmith: bool = False,
) -> str:
    agent = create_deep_agent_investigator(
        context,
        model=model,
        enable_langsmith=enable_langsmith,
    )
    result = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": build_investigation_prompt(context),
                }
            ]
        },
        config={
            "configurable": {"thread_id": context.scan_run_id},
            "metadata": {
                "scan_run_id": context.scan_run_id,
                "permit_status": context.permit_status,
            },
            "tags": ["agent-permit-office", "deep-agent-investigator"],
        },
    )
    return _extract_last_message_text(result)


def _extract_last_message_text(result: Any) -> str:
    messages = result.get("messages", []) if isinstance(result, dict) else []
    if not messages:
        return str(result)
    last_message = messages[-1]
    content = getattr(last_message, "content", None)
    if content is None and isinstance(last_message, dict):
        content = last_message.get("content")
    return str(content)


def _json_text(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)
