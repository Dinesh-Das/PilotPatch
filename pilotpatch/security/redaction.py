import re
from typing import Any

_KEY_LABEL = r"[^\r\n-]*PRIVATE KEY-----"
_KEY_LINE_MARKER = re.compile(rf"-----(BEGIN|END) {_KEY_LABEL}".encode())

_PATTERNS = [
    (
        re.compile(rf"-----BEGIN {_KEY_LABEL}[\s\S]*?(?:-----END {_KEY_LABEL}|\Z)"),
        "[REDACTED PRIVATE KEY]",
    ),
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"), "Bearer [REDACTED]"),
    (
        re.compile(
            r"(?im)(\b(?:password|passwd|api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret)\b\s*[\"']?\s*[:=]\s*)[^\r\n,}]+"
        ),
        r"\1[REDACTED]",
    ),
    (
        re.compile(
            r"\b(?:gh[pousr]_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[A-Z0-9]{16}|sk-[A-Za-z0-9_-]{20,})\b"
        ),
        "[REDACTED TOKEN]",
    ),
    (re.compile(r"\beyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"), "[REDACTED JWT]"),
    (re.compile(r"(https?://)[^\s/@:]+:[^\s/@]+@"), r"\1[REDACTED]@"),
]


def redact_private_key_line(line: bytes, inside_key: bool) -> tuple[bytes, bool]:
    redact_line = inside_key
    for marker in _KEY_LINE_MARKER.finditer(line):
        inside_key = marker[1] == b"BEGIN"
        redact_line |= inside_key
    if not redact_line:
        return line, False
    ending = b"\r\n" if line.endswith(b"\r\n") else b"\n" if line.endswith(b"\n") else b""
    return b"[REDACTED PRIVATE KEY]" + ending, inside_key


def redact(text: str) -> str:
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {k: redact_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_value(v) for v in value]
    return value
