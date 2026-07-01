# Open Source Agent Access Scan Report

Date: 2026-06-30

Source artifacts: local scans executed June 28, 2026 PDT. The artifact timestamps are June 29, 2026 UTC.

## Purpose

This report answers one question:

> Before a repository gives an AI agent, MCP server, or automated workflow more access, what should a reviewer inspect first?

Agent Permit Office is not trying to prove an exploit. It is producing an access review queue. The scanner looks for places where repo automation, agent tooling, credentials, MCP config, or CI permissions create a path that should be approved, changed, or blocked before unattended agent use.

## Scope

This pass used deterministic static scanning only.

- No repository code was executed.
- No MCP server was launched.
- No CI workflow was run.
- No package script was run.
- No live Deep Agent spend was used in this pass.
- Secret values were not emitted; secret variable names may appear as evidence.

The earlier live validation harness still proves the bounded Deep Agent path. This report focuses on fresh real-repo scanner evidence that can be used in a demo and product narrative.

## Result Summary

| Repository | Commit | Result | Findings | Graph paths | Controls | Plain-English outcome |
| --- | --- | --- | ---: | ---: | ---: | --- |
| `langchain-ai/open-swe` | `6d12552` | needs review | 5 | 3 | 8 | Review before approving agent automation. The repo has workflow secrets and write permissions that a reviewer should confirm are only reachable from trusted workflow contexts. |
| `github/github-mcp-server` | `8cd03c0` | needs review | 26 | 9 | 35 | Review before approving. Several workflows combine write permissions and secret references. Validate that each workflow is trusted and least-privilege. |
| `mcp-use/mcp-use` | `648ac11` | blocked | 84 | 22 | 105 | Block unattended agent automation until the risky CI trust paths are fixed or explicitly approved. The repo includes pull-request-target patterns, write permissions, secret references, and an MCP network path. |
| `wanxingai/LightAgent` | `4517cd7` | approved | 0 | 0 | 0 | Approve from this scanner. No configured Agent Permit Office risk matched. |
| `CopilotKit/open-multi-agent-canvas` | `25f20b2` | approved | 0 | 0 | 0 | Approve from this scanner. No configured Agent Permit Office risk matched. |

## What Worked

The scanner produced all three review states against real public repositories:

- `approved`: no configured policy matched.
- `needs_review`: risk exists, but a human can approve after checking context.
- `blocked`: unattended agent access should not proceed without remediation or explicit exception.

That matters because this product is a permit gate, not another generic scanner. The useful output is a decision queue: approve, review, or block access before an agent is allowed to operate.

## Repository Evidence

### `langchain-ai/open-swe`

Commit:

- `6d125526d0ce1d859a9836322a5b59e3be3b997e`
- Date: `2026-06-26T16:08:38-07:00`
- Message: `hotfix: stop prompting agent/reviewer to wrap installs in sfw (#1625)`

Result:

- Status: needs review
- Findings: 5
- Graph paths: 3
- Controls: 8

Rules found:

- `ci-secret-reference`: 4
- `ci-write-permission`: 1

Examples:

- `.github/workflows/pr_lint.yml:17` references `GITHUB_TOKEN`.
- `.github/workflows/promote_main_to_prod.yml:4` grants `contents: write`.
- `.github/workflows/reviewer_eval.yml:90` references `LANGSMITH_API_KEY`.
- `.github/workflows/reviewer_eval.yml:91` references `LANGSMITH_API_KEY`.
- `.github/workflows/reviewer_eval.yml:92` references `ANTHROPIC_API_KEY`.

Reviewer question:

> Can agent or review automation in this repo reach CI secrets or write permissions from an untrusted workflow context?

Product value:

This is a clean needs-review example. The repo should not be called unsafe by default, but a security reviewer needs a short queue of exact workflow files and secret or permission references before approving wider agent automation.

Artifact directory:

```text
/tmp/agent-permit-open-source-validation/langchain-ai__open-swe/.agent-permit/runs/actual-open-swe-20260628171050/
```

### `github/github-mcp-server`

Commit:

- `8cd03c018525ae0bafc9b3cdb84ec2133e01bac2`
- Date: `2026-06-27T09:19:50+02:00`
- Message: `Add reaction tools for issues and pull requests (#2732)`

Result:

- Status: needs review
- Findings: 26
- Graph paths: 9
- Controls: 35

Rules found:

- `ci-secret-reference`: 11
- `ci-write-permission`: 15

Examples:

- `.github/workflows/ai-issue-assessment.yml:11` grants `issues: write`.
- `.github/workflows/ai-issue-assessment.yml:22` references `GITHUB_TOKEN`.
- `.github/workflows/close-inactive-issues.yml:14` grants `issues: write`.
- `.github/workflows/close-inactive-issues.yml:15` grants `pull-requests: write`.
- `.github/workflows/close-inactive-issues.yml:28` references `GITHUB_TOKEN`.
- `.github/workflows/code-scanning.yml:24` grants `security-events: write`.
- `.github/workflows/code-scanning.yml:66` references `GITHUB_REGISTRIES_PROXY`.
- `.github/workflows/docker-publish.yml:36` grants `packages: write`.
- `.github/workflows/docker-publish.yml:39` grants `id-token: write`.
- `.github/workflows/docker-publish.yml:67` references `GITHUB_TOKEN`.

Reviewer question:

> Which GitHub Actions workflows should retain write permissions or secret access before an AI agent or MCP workflow is allowed to automate repository activity?

Product value:

