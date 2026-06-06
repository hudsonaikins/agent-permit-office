from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_permit.models import (
    AgentBom,
    ControlReport,
    Finding,
    GraphPathReport,
)
from agent_permit.redaction import redact_secret_text
from agent_permit.rule_registry import RULES_BY_ID


ALLOWED_EVIDENCE_ARTIFACTS = frozenset(
    {
        "agent-bom.json",
        "controls.json",
        "finding-baseline.json",
        "finding-diff.json",
        "finding-diff.md",
        "graph-paths.json",
        "permit.yaml",
        "policy-evaluation.json",
        "raw-findings.json",
        "risk-report.md",
        "summary.md",
    }
)
MAX_ARTIFACT_READ_CHARS = 20_000


@dataclass(frozen=True)
class EvidenceArtifact:
    name: str
    path: Path
    size_bytes: int


@dataclass(frozen=True)
class EvidenceSummary:
    scan_run_id: str
    permit_status: str
    findings_count: int
    graph_paths_count: int
    controls_count: int
    credential_names: tuple[str, ...]
    available_artifacts: tuple[str, ...]


@dataclass(frozen=True)
class EvidenceContext:
    artifact_dir: Path
    scan_run_id: str
    permit_status: str
    findings: tuple[Finding, ...]
    graph_paths: GraphPathReport
    controls: ControlReport
    agent_bom: AgentBom
    available_artifacts: tuple[EvidenceArtifact, ...]

    @classmethod
    def load(cls, artifact_dir: Path) -> EvidenceContext:
        artifact_dir = artifact_dir.resolve()
        if not artifact_dir.is_dir():
            raise FileNotFoundError(f"artifact directory not found: {artifact_dir}")

        raw_findings_payload = _read_json(artifact_dir / "raw-findings.json")
        findings = tuple(
            Finding.model_validate(finding)
            for finding in raw_findings_payload.get("findings", [])
        )
        graph_paths = GraphPathReport.model_validate(
            _read_json(artifact_dir / "graph-paths.json")
        )
        controls = ControlReport.model_validate(_read_json(artifact_dir / "controls.json"))
        agent_bom = AgentBom.model_validate(_read_json(artifact_dir / "agent-bom.json"))
        permit_status = _read_permit_status(artifact_dir / "permit.yaml")
        scan_run_id = str(
            raw_findings_payload.get("scan_run_id")
            or graph_paths.scan_run_id
            or controls.scan_run_id
            or agent_bom.scan_run_id
        )

        artifacts = tuple(
            EvidenceArtifact(
                name=name,
                path=artifact_dir / name,
                size_bytes=(artifact_dir / name).stat().st_size,
            )
            for name in sorted(ALLOWED_EVIDENCE_ARTIFACTS)
            if (artifact_dir / name).is_file()
        )
        return cls(
            artifact_dir=artifact_dir,
            scan_run_id=scan_run_id,
            permit_status=permit_status,
            findings=findings,
            graph_paths=graph_paths,
            controls=controls,
            agent_bom=agent_bom,
            available_artifacts=artifacts,
        )

    def summary(self) -> EvidenceSummary:
        return EvidenceSummary(
            scan_run_id=self.scan_run_id,
            permit_status=self.permit_status,
            findings_count=len(self.findings),
            graph_paths_count=len(self.graph_paths.paths),
            controls_count=len(self.controls.controls),
            credential_names=tuple(
                sorted({credential.name for credential in self.agent_bom.credential_refs})
            ),
            available_artifacts=tuple(artifact.name for artifact in self.available_artifacts),
        )

    def list_artifacts(self) -> list[str]:
        return [artifact.name for artifact in self.available_artifacts]

    def read_artifact(self, name: str) -> str:
        if name not in ALLOWED_EVIDENCE_ARTIFACTS:
            raise PermissionError(f"artifact is not in bounded evidence set: {name}")
        path = self.artifact_dir / name
        if not path.is_file():
            raise FileNotFoundError(f"artifact not found: {name}")
        text = path.read_text(encoding="utf-8")
        return redact_secret_text(text[:MAX_ARTIFACT_READ_CHARS])

    def citation_ids(self) -> set[str]:
        citation_ids = {"permit", "summary", "risk-report"}
        citation_ids.update(f"artifact:{artifact.name}" for artifact in self.available_artifacts)
        citation_ids.update(f"finding:{finding.id}" for finding in self.findings)
        citation_ids.update(f"rule:{finding.rule_id}" for finding in self.findings)
        citation_ids.update(f"path:{path.id}" for path in self.graph_paths.paths)
        citation_ids.update(f"control:{control.id}" for control in self.controls.controls)
        return citation_ids

    def finding_rule_ids(self) -> set[str]:
        return {finding.rule_id for finding in self.findings}

    def get_finding(self, identifier: str) -> list[dict[str, Any]]:
        matches = [
            finding.model_dump(mode="json")
            for finding in self.findings
            if finding.id == identifier or finding.rule_id == identifier
        ]
        return matches

    def find_paths(
        self,
        *,
        source_category: str | None = None,
        sink_category: str | None = None,
    ) -> list[dict[str, Any]]:
        paths = []
        for graph_path in self.graph_paths.paths:
            if source_category is not None and graph_path.source_category != source_category:
                continue
            if sink_category is not None and graph_path.sink_category != sink_category:
                continue
            paths.append(graph_path.model_dump(mode="json"))
        return paths

    def get_agent_bom(self) -> dict[str, Any]:
        return self.agent_bom.model_dump(mode="json")

    def get_mcp_servers(self) -> list[dict[str, Any]]:
        return [
            server.model_dump(mode="json")
            for server in self.agent_bom.mcp_servers
        ]

    def get_credential_refs(self) -> list[dict[str, Any]]:
        return [
            credential.model_dump(mode="json")
            for credential in self.agent_bom.credential_refs
        ]

    def explain_rule(self, rule_id: str) -> dict[str, Any] | None:
        rule = RULES_BY_ID.get(rule_id)
        if rule is None:
            return None
        return {
            "rule_id": rule.rule_id,
            "scanner": rule.scanner,
            "title": rule.title,
            "default_severity": rule.default_severity,
            "category": rule.category,
        }


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"required artifact not found: {path.name}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"artifact must contain a JSON object: {path.name}")
    return payload


def _read_permit_status(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"required artifact not found: {path.name}")
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("status:"):
            return line.split(":", 1)[1].strip()
    return "unknown"
