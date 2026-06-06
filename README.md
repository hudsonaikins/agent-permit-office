# Agent Permit Office

Agent Permit Office is an investigation-stage project for approving AI agents before they receive tools, credentials, memory, or production access.

Current implementation:

- Python `uv` package with `agent-permit` CLI.
- `agent-permit scan <path>` creates `.agent-permit/runs/<run_id>/`.
- The scan writes metadata-only `file-inventory.json` with file classifications, hashes, and skip counts.
- Real `.env` files and generated/junk directories are skipped; secret values are not emitted.

Current work:

- [LangChain Deep Agents Architecture Research](docs/research/langchain-deep-agents-architecture.md)
- [Starter Scope and Architecture](docs/agent-permit-office-scope.md)
- [Tech Stack Analysis: LangChain, Deep Agents, and LangSmith](docs/tech-stack-langchain-deep-agents.md)
- [Codebase Context, Indexing, and MCP Review](docs/codebase-context-and-indexing.md)
- [Codebase and Services Blueprint](docs/codebase-and-services-blueprint.md)
- [Deterministic Scanners and Model Plan](docs/scanner-and-model-plan.md)
- [Static Analysis and Agent Security Research](docs/research/static-analysis-agent-security-research.md)
- [End-to-End System Diagram](docs/system-diagram-end-to-end.md)
- [Project Management and Sprint Plan](docs/project-management-sprint-plan.md)
- [Plane Execution Sync](docs/plane-execution-sync.md)
