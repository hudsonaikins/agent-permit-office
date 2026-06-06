# Agent Permit Office Starter Scope and Architecture

Research date: 2026-06-06

## Problem

AI agents are gaining access to code, shells, cloud credentials, MCP servers, SaaS APIs, memory, and local files. Existing security review patterns ask whether code or prompts look acceptable, but they often miss the operational question:

What can this agent actually do once it starts acting?

Agent Permit Office issues an evidence-backed permit before an agent receives tools, credentials, memory, or production access.

## Product Thesis

Before an AI agent gets tools, prove:

- what it can access
- what it can change
- what data it can expose
- what external channels it can use
- what prompts, skills, configs, and MCP servers shape its behavior
- what human approvals are required
- what needs to be reduced before the agent can be trusted

## Why This Is Timely

Market and standards signals:

- NIST is exploring identity and authorization controls for software and AI agents.
- NSA released MCP security guidance because MCP adoption is accelerating in sensitive business workflows.
- OWASP highlights agentic skills as an under-protected execution layer.
- CSA survey data says many enterprises report unknown agents and agent-related incidents.
- CSA also frames agent authorization as an "understand -> align -> authorize" problem, not just static permission checking.

This creates a credible wedge: teams need agent visibility, permission review, and evidence before production rollout.

## Initial User

Primary early user:

- security-minded developer or platform engineer adopting Claude Code, Cursor, Codex, LangChain, LangGraph, MCP, or custom agents.

Secondary early user:

- small security team asked to review internal agent deployments.

Do not start with Fortune 500 governance workflows. Start with developer-local review and CI evidence.

## MVP Promise

Run:

```bash
agent-permit scan /path/to/agent-repo
```

Output:

- `agent-bom.json`: discovered agents, prompts, MCP servers, tools, credentials references, shells, memory files.
- `risk-report.md`: human-readable findings with severity, rationale, evidence, and recommendations.
- `permit.yaml`: approve/block/needs-review decision plus required conditions.
- optional `patches/`: suggested diffs, never applied without approval.

## MVP Scan Targets

Local repo/config scan:

- `AGENTS.md`
- `CLAUDE.md`
- `.mcp.json`
- `mcp.json`
- `claude_desktop_config.json`
- Cursor/Windsurf/Codex config files where detectable
- `pyproject.toml`, `package.json`, lockfiles
- LangChain/LangGraph/Deep Agents code patterns
- OpenAI Agents SDK patterns
- shell hooks/scripts
- `.env.example` and env var references, but not secret values
- prompt/skill/memory directories

MVP should not:

- connect to real SaaS accounts
- mutate files by default
- run untrusted shell commands by default
- execute discovered MCP tools
- claim exploit proof unless the exploit test actually ran in a sandbox

## Findings Model

Each finding should have:

- `id`
- `title`
- `severity`: `critical`, `high`, `medium`, `low`, `info`
- `category`: `tool_access`, `credential_scope`, `prompt_risk`, `mcp_risk`, `filesystem_risk`, `network_risk`, `memory_risk`, `supply_chain`, `runtime_policy`
- `evidence`: file path, line range, config key, package, or command result
- `risk`: what could happen
- `recommendation`: concrete fix
- `confidence`: `high`, `medium`, `low`
- `requires_human_review`: boolean

## Permit Model

Permit statuses:

- `approved`: low risk, no blocking issues.
- `approved_with_conditions`: allowed only after listed controls.
- `needs_review`: human must decide.
- `blocked`: unsafe by policy.

Permit fields:

- agent name
- owner
- purpose
- discovered tools
- discovered credentials/scopes
- allowed actions
- forbidden actions
- required approvals
- expiry date
- findings summary
- evidence bundle path

## Deep Agents Architecture

Coordinator:

- Owns the task plan.
- Calls scanner subagents.
- Reads structured findings.
- Writes final permit.
- Does not do raw scanning itself unless task is trivial.

Subagents:

