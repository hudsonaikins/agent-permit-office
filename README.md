# Agent Permit Office

Agent Permit Office is an investigation-stage project for approving AI agents before they receive tools, credentials, memory, or production access.

Current implementation:

- Python `uv` package with `agent-permit` CLI.
- Static scan only; it does not execute agent code, MCP servers, or external tools.
- `agent-permit scan <path>` creates `.agent-permit/runs/<run_id>/`.
- The scan writes metadata-only `file-inventory.json` with file classifications, hashes, and skip counts.
- MCP config scan writes `agent-bom.json` and `raw-findings.json` for `.mcp.json`, `mcp.json`, and `claude_desktop_config.json`.
- Prompt scan adds line-cited findings for risky `AGENTS.md`, `CLAUDE.md`, and skill `SKILL.md` instructions.
- Credential scan records env/example and code credential variable names in `agent-bom.json`.
- CI scan adds line-cited findings for risky GitHub Actions triggers, permissions, and secret usage.
- Graph builder writes `codebase-map.json` with files, MCP servers, credential refs, prompt instructions, workflows, and relationship edges.
- Path finder writes `graph-paths.json` with source/sink taxonomy and bounded risky paths.
- Permit engine writes `controls.json`, `permit.yaml`, and `risk-report.md` with deterministic approval status.
- CI mode writes `summary.md` and exits non-zero for `needs_review` or `blocked` permits.
- SARIF mode writes `results.sarif` for GitHub code scanning upload.
- Baseline mode writes deterministic finding baselines and diffs so CI can fail only on newly introduced findings.
- Policy mode reads `agent-permit-policy.json` or `--policy` and writes `policy-evaluation.json`.
- Eval mode writes fixture regression and Phoenix dataset-row artifacts under `.agent-permit/evals/<run_id>/`.
- Investigation mode uses a required bounded LangChain Deep Agent, defaulting to Claude Sonnet 4.6 through OpenRouter.
- Live validation mode scans fresh, runs the Deep Agent, citation-checks the report, and writes `live-validation.json`.
- Optional Phoenix/OpenTelemetry tracing can be enabled for live Deep Agent investigations, including evidence-tool spans.
- Real `.env` files and generated/junk directories are skipped; secret values are not emitted.

Run locally:

```bash
uv sync --all-extras --dev
uv run agent-permit scan .
```

Run in CI:

```bash
uv run agent-permit scan . --ci
```

Run in CI and write SARIF:

```bash
uv run agent-permit scan . --ci --sarif
```

Run with an exclusion:

```bash
uv run agent-permit scan . --ci --exclude "tests/fixtures/**"
```

Write a cited Deep Agent investigation from scan artifacts:

```bash
export OPENROUTER_API_KEY=<key>
uv run --extra deep-agent agent-permit investigate .agent-permit/runs/<run_id>
```

Run the full live validation harness:

```bash
export OPENROUTER_API_KEY=<key>
uv run --extra deep-agent --extra phoenix agent-permit live-validate . \
  --agent-recursion-limit 20 \
  --phoenix
```

Write the offline deterministic fallback for tests or no-key debugging:

```bash
uv run agent-permit investigate .agent-permit/runs/<run_id> --deterministic-only
```

Write SARIF from existing scan artifacts:

```bash
uv run agent-permit sarif .agent-permit/runs/<run_id>
```

Write a finding baseline from existing scan artifacts:

```bash
uv run agent-permit baseline .agent-permit/runs/<run_id> --output .agent-permit/finding-baseline.json
```

Run CI against an existing baseline and fail only on new findings:

```bash
uv run agent-permit scan . --ci --baseline .agent-permit/finding-baseline.json --ci-new-findings-only
```

Run with an explicit repo policy:

```bash
uv run agent-permit scan . --ci --policy agent-permit-policy.json
```

Run local deterministic evals:

```bash
uv run agent-permit eval tests/fixtures
```

Upload eval rows to a running local Phoenix server:

```bash
uv run --extra phoenix agent-permit eval tests/fixtures --upload-phoenix
```

Run repeatable real-repo evals against local public clones:

```bash
uv run agent-permit eval-real docs/evals/real-repos.json --repo-root /tmp/agent-permit-validation
```

Run repeatable live validation against local recent open-source clones:

```bash
export OPENROUTER_API_KEY=<key>
uv run --extra deep-agent --extra phoenix agent-permit live-validate-real \
  docs/evals/open-source-live-repos.json \
  --repo-root /tmp/agent-permit-open-source-validation-20260607 \
  --agent-recursion-limit 20 \
  --phoenix \
  --exclude ".agent-permit/**"
```

Run the full open-source demo path, including clone/refresh and shareable reports:

```bash
export OPENROUTER_API_KEY=<key>
uv run --extra deep-agent --extra phoenix agent-permit open-source-demo \
  docs/evals/open-source-live-repos.json \
  --repo-root /tmp/agent-permit-open-source-validation \
  --agent-recursion-limit 20 \
  --phoenix \
  --exclude ".agent-permit/**"
```

List deterministic rules:

```bash
uv run agent-permit rules
```

Current work:

- [LangChain Deep Agents Architecture Research](docs/research/langchain-deep-agents-architecture.md)
- [Starter Scope and Architecture](docs/agent-permit-office-scope.md)
- [Tech Stack Analysis: LangChain, Deep Agents, and LangSmith](docs/tech-stack-langchain-deep-agents.md)
- [Codebase Context, Indexing, and MCP Review](docs/codebase-context-and-indexing.md)
- [Codebase and Services Blueprint](docs/codebase-and-services-blueprint.md)
- [Deterministic Scanners and Model Plan](docs/scanner-and-model-plan.md)
- [Static Analysis and Agent Security Research](docs/research/static-analysis-agent-security-research.md)
- [SARIF MVP Decision](docs/research/sarif-mvp-decision.md)
- [GitHub Action](docs/github-action.md)
- [SARIF and Code Scanning](docs/sarif-code-scanning.md)
- [Baseline and Diff Mode](docs/baseline-diff-mode.md)
- [Repository Policy Configuration](docs/repository-policy-config.md)
- [OpenRouter Model Decision](docs/openrouter-model-decision.md)
- [Live Deep Agent Validation](docs/live-deep-agent-validation.md)
- [Open Source Live Validation](docs/open-source-live-validation.md)
- [Open Source Release Readiness](docs/open-source-release-readiness.md)
- [Open Core Business Plan](docs/open-core-business-plan.md)
- [Product Scope and Market Review](docs/product-scope-market-review.md)
- [Product Analytics and Evals Roadmap](docs/product-analytics-evals-roadmap.md)
- [Sanitized Demo Artifacts](docs/sanitized-demo-artifacts.md)
- [Demo](docs/demo.md)
- [Deep Agent Investigator](docs/deep-agent-investigator.md)
- [Phoenix Observability and Evaluation](docs/phoenix-observability-evaluation.md)
- [MVP Hardening](docs/mvp-hardening.md)
- [Real Repo Validation](docs/real-repo-validation.md)
- [CI Context Hardening](docs/ci-context-hardening.md)
- [End-to-End System Diagram](docs/system-diagram-end-to-end.md)
- [Project Management and Sprint Plan](docs/project-management-sprint-plan.md)
- [Plane Execution Sync](docs/plane-execution-sync.md)
