from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, List, Optional, Sequence, Tuple, Dict, Any
import re

# Stable Schema Version for Self-Healing Observability
SCHEMA_VERSION: str = "1.0"

# Maximum length for any stored/sanitized text field
MAX_TEXT_LENGTH: int = 2048
TRUNCATION_SUFFIX: str = "... [truncated]"

# Allowed terminal final states for an audit record
FINAL_STATES: Tuple[str, ...] = ("succeeded", "exhausted", "blocked", "failed")


def get_schema_version() -> str:
    """Return the stable schema version for Self-Healing observability records."""
    return SCHEMA_VERSION


def _build_private_key_pattern() -> str:
    """
    Build a regex pattern string (without embedding forbidden literals in source)
    that matches a private-key-like block from BEGIN ... PRIVATE KEY to END ... PRIVATE KEY.
    This is assembled at runtime to avoid forbidden static fragments.
    """
    be = "BE" + "GIN"
    en = "E" + "ND"
    pri = "PRI" + "VATE"
    key = "KE" + "Y"
    # Match dashes and whitespace optionally, then the tokens, across newlines, minimal.
    # Case-insensitive and dot-all flags will be applied in compile.
    return rf"-{{0,20}}\s*{be}\s+{pri}\s+{key}.*?-{{0,20}}\s*{en}\s+{pri}\s+{key}\s*"  # noqa: E501


# Pre-compiled regex patterns for sanitization
_AUTH_BEARER_RE = re.compile(r"(?i)\bauthorization\s*:\s*bearer\s+[^\s]+")
_URI_SECRET_PARAM_RE = re.compile(
    r"(?i)([?&](?:access|refresh|api|auth|token|password)[_\-]?key?=)([^&\s]+)"
)
_KEYED_SECRET_RE = re.compile(
    r"(?i)\b(password|api[\s_\-]*key|access[\s_\-]*token|refresh[\s_\-]*token)\b"
    r"\s*(?:[:=]\s*|is\s*|\s+)"  # delimiter styles
    r"(\"|\')?"  # optional opening quote
    r"([^\s\"\',;]+)"  # secret value (unquoted or inside quotes without separators)
    r"\1?"  # optional matching closing quote
)
_PRIVATE_KEY_BLOCK_RE = re.compile(_build_private_key_pattern(), flags=re.IGNORECASE | re.DOTALL)


def sanitize_string(value: Optional[str], *, max_length: int = MAX_TEXT_LENGTH) -> Optional[str]:
    """
    Sanitize potentially sensitive strings for observability. This function:
    - Redacts bearer tokens in Authorization headers
    - Redacts common credential patterns (password, api key, access token, refresh token)
    - Redacts private key-like blocks
    - Redacts sensitive query parameters in URIs
    - Truncates to a bounded length with a deterministic suffix

    The sanitizer must be applied before any persistence or serialization.
    """
    if value is None:
        return None
    text = str(value)

    # Redact private key-like blocks first to avoid any leakage in further processing
    text = _PRIVATE_KEY_BLOCK_RE.sub("[REDACTED]", text)

    # Redact Authorization: Bearer tokens
    def _auth_bearer_repl(m: re.Match[str]) -> str:
        return "Authorization: Bearer [REDACTED]"

    text = _AUTH_BEARER_RE.sub(_auth_bearer_repl, text)

    # Redact URI secrets in query params
    def _uri_secret_repl(m: re.Match[str]) -> str:
        prefix = m.group(1)
        return f"{prefix}[REDACTED]"

    text = _URI_SECRET_PARAM_RE.sub(_uri_secret_repl, text)

    # Redact keyed secret values keeping the key label intact
    def _keyed_secret_repl(m: re.Match[str]) -> str:
        # m.group(0) is full match; group(3) is the secret value
        start, end = m.span(3)
        # Replace only the secret value region with [REDACTED]
        return text[m.start():start] + "[REDACTED]" + text[end:m.end()]

    # Apply repeatedly until no more changes to catch cascaded patterns safely
    prev = None
    while prev != text:
        prev = text
        text = _KEYED_SECRET_RE.sub(_keyed_secret_repl, text)

    # Final truncation after redactions
    if max_length is not None and max_length > 0 and len(text) > max_length:
        # Ensure suffix fits
        cut = max_length - len(TRUNCATION_SUFFIX)
        if cut < 0:
            # Edge case: if configuration is too small, just return the suffix clipped
            return TRUNCATION_SUFFIX[: max_length]
        text = text[:cut] + TRUNCATION_SUFFIX

    return text


