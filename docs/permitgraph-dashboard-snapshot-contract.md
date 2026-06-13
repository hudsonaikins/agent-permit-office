# PermitGraph Dashboard Snapshot Contract

Date: 2026-06-12

## Decision

PermitGraph reads one generated JSON snapshot:

```text
dashboard/src/data/generated/dashboardSnapshot.json
```

The current contract version is:

```text
permitgraph.dashboard.snapshot.v1
```

The exporter owns this contract. The frontend should not read scattered `.agent-permit` files directly.

## Top-Level Shape

```text
contractVersion
generatedAt
selectedRunId
source
runMeta
repos[]
runs[]
summary
savedViews[]
findings[]
artifactPreviews{}
runDetails{}
decisionLog[]
traceSteps[]
policyControls[]
proofPack
```

## Responsibilities

| Field | Purpose |
| --- | --- |
| `contractVersion` | Lets future dashboard code branch safely if the generated shape changes. |
| `selectedRunId` | Default run for first render. Today this is the aggregate validation run. |
| `source` | Points back to source aggregate artifacts and latest local scan metrics. |
| `runMeta` | Header-level title, repo/suite label, branch label, run ID, and completion time. |
| `repos[]` | Repo selector data: repo identity, source, status, latest run, commit, and counts. |
| `runs[]` | Run selector data: aggregate validation run plus repo-level validation runs. |
| `summary` | Dashboard-wide totals for posture, citations, cost/cache, evals, and latest scan. |
| `savedViews[]` | Current queue filters. These are derived from `summary` and rows. |
| `findings[]` | Review rows. Today one row equals one repo validation result, not one raw finding. |
| `artifactPreviews{}` | Small inline previews keyed by artifact path. |
| `runDetails{}` | Per-run row IDs, preview paths, artifact availability, and missing artifact list. |
| `decisionLog[]` | Human-readable decision chain: scanner, graph, permit, Deep Agent, cost controls. |
| `traceSteps[]` | Existing trace-style status cards. Kept for backwards compatibility. |
| `policyControls[]` | Existing control status cards. Kept for backwards compatibility. |
| `proofPack` | Export readiness manifest: included artifacts, missing artifacts, status, reason. |

## Status Values

Permit statuses:

```text
approved
needs-review
blocked
```

Trace states:

```text
passed
review
blocked
```

Artifact status:

```text
available
partial
missing
aggregate
```

## Backwards-Compatible Defaults

The exporter must emit stable defaults:

| Missing input | Snapshot default |
| --- | --- |
| No validation file | Empty rows, zero counts, source paths set to empty or null. |
| No demo prep file | Repo commit fields become `null`, source falls back to validation result source. |
| No eval trends | `evalPassRate` becomes `null`. |
| No scan metrics | latest scan fields become `null`. |
| No per-repo artifacts | `artifactStatus: "partial"` and `missingArtifacts` lists the absent evidence files. |
| No previews | `artifactPreviews: {}` and proof pack status becomes `partial` or `missing`. |

## Artifact Preservation

Sprint 23 live validation rows reference per-repo artifact directories under `/private/tmp/...`. Those directories are not durable. Therefore `v1` must make missing per-repo artifacts explicit instead of pretending the dashboard has full evidence.

New live validation runs copy each per-repo run directory into:

```text
.agent-permit/live-repo-validations/<validation_run_id>/repos/<repo_id>/<repo_run_id>/
```

Old aggregate runs may still show `artifactStatus: "partial"` until regenerated.

## Frontend Rule

Dashboard components consume `dashboard/src/data/permitQueue.ts` exports only. They should not import generated JSON directly outside that data module.
