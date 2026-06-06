# Codebase Context, Indexing, and MCP Review

Research date: 2026-06-06

## Question

How does Agent Permit Office give the agent a useful "web of the codebase" without dumping the whole repo into the model context?

## Short Answer

Use a layered code intelligence stack:

1. deterministic repo crawler
2. symbol/dependency graph
3. lexical search
4. optional vector index
5. focused evidence packs for the Deep Agent

The Deep Agent should query this index through controlled tools. It should not read the whole repo directly.

## Why Not Just Give Agent Repo Access

Direct repo access is simple, but inefficient and risky.

Problems:

- token waste from reading irrelevant files
- missed evidence because the model scans unevenly
- prompt injection from repo docs/configs
- accidental secret exposure
- hard-to-reproduce findings
- no stable evidence model for reports or CI

Better pattern:

- scanners build a map
- retrieval tools return small, cited slices
- agent reasons over evidence packs
- report links back to file paths and line ranges

## Codebase Web Model

Agent Permit Office should create a local `CodebaseMap`.

Entities:

- files
- directories
- package manifests
- agent configs
- MCP configs
- prompts/instructions
- skills/memory files
- Python modules/classes/functions
- TypeScript modules/functions/classes
- tool definitions
- environment variable references
- shell hooks/scripts
- network clients/API clients
- dependency packages

Edges:

- imports
- calls, where cheap to detect
- config loads
- tool registration
- MCP server declaration
- prompt/memory attachment
- env var use
- file read/write capability
- shell command capability
- outbound network capability

Output:

- `.agent-permit/runs/<run_id>/codebase-map.json`
- `.agent-permit/runs/<run_id>/agent-bom.json`
- `.agent-permit/runs/<run_id>/evidence-packs/*.json`

## Index Layers

### 1. File Inventory

Purpose:

- know what exists
- classify files
- exclude junk

Good first pass:

- walk repo
- respect `.gitignore`
- skip `.git`, `node_modules`, `.venv`, build outputs, large binaries
- classify by path/name/type

High-signal files:

- `AGENTS.md`
- `CLAUDE.md`
- `.mcp.json`
- `mcp.json`
- `claude_desktop_config.json`
- `package.json`
- `pyproject.toml`
- lockfiles
- `.env.example`
- `Dockerfile`
- GitHub Actions workflows
- `src/**`
- `skills/**`
- `prompts/**`
- `memory/**`

### 2. Symbol Graph

Purpose:

- understand code structure without reading every file
- find tool definitions and agent constructors

Implementation choices:

- `tree-sitter` later for robust Python/TS parsing
- Python `ast` first for Python
- TypeScript compiler/parser later
- simple regex fallback for early prototype

Detected patterns:

- LangChain `create_agent`
- Deep Agents `create_deep_agent`
- LangGraph `StateGraph`
- OpenAI Agents SDK agent/tool definitions
- CrewAI/AutoGen/other agent constructors later
- MCP client/server usage
- shell subprocess usage
- file write/read APIs
- HTTP clients
- env var access

### 3. Lexical Search

Purpose:

- fast exact match
- line-range evidence
- no embedding cost

Use:

- ripgrep-like search
- path filters
- known pattern sets

Examples:

- `create_deep_agent`
- `MultiServerMCPClient`
- `subprocess`
- `os.environ`
- `process.env`
- `write_file`
- `execute`
- `SLACK_BOT_TOKEN`
- `GITHUB_TOKEN`

### 4. Vector Index

Purpose:

- semantic lookup when terms vary
- understand natural-language prompts and docs
- retrieve relevant context for risk reasoning

Use only for:

- prompts/instructions
- README/docs
- tool descriptions
- large policy text
- code comments/docstrings

Do not use vector index as truth.

Reasons:

- embeddings can miss exact risky strings
- vector hits are approximate
- security findings need exact evidence

Best use:

- "find instructions that ask agent to ignore policies"
- "find docs describing external data exfil"
- "find tool descriptions that imply network write"

