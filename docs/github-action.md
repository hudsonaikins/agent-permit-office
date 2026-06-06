# GitHub Action

Agent Permit Office ships as a composite GitHub Action through `action.yml`.

## Recommended Workflow

```yaml
name: Agent Permit Office

on:
  pull_request:
  push:
    branches:
      - main
  workflow_dispatch:

permissions:
  contents: read

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v6
        with:
          persist-credentials: false

      - name: Run Agent Permit Office
        uses: OWNER/agent-permit-office@v0.1.0
        with:
          path: .
          artifact-name: agent-permit-office-${{ github.run_id }}
```

For production use, pin `OWNER/agent-permit-office` to a release tag or commit SHA.

## Inputs

| Input | Default | Meaning |
| --- | --- | --- |
| `path` | `.` | Repo path to scan, relative to `GITHUB_WORKSPACE` unless absolute. |
| `run-id` | empty | Optional deterministic scan run ID. |
| `exclude` | empty | Newline-separated gitignore-style patterns to skip. |
| `upload-artifacts` | `true` | Upload `.agent-permit/runs/<run_id>/` as a workflow artifact. |
| `artifact-name` | `agent-permit-office` | Artifact name. |
| `sarif` | `false` | Generate `results.sarif` in the scan artifact directory. |
| `upload-sarif` | `false` | Upload `results.sarif` to GitHub code scanning. Requires `security-events: write`. |
| `sarif-category` | `agent-permit-office` | Code scanning category. |
| `baseline` | empty | Optional finding baseline JSON path, relative to `GITHUB_WORKSPACE` unless absolute. |
| `ci-new-findings-only` | `false` | With `baseline`, fail CI only when new findings are introduced. |
| `policy` | empty | Optional policy JSON path, relative to `GITHUB_WORKSPACE` unless absolute. |

## Outputs

| Output | Meaning |
| --- | --- |
| `exit_code` | Scanner exit code before artifact upload. |
| `artifact_dir` | Absolute path to generated run artifacts. |
| `summary_path` | Absolute path to `summary.md`. |
| `sarif_path` | Absolute path to `results.sarif` when generated. |
| `sarif_upload_path` | Repository-relative SARIF path when possible. |

## Exit Behavior

The action runs:

```bash
agent-permit scan <path> --ci
```

It fails the job when permit status is `needs_review` or `blocked`.

Artifacts still upload before the final failure step, so failed PRs retain:

- `summary.md`
- `risk-report.md`
- `permit.yaml`
- `controls.json`
- `graph-paths.json`
- scanner JSON artifacts
- optional `results.sarif`

## SARIF And Code Scanning

Generate SARIF but keep upload off:

```yaml
permissions:
  contents: read

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
        with:
          persist-credentials: false
      - uses: OWNER/agent-permit-office@v0.1.0
        with:
          path: .
          sarif: "true"
```

Upload SARIF to GitHub code scanning:

```yaml
permissions:
  contents: read
  security-events: write

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
        with:
          persist-credentials: false
      - uses: OWNER/agent-permit-office@v0.1.0
        with:
          path: .
          upload-sarif: "true"
          sarif-category: agent-permit-office
```

Upload is opt-in because GitHub requires code scanning write permission. The upload step is non-blocking; permit enforcement remains independent, so the action fails based on permit status, not SARIF upload result.

## Baseline And Diff Mode

Use baseline mode when a repo has accepted inherited findings and you want CI to fail only on newly introduced findings.

```yaml
permissions:
  contents: read

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
        with:
          persist-credentials: false
      - uses: OWNER/agent-permit-office@v0.1.0
        with:
          path: .
          baseline: .agent-permit/finding-baseline.json
          ci-new-findings-only: "true"
```

Default `--ci` behavior is unchanged. Without `ci-new-findings-only`, the action still fails on `needs_review` or `blocked` permit status. With `ci-new-findings-only`, the action writes `finding-diff.json` and `finding-diff.md`, keeps permit status unchanged, and exits non-zero only when new findings appear.

## Policy Configuration

Use `policy` to pass a repo-local policy file:

```yaml
permissions:
  contents: read

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
        with:
          persist-credentials: false
      - uses: OWNER/agent-permit-office@v0.1.0
        with:
          path: .
          policy: agent-permit-policy.json
```

If `agent-permit-policy.json` exists at the scanned repo root, the CLI also auto-loads it. Policy mode writes `policy-evaluation.json` and keeps matching findings visible.

## Excluding Intentional Fixtures

Use `exclude` for intentionally risky fixtures, generated samples, or vendored code that should not affect the permit decision.

```yaml
with:
  path: .
  exclude: |
    tests/fixtures/**
    examples/intentionally-risky/**
```

Default scanner behavior remains strict. Exclusions are opt-in.

## Security Notes

- Use `pull_request`, not `pull_request_target`, for untrusted PR scans.
- Keep workflow permissions at `contents: read` unless SARIF upload is enabled.
- Add `security-events: write` only when `upload-sarif` is `true`.
- Keep `persist-credentials: false` on checkout unless later steps need push access.
