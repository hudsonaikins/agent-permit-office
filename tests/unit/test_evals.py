import json
from io import StringIO
from pathlib import Path

import agent_permit.cli as cli
from agent_permit.cli import main
from agent_permit.analytics import (
    ANALYTICS_EVENTS_FILE,
    EVAL_TRENDS_JSON_FILE,
    EVAL_TRENDS_MARKDOWN_FILE,
)
from agent_permit.evals import (
    EVAL_REPORT_FILE,
    EVAL_RESULTS_FILE,
    LIVE_REPO_VALIDATION_REPORT_FILE,
    LIVE_REPO_VALIDATION_RESULTS_FILE,
    PHOENIX_DATASET_ROWS_FILE,
    PhoenixDatasetUploadResult,
    REAL_REPO_EVAL_REPORT_FILE,
    REAL_REPO_EVAL_RESULTS_FILE,
    build_phoenix_dataset_rows,
    load_live_repo_validation_cases,
    load_real_repo_cases,
    run_fixture_eval_suite,
    run_live_repo_validation_suite,
    run_real_repo_eval_suite,
    upload_phoenix_dataset_rows,
)


FIXTURES_DIR = Path(__file__).parents[1] / "fixtures"


def test_fixture_eval_suite_passes_against_manifest_truth(tmp_path) -> None:
    eval_run = run_fixture_eval_suite(
        FIXTURES_DIR,
        eval_run_id="unit-eval",
        output_dir=tmp_path / "eval-output",
    )

    results_path = eval_run.output_dir / EVAL_RESULTS_FILE
    report_path = eval_run.output_dir / EVAL_REPORT_FILE
    payload = json.loads(results_path.read_text())
    dataset_rows_path = eval_run.output_dir / PHOENIX_DATASET_ROWS_FILE
    dataset_rows = [
        json.loads(line)
        for line in dataset_rows_path.read_text().splitlines()
    ]

    assert eval_run.passed is True
    assert payload["passed"] is True
    assert payload["summary"] == {"failed": 0, "passed": 4, "total": 4}
    assert report_path.is_file()
    assert dataset_rows_path.is_file()
    trend_json_path = (
        eval_run.output_dir / "eval-trends" / "unit-eval" / EVAL_TRENDS_JSON_FILE
    )
    trend_markdown_path = (
        eval_run.output_dir / "eval-trends" / "unit-eval" / EVAL_TRENDS_MARKDOWN_FILE
    )
    assert trend_json_path.is_file()
    assert trend_markdown_path.is_file()
    trend_payload = json.loads(trend_json_path.read_text())
    assert trend_payload["summary"]["runs"] == 1
    assert trend_payload["summary"]["latest_run_id"] == "unit-eval"
    assert trend_payload["summary"]["latest_pass_rate"] == 1.0
    events = [
        json.loads(line)
        for line in (eval_run.output_dir / ANALYTICS_EVENTS_FILE)
        .read_text()
        .splitlines()
    ]
    assert [event["event_name"] for event in events] == ["eval_completed"]
    assert events[0]["payload"]["total_cases"] == 4
    assert build_phoenix_dataset_rows(eval_run) == dataset_rows
    assert "Cases: `4/4`" in report_path.read_text()
    for result in eval_run.results:
        assert result.status_check_passed is True
        assert result.rule_id_check_passed is True
        assert result.citation_check_passed is True
        assert result.secret_leak_check_passed is True
        assert result.quality_score == 1.0
        assert result.artifact_dir.is_dir()
    first_row = dataset_rows[0]
    assert first_row["id"].startswith("agent-permit-fixture-")
    assert set(first_row) == {"id", "inputs", "outputs", "metadata"}
    assert "expected_permit_status" in first_row["outputs"]
    assert "quality_score" in first_row["metadata"]


