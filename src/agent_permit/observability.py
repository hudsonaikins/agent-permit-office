from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
import os
from typing import Any
from urllib.parse import urlparse


DEFAULT_PHOENIX_BASE_URL = "http://localhost:6006"
DEFAULT_PHOENIX_ENDPOINT = f"{DEFAULT_PHOENIX_BASE_URL}/v1/traces"
DEFAULT_OBSERVABILITY_PROJECT = "agent-permit-office"
EVIDENCE_TOOL_SPAN_NAME = "agent_permit.evidence_tool"


@dataclass(frozen=True)
class PhoenixTracingConfig:
    project_name: str
    endpoint: str
    auto_instrument: bool


def configure_phoenix_tracing(
    *,
    project_name: str = DEFAULT_OBSERVABILITY_PROJECT,
    endpoint: str | None = None,
    auto_instrument: bool = True,
) -> PhoenixTracingConfig:
    try:
        from phoenix.otel import register
    except ImportError as exc:
        raise RuntimeError(
            "Phoenix tracing requires the optional extra: "
            "uv run --extra phoenix agent-permit investigate ..."
        ) from exc

    resolved_endpoint = normalize_phoenix_collector_endpoint(
        endpoint or os.environ.get(
            "PHOENIX_COLLECTOR_ENDPOINT",
            DEFAULT_PHOENIX_ENDPOINT,
        )
    )
    os.environ["PHOENIX_COLLECTOR_ENDPOINT"] = resolved_endpoint
    os.environ.setdefault("PHOENIX_PROJECT_NAME", project_name)
    register(
        project_name=project_name,
        endpoint=resolved_endpoint,
        auto_instrument=auto_instrument,
    )
    return PhoenixTracingConfig(
        project_name=project_name,
        endpoint=resolved_endpoint,
        auto_instrument=auto_instrument,
    )


def normalize_phoenix_collector_endpoint(endpoint: str) -> str:
    normalized = endpoint.rstrip("/")
    parsed = urlparse(normalized)
    if parsed.path in {"", "/"}:
        return f"{normalized}/v1/traces"
    return normalized


@contextmanager
def trace_evidence_tool_call(
    *,
    tool_name: str,
    scan_run_id: str,
    permit_status: str,
    input_metadata: Mapping[str, Any] | None = None,
) -> Iterator[Any]:
    tracer = _get_tracer()
    if tracer is None:
        yield _NoopSpan()
        return

    with tracer.start_as_current_span(EVIDENCE_TOOL_SPAN_NAME) as span:
        _set_attribute(span, "agent_permit.tool.name", tool_name)
        _set_attribute(span, "agent_permit.scan_run_id", scan_run_id)
        _set_attribute(span, "agent_permit.permit_status", permit_status)
        for key, value in (input_metadata or {}).items():
            _set_attribute(span, f"agent_permit.tool.input.{key}", value)
        yield span


def record_evidence_tool_result(span: Any, result: object) -> None:
    text = str(result)
    _set_attribute(span, "agent_permit.tool.outcome", "success")
    _set_attribute(span, "agent_permit.tool.output_chars", len(text))
    _set_attribute(span, "agent_permit.tool.output_lines", text.count("\n") + 1)


def record_evidence_tool_error(span: Any, exc: BaseException) -> None:
    _set_attribute(span, "agent_permit.tool.outcome", "error")
    _set_attribute(span, "agent_permit.tool.error_type", type(exc).__name__)
    if hasattr(span, "set_status"):
        try:
            from opentelemetry.trace import Status, StatusCode
        except ImportError:
            return
        span.set_status(Status(StatusCode.ERROR))


def build_evidence_tool_input_metadata(
    args: tuple[object, ...],
    kwargs: Mapping[str, object],
) -> dict[str, object]:
    return {
        "arg_count": len(args),
        "kwarg_keys": ",".join(sorted(kwargs)) or "none",
    }


def _get_tracer() -> Any | None:
    try:
        from opentelemetry import trace
    except ImportError:
        return None
    return trace.get_tracer("agent_permit")


def _set_attribute(span: Any, key: str, value: object) -> None:
    if value is None or not hasattr(span, "set_attribute"):
        return
    if isinstance(value, str | int | float | bool):
        span.set_attribute(key, value)
    else:
        span.set_attribute(key, str(value))


class _NoopSpan:
    def set_attribute(self, _key: str, _value: object) -> None:
        return None
