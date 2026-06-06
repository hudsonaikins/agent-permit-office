# Static Analysis And Agent Security Research

Research date: 2026-06-06

## Why This Document Exists

The first scanner plan was directionally right, but too thin.

It said:

- deterministic scanners
- capability graph
- source/sink rules
- Deep Agent investigator later

That is not enough for an industry-grade project. The technical foundation needs to borrow from mature static application security testing, code property graphs, taint analysis, policy-as-code, prompt-injection research, MCP security research, and fuzzing.

The stronger product thesis:

> Agent Permit Office should build an Agent Capability Graph, then run deterministic source-to-sink and policy rules over that graph. Deep Agents investigate and explain findings. Reinforcement learning belongs later as a dynamic fuzzing/search optimizer, not as the phase-one scanner brain.

## Research Sources Reviewed

| Area | Source | Useful idea | Product implication |
| --- | --- | --- | --- |
| Code property graphs | [Joern Code Property Graph docs](https://docs.joern.io/code-property-graph/) and [CPG specification](https://cpg.joern.io/) | CPG joins syntax, control flow, and data flow into one queryable representation. | Build an agent-specific graph instead of relying on plain regex scans. |
| Data-flow analysis | [CodeQL Python data flow docs](https://codeql.github.com/docs/codeql-language-guides/analyzing-data-flow-in-python/) | Sources, sinks, barriers, local/global flow, and taint tracking. | Model credentials, prompts, repo data, tools, and network sends as source/sink problems. |
| Taint rules | [Semgrep taint analysis docs](https://semgrep.dev/docs/writing-rules/data-flow/taint-mode/overview) | `pattern-sources`, `pattern-propagators`, `pattern-sanitizers`, and `pattern-sinks`. | Use declarative rules for early scanners; add Semgrep adapter later. |
| Python SAST | [Pysa at Meta](https://engineering.fb.com/2020/08/07/security/pysa/) and [Pysa basics](https://pyre-check.org/docs/pysa-basics/) | Security/privacy bugs are often unsafe data flows from source to sink. | Our Python scanner should use AST facts first, then optional taint-analysis adapters. |
| Persistent code graphs | [Codebase-Memory paper](https://arxiv.org/abs/2603.27277) | Tree-sitter graph via MCP cuts token usage and tool calls while preserving codebase structure. | Build compact graph/evidence packs so the Deep Agent does not read the whole repo. |
| CPG for LLM agents | [Codebadger paper](https://arxiv.org/abs/2603.24837) | LLMs should use high-level tools for slicing, taint tracking, data flow, and semantic navigation instead of raw CPG queries. | Give Deep Agent small graph tools with capped output, not unrestricted repo or graph access. |
| Prompt-injection architecture | [CaMeL / Defeating Prompt Injections by Design](https://arxiv.org/abs/2503.18813) | Separate trusted control flow from untrusted data flow; use capabilities to prevent unauthorized flows. | Permit Office should score whether untrusted content can influence tool execution or data exfiltration. |
| MCP security | [Breaking the Protocol: Security Analysis of MCP](https://arxiv.org/abs/2601.17549) | MCP risk includes missing capability attestation, sampling origin gaps, and implicit trust propagation. | MCP scanner should inspect capability claims, transports, credentials, and multi-server trust chains. |
| MCP threat modeling | [MCP tool poisoning threat modeling](https://arxiv.org/abs/2603.22489) | Tool metadata can carry malicious instructions; defenses include static metadata analysis and decision-path tracking. | Scan tool descriptions and prompts for hidden control instructions, then trace whether tools can act. |
| Multi-tool agent fuzzing | [ChainFuzzer](https://arxiv.org/abs/2603.12614) | Multi-tool vulnerabilities emerge through source-to-sink tool composition; greybox fuzzing can reproduce them. | Later dynamic scanner should test chains, not just individual tools. |
| RL and fuzzing | [FuzzerGym](https://arxiv.org/abs/1807.07490) | Reinforcement learning can guide mutation strategies using coverage/program-state feedback. | RL is useful for adversarial prompt/tool-chain fuzzing after deterministic graph and harness exist. |
| Agent benchmark | [AgentDojo paper](https://arxiv.org/abs/2406.13352) and [AgentDojo GitHub](https://github.com/ethz-spylab/agentdojo) | Dynamic environment for prompt-injection attacks and defenses across realistic agent tasks. | Use as benchmark inspiration for test fixtures and attack scenarios. |
| Policy engine | [Open Policy Agent docs](https://www.openpolicyagent.org/docs) | Policy-as-code separates evidence collection from decision logic. | Early Python rules can later compile/export to Rego-like policies. |
| OSS competitor | [Agentic Radar](https://github.com/splx-ai/agentic-radar) | Open-source scanner for LangGraph, CrewAI, n8n, OpenAI Agents, and AutoGen workflows. | Shows demand; our differentiation must be stronger evidence, permit status, source-to-sink paths, and MCP/capability depth. |
| OSS competitor | [Tencent AI-Infra-Guard](https://github.com/Tencent/AI-Infra-Guard) | Full-stack AI security scanning, including MCP, agent scan, skills scan, infra scan, and jailbreak eval. | Market is moving; narrow wedge should be pre-deploy agent permits with defensible evidence. |
| OSS red-team tool | [NVIDIA garak](https://github.com/NVIDIA/garak) | LLM vulnerability scanner using probes and detectors. | Useful later for dynamic model/system probing, not as phase-one repo scanner. |

## Core Technical Method

Agent Permit Office should not be "an AI that reads a repo and says risky."

It should be:

```text
repo files/configs
  -> parsers
  -> typed facts
  -> Agent Capability Graph
  -> source/sink + policy rules
  -> line-cited findings
  -> permit decision
  -> Deep Agent investigation/report
  -> optional dynamic fuzzing/RL later
```

This follows the same family of methods used by CodeQL, Joern, Semgrep, Pysa, OPA, and agent-security fuzzers.

## Agent Capability Graph

The key architecture upgrade is to define an Agent Capability Graph, or ACG.

It is inspired by code property graphs, but the graph nodes are agent-security objects instead of only code objects.

### Node Types

- `Agent`
- `Subagent`
- `Tool`
- `McpServer`
- `Prompt`
- `Instruction`
- `CredentialRef`
- `SecretSource`
- `MemoryStore`
- `FileSet`
- `NetworkEndpoint`
- `CloudRole`
- `CiWorkflow`
- `Sandbox`
- `ApprovalGate`
- `HumanReviewer`
- `Package`
- `Command`

### Edge Types

- `uses`
- `registers`
- `delegates_to`
- `launches`
- `receives_credential`
- `reads`
- `writes`
- `sends_to`
- `imports`
- `calls`
- `influenced_by`
- `trusts`
- `gated_by`
- `lacks_gate`
- `sanitizes`
- `blocks`
- `pins_version`
- `runs_in`

### Example Graph

```text
Agent("support-agent")
  uses -> McpServer("github")
McpServer("github")
  launches -> Command("npx -y github-mcp-server")
McpServer("github")
  receives_credential -> CredentialRef("GITHUB_TOKEN")
Agent("support-agent")
  reads -> FileSet("repo")
Agent("support-agent")
  sends_to -> NetworkEndpoint("slack")
Agent("support-agent")
  lacks_gate -> ApprovalGate("external_send")
Prompt("system")
  influenced_by -> Instruction("do not ask approval")
```

That graph lets the scanner ask:

- Can an untrusted tool receive credentials?
- Can repo/private data flow to an external sink?
- Can prompt or tool metadata influence control flow?
- Is a high-impact action covered by approval?
- Does CI run the agent with write permissions?
- Is a stdio MCP server launched from an unpinned package?

## Fact Extraction

Phase one should extract facts from known file types. No LLM needed.

| Scanner | Parser | Facts |
| --- | --- | --- |
| File inventory | filesystem + `.gitignore` pathspec | file class, size, language, high-signal paths |
| MCP config | JSON/YAML | server name, transport, command, args, URL, env vars |
| Prompt/instruction | Markdown/plain text | unsafe phrases, approval bypass, hidden tool instructions |
| Python agent code | Python `ast` | imports, calls, decorators, env access, subprocess, filesystem/network use |
| JS/TS agent code | lexical first, Tree-sitter later | imports, tool registration, env access, child process, network calls |
| Package manifests | JSON/TOML/YAML | package names, versions, scripts, unpinned dependencies |
| CI workflows | YAML | permissions, secrets exposure, PR event context, command execution |
| Credentials | AST/config/text | secret variable references and scopes, never secret values |

Fact example:

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

Credential fact:

```json
{
  "type": "credential_ref",
  "name": "GITHUB_TOKEN",
  "attached_to": "mcp_server:github-tools",
  "path": ".mcp.json",
  "line_start": 10,
  "line_end": 10,
  "secret_value_recorded": false
}
```

## Source/Sink Model

This is the strongest deterministic scanner core.

### Sensitive Sources

- environment variables
- secret managers
- `.env` references
- repository files
- private docs
- memory stores
- user messages
- tool outputs
- browser/web data
- database rows
- cloud credentials
- GitHub tokens
- Slack/email tokens

### Dangerous Sinks

- shell execution
- MCP server environment
- external HTTP request
- Slack/email send
- GitHub write operation
- cloud write API
- database write
- file write
- browser automation
- memory write
- model context injection

### Propagators

- assignment
- function argument passing
- tool registration
- MCP server config
- prompt template interpolation
- memory retrieval
- subagent handoff
- workflow step output
- CI environment variable passthrough

### Sanitizers / Barriers

- scoped read-only token
- allowlisted endpoint
- explicit approval gate
- sandbox without network
- blocked shell execution
- pinned package version
- validated schema
- output escaping
- prompt/tool-output quarantine
- user confirmation before external send

## Deterministic Rule Examples

### Rule: Unpinned Stdio MCP Receives Credential

```text
IF McpServer.transport == "stdio"
AND McpServer.launches.command IN ["npx", "uvx", "python", "node"]
AND Package.version IS missing_or_unpinned
AND McpServer.receives_credential EXISTS
THEN severity = high
```

Why this matters:

- stdio MCP servers execute local code
- unpinned package resolution adds supply-chain risk
- credentials cross into that process

### Rule: Repo Data Can Reach External Send

```text
IF Agent reads FileSet("repo" OR "private_docs" OR "secrets")
AND Agent sends_to NetworkEndpoint("external")
AND NOT Agent gated_by ApprovalGate("external_send")
THEN severity = critical
```

Why this matters:

- this is an exfiltration path
- no exploit needs to be run to show the path exists

### Rule: Prompt Controls Dangerous Action

```text
IF Prompt contains approval_bypass_instruction
AND Prompt influences Agent
AND Agent uses Tool(shell OR github_write OR email_send OR cloud_write)
THEN severity = high
```

Why this matters:

- untrusted or unsafe instructions can change control flow
- CaMeL's core lesson is that untrusted data must not control actions

### Rule: Tool Metadata Poisoning

```text
IF Tool.description contains hidden_instruction_pattern
AND Tool can influence model_context
AND Agent has dangerous_sink
THEN severity = high
```

Why this matters:

- MCP tool metadata can carry instructions
- the scanner should flag metadata that attempts to steer the model outside the user request

### Rule: CI Agent Runs With Write Permission

```text
IF CiWorkflow.triggers includes pull_request_target OR untrusted_context
AND CiWorkflow.permissions includes write
AND CiWorkflow.runs_agent_command == true
THEN severity = critical
```

Why this matters:

- untrusted PR content plus write tokens plus agent execution is a high-impact control boundary failure

## Why This Has Intelligence Without LLMs

The intelligence sits in the intermediate representation and the rules.

It is not just regex. It is:

- typed fact extraction
- graph construction
- source/sink tracking
- trust-boundary analysis
- control detection
- policy-as-code
- reproducible evidence

This is the same reason CodeQL and Pysa can find real vulnerabilities without an LLM. The system understands enough structure to reason about paths.

## Where Deep Agents Fit

Deep Agents should not decide raw facts.

Deep Agents should:

- read evidence packs
- ask graph tools focused questions
- compare findings against policy
- write a human-readable permit report
- identify missing context
- propose follow-up scanner rules
- generate remediation plans
- critique the permit decision

Deep Agent tools should be high-level and capped:

- `get_finding(finding_id)`
- `find_paths(source_type, sink_type, max_depth)`
- `get_agent_bom()`
- `get_mcp_servers()`
- `get_credential_refs()`
- `get_evidence_pack(finding_id)`
- `search_prompt_instructions(pattern_id)`
- `explain_rule(rule_id)`

Do not expose:

- unrestricted filesystem reads
- shell execution
- raw MCP execution
- raw graph database query
- remote network calls
- secret values

This follows the Codebadger lesson: LLMs should use high-level program-analysis tools, not generate complex graph queries from scratch.

## Where Reinforcement Learning Fits

RL should not be used for phase-one static scanning.

Bad phase-one RL idea:

```text
train an RL model to decide whether an agent repo is safe
```

Problems:

- no labeled dataset at start
- false confidence
- hard to explain to buyers
- hard to reproduce
- weak audit trail
- expensive before product-market proof

Good later RL idea:

```text
use RL/bandits to guide dynamic prompt and tool-chain fuzzing
```

### RL Fuzzing Loop

State:

- current agent trace
- tools discovered
- visited graph nodes
- source/sink distance
- guardrail responses
- previous payload mutations
- coverage of tool chains

Actions:

- choose source data
- choose tool chain target
- mutate prompt
- mutate tool output
- mutate MCP metadata
- choose attack strategy
- choose sink oracle

Reward:

- new source-to-sink path reached
- dangerous sink invoked
- guardrail bypassed
- new tool chain covered
- exploit reproduced with fewer steps
- lower token/tool-call cost

Environment:

- local fixture agent
- sandboxed target repo
- mocked credentials
- mocked external services
- deterministic oracle for unsafe action

This is close to FuzzerGym and ChainFuzzer, adapted for LLM agents:

- fuzzing gives the environment
- source/sink graph gives targets
- RL/bandits optimize exploration
- Deep Agent can help design attack hypotheses

## Open-Source Technology Map

### Should We Use Joern Directly?

Not in phase one.

Use Joern as an architectural reference. It is powerful, but heavy for the first wedge. The initial product is not general C/C++ vulnerability analysis; it is agent/MCP permit analysis.

Good later use:

- optional adapter for deep code slicing
- high-risk repos
- enterprise mode

### Should We Use CodeQL Directly?

Not as the first runtime dependency.

Use CodeQL concepts first. Add CodeQL adapter later for GitHub-native enterprise scanning.

Good later use:

- SARIF output
- custom CodeQL queries for agent frameworks
- GitHub Advanced Security users

### Should We Use Semgrep?

Likely yes as an optional phase-two adapter.

Reason:

- easy local install
- good custom rules
- language coverage
- mature taint vocabulary

But the product should not only be a Semgrep rule pack. The core value is the Agent Capability Graph and permit decision.

### Should We Use Pysa?

Maybe later for Python-heavy enterprise apps.

Phase one should keep Python `ast` simple. Pysa needs model files and deeper setup. It is useful when scanning Python services at scale, less useful as a first CLI demo.

### Should We Use Tree-sitter?

Yes, after Python-only MVP.

Tree-sitter is the right path for multi-language parsing and codebase graph construction. Codebase-Memory supports the token-saving rationale.

### Should We Use OPA/Rego?

Later.

Phase one can use Python policy rules because iteration speed matters. The data model should be shaped so rules can later become Rego policies.

### Should We Use Agentic Radar / AI-Infra-Guard / garak?

Study them, do not clone them.

Positioning difference:

- Agentic Radar: workflow scanner and test generator.
- AI-Infra-Guard: broad AI security platform.
- garak: LLM vulnerability probing.
- Agent Permit Office: pre-deploy permit decision with deterministic evidence, source-to-sink paths, MCP/tool capability graph, and Deep Agent explanation.

## Product Wedge

The buyer does not need another generic "AI security scanner."

The buyer needs:

```text
Can this agent be allowed to run with these tools, credentials, and permissions?
```

That becomes a permit workflow:

- `approved`
- `approved_with_conditions`
- `needs_review`
- `blocked`

The report should say:

- which agent exists
- what tools it has
- what credentials it touches
- what data it can read
- where it can send/write/execute
- what controls exist
- what missing controls block approval
- exact evidence paths and lines

## Recommended Build Path

### Phase 1A: Agent Capability Graph MVP

Build:

- typed facts
- graph model
- source/sink categories
- 15 to 25 deterministic rules
- JSON and Markdown reports
- fixture repos
- no LLM

Technology:

- Python
- `uv`
- Pydantic
- Python `ast`
- JSON/YAML/TOML parsers
- `networkx` or simple in-memory adjacency first
- pytest fixtures

### Phase 1B: Evidence Quality

Build:

- line extraction
- confidence scoring
- rule explanations
- severity formula
- false-positive suppression file
- permit status

### Phase 2: Deep Agent Investigator

Build:

- LangGraph/Deep Agent coordinator
- high-level graph tools
- evidence-pack retrieval
- report writer subagent
- critic subagent
- optional LangSmith tracing

Important:

- Deep Agent reads artifacts, not raw repo
- no shell tool
- no MCP execution
- no secret access

### Phase 3: Dynamic Fuzzing

Build:

- sandbox target runner
- mocked external sinks
- prompt/tool-output mutation set
- source/sink oracles
- trace capture
- replayable exploit report

Borrow from:

- ChainFuzzer
- AgentDojo
- garak probe/detector pattern

### Phase 4: RL/Bandit Fuzzer

Build only after deterministic fuzzing exists.

Start with:

- multi-armed bandit for mutation strategy selection
- coverage-guided reward
- source-to-sink path reward

Avoid deep RL until there is enough trace data.

## What Is Novel Enough

Not novel:

- static analysis
- taint analysis
- prompt-injection scanner
- LLM red-team probes
- generic LangGraph scanner

Potentially novel:

- Agent Capability Graph as an audit IR
- permit decision model for agent/tool/credential approval
- deterministic source-to-sink paths over MCP, prompts, tools, CI, credentials, and memory
- Deep Agent investigator constrained to evidence packs
- later dynamic fuzzing that targets graph-discovered source/sink paths
- policy-as-code controls for agent deployment approval

## Hard Recommendation

Build Agent Permit Office as:

```text
Agent Capability Graph + deterministic permit engine first.
Deep Agent investigation second.
Dynamic fuzzing third.
RL-guided fuzzing fourth.
```

Do not lead with:

- generic LLM scanner
- RL safety classifier
- broad AI security platform
- hosted SaaS first
- LangGraph demo app first

The sellable wedge is:

> "Before your AI agent gets GitHub, Slack, browser, filesystem, MCP, cloud, or production credentials, Agent Permit Office proves what it can touch, where data can flow, what controls exist, and whether it deserves a permit."

