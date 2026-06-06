# Real Repo Validation

Date: 2026-06-06

Validation used shallow public clones in `/tmp/agent-permit-validation`. Clones are not committed.

## Repositories

| Repo | Source |
| --- | --- |
| `open_deep_research` | <https://github.com/langchain-ai/open_deep_research> |
| `crewAI-examples` | <https://github.com/crewAIInc/crewAI-examples> |
| `autogen` | <https://github.com/microsoft/autogen> |

## Commands

```bash
git clone --depth 1 https://github.com/langchain-ai/open_deep_research.git /tmp/agent-permit-validation/open_deep_research
git clone --depth 1 https://github.com/crewAIInc/crewAI-examples.git /tmp/agent-permit-validation/crewAI-examples
git clone --depth 1 https://github.com/microsoft/autogen.git /tmp/agent-permit-validation/autogen
```

```bash
uv run agent-permit scan /tmp/agent-permit-validation/open_deep_research --ci --run-id validation3-open_deep_research
uv run agent-permit scan /tmp/agent-permit-validation/crewAI-examples --ci --run-id validation3-crewAI-examples
uv run agent-permit scan /tmp/agent-permit-validation/autogen --ci --run-id validation3-autogen
```

Each run was followed by:

```bash
uv run agent-permit investigate /tmp/agent-permit-validation/<repo>/.agent-permit/runs/<run_id>
```

## Results

| Repo | Permit | Findings | Graph paths | Controls | Main rules |
| --- | --- | ---: | ---: | ---: | --- |
| `open_deep_research` | `needs_review` | 4 | 2 | 6 | 2 `ci-secret-reference`, 2 `ci-write-permission` |
| `crewAI-examples` | `needs_review` | 3 | 1 | 4 | 1 `ci-secret-reference`, 2 `ci-write-permission` |
| `autogen` | `needs_review` | 32 | 9 | 41 | 20 `ci-secret-reference`, 12 `ci-write-permission` |

All investigation reports passed citation checks.

## Finding

The scanner found real CI review needs in all three repos: workflow secret references and write permissions. None of the tested repos triggered `pull_request_target` critical rules in this pass, so the correct output is `needs_review`, not `blocked`.

## Bug Found And Fixed

Initial validation exposed two issues:

- Evidence loader redacted raw JSON text before parsing. Workflow syntax such as `${{ secrets.NAME }}` could break JSON loading. Fix: parse JSON first; keep redaction on free-text artifact reads.
- Workflow graph paths escalated medium CI findings to critical path severity. Fix: workflow path severity is `high`; critical status comes from critical CI findings like `ci-pr-target-write-token` or `ci-pr-target-head-checkout`.

## Product Notes

- Real repo signal is useful now, but CI findings need better workflow context.
- `ci-write-permission` should eventually distinguish dangerous jobs from benign maintenance jobs.
- `ci-secret-reference` should include event context and job scope in reports.
- Agent/MCP findings were sparse in these repos because no MCP configs were found.
- Prompt instruction scanning did not fire because these repos did not expose `AGENTS.md`, `CLAUDE.md`, or `.codex/skills/**/SKILL.md` patterns.

## Next Hardening

- add `--format json` for `agent-permit rules`
- distinguish top-level permissions from job-level permissions explicitly
- group CI findings by workflow/job in reports
