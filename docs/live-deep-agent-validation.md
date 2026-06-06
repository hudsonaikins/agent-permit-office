# Live Deep Agent Validation

Date: 2026-06-06

## Scope

Validate the required live Deep Agent product path with OpenRouter Claude Sonnet 4.6, prompt/response cache controls, bounded recursion, and deterministic citation checking.

## Fixture

```bash
uv run agent-permit scan tests/fixtures/risky-ci-agent --run-id sprint19-live-risky-ci
```

Scan result:

- permit status: `blocked`
- findings: `4`
- graph paths: `1`
- controls: `5`

## Live Run

```bash
OPENROUTER_TIMEOUT_SECONDS=30 \
OPENROUTER_MAX_COMPLETION_TOKENS=2400 \
uv run --extra deep-agent agent-permit investigate \
  tests/fixtures/risky-ci-agent/.agent-permit/runs/sprint19-live-risky-ci \
  --agent-recursion-limit 20
```

Result:

- exit code: `0`
- citation check: `passed`
- model: `openrouter:anthropic/claude-sonnet-4.6`
- report lines: `97`
- sentinel stripped: yes
- generated artifact: `agent-investigation.md`
- generated usage artifact: `openrouter-usage.json`

Usage summary:

```json
{
  "cache_hit_ratio": 0.6836,
  "cache_write_tokens": 0,
  "cached_tokens": 27450,
  "input_tokens": 40156,
  "model_calls": 4,
  "output_tokens": 2026,
  "total_tokens": 42182
}
```

Estimated Sonnet 4.6 spend from the usage counters is about `$0.08`, assuming OpenRouter Anthropic pricing of `$3/M` input, `$15/M` output, and `0.1x` input price for cache reads.

## Fixes From Validation

Initial live runs hit LangGraph recursion limits because the model repeatedly called `validate_report_citations` without the required `report_markdown` argument. The CLI already runs deterministic citation validation after the final answer, so the validation tool was removed from the live agent tool surface.

The live path now has these guardrails:

- `--agent-recursion-limit`, default `12`
- `OPENROUTER_TIMEOUT_SECONDS`, default `45`
- `OPENROUTER_MAX_COMPLETION_TOKENS`, default `2400`
- `END_OF_REPORT` sentinel required for live reports
- deterministic citation critic still gates final report success

## Next Validation

Run the same live path with Phoenix enabled, then test one real local repo with Sonnet 4.6. Only use GPT-5.5 after Sonnet produces a citation failure or materially weaker report.
