# Tech Stack Analysis: LangChain, Deep Agents, and LangSmith

Research date: 2026-06-06

## Purpose

This note defines the technical stack for Agent Permit Office and decides which LangChain/Deep Agents/LangSmith features should be enabled first.

## Short Answer

Agent Permit Office should start as a Python CLI with deterministic scanners. Deep Agents should be added as an investigation coordinator after scanners produce reliable evidence.

Do not start with hosted LangSmith Deployment, Managed Deep Agents, async subagents, MCP execution, or shell execution. Those are powerful later, but they add trust and operations complexity before the product proves its core permit workflow.

## What Deep Agents Is

Deep Agents is an agent harness, not a standalone product server.

It wraps LangChain's normal model/tool loop with built-in capabilities for:

- planning with `write_todos`
- virtual filesystem context
- subagent delegation
- long-run context compression
- memory
- skills
- filesystem permissions
- human approval
- sandbox execution when a sandbox backend is used
- streaming
- model/provider flexibility

LangChain describes it as a standalone library built on LangChain agent building blocks and using LangGraph runtime features for durable execution, streaming, and human-in-the-loop workflows.

Source: https://docs.langchain.com/oss/python/deepagents/overview

## Stack Layers

### Local Product Layer

This is our code.

- Python package: `agent_permit`
- CLI: `agent-permit scan <repo>`
- deterministic scanners
- report writer
- fixtures and tests
- later: Deep Agent coordinator

### LangChain Layer

Role: model/tool framework.

Use for:

- tool definitions
- structured tool inputs/outputs
- model provider abstraction
- middleware hooks
- MCP adapters, later

Source: https://docs.langchain.com/oss/python/langchain/overview

### LangGraph Layer

Role: stateful runtime.

Use for:

- graph state
- checkpointers
- interrupts
- durable execution
- streaming
- long-running runs

Source: https://docs.langchain.com/oss/python/langgraph/durable-execution

### Deep Agents Layer

Role: opinionated agent harness.

Use for:

- planner/coordinator
- sync scanner subagents
- file-backed intermediate artifacts
- final permit synthesis
- human approval before risky actions

Source: https://docs.langchain.com/oss/python/deepagents/overview

### LangSmith Layer

Role: observability, evaluation, deployment, and managed operations.

Use later for:

- trace inspection
- eval datasets
- dashboards
- annotation queues
- deployment
- Context Hub
- Engine
- LLM Gateway

Sources:

- Observability: https://docs.langchain.com/langsmith/observability-quickstart
- Evaluation: https://docs.langchain.com/langsmith/evaluation-approaches
- Deployment: https://docs.langchain.com/langsmith/deployment

## Microservices and Managed Services

Deep Agents local mode does not require microservices. It is just a Python library running in our process.

If deployed through LangSmith or Agent Server, the architecture becomes service-based.

### Local MVP

Services:

- none

Runtime:

- local Python process
- local filesystem
- model provider API, only if Deep Agent mode is used

### LangSmith Cloud Deployment

Services:

- LangSmith control plane
- Agent Server runtime
- trace/eval storage
- model provider APIs
- optional sandbox service
- optional MCP servers

LangSmith Cloud is managed by LangChain and can deploy from GitHub or `langgraph deploy`.

Source: https://docs.langchain.com/langsmith/deployment

### Standalone Agent Server

Services:

- Agent Server container
- PostgreSQL
- Redis
- optional MongoDB checkpointer
- optional LangSmith tracing endpoint

Postgres stores assistants, threads, runs, thread state, long-term memory, and background task queue state. Redis enables streaming from background runs.

Source: https://docs.langchain.com/langsmith/deploy-standalone-server

### Full Self-Hosted LangSmith

Services:

- LangSmith control plane
- LangSmith data plane
- Agent Servers
- backing databases/caches/object stores, depending deployment

This is Enterprise-level and out of scope now.

## Deep Agents Elements Available To Us

### Models

Available:

- Anthropic
- OpenAI
- Google Gemini
- OpenRouter
- Fireworks
- Baseten
- Ollama
- any LangChain-supported chat model

Decision:

- Start with explicit model config, not default model behavior.
- Use one strong model for synthesis.
- Use deterministic scanners for truth.

### Built-In Tools

Available:

- `write_todos`
- `ls`
- `read_file`
- `write_file`
- `edit_file`
- `glob`
- `grep`
- `execute`, only with shell/sandbox backend
- `task`, when subagents exist
- async task tools, when async subagents exist

Decision:

- Turn on `write_todos`.
- Turn on filesystem only for run artifacts, not target repo.
- Turn off `execute` in MVP.
- Turn on `task` when Deep Agent wrapper is added.

