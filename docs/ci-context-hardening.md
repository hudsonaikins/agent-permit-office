# CI Context Hardening

Date: 2026-06-06

## Delivered

CI findings now carry structured workflow context:

- `workflow_event`
- `workflow_job`
- `permission_scope`
- `secret_name`
- `context_note`

Summaries and risk reports surface that context in top findings.

## Why

The first real-repo validation pass proved the scanner can find useful CI risks, but raw `ci-write-permission` and `ci-secret-reference` findings were too flat. A developer needs to know whether the finding is tied to:

- pull request execution
- a specific job
- a specific permission scope
- a specific secret name
- a likely maintenance workflow

This makes the review actionable without needing to open the workflow file first.

## Public Repo Validation

Re-ran the same public repos with `validation5-*` run IDs.

| Repo | Permit | Findings | Context improvement |
| --- | --- | ---: | --- |
| `open_deep_research` | `needs_review` | 4 | shows pull request event, Claude review jobs, `id-token` scope, Anthropic secret reference |
| `crewAI-examples` | `needs_review` | 3 | marks stale workflow as maintenance heuristic with issues/pull-request scopes |
| `autogen` | `needs_review` | 32 | shows pull request jobs, Codecov/OpenAI secrets, security-events/pages/packages scopes |

All investigation reports passed citation checks.

## Example

```text
ci-secret-reference at .github/workflows/checks.yml:261
(event=pull_request, job=codecov, secret=CODECOV_TOKEN)
```

```text
ci-write-permission at .github/workflows/stale.yml:12
(job=stale, scope=issues, maintenance)
```

## Scope

This is still lightweight YAML context tracking, not a full GitHub Actions semantic parser.

Current method:

- line-based event detection
- line-based job tracking inside `jobs:`
- line-based permission and secret extraction
- heuristic maintenance context from workflow path/job names

## Next

- distinguish top-level permissions from job-level permissions explicitly
- parse event filters such as branches, paths, and workflow triggers
- group findings by workflow/job in the report
- add JSON output for `agent-permit rules`
