# PermitGraph Proof Pack Export

Date: 2026-06-12

## Purpose

The proof pack is a local, shareable evidence bundle for customer demos and discovery calls. It packages the dashboard snapshot, validation report, scanner artifacts, metrics, and optional SARIF into one sanitized directory plus zip file.

## Generate

```bash
python3 tools/export_dashboard_snapshot.py --proof-pack
```

The exporter prints both paths:

```text
Proof pack: .agent-permit/proof-packs/<validation_run_id>
Proof pack zip: .agent-permit/proof-packs/<validation_run_id>.zip
```

## Contents

The pack is allowlisted. It may include:

- `proof-pack-report.md`
- `proof-pack-manifest.json`
- `dashboard/dashboardSnapshot.json`
- `validation/live-repo-validation-results.json`
- `validation/live-repo-validation-report.md`
- `scan/permit.yaml`
- `scan/raw-findings.json`
- `scan/graph-paths.json`
- `scan/run-metrics.json`
- `scan/results.sarif` when present
- optional scanner reports such as `summary.md`, `risk-report.md`, `controls.json`, and `agent-investigation.md`
- durable repo-level artifacts when they exist under `.agent-permit/live-repo-validations/<run_id>/repos/...`

## Sanitization

The exporter does not copy arbitrary local files. It copies only allowlisted artifact names and applies redaction before writing the pack:

- JSON values under sensitive key names are replaced with `[redacted]`.
- Text assignments that look like tokens, secrets, passwords, API keys, authorization values, or private keys are redacted.
- Secret variable names may remain when they are evidence, but raw secret values should not be exported.

## Partial Packs

Old Sprint 23 validation artifacts may reference deleted `/private/tmp/...` repo directories. In that case the proof pack is marked `partial` and the manifest lists missing per-repo files. Regenerate live validation to produce durable repo artifacts before using the proof pack as complete audit evidence.
