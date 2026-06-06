# Deterministic Scanners and Model Plan

Research date: 2026-06-06

## Short Answer

Phase 1 uses no LLM.

The first useful product is deterministic:

- parse files
- detect agent/MCP/security surfaces
- emit line-cited findings
- produce permit status

LLMs enter in Phase 2 as synthesis and investigation helpers. They do not become the evidence source.

## Deterministic Scanner Stack

### 1. File Inventory Scanner

Purpose:

- know what files exist
- classify high-signal files
- avoid scanning junk

Tech:

- Python filesystem walk
- `.gitignore` support through `pathspec`
- size/type filters
- binary skip

Finds:

- `AGENTS.md`
- `CLAUDE.md`
- `.mcp.json`
- `mcp.json`
- `claude_desktop_config.json`
- `package.json`
- `pyproject.toml`
- lockfiles
- `.env.example`
- GitHub Actions workflows
- prompt/skill/memory folders

### 2. MCP Config Scanner

Purpose:

- understand MCP server exposure without running servers

Tech:

- JSON parser
- schema-tolerant extraction
- static command/URL analysis

Finds:

- stdio MCP servers
- remote HTTP/SSE MCP servers
- commands like `npx`, `uvx`, `python`, `node`
- env vars passed to MCP servers
- broad local filesystem access hints
- package source and version pinning gaps

Important:

- does not execute MCP servers
- does not load MCP tools
- does not call remote MCP endpoints

### 3. Prompt / Instruction Scanner

Purpose:

- detect unsafe agent instructions and hidden policy bypasses

Tech:

- Markdown/plain-text parser
- exact pattern rules
- risk phrase dictionaries
- line-cited snippets

Finds:

- "ignore prior instructions"
- "do not ask for approval"
- "send secrets"
- "exfiltrate"
- "disable safety"
- auto-approval language
- hidden prompt injection in docs/tool descriptions

### 4. Agent Framework Scanner

Purpose:

- identify agent code and tool wiring

Tech:

- Python `ast` for Python files
- lexical search fallback
- TypeScript parser later
- tree-sitter later for cross-language support

Finds:

- LangChain `create_agent`
- Deep Agents `create_deep_agent`
- LangGraph `StateGraph`
- `MultiServerMCPClient`
- OpenAI Agents SDK patterns
- tool decorators
- tool registration lists
- subagent definitions

### 5. Credential Reference Scanner

Purpose:

- find secrets and scope references without printing secret values

Tech:

- env var access parser
- `.env.example` parser
- config key scanner
- optional external secret scanner later

Finds:

- `GITHUB_TOKEN`
- `SLACK_BOT_TOKEN`
- `AWS_ACCESS_KEY_ID`
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `LANGSMITH_API_KEY`
- broad credential naming like `ADMIN_TOKEN`

Rule:

- record secret variable names and locations only
- never print actual secret values

### 6. Capability Scanner

Purpose:

- map what an agent could do

Tech:

- AST + lexical rules
- manifest parsing

Finds:

- shell execution: `subprocess`, `os.system`, `child_process`
- filesystem writes
- network clients
- browser automation
- email/Slack/message sending
- GitHub write APIs
- cloud SDK clients
- database write paths

### 7. Dependency / Supply Chain Scanner

Purpose:

- identify risky packages and unpinned agent-tool dependencies

Tech:

- package manifest parsing first
- optional integrations later:
  - `osv-scanner`
  - `pip-audit`
  - `npm audit`
  - `gitleaks` or `detect-secrets`
  - `semgrep`

Phase 1:

- parse manifests and flags
- do not depend on external scanner binaries

Phase 2+:

- add adapters for proven scanners when present

### 8. CI / Workflow Scanner

Purpose:

- detect agent workflows with broad automation access

Tech:

- YAML parser
- GitHub Actions workflow parser

Finds:

- `pull_request_target`
- broad `permissions: write-all`
- unchecked script execution
- secrets exposed to PR contexts
- agent-related CI jobs

### 9. Codebase Map Builder

Purpose:

- merge all scanner results into a compact graph

Output:

- `codebase-map.json`
- nodes: files, configs, tools, agents, credentials, MCP servers
- edges: imports, registers, uses env, exposes tool, writes file, sends network

### 10. Evidence Pack Writer

Purpose:

- save tokens and keep reports grounded

Output per finding:

- exact file path
- line numbers
- snippet
- detector rule
- confidence
- risk rationale
- recommended next lookup

## What Counts As Deterministic

Deterministic means:

