from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
import re
from typing import Any


OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_API_KEY_ENV = "OPENROUTER_API_KEY"
OPENROUTER_DEFAULT_MODEL = "anthropic/claude-sonnet-4.6"
OPENROUTER_ESCALATION_MODEL = "openai/gpt-5.5"
OPENROUTER_MODEL_PREFIX = "openrouter:"
OPENROUTER_RESPONSE_CACHE_ENV = "OPENROUTER_RESPONSE_CACHE"
OPENROUTER_RESPONSE_CACHE_TTL_ENV = "OPENROUTER_RESPONSE_CACHE_TTL_SECONDS"
OPENROUTER_PROMPT_CACHE_ENV = "OPENROUTER_PROMPT_CACHE"
OPENROUTER_PROMPT_CACHE_TTL_ENV = "OPENROUTER_PROMPT_CACHE_TTL"
OPENROUTER_TIMEOUT_ENV = "OPENROUTER_TIMEOUT_SECONDS"
OPENROUTER_MAX_COMPLETION_TOKENS_ENV = "OPENROUTER_MAX_COMPLETION_TOKENS"
OPENROUTER_DEFAULT_RESPONSE_CACHE_TTL_SECONDS = 300
OPENROUTER_DEFAULT_TIMEOUT_SECONDS = 45
OPENROUTER_DEFAULT_MAX_COMPLETION_TOKENS = 2400
OPENROUTER_MAX_SESSION_ID_LENGTH = 256

_OPENROUTER_ALIASES = {
    "default": OPENROUTER_DEFAULT_MODEL,
    "sonnet": OPENROUTER_DEFAULT_MODEL,
    "sonnet-4.6": OPENROUTER_DEFAULT_MODEL,
    "claude-sonnet-4.6": OPENROUTER_DEFAULT_MODEL,
    "anthropic/claude-sonnet-4.6": OPENROUTER_DEFAULT_MODEL,
    "gpt-5.5": OPENROUTER_ESCALATION_MODEL,
    "openai/gpt-5.5": OPENROUTER_ESCALATION_MODEL,
}


@dataclass(frozen=True)
class OpenRouterCostControls:
    model_id: str
    prompt_cache_enabled: bool
    prompt_cache_ttl: str | None
    response_cache_enabled: bool
    response_cache_ttl_seconds: int
    session_id: str | None
    timeout_seconds: int
    max_completion_tokens: int
    experimental_metadata_enabled: bool


def is_openrouter_model(model: str) -> bool:
    normalized = model.strip()
    if normalized.startswith(OPENROUTER_MODEL_PREFIX):
        return True
    return normalized in set(_OPENROUTER_ALIASES.values())


def resolve_openrouter_model_id(model: str | None) -> str:
    normalized = (model or "default").strip()
    if normalized.startswith(OPENROUTER_MODEL_PREFIX):
        normalized = normalized.removeprefix(OPENROUTER_MODEL_PREFIX)
    return _OPENROUTER_ALIASES.get(normalized, normalized)


def create_openrouter_chat_model(
    model: str | None = None,
    *,
    api_key: str | None = None,
    session_id: str | None = None,
    chat_model_cls: Callable[..., Any] | None = None,
) -> Any:
    api_key = api_key or os.getenv(OPENROUTER_API_KEY_ENV)
    if not api_key:
        raise RuntimeError(
            f"OpenRouter live Deep Agent runs require {OPENROUTER_API_KEY_ENV}."
        )
    model_id = resolve_openrouter_model_id(model)
    headers = build_openrouter_headers(session_id=session_id)
    extra_body = build_openrouter_extra_body(model_id, session_id=session_id)

    if chat_model_cls is None:
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            raise RuntimeError(
                "OpenRouter model support requires the deep-agent extra: "
                "uv sync --extra deep-agent"
            ) from exc
        chat_model_cls = ChatOpenAI

    kwargs: dict[str, Any] = {
        "model": model_id,
        "api_key": api_key,
        "base_url": OPENROUTER_BASE_URL,
        "temperature": 0,
        "max_retries": 2,
        "timeout": _env_int(
            OPENROUTER_TIMEOUT_ENV,
            default=OPENROUTER_DEFAULT_TIMEOUT_SECONDS,
            minimum=5,
            maximum=600,
        ),
        "max_completion_tokens": _env_int(
            OPENROUTER_MAX_COMPLETION_TOKENS_ENV,
            default=OPENROUTER_DEFAULT_MAX_COMPLETION_TOKENS,
            minimum=128,
            maximum=8192,
        ),
        "default_headers": headers,
        "include_response_headers": True,
    }
    if extra_body:
        kwargs["extra_body"] = extra_body
    return chat_model_cls(**kwargs)


