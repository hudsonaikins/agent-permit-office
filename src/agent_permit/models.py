from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list[JsonScalar] | dict[str, JsonScalar]

_FORBIDDEN_PAYLOAD_KEYS = {
    "password",
    "password_value",
    "private_key",
    "raw",
    "raw_secret",
    "raw_value",
    "secret",
    "secret_value",
    "token",
    "token_value",
    "value",
}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)


def reject_forbidden_payload_keys(payload: dict[str, JsonValue]) -> dict[str, JsonValue]:
    bad_keys = sorted(key for key in payload if key.lower() in _FORBIDDEN_PAYLOAD_KEYS)
    if bad_keys:
        raise ValueError(
            "payload cannot contain raw secret/value keys: " + ", ".join(bad_keys)
        )
    return payload


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class FactKind(str, Enum):
    FILE = "file"
    AGENT = "agent"
    TOOL = "tool"
    MCP_SERVER = "mcp_server"
    CREDENTIAL_REF = "credential_ref"
    PROMPT_INSTRUCTION = "prompt_instruction"
    WORKFLOW = "workflow"
    PACKAGE = "package"
    CAPABILITY = "capability"
    CONTROL = "control"


class FileKind(str, Enum):
    AGENT_INSTRUCTION = "agent_instruction"
    MCP_CONFIG = "mcp_config"
    CI_WORKFLOW = "ci_workflow"
    ENV_EXAMPLE = "env_example"
    PACKAGE_MANIFEST = "package_manifest"
    LOCKFILE = "lockfile"
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    MARKDOWN = "markdown"
    YAML = "yaml"
    JSON = "json"
    TOML = "toml"
    OTHER = "other"


class FindingCategory(str, Enum):
    TOOL_ACCESS = "tool_access"
    CREDENTIAL_SCOPE = "credential_scope"
    PROMPT_RISK = "prompt_risk"
    MCP_RISK = "mcp_risk"
    FILESYSTEM_RISK = "filesystem_risk"
    NETWORK_RISK = "network_risk"
    MEMORY_RISK = "memory_risk"
    SUPPLY_CHAIN = "supply_chain"
    RUNTIME_POLICY = "runtime_policy"


class GraphEdgeKind(str, Enum):
    USES = "uses"
    REGISTERS = "registers"
    DELEGATES_TO = "delegates_to"
    LAUNCHES = "launches"
    RECEIVES_CREDENTIAL = "receives_credential"
    READS = "reads"
    WRITES = "writes"
    SENDS_TO = "sends_to"
    IMPORTS = "imports"
    CALLS = "calls"
    INFLUENCED_BY = "influenced_by"
    TRUSTS = "trusts"
    GATED_BY = "gated_by"
    LACKS_GATE = "lacks_gate"
    SANITIZES = "sanitizes"
    BLOCKS = "blocks"
    PINS_VERSION = "pins_version"
    RUNS_IN = "runs_in"


class GraphNodeKind(str, Enum):
    AGENT = "agent"
    SUBAGENT = "subagent"
    TOOL = "tool"
    MCP_SERVER = "mcp_server"
    PROMPT = "prompt"
    INSTRUCTION = "instruction"
    CREDENTIAL_REF = "credential_ref"
    SECRET_SOURCE = "secret_source"
    MEMORY_STORE = "memory_store"
    FILE_SET = "file_set"
    NETWORK_ENDPOINT = "network_endpoint"
    CLOUD_ROLE = "cloud_role"
    CI_WORKFLOW = "ci_workflow"
    SANDBOX = "sandbox"
    APPROVAL_GATE = "approval_gate"
    HUMAN_REVIEWER = "human_reviewer"
    PACKAGE = "package"
    COMMAND = "command"
    CONTROL = "control"


class PermitStatus(str, Enum):
    APPROVED = "approved"
    APPROVED_WITH_CONDITIONS = "approved_with_conditions"
    NEEDS_REVIEW = "needs_review"
    BLOCKED = "blocked"


class ScanRunStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class EvidenceLocation(StrictModel):
    path: str
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)
    config_key: str | None = None
    package: str | None = None
    command: str | None = None
    redacted_snippet: str | None = None

    @model_validator(mode="after")
    def validate_line_range(self) -> EvidenceLocation:
        if (
            self.line_start is not None
            and self.line_end is not None
            and self.line_end < self.line_start
        ):
            raise ValueError("line_end must be greater than or equal to line_start")
        return self