- same input repo produces same finding
- no model judgment required
- evidence has path and line refs
- rule has an ID
- report can be tested against fixtures

Examples:

- "`.mcp.json` declares a stdio server launched through `npx`"
- "`agent.py` calls `create_deep_agent`"
- "`AGENTS.md` says to bypass approval"
- "`workflow.yml` grants `contents: write`"

Non-deterministic:

- "this agent feels risky"
- "this prompt may be suspicious"
- "model thinks this tool is probably dangerous"

Those belong in LLM synthesis, not scanner truth.

## How The Scanner Determines Risk Without AI

The scanner uses security static analysis methods, not model judgment.

Research basis:

- CodeQL/Pysa-style source-to-sink and taint analysis
- Joern-style graph representation
- Semgrep-style declarative rules
- CaMeL-style trusted control flow vs untrusted data flow
- MCP threat-modeling work around tool poisoning and trust propagation

See: [Static Analysis and Agent Security Research](research/static-analysis-agent-security-research.md).

Core method:

```text
source files/configs
  -> parsers
  -> normalized facts
  -> Agent Capability Graph
  -> attack-path rules
  -> policy decision
  -> evidence-backed finding
```

### 1. Parsers Extract Facts

Parsers convert source material into exact facts.

Examples:

- JSON parser reads `.mcp.json`.
- YAML parser reads GitHub Actions.
- TOML parser reads `pyproject.toml`.
- Python `ast` reads imports, calls, decorators, env var access.
- text scanner reads `AGENTS.md` and prompt files.

Example fact records:

```json
{
  "type": "mcp_server",
  "id": "github-tools",
  "transport": "stdio",
  "command": "npx",
  "args": ["-y", "github-mcp-server"],
  "path": ".mcp.json",
  "line_start": 4,
  "line_end": 12
}
```

```json
{
  "type": "credential_reference",
  "name": "GITHUB_TOKEN",
  "sink": "mcp_server_env",
  "target": "github-tools",
  "path": ".mcp.json",
  "line_start": 10,
  "line_end": 10
}
```

No inference yet. Just facts.

### 2. Normalized Intermediate Representation

All scanners write one common data model.

Entities:

- `Agent`
- `Tool`
- `McpServer`
- `CredentialRef`
- `PromptInstruction`
- `Workflow`
- `FileCapability`
- `NetworkCapability`
- `ShellCapability`
- `ApprovalGate`

This makes different technologies comparable.

LangChain, Claude Code, Cursor, and custom MCP configs all become the same shape:

```text
actor -> capability -> data/control boundary
```

### 3. Agent Capability Graph

The scanner builds a graph from facts.

Example graph:

```text
Agent("repo-agent")
  uses -> McpServer("github-tools")
McpServer("github-tools")
  launched_by -> Command("npx -y github-mcp-server")
McpServer("github-tools")
  receives -> CredentialRef("GITHUB_TOKEN")
CredentialRef("GITHUB_TOKEN")
  grants -> GitHubAccess("unknown_or_broad")
Agent("repo-agent")
  has -> NetworkEgress("slack/send")
Agent("repo-agent")
  lacks -> ApprovalGate("external_send")
```

Graph can answer:

- can this agent read sensitive data?
- can it send data outward?
- can an untrusted tool receive credentials?
- can prompt instructions bypass approval?
- can CI run this with write permissions?

### 4. Attack-Path Rules

Rules compose facts into risk.

Example rule:

```text
IF mcp_server.transport == "stdio"
AND mcp_server.command IN ["npx", "uvx", "python", "node"]
AND package_version IS unpinned_or_unknown
AND mcp_server.receives credential
THEN finding = "Unpinned stdio MCP receives credential"
severity = high
```

Example exfil rule:

```text
IF agent can_read private_code_or_secret
AND agent can_send external_message_or_network
AND no approval_gate covers external_send
THEN finding = "Agent has exfiltration path"
severity = critical
```

Example prompt-bypass rule:

```text
IF prompt contains bypass_approval_phrase
AND agent has write_or_execute_capability
THEN finding = "Prompt can weaken action approval"
severity = high
```

This is same family as:

- Semgrep rules
- CodeQL dataflow queries
- IAM policy analyzers
- Kubernetes policy engines
- attack graph analysis
- taint analysis

Not novel because "AI." Novel angle is applying these static-analysis patterns to agent/MCP capability permits.

### 5. Taint And Sink Analysis

The scanner tracks sensitive sources to dangerous sinks.

Sources:

- env vars
- credentials
- repo files
- private docs
- database URLs
- cloud roles

Sinks:

