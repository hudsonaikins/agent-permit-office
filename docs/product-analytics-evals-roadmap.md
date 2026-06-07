# Product Analytics And Evals Roadmap

Date: 2026-06-07

## Current State

Agent Permit Office has engineering observability and local eval plumbing.

It does not yet have hosted product analytics because there is no hosted control plane, account model, or customer workspace.

## Existing Plumbing

| Layer | Status | Artifact |
| --- | --- | --- |
| Deterministic scan evidence | built | `.agent-permit/runs/<run_id>/` |
| Permit decision | built | `permit.yaml` |
| Human report | built | `summary.md`, `risk-report.md` |
| Deep Agent report | built | `agent-investigation.md` |
| Citation critic | built | command exit, `live-validation.json` |
| Aggregate severity validation | built | citation critic aggregate checks |
| Run metrics | built | `run-metrics.json` |
| OpenRouter usage | built | `openrouter-usage.json` |
| Live validation | built | `live-validation.json` |
| Fixture evals | built | `.agent-permit/evals/<run_id>/eval-results.json` |
| Phoenix dataset rows | built | `phoenix-dataset-rows.jsonl` |
| Real repo evals | built | `.agent-permit/real-repo-evals/<run_id>/` |
| Live repo evals | built | `.agent-permit/live-repo-validations/<run_id>/` |
| Phoenix traces | optional | OpenTelemetry spans with `--phoenix` |
| LangSmith traces | optional | LangSmith trace env with `--langsmith` |

## Gaps

Missing product analytics:

- org, user, repo, and workspace identity
- persisted scan history
- active repo count
- time-to-first-scan
- scan frequency
- finding acceptance and suppression rate
- false-positive feedback
- approval workflow metrics
- customer-level model spend
- hosted dashboard funnel
- retention and churn signals

Missing eval analytics:

- trend file across eval runs
- severity aggregate consistency score
- Deep Agent citation failure rate over time
- model quality comparison
- cache hit trend
- cost per successful report
- runtime latency metrics
- failure taxonomy

## Recommended Next Build

### 1. `run-metrics.json`

Write one normalized metrics artifact for every scan and live validation.

Status: built in Sprint 29.

Shape:

```json
{
  "version": 1,
  "run_id": "example",
  "run_type": "live_validation",
  "target_hash": "repo-fingerprint",
  "status": "passed",
  "permit_status": "blocked",
  "files_indexed": 4989,
  "findings": 54,
  "finding_severity_counts": {
    "critical": 2,
    "high": 2,
    "medium": 50,
    "low": 0,
    "info": 0
  },
  "graph_paths": 6,
  "controls": 60,
  "credentials": 11,
  "mcp_servers": 0,
  "citation_check_status": "passed",
  "aggregate_mismatches": 0,
  "model": "openrouter:anthropic/claude-sonnet-4.6",
  "model_calls": 4,
  "total_tokens": 54336,
  "cached_tokens": 35159,
  "cache_hit_ratio": 0.6749
}
```

Reason:

- single dashboard-ready payload
- easier eval trend analysis
- easier hosted ingestion later
- sanitized target fingerprint instead of raw repo path

### 2. `analytics-events.jsonl`

Write local product-style events without sending them anywhere.

Events:

- `scan_started`
- `scan_completed`
- `permit_decided`
- `investigation_started`
- `investigation_completed`
- `citation_check_failed`
- `live_validation_completed`
- `eval_completed`

No user identity. No repo contents. No secret values.

### 3. Eval Trend Report

Add:

```text
.agent-permit/eval-trends/<run_id>/
  eval-trends.json
  eval-trends.md
```

Metrics:

- pass rate
- permit status accuracy
- expected rule coverage
- citation failure rate
- aggregate mismatch rate
- token cost proxy
- cache hit ratio

### 4. Product Analytics Schema

Design hosted schema before implementation:

- `organizations`
- `users`
- `repositories`
- `scan_runs`
- `permit_decisions`
- `findings`
- `policy_adjustments`
- `approvals`
- `model_usage`
- `eval_runs`

Do not build hosted analytics until repo-level local metrics are stable.

## Product Questions To Answer

Analytics should answer:

- How many repos scanned?
- How many repos blocked?
- Which rules drive most blocks?
- Which findings are repeatedly accepted as safe?
- Which rules cause false positives?
- How often does Deep Agent fail citation or aggregate checks?
- What is model spend per report?
- What is cache hit rate by repo/run?
- Which users complete first scan?
- Which teams move from scan to approval workflow?

## Decision

Next analytics work should stay local-first:

```text
analytics-events.jsonl + eval trend report + local dashboard
```

Hosted product analytics comes later with the open-core control plane.
