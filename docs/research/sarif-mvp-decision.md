# SARIF MVP Decision

Date: 2026-06-06

## Decision

Original decision: defer first-class SARIF generation from the MVP.

Sprint 14 update: SARIF is now implemented as an optional CI/product surface after rule IDs, GitHub Action packaging, Phoenix/local evals, and real-repo evals stabilized.

Ship these first:

- `agent-permit scan . --ci`
- non-zero CI exit for `needs_review` and `blocked`
- `summary.md` for PR and terminal review
- `risk-report.md`, `permit.yaml`, `controls.json`, `graph-paths.json`, and scanner JSON artifacts

SARIF was added after GitHub Action packaging became stable.

## Reasoning

SARIF is valuable, but it is a distribution feature, not the core permit engine. GitHub uses SARIF to turn third-party static-analysis output into code scanning alerts, and SARIF 2.1.0 is the standard static-analysis interchange format. That fits Agent Permit Office because the deterministic scanner already emits line-cited findings.

The MVP risk is premature alert plumbing. A useful SARIF writer needs stable rule IDs, stable file paths, deterministic severity mapping, useful result messages, and duplicate-alert behavior. GitHub code scanning relies on consistent `ruleId` values, consistent file paths, result locations, and optional `partialFingerprints` to avoid duplicate alerts across runs.

Right now, the highest-value product proof is simpler:

- can the scanner identify risky agent permission paths?
- can it produce a clear permit decision?
- can CI fail when a repo is unsafe?
- can a developer understand the top reasons without opening GitHub Security views?

Markdown plus JSON/YAML answers those questions sooner.

## Build Now

- PR-friendly `summary.md`
- deterministic exit codes
- machine-readable raw artifacts
- stable finding IDs and evidence paths
- CLI UX that works before any hosted service exists

## Deferred In MVP, Implemented In Sprint 14

- `results.sarif` writer
- `github/codeql-action/upload-sarif` workflow template
- GitHub code scanning category strategy
- `partialFingerprints` strategy
- SARIF validation tests against the 2.1.0 schema
- alert triage docs

Plane follow-up: `APO-44` Add optional SARIF writer and upload workflow. Completed in Sprint 14.

## Do Not Build Yet

- automatic upload into a user's repository without explicit opt-in
- SARIF output that includes secret values or raw environment contents
- LLM-authored SARIF findings
- unstable rule IDs that would churn code scanning alerts

## Trigger Criteria

Build SARIF when all are true:

- deterministic rule IDs are stable across at least one sprint
- each finding has one primary repo-relative file path and line
- severity mapping is fixed from permit severity to SARIF `level` and GitHub security severity
- output can validate as SARIF 2.1.0
- GitHub Action template exists and uses least-needed permissions
- generated alerts add value beyond `summary.md`

## Future Shape

The implementation now produces:

```text
.agent-permit/runs/<run_id>/
  results.sarif
  summary.md
  risk-report.md
  permit.yaml
  controls.json
  graph-paths.json
```

CLI option:

```bash
uv run agent-permit scan . --ci --sarif
```

Existing-artifact option:

```bash
uv run agent-permit sarif .agent-permit/runs/<run_id>
```

GitHub Action behavior:

- run scan
- upload artifacts
- optionally upload SARIF with non-blocking `github/codeql-action/upload-sarif`
- fail the job based on permit status, not based on SARIF upload success

Status now:

- implemented: SARIF writer from deterministic scan artifacts
- implemented: deterministic `partialFingerprints`
- implemented: optional composite action upload with least-needed permissions in caller workflow
- implemented: SARIF tests for rules, results, locations, fingerprints, and snippet omission

## Sources

- [OASIS SARIF 2.1.0 standard](https://www.oasis-open.org/standard/sarif-v2-1-0/)
- [GitHub Docs: About SARIF files for code scanning](https://docs.github.com/en/code-security/concepts/code-scanning/sarif-files)
- [GitHub Docs: SARIF support for code scanning](https://docs.github.com/en/code-security/reference/code-scanning/sarif-files/sarif-support)
- [GitHub Docs: Uploading a SARIF file to GitHub](https://docs.github.com/en/code-security/how-tos/find-and-fix-code-vulnerabilities/integrate-with-existing-tools/upload-sarif-file)