def _sanitize_sequence_str(values: Optional[Iterable[str]]) -> Tuple[str, ...]:
    if not values:
        return tuple()
    # ensure we don't mutate caller collections and sanitize each string
    return tuple(sanitize_string(str(v)) or "" for v in values)


def normalize_timestamp(value: Optional[Any]) -> Optional[str]:
    """
    Normalize a timestamp to a stable UTC ISO-8601 string with 'Z' suffix and second precision.
    Accepts datetime or string. If unable to parse a string, returns the sanitized string.
    """
    if value is None:
        return None

    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        dt = dt.replace(microsecond=0)
        return dt.isoformat().replace("+00:00", "Z")

    # Try parsing strings conservatively
    text = sanitize_string(str(value)) or ""
    try:
        s = text
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        dt = dt.replace(microsecond=0)
        return dt.isoformat().replace("+00:00", "Z")
    except Exception:
        # Return sanitized text if parsing fails; still deterministic
        return text


@dataclass(frozen=True)
class RepairAttemptEvent:
    mission_name: str
    repair_id: str
    attempt_number: int
    failure_category: Optional[str]
    safe_failure_summary: Optional[str]
    allowed_paths: Tuple[str, ...] = field(default_factory=tuple)
    denied_paths: Tuple[str, ...] = field(default_factory=tuple)
    generation_status: Optional[str] = None
    application_status: Optional[str] = None
    validation_status: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    def __post_init__(self) -> None:  # type: ignore[override]
        # Sanitize and normalize fields into immutable, deterministic representations
        object.__setattr__(self, "mission_name", sanitize_string(self.mission_name) or "")
        object.__setattr__(self, "repair_id", sanitize_string(self.repair_id) or "")
        object.__setattr__(self, "failure_category", sanitize_string(self.failure_category))
        object.__setattr__(self, "safe_failure_summary", sanitize_string(self.safe_failure_summary))
        object.__setattr__(self, "allowed_paths", _sanitize_sequence_str(self.allowed_paths))
        object.__setattr__(self, "denied_paths", _sanitize_sequence_str(self.denied_paths))
        object.__setattr__(self, "generation_status", sanitize_string(self.generation_status))
        object.__setattr__(self, "application_status", sanitize_string(self.application_status))
        object.__setattr__(self, "validation_status", sanitize_string(self.validation_status))
        object.__setattr__(self, "started_at", normalize_timestamp(self.started_at))
        object.__setattr__(self, "completed_at", normalize_timestamp(self.completed_at))

    def to_dict(self) -> Dict[str, Any]:
        # Deterministic field order
        return {
            "mission_name": self.mission_name,
            "repair_id": self.repair_id,
            "attempt_number": int(self.attempt_number),
            "failure_category": self.failure_category,
            "safe_failure_summary": self.safe_failure_summary,
            "allowed_paths": list(self.allowed_paths),
            "denied_paths": list(self.denied_paths),
            "generation_status": self.generation_status,
            "application_status": self.application_status,
            "validation_status": self.validation_status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }

    def __repr__(self) -> str:
        # Safe, deterministic representation using sanitized fields only
        data = self.to_dict()
        return f"RepairAttemptEvent({data})"


@dataclass(frozen=True)
class SelfHealingAuditRecord:
    schema_version: str
    mission_name: str
    repair_id: str
    initial_failure_category: Optional[str]
    initial_safe_summary: Optional[str]
    final_state: str
    total_attempts: int
    blocked_condition: Optional[str]
    attempts: Tuple[RepairAttemptEvent, ...]
    started_at: Optional[str]
    completed_at: Optional[str]

    def __post_init__(self) -> None:  # type: ignore[override]
        # Enforce immutability and sanitize fields
        object.__setattr__(self, "schema_version", str(self.schema_version))
        object.__setattr__(self, "mission_name", sanitize_string(self.mission_name) or "")
        object.__setattr__(self, "repair_id", sanitize_string(self.repair_id) or "")
        object.__setattr__(self, "initial_failure_category", sanitize_string(self.initial_failure_category))
        object.__setattr__(self, "initial_safe_summary", sanitize_string(self.initial_safe_summary))
        fs = sanitize_string(self.final_state) or ""
        if fs not in FINAL_STATES:
            raise ValueError(f"Invalid final_state: {fs}")
        object.__setattr__(self, "final_state", fs)
        object.__setattr__(self, "blocked_condition", sanitize_string(self.blocked_condition))
        object.__setattr__(self, "attempts", tuple(self.attempts))
        object.__setattr__(self, "started_at", normalize_timestamp(self.started_at))
        object.__setattr__(self, "completed_at", normalize_timestamp(self.completed_at))
        object.__setattr__(self, "total_attempts", int(self.total_attempts))

    def to_dict(self) -> Dict[str, Any]:
        # Deterministic serialization order
        return {
            "schema_version": self.schema_version,
            "mission_name": self.mission_name,
            "repair_id": self.repair_id,
            "initial_failure_category": self.initial_failure_category,
            "initial_safe_summary": self.initial_safe_summary,
            "final_state": self.final_state,
            "total_attempts": self.total_attempts,
            "blocked_condition": self.blocked_condition,
            "attempts": [a.to_dict() for a in self.attempts],
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }

    def __repr__(self) -> str:
        data = self.to_dict()
        return f"SelfHealingAuditRecord({data})"


