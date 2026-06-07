# Plane Execution Sync

Date: 2026-06-06

## Plane Project

Plane project:

- Name: `Agent Permit Office`
- Identifier: `APO`
- Project ID: `1b183f56-2d1d-4788-8c25-f07e4987dcc8`
- Lead/default assignee: Hudson

Purpose:

```text
execution management and progress tracking for Agent Permit Office
```

## Enabled Structure

Project features enabled:

- modules
- cycles
- views
- pages
- intakes

Epics were not enabled by Plane in this setup. Modules are the milestone/epic layer.

## Kanban States

Created states:

- `Backlog`
- `Ready`
- `In Progress`
- `Review`
- `Validate`
- `Done`
- `Blocked`

Sprint 1 items are in `Ready`.
Future sprint items are in `Backlog`.
Planning/setup items are in `Done`.

## Labels

Created labels:

- `type:research`
- `type:scanner`
- `type:graph`
- `type:policy`
- `type:agent`
- `type:reporting`
- `type:fixtures`
- `type:ops`
- `risk:security`
- `phase:mvp`
- `phase:later`

## Modules

Created modules:

- `Research And Architecture`
- `Scanner Core`
- `Agent Capability Graph`
- `Permit Engine`
- `Deep Agent Investigator`
- `CI And Demo`

## Cycles

Created cycles:

- `Sprint 1 - Scaffold And Schemas`: 2026-06-08 to 2026-06-12
- `Sprint 2 - First Deterministic Scanners`: 2026-06-15 to 2026-06-19
- `Sprint 3 - Agent Capability Graph`: 2026-06-22 to 2026-06-26
- `Sprint 4 - Permit Engine And Reports`: 2026-06-29 to 2026-07-03
- `Sprint 5 - Deep Agent Investigator`: 2026-07-06 to 2026-07-10
- `Sprint 6 - CI And Demo`: 2026-07-13 to 2026-07-17

## Work Items Created

Total created work items: 34.

Planning/setup done items:

- `APO-30`: Complete LangChain Deep Agents architecture research
- `APO-31`: Complete static-analysis and agent-security research
- `APO-32`: Complete end-to-end system diagram
- `APO-33`: Complete Agile Kanban sprint plan
- `APO-34`: Set up Plane project for execution management

Sprint 1 ready items:

- `APO-1`: Scaffold uv Python package and CLI entrypoint
- `APO-2`: Define Pydantic schemas for facts, graph, findings, evidence, and permits
- `APO-3`: Implement `.agent-permit` run artifact writer
- `APO-4`: Create safe and risky fixture repo structure
- `APO-5`: Implement no-op scan command with summary output

Sprint 2 backlog items:

- `APO-6`: Build file inventory scanner
- `APO-7`: Build MCP config scanner
- `APO-8`: Build prompt and instruction scanner
- `APO-9`: Build credential reference scanner with redaction guarantees
- `APO-10`: Build GitHub Actions CI scanner

Sprint 3 backlog items:

- `APO-11`: Build Agent Capability Graph model and builder
- `APO-12`: Define source and sink taxonomy
- `APO-13`: Implement bounded source-to-sink path finder
- `APO-14`: Represent controls in the graph

Sprint 4 backlog items:

- `APO-15`: Implement deterministic rule engine with first 15-25 rules
- `APO-16`: Implement severity scoring and control reductions
- `APO-17`: Implement permit status decision model
- `APO-18`: Render Markdown risk report
- `APO-19`: Emit stable JSON/YAML artifacts

Sprint 5 backlog items:

- `APO-20`: Build controlled graph and evidence tools for Deep Agent - done
- `APO-21`: Create Deep Agent coordinator prompt - done
- `APO-22`: Add MCP, prompt, policy, and critic subagents - done
- `APO-23`: Add optional LangSmith tracing for investigation runs - done
- `APO-24`: Test report critic catches invented claims - done

Sprint 6 backlog items:

- `APO-25`: Implement CI mode with blocking exit codes - done
- `APO-26`: Generate PR-friendly Markdown summary - done
- `APO-27`: Decide SARIF support for MVP - done, defer first-class SARIF until GitHub Action packaging and stable rule IDs exist.
- `APO-28`: Create public-ready demo repo or demo fixture - done, demo uses safe and risky fixtures.
- `APO-29`: Write install and first-scan setup docs - done, README plus GitHub Action and demo docs.

Deferred follow-up:

- `APO-44`: Add optional SARIF writer and upload workflow

Sprint 7 hardening items:

- `APO-45`: Centralize deterministic rule registry and rules CLI - done

Sprint 8 validation items:

- `APO-46`: Validate scanner on public agent repos and typed evidence tools - done

Sprint 9 CI context items:

- `APO-47`: Add workflow event/job/scope context to CI findings - done

Sprint 10 observability items:

- `APO-48`: Add Phoenix observability and local eval harness - done

Sprint 11 trace quality items:

- `APO-49`: Add Phoenix trace-quality metadata and eval exports - done

Sprint 12 Phoenix live validation items:

- `APO-50`: Add Phoenix live validation and dataset upload - done

Sprint 13 real repo eval items:

- `APO-51`: Add real repo eval manifest and runner - done

Sprint 14 SARIF/code scanning items:

- `APO-52`: Add SARIF writer and GitHub code scanning surface - done

Sprint 15 baseline/diff items:

- `APO-53`: Add baseline and diff mode for CI findings - done

Sprint 16 repository policy items:

- `APO-54`: Add repository policy configuration for trusted agent surfaces - done

Sprint 17 OpenRouter model provider items:

- `APO-55`: Wire OpenRouter default model for required Deep Agent assessment - done

Sprint 18 OpenRouter cost controls items:

- `APO-56`: Add OpenRouter cache controls and usage metrics - done

Sprint 19 live Deep Agent validation items:

- `APO-57`: Validate live Deep Agent report path with Sonnet - done

Sprint 20 Phoenix and real repo live validation items:

- `APO-58`: Validate Phoenix trace export and real repo Deep Agent report - done

Sprint 21 live validation harness items:

- `APO-59`: Productize live scan and Deep Agent validation harness - done

Sprint 22 open source live validation items:

- `APO-60`: Run live validation against recent open source agent repos - done

Sprint 23 live validation manifest runner items:

- `APO-61`: Add manifest runner for open source live validation - done

Sprint 24 open source demo package items:

- `APO-62`: Package open source validation as a demo command - done

Sprint 25 open source release and open-core planning items:

- `APO-63`: Plan open-source release and open-core business path - done

Sprint 26 public repo hardening items:

- `APO-64`: Add public repo governance and release hardening - done

Sprint 27 product hygiene and market review items:

- `APO-65`: Review repo hygiene and product market scope - done

## Operating Rule

Plane is now the execution tracker.

Repo Markdown stays the planning artifact source, but active delivery progress should move through Plane states and cycles.
