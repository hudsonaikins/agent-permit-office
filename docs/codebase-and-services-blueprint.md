# Codebase and Services Blueprint

Research date: 2026-06-06

## Core Decision

Develop Agent Permit Office from the ground up.

Do not import a template repo as the foundation. Borrow patterns from LangChain's `deep-agent-template`, but keep our repo architecture scanner-first.

Reason:

- Agent Permit Office is a security/evidence product.
- The source of truth must be deterministic scanners, parsers, and line-cited evidence.
- Deep Agents should coordinate and synthesize after scanner outputs exist.
- Importing a Deep Agents template first would make the agent runtime the center too early.

## Why Not Import A Repo

Template repos are useful when the product is "build a deep agent."

This product is different:

- it scans risky agent repos
- it evaluates MCP/tool/config exposure
- it produces permit decisions
- it needs reproducible findings
- it must avoid overclaiming

The official Deep Agents template gives useful pieces:

- `pyproject.toml`
- `langgraph.json`
- `src/deep_agent/graph.py`
- subagent pattern
- HITL around `execute` and `write_file`
- tests

But importing it would front-load:

- LangSmith deployment shape
- sandbox concerns
- agent graph code
- model-provider setup

Those should come after the scanner engine.

## Product Architecture In One Sentence

Agent Permit Office is a scanner plus agentic investigator:

- scanners collect exact evidence
- indexers organize codebase context
- Deep Agent interprets findings and writes permit
- humans approve risky actions
- reports become CI/web/runtime evidence

## Initial Repo Shape

```text
agent-permit-office/
  README.md
  pyproject.toml
  uv.lock
  .gitignore
  .env.example
  docs/
    agent-permit-office-scope.md
    tech-stack-langchain-deep-agents.md
    codebase-context-and-indexing.md
    codebase-and-services-blueprint.md
    research/
      langchain-deep-agents-architecture.md
  src/
    agent_permit/
      __init__.py
      cli.py
      config.py
      models.py
      paths.py
      scans/
        __init__.py
        run.py
        file_inventory.py
        codebase_map.py
        evidence.py
      scanners/
        __init__.py
        agent_frameworks.py
        credentials.py
        mcp.py
        prompts.py
        repo.py
      reports/
        __init__.py
        permit.py
        markdown.py
        json_writer.py
      policy/
        __init__.py
        rules.py
        severity.py
      agent/
        __init__.py
        graph.py
        prompts.py
        tools.py
        subagents.py
  tests/
    fixtures/
      safe-agent/
      risky-mcp-agent/
      poisoned-instructions/
    unit/
      test_file_inventory.py
      test_mcp_scanner.py
      test_prompt_scanner.py
      test_agent_bom.py
    integration/
      test_scan_cli.py
```

## Module Responsibilities

`cli.py`

- user entrypoint
- command: `agent-permit scan <path>`
- prints concise summary
- writes artifacts

`models.py`

- Pydantic schemas:
  - `ScanRun`
  - `CodebaseMap`
  - `AgentBom`
  - `Finding`
  - `Evidence`
  - `Permit`

`scans/file_inventory.py`

- walks repo
- respects ignore rules
- classifies files
- finds high-signal files

`scans/codebase_map.py`

- creates lightweight graph:
  - files
  - configs
  - agent surfaces
  - MCP servers
  - env references
  - tool definitions

`scanners/mcp.py`

- parses MCP configs
- identifies stdio/HTTP servers
- detects command execution risk
- extracts tool/server metadata where static data exists
- does not execute MCP servers

`scanners/prompts.py`

- scans `AGENTS.md`, `CLAUDE.md`, skills, memory, prompt files
- detects unsafe instructions:
  - ignore policies
  - exfiltrate data
  - auto-approve actions
  - bypass confirmation

`scanners/agent_frameworks.py`

- detects agent framework use:
  - LangChain `create_agent`
  - Deep Agents `create_deep_agent`
  - LangGraph `StateGraph`
  - OpenAI Agents SDK
  - CrewAI/AutoGen later

`scanners/credentials.py`

- finds env var references and token scope hints
- never prints secret values
- marks secret references only

`reports/permit.py`

- converts findings into permit status:
  - `approved`
  - `approved_with_conditions`
  - `needs_review`
  - `blocked`

`agent/graph.py`

- Phase 2 only
- builds `create_deep_agent`
- coordinator uses scanner tools and evidence packs

## Artifact Contract

Every scan writes a run directory:

```text
.agent-permit/
  runs/
    <run_id>/
      scan-input.json
      file-inventory.json
      codebase-map.json
      agent-bom.json
      raw-findings.json
      permit.yaml
      risk-report.md
      evidence-packs/
        <finding_id>.json
```

Artifacts are the product's audit trail.

The Deep Agent never needs raw whole-repo context if these artifacts are good.

## Development Phases

### Phase 1: Local Scanner Monolith

One Python package. No services.

Inputs:

- local repo path

Outputs:

- JSON/YAML/Markdown artifacts

Capabilities:

