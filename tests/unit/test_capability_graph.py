from pathlib import Path

from agent_permit.capability_graph import CapabilityGraphBuilder
from agent_permit.scanners.ci_workflows import CiWorkflowScanner
from agent_permit.scanners.credential_refs import CredentialReferenceScanner
from agent_permit.scanners.file_inventory import FileInventoryScanner
from agent_permit.scanners.mcp_config import McpConfigScanner
from agent_permit.scanners.prompt_instructions import PromptInstructionScanner


FIXTURES_DIR = Path(__file__).parents[1] / "fixtures"


def test_graph_builder_links_mcp_server_to_credential() -> None:
    target = FIXTURES_DIR / "risky-mcp-agent"
    inventory = FileInventoryScanner().scan(target, scan_run_id="run-mcp")
    mcp_result = McpConfigScanner().scan(
        target,
        scan_run_id="run-mcp",
        inventory=inventory,
    )
    credential_refs = CredentialReferenceScanner().scan(
        target,
        scan_run_id="run-mcp",
        inventory=inventory,
    )
    mcp_result.agent_bom.credential_refs.extend(credential_refs)

    result = CapabilityGraphBuilder().build(
        scan_run_id="run-mcp",
        inventory=inventory,
        agent_bom=mcp_result.agent_bom,
        findings=mcp_result.findings,
    )
    node_ids = {node.id for node in result.codebase_map.nodes}
    edge_index = {
        (edge.source_id, edge.target_id, edge.kind)
        for edge in result.codebase_map.edges
    }
    fact_ids = {fact.id for fact in result.codebase_map.facts}

    assert "file:.mcp.json" in node_ids
    assert "mcp-server:.mcp.json:github-tools" in node_ids
    assert "credential-ref:GITHUB_TOKEN" in node_ids
    assert (
        "mcp-server:.mcp.json:github-tools",
        "credential-ref:GITHUB_TOKEN",
        "receives_credential",
    ) in edge_index
    assert (
        "file:.mcp.json",
        "mcp-server:.mcp.json:github-tools",
        "launches",
    ) in edge_index
    assert "mcp-server:.mcp.json:github-tools" in fact_ids
    assert "mcp-server:.mcp.json:github-tools" in result.findings[0].source_fact_ids


def test_graph_builder_adds_prompt_instruction_context() -> None:
    target = FIXTURES_DIR / "poisoned-instructions"
    inventory = FileInventoryScanner().scan(target, scan_run_id="run-prompt")
    findings = PromptInstructionScanner().scan(
        target,
        scan_run_id="run-prompt",
        inventory=inventory,
    )

    result = CapabilityGraphBuilder().build(
        scan_run_id="run-prompt",
        inventory=inventory,
        agent_bom=_empty_agent_bom("run-prompt"),
        findings=findings,
    )
    instruction_nodes = [
        node for node in result.codebase_map.nodes if node.kind == "instruction"
    ]
    prompt_facts = [
        fact for fact in result.codebase_map.facts if fact.kind == "prompt_instruction"
    ]

    assert instruction_nodes
    assert prompt_facts
    assert all(finding.source_fact_ids for finding in result.findings)


def test_graph_builder_adds_ci_workflow_context() -> None:
    target = FIXTURES_DIR / "risky-ci-agent"
    inventory = FileInventoryScanner().scan(target, scan_run_id="run-ci")
    findings = CiWorkflowScanner().scan(
        target,
        scan_run_id="run-ci",
        inventory=inventory,
    )

    result = CapabilityGraphBuilder().build(
        scan_run_id="run-ci",
        inventory=inventory,
        agent_bom=_empty_agent_bom("run-ci"),
        findings=findings,
    )
    workflow_nodes = [
        node for node in result.codebase_map.nodes if node.kind == "ci_workflow"
    ]
    workflow_facts = [
        fact for fact in result.codebase_map.facts if fact.kind == "workflow"
    ]

    assert workflow_nodes[0].id == "workflow:.github/workflows/agent.yml"
    assert len(workflow_facts) == len(findings)
    assert all(finding.source_fact_ids for finding in result.findings)
    secret_fact = next(
        fact
        for fact in workflow_facts
        if fact.attributes["rule_id"] == "ci-secret-reference"
    )
    assert secret_fact.attributes["workflow_job"] == "agent-review"
    assert secret_fact.attributes["secret_name"] == "GITHUB_TOKEN"


def test_graph_builder_output_is_deterministic() -> None:
    target = FIXTURES_DIR / "risky-ci-agent"
    inventory = FileInventoryScanner().scan(target, scan_run_id="run-stable")
    findings = CiWorkflowScanner().scan(
        target,
        scan_run_id="run-stable",
        inventory=inventory,
    )

    first = CapabilityGraphBuilder().build(
        scan_run_id="run-stable",
        inventory=inventory,
        agent_bom=_empty_agent_bom("run-stable"),
        findings=findings,
    )
    second = CapabilityGraphBuilder().build(
        scan_run_id="run-stable",
        inventory=inventory,
        agent_bom=_empty_agent_bom("run-stable"),
        findings=findings,
    )

    assert first.codebase_map.model_dump(mode="json") == second.codebase_map.model_dump(
        mode="json"
    )


def _empty_agent_bom(scan_run_id: str):
    from agent_permit.models import AgentBom

    return AgentBom(scan_run_id=scan_run_id)
