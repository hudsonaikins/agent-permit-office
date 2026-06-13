# Sanitized Demo Artifacts

Date: 2026-06-07

## Decision

Do not commit generated `.agent-permit/` run directories by default.

For public launch, commit only a small sanitized demo artifact set after a manual scrub.

Recommended public artifact:

```text
docs/demo-artifacts/open-source-demo-report.html
docs/demo-artifacts/open-source-demo-report.md
docs/demo-artifacts/open-source-demo-results.json
```

This folder does not exist yet. Add it only after choosing the exact report to publish.

## Sprint 35 Release Candidate Policy

The release candidate does not commit demo artifacts yet.

Reason:

- current old proof packs can be partial when they reference temp repo checkout paths that no longer exist
- a public artifact needs a fresh no-spend or live validation run
- live validation needs OpenRouter credits/API access and explicit spend approval
- committed reports must be manually scrubbed after generation

Until then, publish the command path and scrub policy, not generated evidence.

## Why

Generated scan artifacts can include:

- private local paths
- live run IDs
- model generation IDs
- token usage metadata
- repository commit SHAs
- workflow file paths
- finding snippets from scanned repositories
- trace or provider metadata

The scanner is designed not to emit raw secret values, but public demo artifacts still need a human review before commit.

## Safe Public Demo Strategy

Use the existing no-spend path first:

```bash
uv run agent-permit open-source-demo docs/evals/open-source-live-repos.json \
  --repo-root /tmp/agent-permit-open-source-validation \
  --run-id public-demo-smoke \
  --skip-live
```

Use the live path only when a model-key-backed demo report is needed:

```bash
export OPENROUTER_API_KEY=<key>
uv run --extra deep-agent --extra phoenix agent-permit open-source-demo \
  docs/evals/open-source-live-repos.json \
  --repo-root /tmp/agent-permit-open-source-validation \
  --run-id public-demo-live \
  --agent-recursion-limit 20 \
  --exclude ".agent-permit/**"
```

Then copy only the final report files into `docs/demo-artifacts/` after review.

## Scrub Checklist

Before committing demo artifacts:

- no raw API keys or token-like values
- no `.env.local` values
- no local home directory paths
- no private repo names
- no private organization names
- no customer data
- no provider generation IDs if not needed for public proof
- no Phoenix trace payloads
- no large generated run directories
- no unsupported Deep Agent claims
- citation critic result passed for live reports

Suggested checks:

```bash
rg -n "OPENROUTER|API_KEY|TOKEN|SECRET|PASSWORD|/Users/|hudson|generation_id|trace" docs/demo-artifacts
uv run agent-permit scan . --ci --exclude "tests/fixtures/**"
```

If a report fails the scrub, regenerate or redact it before commit.

## What Not To Publish

Do not publish:

- `.env.local`
- full `.agent-permit/runs/` directories
- Phoenix trace exports
- customer repository reports
- private repo validation manifests
- provider response headers
- screenshots containing local filesystem paths or secrets

## Future Improvement

Add a `agent-permit demo-sanitize` command later if sanitized demo publishing becomes frequent.
