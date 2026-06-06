# Deep Agent Investigator

Sprint 5 adds an optional LangChain Deep Agents layer on top of deterministic scan artifacts.

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

The optional Deep Agent surface now includes typed read-only helpers:

- `get_finding(identifier)`
- `find_paths(source_category, sink_category)`
- `get_agent_bom()`
- `get_mcp_servers()`
- `get_credential_refs()`
- `explain_rule(rule_id)`

These tools read structured scan artifacts only. They do not open arbitrary repo files or execute anything.

## Local Deterministic Investigation

Run a scan:

```bash
uv run agent-permit scan tests/fixtures/risky-ci-agent --run-id demo-investigate
```

Write a cited investigation report without an LLM:

```bash
uv run agent-permit investigate \
  tests/fixtures/risky-ci-agent/.agent-permit/runs/demo-investigate
```

Output:

```text
tests/fixtures/risky-ci-agent/.agent-permit/runs/demo-investigate/agent-investigation.md
```

This path is the default for tests and CI because it requires no API keys.

## Optional Deep Agents Run

Install the optional extra and provide model credentials:

```bash
uv run --extra deep-agent agent-permit investigate \
  tests/fixtures/risky-ci-agent/.agent-permit/runs/demo-investigate \
  --model openai:gpt-5.4
```

The integration uses `deepagents.create_deep_agent` with:

- a `StateBackend`, not a local filesystem backend
- filesystem permissions that deny built-in read/write access to `/**`
- custom evidence tools only
- specialist subagent specs for MCP, prompt, policy, and citation review

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
  --model openai:gpt-5.4 \
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

Deep Agents are useful here because they provide planning, context management, and subagent delegation over a bounded task. The product risk is giving the agent direct repo or tool access too early. This implementation keeps Deep Agents behind deterministic artifacts until the scanner and evidence contract are stable.

## Sources

- [LangChain Deep Agents overview](https://docs.langchain.com/oss/python/deepagents/overview)
- [Deep Agents `create_deep_agent` reference](https://reference.langchain.com/python/deepagents/graph/create_deep_agent)
- [Deep Agents backends](https://docs.langchain.com/oss/python/deepagents/backends)
- [Deep Agents permissions](https://docs.langchain.com/oss/python/deepagents/permissions)
- [LangSmith tracing with LangChain](https://docs.langchain.com/langsmith/trace-with-langchain)
