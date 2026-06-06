import json

from agent_permit.scanners.file_inventory import FileInventoryScanner


def test_file_inventory_classifies_high_signal_files_and_skips_junk(tmp_path) -> None:
    (tmp_path / ".gitignore").write_text("ignored.txt\nignored-dir/\n")
    (tmp_path / "AGENTS.md").write_text("# Instructions\n")
    (tmp_path / ".mcp.json").write_text('{"mcpServers": {}}\n')
    (tmp_path / "agent.py").write_text("print('agent')\n")
    (tmp_path / "ignored.txt").write_text("ignored\n")
    (tmp_path / "ignored-dir").mkdir()
    (tmp_path / "ignored-dir" / "kept-out.txt").write_text("ignored\n")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "tool.js").write_text("ignored\n")
    (tmp_path / ".agent-permit").mkdir()
    (tmp_path / ".agent-permit" / "generated.json").write_text("{}\n")
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "agent.yml").write_text("name: agent\n")

    inventory = FileInventoryScanner().scan(tmp_path, scan_run_id="run-1")
    files_by_path = {entry.path: entry for entry in inventory.files}

    assert set(files_by_path) == {
        ".gitignore",
        ".github/workflows/agent.yml",
        ".mcp.json",
        "AGENTS.md",
        "agent.py",
    }
    assert files_by_path["AGENTS.md"].kind == "agent_instruction"
    assert files_by_path["AGENTS.md"].high_signal is True
    assert files_by_path[".mcp.json"].kind == "mcp_config"
    assert files_by_path[".github/workflows/agent.yml"].kind == "ci_workflow"
    assert files_by_path["agent.py"].kind == "python"
    assert inventory.skipped["gitignore"] == 2
    assert inventory.skipped["junk_dir"] == 2


def test_file_inventory_skips_sensitive_env_files_without_secret_values(tmp_path) -> None:
    (tmp_path / ".env").write_text("OPENAI_API_KEY=sk-live-secret\n")
    (tmp_path / ".env.production").write_text("GITHUB_TOKEN=ghp_live_secret\n")
    (tmp_path / ".env.example").write_text("OPENAI_API_KEY=\n")

    inventory = FileInventoryScanner().scan(tmp_path, scan_run_id="run-env")
    disk_safe_payload = inventory.model_dump_json()

    assert [entry.path for entry in inventory.files] == [".env.example"]
    assert inventory.files[0].kind == "env_example"
    assert inventory.skipped["sensitive_env_file"] == 2
    assert "sk-live-secret" not in disk_safe_payload
    assert "ghp_live_secret" not in disk_safe_payload


def test_file_inventory_skips_binary_and_large_files(tmp_path) -> None:
    (tmp_path / "image.png").write_bytes(b"\x89PNG\x00binary")
    (tmp_path / "large.txt").write_text("x" * 21)

    inventory = FileInventoryScanner(max_file_bytes=20).scan(
        tmp_path,
        scan_run_id="run-skip",
    )

    assert inventory.files == []
    assert inventory.skipped == {"binary": 1, "too_large": 1}


def test_file_inventory_json_is_deterministic(tmp_path) -> None:
    (tmp_path / "b.py").write_text("print('b')\n")
    (tmp_path / "a.py").write_text("print('a')\n")

    inventory = FileInventoryScanner().scan(tmp_path, scan_run_id="run-sort")
    payload = json.loads(inventory.model_dump_json())

    assert [entry["path"] for entry in payload["files"]] == ["a.py", "b.py"]
