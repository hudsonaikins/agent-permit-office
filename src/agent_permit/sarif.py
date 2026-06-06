from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from agent_permit import __version__
from agent_permit.evidence_context import EvidenceContext
from agent_permit.models import EvidenceLocation, Finding, Severity
from agent_permit.rule_registry import RULES_BY_ID


SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"
SARIF_VERSION = "2.1.0"
SARIF_FILE = "results.sarif"
DEFAULT_SARIF_CATEGORY = "agent-permit-office"

_SARIF_SECURITY_SEVERITY = {
    Severity.CRITICAL: "9.0",
    Severity.HIGH: "7.0",
    Severity.MEDIUM: "5.0",
    Severity.LOW: "2.0",
    Severity.INFO: "1.0",
}


def build_sarif_log(
    context: EvidenceContext,
    *,
    category: str = DEFAULT_SARIF_CATEGORY,
) -> dict[str, Any]:
    findings = sorted(context.findings, key=lambda finding: finding.id)
    rule_ids = sorted({finding.rule_id for finding in findings})
    rule_indexes = {rule_id: index for index, rule_id in enumerate(rule_ids)}
    return {
        "$schema": SARIF_SCHEMA,
        "version": SARIF_VERSION,
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "Agent Permit Office",
                        "semanticVersion": __version__,
                        "rules": [_build_rule(rule_id) for rule_id in rule_ids],
                    }
                },
                "automationDetails": {
                    "id": category,
                },
                "invocations": [
                    {
                        "executionSuccessful": True,
                        "properties": {
                            "scan_run_id": context.scan_run_id,
                            "permit_status": context.permit_status,
                        },
                    }
                ],
                "results": [
                    _build_result(finding, rule_indexes[finding.rule_id])
                    for finding in findings
                ],
            }
        ],
    }


def write_sarif_file(
    context: EvidenceContext,
    output_path: Path | None = None,
    *,
    category: str = DEFAULT_SARIF_CATEGORY,
) -> Path:
    output_path = output_path or (context.artifact_dir / SARIF_FILE)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(build_sarif_log(context, category=category), indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    return output_path


def _build_rule(rule_id: str) -> dict[str, Any]:
    definition = RULES_BY_ID.get(rule_id)
    if definition is None:
        return {
            "id": rule_id,
            "name": rule_id,
            "shortDescription": {"text": rule_id},
        }
    return {
        "id": definition.rule_id,
        "name": definition.title,
        "shortDescription": {"text": definition.title},
        "defaultConfiguration": {
            "level": _level_for_severity(definition.default_severity),
        },
        "properties": {
            "category": definition.category,
            "precision": "high",
            "problem.severity": definition.default_severity,
            "security-severity": _security_severity(definition.default_severity),
            "tags": [
                "security",
                "agent-security",
                str(definition.category),
                str(definition.scanner),
            ],
        },
    }


def _build_result(finding: Finding, rule_index: int) -> dict[str, Any]:
    result = {
        "ruleId": finding.rule_id,
        "ruleIndex": rule_index,
        "level": _level_for_severity(Severity(finding.severity)),
        "message": {
            "text": _result_message(finding),
        },
        "locations": [_build_location(location) for location in finding.evidence],
        "partialFingerprints": {
            "agentPermitFinding/v1": _finding_fingerprint(finding),
        },
        "properties": {
            "agent_permit_finding_id": finding.id,
            "category": finding.category,
            "confidence": finding.confidence,
            "requires_human_review": finding.requires_human_review,
            "severity": finding.severity,
        },
    }
    if not result["locations"]:
        result.pop("locations")
    return result


def _build_location(location: EvidenceLocation) -> dict[str, Any]:
    physical_location: dict[str, Any] = {
        "artifactLocation": {
            "uri": location.path,
            "uriBaseId": "%SRCROOT%",
        }
    }
    region: dict[str, Any] = {}
    if location.line_start is not None:
        region["startLine"] = location.line_start
    if location.line_end is not None:
        region["endLine"] = location.line_end
    if region:
        physical_location["region"] = region
    return {"physicalLocation": physical_location}


def _result_message(finding: Finding) -> str:
    return (
        f"{finding.title}. Risk: {finding.risk} "
        f"Recommendation: {finding.recommendation}"
    )


def _finding_fingerprint(finding: Finding) -> str:
    evidence = finding.evidence[0] if finding.evidence else None
    path = evidence.path if evidence is not None else ""
    line = evidence.line_start if evidence is not None else ""
    digest_input = "|".join(
        [
            finding.rule_id,
            path,
            str(line),
            finding.title,
        ]
    ).encode("utf-8")
    return hashlib.sha256(digest_input).hexdigest()


def _level_for_severity(severity: Severity) -> str:
    if severity in {Severity.CRITICAL, Severity.HIGH}:
        return "error"
    if severity is Severity.MEDIUM:
        return "warning"
    return "note"


def _security_severity(severity: Severity) -> str:
    return _SARIF_SECURITY_SEVERITY[severity]
