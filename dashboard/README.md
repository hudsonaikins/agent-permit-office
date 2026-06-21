# Agent Permit Office Dashboard

Local dashboard for reviewing Agent Permit Office scan, live-validation, and Deep Agent evidence artifacts.

```bash
bun install
bun dev
```

Live local stack:

```bash
cp .env.example .env
bun dev
```

The dashboard reads `VITE_AGENT_PERMIT_API_URL`, defaulting to `http://127.0.0.1:8787/api`.
If the Worker API is unavailable, it falls back to the generated static snapshot.

Queueing a scan from the dashboard creates a Postgres job through `POST /api/jobs`.
Process the queued job from the repo root:

```bash
DATABASE_URL="postgresql://..." uv run --extra db agent-permit runner --once
```

Refresh the dashboard data snapshot from repo-local `.agent-permit` artifacts:

```bash
python3 ../tools/export_dashboard_snapshot.py
```

Write a sanitized customer-demo proof pack:

```bash
python3 ../tools/export_dashboard_snapshot.py --proof-pack
```

Proof pack docs: [`../docs/proof-pack-export.md`](../docs/proof-pack-export.md)

Snapshot contract:

- Version: `permitgraph.dashboard.snapshot.v1`
- Contract doc: [`../docs/permitgraph-dashboard-snapshot-contract.md`](../docs/permitgraph-dashboard-snapshot-contract.md)
- Data bridge: `src/data/permitQueue.ts`

Current scope:

- Vite React TypeScript app
- Bun package lifecycle
- shadcn/ui primitives with Phosphor icons
- live Worker API mode with static dashboard snapshot fallback
- local repository scan queue form
- local-only, no hosted integrations yet
