# LangChain Deep Agents Architecture Research

Research date: 2026-06-06

## Purpose

This note explains how LangChain Deep Agents, LangGraph, and LangSmith fit together, then maps the pieces to Agent Permit Office.

## Source Base

Primary sources:

- Deep Agents overview: https://docs.langchain.com/oss/python/deepagents/overview
- Deep Agents quickstart: https://docs.langchain.com/oss/python/deepagents/quickstart
- Deep Agents customization: https://docs.langchain.com/oss/python/deepagents/customization
- Deep Agents subagents: https://docs.langchain.com/oss/python/deepagents/subagents
- Deep Agents async subagents: https://docs.langchain.com/oss/python/deepagents/async-subagents
- Deep Agents context engineering: https://docs.langchain.com/oss/python/deepagents/context-engineering
- Deep Agents backends: https://docs.langchain.com/oss/python/deepagents/backends
- Deep Agents permissions: https://docs.langchain.com/oss/python/deepagents/permissions
- Deep Agents human-in-the-loop: https://docs.langchain.com/oss/python/deepagents/human-in-the-loop
- LangChain overview: https://docs.langchain.com/oss/python/langchain/overview
- LangGraph overview: https://docs.langchain.com/oss/python/langgraph/overview
- LangSmith tracing: https://docs.langchain.com/langsmith/observability-quickstart
- LangSmith eval approaches: https://docs.langchain.com/langsmith/evaluation-approaches
- Managed Deep Agents: https://docs.langchain.com/langsmith/managed-deep-agents-overview
- Official Deep Agents repo: https://github.com/langchain-ai/deepagents
- Official template repo: https://github.com/langchain-ai/deep-agent-template
- From-scratch teaching repo: https://github.com/langchain-ai/deep-agents-from-scratch

Security context sources:

- NIST software and AI agent identity/authorization concept: https://www.nist.gov/news-events/news/2026/02/new-concept-paper-identity-and-authority-software-agents
- NSA MCP security design considerations: https://www.nsa.gov/Press-Room/Press-Releases-Statements/Press-Release-View/Article/4496698/nsa-releases-security-design-considerations-for-ai-driven-automation-leveraging/
- OWASP Agentic Skills Top 10: https://owasp.org/www-project-agentic-skills-top-10/
- CSA AI agent visibility survey: https://cloudsecurityalliance.org/press-releases/2026/04/21/new-cloud-security-alliance-survey-reveals-82-of-enterprises-have-unknown-ai-agents-in-their-environments
- CSA agentic authorization article: https://cloudsecurityalliance.org/blog/2026/03/19/rethinking-authorization-for-the-age-of-agentic-ai

## Stack Model

LangChain:

- Agent framework.
- Gives model abstraction, tool abstraction, middleware, messages, structured output, MCP adapters, and `create_agent`.
- Good for light agents where the standard model-tool loop is enough.

LangGraph:

- Runtime and orchestration layer.
- Gives durable execution, persistence, checkpointers, memory, interrupts, streaming, subgraphs, and production deployment.
- Best when the process must survive long runs, partial state, approval gates, retries, and human review.

Deep Agents:

- Opinionated agent harness on top of LangChain agents and LangGraph runtime.
- Adds planning, filesystem context, subagents, context management, memory, permissions, sandbox execution, skills, and human approval.
- Best when the job is long, multi-step, tool-heavy, evidence-heavy, or benefits from isolated sub-work.

LangSmith:

- Observability, evaluation, tracing, deployment, and managed runtime layer.
- Gives trace inspection, tool-call visibility, thread state, eval datasets, trajectory evaluation, dashboards, Engine, and Managed Deep Agents.

## Core Deep Agent Primitives

`create_deep_agent(...)` is the main entry point. Current core options include:

- `model`: model string or initialized chat model.
- `tools`: custom tools available to the agent.
- `system_prompt`: user-provided instructions prepended before SDK defaults.
- `middleware`: custom middleware.
- `subagents`: sync, compiled, or async subagent specs.
- `skills`: reusable skill directories.
- `memory`: memory files loaded into the system prompt.
- `permissions`: filesystem path rules.
- `backend`: file storage and execution backend.
- `interrupt_on`: human approval rules for sensitive tools.
- `response_format`: structured output schema.
- `checkpointer`: state persistence.
- `store`: long-term persistence.
- `context_schema`: immutable run-scoped context.

