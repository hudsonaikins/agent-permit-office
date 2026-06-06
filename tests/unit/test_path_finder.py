from pathlib import Path

from agent_permit.capability_graph import CapabilityGraphBuilder
from agent_permit.path_finder import CapabilityPathFinder
from agent_permit.scanners.ci_workflows import CiWorkflowScanner
from agent_permit.scanners.credential_refs import CredentialReferenceScanner
from agent_permit.scanners.file_inventory import FileInventoryScanner
from agent_permit.scanners.mcp_config import McpConfigScanner
from agent_permit.scanners.prompt_instructions import PromptInstructionScanner


FIXTURES_DIR = Path(__file__).parents[1] / "fixtures"


def test_path_finder_finds_credential_to_mcp_path() -> None:
    target = FIXTURES_DIR / "risky-mcp-agent"
    codebase_map = _build_codebase_map(target, "run-mcp")

    report = CapabilityPathFinder().find_paths(codebase_map)
    paths_by_pair = {
        (path.source_id, path.sink_id, path.source_category, path.sink_category): path
        for path in report.paths
    }

    path = paths_by_pair[
        (
            "credential-ref:GITHUB_TOKEN",
            "mcp-server:.mcp.json:github-tools",
            "credential",
            "mcp_server",
        )
    ]
    assert path.severity == "high"
    assert path.node_ids == [
        "credential-ref:GITHUB_TOKEN",
        "mcp-server:.mcp.json:github-tools",
    ]
    assert path.edge_ids == [
        "edge:mcp-server:.mcp.json:github-tools:receives_credential:credential-ref:GITHUB_TOKEN"
    ]


def test_path_finder_finds_repo_config_to_remote_endpoint_path(tmp_path) -> None:
    (tmp_path / "mcp.json").write_text(
        """{
  "servers": {
    "docs": {
      "url": "https://example.com/mcp"
    }
  }
}
"""
    )
    codebase_map = _build_codebase_map(tmp_path, "run-remote")

    report = CapabilityPathFinder().find_paths(codebase_map)
    paths = [
        path
        for path in report.paths
        if path.source_category == "repo_config"
        and path.sink_category == "network_endpoint"
    ]

    assert len(paths) == 1
    assert paths[0].node_ids == [
        "file:mcp.json",
        "mcp-server:mcp.json:docs",
        "network-endpoint:https://example.com/mcp",
    ]
    assert paths[0].severity == "medium"


def test_path_finder_finds_workflow_file_to_privileged_workflow_path() -> None:
    target = FIXTURES_DIR / "risky-ci-agent"
    codebase_map = _build_codebase_map(target, "run-ci")

    report = CapabilityPathFinder().find_paths(codebase_map)
    paths = [
        path
        for path in report.paths
        if path.source_category == "workflow_file"
        and path.sink_category == "privileged_ci_workflow"
    ]

    assert len(paths) == 1
    assert paths[0].source_id == "file:.github/workflows/agent.yml"
    assert paths[0].sink_id == "workflow:.github/workflows/agent.yml"
    assert paths[0].severity == "high"


def test_path_finder_taxonomy_is_deterministic() -> None:
    target = FIXTURES_DIR / "poisoned-instructions"
    codebase_map = _build_codebase_map(target, "run-prompt")

    first = CapabilityPathFinder().find_paths(codebase_map)
    second = CapabilityPathFinder().find_paths(codebase_map)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def _build_codebase_map(target: Path, scan_run_id: str):
    inventory = FileInventoryScanner().scan(target, scan_run_id=scan_run_id)
    mcp_result = McpConfigScanner().scan(
        target,
        scan_run_id=scan_run_id,
        inventory=inventory,
    )
    mcp_result.agent_bom.credential_refs.extend(
        CredentialReferenceScanner().scan(
            target,
            scan_run_id=scan_run_id,
            inventory=inventory,
        )
    )
    findings = [
        *mcp_result.findings,
        *PromptInstructionScanner().scan(
            target,
            scan_run_id=scan_run_id,
            inventory=inventory,
        ),
        *CiWorkflowScanner().scan(
            target,
            scan_run_id=scan_run_id,
            inventory=inventory,
        ),
    ]
    return CapabilityGraphBuilder().build(
        scan_run_id=scan_run_id,
        inventory=inventory,
        agent_bom=mcp_result.agent_bom,
        findings=findings,
    ).codebase_map
