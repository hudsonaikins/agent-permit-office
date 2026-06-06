# Deep Agent Investigator

Sprint 5 adds the required LangChain Deep Agents investigation layer on top of deterministic scan artifacts.

## Boundary

The scanner remains source of truth.

The Deep Agent investigator may read only this bounded evidence set:

- `summary.md`
- `risk-report.md`
- `permit.yaml`
- `raw-findings.json`
- `graph-paths.json`
- `controls.json`
- `agent-bom.json`

It does not read repository files directly, execute shell commands, launch MCP servers, run workflows, fetch secrets, or write repo files.

## Typed Evidence Tools

The Deep Agent surface includes typed read-only helpers:

- `get_finding(identifier)`
- `find_paths(source_category, sink_category)`
- `get_agent_bom()`
- `get_mcp_servers()`
- `get_credential_refs()`
- `explain_rule(rule_id)`

These tools read structured scan artifacts only. They do not open arbitrary repo files or execute anything.

## Live Deep Agents Investigation

Run a scan:

```bash
uv run agent-permit scan tests/fixtures/risky-ci-agent --run-id demo-investigate
```

Install the optional runtime extra and provide OpenRouter credentials:

```bash
export OPENROUTER_API_KEY=<key>
```

Run the default MVP model, Claude Sonnet 4.6 through OpenRouter:

```bash
uv run --extra deep-agent agent-permit investigate \
  tests/fixtures/risky-ci-agent/.agent-permit/runs/demo-investigate \
  --agent-recursion-limit 12
```

Output:

```text
tests/fixtures/risky-ci-agent/.agent-permit/runs/demo-investigate/agent-investigation.md
tests/fixtures/risky-ci-agent/.agent-permit/runs/demo-investigate/openrouter-usage.json
```

The `investigate` command defaults to the live Deep Agent path. Without `OPENROUTER_API_KEY`, it fails before a report is written.
`openrouter-usage.json` is written when LangChain exposes usage metadata from the provider response.

Override with the explicit default alias:

```bash
uv run --extra deep-agent agent-permit investigate \
  tests/fixtures/risky-ci-agent/.agent-permit/runs/demo-investigate \
  --model openrouter:sonnet-4.6
```

Escalate to GPT-5.5 through OpenRouter when evals or citation quality justify the extra cost:

```bash
uv run --extra deep-agent agent-permit investigate \
  tests/fixtures/risky-ci-agent/.agent-permit/runs/demo-investigate \
  --model openrouter:gpt-5.5
```

The integration uses `deepagents.create_deep_agent` with:

- a `StateBackend`, not a local filesystem backend
- filesystem permissions that deny built-in read/write access to `/**`
- custom evidence tools only
- specialist subagent specs for MCP, prompt, policy, and citation review
- OpenRouter prompt caching, response caching, and sticky session routing enabled by default
- request timeout, max completion tokens, and graph recursion limit to bound live spend
- `END_OF_REPORT` sentinel check so truncated live reports fail instead of passing citation checks accidentally

## Offline Deterministic Fallback

For tests, CI, and no-key local debugging, write the deterministic citation report explicitly:

```bash
uv run agent-permit investigate \
  tests/fixtures/risky-ci-agent/.agent-permit/runs/demo-investigate \
  --deterministic-only
```

This fallback is not the MVP product path. It exists to keep scanner validation repeatable without live model spend.

## Optional Phoenix Tracing

Phoenix is the preferred local observability path for now.

Start the local Phoenix server:

```bash
uv run --extra phoenix python -m phoenix.server.main serve
```

Then trace a live Deep Agent run:

```bash
uv run --extra deep-agent --extra phoenix agent-permit investigate \
  tests/fixtures/risky-ci-agent/.agent-permit/runs/demo-investigate \
  --phoenix
```

Tracing is off by default. The `--phoenix` flag initializes Phoenix/OpenTelemetry before the Deep Agent runtime is created.

Evidence tools emit local OpenTelemetry spans when tracing is available. Span attributes include:

- `agent_permit.tool.name`
- `agent_permit.scan_run_id`
- `agent_permit.permit_status`
- `agent_permit.tool.input.arg_count`
- `agent_permit.tool.input.kwarg_keys`
- `agent_permit.tool.output_chars`
- `agent_permit.tool.output_lines`
- `agent_permit.tool.error_type`

## Optional LangSmith Tracing

Set environment variables:

```bash
export LANGSMITH_TRACING=true
export LANGSMITH_API_KEY=<your-api-key>
export LANGSMITH_PROJECT=agent-permit-office
```

Or request tracing for a live Deep Agent run:

```bash
uv run --extra deep-agent agent-permit investigate \
  tests/fixtures/risky-ci-agent/.agent-permit/runs/demo-investigate \
  --langsmith
```

Tracing is off by default.

## Citation Critic

The critic checks:

- unsupported citation IDs, such as `[finding:not-real]`
- deterministic scanner rule IDs that are mentioned but not present in artifacts
- known rule IDs mentioned without `[rule:<rule_id>]` citation

Reports fail the command if the citation check fails.

## Why This Shape

Deep Agents are useful here because they provide planning, context management, and subagent delegation over a bounded task. The product risk is giving the agent direct repo or tool access too early. This implementation makes Deep Agents the investigation path while keeping them behind deterministic artifacts until the scanner and evidence contract are stable.

## Sources

- [LangChain Deep Agents overview](https://docs.langchain.com/oss/python/deepagents/overview)
- [Deep Agents `create_deep_agent` reference](https://reference.langchain.com/python/deepagents/graph/create_deep_agent)
- [Deep Agents backends](https://docs.langchain.com/oss/python/deepagents/backends)
- [Deep Agents permissions](https://docs.langchain.com/oss/python/deepagents/permissions)
- [Phoenix OTEL setup](https://www.arize.com/docs/phoenix/tracing/how-to-tracing/setup-tracing/setup-using-phoenix-otel)
- [OpenInference LangChain instrumentation](https://arize-ai.github.io/openinference/python/instrumentation/openinference-instrumentation-langchain/)
- [LangSmith tracing with LangChain](https://docs.langchain.com/langsmith/trace-with-langchain)
- [OpenRouter model decision](openrouter-model-decision.md)