Deep Agents auto-installs useful tools and middleware:

- `write_todos` for planning.
- `ls`, `read_file`, `write_file`, `edit_file`, `glob`, `grep` for filesystem work.
- `execute` when the backend supports sandbox/shell execution.
- `task` when synchronous subagents exist.
- async task tools when async subagents exist.

## Internal Middleware Stack

The official source shows `create_deep_agent` builds a LangChain `create_agent` with a layered middleware stack.

Base stack:

- `TodoListMiddleware`
- `SkillsMiddleware`, when skills are configured
- `FilesystemMiddleware`
- `SubAgentMiddleware`, when sync subagents exist
- summarization middleware
- `PatchToolCallsMiddleware`
- `AsyncSubAgentMiddleware`, when async subagents exist

User middleware goes after this base stack.

Tail stack:

- harness profile middleware
- tool exclusion middleware, if configured
- Anthropic prompt caching middleware
- `MemoryMiddleware`, when memory files are configured
- `HumanInTheLoopMiddleware`, when tool interrupts or permission interrupts exist

Implication: Deep Agents is not a separate new runtime. It is a prebuilt agent harness around LangChain's model-tool loop, executed by LangGraph.

## Subagents

Synchronous subagents:

- Invoked through the `task` tool.
- Receive isolated context.
- Parent sees final answer, not the whole subagent trace.
- Useful for context quarantine and focused evidence collection.
- Can have distinct prompts, tools, models, middleware, skills, permissions, and structured response formats.
- Default `general-purpose` subagent exists unless disabled.

Compiled subagents:

- Let a prebuilt LangGraph graph or LangChain agent run as a subagent.
- Useful when part of the workflow needs deterministic orchestration or a custom graph.

Async subagents:

- Run in the background through Agent Protocol-compatible servers or LangSmith Deployments.
- Supervisor can start, check, update, cancel, and list tasks.
- Useful for long-running and parallel workstreams.
- Preview feature; API stability risk.

Agent Permit Office implication:

- Start with sync subagents for local scan phases.
- Add async subagents later for long-running cloud scans or exploit simulations.
- Use structured responses for scanner subagents so parent can reliably merge findings.

## Filesystem, Backends, and Context

Deep Agents uses a virtual filesystem to store intermediate work outside the message context.

Built-in backend options include:

- `StateBackend`: default thread-scoped backend stored in LangGraph state.
- `FilesystemBackend`: local disk persistence.
- `LocalShellBackend`: local shell-backed filesystem/execution.
- `StoreBackend`: LangGraph store-backed persistence.
- `CompositeBackend`: route path prefixes to different backends.
- `ContextHubBackend`: managed LangSmith context storage.
- sandbox backends: isolated execution plus filesystem.

Context engineering pattern:

- Put large scan outputs in files.
- Keep messages concise.
- Subagents write detailed findings to files.
- Coordinator reads only summaries and selected evidence.
- Use long-term memory only for persistent conventions, not raw scan outputs.

Agent Permit Office implication:

- MVP should use `FilesystemBackend` rooted in a `.agent-permit/runs/<run_id>/` workspace.
- Scanner outputs should be files: `agent-bom.json`, `mcp-findings.json`, `repo-findings.json`, `risk-report.md`, `permit.yaml`.
- Later production version can route reports to S3/Postgres through a custom backend or app service, not direct agent memory.

## Permissions and HITL

Deep Agents supports declarative filesystem permissions:

- operations: `read` or `write`
- paths: POSIX glob patterns beginning with `/`
- mode: `allow`, `deny`, or `interrupt`

Limits:

- Permissions apply only to built-in filesystem tools.
- They do not automatically cover custom tools, MCP tools, or sandbox `execute`.
- For custom tools, policy must live inside the tool implementation or backend hooks.

Human-in-the-loop:

