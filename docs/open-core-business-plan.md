# Open Core Business Plan

Date: 2026-06-13

## Product Thesis

Agent Permit Office should be an open-core security product.

Core thesis:

```text
AI agents need a permit layer before they receive tool, credential, memory, or production access.
```

Open-source core earns trust by showing the scanner, rules, evidence artifacts, and Deep Agent workflow. Paid product captures value where teams need managed workflow, governance, integrations, retention, and support.

## Buyer

Primary users:

- AI platform engineers
- AppSec engineers
- DevSecOps teams
- platform security teams
- engineering managers approving agent rollouts

Economic buyers:

- CISO
- VP Engineering
- Head of Platform
- Head of AI Enablement
- Compliance or GRC leader in regulated teams

High-intent trigger events:

- company adopts MCP servers
- internal agents gain repository write access
- teams start using agentic coding tools in CI
- security team needs evidence for AI-agent approvals
- a customer asks for proof that AI tools do not expose credentials

## Open-Core Boundary

Open core:

| Capability | Why open |
| --- | --- |
| Deterministic scanner | Trust requires visible rules and evidence. |
| Rule registry | Community can improve coverage and reduce false positives. |
| Artifact schemas | Integrations need stable machine-readable contracts. |
| Permit engine | Teams must know why a repo is approved, needs review, or blocked. |
| SARIF output | GitHub code scanning is a developer adoption surface. |
| Baseline/diff | Existing repos need incremental adoption. |
| Policy config | Users need transparent exceptions. |
| Local Deep Agent path | The product promise needs visible AI reasoning over bounded evidence. |
| Citation critic | Trust requires checking model output against deterministic artifacts. |
| Phoenix local observability | Security demos should not require hosted trace storage. |
| GitHub Action | CI adoption should be frictionless. |

Paid product:

| Capability | Why paid |
| --- | --- |
| Hosted dashboard | Multi-repo and team review creates recurring workflow value. |
| Private repo connectors | Higher trust, auth, tenancy, and operational support. |
| Scheduled scans | Continuous monitoring belongs in managed service. |
| Policy packs | Compliance mapping and maintenance are commercial value. |
| Custom rules | Customer-specific risk logic needs support and review. |
| Approval workflows | Team gates, audit trails, and assignments are org features. |
| SSO/RBAC | Enterprise control surface. |
| Evidence retention | Audit storage and reporting are compliance value. |
| Managed LLM gateway | Cost controls, key isolation, model policy, and trace capture. |
| Support/SLA | Enterprise reliability and response path. |

## License Strategy

Recommended default:

```text
Apache-2.0 open-source core + proprietary hosted/enterprise extensions
```

Reason:

- clean enterprise adoption path
- patent grant helps buyer confidence
- avoids "source available but not open source" confusion
- lets the community fork and inspect the actual scanner
- keeps commercial value in workflow, hosting, compliance, and support

Avoid for core launch:

- BUSL/FSL/Fair Source for the scanner core if the public story is "open source"
- ambiguous "open-core" claims without an OSI-approved core license
- license changes after community contributions without a clear contributor policy

Pragmatic stance:

```text
Call the core open source only if the core uses an OSI-approved license. Call other tiers proprietary or source-available if they are not OSI open source.
```

## Product Packaging

### Free Community

For individual developers and small teams:

- local CLI
- GitHub Action
- deterministic scanner
- Deep Agent investigation with user's OpenRouter key
- SARIF
- baseline/diff
- repo policy config
- local Phoenix traces
- fixture evals
- public docs and examples

### Team Cloud

For teams with multiple repos:

- hosted project/repo inventory
- scheduled scans
- GitHub app
- team approval queue
- report history
- shared policy profiles
- managed OpenRouter key option
- Slack/GitHub notifications
- basic retention

### Enterprise

For regulated or larger customers:

- SSO/RBAC
- private deployment option
- custom rule packs
- evidence retention controls
- audit export
- advanced policy packs
- procurement/security review package
- support SLA
- model gateway policy and spend controls

## Hosted Stack Map

The hosted product should start as a managed review workflow around the open-source artifacts. It should not become a separate scanner that hides the evidence model.

