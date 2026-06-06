# SARIF And Code Scanning

Sprint 14 adds deterministic SARIF output for GitHub code scanning.

SARIF is generated only from scanner artifacts. Deep Agent investigations do not create SARIF findings.

## Commands

Generate SARIF during scan:

```bash
uv run agent-permit scan . --ci --sarif
```

Generate SARIF from existing artifacts:

```bash
uv run agent-permit sarif .agent-permit/runs/<run_id>
```

Default output:

```text
.agent-permit/runs/<run_id>/results.sarif
```

## Mapping

| Agent Permit severity | SARIF level | GitHub `security-severity` |
| --- | --- | --- |
| `critical` | `error` | `9.0` |
| `high` | `error` | `7.0` |
| `medium` | `warning` | `5.0` |
| `low` | `note` | `2.0` |
| `info` | `note` | `1.0` |

Each result includes:

- stable `ruleId`
- `ruleIndex`
- file URI and line range
- deterministic partial fingerprint
- finding metadata: severity, confidence, category, human-review flag

SARIF intentionally omits source snippets. Locations point reviewers to the right file and line without repeating workflow secret references or raw environment text in the upload artifact.

## GitHub Action Upload

Generate SARIF without upload:

```yaml
with:
  path: .
  sarif: "true"
```

Upload SARIF:

```yaml
permissions:
  contents: read
  security-events: write

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

Upload is opt-in and non-blocking. The action still enforces permit status using the scan exit code.

## References

- OASIS SARIF 2.1.0: https://docs.oasis-open.org/sarif/sarif/v2.1.0/os/sarif-v2.1.0-os.html
- GitHub SARIF upload docs: https://docs.github.com/en/code-security/how-tos/find-and-fix-code-vulnerabilities/integrate-with-existing-tools/upload-sarif-file
- GitHub SARIF support docs: https://docs.github.com/en/code-security/reference/code-scanning/sarif-files/sarif-support