### Filesystem Backends

Available:

- `StateBackend`
- `FilesystemBackend`
- `LocalShellBackend`
- `StoreBackend`
- `CompositeBackend`
- `ContextHubBackend`
- sandbox backends
- custom backend

Decision:

- Phase 1 scanner CLI: no Deep Agent backend needed.
- Phase 2 Deep Agent: use `FilesystemBackend` rooted in `.agent-permit/runs/<run_id>/`.
- Do not mount target repo as agent filesystem. Scanner tools read target repo and return structured evidence.
- Defer `StoreBackend`, `CompositeBackend`, and `ContextHubBackend`.

### Subagents

Available:

- sync declarative subagents
- compiled subagents
- async subagents over Agent Protocol/LangSmith Deployment

Decision:

- Turn on sync declarative subagents in Phase 2.
- Defer compiled subagents until one scanner needs a custom graph.
- Defer async subagents until scans become long-running or remote.

### Middleware

Available provider-agnostic middleware includes:

- summarization
- human-in-the-loop
- model call limits
- tool call limits
- model fallback
- PII detection
- todo list
- LLM tool selector
- tool retry
- model retry
- tool emulator
- context editing
- shell tool
- file search
- filesystem
- subagent

Source: https://docs.langchain.com/oss/python/langchain/middleware/built-in

Decision:

- Turn on model call limit.
- Turn on tool call limit.
- Turn on human-in-the-loop before writes/remediation.
- Keep summarization through Deep Agents default.
- Defer PII detection to report export or provider gateway.
- Turn off shell tool.
- Turn off LLM tool selector until tool count becomes large.
- Turn off model fallback until reports need reliability against provider failure.

### Permissions and Human Approval

Available:

- filesystem allow/deny/interrupt rules
- `interrupt_on` for tool calls
- LangGraph interrupts with checkpointing

Decision:

- Deny agent reads outside run output.
- Interrupt on `write_file` and `edit_file`.
- Do not expose destructive scanner tools.
- Require explicit user approval for patches, shell execution, network probes, and SaaS/cloud connections.

Sources:

- https://docs.langchain.com/oss/python/deepagents/permissions
- https://docs.langchain.com/oss/python/deepagents/human-in-the-loop

### MCP

Available:

- load MCP tools through `langchain-mcp-adapters`
- stdio and HTTP server transports
- interceptors for runtime context and request control

Decision:

- Scan MCP configs as product input.
- Do not execute target MCP tools during MVP.
- Defer using MCP tools inside our own agent.
- Later, allow trusted read-only MCP tools only through explicit allowlist and interceptors.

Source: https://docs.langchain.com/oss/python/langchain/mcp

### Memory and Skills

Available:

- memory files
- reusable skills
- Context Hub managed skills/agents

Decision:

- Turn off long-term memory in MVP.
- Turn off skills in MVP.
- Store policies in versioned repo files first.
- Later use skills for scanner workflows and Context Hub for staging/production prompts.

Source: https://docs.langchain.com/langsmith/use-the-context-hub

### LangSmith Tracing

Available:

- automatic tracing
- trace inspection
- dashboards
- feedback
- annotation queues
- eval datasets

Decision:

- Optional local tracing in Phase 2.
- Turn on before demos.
- Use one LangSmith project: `agent-permit-office-dev`.
- Do not require LangSmith for deterministic scanner CLI.

Sources:

- https://docs.langchain.com/langsmith/observability-quickstart
- https://docs.langchain.com/langsmith/dashboards
- https://docs.langchain.com/langsmith/annotation-queues

### LangSmith Deployment

Available:

- Cloud Deployment
- Standalone Agent Server
- Self-hosted platform
- assistants, threads, runs
- streaming
- HITL
- MCP/A2A endpoints
- RemoteGraph

Decision:

- Turn off for MVP.
- Use local CLI first.
- Consider Cloud Deployment after we have repeatable scans and an interactive demo.
- Consider standalone Agent Server only if we need to host the runtime ourselves.

Source: https://docs.langchain.com/langsmith/deployment

### Managed Deep Agents

Available:

- private preview hosted deep-agent runtime in LangSmith
- agent files, threads, streaming, inspection

Decision:

- Turn off now.
- Revisit after local agent works.
- Private preview status makes it bad for first architecture.

Source: https://docs.langchain.com/langsmith/deploy-managed-deep-agent

### LLM Gateway

Available:

- private beta proxy between clients and LLM providers
- provider secret storage
- spend limits
- PII redaction
- secrets redaction
- trace continuity
- audit logs

Decision:

- Turn off now.
- Revisit if we build hosted product or team demo with multiple model keys.
- For local MVP, keep provider key in `.env` and do not commit secrets.

Source: https://docs.langchain.com/langsmith/llm-gateway

### LangSmith Engine

Available:

- beta trace analysis workflow
- clusters recurring issues
- proposes fixes
- generates evaluators and dataset examples

Decision:

- Turn off now.
- Turn on only after we have enough real traces and evals.
- Later, useful for improving Agent Permit's own false positives/false negatives.

Source: https://docs.langchain.com/langsmith/engine

## Recommended Toggle Matrix

| Capability | MVP | Later | Reason |
|---|---:|---:|---|
| Python CLI | On | On | Fastest proof of product value. |
| Deterministic scanners | On | On | Source of truth. |
| Deep Agent coordinator | Off in Phase 1 | On in Phase 2 | Needs scanner evidence first. |
| Sync subagents | Off in Phase 1 | On in Phase 2 | Good for investigation decomposition. |
| Async subagents | Off | Later | Adds server/runtime complexity. |
| FilesystemBackend | Off in Phase 1 | On in Phase 2 | Useful for run artifacts. |
| Agent target-repo file access | Off | Off by default | Product should not let agent roam target repo. |
| Shell execution | Off | Conditional | High risk. Only sandboxed and approved. |
| MCP execution | Off | Conditional | We scan MCP as risk input before using it. |
| MCP config scanning | On | On | Core product surface. |
| HITL | Off in scanner CLI | On with agent | Required before writes/actions. |
| LangSmith tracing | Optional | On | Great for debugging/demos, not required for scanner. |
| LangSmith evals | Off | On | Needs fixtures and trace history first. |
| LangSmith Deployment | Off | Later | Host only after local workflow works. |
| Managed Deep Agents | Off | Later | Private preview; avoid dependency. |
| Context Hub | Off | Later | Use repo files until prompts/policies mature. |
| LLM Gateway | Off | Later | Private beta; useful when hosted/team usage begins. |
| Engine | Off | Later | Needs production traces and evals. |

## Proposed Initial Tech Stack

Language:

- Python 3.11+

Package manager:

- `uv`

Core libraries:

- `pydantic` for findings and permit schemas
- `typer` or `click` for CLI
- `rich` for readable CLI output
- `tomli` or stdlib TOML depending Python version
- `pyyaml` for YAML configs
- `pytest` for fixtures
- `ruff` for formatting/lint

LangChain stack, Phase 2:

- `deepagents`
- `langchain`
- `langgraph`
- `langsmith`
- one model provider package

File outputs:

- `.agent-permit/runs/<run_id>/agent-bom.json`
- `.agent-permit/runs/<run_id>/raw-findings.json`
- `.agent-permit/runs/<run_id>/risk-report.md`
- `.agent-permit/runs/<run_id>/permit.yaml`

## Proposed Deep Agent Shape

Coordinator:

- Prompt: issue evidence-backed permits, never invent findings.
- Tools: `run_repo_scan`, `run_mcp_scan`, `run_prompt_scan`, `read_scan_artifact`, `write_report`.
- No direct shell.
- No target repo filesystem access.

Subagents:

- `repo-inspector`: analyzes structured repo scan output.
- `mcp-inspector`: analyzes MCP config and tool risk output.
- `prompt-skill-inspector`: analyzes instructions, skills, hooks, and memory risks.
- `credential-inspector`: analyzes env var references and overbroad scope hints.
- `risk-modeler`: maps findings into attack paths and permit conditions.
- `critic`: checks final permit for unsupported claims.

Backend:

- `FilesystemBackend(root_dir=".agent-permit/runs/<run_id>")`

Permissions:

- allow read/write in `/`
- no mounted target repo
- interrupt writes when running interactively

Model:

- explicit configurable model, no implicit default.

## What We Should Build Next

1. Scaffold Python package.
2. Add Pydantic models for `Finding`, `AgentBom`, `Permit`.
3. Add deterministic scanner for files/config discovery.
4. Add fixtures:
   - safe agent
   - risky MCP agent
   - poisoned instruction agent
5. Add CLI output.
6. Add tests.
7. Only then add Deep Agent coordinator.

## Decision

Use LangChain/Deep Agents as the investigation and synthesis layer, not as the scanning engine.

Turn on only the features that make the agent safer and more inspectable:

- deterministic scanners
- structured outputs
- local run artifacts
- sync subagents
- HITL
- tracing
- evals after fixtures exist

Turn off features that let the agent act before the product can explain its own risk:

- shell execution
- MCP execution
- target repo filesystem access
- managed deployment
- async subagents
- persistent memory
- auto-remediation

