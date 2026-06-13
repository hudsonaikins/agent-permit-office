# Demo

Use this script to show Agent Permit Office as a permit workflow, not a generic scanner.

## Demo Thesis

Talk track:

```text
AI agents now sit near repo files, MCP tools, CI tokens, and credentials. Agent Permit Office answers one operational question before the agent runs: should this repo be allowed to give that agent access?
```

The demo should prove four things:

- deterministic scanner finds risky agent capability paths without executing code
- permit status is explainable through local artifacts
- Deep Agent evidence is bounded by scanner artifacts and citation-checked
- dashboard turns repo evidence into a review workflow a security or platform team can use

## No-Spend Default

Start with local deterministic commands. Do not call OpenRouter, Phoenix upload, hosted APIs, or external services unless the demo explicitly needs the live Deep Agent path.

Install once:

```bash
uv sync --all-extras --dev
```

## Fixture Warm-Up

### Safe Agent

```bash
uv run agent-permit scan tests/fixtures/safe-agent --ci --run-id demo-safe
```

Expected:

```text
Permit status: approved
CI mode: on
```

Open:

```text
tests/fixtures/safe-agent/.agent-permit/runs/demo-safe/summary.md
tests/fixtures/safe-agent/.agent-permit/runs/demo-safe/permit.yaml
```

Message:

```text
Clean repos should pass quickly. A useful permit system cannot only find bad news.
```

### Risky GitHub Actions Agent

```bash
uv run agent-permit scan tests/fixtures/risky-ci-agent --ci --run-id demo-risky || true
```

Expected:

```text
Permit status: blocked
CI mode: on
```

Open:

```text
tests/fixtures/risky-ci-agent/.agent-permit/runs/demo-risky/summary.md
tests/fixtures/risky-ci-agent/.agent-permit/runs/demo-risky/risk-report.md
tests/fixtures/risky-ci-agent/.agent-permit/runs/demo-risky/permit.yaml
tests/fixtures/risky-ci-agent/.agent-permit/runs/demo-risky/raw-findings.json
tests/fixtures/risky-ci-agent/.agent-permit/runs/demo-risky/graph-paths.json
```

Message:

```text
This is not style lint. The scanner connects privileged PR workflow context, write permissions, and secret references into a blocked permit decision.
```

### Risky MCP Agent

```bash
uv run agent-permit scan tests/fixtures/risky-mcp-agent --ci --run-id demo-mcp || true
```

Expected:

```text
Permit status: needs_review
CI mode: on
```

Message:

```text
MCP config can connect local files, external tools, and credential references. The scanner records variable names and capability paths, not raw secret values.
```

## Self-Scan

This repository contains intentionally risky fixtures. Exclude them when scanning the project itself:

```bash
uv run agent-permit scan . --ci --exclude "tests/fixtures/**"
```

Expected:

```text
Permit status: approved
CI mode: on
```

If this fails, use the failure as product evidence only after checking whether a real repo risk or doc/example drift caused it.

## Open-Source Demo Package

Fast dry run without model spend:

```bash
uv run agent-permit open-source-demo docs/evals/open-source-live-repos.json \
  --repo-root /tmp/agent-permit-open-source-validation \
  --run-id open-source-demo-prep \
  --skip-live
```

Expected:

```text
Open source demo report:
.agent-permit/open-source-demos/open-source-demo-prep/open-source-demo-report.md
.agent-permit/open-source-demos/open-source-demo-prep/open-source-demo-report.html
.agent-permit/open-source-demos/open-source-demo-prep/open-source-demo-results.json
```

Use this to prove repo prep, reporting, and packaging without LLM cost.

## Live Deep Agent Path

Use only when OpenRouter credits/API access are available and the demo needs a live Deep Agent report.

```bash
export OPENROUTER_API_KEY=<key>
OPENROUTER_TIMEOUT_SECONDS=30 \
OPENROUTER_MAX_COMPLETION_TOKENS=2400 \
PHOENIX_COLLECTOR_ENDPOINT=http://localhost:6006 \
uv run --extra deep-agent --extra phoenix agent-permit open-source-demo \
  docs/evals/open-source-live-repos.json \
  --repo-root /tmp/agent-permit-open-source-validation \
  --run-id open-source-live-demo \
  --agent-recursion-limit 20 \
  --phoenix \
  --exclude ".agent-permit/**"
```

Expected:

```text
Open source demo report:
.agent-permit/open-source-demos/open-source-live-demo/open-source-demo-report.md
.agent-permit/open-source-demos/open-source-live-demo/open-source-demo-report.html
.agent-permit/open-source-demos/open-source-live-demo/open-source-demo-results.json
```