- `interrupt_on` can pause tool calls for approve/edit/reject/respond.
- Requires checkpointer.
- Applies to main agent; subagents can inherit or override.
- Good for file writes, shell execution, external network calls, and remediation patches.

Agent Permit Office implication:

- The product being built is about permits, but our own deep agent still needs permits.
- MVP should avoid write/destructive tools by default.
- Any shell execution should be opt-in and sandboxed.
- Any remediation patch should require approval.

## MCP

LangChain supports MCP via `langchain-mcp-adapters`.

Architecture:

- `MultiServerMCPClient` loads tools from one or more MCP servers.
- Supports stdio and HTTP transports.
- Useful for connecting external tools without hand-writing every integration.

Security implication:

- MCP tool loading is also part of the attack surface.
- Agent Permit Office should treat MCP configs as scan targets first.
- Product should not blindly execute arbitrary MCP tools during assessment.

## Streaming and UI

Deep Agents expose top-level streams and subagent streams.

Useful UI streams:

- coordinator messages
- subagent lifecycle
- subagent messages
- tool calls
- tool results
- nested subagent activity

Agent Permit Office implication:

- MVP CLI can print phase progress.
- Later web app should visualize a "permit investigation tree": coordinator at top, repo/MCP/IAM/prompt/red-team subagents below.

## LangSmith Role

Use LangSmith for:

- tracing all agent and subagent steps
- debugging tool misuse
- checking cost and latency
- eval datasets
- trajectory evaluation: did the agent call expected tools in expected order?
- final response evaluation: is permit rationale correct?
- single-step evaluation: did scanner choose the right tool?

Managed Deep Agents:

- Private preview.
- Lets users keep agent project files locally, deploy to LangSmith, run through REST API, inspect traces/files/tool calls/runtime state.
- Supports managed file tree for instructions, skills, subagents, tools, and runtime files.
- Useful later, but not necessary for MVP.

## Official Repo and Template Findings

The official `langchain-ai/deepagents` repo has examples:

- `deep_research`: multi-step research with Tavily, one research subagent, explicit planning, report files, citation consolidation.
- `text-to-sql-agent`: local CLI pattern using `FilesystemBackend`, memory via `AGENTS.md`, skills, and read-only SQL tools.
- `deploy-coding-agent`: deployable coding agent with sandbox.
- `deploy-content-writer`: deployable content writer with per-user memory.
- `deploy-mcp-docs-agent`: prompt-only docs-first agent using MCP tools.
- `deploy-gtm-agent`: coordinator with sync and async subagents.
- `async-subagent-server`: self-hosted Agent Protocol server and supervisor.
- `better-harness`: eval-driven outer-loop optimization of a deep agent harness.

The official `deep-agent-template` gives:

- `pyproject.toml`, `langgraph.json`, `src/deep_agent/graph.py`, starter tests, `Makefile`.
- Two subagents: researcher and critic.
- HITL interrupts on `execute` and `write_file`.
- LangSmith sandbox backend wrapper.

The `deep-agents-from-scratch` repo teaches the underlying patterns:

- TODO planning.
- virtual filesystem in graph state.
- context isolation through subagent delegation.
- final full research agent.

## Best Reference Pattern for Agent Permit Office

Use a hybrid of:

- `text-to-sql-agent`: local CLI, explicit safe tools, filesystem backend, memory/skills.
- `deep_research`: coordinator/subagent research pattern, report files, explicit workflow.
- `deep-agent-template`: deployable graph layout, tests, LangGraph dev server option.
- `async-subagent-server`: only after MVP, for long-running cloud or sandbox tasks.

Do not start with Managed Deep Agents. It is useful later, but private-preview constraints and deployment overhead will slow learning.

## Architecture Lesson

For Agent Permit Office, the deep agent should not be allowed to roam freely. It should coordinate specialized deterministic scanners.

Recommended split:

- Deterministic tools scan files/configs and return structured findings.
- Deep agent plans, delegates, prioritizes, writes the permit report, and asks for approval before risky action.
- Subagents get narrow tools and narrow prompts.
- Filesystem stores evidence and reports.
- LangSmith traces become audit evidence.

This preserves the point of Deep Agents without creating a security product that violates its own premise.