- file inventory
- MCP config scan
- prompt/instruction scan
- framework detector
- env var reference scan
- permit status

Why:

- fastest validation
- no auth
- no cloud
- no app shell
- easiest tests

### Phase 2: Deep Agent Investigator

Still one Python package.

Adds:

- `create_deep_agent`
- scanner tools
- evidence-pack retrieval tools
- sync subagents
- report critic
- optional LangSmith tracing

No services yet.

Why:

- lets us practice Deep Agents
- keeps architecture simple
- preserves scanner as truth source

### Phase 3: GitHub Action / CI Mode

Still not a long-running service.

Adds:

- `agent-permit scan . --ci`
- SARIF or Markdown PR comment later
- fail/warn policy

Why:

- strongest developer distribution path
- obvious buyer workflow
- easy to demo

### Phase 4: Local Web Report

Still mostly static.

Adds:

- HTML report
- graph visualization
- finding drilldown
- permit timeline

Why:

- better showcase
- useful before hosted SaaS

### Phase 5: Hosted App

Now microservices begin.

Services:

- API service
- web frontend
- scan worker
- agent worker
- artifact store
- database
- queue

Why:

- team workflow
- scheduled scans
- approvals
- persistent history
- GitHub app

## Microservice Architecture Later

Do not build this first. This is target shape after the CLI proves value.

```text
                    +----------------+
User / GitHub App -> | API Service    |
                    +-------+--------+
                            |
                            v
                    +-------+--------+
                    | Queue          |
                    +---+--------+---+
                        |        |
                        v        v
              +---------+--+  +--+-------------+
              | Scan Worker |  | Agent Worker   |
              +------+-----+  +-------+--------+
                     |                |
                     v                v
              +------+----------------+--------+
              | Artifact Store / Object Storage |
              +------+----------------+--------+
                     |
                     v
              +------+------+
              | Database    |
              +------+------+
                     |
                     v
              +------+------+
              | Web App     |
              +-------------+
```

## Service Responsibilities

### API Service

- auth
- create scan runs
- show scan status
- serve reports
- accept approvals
- manage org/repo settings

### Scan Worker

- clone/fetch repo
- run deterministic scanners
- build `CodebaseMap`
- write raw artifacts
- no LLM required

### Agent Worker

- run Deep Agent coordinator
- read scanner artifacts
- synthesize report
- critique permit
- require HITL for patches/actions

### Index Worker

May be separate later.

- builds symbol graph
- builds lexical index
- builds vector index
- updates incrementally

### Artifact Store

- stores scan artifacts
- evidence packs
- reports
- traces/export bundles

Local: filesystem.

Hosted: S3/R2/GCS.

### Database

Stores:

- users/orgs
- repos
- scan runs
- permit statuses
- findings metadata
- approvals
- policies

Good first hosted option:

- Postgres

### Queue

Runs:

- scan jobs
- agent synthesis jobs
- scheduled rescans
- remediation draft jobs

Options later:

- Redis queue
- Celery/RQ
- Cloudflare Queues
- AWS SQS
- LangGraph Agent Server background runs

## LangGraph / LangSmith Service Option

If we use LangSmith Deployment later:

- Agent Server gives assistants, threads, and runs.
- LangSmith gives trace/eval/deployment UI.
- Standalone Agent Server requires Postgres and Redis.

Do not use this as first hosted architecture unless we specifically want LangGraph runtime semantics for all jobs.

For Agent Permit Office, normal job workers may be simpler:

- deterministic scans as normal workers
- Deep Agent only as one job phase

## Should Deep Agent Be A Microservice?

Not at first.

Phase 2:

- Deep Agent is a function called by CLI.

Hosted later:

- Deep Agent can become `agent-worker`.

Only after that:

- consider LangSmith Deployment or standalone Agent Server.

## Build From Ground Up, But Borrow These Patterns

Borrow from `deep-agent-template`:

- `uv` project structure
- `src/` package layout
- `langgraph.json` later
- `agent/graph.py` pattern later
- tests around graph behavior
- HITL defaults for writes/execution

Borrow from Deep Research example:

- coordinator prompt
- evidence files
- subagent findings
- final report writing

Borrow from text-to-SQL example:

- local CLI
- read-only tools
- `FilesystemBackend`
- memory/skills later

Do not copy:

- sandbox backend first
- deployment-first structure
- general-purpose agent defaults as product behavior

## Immediate Next Build

Scaffold Phase 1:

1. `pyproject.toml`
2. `src/agent_permit/models.py`
3. `src/agent_permit/cli.py`
4. file inventory scanner
5. MCP config scanner
6. prompt scanner
7. sample fixtures
8. unit tests

The first useful command:

```bash
uv run agent-permit scan tests/fixtures/risky-mcp-agent
```

Expected output:

- console summary
- `agent-bom.json`
- `raw-findings.json`
- `permit.yaml`
- `risk-report.md`

## Decision

Start as a scanner-first Python monolith.

No imported repo. No microservices yet.

Microservices become relevant only when we need hosted team workflows, GitHub app integration, scheduled scans, persisted approvals, and runtime monitoring.

