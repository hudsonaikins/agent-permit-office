import json
from io import StringIO
from pathlib import Path

from agent_permit.cli import main
from agent_permit.evals import (
    EVAL_REPORT_FILE,
    EVAL_RESULTS_FILE,
    PHOENIX_DATASET_ROWS_FILE,
    PhoenixDatasetUploadResult,
    build_phoenix_dataset_rows,
    run_fixture_eval_suite,
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
