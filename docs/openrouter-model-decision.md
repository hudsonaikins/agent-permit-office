# OpenRouter Model Decision

Date: 2026-06-06

## Decision

Use OpenRouter for live Deep Agent runs.

Default model:

```text
openrouter:anthropic/claude-sonnet-4.6
```

Escalation model:

```text
openrouter:openai/gpt-5.5
```

## Why Sonnet 4.6 Default

Agent Permit Office needs cited, tool-using permit dossiers over bounded scanner artifacts. It does not need to dump a full raw repo into the model.

Claude Sonnet 4.6 is the better default because:

- strong agent/tool behavior
- strong coding and security-review fit
- 1M context on OpenRouter
- lower price than GPT-5.5
- enough capability for evidence-bound narrative and remediation

OpenRouter lists Claude Sonnet 4.6 at `$3/M` input and `$15/M` output with `1M` context.

## Why GPT-5.5 Escalation

GPT-5.5 is stronger frontier reasoning for harder cases, but costs more.

Use GPT-5.5 when:

- the citation critic repeatedly fails a Sonnet dossier
- findings span many controls and policy exceptions
- a high-stakes customer demo needs maximum reasoning headroom
- comparing model quality during evals

OpenRouter lists GPT-5.5 at `$5/M` input and `$30/M` output with `1M` context.

## Runtime

Set:

```bash
export OPENROUTER_API_KEY=<key>
```

Run default:

```bash
uv run --extra deep-agent agent-permit investigate \
  .agent-permit/runs/<run_id>
```

Run default with explicit alias:

```bash
uv run --extra deep-agent agent-permit investigate \
  .agent-permit/runs/<run_id> \
  --model openrouter:sonnet-4.6
```

Run escalation:

```bash
uv run --extra deep-agent agent-permit investigate \
  .agent-permit/runs/<run_id> \
  --agent-recursion-limit 12 \
  --model openrouter:gpt-5.5
```

Both model strings route through OpenRouter's OpenAI-compatible chat endpoint.

## Cost Controls

OpenRouter cost controls are enabled by default for live Deep Agent runs:

- top-level `cache_control: {"type": "ephemeral"}` for Claude prompt caching
- `session_id` based on the scan run ID for sticky provider routing
- `X-OpenRouter-Cache: true` response cache for exact reruns
- `X-OpenRouter-Cache-TTL: 300` short default response-cache TTL
- `X-OpenRouter-Experimental-Metadata: enabled` for routing metadata
- `include_response_headers=True` so LangChain can surface generation metadata when available
- provider request timeout defaults to `45` seconds
- max completion tokens default to `2400`
- live Deep Agent recursion limit defaults to `12` graph steps

Environment toggles:

```bash
OPENROUTER_PROMPT_CACHE=true
OPENROUTER_PROMPT_CACHE_TTL=
OPENROUTER_RESPONSE_CACHE=true
OPENROUTER_RESPONSE_CACHE_TTL_SECONDS=300
OPENROUTER_TIMEOUT_SECONDS=45
OPENROUTER_MAX_COMPLETION_TOKENS=2400
```

Leave `OPENROUTER_PROMPT_CACHE_TTL` empty for the provider default 5-minute prompt cache. Set it to `1h` only for longer demo/review sessions where the higher cache-write price is worth it.

When LangChain exposes token usage metadata, the CLI writes:

```text
.agent-permit/runs/<run_id>/openrouter-usage.json
```

The file tracks model call count, input/output/total tokens, cached tokens, cache-write tokens, cache hit ratio, and generation IDs.
Live Deep Agent reports must end with `END_OF_REPORT`; the CLI strips this sentinel before writing the report and fails the run if the sentinel is missing.

## Notes

The verified OpenRouter model IDs are:

- `anthropic/claude-sonnet-4.6`
- `openai/gpt-5.5`

Do not use `anthropic/claude-4.6-sonnet`; the OpenRouter model list currently exposes the Sonnet route as `anthropic/claude-sonnet-4.6`.

## Sources

- OpenRouter Claude Sonnet 4.6: https://openrouter.ai/anthropic/claude-sonnet-4.6
- OpenRouter GPT-5.5: https://openrouter.ai/openai/gpt-5.5
- OpenRouter chat completion API: https://openrouter.ai/docs/api/api-reference/chat/send-chat-completion-request
- OpenRouter prompt caching: https://openrouter.ai/docs/guides/best-practices/prompt-caching
- OpenRouter response caching: https://openrouter.ai/docs/guides/features/response-caching