### 5. Evidence Packs

Purpose:

- save tokens
- keep agent grounded

An evidence pack is a small JSON/Markdown bundle:

- finding candidate
- exact file path
- line numbers
- snippet
- parser metadata
- why scanner flagged it
- confidence
- recommended follow-up query

Deep Agent consumes evidence packs, not whole repo.

## Retrieval Tools For Deep Agent

Expose narrow tools:

- `list_agent_surfaces()`
- `get_codebase_map_summary()`
- `search_code(pattern, path_glob=None)`
- `get_symbol(symbol_id)`
- `get_file_slice(path, start, end)`
- `get_evidence_pack(pack_id)`
- `find_related_evidence(finding_id)`
- `write_permit_report(...)`

Do not expose:

- unrestricted filesystem read
- unrestricted shell
- arbitrary MCP execution
- secret-value read

## Token-Saving Strategy

Use progressive context:

1. Agent sees repo summary only.
2. Agent selects scanner outputs.
3. Agent reads top evidence packs.
4. Agent asks for specific file slices only if needed.
5. Agent writes permit from cited evidence.

This keeps the model from reading thousands of lines.

Good budget target:

- repo summary: under 2k tokens
- each evidence pack: 300-800 tokens
- final report context: under 20k tokens

## MCP Review

MCP has two roles in this product:

1. Input risk surface: scan target repos for MCP configs and servers.
2. Optional integration surface: use trusted MCP tools to inspect external systems later.

Start with role 1.

### Official Registry

The official MCP Registry exists at:

- https://registry.modelcontextprotocol.io/
- https://modelcontextprotocol.io/registry/about

The registry is a metadata catalog for publicly accessible MCP servers. Its own terms warn users to evaluate servers and suitability before use.

### Useful MCP Categories Later

Potential useful MCPs for Agent Permit Office:

- GitHub MCP: inspect repos/issues/PRs.
- filesystem MCP: local files, risky unless sandboxed.
- AWS MCP: cloud posture checks, later only with read-only role.
- docs/search MCP: standards and vendor docs.
- package/security MCPs: dependency and vulnerability metadata.
- code intelligence MCPs like Serena-style semantic code tools.

### Why MCP Execution Is Off In MVP

MCP is part of the risk we are assessing.

Known risk classes:

- untrusted server process execution
- malicious tool descriptions
- tool poisoning
- prompt injection through retrieved content
- overbroad OAuth/API scopes
- data exfiltration through combined tools
- implicit trust across multiple MCP servers
- package typosquatting or stale servers

Research and official guidance are moving quickly here, so initial product should inspect MCP configs and metadata, not execute unknown MCP servers.

Sources:

- Official registry: https://registry.modelcontextprotocol.io/
- Registry about: https://modelcontextprotocol.io/registry/about
- Registry terms: https://modelcontextprotocol.io/registry/terms-of-service
- NSA MCP security guidance: https://www.nsa.gov/Press-Room/Press-Releases-Statements/Press-Release-View/Article/4496698/nsa-releases-security-design-considerations-for-ai-driven-automation-leveraging/
- MCP security analysis: https://arxiv.org/abs/2601.17549
- MCP tool poisoning threat model: https://arxiv.org/abs/2603.22489

## Build Order

Phase 1:

- file inventory
- lexical scanner
- MCP config parser
- prompt/instruction scanner
- evidence pack writer

Phase 2:

- Python AST symbol parser
- import graph
- env var references
- agent framework detectors

Phase 3:

- vector index for docs/prompts/tool descriptions
- query tools for Deep Agent
- evidence-pack retrieval

Phase 4:

- tree-sitter for multi-language parsing
- dependency graph
- graph visualization

Phase 5:

- trusted MCP integrations
- GitHub Action
- hosted dashboard

## Decision

Yes, Agent Permit Office should have a codebase graph and eventually a vector index.

But vector search should be secondary. Exact parsers, lexical search, and line-cited evidence are primary because this is a security/product-trust tool.

