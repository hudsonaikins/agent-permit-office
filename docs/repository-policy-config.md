# Repository Policy Configuration

Sprint 16 adds repo-local policy configuration.

Default file:

```text
agent-permit-policy.json
```

The scanner auto-loads this file when it exists in the scanned repo root. You can also pass an explicit path:

```bash
uv run agent-permit scan . --ci --policy agent-permit-policy.json
```

## Example

```json
{
  "version": 1,
  "allowed_mcp_servers": ["github-tools"],
  "approved_credential_refs": ["REVIEW_TOKEN"],
  "trusted_workflow_permissions": [
    {
      "path": ".github/workflows/agent.yml",
      "event": "pull_request",
      "scope": "contents"
    }
  ],
  "severity_overrides": {
    "ci-write-permission": "low"
  }
}
```

## Fields

| Field | Meaning |
| --- | --- |
| `allowed_mcp_servers` | MCP server names that are accepted for local use. Matching `mcp-stdio-credential-ref` findings are lowered to `low`, and credential-to-MCP graph paths for that server are lowered to `low`. |
| `approved_credential_refs` | Credential or secret names approved outside `pull_request_target`. Matching `ci-secret-reference` findings are lowered to `low`. |
| `trusted_workflow_permissions` | Scoped workflow permission entries. Matching `ci-write-permission` findings are lowered to `low`. |
| `severity_overrides` | Rule-ID keyed severity overrides. Values must be `critical`, `high`, `medium`, `low`, or `info`. |

Trusted workflow permission fields:

| Field | Required | Meaning |
| --- | --- | --- |
| `path` | yes | Workflow file path. |
| `scope` | yes | GitHub permission scope, for example `contents` or `pull-requests`. |
| `event` | no | Workflow event that must match. |
| `job` | no | Job name that must match. |

## Behavior

Policy does not delete findings.

When a policy entry matches:

- the finding remains in `raw-findings.json`
- severity can be lowered
- `requires_human_review` can become `false`
- permit status can move from `needs_review` to `approved_with_conditions`
- `policy-evaluation.json` records the adjustment

No policy means strict scanner behavior is unchanged.

Invalid policy fails before scan artifacts are created.

## Artifact

Policy scans write:

```text
.agent-permit/runs/<run_id>/policy-evaluation.json
```

This artifact contains finding IDs, rule IDs, actions, severity changes, and rationales. It does not contain raw secret values.

## GitHub Action

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

## Boundaries

Policy config is deterministic JSON. It does not use hosted state, GitHub APIs, Deep Agent output, or LLM interpretation. Broad suppressions are intentionally not supported; policy entries must match specific server names, credential names, workflow paths/scopes, or rule IDs.
