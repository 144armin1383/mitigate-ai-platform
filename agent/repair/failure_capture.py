from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Optional

# One explicit maximum diagnostic length
MAX_DIAGNOSTIC_LENGTH: int = 2048
_TRUNCATION_SUFFIX = "... [truncated]"

# Precompile regex patterns used during sanitization
# Bearer-specific rule (must run first and take precedence over generic rules)
# Matches Authorization headers using the Bearer scheme (case-insensitive), anywhere in text, to end-of-line
_BEARER_HEADER_RE = re.compile(r"(?i)\bauthorization\s*:\s*bearer\s+[^\r\n]+")

# Generic credential-like patterns (run after Bearer-specific rule). These are intentionally broad but
# avoid altering canonical Bearer redacted strings.
_GENERIC_KV_RE = re.compile(
    r"(?i)\b(password|passwd|pwd|token|secret|api[_-]?key)\s*([:=])\s*(?:[^\s\r\n\"']+|\"[^\"\r\n]*\"|'[^'\r\n]*')"
)


def _redact_bearer(text: str) -> str:
    # Replace any Authorization: Bearer <credential> with the canonical sanitized form
    # Output must be exactly: Authorization: Bearer [REDACTED]
    def repl(_: re.Match) -> str:
        return "Authorization: Bearer [REDACTED]"

    # Apply repeatedly until no further change to handle multiple occurrences robustly
    prev = None
    cur = text
    while prev != cur:
        prev = cur
        cur = _BEARER_HEADER_RE.sub(repl, cur)
    return cur


def _redact_generic(text: str) -> str:
    def repl(m: re.Match) -> str:
        full = m.group(0)
        # Do not disturb already-sanitized Bearer outputs
        if "Bearer [REDACTED]" in full:
            return full
        key = m.group(1)
        sep = m.group(2)
        # Preserve original key casing and separator, replace only the value
        return f"{key}{sep} [REDACTED]"

    return _GENERIC_KV_RE.sub(repl, text)


def _truncate(text: str, limit: int) -> str:
    if limit <= 0:
        # Defensive: never allow non-positive; but contract expects positive constant
        return _TRUNCATION_SUFFIX
    if len(text) <= limit:
        return text
    # Ensure the final result is within the maximum and ends exactly with suffix (no trailing whitespace)
    keep = max(0, limit - len(_TRUNCATION_SUFFIX))
    result = text[:keep] + _TRUNCATION_SUFFIX
    # Guarantee no trailing newline or whitespace after suffix
    return result.rstrip() if result.endswith(_TRUNCATION_SUFFIX) else result


def sanitize_diagnostic(diagnostic: Optional[str], max_length: int = MAX_DIAGNOSTIC_LENGTH) -> str:
    """Sanitize and bound diagnostic text.

    Steps:
    1. Apply Bearer-specific redaction first, producing canonical 'Authorization: Bearer [REDACTED]'.
    2. Apply generic redaction rules for obvious credential-like values.
    3. Enforce a maximum length with an exact truncation suffix when truncation occurs.
    """
    if diagnostic is None:
        diagnostic = ""
    # Normalize to string
    text = str(diagnostic)

    # 1) Bearer-specific redaction with precedence
    text = _redact_bearer(text)

    # 2) Generic redaction
    text = _redact_generic(text)

    # 3) Enforce diagnostic maximum length and suffix
    text = _truncate(text, max_length)

    return text


@dataclass(frozen=True)
class FailureRecord:
    """Immutable structured failure record for self-healing repair.

    Categories supported:
    - compilation_failure
    - unittest_failure
    - validation_failure
    - generated_file_failure
    - unknown_failure
    """

    category: str
    safe_summary: str
    return_code: Optional[int]
    attempt_number: int
    retryable: bool
    source: str
    diagnostic: str

    def __init__(
        self,
        category: str,
        safe_summary: str,
        return_code: Optional[int],
        attempt_number: int,
        retryable: bool,
        source: str,
        diagnostic: Optional[str],
    ) -> None:
        # Validate category
        allowed = {
            "compilation_failure",
            "unittest_failure",
            "validation_failure",
            "generated_file_failure",
            "unknown_failure",
        }
        if category not in allowed:
            raise ValueError(f"Unsupported failure category: {category}")
        if attempt_number <= 0:
            raise ValueError("attempt_number must be positive")
        # Sanitize diagnostic
        sanitized = sanitize_diagnostic(diagnostic)
        # Bypass frozen enforcement during initialization
        object.__setattr__(self, "category", category)
        object.__setattr__(self, "safe_summary", str(safe_summary))
        object.__setattr__(self, "return_code", return_code)
        object.__setattr__(self, "attempt_number", int(attempt_number))
        object.__setattr__(self, "retryable", bool(retryable))
        object.__setattr__(self, "source", str(source))
        object.__setattr__(self, "diagnostic", sanitized)
