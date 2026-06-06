# Agent Permit Office Fixtures

Small synthetic repos for deterministic scanner tests.

| Fixture | Expected permit status | Purpose |
| --- | --- | --- |
| `safe-agent` | `approved` | Minimal read-only agent shape. |
| `risky-mcp-agent` | `needs_review` | Unpinned stdio MCP server receives a credential reference. |
| `poisoned-instructions` | `blocked` | Prompt/instruction file attempts approval bypass and data exfiltration. |
| `risky-ci-agent` | `blocked` | GitHub Actions workflow runs agent work from untrusted PR context with write permissions. |

Rules:

- fixtures must stay small
- fixtures must use placeholder credential names only
- fixtures must not include real secret values

