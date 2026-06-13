# Open Source Release Readiness

Date: 2026-06-07

## Decision

Agent Permit Office is demo-ready locally, but not yet public-release-ready.

Release target:

```text
public GitHub repo with true open-source core, clear security posture, repeatable demo, and explicit commercial boundary
```

Recommended license posture:

```text
Apache-2.0 for the open core unless counsel recommends a different OSI-approved license
```

Reason:

- the product needs developer and security-team trust
- the core scanner benefits from adoption, issues, rules, fixtures, and integrations
- OSI-approved licensing avoids calling a source-available product "open source"
- commercial value can live in hosted control plane, org workflow, policy packs, and support

Legal note: this is product planning, not legal advice. Final license, trademark, CLA/DCO, and company structure need counsel before public launch.

## Current State

Already built:

- Python `uv` package and `agent-permit` CLI
- deterministic scanner, graph builder, permit engine, reports, SARIF, baseline/diff, policy config
- required bounded LangChain Deep Agent investigation path
- OpenRouter default model path with prompt/response caching and usage artifact
- Phoenix local tracing and eval artifacts
- real-repo eval runner
- live validation harness
- open-source live validation manifest
- one-command open-source demo package with JSON, Markdown, and HTML output
- composite GitHub Action

Recent proof:

- Sprint 23 live validation: 5 recent public repos passed validation, 218,401 total tokens, 67.21% cache hit ratio.
- Sprint 24 demo smoke: repo prep 5/5, live validation skipped, JSON/Markdown/HTML demo report generated.
- Local tests at Sprint 24: 117 passed.

## Sprint 34 Readiness Note

Date: 2026-06-13

Local release hygiene pass:

| Check | Result |
| --- | --- |
| Git object size | 4.83 MiB loose objects |
| Tracked files | 157 |
| Tracked Markdown files | 54 |
| Tracked test/spec-like files | 41 |
| Markdown links | all tracked Markdown links resolve locally |
| Python package wheel | 34 files; Python package only |
| Python sdist | 157 files after excludes |
| Generated/vendor sdist leak | fixed; sdist no longer includes `dashboard/node_modules`, `dashboard/.fallow`, `dashboard/dist`, `.agent-permit`, root `dist`, `__pycache__`, or `.pytest_cache` |
| Tracked generated artifacts | no tracked `.agent-permit`, root `dist`, `dashboard/dist`, cache, or private env files |
| Tracked env files | only `.env.example` |

Commands run:

```bash
uv run pytest
uv run agent-permit scan . --ci --exclude "tests/fixtures/**"
cd dashboard && bun run lint
cd dashboard && bun run build
uv build
```

Results:

- `uv run pytest`: 119 passed.
- self-scan: approved, 0 findings, 0 graph paths, 0 controls.
- dashboard lint: passed.
- dashboard build: passed.
- `uv build`: passed after sdist excludes were added.
- secret-pattern scan produced only redaction/test literals, not live keys.

Cleanup completed:

- deleted unreachable `dashboard/src/components/ui/skeleton.tsx`
- removed unused direct `@radix-ui/react-slot` dependency from `dashboard/package.json`
- added Hatch sdist excludes for generated dashboard/vendor/cache artifacts

Residual risks:

- Fallow still reports unused shadcn exports/types. Keep for now because they are source-owned component API surface, not release leakage.
- Fallow complexity still reports high CRAP on `PermitReviewQueue.tsx` because dashboard has no component tests or runtime coverage. Treat as post-MVP refactor/test debt.
- public sanitized sample artifact still missing; do not publish generated `.agent-permit/` runs without scrub.
- current proof pack can be partial when based on old Sprint 23 temp repo paths; rerun live validation after OpenRouter credits/API access are restored.
- final public release still needs legal review for license, trademark, CLA/DCO, and commercial boundary.

## Sprint 35 Release Candidate Note

Date: 2026-06-13

Sprint 35 moves from planning docs into public-release mechanics while staying local-only:

- `tools/release_check.py` provides one local command for Markdown link checks, Python tests, self-scan, package build, dashboard lint, and dashboard build.
- `.github/ISSUE_TEMPLATE/` now includes bug, false-positive, rule-request, and integration-request forms.
- `.github/pull_request_template.md` now asks for verification, safety, scanner evidence, and docs checks.
- `docs/release-candidate-plan.md` defines the no-remote tag plan, launch checklist, demo artifact policy, and known blockers.
- No generated `.agent-permit/` run directories or live proof artifacts are committed.

## Public Release Gate

Do not publish until these are true:

