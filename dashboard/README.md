# Agent Permit Office Dashboard

Local dashboard for reviewing Agent Permit Office scan, live-validation, and Deep Agent evidence artifacts.

```bash
bun install
bun dev
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
- static dashboard snapshot generated from local artifacts
- local-only, no hosted integrations yet
