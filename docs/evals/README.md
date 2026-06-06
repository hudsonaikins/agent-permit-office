# Eval Manifests

This directory stores committed eval definitions, not cloned repos.

## Real Repos

`real-repos.json` defines the current public-repo validation set:

- `langchain-ai/open_deep_research`
- `crewAIInc/crewAI-examples`
- `microsoft/autogen`

Clone or refresh the repos separately:

```bash
mkdir -p /tmp/agent-permit-validation
git clone --depth 1 https://github.com/langchain-ai/open_deep_research.git /tmp/agent-permit-validation/open_deep_research
git clone --depth 1 https://github.com/crewAIInc/crewAI-examples.git /tmp/agent-permit-validation/crewAI-examples
git clone --depth 1 https://github.com/microsoft/autogen.git /tmp/agent-permit-validation/autogen
```

Run:

```bash
uv run agent-permit eval-real docs/evals/real-repos.json \
  --repo-root /tmp/agent-permit-validation \
  --run-id local-real-repos
```

The runner scans local checkouts and writes:

```text
.agent-permit/real-repo-evals/<run_id>/
  real-repo-eval-results.json
  real-repo-eval-report.md
```

The manifest intentionally checks expected status and rule families. It does not require exact finding counts because public repos can drift.