class Fact(StrictModel):
    id: str
    kind: FactKind
    name: str
    source: EvidenceLocation
    attributes: dict[str, JsonValue] = Field(default_factory=dict)
    confidence: Confidence = Confidence.HIGH

    @field_validator("attributes")
    @classmethod
    def reject_secret_payload_keys(cls, attributes: dict[str, JsonValue]) -> dict[str, JsonValue]:
        return reject_forbidden_payload_keys(attributes)


class CredentialRef(StrictModel):
    name: str
    provider: str | None = None
    scope_hint: str | None = None
    attached_to: str | None = None
    source: EvidenceLocation


class GraphNode(StrictModel):
    id: str
    kind: GraphNodeKind
    label: str
    source_fact_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def reject_secret_metadata_keys(cls, metadata: dict[str, JsonValue]) -> dict[str, JsonValue]:
        return reject_forbidden_payload_keys(metadata)


class GraphEdge(StrictModel):
    id: str
    source_id: str
    target_id: str
    kind: GraphEdgeKind
    source_fact_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def reject_secret_metadata_keys(cls, metadata: dict[str, JsonValue]) -> dict[str, JsonValue]:
        return reject_forbidden_payload_keys(metadata)


class Finding(StrictModel):
    id: str
    rule_id: str
    title: str
    severity: Severity
    category: FindingCategory
    evidence: list[EvidenceLocation]
    risk: str
    recommendation: str
    confidence: Confidence
    requires_human_review: bool = False
    source_fact_ids: list[str] = Field(default_factory=list)


class EvidencePack(StrictModel):
    id: str
    finding_id: str
    summary: str
    evidence: list[EvidenceLocation]
    related_fact_ids: list[str] = Field(default_factory=list)
    redaction_applied: bool = True
    artifact_path: str | None = None

    @field_validator("redaction_applied")
    @classmethod
    def require_redaction(cls, redaction_applied: bool) -> bool:
        if not redaction_applied:
            raise ValueError("evidence packs must be redacted by default")
        return redaction_applied


class AgentSummary(StrictModel):
    id: str
    name: str
    framework: str | None = None
    source_fact_ids: list[str] = Field(default_factory=list)


class ToolSummary(StrictModel):
    id: str
    name: str
    kind: str
    source_fact_ids: list[str] = Field(default_factory=list)


class McpServerSummary(StrictModel):
    id: str
    name: str
    transport: str
    command: str | None = None
    url: str | None = None
    source_fact_ids: list[str] = Field(default_factory=list)


class AgentBom(StrictModel):
    scan_run_id: str
    agents: list[AgentSummary] = Field(default_factory=list)
    tools: list[ToolSummary] = Field(default_factory=list)
    mcp_servers: list[McpServerSummary] = Field(default_factory=list)
    credential_refs: list[CredentialRef] = Field(default_factory=list)


class CodebaseMap(StrictModel):
    scan_run_id: str
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    facts: list[Fact] = Field(default_factory=list)


class ScanRun(StrictModel):
    id: str
    target_path: Path
    artifact_dir: Path
    status: ScanRunStatus = ScanRunStatus.CREATED
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    completed_at: datetime | None = None


class FileInventoryEntry(StrictModel):
    path: str
    kind: FileKind
    size_bytes: int = Field(ge=0)
    sha256: str
    is_text: bool = True
    high_signal: bool = False
    language: str | None = None


class FileInventory(StrictModel):
    scan_run_id: str
    root_path: str
    files: list[FileInventoryEntry] = Field(default_factory=list)
    skipped: dict[str, int] = Field(default_factory=dict)


class Permit(StrictModel):
    scan_run_id: str
    status: PermitStatus
    agent_name: str
    owner: str | None = None
    purpose: str | None = None
    discovered_tools: list[str] = Field(default_factory=list)
    discovered_credentials: list[str] = Field(default_factory=list)
    allowed_actions: list[str] = Field(default_factory=list)
    forbidden_actions: list[str] = Field(default_factory=list)
    required_approvals: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    expires_at: date | None = None
    findings_summary: dict[Severity, int] = Field(default_factory=dict)
    evidence_bundle_path: str | None = None

    @field_validator("discovered_credentials")
    @classmethod
    def credential_names_only(cls, credential_names: list[str]) -> list[str]:
        for credential_name in credential_names:
            if "=" in credential_name:
                raise ValueError(
                    "discovered_credentials must contain variable names only"
                )
        return credential_names