| Area | Gate | Status |
| --- | --- | --- |
| License | `LICENSE` exists with chosen OSI-approved license. | added: Apache-2.0 |
| Security | `SECURITY.md` defines vulnerability reporting and no-secret policy. | added |
| Contribution | `CONTRIBUTING.md` explains rule fixtures, tests, scanner safety boundary, issue intake, and PR checks. | added |
| Conduct | `CODE_OF_CONDUCT.md` exists or project explicitly defers it. | added |
| Support | `SUPPORT.md` tells users what is community vs paid. | added |
| README | README has install, quickstart, demo, architecture, limits, and OpenRouter/Phoenix notes. | partial |
| Demo artifact | HTML report screenshot or committed sanitized sample report is linked. | strategy added; sample missing |
| Packaging | package metadata is public-ready; release tags are defined. | metadata aligned; local tag plan added |
| CI | GitHub Actions run tests and self-scan with fixture exclusions. | added |
| Secret hygiene | no `.env.local`, generated private reports, API keys, or live traces are committed. | checked locally; rerun before publish |
| Legal/commercial | license, trademark, open-core boundary, and company docs reviewed. | missing |

## What Goes Open

Open-source core:

- CLI scanner and artifact writer
- deterministic rules and rule registry
- scanner schemas and redaction guarantees
- Agent Capability Graph builder and bounded path finder
- permit status engine
- Markdown, JSON, YAML, SARIF, baseline, diff, and policy artifacts
- local eval harness
- live validation runner and manifest format
- Deep Agent evidence tools, coordinator prompt, specialist subagent specs, and citation critic
- OpenRouter provider adapter and local cost/cache telemetry
- Phoenix local tracing and dataset export support
- GitHub Action
- fixtures and public-repo validation manifests

Keep out of the public core for now:

- customer-specific rules
- hosted dashboard/control-plane code
- billing, tenancy, RBAC, and SSO
- proprietary policy packs
- private repo validation data
- managed LLM routing credentials
- customer reports, traces, or security findings

## Repo Hygiene Checklist

Before remote creation:

```bash
python3 tools/release_check.py
git status --short
find . -maxdepth 3 -name ".env*"
uv run --all-extras pytest
uv run agent-permit scan . --ci --exclude "tests/fixtures/**"
uv run agent-permit open-source-demo docs/evals/open-source-live-repos.json \
  --repo-root /tmp/agent-permit-open-source-validation \
  --run-id public-release-dry-run \
  --skip-live
```

Check manually:

- `.env.local` remains untracked
- `.agent-permit/` generated reports stay untracked unless a sanitized sample is intentionally committed
- docs do not claim hosted features that do not exist
- Deep Agent is described as required for the MVP investigation product path, not an optional side quest
- zero raw secret values appear in fixtures, docs, or generated artifacts

## Public Repo Shape

Recommended root files:

```text
README.md
LICENSE
SECURITY.md
CONTRIBUTING.md
CODE_OF_CONDUCT.md
SUPPORT.md
CHANGELOG.md
ROADMAP.md
.github/ISSUE_TEMPLATE/
.github/pull_request_template.md
action.yml
pyproject.toml
uv.lock
docs/
src/
tests/
```

Recommended GitHub settings:

- topics: `ai-security`, `agents`, `mcp`, `langgraph`, `langchain`, `sarif`, `devsecops`
- branch protection on `main`
- required tests before merge
- Dependabot or Renovate after public launch
- GitHub code scanning upload sample workflow
- issue templates for bug, false positive, rule request, and integration request

## Launch Narrative

One-line positioning:

```text
Agent Permit Office checks whether an AI agent should receive tools, credentials, memory, or production access before it is allowed to run.
```

Developer value:

- fast local scan
- CI gate before agent permissions land
- deterministic findings with line evidence
- bounded Deep Agent report over scanner artifacts
- SARIF and baseline mode for existing repos
- local observability through Phoenix

Enterprise buyer value:

- reduce unmanaged agent/tool/credential risk
- produce reviewable permit evidence before production rollout
- standardize exceptions through repo policy
- create audit trail for agent access approvals
- integrate with AppSec and platform security workflows

## Release Phases

### Phase 1: Public Core

Goal:

- public GitHub repo can be cloned, installed, tested, scanned, and demoed

Deliver:

- license and governance files
- cleaned README
- release readiness checklist
- GitHub Action docs
- no-spend demo path
- optional live demo path

### Phase 2: Community Proof

Goal:

- prove useful signal beyond our own fixtures

Deliver:

- curated public-repo validation set
- sanitized sample HTML reports
- rule contribution guide
- false-positive triage workflow
- public roadmap

### Phase 3: Commercial Control Plane

Goal:

- turn one-off CLI value into recurring workflow value

Deliver:

- hosted dashboard
- org/project/repo inventory
- scheduled scans
- policy pack management
- trace/eval review
- team approvals
- notification integrations
- private repo connectors

### Phase 4: Enterprise Package

Goal:

- support regulated and larger customers

Deliver:

- SSO/RBAC
- audit evidence retention
- custom rule packs
- self-hosted or VPC deployment option
- model gateway controls
- procurement/security package

## Sources

- Open Source Initiative FAQ: https://opensource.org/faq/
- Open Source Definition: https://opensource.org/osd/
- GitLab handbook: https://handbook.gitlab.com/
- Sentry open source and Fair Source explanation: https://open.sentry.io/
- HashiCorp Business Source License announcement: https://www.hashicorp.com/blog/hashicorp-adopts-business-source-license
- OpenTofu fork announcement: https://opentofu.org/blog/opentofu-announces-fork-of-terraform/