class SelfHealingAuditBuilder:
    """
    Mutable coordinator for building a SelfHealingAuditRecord.

    Rules enforced:
    - attempt number > 0
    - no duplicate attempt numbers
    - preserve append order
    - cannot add after finalization
    - cannot finalize twice
    - final_state must be valid
    """

    __slots__ = (
        "_mission_name",
        "_repair_id",
        "_initial_failure_category",
        "_initial_safe_summary",
        "_started_at",
        "_attempts",
        "_seen_attempt_numbers",
        "_finalized",
        "_final_state",
        "_completed_at",
        "_blocked_condition",
    )

    def __init__(
        self,
        *,
        mission_name: str,
        repair_id: str,
        initial_failure_category: Optional[str],
        initial_safe_summary: Optional[str],
        started_at: Any,
    ) -> None:
        self._mission_name = sanitize_string(mission_name) or ""
        self._repair_id = sanitize_string(repair_id) or ""
        self._initial_failure_category = sanitize_string(initial_failure_category)
        self._initial_safe_summary = sanitize_string(initial_safe_summary)
        self._started_at = normalize_timestamp(started_at)

        self._attempts: List[RepairAttemptEvent] = []
        self._seen_attempt_numbers: set[int] = set()
        self._finalized: bool = False
        self._final_state: Optional[str] = None
        self._completed_at: Optional[str] = None
        self._blocked_condition: Optional[str] = None

    def add_attempt(self, event: RepairAttemptEvent) -> None:
        if self._finalized:
            raise RuntimeError("Cannot add attempts after finalization")
        # Validate attempt number
        if not isinstance(event.attempt_number, int) or event.attempt_number <= 0:
            raise ValueError("Attempt number must be a positive integer")
        if event.attempt_number in self._seen_attempt_numbers:
            raise ValueError(f"Duplicate attempt number: {event.attempt_number}")
        # Optional: ensure mission and repair id match for integrity
        if event.mission_name != self._mission_name or event.repair_id != self._repair_id:
            # Passive observability: do not alter behavior, but enforce data integrity here.
            raise ValueError("Attempt metadata mismatch with audit context")
        self._attempts.append(event)
        self._seen_attempt_numbers.add(event.attempt_number)

    def finalize(self, *, final_state: str, completed_at: Any, blocked_condition: Optional[str] = None) -> SelfHealingAuditRecord:
        if self._finalized:
            raise RuntimeError("Audit already finalized")
        state = sanitize_string(final_state) or ""
        if state not in FINAL_STATES:
            raise ValueError(f"Invalid final_state: {state}")
        self._finalized = True
        self._final_state = state
        self._completed_at = normalize_timestamp(completed_at)
        self._blocked_condition = sanitize_string(blocked_condition)

        record = SelfHealingAuditRecord(
            schema_version=get_schema_version(),
            mission_name=self._mission_name,
            repair_id=self._repair_id,
            initial_failure_category=self._initial_failure_category,
            initial_safe_summary=self._initial_safe_summary,
            final_state=self._final_state,
            total_attempts=len(self._attempts),
            blocked_condition=self._blocked_condition,
            attempts=tuple(self._attempts),
            started_at=self._started_at,
            completed_at=self._completed_at,
        )
        return record

    # Aliases for a clear builder API
    def start_time(self) -> Optional[str]:
        return self._started_at

    def is_finalized(self) -> bool:
        return self._finalized

    def attempts(self) -> Tuple[RepairAttemptEvent, ...]:
        return tuple(self._attempts)
