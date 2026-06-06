from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from agent_permit.models import (
    Confidence,
    EvidenceLocation,
    FileInventory,
    FileKind,
    Finding,
    FindingCategory,
    Severity,
)
from agent_permit.redaction import redact_secret_text


@dataclass(frozen=True)
class PromptRule:
    rule_id: str
    title: str
    severity: Severity
    patterns: tuple[re.Pattern[str], ...]
    risk: str
    recommendation: str


PROMPT_RULES = (
    PromptRule(
        rule_id="prompt-ignore-instructions",
        title="Instruction attempts to ignore higher-priority instructions",
        severity=Severity.HIGH,
        patterns=(
            re.compile(
                r"\bignore\s+(?:all\s+)?(?:prior|previous|system|developer|user)"
                r"\s+instructions?\b",
                re.IGNORECASE,
            ),
        ),
        risk=(
            "Prompt text that tells the agent to ignore higher-priority "
            "instructions can override the intended safety and approval model."
        ),
        recommendation=(
            "Remove the instruction override and keep authority boundaries "
            "explicit in agent instruction files."
        ),
    ),
    PromptRule(
        rule_id="prompt-approval-bypass",
        title="Instruction attempts to bypass approval",
        severity=Severity.HIGH,
        patterns=(
            re.compile(r"\bignore\s+approval\s+requirements?\b", re.IGNORECASE),
            re.compile(
                r"\b(?:do\s+not|don't|never)\s+ask(?:\s+the\s+user)?"
                r"(?:\s+before|\s+for\s+(?:approval|permission))",
                re.IGNORECASE,
            ),
            re.compile(
                r"\b(?:bypass|skip|override)\s+(?:approval|permission|review)\b",
                re.IGNORECASE,
            ),
            re.compile(r"\bauto-?approve\b", re.IGNORECASE),
        ),
        risk=(
            "Approval-bypass language can cause an agent to use tools, write "
            "files, or take external actions without the expected human gate."
        ),
        recommendation=(
            "Require explicit approval for sensitive tools and remove wording "
            "that suppresses user confirmation."
        ),
    ),
    PromptRule(
        rule_id="prompt-credential-exfiltration",
        title="Instruction attempts credential or source-code exfiltration",
        severity=Severity.CRITICAL,
        patterns=(
            re.compile(
                r"\bsend\s+(?:them|it|credentials?|secrets?|private\s+source\s+code)"
                r".*(?:external|endpoint|server|url|webhook)\b",
                re.IGNORECASE,
            ),
            re.compile(r"\bexfiltrat(?:e|ion|ing)?\b", re.IGNORECASE),
            re.compile(r"\bleak\s+(?:credentials?|secrets?|source\s+code)\b", re.IGNORECASE),
        ),
        risk=(
            "The instruction asks the agent to move secrets or private code to "
            "an external destination."
        ),
        recommendation=(
            "Block this agent until the exfiltration instruction is removed and "
            "the source of the instruction is reviewed."
        ),
    ),
    PromptRule(
        rule_id="prompt-safety-disable",
        title="Instruction attempts to disable safety checks",
        severity=Severity.HIGH,
        patterns=(
            re.compile(r"\bdisable\s+safety\s+checks?\b", re.IGNORECASE),
            re.compile(r"\b(?:bypass|ignore|turn\s+off)\s+safety\b", re.IGNORECASE),
        ),
        risk=(
            "Safety-disable language can suppress runtime controls that should "
            "remain active for tool and credential access."
        ),
        recommendation=(
            "Remove safety-disable instructions and require review before "
            "running this agent with sensitive capabilities."
        ),
    ),
    PromptRule(
        rule_id="prompt-hidden-instruction",
        title="Instruction attempts to hide itself from review",
        severity=Severity.HIGH,
        patterns=(
            re.compile(
                r"\b(?:do\s+not|don't|never)\s+(?:mention|disclose|reveal|report)"
                r".*(?:instruction|policy|rule)\b",
                re.IGNORECASE,
            ),
            re.compile(r"\bhidden\s+instruction\b", re.IGNORECASE),
        ),
        risk=(
            "Hidden-instruction language makes review and incident response less "
            "reliable because the agent is told not to disclose risky behavior."
        ),
        recommendation=(
            "Remove concealment language and require reports to disclose all "
            "relevant instructions and tool-use constraints."
        ),
    ),
)


class PromptInstructionScanner:
    def scan(
        self,
        root_path: Path,
        *,
        scan_run_id: str,
        inventory: FileInventory,
    ) -> list[Finding]:
        root_path = root_path.resolve()
        findings: list[Finding] = []

        for entry in inventory.files:
            if entry.kind != FileKind.AGENT_INSTRUCTION:
                continue

            instruction_path = root_path / entry.path
            text = instruction_path.read_text(encoding="utf-8", errors="replace")
            findings.extend(_scan_instruction_text(entry.path, text))

        return findings


def _scan_instruction_text(rel_path: str, text: str) -> list[Finding]:
    findings: list[Finding] = []
    previous_non_empty: list[str] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        if _is_prohibition_list_item(line, previous_non_empty):
            previous_non_empty.append(line)
            continue

        for rule in PROMPT_RULES:
            if any(pattern.search(line) for pattern in rule.patterns):
                findings.append(_finding_for_rule(rule, rel_path, line_number, line))

        previous_non_empty.append(line)
    return findings


def _is_prohibition_list_item(line: str, previous_non_empty: list[str]) -> bool:
    stripped = line.strip()
    if not stripped.startswith(("- ", "* ")):
        return False
    for previous_line in reversed(previous_non_empty):
        normalized = previous_line.strip().lower()
        if normalized.startswith(("- ", "* ")):
            continue
        if normalized.endswith(("must not:", "must never:", "forbidden:")):
            return True
        return False
    return False


def _finding_for_rule(
    rule: PromptRule,
    rel_path: str,
    line_number: int,
    line: str,
) -> Finding:
    return Finding(
        id=f"finding:{rule.rule_id}:{rel_path}:{line_number}",
        rule_id=rule.rule_id,
        title=rule.title,
        severity=rule.severity,
        category=FindingCategory.PROMPT_RISK,
        evidence=[
            EvidenceLocation(
                path=rel_path,
                line_start=line_number,
                line_end=line_number,
                redacted_snippet=redact_secret_text(line.strip()),
            )
        ],
        risk=rule.risk,
        recommendation=rule.recommendation,
        confidence=Confidence.HIGH,
        requires_human_review=True,
    )