| Layer | Choice | Responsibility | Open-core note |
| --- | --- | --- | --- |
| Frontend | React + Vite dashboard with shadcn/ui and Phosphor icons | Review queue, run scope, findings spreadsheet, selected evidence, Decision Log, artifact drawer, product workflow | Current local dashboard remains OSS; hosted adds auth, persistence, and collaboration. |
| Runtime | Bun for dashboard package lifecycle | Local dev, build, test, scripts | Python CLI stays on `uv`; Bun is dashboard-only. |
| Compute/hosting | Cloudflare Workers | API routes, static dashboard assets, auth gate, webhook ingestion, signed artifact flows | Hosted control plane only; no deploy needed for local OSS use. |
| Database | Neon Postgres through Cloudflare Hyperdrive | Organizations, repos, scan runs, findings, approvals, suppressions, policies, model usage, eval runs | Store normalized metadata, not raw repo contents. |
| Auth | Clerk | Users, organizations, sessions, backend request verification | Use org ID as tenant boundary; never trust frontend org IDs without Worker verification. |
| Blob storage | Cloudflare R2 | Redacted scan bundles, reports, SARIF, dashboard exports, proof packs, evidence archives | Store object keys and hashes in Neon; keep raw secrets out. |
| Product analytics | PostHog | Activation funnel, first scan, first blocked permit, first approval, dashboard usage, feature flags | Hosted mode only by default; OSS local telemetry must stay opt-in. |
| LLM observability | Phoenix/OpenTelemetry first, hosted trace store later | Local traces, evidence-tool spans, eval rows, citation failures, model-quality debugging | Keep local Phoenix OSS path. Hosted trace retention is paid only when customers need managed retention. |
| Model gateway | OpenRouter now, managed gateway later | Model routing, prompt caching, response caching, spend caps, usage artifacts | BYO key in Community/early Team; managed key is paid because it carries cost and governance. |

Hosted request flow:

```text
CLI scan/live validation
  -> redacted artifact bundle
  -> hosted ingest endpoint
  -> Cloudflare Worker verifies Clerk/GitHub context
  -> Neon stores run/finding/approval metadata
  -> R2 stores artifact blobs
  -> PostHog records product events without security payloads
  -> dashboard shows team review queue and audit trail
```

## First Paid Workflows

Start with workflows that teams already pay people to coordinate manually.

### 1. Multi-Repo Permit Queue

Buyer pain:

```text
Security and platform teams cannot manually inspect every agent/MCP repo before access changes ship.
```

Paid value:

- org-level repo inventory
- scheduled scans
- blocked/needs-review queue
- saved views by owner, severity, rule, and repo
- historical status by repo
- Slack/GitHub notifications

### 2. Approval And Exception Workflow

Buyer pain:

```text
Agent access exceptions happen in Slack, PR comments, and spreadsheets with weak audit trail.
```

Paid value:

- request changes
- approve exception
- assign owner
- attach policy condition
- expiration date
- approval history
- audit export

### 3. Evidence Retention And Proof Packs

Buyer pain:

```text
Customer/security review asks for proof that agent access was assessed, but local artifacts disappear.
```

Paid value:

- durable proof packs in R2
- retention policies
- signed download links
- report history
- compliance-friendly export
- manifest integrity checks

### 4. Managed Model Gateway

Buyer pain:

```text
Teams want Deep Agent reports, but do not want every repo owner managing model keys, spend caps, or model policy.
```

Paid value:

- managed provider keys
- allowed model policy
- prompt and response caching
- spend quotas
- usage dashboards
- citation-failure monitoring
- model escalation rules

### 5. Policy Packs And Custom Rules

Buyer pain:

```text
Generic rules are useful, but regulated teams need policy language mapped to their controls.
```

Paid value:

- maintained policy packs
- rule-to-control mapping
- custom rules with review
- false-positive triage
- org-level policy profiles
- compliance export

## What Not To Monetize Yet

Do not charge for the things that create trust and adoption.

Keep open:

- scanner engine
- default rules
- artifact schemas
- permit engine
- local dashboard snapshot
- SARIF
- baseline/diff
- repo policy config
- local Deep Agent path with user's key
- citation critic
- local Phoenix tracing/export
- GitHub Action
- fixtures and public validation manifests

Avoid early monetization:

- basic local scan limits
- hiding rule logic
- locking SARIF behind paid tier
- charging for local false-positive fixes
- gating local proof-pack generation
- forcing hosted telemetry from OSS usage
- making managed LLM key mandatory

Reason:

```text
Open source wins trust by making the permit decision inspectable. Paid product should sell managed workflow and governance, not opaque risk scoring.
```

## Pricing Shape

Do not overprice the CLI. Charge for managed workflow.

Suggested starting shape:

| Tier | Price shape | Notes |
| --- | --- | --- |
| Community | free | OSS core, bring your own LLM key. |
| Team | per repo/month or per seat/month | Pick one simple metric after design-partner usage is measured. |
| Enterprise | annual contract | SSO, retention, custom rules, self-host/VPC, support. |

Initial team pricing hypothesis:

```text
$20-$50 per active repo/month, or $15-$30 per active security/platform user/month
```

Enterprise hypothesis:

