from __future__ import annotations

import re


_SECRET_ASSIGNMENT_RE = re.compile(
    r"\b([A-Z0-9_]*(?:API_KEY|TOKEN|SECRET|PASSWORD|PRIVATE_KEY)[A-Z0-9_]*)"
    r"\s*=\s*(\"[^\"]+\"|'[^']+'|\S+)",
    re.IGNORECASE,
)
_SECRET_VALUE_RES = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{12,}\b"),
    re.compile(r"\bghp_[A-Za-z0-9_]{8,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{8,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\bxoxb-[A-Za-z0-9-]{8,}\b"),
)


def redact_secret_text(text: str) -> str:
    redacted = _SECRET_ASSIGNMENT_RE.sub(r"\1=<redacted>", text)
    for pattern in _SECRET_VALUE_RES:
        redacted = pattern.sub("<redacted>", redacted)
    return redacted
