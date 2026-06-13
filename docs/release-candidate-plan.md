# Release Candidate Plan

Date: 2026-06-13

## Decision

Sprint 35 prepares a local public release candidate without creating a remote repository, pushing branches, publishing packages, or spending model tokens.

Release candidate target:

```text
v0.1.0 local RC: installable CLI, deterministic scan, required Deep Agent path, public docs, governance, CI templates, dashboard snapshot workflow, and no generated private artifacts committed
```

## Local Verification Command

Run the full local release check:

```bash
python3 tools/release_check.py
```

The command runs:

- tracked Markdown local-link checks
- `uv run --frozen --all-extras pytest`
- `uv run --frozen agent-permit scan . --ci --exclude "tests/fixtures/**"`
- `uv build`
- `cd dashboard && bun run lint`
- `cd dashboard && bun run build`

Use narrow skips only when the missing tool is unrelated to the change:

```bash
python3 tools/release_check.py --skip-dashboard
python3 tools/release_check.py --skip-package
```

## Public Intake Surface

The release candidate includes:

- bug report issue form
- false-positive issue form
- rule-request issue form
- integration-request issue form
- pull request template

These forms ask for sanitized artifacts and explicitly reject secrets, private code, private traces, and customer data.

## Demo Artifact Policy

Do not commit generated `.agent-permit/` run directories.

Public demo artifacts stay out of the release candidate until a specific report is regenerated and manually scrubbed. The allowed future shape is:

```text
docs/demo-artifacts/open-source-demo-report.html
docs/demo-artifacts/open-source-demo-report.md
docs/demo-artifacts/open-source-demo-results.json
```

Current limitation:

- existing old proof packs can be partial when temp repo paths no longer exist
- complete audit-grade proof needs a fresh live validation rerun
- live rerun waits on OpenRouter credits/API access and explicit spend approval

## Tag Plan

Do not create or push the tag until the user approves remote publication.

Proposed local tag command after checks pass:

```bash
git tag -a v0.1.0 -m "Agent Permit Office v0.1.0"
```

Proposed remote steps after approval:

```bash
git remote add origin <repo-url>
git push -u origin main
git push origin v0.1.0
```

## Release Checklist

- [ ] `python3 tools/release_check.py` passes.
- [ ] `git status --short` has only intentional source changes.
- [ ] No `.env.local`, `.agent-permit/`, Phoenix traces, private reports, or generated build output are tracked.
- [ ] README quickstart works from a clean checkout.
- [ ] Public GitHub issue forms and PR template exist.
- [ ] `CHANGELOG.md` reflects the release.
- [ ] `ROADMAP.md` reflects current open-core direction.
- [ ] OpenRouter live proof rerun blocker is documented.
- [ ] Legal review covers Apache-2.0, trademark, CLA/DCO, and company/commercial boundary before public launch.

## Known Blockers

| Blocker | Impact | Current action |
| --- | --- | --- |
| OpenRouter `402 Insufficient credits` | Blocks fresh live Deep Agent proof rerun and APO-66 completion. | Keep blocked until credits/API access and spend approval exist. |
| No scrubbed committed demo report | Public repo lacks a durable visual proof artifact. | Keep policy documented; regenerate and scrub later. |
| No legal review | Public release can create license/trademark risk. | Treat public launch as blocked until reviewed. |
| Dashboard component tests missing | Dashboard build passes, but UI regression risk remains. | Post-RC debt unless dashboard becomes release-critical. |