This is a realistic enterprise case. The repo has legitimate automation, but many workflows deserve least-privilege review before agent automation is layered on top.

Artifact directory:

```text
/tmp/agent-permit-open-source-validation/github__github-mcp-server/.agent-permit/runs/actual-github-mcp-server-20260628171050/
```

### `mcp-use/mcp-use`

Commit:

- `648ac110b38b21311e4c3f01e4ce67a7477aec14`
- Date: `2026-06-26T17:41:12+02:00`
- Message: `docs: exclude auto-generated Python API reference from docs search`

Result:

- Status: blocked
- Findings: 84
- Graph paths: 22
- Controls: 105

Rules found:

- `ci-pr-target-write-token`: 2
- `ci-pull-request-target`: 2
- `ci-secret-reference`: 48
- `ci-write-permission`: 32

Examples:

- `.github/workflows/approve-fork-pr.yml:12` grants `contents: write`.
- `.github/workflows/auto-label.yml:7` grants `issues: write`.
- `.github/workflows/auto-label.yml:8` grants `pull-requests: write`.
- `.github/workflows/auto-label.yml:21` references `GITHUB_TOKEN`.
- `.github/workflows/bump-mcp-use-reusable.yml:7` grants `contents: write`.
- `.github/workflows/ci.yml:258` grants `pull-requests: write`.
- `.github/workflows/ci.yml:423` grants `pull-requests: write`.
- `.github/workflows/ci.yml:554` references `OPENAI_API_KEY`.
- `.github/workflows/ci.yml:579` references `OPENAI_API_KEY`.
- `.github/workflows/ci.yml:692` references `LANGFUSE_PUBLIC_KEY`.

Graph path example:

```text
file:.mcp.json -> mcp-server:.mcp.json:mcp-use-docs -> network-endpoint:https://manufact.com/docs/mcp
```

Scanner rationale:

```text
Repository MCP config can route tool traffic to a network endpoint.
```

Reviewer question:

> Should unattended agent automation be allowed while this repo has pull-request-target patterns, CI write permissions, secret references, and an MCP network route?

Product value:

This is the blocked demo case. It shows why the scanner is not only looking for secrets or only looking for CI permissions. The value is the combined access path: workflow trust, write scopes, credential references, and agent/MCP routing.

Artifact directory:

```text
/tmp/agent-permit-open-source-validation/mcp-use__mcp-use/.agent-permit/runs/actual-mcp-use-20260628171050/
```

### `wanxingai/LightAgent`

Commit:

- `4517cd7858504f590a6b1af1ba7c286d31b16f08`
- Date: `2026-06-24T15:31:23+08:00`
- Message: `docs: sync localized READMEs for v0.9.0 (#65)`

Result:

- Status: approved
- Findings: 0
- Graph paths: 0
- Controls: 0

Reviewer question:

> Did this scanner find any configured policy reason to stop agent access?

Answer:

No. This run found no configured Agent Permit Office risk.

Artifact directory:

```text
/tmp/agent-permit-open-source-validation/wanxingai__LightAgent/.agent-permit/runs/actual-lightagent-20260628171050/
```

### `CopilotKit/open-multi-agent-canvas`

Commit:

- `25f20b22e7afe3277b6c350c14ef4d54f7147e49`
- Date: `2026-06-04T21:59:57-05:00`
- Message: `fix: point Copilot Cloud links at the Intelligence dashboard`

Result:

- Status: approved
- Findings: 0
- Graph paths: 0
- Controls: 0

Reviewer question:

> Did this scanner find any configured policy reason to stop agent access?

Answer:

No. This run found no configured Agent Permit Office risk.

Artifact directory:

```text
/tmp/agent-permit-open-source-validation/CopilotKit__open-multi-agent-canvas/.agent-permit/runs/actual-open-multi-agent-canvas-20260628171050/
```

## How This Becomes A DevSecOps Feature

Feature name:

```text
AI Agent Access Review
```

Where it fits:

- Before enabling an AI coding agent on a repo.
- Before installing a new MCP server.
- Before granting a workflow new write permissions.
- Before letting agent automation run on pull requests.
- Before approving a production-facing agent tool.

Platform surfaces:

- GitHub check: fail or warn on blocked agent-access paths.
- SARIF or code scanning alert: show exact files and policy rules.
- Dashboard queue: route findings to AppSec, DevEx, or platform owners.
- Pull request comment: plain-English reviewer question plus exact evidence.
- Policy gate: require approval before agent/MCP access is enabled.

What this adds beyond normal security tooling:

- SAST asks whether code has exploitable flaws.
- Secret scanners ask whether secrets leaked.
- CI linters ask whether workflow syntax is valid.
- Agent Permit Office asks whether an agent-access path should be permitted.

That is the product wedge.

## What Still Needs Work

1. CI findings need better grouping by workflow and job.
2. Write-permission findings need stronger severity tuning so benign maintenance jobs do not overwhelm the queue.
3. The dashboard should show reviewer questions first, then evidence.
4. Deep Agent evidence should be framed as explanation and citation checking, not as the source of truth.
5. The one-command demo should output this kind of customer-readable report automatically.

## Next Build Target

The next sprint should turn this report shape into product behavior:

1. Generate a plain-English scan report from `.agent-permit/runs/<run_id>/`.
2. Make the dashboard detail page use the same reviewer-question structure.
3. Add a local demo command that scans the open-source manifest and exports a customer-ready HTML report.
4. Add tests that assert approved, needs-review, and blocked repo examples render with clear reviewer language.