```text
$15k-$75k annual contracts depending on repo count, deployment model, retention, and support
```

These are planning ranges, not validated pricing.

## Cost Model

Current cost drivers:

- LLM tokens for live Deep Agent reports
- hosted dashboard compute
- database/storage for scan history and evidence
- tracing/eval storage
- private repo connector operations
- support time

Current product cost posture:

- open-source CLI has near-zero vendor cost when users bring their own key
- demo path can run with `--skip-live` to avoid model spend
- live validation already records token, cached token, model call, and cache-hit metrics
- Sonnet 4.6 remains the default; GPT-5.5 is escalation only
- prompt caching, response caching, sticky routing, timeout, and completion caps are enabled

ProfitCtl quick scenario, using bundled generic SaaS templates:

| Scenario | Users | Revenue | Fixed monthly cost | Total cost | Cost/user | Gross margin | Covenant |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Cloudflare Workers AI SaaS template | 100 | $4,095 | $340 | $340.45 | $3.40 | 91.69% | pass |
| Cloud Run AI SaaS template | 100 | $4,095 | $445 | $445.69 | $4.46 | 89.12% | pass |

Interpretation:

- hosted control plane economics look viable in rough template form
- Cloudflare-style edge/runtime cost is cheaper in the generic template
- this is not decision-grade until real scan frequency, model mix, trace retention, and customer repo count are measured

Cost guardrails for MVP cloud design:

- keep live Deep Agent runs explicit or scheduled with quotas
- persist token/cache metrics per run
- let customers bring their own model key in early Team tier
- cache shared prompts and artifacts aggressively
- avoid storing raw repo contents
- store normalized findings and report artifacts, not full code snapshots

## Go-To-Market

First wedge:

```text
CI permit gate for AI agents and MCP usage in repos.
```

Launch assets:

- public repo
- one-command open-source demo
- sanitized HTML demo report
- "AI Agent Permit Gate" blog post
- five public-repo validation results
- short demo video
- false-positive and rule-request issue templates

Design partner targets:

- companies adopting MCP internally
- AI platform teams building internal coding agents
- AppSec teams asked to review agentic workflows
- devtools startups using agents in CI
- regulated engineering orgs experimenting with AI development tools

Discovery questions:

- where do agents get credentials today?
- who approves MCP/tool access?
- what would block production rollout?
- what evidence do security reviewers need?
- how many repos would need periodic review?
- does the team prefer hosted, self-hosted, or bring-your-own-key?

## Moat

Durable advantages:

- evidence-first scanner artifacts
- source-to-sink agent capability graph
- deterministic permit outcomes
- bounded Deep Agent investigation with citation critic
- growing rule corpus and false-positive corpus
- public validation manifests against real agent repos
- CI/SARIF/baseline adoption path
- enterprise workflow and policy packs

Avoid weak positioning:

- do not frame as generic SAST
- do not frame as generic LLM security chatbot
- do not let the Deep Agent become unbounded repo browsing
- do not sell "AI decides security"; sell deterministic evidence plus bounded AI investigation

## 12-Month Scope

### Quarter 1: Public Core

- publish repo
- harden docs and governance
- release first tagged version
- publish GitHub Action
- ship public demo report
- recruit five design partners

### Quarter 2: Team Workflow

- hosted dashboard prototype
- GitHub app ingestion
- scheduled scans
- team approvals
- org policy profiles
- report history

### Quarter 3: Enterprise Readiness

- SSO/RBAC
- custom rule packs
- audit exports
- retention controls
- self-host/VPC design
- procurement/security packet

### Quarter 4: Category Build

- agent permit benchmark corpus
- MCP risk registry
- policy-pack marketplace
- partner integrations
- annual enterprise contracts

## Next Build Slice

Sprint 25 outcome:

- release-readiness doc
- open-core plan
- README links
- Plane sync
- tests and help smoke
- local commit only

Sprint 26 candidate:

- add public repo governance files
- add `ROADMAP.md`
- add release checklist command or script
- add sanitized demo artifact strategy
- add CI workflow for tests plus self-scan

## Sources

- Open Source Initiative FAQ: https://opensource.org/faq/
- Open Source Definition: https://opensource.org/osd/
- Sentry open source and Fair Source explanation: https://open.sentry.io/
- Fair Source definition: https://fair.io/about/
- Functional Source License: https://fcl.dev/
- HashiCorp Business Source License announcement: https://www.hashicorp.com/blog/hashicorp-adopts-business-source-license
- HashiCorp licensing FAQ: https://www.hashicorp.com/en/license-faq
- OpenTofu fork announcement: https://opentofu.org/blog/opentofu-announces-fork-of-terraform/