def test_eval_cli_writes_local_artifacts(tmp_path) -> None:
    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(
        [
            "eval",
            str(FIXTURES_DIR),
            "--run-id",
            "cli-eval",
            "--output",
            str(tmp_path / "cli-output"),
        ],
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert "Status: eval_complete" in stdout.getvalue()
    assert "Cases: 4/4 passed" in stdout.getvalue()
    assert "Phoenix dataset rows:" in stdout.getvalue()
    assert (tmp_path / "cli-output" / EVAL_RESULTS_FILE).is_file()
    assert (tmp_path / "cli-output" / EVAL_REPORT_FILE).is_file()
    assert (tmp_path / "cli-output" / PHOENIX_DATASET_ROWS_FILE).is_file()
    assert (
        tmp_path
        / "cli-output"
        / "eval-trends"
        / "cli-eval"
        / EVAL_TRENDS_JSON_FILE
    ).is_file()
    assert (tmp_path / "cli-output" / ANALYTICS_EVENTS_FILE).is_file()
    assert "Eval trends:" in stdout.getvalue()
    assert "Events:" in stdout.getvalue()


def test_eval_cli_uploads_to_phoenix_when_requested(tmp_path, monkeypatch) -> None:
    stdout = StringIO()
    stderr = StringIO()
    calls = []

    def fake_upload(eval_run, *, dataset_name: str, base_url: str):
        calls.append((eval_run.eval_run_id, dataset_name, base_url))
        return PhoenixDatasetUploadResult(
            dataset_name=dataset_name,
            example_count=len(eval_run.results),
            base_url=base_url,
            dataset_id="dataset-123",
            version_id="version-456",
        )

    monkeypatch.setattr("agent_permit.cli.upload_phoenix_dataset_rows", fake_upload)

    exit_code = main(
        [
            "eval",
            str(FIXTURES_DIR),
            "--run-id",
            "upload-eval",
            "--output",
            str(tmp_path / "upload-output"),
            "--upload-phoenix",
            "--phoenix-base-url",
            "http://localhost:6006",
            "--phoenix-dataset-name",
            "agent-permit-test",
        ],
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert calls == [
        ("upload-eval", "agent-permit-test", "http://localhost:6006")
    ]
    assert "Phoenix upload: complete" in stdout.getvalue()
    assert "Phoenix dataset: agent-permit-test" in stdout.getvalue()
    assert "Phoenix examples: 4" in stdout.getvalue()
    assert "Phoenix dataset ID: dataset-123" in stdout.getvalue()


def test_upload_phoenix_dataset_rows_uses_stable_examples(
    tmp_path,
    monkeypatch,
) -> None:
    eval_run = run_fixture_eval_suite(
        FIXTURES_DIR,
        eval_run_id="upload-helper",
        output_dir=tmp_path / "helper-output",
    )
    created = {}

    class FakeDataset:
        name = "agent-permit-test"
        example_count = 4
        id = "dataset-123"
        version_id = "version-456"

    class FakeDatasets:
        def create_dataset(self, **kwargs):
            created.update(kwargs)
            return FakeDataset()

    class FakeClient:
        def __init__(self, *, base_url: str):
            created["base_url"] = base_url
            self.datasets = FakeDatasets()

    monkeypatch.setitem(
        __import__("sys").modules,
        "phoenix.client",
        type("FakePhoenixClientModule", (), {"Client": FakeClient}),
    )

    result = upload_phoenix_dataset_rows(
        eval_run,
        dataset_name="agent-permit-test",
        base_url="http://localhost:6006",
    )

    assert result.dataset_name == "agent-permit-test"
    assert result.example_count == 4
    assert result.dataset_id == "dataset-123"
    assert created["base_url"] == "http://localhost:6006"
    assert created["name"] == "agent-permit-test"
    assert len(created["examples"]) == 4
    first_example = created["examples"][0]
    assert first_example["id"].startswith("agent-permit-fixture-")
    assert set(first_example) == {"id", "input", "output", "metadata"}
    assert "fixture_id" in first_example["input"]
    assert "expected_permit_status" in first_example["output"]
    assert "quality_score" in first_example["metadata"]


def test_upload_phoenix_dataset_rows_uses_env_base_url(
    tmp_path,
    monkeypatch,
) -> None:
    eval_run = run_fixture_eval_suite(
        FIXTURES_DIR,
        eval_run_id="upload-env",
        output_dir=tmp_path / "env-output",
    )
    created = {}

    class FakeDataset:
        name = "agent-permit-fixture-evals"
        example_count = 4

    class FakeDatasets:
        def create_dataset(self, **kwargs):
            created.update(kwargs)
            return FakeDataset()

    class FakeClient:
        def __init__(self, *, base_url: str):
            created["base_url"] = base_url
            self.datasets = FakeDatasets()

    monkeypatch.setitem(
        __import__("sys").modules,
        "phoenix.client",
        type("FakePhoenixClientModule", (), {"Client": FakeClient}),
    )
    monkeypatch.setenv("PHOENIX_BASE_URL", "http://phoenix.local")

    result = upload_phoenix_dataset_rows(eval_run)

    assert result.base_url == "http://phoenix.local"
    assert created["base_url"] == "http://phoenix.local"


def test_eval_cli_returns_error_when_phoenix_upload_fails(
    tmp_path,
    monkeypatch,
) -> None:
    stdout = StringIO()
    stderr = StringIO()

    def fake_upload(_eval_run, *, dataset_name: str, base_url: str):
        raise RuntimeError(f"server unavailable at {base_url} for {dataset_name}")

    monkeypatch.setattr("agent_permit.cli.upload_phoenix_dataset_rows", fake_upload)

    exit_code = main(
        [
            "eval",
            str(FIXTURES_DIR),
            "--run-id",
            "upload-fail",
            "--output",
            str(tmp_path / "upload-fail-output"),
            "--upload-phoenix",
        ],
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 1
    assert stdout.getvalue() == ""
    assert "Phoenix upload failed" in stderr.getvalue()
    assert "server unavailable" in stderr.getvalue()


def test_eval_cli_rejects_missing_fixture_root(tmp_path) -> None:
    stdout = StringIO()
    stderr = StringIO()
    missing = tmp_path / "missing"

    exit_code = main(["eval", str(missing)], stdout=stdout, stderr=stderr)

    assert exit_code == 2
    assert stdout.getvalue() == ""
    assert f"fixture root does not exist: {missing}" in stderr.getvalue()


def test_eval_cli_rejects_empty_fixture_root(tmp_path) -> None:
    stdout = StringIO()
    stderr = StringIO()
    empty = tmp_path / "empty"
    empty.mkdir()

    exit_code = main(["eval", str(empty)], stdout=stdout, stderr=stderr)

    assert exit_code == 1
    assert stdout.getvalue() == ""
    assert "no fixture manifests found" in stderr.getvalue()


def test_real_repo_eval_suite_scans_manifest_repos(tmp_path) -> None:
    repo_root = tmp_path / "repos"
    repo_root.mkdir()
    _write_real_repo_fixture(repo_root / "agent-repo")
    manifest_path = _write_real_repo_manifest(tmp_path, local_path="agent-repo")

    eval_run = run_real_repo_eval_suite(
        manifest_path,
        repo_root=repo_root,
        eval_run_id="real-eval",
        output_dir=tmp_path / "real-output",
    )
    payload = json.loads(
        (eval_run.output_dir / REAL_REPO_EVAL_RESULTS_FILE).read_text()
    )

    assert eval_run.passed is True
    assert payload["passed"] is True
    assert payload["summary"] == {"failed": 0, "passed": 1, "total": 1}
    assert (eval_run.output_dir / REAL_REPO_EVAL_REPORT_FILE).is_file()
    result = eval_run.results[0]
    assert result.actual_permit_status == "needs_review"
    assert result.expected_rule_check_passed is True
    assert result.forbidden_rule_check_passed is True
    assert result.citation_check_passed is True
    assert result.secret_leak_check_passed is True
    assert result.quality_score == 1.0
    assert result.artifact_dir.is_dir()
    assert result.investigation_report.is_file()


def test_real_repo_eval_cli_writes_artifacts(tmp_path) -> None:
    repo_root = tmp_path / "repos"
    repo_root.mkdir()
    _write_real_repo_fixture(repo_root / "agent-repo")
    manifest_path = _write_real_repo_manifest(tmp_path, local_path="agent-repo")
    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(
        [
            "eval-real",
            str(manifest_path),
            "--repo-root",
            str(repo_root),
            "--run-id",
            "cli-real",
            "--output",
            str(tmp_path / "cli-real-output"),
        ],
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert "Status: real_repo_eval_complete" in stdout.getvalue()
    assert "Repos: 1/1 passed" in stdout.getvalue()
    assert (tmp_path / "cli-real-output" / REAL_REPO_EVAL_RESULTS_FILE).is_file()
    assert (tmp_path / "cli-real-output" / REAL_REPO_EVAL_REPORT_FILE).is_file()


def test_real_repo_manifest_resolves_relative_paths(tmp_path) -> None:
    repo_root = tmp_path / "repos"
    repo_root.mkdir()
    manifest_path = _write_real_repo_manifest(tmp_path, local_path="agent-repo")

    cases = load_real_repo_cases(manifest_path, repo_root=repo_root)

    assert cases[0].repo_path == (repo_root / "agent-repo").resolve()
    assert cases[0].expected_rule_ids_present == (
        "ci-secret-reference",
        "ci-write-permission",
    )


def test_real_repo_eval_cli_rejects_missing_manifest(tmp_path) -> None:
    stdout = StringIO()
    stderr = StringIO()
    missing = tmp_path / "missing.json"

    exit_code = main(["eval-real", str(missing)], stdout=stdout, stderr=stderr)

    assert exit_code == 2
    assert stdout.getvalue() == ""
    assert f"manifest does not exist: {missing}" in stderr.getvalue()


def test_live_repo_validation_suite_runs_manifest_repos(tmp_path, monkeypatch) -> None:
    repo_root = tmp_path / "repos"
    repo_root.mkdir()
    _write_real_repo_fixture(repo_root / "agent-repo")
    manifest_path = _write_live_repo_manifest(tmp_path, local_path="agent-repo")
    monkeypatch.setattr(cli, "run_live_validate", _fake_run_live_validate)

    validation_run = run_live_repo_validation_suite(
        manifest_path,
        repo_root=repo_root,
        validation_run_id="live-real",
        output_dir=tmp_path / "live-output",
        agent_recursion_limit=9,
        enable_phoenix=True,
        exclude_patterns=(".agent-permit/**",),
    )
    payload = json.loads(
        (validation_run.output_dir / LIVE_REPO_VALIDATION_RESULTS_FILE).read_text()
    )

    assert validation_run.passed is True
    assert payload["passed"] is True
    assert payload["summary"] == {
        "cache_hit_ratio": 0.5,
        "cached_tokens": 50,
        "failed": 0,
        "input_tokens": 100,
        "passed": 1,
        "total": 1,
        "total_tokens": 140,
    }
    assert (validation_run.output_dir / LIVE_REPO_VALIDATION_REPORT_FILE).is_file()
    result = validation_run.results[0]
    assert result.run_id == "live-real-agent-repo"
    preserved_dir = (
        validation_run.output_dir
        / "repos"
        / "agent-repo"
        / "live-real-agent-repo"
    )
    assert result.artifact_dir == preserved_dir
    assert (preserved_dir / "raw-findings.json").is_file()
    assert payload["results"][0]["artifact_dir"] == str(preserved_dir)
    assert payload["results"][0]["report_path"] == str(
        preserved_dir / "agent-investigation.md"
    )
    assert payload["results"][0]["validation_path"] == str(
        preserved_dir / "live-validation.json"
    )
    assert result.actual_permit_status == "needs_review"
    assert result.actual_rule_ids == ("ci-secret-reference", "ci-write-permission")
    assert result.citation_check_passed is True
    assert result.model_calls == 1
    assert result.input_tokens == 100
    assert result.total_tokens == 140
    assert result.cached_tokens == 50
    assert result.cache_hit_ratio == 0.5


def test_live_repo_validation_cli_writes_artifacts(tmp_path, monkeypatch) -> None:
    repo_root = tmp_path / "repos"
    repo_root.mkdir()
    _write_real_repo_fixture(repo_root / "agent-repo")
    manifest_path = _write_live_repo_manifest(tmp_path, local_path="agent-repo")
    stdout = StringIO()
    stderr = StringIO()
    monkeypatch.setattr(cli, "run_live_validate", _fake_run_live_validate)

    exit_code = main(
        [
            "live-validate-real",
            str(manifest_path),
            "--repo-root",
            str(repo_root),
            "--run-id",
            "cli-live-real",
            "--output",
            str(tmp_path / "cli-live-output"),
            "--agent-recursion-limit",
            "9",
            "--phoenix",
            "--exclude",
            ".agent-permit/**",
        ],
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert "Status: live_repo_validation_complete" in stdout.getvalue()
    assert "Repos: 1/1 passed" in stdout.getvalue()
    assert "Cache hit ratio: 50.00%" in stdout.getvalue()
    assert (tmp_path / "cli-live-output" / LIVE_REPO_VALIDATION_RESULTS_FILE).is_file()
    assert (tmp_path / "cli-live-output" / LIVE_REPO_VALIDATION_REPORT_FILE).is_file()


def test_live_repo_validation_manifest_resolves_relative_paths(tmp_path) -> None:
    repo_root = tmp_path / "repos"
    repo_root.mkdir()
    manifest_path = _write_live_repo_manifest(tmp_path, local_path="agent-repo")

    cases = load_live_repo_validation_cases(manifest_path, repo_root=repo_root)

    assert cases[0].repo_path == (repo_root / "agent-repo").resolve()
    assert cases[0].expected_permit_status == "needs_review"
    assert cases[0].expected_rule_ids_present == (
        "ci-secret-reference",
        "ci-write-permission",
    )


def _write_real_repo_fixture(repo_path: Path) -> None:
    workflow_dir = repo_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    (repo_path / "README.md").write_text("# Agent repo\n", encoding="utf-8")
    (workflow_dir / "agent.yml").write_text(
        """name: Agent
on:
  workflow_dispatch:
permissions:
  contents: write
jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - name: Use secret
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: python agent.py
""",
        encoding="utf-8",
    )


def _write_real_repo_manifest(tmp_path: Path, *, local_path: str) -> Path:
    manifest_path = tmp_path / "real-repos.json"
    manifest_path.write_text(
        json.dumps(
            {
                "version": 1,
                "repos": [
                    {
                        "id": "agent-repo",
                        "source": "local-test",
                        "local_path": local_path,
                        "expected_permit_status": "needs_review",
                        "expected_rule_ids_present": [
                            "ci-secret-reference",
                            "ci-write-permission",
                        ],
                        "expected_rule_ids_absent": [
                            "ci-pull-request-target",
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return manifest_path


def _write_live_repo_manifest(tmp_path: Path, *, local_path: str) -> Path:
    manifest_path = tmp_path / "live-repos.json"
    manifest_path.write_text(
        json.dumps(
            {
                "version": 1,
                "repos": [
                    {
                        "id": "agent-repo",
                        "source": "local-test",
                        "local_path": local_path,
                        "expected_permit_status": "needs_review",
                        "expected_rule_ids_present": [
                            "ci-secret-reference",
                            "ci-write-permission",
                        ],
                        "expected_rule_ids_absent": [
                            "ci-pull-request-target",
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return manifest_path


def _fake_run_live_validate(target_path: Path, *, run_id: str, stdout, **_kwargs) -> int:
    artifact_dir = target_path / ".agent-permit" / "runs" / run_id
    artifact_dir.mkdir(parents=True)
    report_path = artifact_dir / "agent-investigation.md"
    usage_path = artifact_dir / "openrouter-usage.json"
    validation_path = artifact_dir / "live-validation.json"
    report_path.write_text("# Report\n", encoding="utf-8")
    usage_path.write_text(
        json.dumps(
            {
                "cached_tokens": 50,
                "input_tokens": 100,
                "model_calls": 1,
                "total_tokens": 140,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (artifact_dir / "raw-findings.json").write_text(
        json.dumps(
            {
                "findings": [
                    {"rule_id": "ci-secret-reference"},
                    {"rule_id": "ci-write-permission"},
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )
    validation_path.write_text(
        json.dumps(
            {
                "artifact_dir": str(artifact_dir),
                "citation_check": {"status": "passed", "supported": True},
                "controls": 4,
                "findings": 2,
                "graph_paths": 2,
                "permit_status": "needs_review",
                "report_path": str(report_path),
                "run_id": run_id,
                "status": "passed",
                "usage_path": str(usage_path),
                "usage_summary": {
                    "cache_hit_ratio": 0.5,
                    "cached_tokens": 50,
                    "input_tokens": 100,
                    "model_calls": 1,
                    "total_tokens": 140,
                },
                "validation_path": str(validation_path),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    print("Status: live_validation_complete", file=stdout)
    return 0
