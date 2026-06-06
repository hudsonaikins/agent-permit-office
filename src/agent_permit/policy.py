from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Sequence

from pydantic import ValidationError

from agent_permit.models import (
    AgentPermitPolicy,
    Finding,
    GraphPathReport,
    PolicyAdjustment,
    PolicyEvaluation,
    Severity,
    TrustedWorkflowPermission,
)


DEFAULT_POLICY_FILE = "agent-permit-policy.json"
POLICY_EVALUATION_FILE = "policy-evaluation.json"


def load_policy(
    root_path: Path,
    policy_path: Path | None = None,
) -> tuple[AgentPermitPolicy | None, Path | None]:
    resolved_path = policy_path or (root_path / DEFAULT_POLICY_FILE)
    if not resolved_path.is_absolute():
        resolved_path = root_path / resolved_path
    if policy_path is None and not resolved_path.is_file():
        return None, None
    if not resolved_path.is_file():
        raise FileNotFoundError(f"policy file not found: {resolved_path}")
    try:
        payload = json.loads(resolved_path.read_text(encoding="utf-8"))
        return AgentPermitPolicy.model_validate(payload), resolved_path
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(f"invalid policy file: {resolved_path}: {exc}") from exc


def apply_policy(
    findings: Sequence[Finding],
    *,
    policy: AgentPermitPolicy,
    policy_path: Path,
    scan_run_id: str,
) -> tuple[list[Finding], PolicyEvaluation]:
    adjusted_findings: list[Finding] = []
    adjustments: list[PolicyAdjustment] = []

    for finding in findings:
        adjusted = finding
        for action, severity, human_review, rationale in _policy_decisions(
            finding,
            policy,
        ):
            updated = adjusted.model_copy(
                update={
                    "severity": severity,
                    "requires_human_review": human_review,
                }
            )
            if updated.severity != adjusted.severity:
                adjustments.append(
                    PolicyAdjustment(
                        finding_id=finding.id,
                        rule_id=finding.rule_id,
                        action=action,
                        from_severity=Severity(adjusted.severity),
                        to_severity=Severity(updated.severity),
                        rationale=rationale,
                    )
                )
            adjusted = updated
        adjusted_findings.append(adjusted)

    return adjusted_findings, PolicyEvaluation(
        scan_run_id=scan_run_id,
        policy_path=str(policy_path),
        adjustments=adjustments,
        findings_before=len(findings),
        findings_after=len(adjusted_findings),
    )


def write_policy_evaluation(
    evaluation: PolicyEvaluation,
    output_dir: Path,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / POLICY_EVALUATION_FILE
    path.write_text(
        json.dumps(evaluation.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def apply_policy_to_graph_paths(
    graph_paths: GraphPathReport,
    *,
    policy: AgentPermitPolicy,
) -> GraphPathReport:
    if not policy.allowed_mcp_servers:
        return graph_paths

    adjusted_paths = []
    for path in graph_paths.paths:
        server_name = path.sink_id.rsplit(":", 1)[-1]
        if (
            path.source_category == "credential"
            and path.sink_category == "mcp_server"
            and server_name in set(policy.allowed_mcp_servers)
        ):
            adjusted_paths.append(
                path.model_copy(
                    update={
                        "severity": Severity.LOW,
                        "rationale": (
                            path.rationale
                            + " Policy allowlists this MCP server for local use."
                        ),
                    }
                )
            )
        else:
            adjusted_paths.append(path)
    return graph_paths.model_copy(update={"paths": adjusted_paths})


def _policy_decisions(
    finding: Finding,
    policy: AgentPermitPolicy,
) -> list[tuple[str, Severity, bool, str]]:
    decisions: list[tuple[str, Severity, bool, str]] = []

    if (
        finding.rule_id == "mcp-stdio-credential-ref"
        and _mcp_server_name(finding) in set(policy.allowed_mcp_servers)
    ):
        decisions.append(
            (
                "allowed_mcp_server",
                Severity.LOW,
                False,
                "Policy allowlists this MCP server for local credential review.",
            )
        )

    if (
        finding.rule_id == "ci-write-permission"
        and _trusted_workflow_permission(finding, policy.trusted_workflow_permissions)
    ):
        decisions.append(
            (
                "trusted_workflow_permission",
                Severity.LOW,
                False,
                "Policy marks this workflow permission as trusted for this path/scope.",
            )
        )

    if (
        finding.rule_id == "ci-secret-reference"
        and _approved_secret_reference(finding, policy.approved_credential_refs)
    ):
        decisions.append(
            (
                "approved_credential_ref",
                Severity.LOW,
                False,
                "Policy approves this credential reference outside pull_request_target.",
            )
        )

    override = policy.severity_overrides.get(finding.rule_id)
    if override is not None:
        decisions.append(
            (
                "severity_override",
                Severity(override),
                _requires_review_for(Severity(override)),
                "Policy overrides severity for this rule ID.",
            )
        )

    return decisions


def _mcp_server_name(finding: Finding) -> str | None:
    for evidence in finding.evidence:
        if evidence.config_key:
            match = re.match(r"^mcpServers\.(?P<server>[^.]+)\.", evidence.config_key)
            if match is not None:
                return match.group("server")
    if finding.id.startswith("finding:mcp-"):
        return finding.id.rsplit(":", 1)[-1]
    return None


def _trusted_workflow_permission(
    finding: Finding,
    permissions: Sequence[TrustedWorkflowPermission],
) -> bool:
    for evidence in finding.evidence:
        for permission in permissions:
            if evidence.path != permission.path:
                continue
            if evidence.permission_scope != permission.scope:
                continue
            if permission.job is not None and evidence.workflow_job != permission.job:
                continue
            if permission.event is not None and not _event_matches(
                evidence.workflow_event,
                permission.event,
            ):
                continue
            return True
    return False


def _approved_secret_reference(
    finding: Finding,
    approved_credential_refs: Sequence[str],
) -> bool:
    approved = set(approved_credential_refs)
    for evidence in finding.evidence:
        if evidence.secret_name not in approved:
            continue
        if _event_matches(evidence.workflow_event, "pull_request_target"):
            continue
        return True
    return False


def _event_matches(actual: str | None, expected: str) -> bool:
    if actual is None:
        return False
    events = {part.strip() for part in actual.split(",") if part.strip()}
    return expected in events


def _requires_review_for(severity: Severity) -> bool:
    return severity in {Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM}
