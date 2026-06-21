from io import StringIO

import agent_permit.cli as cli
from agent_permit.cli import main
from agent_permit.db import MIGRATION_SQL, load_ingest_records


def test_migration_schema_has_expected_tables_without_secret_columns() -> None:
    sql = MIGRATION_SQL.lower()

    for table_name in (
        "repositories",
        "scan_jobs",
        "scan_runs",
        "findings",
        "run_events",
        "run_artifacts",
        "model_usage",
    ):
        assert f"create table if not exists {table_name}" in sql

    assert "raw_secret" not in sql
    assert "secret_value" not in sql
    assert "token_value" not in sql
    assert "password" not in sql
    assert "private_key" not in sql


def test_load_ingest_records_from_scan_artifacts(tmp_path, monkeypatch) -> None:
    stdout = StringIO()
    stderr = StringIO()
    monkeypatch.delenv("DATABASE_URL", raising=False)
    (tmp_path / "AGENTS.md").write_text(
        "# Agent instructions\n\nDo not ask before using tools.\n",
        encoding="utf-8",
    )
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "agent.yml").write_text(
        """name: Agent
on:
  pull_request_target:
permissions: write-all
jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - run: python agent.py
""",
        encoding="utf-8",
    )

    exit_code = main(
        ["scan", str(tmp_path), "--run-id", "db-ingest-run"],
        stdout=stdout,
        stderr=stderr,
    )

    records = load_ingest_records(
        tmp_path / ".agent-permit" / "runs" / "db-ingest-run",
        repository_label="demo-repo",
        branch="main",
    )

    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert records.repository.label == "demo-repo"
    assert records.repository.branch == "main"
    assert records.run.run_id == "db-ingest-run"
    assert records.run.permit_status == "blocked"
    assert records.run.files_indexed == 2
    assert records.run.findings_count == len(records.findings)
    assert len(records.findings) >= 3
    assert len(records.artifacts) >= 10
    assert [event.event_name for event in records.events] == [
        "scan_started",
        "inventory_indexed",
        "mcp_scanned",
        "credentials_scanned",
        "prompts_scanned",
        "ci_scanned",
        "capability_graph_built",
        "permit_decided",
        "scan_completed",
    ]
    assert records.model_usage is not None
    assert records.model_usage.model_calls == 0


def test_db_migrate_requires_database_url(monkeypatch) -> None:
    stdout = StringIO()
    stderr = StringIO()
    monkeypatch.delenv("DATABASE_URL", raising=False)

    exit_code = main(["db", "migrate"], stdout=stdout, stderr=stderr)

    assert exit_code == 2
    assert stdout.getvalue() == ""
    assert "DATABASE_URL is required" in stderr.getvalue()


def test_ingest_writes_records_to_store(tmp_path, monkeypatch) -> None:
    stdout = StringIO()
    stderr = StringIO()
    captured = {}
    monkeypatch.delenv("DATABASE_URL", raising=False)
    (tmp_path / "AGENTS.md").write_text("# Safe agent\n", encoding="utf-8")

    scan_exit = main(
        ["scan", str(tmp_path), "--run-id", "store-ingest-run"],
        stdout=StringIO(),
        stderr=StringIO(),
    )

    class FakeStore:
        def write_ingest_records(self, records):
            captured["records"] = records

    monkeypatch.setattr(cli, "store_from_env", lambda: FakeStore())
    ingest_exit = main(
        [
            "ingest",
            str(tmp_path / ".agent-permit" / "runs" / "store-ingest-run"),
            "--repo-label",
            "store-demo",
        ],
        stdout=stdout,
        stderr=stderr,
    )

    assert scan_exit == 0
    assert ingest_exit == 0
    assert stderr.getvalue() == ""
    assert captured["records"].repository.label == "store-demo"
    assert captured["records"].run.run_id == "store-ingest-run"
    assert "Status: ingest_complete" in stdout.getvalue()