- MCP server env
- shell execution
- HTTP requests
- Slack/email send
- GitHub write APIs
- file writes
- browser automation

Example:

```text
GITHUB_TOKEN -> MCP env -> unpinned stdio package
```

This becomes high risk even if no exploit ran.

### 6. Control Detection

Risk drops when controls exist.

Controls:

- version pinning
- read-only token
- scoped token
- allowlist
- approval gate
- sandbox
- no outbound network
- disabled shell
- CI read-only permissions

Example:

```text
MCP receives GITHUB_TOKEN + token marked read-only + package pinned
= medium, not high
```

### 7. Severity Scoring

Severity is computed from rule weights.

Inputs:

- capability impact
- sensitivity of data
- trust level of tool/server
- exposure path
- missing controls
- confidence

Simple formula:

```text
severity_score =
  impact
  + exposure
  + credential_sensitivity
  + untrusted_code_risk
  - controls
```

Then map:

- `>= 90`: critical
- `70-89`: high
- `40-69`: medium
- `15-39`: low
- `< 15`: info

### 8. Why This Has Deep Intelligence Without AI

The intelligence is in:

- normalized agent capability model
- static capability graph
- taint/source-sink tracking
- attack-path composition
- policy-as-code
- evidence pack generation

LLM adds communication and investigation. Scanner adds proof.

## LLM Use By Phase

### Phase 1: No LLM

Use no model.

Reason:

- proves scanner value
- cheap
- testable
- no provider setup
- avoids trust problem

### Phase 2: Deep Agent Coordinator

Use one strong tool-calling model.

Role:

- plan review
- call scanner retrieval tools
- compare findings
- explain attack paths
- write `risk-report.md`
- write permit rationale
- ask for missing evidence
- avoid overclaiming

Candidate model families:

- Anthropic Claude Sonnet class through `langchain-anthropic`
- OpenAI GPT-5.x class through `langchain-openai`
- Google Gemini Pro/Flash class through `langchain-google-genai`
- OpenRouter through `langchain-openrouter` for model routing experiments

LangChain/Deep Agents support `provider:model` strings and configured model instances. Source: https://docs.langchain.com/oss/python/deepagents/models

### Phase 3: Cheaper Classifier / Critic

Optional second model.

Uses:

- classify low-risk findings
- summarize long docs
- critique final permit
- reduce cost

Rule:

- never let cheaper model create final high-stakes permit without coordinator review.

### Phase 4: Embeddings

Optional vector index.

Use:

- semantic search over prompts/docs/tool descriptions
- not source of truth

Current OpenAI embedding docs list:

- `text-embedding-3-small`
- `text-embedding-3-large`

Source: https://platform.openai.com/docs/guides/embeddings

## Recommended Model Defaults

For local development:

- no model by default
- scanner CLI works without any API key

For Deep Agent mode:

- environment variable: `AGENT_PERMIT_MODEL`
- default example: `anthropic:claude-sonnet-4-6` or current OpenAI GPT-5.x model
- allow override through CLI

Example:

```bash
agent-permit investigate . --model anthropic:claude-sonnet-4-6
agent-permit investigate . --model openai:gpt-5.2
agent-permit investigate . --model openrouter:anthropic/claude-sonnet-4-6
```

Do not hardcode one provider into architecture.

## Model Selection Logic

Coordinator model needs:

- strong tool calling
- structured output
- long context
- reliable instruction following
- good code/security reasoning
- low hallucination under evidence constraints

Classifier model needs:

- low cost
- fast
- enough structured output reliability

Embedding model needs:

- cheap semantic retrieval
- stable dimensions
- no reasoning capability

## Prompt Contract

Deep Agent must follow these rules:

- every claim needs evidence ID
- no evidence, no finding
- scanner output beats model inference
- uncertain findings become `needs_review`
- never expose secret values
- never execute target MCP tools
- never run shell without explicit approval

## Evaluation Plan

Use fixture repos:

- `safe-agent`
- `risky-mcp-agent`
- `poisoned-instructions`
- `overbroad-github-token`
- `shell-enabled-agent`

Tests:

- deterministic scanner expected findings
- no secret values in output
- permit status expected
- line refs valid
- Deep Agent report does not invent findings

## Decision

Rely first on custom deterministic scanners plus standard parsers.

Add existing scanners as adapters only when useful:

- Semgrep for code rules
- OSV/pip-audit/npm audit for dependencies
- gitleaks/detect-secrets for secret detection

Use LLMs only for synthesis, prioritization, explanation, and report writing after deterministic evidence exists.
