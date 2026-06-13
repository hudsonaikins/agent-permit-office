# Agent Permit Office

PermitGraph for AI agents: a local permit gate that checks whether a repository's agents should receive tools, credentials, memory, or production access.

AI teams are starting to wire coding agents, MCP servers, CI workflows, and long-lived credentials into the same repos. That creates a new approval problem: a normal code review does not show whether an agent can reach a secret, write to a protected branch, follow unsafe repository instructions, or pass repo context into an external tool. Agent Permit Office turns those facts into reviewable evidence before the agent runs.

## What It Does

- Scans a repository without executing agent code, MCP servers, workflows, package scripts, or external tools.
- Builds an Agent Capability Graph from MCP configs, prompt instructions, credential references, CI workflows, file inventory, and relationship edges.
- Finds risky source-to-sink paths such as repo file access to credential context, privileged CI trust paths, or prompt instructions that override scanner boundaries.
- Writes deterministic permit artifacts: `approved`, `needs_review`, or `blocked`.
- Runs a bounded LangChain Deep Agent investigation over scanner artifacts when model access is enabled.
- Citation-checks Deep Agent output against local evidence.
- Exports SARIF, baselines, policy evaluations, local analytics, dashboard snapshots, and sanitized proof packs.

## Quickstart

Install dependencies:

```bash
uv sync --all-extras --dev
```

Scan the repo:

```bash
uv run agent-permit scan . --ci --exclude "tests/fixtures/**"
```

Open the run artifacts:

```text
.agent-permit/runs/<run_id>/summary.md
.agent-permit/runs/<run_id>/risk-report.md
.agent-permit/runs/<run_id>/permit.yaml
.agent-permit/runs/<run_id>/raw-findings.json
.agent-permit/runs/<run_id>/graph-paths.json
.agent-permit/runs/<run_id>/run-metrics.json
```

Generate dashboard data and a shareable proof pack:

```bash
python3 tools/export_dashboard_snapshot.py
python3 tools/export_dashboard_snapshot.py --proof-pack
```

The proof pack exporter prints both paths:

```text
.agent-permit/proof-packs/<validation_run_id>
.agent-permit/proof-packs/<validation_run_id>.zip
```

Run the local dashboard:

```bash
cd dashboard
bun install
bun dev
```

Then open the localhost URL printed by Vite.

Run the local public-release check:

```bash
python3 tools/release_check.py
```

## Deep Agent Investigation

Deep Agent investigation is part of the product path, not a side demo. The deterministic scanner creates bounded evidence. The Deep Agent reads that evidence, reasons across related artifacts, writes a cited report, and the citation critic checks whether claims are grounded.

Run from an existing scan:

```bash
export OPENROUTER_API_KEY=<key>
uv run --extra deep-agent agent-permit investigate .agent-permit/runs/<run_id>
```

Run the full live validation harness with Phoenix tracing:

```bash
export OPENROUTER_API_KEY=<key>
uv run --extra deep-agent --extra phoenix agent-permit live-validate . \
  --agent-recursion-limit 20 \
  --phoenix
```

Offline deterministic fallback for tests or no-key debugging:

```bash
uv run agent-permit investigate .agent-permit/runs/<run_id> --deterministic-only
```

Default model path is Claude Sonnet 4.6 through OpenRouter. Prompt caching, response caching, timeout caps, completion caps, token metrics, and cache-hit metrics are recorded in local run artifacts.

## Demo Paths

Safe fixture:

```bash
uv run agent-permit scan tests/fixtures/safe-agent --ci --run-id demo-safe
```

Risky CI fixture:

```bash
uv run agent-permit scan tests/fixtures/risky-ci-agent --ci --run-id demo-risky || true
```

Risky MCP fixture:

```bash
uv run agent-permit scan tests/fixtures/risky-mcp-agent --ci --run-id demo-mcp || true
```

Open-source validation dry run without model spend:

```bash
uv run agent-permit open-source-demo docs/evals/open-source-live-repos.json \
  --repo-root /tmp/agent-permit-open-source-validation \
  --run-id open-source-demo-prep \
  --skip-live
```

Full open-source validation with Deep Agent and Phoenix:

```bash
export OPENROUTER_API_KEY=<key>
uv run --extra deep-agent --extra phoenix agent-permit open-source-demo \
  docs/evals/open-source-live-repos.json \
  --repo-root /tmp/agent-permit-open-source-validation \
  --agent-recursion-limit 20 \
  --phoenix \
  --exclude ".agent-permit/**"
```

