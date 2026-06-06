import json
from pathlib import Path


FIXTURES_DIR = Path(__file__).parents[1] / "fixtures"
EXPECTED_FIXTURES = {
    "safe-agent": "approved",
    "risky-mcp-agent": "needs_review",
    "poisoned-instructions": "blocked",
    "risky-ci-agent": "blocked",
}
SECRET_VALUE_MARKERS = (
    "-----BEGIN PRIVATE KEY-----",
    "AKIA",
    "ghp_",
    "github_pat_",
    "sk-",
    "xoxb-",
)


def test_expected_fixtures_exist_with_manifest() -> None:
    for fixture_name, expected_status in EXPECTED_FIXTURES.items():
        fixture_dir = FIXTURES_DIR / fixture_name
        manifest_path = fixture_dir / "fixture.json"

        assert fixture_dir.is_dir()
        assert manifest_path.is_file()

        manifest = json.loads(manifest_path.read_text())
        assert manifest["id"] == fixture_name
        assert manifest["expected_permit_status"] == expected_status
        assert isinstance(manifest["expected_findings"], list)


def test_fixtures_are_small_and_readable() -> None:
    for fixture_dir in _fixture_dirs():
        files = _fixture_files(fixture_dir)
        assert len(files) <= 8
        for path in files:
            assert path.stat().st_size <= 4096
            path.read_text()


def test_fixtures_contain_no_real_secret_values() -> None:
    for fixture_dir in _fixture_dirs():
        for path in _fixture_files(fixture_dir):
            text = path.read_text()
            for marker in SECRET_VALUE_MARKERS:
                assert marker not in text, f"{path} contains secret-like marker {marker}"


def _fixture_dirs() -> list[Path]:
    return sorted(
        path
        for path in FIXTURES_DIR.iterdir()
        if path.is_dir() and path.name in EXPECTED_FIXTURES
    )


def _fixture_files(fixture_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in fixture_dir.rglob("*")
        if path.is_file() and ".agent-permit" not in path.parts
    )
