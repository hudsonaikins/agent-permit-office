from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import wraps
import json
from typing import Any

from agent_permit import observability
from agent_permit.evidence_context import EvidenceContext
from agent_permit.investigation import critique_investigation_report
from agent_permit.model_provider import resolve_deep_agent_model


@dataclass(frozen=True)
class DeepAgentInvestigationResult:
    report_markdown: str
    usage_summary: dict[str, Any] | None


DEFAULT_DEEP_AGENT_RECURSION_LIMIT = 12
FINAL_REPORT_SENTINEL = "END_OF_REPORT"


DEEP_AGENT_SYSTEM_PROMPT = """You are Agent Permit Office's evidence-bound investigator.

You may only use the provided evidence tools and the bounded scan artifacts they expose.
Do not claim a finding exists unless it appears in raw-findings.json or graph-paths.json.
Do not execute shell commands, launch MCP servers, read repository files, read secrets, or
modify files. Every security claim must cite one of the citation IDs returned by the tools.
If evidence is insufficient, say what artifact is missing instead of guessing.
Every mention of a scanner rule ID must include the matching [rule:<rule_id>] citation
in the same paragraph or table row. Do not include calendar dates unless a scan artifact
contains that exact date. Do not write preamble before the report heading.
Complete the investigation within the configured graph recursion limit. Prefer a short
coordinator pass: summarize evidence, inspect the relevant findings or paths, draft the
report, then return final Markdown. The CLI runs a deterministic citation critic after
the final answer. Do not create TODO lists or delegate to subagents unless the evidence
is ambiguous. Keep the final report under 900 words and end it with END_OF_REPORT on
its own line.
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
            "Use at most six evidence-tool calls.",
            "Do not create TODO lists.",
            "Do not include a calendar date unless it is present in the scan artifacts.",
            "Do not write any preamble before the report heading.",
            "Every rule ID mention must include [rule:<rule_id>] in the same paragraph or table row.",
            "Return the final Markdown directly; the CLI validates citations after you finish.",
            f"End the final Markdown with `{FINAL_REPORT_SENTINEL}` on its own line.",
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

    tools = [
        list_evidence_artifacts,
        read_evidence_artifact,
        summarize_evidence_context,
        list_citation_ids,
        get_finding,
        find_paths,
        get_agent_bom,
        get_mcp_servers,
        get_credential_refs,
        explain_rule,
    ]
    return [_instrument_evidence_tool(context, tool) for tool in tools]


def _instrument_evidence_tool(
    context: EvidenceContext,
    tool: Callable[..., str],
) -> Callable[..., str]:
    @wraps(tool)
    def traced_tool(*args: Any, **kwargs: Any) -> str:
        input_metadata = observability.build_evidence_tool_input_metadata(
            args,
            kwargs,
        )
        with observability.trace_evidence_tool_call(
            tool_name=tool.__name__,
            scan_run_id=context.scan_run_id,
            permit_status=context.permit_status,
            input_metadata=input_metadata,
        ) as span:
            try:
                result = tool(*args, **kwargs)
            except Exception as exc:
                observability.record_evidence_tool_error(span, exc)
                raise
            observability.record_evidence_tool_result(span, result)
            return result

    return traced_tool


def create_deep_agent_investigator(
    context: EvidenceContext,
    *,
    model: str,
    enable_langsmith: bool = False,
    enable_phoenix: bool = False,
) -> Any:
    if enable_phoenix:
        from agent_permit.observability import configure_phoenix_tracing

        configure_phoenix_tracing()

    if enable_langsmith:
        os.environ.setdefault("LANGSMITH_TRACING", "true")
        os.environ.setdefault("LANGSMITH_PROJECT", "agent-permit-office")

    try:
        from deepagents import FilesystemPermission, create_deep_agent
        from deepagents.backends import StateBackend
    except ImportError as exc:
        raise RuntimeError(
            "Deep Agent investigator requires the optional extra: "
            "uv run --extra deep-agent agent-permit investigate ..."
        ) from exc

    return create_deep_agent(
        model=resolve_deep_agent_model(model, session_id=context.scan_run_id),
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
    enable_phoenix: bool = False,
    recursion_limit: int = DEFAULT_DEEP_AGENT_RECURSION_LIMIT,
) -> str:
    return invoke_deep_agent_investigator_with_metadata(
        context,
        model=model,
        enable_langsmith=enable_langsmith,
        enable_phoenix=enable_phoenix,
        recursion_limit=recursion_limit,
    ).report_markdown


def invoke_deep_agent_investigator_with_metadata(
    context: EvidenceContext,
    *,
    model: str,
    enable_langsmith: bool = False,
    enable_phoenix: bool = False,
    recursion_limit: int = DEFAULT_DEEP_AGENT_RECURSION_LIMIT,
) -> DeepAgentInvestigationResult:
    if recursion_limit < 2:
        raise RuntimeError("Deep Agent recursion limit must be at least 2.")
    agent = create_deep_agent_investigator(
        context,
        model=model,
        enable_langsmith=enable_langsmith,
        enable_phoenix=enable_phoenix,
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
            "recursion_limit": recursion_limit,
        },
    )
    report_markdown = _strip_final_report_sentinel(
        _extract_last_message_text(result)
    )
    return DeepAgentInvestigationResult(
        report_markdown=report_markdown,
        usage_summary=summarize_openrouter_usage(result),
    )


def summarize_openrouter_usage(result: Any) -> dict[str, Any] | None:
    messages = result.get("messages", []) if isinstance(result, dict) else []
    summary: dict[str, Any] = {
        "model_calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "cached_tokens": 0,
        "cache_write_tokens": 0,
        "generation_ids": [],
    }
    for message in messages:
        usage_metadata = _mapping_from_message(message, "usage_metadata")
        response_metadata = _mapping_from_message(message, "response_metadata")
        token_usage = _mapping_from_value(
            response_metadata.get("token_usage")
            or response_metadata.get("usage")
        )
        usage = usage_metadata or token_usage
        if not usage:
            continue
        summary["model_calls"] += 1
        input_tokens = _usage_int(
            usage,
            "input_tokens",
            "prompt_tokens",
        )
        output_tokens = _usage_int(
            usage,
            "output_tokens",
            "completion_tokens",
        )
        total_tokens = _usage_int(usage, "total_tokens") or (
            input_tokens + output_tokens
        )
        summary["input_tokens"] += input_tokens
        summary["output_tokens"] += output_tokens
        summary["total_tokens"] += total_tokens
        details = _mapping_from_value(
            usage.get("input_token_details")
            or usage.get("prompt_tokens_details")
            or token_usage.get("prompt_tokens_details")
        )
        summary["cached_tokens"] += _usage_int(
            details,
            "cached_tokens",
            "cache_read",
            "cache_read_tokens",
        )
        summary["cache_write_tokens"] += _usage_int(
            details,
            "cache_write_tokens",
            "cache_write",
        )
        generation_id = (
            response_metadata.get("id")
            or response_metadata.get("generation_id")
            or getattr(message, "id", None)
        )
        if generation_id:
            summary["generation_ids"].append(str(generation_id))

    if summary["model_calls"] == 0:
        return None
    summary["cache_hit_ratio"] = (
        round(summary["cached_tokens"] / summary["input_tokens"], 4)
        if summary["input_tokens"]
        else 0.0
    )
    summary["generation_ids"] = sorted(set(summary["generation_ids"]))
    return summary


def _extract_last_message_text(result: Any) -> str:
    messages = result.get("messages", []) if isinstance(result, dict) else []
    if not messages:
        return str(result)
    last_message = messages[-1]
    content = getattr(last_message, "content", None)
    if content is None and isinstance(last_message, dict):
        content = last_message.get("content")
    return str(content)


def _strip_final_report_sentinel(report_markdown: str) -> str:
    stripped = report_markdown.rstrip()
    if not stripped.endswith(FINAL_REPORT_SENTINEL):
        raise RuntimeError(
            "Deep Agent report was truncated or missing END_OF_REPORT sentinel. "
            "Increase OPENROUTER_MAX_COMPLETION_TOKENS or reduce report scope."
        )
    return stripped[: -len(FINAL_REPORT_SENTINEL)].rstrip() + "\n"


def _json_text(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def _mapping_from_message(message: Any, attribute: str) -> Mapping[str, Any]:
    value = getattr(message, attribute, None)
    if value is None and isinstance(message, dict):
        value = message.get(attribute)
    return _mapping_from_value(value)


def _mapping_from_value(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _usage_int(mapping: Mapping[str, Any], *keys: str) -> int:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, int | float):
            return int(value)
    return 0
