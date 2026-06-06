import pytest

from agent_permit.model_provider import (
    OPENROUTER_BASE_URL,
    OPENROUTER_DEFAULT_MODEL,
    OPENROUTER_ESCALATION_MODEL,
    build_openrouter_cost_controls,
    build_openrouter_session_id,
    create_openrouter_chat_model,
    is_openrouter_model,
    resolve_openrouter_model_id,
)


def test_openrouter_model_aliases_resolve_to_current_ids() -> None:
    assert resolve_openrouter_model_id(None) == OPENROUTER_DEFAULT_MODEL
    assert resolve_openrouter_model_id("openrouter:sonnet-4.6") == (
        "anthropic/claude-sonnet-4.6"
    )
    assert resolve_openrouter_model_id("openrouter:claude-sonnet-4.6") == (
        "anthropic/claude-sonnet-4.6"
    )
    assert resolve_openrouter_model_id("openrouter:gpt-5.5") == "openai/gpt-5.5"
    assert resolve_openrouter_model_id("openrouter:openai/gpt-5.5") == (
        "openai/gpt-5.5"
    )


def test_openrouter_model_detection() -> None:
    assert is_openrouter_model("openrouter:sonnet-4.6") is True
    assert is_openrouter_model(OPENROUTER_DEFAULT_MODEL) is True
    assert is_openrouter_model(OPENROUTER_ESCALATION_MODEL) is True
    assert is_openrouter_model("openai:gpt-5.5") is False


def test_openrouter_model_requires_api_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        create_openrouter_chat_model("openrouter:sonnet-4.6")


def test_openrouter_chat_model_uses_openai_compatible_base_url() -> None:
    calls = []

    class FakeChatModel:
        def __init__(self, **kwargs):
            calls.append(kwargs)

    model = create_openrouter_chat_model(
        "openrouter:gpt-5.5",
        api_key="test-key",
        chat_model_cls=FakeChatModel,
    )

    assert isinstance(model, FakeChatModel)
    assert calls == [
        {
            "model": "openai/gpt-5.5",
            "api_key": "test-key",
            "base_url": OPENROUTER_BASE_URL,
            "temperature": 0,
            "max_retries": 2,
            "timeout": 45,
            "max_completion_tokens": 2400,
            "default_headers": {
                "X-Title": "Agent Permit Office",
                "X-OpenRouter-Cache": "true",
                "X-OpenRouter-Cache-TTL": "300",
                "X-OpenRouter-Experimental-Metadata": "enabled",
            },
            "include_response_headers": True,
        }
    ]


def test_openrouter_sonnet_enables_prompt_cache_and_sticky_session() -> None:
    calls = []

    class FakeChatModel:
        def __init__(self, **kwargs):
            calls.append(kwargs)

    create_openrouter_chat_model(
        "openrouter:sonnet-4.6",
        api_key="test-key",
        session_id="scan run 1",
        chat_model_cls=FakeChatModel,
    )

    session_id = "agent-permit-office:scan-run-1"
    assert calls[0]["default_headers"] == {
        "X-Title": "Agent Permit Office",
        "X-OpenRouter-Cache": "true",
        "X-OpenRouter-Cache-TTL": "300",
        "X-OpenRouter-Experimental-Metadata": "enabled",
        "x-session-id": session_id,
    }
    assert calls[0]["extra_body"] == {
        "cache_control": {"type": "ephemeral"},
        "session_id": session_id,
    }


def test_openrouter_cost_controls_follow_env(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_RESPONSE_CACHE", "false")
    monkeypatch.setenv("OPENROUTER_RESPONSE_CACHE_TTL_SECONDS", "900")
    monkeypatch.setenv("OPENROUTER_PROMPT_CACHE_TTL", "1h")
    monkeypatch.setenv("OPENROUTER_TIMEOUT_SECONDS", "30")
    monkeypatch.setenv("OPENROUTER_MAX_COMPLETION_TOKENS", "2048")

    controls = build_openrouter_cost_controls(
        "openrouter:sonnet-4.6",
        session_id="cost-run",
    )

    assert controls.model_id == "anthropic/claude-sonnet-4.6"
    assert controls.prompt_cache_enabled is True
    assert controls.prompt_cache_ttl == "1h"
    assert controls.response_cache_enabled is False
    assert controls.response_cache_ttl_seconds == 900
    assert controls.session_id == "agent-permit-office:cost-run"
    assert controls.timeout_seconds == 30
    assert controls.max_completion_tokens == 2048
    assert controls.experimental_metadata_enabled is True


def test_openrouter_session_id_is_sanitized_and_bounded() -> None:
    raw_value = "bad session id " + ("x" * 300)

    session_id = build_openrouter_session_id(raw_value)

    assert session_id is not None
    assert " " not in session_id
    assert len(session_id) == 256