## CLI Reference

Common commands:

```bash
uv run agent-permit rules
uv run agent-permit scan . --ci --sarif
uv run agent-permit sarif .agent-permit/runs/<run_id>
uv run agent-permit baseline .agent-permit/runs/<run_id> --output .agent-permit/finding-baseline.json
uv run agent-permit scan . --ci --baseline .agent-permit/finding-baseline.json --ci-new-findings-only
uv run agent-permit scan . --ci --policy agent-permit-policy.json
uv run agent-permit analytics summarize .
uv run agent-permit eval tests/fixtures
uv run --extra phoenix agent-permit eval tests/fixtures --upload-phoenix
uv run agent-permit eval-real docs/evals/real-repos.json --repo-root /tmp/agent-permit-validation
```

## Open Core Boundary

Open-source core:

- deterministic scanner and rule registry
- Agent Capability Graph builder and risky path finder
- permit engine and local artifact schemas
- Markdown, JSON, YAML, SARIF, baseline, diff, policy, metrics, and eval outputs
- bounded Deep Agent evidence tools, prompt flow, and citation critic
- OpenRouter adapter with local cost/cache telemetry
- Phoenix local tracing and eval export support
- GitHub Action and local dashboard snapshot workflow

Hosted product roadmap:

- multi-repo dashboard and team review queue
- private repo connectors and scheduled scans
- SSO/RBAC, assignments, approval history, and audit retention
- managed model gateway, model policy, key isolation, and spend controls
- policy packs, custom rules, notifications, and support/SLA

The hosted product is not required to use the local scanner. The commercial value is managed workflow, governance, retention, and integrations, not hiding the scanner logic.

## Safety Boundaries

- Static scanning only: no agent, MCP server, CI workflow, package script, or external tool execution during scans.
- Real `.env` files and generated/junk directories are skipped.
- Secret values are not emitted; evidence may include secret variable names when needed for risk explanation.
- Proof packs copy only allowlisted artifacts and apply redaction before export.
- Old validation runs may produce partial proof packs when referenced temp repo directories no longer exist. Regenerate live validation for complete audit evidence.

## Docs Map

Product and business:

- [Product Scope and Market Review](docs/product-scope-market-review.md)
- [Open Core Business Plan](docs/open-core-business-plan.md)
- [Customer Discovery Kit](docs/customer-discovery-kit.md)
- [Open Source Release Readiness](docs/open-source-release-readiness.md)
- [Release Candidate Plan](docs/release-candidate-plan.md)
- [Project Management and Sprint Plan](docs/project-management-sprint-plan.md)

Architecture:

- [Starter Scope and Architecture](docs/agent-permit-office-scope.md)
- [Codebase and Services Blueprint](docs/codebase-and-services-blueprint.md)
- [End-to-End System Diagram](docs/system-diagram-end-to-end.md)
- [Dashboard Stack Architecture](docs/dashboard-stack-architecture.md)

Scanner and evidence:

- [Deterministic Scanners and Model Plan](docs/scanner-and-model-plan.md)
- [Static Analysis and Agent Security Research](docs/research/static-analysis-agent-security-research.md)
- [Repository Policy Configuration](docs/repository-policy-config.md)
- [SARIF and Code Scanning](docs/sarif-code-scanning.md)
- [Baseline and Diff Mode](docs/baseline-diff-mode.md)
- [PermitGraph Proof Pack Export](docs/proof-pack-export.md)

Deep Agent and observability:

- [LangChain Deep Agents Architecture Research](docs/research/langchain-deep-agents-architecture.md)
- [Deep Agent Investigator](docs/deep-agent-investigator.md)
- [Live Deep Agent Validation](docs/live-deep-agent-validation.md)
- [Live Proof Rerun Plan](docs/live-proof-rerun-plan.md)
- [OpenRouter Model Decision](docs/openrouter-model-decision.md)
- [Phoenix Observability and Evaluation](docs/phoenix-observability-evaluation.md)
- [Product Analytics and Evals Roadmap](docs/product-analytics-evals-roadmap.md)

Demo and release:

- [Demo](docs/demo.md)
- [Sanitized Demo Artifacts](docs/sanitized-demo-artifacts.md)
- [Open Source Live Validation](docs/open-source-live-validation.md)
- [Real Repo Validation](docs/real-repo-validation.md)
- [MVP Hardening](docs/mvp-hardening.md)