- `repo-inspector`: scans source files and agent framework usage.
- `mcp-inspector`: scans MCP server configs and tool descriptions.
- `prompt-skill-inspector`: reviews `AGENTS.md`, skills, memory, hidden instruction risks.
- `credential-inspector`: finds env var and token scope references without printing secret values.
- `risk-modeler`: converts raw findings into attack paths and permit conditions.
- `critic`: reviews final permit for missing evidence and overclaims.

Tools:

- deterministic file scanners
- JSON/TOML/YAML parsers
- package manifest parsers
- regex matchers for known risky patterns
- optional sandboxed probe tools later

Filesystem:

- Use Deep Agents `FilesystemBackend` for working files.
- Store all run outputs under `.agent-permit/runs/<run_id>/`.
- Keep scanner raw outputs separate from synthesized report.

Human-in-the-loop:

- Required before write operations.
- Required before shell execution.
- Required before outbound network probes.
- Required before remediation patches.

LangSmith:

- Optional in local MVP.
- Recommended once agent exists.
- Use tracing to inspect tool calls and subagent paths.
- Use evals to test whether the agent flags known bad sample repos.

## Architecture Options

Option 1: Deterministic CLI only.

- Pros: easiest to trust, fast, cheap.
- Cons: misses synthesis and investigation value; not good Deep Agents practice.

Option 2: Deep Agent as scanner.

- Pros: fastest demo.
- Cons: risky and unreliable; agent may miss exact config details or overclaim.

Option 3: Deep Agent as investigator over deterministic scanners.

- Pros: best fit. Deterministic evidence plus agentic synthesis.
- Cons: more engineering than prompt-only demo.

Chosen: Option 3.

## Starter Build Plan

Phase 0: Research and docs.

- Capture LangChain/Deep Agents architecture.
- Define MVP scope and non-goals.
- Create sample risky agent repo fixtures.

Phase 1: Deterministic scanner CLI.

- Python project with `uv`.
- Parse repo tree.
- Detect agent files/configs.
- Emit `agent-bom.json`.
- Add tests around fixtures.

Phase 2: Deep Agent wrapper.

- Add `create_deep_agent`.
- Give agent narrow tools that call scanners.
- Add subagents with structured outputs.
- Emit `risk-report.md` and `permit.yaml`.

Phase 3: Red-team simulation.

- Add sample malicious configs.
- Add prompt injection and tool poisoning test fixtures.
- Add evaluator checks: expected findings and expected permit status.

Phase 4: CI/GitHub app.

- Run on PR.
- Fail or warn based on policy.
- Upload report artifact.

Phase 5: Runtime expansion.

- Add cloud/OAuth/SaaS scope scanning.
- Add runtime trace import.
- Add approval workflow and team dashboard.

## Recommended Initial Repo Shape

```text
agent-permit-office/
  README.md
  docs/
    research/
      langchain-deep-agents-architecture.md
    agent-permit-office-scope.md
  src/
    agent_permit/
      __init__.py
      cli.py
      scanners/
        repo.py
        mcp.py
        prompts.py
        credentials.py
      agent/
        graph.py
        prompts.py
        subagents.py
      models.py
      report.py
  tests/
    fixtures/
      safe-agent/
      risky-mcp-agent/
      poisoned-instructions/
    unit/
    integration/
  pyproject.toml
```

## Risks

Technical risks:

- Agent overclaims findings not backed by files.
- Agent executes unsafe tools while analyzing unsafe tools.
- MCP configs are too varied for early robust parsing.
- New agent frameworks appear faster than rules can update.

Product risks:

- Market may prefer full enterprise agent security platforms.
- Developer-local wedge may not convert to paid product.
- Security teams may require integrations before caring.

Mitigation:

- Evidence-first reports.
- No unsafe execution in MVP.
- Fixture-based tests.
- Strong "permit" language: approve, condition, review, block.
- Start with local/CI use, not enterprise dashboard.

## Decision

Build small first:

- deterministic scanner
- deep-agent investigator
- permit report
- sample risky fixtures

Defer:

- hosted app
- real SaaS integrations
- runtime monitoring
- managed deployment
- auto-remediation

Deep Agents should be used as the investigation coordinator, not as the source of truth. Source of truth comes from parsed files, tool manifests, config scans, and explicit evidence.