Message:

```text
The model does not inspect arbitrary repo state. It investigates bounded scanner artifacts, writes a cited report, and the citation critic checks the claims.
```

## Dashboard And Proof Pack

Refresh dashboard data from local artifacts:

```bash
python3 tools/export_dashboard_snapshot.py
```

Write a sanitized proof pack:

```bash
python3 tools/export_dashboard_snapshot.py --proof-pack
```

Expected:

```text
Dashboard snapshot: dashboard/src/data/generated/dashboardSnapshot.json
Proof pack: .agent-permit/proof-packs/<validation_run_id>
Proof pack zip: .agent-permit/proof-packs/<validation_run_id>.zip
```

Run dashboard:

```bash
cd dashboard
bun install
bun dev
```

Open the Vite localhost URL.

## Dashboard Walkthrough

1. Start at the sidebar.

   Message:

   ```text
   Sidebar is not app navigation yet. It is a review workflow: current decision, repo/finding/path scope, then the three steps a reviewer follows.
   ```

2. Use the top header.

   Show:

   - run title
   - repo, branch, run id
   - dark mode toggle
   - Export action

   Message:

   ```text
   Header anchors the active validation run. Dark mode exists because security teams often present this in low-light review rooms, but it uses the same evidence hierarchy.
   ```

3. Change review scope.

   Use:

   - `Repository` dropdown
   - `Run` dropdown
   - artifact availability badge

   Message:

   ```text
   Scope decides which evidence set the queue represents: all repos, one repo, or one run. Artifact availability tells whether local proof is complete, partial, or missing.
   ```

4. Read the decision snapshot.

   Show:

   - verdict card
   - findings count
   - blocked repo count
   - citation coverage
   - cache hit

   Message:

   ```text
   These numbers are not generic analytics. They answer: can this validation set pass unattended, what blocks it, is the Deep Agent grounded, and how much model cost was saved by caching?
   ```

5. Work the findings spreadsheet.

   Use:

   - saved views
   - severity filter
   - search
   - selected finding row

   Message:

   ```text
   The spreadsheet is the operating surface. Rows are sorted by risk so AppSec can start with blocked/high-severity paths and inspect evidence without reading every artifact manually.
   ```

6. Inspect selected finding evidence.

   Show:

   - selected finding ID and status
   - rule, severity, owner
   - scanner evidence
   - capability path
   - remediation

   Message:

   ```text
   Each finding ties a scanner rule to a capability path and a permit decision. The reviewer can request changes or approve a documented exception.
   ```

7. Explain the Decision Log.

   Show:

   - scanner step
   - graph step
   - permit step
   - Deep Agent/citation step when available

   Message:

   ```text
   Decision Log is the audit spine. It shows how the decision moved from deterministic evidence to graph reasoning to permit outcome to Deep Agent grounding.
   ```

8. Open the artifact drawer.

   Click an artifact row under `Selected finding evidence` -> `Evidence` -> `Artifacts`.

   Show:

   - interpreted artifact insight
   - path
   - kind
   - size
   - raw preview

   Message:

   ```text
   Artifact drawer keeps the reviewer in context. The app interprets the artifact first, then exposes raw evidence for trust and debugging.
   ```

9. Show proof pack output.

   Open:

   ```text
   .agent-permit/proof-packs/<validation_run_id>/proof-pack-report.md
   .agent-permit/proof-packs/<validation_run_id>/proof-pack-manifest.json
   .agent-permit/proof-packs/<validation_run_id>/dashboard/dashboardSnapshot.json
   ```

   Message:

   ```text
   Proof pack is the handoff artifact for customer discovery, security review, and later audit retention. It is allowlisted and redacted before export.
   ```

## Partial Proof Limitation

If the proof pack manifest says `partial`, explain it directly:

```text
This pack was generated from older Sprint 23 validation metadata that referenced temp repo directories. The aggregate report and dashboard snapshot remain useful for a demo, but missing per-repo artifacts mean it is not complete audit evidence. A fresh live validation rerun will preserve durable per-repo artifacts and make the pack complete.
```

Do not present a partial proof pack as complete customer evidence.

## What Not To Show

- raw `.env` files
- private customer repos
- full Phoenix trace payloads
- provider generation IDs unless needed for debugging
- generated `.agent-permit/` directories as committed source artifacts
- hosted workflow claims before the hosted product exists

## Close

End with the open-core story:

```text
The scanner, rules, artifacts, local Deep Agent path, and dashboard proof workflow can be open. Paid product value comes from managed multi-repo workflow, private repo connectors, policy packs, retention, SSO/RBAC, and model gateway governance.
```