def resolve_deep_agent_model(model: str, *, session_id: str | None = None) -> Any:
    if model.startswith(OPENROUTER_MODEL_PREFIX) or is_openrouter_model(model):
        return create_openrouter_chat_model(model, session_id=session_id)
    return model


def build_openrouter_headers(*, session_id: str | None = None) -> dict[str, str]:
    headers = {
        "X-Title": "Agent Permit Office",
        "X-OpenRouter-Experimental-Metadata": "enabled",
    }
    referer = os.getenv("OPENROUTER_HTTP_REFERER")
    if referer:
        headers["HTTP-Referer"] = referer
    if _env_bool(OPENROUTER_RESPONSE_CACHE_ENV, default=True):
        headers["X-OpenRouter-Cache"] = "true"
        headers["X-OpenRouter-Cache-TTL"] = str(
            _env_int(
                OPENROUTER_RESPONSE_CACHE_TTL_ENV,
                default=OPENROUTER_DEFAULT_RESPONSE_CACHE_TTL_SECONDS,
                minimum=1,
                maximum=86400,
            )
        )
    resolved_session_id = build_openrouter_session_id(session_id)
    if resolved_session_id:
        headers["x-session-id"] = resolved_session_id
    return headers


def build_openrouter_extra_body(
    model_id: str,
    *,
    session_id: str | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {}
    resolved_session_id = build_openrouter_session_id(session_id)
    if resolved_session_id:
        body["session_id"] = resolved_session_id
    if _supports_top_level_prompt_cache(model_id) and _env_bool(
        OPENROUTER_PROMPT_CACHE_ENV,
        default=True,
    ):
        cache_control = {"type": "ephemeral"}
        ttl = os.getenv(OPENROUTER_PROMPT_CACHE_TTL_ENV, "").strip()
        if ttl:
            cache_control["ttl"] = ttl
        body["cache_control"] = cache_control
    return body


def build_openrouter_cost_controls(
    model: str | None = None,
    *,
    session_id: str | None = None,
) -> OpenRouterCostControls:
    model_id = resolve_openrouter_model_id(model)
    return OpenRouterCostControls(
        model_id=model_id,
        prompt_cache_enabled=(
            _supports_top_level_prompt_cache(model_id)
            and _env_bool(OPENROUTER_PROMPT_CACHE_ENV, default=True)
        ),
        prompt_cache_ttl=os.getenv(OPENROUTER_PROMPT_CACHE_TTL_ENV, "").strip()
        or None,
        response_cache_enabled=_env_bool(OPENROUTER_RESPONSE_CACHE_ENV, default=True),
        response_cache_ttl_seconds=_env_int(
            OPENROUTER_RESPONSE_CACHE_TTL_ENV,
            default=OPENROUTER_DEFAULT_RESPONSE_CACHE_TTL_SECONDS,
            minimum=1,
            maximum=86400,
        ),
        session_id=build_openrouter_session_id(session_id),
        timeout_seconds=_env_int(
            OPENROUTER_TIMEOUT_ENV,
            default=OPENROUTER_DEFAULT_TIMEOUT_SECONDS,
            minimum=5,
            maximum=600,
        ),
        max_completion_tokens=_env_int(
            OPENROUTER_MAX_COMPLETION_TOKENS_ENV,
            default=OPENROUTER_DEFAULT_MAX_COMPLETION_TOKENS,
            minimum=128,
            maximum=8192,
        ),
        experimental_metadata_enabled=True,
    )


def build_openrouter_session_id(session_id: str | None) -> str | None:
    if session_id is None:
        return None
    normalized = re.sub(r"[^A-Za-z0-9_.:-]+", "-", session_id.strip())
    normalized = normalized.strip("-")
    if not normalized:
        return None
    value = f"agent-permit-office:{normalized}"
    return value[:OPENROUTER_MAX_SESSION_ID_LENGTH]


def _supports_top_level_prompt_cache(model_id: str) -> bool:
    return model_id.startswith("anthropic/claude")


def _env_bool(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _env_int(
    name: str,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    try:
        value = int(raw_value)
    except ValueError:
        return default
    return max(minimum, min(maximum, value))
