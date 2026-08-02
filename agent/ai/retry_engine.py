from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Pattern


class FailureCategory(str, Enum):
    GENERATION = "generation"
    PARSING = "parsing"
    POLICY = "policy"
    COMPILATION = "compilation"
    VALIDATION = "validation"
    TESTING = "testing"
    PROVIDER = "provider"
    GIT = "git"
    UNKNOWN = "unknown"


class FinalStatus(str, Enum):
    SUCCEEDED = "succeeded"
    EXHAUSTED = "exhausted"
    BLOCKED = "blocked"
    FAILED = "failed"


_DEF_REDACTION_PATTERNS: List[Pattern[str]] = [
    # Authorization headers (Bearer tokens)
    re.compile(r"(authorization\s*:\s*bearer\s*)([A-Za-z0-9\._\-~+/=]+)", re.IGNORECASE),
    # Generic API key formats
    re.compile(r"(api[-_ ]?key\s*[:=]\s*)([^\s'\"]+)", re.IGNORECASE),
    re.compile(r"(x-api-key\s*:\s*)([A-Za-z0-9\-_]+)", re.IGNORECASE),
    # Tokens
    re.compile(r"(token\s*[:=]\s*)([^\s'\"]+)", re.IGNORECASE),
    # Passwords
    re.compile(r"(password\s*[:=]\s*)([^\s'\"]+)", re.IGNORECASE),
    # Secret keys
    re.compile(r"(secret[_-]?key\s*[:=]\s*)([^\s'\"]+)", re.IGNORECASE),
    # AWS Access Key ID
    re.compile(r"(AKIA[0-9A-Z]{16})"),
    # Private keys
    re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----",
        re.MULTILINE,
    ),
]


def _now_utc_iso() -> str:
    # Deterministic UTC timestamp in ISO8601 Zulu format
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class RetryConfiguration:
    max_attempts: int = 3
    safe_error_bytes: int = 2048
    redaction_patterns: List[Pattern[str]] = field(
        default_factory=lambda: list(_DEF_REDACTION_PATTERNS)
    )

    def __post_init__(self) -> None:  # type: ignore[override]
        if self.max_attempts <= 0:
            raise ValueError("max_attempts must be a positive integer")
        if self.safe_error_bytes <= 0:
            # Reject only zero or negative values
            raise ValueError("safe_error_bytes must be a positive integer")
        # Ensure patterns are compiled
        object.__setattr__(self, "redaction_patterns", [
            p if isinstance(p, re.Pattern) else re.compile(str(p)) for p in self.redaction_patterns
        ])


@dataclass
class FailureContext:
    category: FailureCategory
    summary: str
    details: Optional[str] = None
    test_failures: List[str] = field(default_factory=list)
    validation_failures: List[str] = field(default_factory=list)
    error_output: Optional[str] = None

    # Specific flags to determine blocking/handling
    policy_violation: bool = False
    unsafe_path_violation: bool = False
    secret_exposure: bool = False
    dirty_repo: bool = False
    git_integrity_error: bool = False

    provider_unavailable: bool = False
    provider_auth_error: bool = False
    provider_billing_error: bool = False

    invalid_ai_output: bool = False  # e.g., invalid JSON structure
    missing_deliverables: bool = False


@dataclass
class RetryDecision:
    retryable: bool
    reason: str
    instructions: Optional[str] = None
    blocked: bool = False


@dataclass
class RetryAttempt:
    number: int
    timestamp: str
    succeeded: bool
    category: Optional[FailureCategory] = None
    error_summary: Optional[str] = None
    test_failures: List[str] = field(default_factory=list)
    validation_failures: List[str] = field(default_factory=list)
    error_output_snippet: Optional[str] = None
    decision: Optional[RetryDecision] = None

    def to_dict(self) -> Dict[str, Any]:
        # Deterministic serialization order
        d: Dict[str, Any] = {
            "number": self.number,
            "timestamp": self.timestamp,
            "succeeded": self.succeeded,
            "category": self.category.value if self.category is not None else None,
            "error_summary": self.error_summary,
            "test_failures": list(self.test_failures),
            "validation_failures": list(self.validation_failures),
            "error_output_snippet": self.error_output_snippet,
            "retryable": self.decision.retryable if self.decision else None,
            "decision_reason": self.decision.reason if self.decision else None,
            "blocked": self.decision.blocked if self.decision else None,
            "instructions": self.decision.instructions if self.decision else None,
        }
        return d


@dataclass
class RetryReport:
    original_requirements: str
    configuration: RetryConfiguration
    attempts: List[RetryAttempt]
    status: FinalStatus

    @property
    def attempts_used(self) -> int:
        return len(self.attempts)

    @property
    def attempts_remaining(self) -> int:
        remain = self.configuration.max_attempts - self.attempts_used
        return remain if remain > 0 else 0

    @property
    def success(self) -> bool:
        return any(a.succeeded for a in self.attempts)

    def to_dict(self) -> Dict[str, Any]:
        # Deterministic serialization order
        d: Dict[str, Any] = {
            "mission_requirements": self.original_requirements,
            "max_attempts": self.configuration.max_attempts,
            "safe_error_bytes": self.configuration.safe_error_bytes,
            "attempts_used": self.attempts_used,
            "attempts_remaining": self.attempts_remaining,
            "status": self.status.value,
            "success": self.success,
            "attempts": [a.to_dict() for a in self.attempts],
        }
        return d


class RetryEngine:
    def __init__(self, configuration: RetryConfiguration, mission_requirements: str, logger: Optional[logging.Logger] = None) -> None:
        self.config = configuration
        self.mission_requirements = mission_requirements
        self.attempts: List[RetryAttempt] = []
        self._blocked: bool = False
        self._logger = logger or logging.getLogger("mitigate.retry_engine")
        if not self._logger.handlers:
            # Avoid duplicate handlers if provided externally
            self._logger.addHandler(logging.NullHandler())
        self._logger.debug("RetryEngine initialized with max_attempts=%s, safe_error_bytes=%s", self.config.max_attempts, self.config.safe_error_bytes)

    # Public behavior: evaluate a failure and determine whether it is retryable
    def evaluate_failure(self, failure: FailureContext) -> RetryDecision:
        self._logger.debug("Evaluating failure: %s", failure)
        # Immediate blocking conditions
        if failure.policy_violation or failure.unsafe_path_violation or failure.secret_exposure:
            return RetryDecision(
                retryable=False,
                reason="Security policy violation or secret exposure",
                blocked=True,
            )
        if failure.dirty_repo or failure.git_integrity_error or failure.category == FailureCategory.GIT:
            return RetryDecision(
                retryable=False,
                reason="Git repository integrity or dirty state",
                blocked=True,
            )
        if failure.provider_auth_error or failure.provider_billing_error or failure.provider_unavailable:
            return RetryDecision(
                retryable=False,
                reason="Provider authentication, billing, or availability failure",
                blocked=True,
            )

        # Retryable categories and scenarios
        if failure.category in (FailureCategory.COMPILATION, FailureCategory.VALIDATION, FailureCategory.TESTING, FailureCategory.PARSING):
            return RetryDecision(
                retryable=True,
                reason=f"{failure.category.value} failure is retryable",
            )
        if failure.invalid_ai_output or failure.missing_deliverables or failure.category == FailureCategory.GENERATION:
            return RetryDecision(
                retryable=True,
                reason="Deterministic generation issue (invalid output or missing deliverables)",
            )

        if failure.category in (FailureCategory.PROVIDER, FailureCategory.POLICY, FailureCategory.GIT):
            # Provider issues that are not auth/billing/unavailable default to not retryable
            return RetryDecision(
                retryable=False,
                reason=f"{failure.category.value} failure is not retryable",
            )

        # Unknown default: allow a cautious retry unless max attempts exhausted later
        return RetryDecision(
            retryable=True,
            reason="Unknown failure considered retryable by policy",
        )

    # Public behavior: record failed attempts
    def record_failure(self, failure: FailureContext) -> RetryDecision:
        number = len(self.attempts) + 1
        self._logger.debug("Recording failure for attempt #%d", number)
        decision = self.evaluate_failure(failure)

        # Enforce attempt limit strictly (never allow unlimited retries)
        remaining_after = self.config.max_attempts - number
        if decision.retryable and remaining_after <= 0:
            decision = RetryDecision(
                retryable=False,
                reason="Maximum retry attempts exhausted",
                blocked=False,
                instructions=None,
            )

        # Generate corrective instructions only if retryable
        instructions: Optional[str] = None
        if decision.retryable:
            instructions = self._build_corrective_instructions(failure)
            decision.instructions = instructions

        snippet = self._sanitize_error_output(failure.error_output or "") if failure.error_output else None

        attempt = RetryAttempt(
            number=number,
            timestamp=_now_utc_iso(),
            succeeded=False,
            category=failure.category,
            error_summary=failure.summary,
            test_failures=list(failure.test_failures),
            validation_failures=list(failure.validation_failures),
            error_output_snippet=snippet,
            decision=decision,
        )
        self.attempts.append(attempt)
        self._logger.debug("Attempt #%d recorded. Retryable=%s Blocked=%s Remaining after=%d", number, decision.retryable, decision.blocked, remaining_after)

        if decision.blocked:
            self._blocked = True
        return decision

    # Public behavior: record successful attempts
    def record_success(self, summary: str = "All requirements validated and tests passed.") -> None:
        number = len(self.attempts) + 1
        self._logger.debug("Recording success for attempt #%d", number)
        attempt = RetryAttempt(
            number=number,
            timestamp=_now_utc_iso(),
            succeeded=True,
            category=None,
            error_summary=summary,
        )
        self.attempts.append(attempt)

    # Public behavior: build and return final structured report
    def build_report(self) -> RetryReport:
        status = self._final_status()
        self._logger.debug("Building report with status=%s", status.value)
        return RetryReport(
            original_requirements=self.mission_requirements,
            configuration=self.config,
            attempts=list(self.attempts),
            status=status,
        )

    # Utility: number of attempts used/remaining
    @property
    def attempts_used(self) -> int:
        return len(self.attempts)

    @property
    def attempts_remaining(self) -> int:
        remain = self.config.max_attempts - self.attempts_used
        return remain if remain > 0 else 0

    # Internal helpers
    def _final_status(self) -> FinalStatus:
        if any(a.succeeded for a in self.attempts):
            return FinalStatus.SUCCEEDED
        if self._blocked:
            return FinalStatus.BLOCKED
        if self.attempts_used >= self.config.max_attempts:
            return FinalStatus.EXHAUSTED
        return FinalStatus.FAILED

    def _sanitize_error_output(self, text: str) -> str:
        # Redact secrets first
        redacted = self._redact(text)
        # Then truncate to safe byte size
        truncated = self._truncate_utf8(redacted, self.config.safe_error_bytes)
        self._logger.debug(
            "Sanitized error output from %d to %d bytes (limit=%d)",
            len(text.encode("utf-8")),
            len(truncated.encode("utf-8")),
            self.config.safe_error_bytes,
        )
        return truncated

    def _redact(self, text: str) -> str:
        redacted = text
        for pat in self.config.redaction_patterns:
            # For patterns with groups, retain prefix and redact the value group only if present
            def _sub(m: re.Match[str]) -> str:
                if m.lastindex and m.lastindex >= 2:
                    # Preserve group 1, redact group 2 and beyond
                    prefix = m.group(1)
                    return f"{prefix}[REDACTED]"
                # Otherwise redact the whole match
                return "[REDACTED]"

            redacted = pat.sub(_sub, redacted)
        return redacted

    @staticmethod
    def _truncate_utf8(text: str, max_bytes: int) -> str:
        data = text.encode("utf-8")
        if len(data) <= max_bytes:
            return text
        truncated = data[:max_bytes]
        # Remove potential incomplete trailing bytes to preserve valid UTF-8
        safe = truncated.decode("utf-8", errors="ignore")
        return safe

    def _build_corrective_instructions(self, failure: FailureContext) -> str:
        # Deterministic, minimal, and relevant corrective guidance
        lines: List[str] = []
        lines.append("Follow these corrective steps deterministically. Do not deviate.")
        lines.append("")
        lines.append("Mission Requirements (preserve exactly):")
        lines.append(self.mission_requirements.strip())
        lines.append("")
        lines.append(f"Failure Category: {failure.category.value}")
        lines.append(f"Error Summary: {failure.summary}")
        if failure.validation_failures:
            lines.append("Validation Failures:")
            for v in failure.validation_failures:
                lines.append(f"- {v}")
        if failure.test_failures:
            lines.append("Test Failures:")
            for t in failure.test_failures:
                lines.append(f"- {t}")
        if failure.error_output:
            sanitized = self._sanitize_error_output(failure.error_output)
            lines.append("Relevant Error Output (sanitized):")
            lines.append(sanitized)
        lines.append("")
        lines.extend(self._category_guidance(failure))
        # Deterministic join with newline
        return "\n".join(lines)

    @staticmethod
    def _category_guidance(failure: FailureContext) -> List[str]:
        cat = failure.category
        g: List[str] = ["Deterministic Remediation Steps:"]
        if cat == FailureCategory.COMPILATION:
            g.extend([
                "- Identify syntax and import errors deterministically.",
                "- Correct type hints and resolve missing symbols.",
                "- Ensure Python 3.12 compatibility without adding dependencies.",
            ])
        elif cat == FailureCategory.VALIDATION:
            g.extend([
                "- Address each validation failure directly and deterministically.",
                "- Keep behavior unchanged outside the failing areas.",
            ])
        elif cat == FailureCategory.TESTING:
            g.extend([
                "- Reproduce the failing tests deterministically.",
                "- Fix logic while maintaining public contracts.",
                "- Do not remove or skip tests.",
            ])
        elif cat == FailureCategory.PARSING:
            g.extend([
                "- Produce valid JSON with stable key ordering and required fields.",
                "- Avoid trailing commas and ensure correct data types.",
            ])
        elif cat == FailureCategory.GENERATION:
            g.extend([
                "- Provide all required deliverables.",
                "- Ensure correct file paths and English-only source and comments.",
            ])
        elif cat == FailureCategory.PROVIDER:
            g.extend([
                "- Provider issue detected; adjust prompt deterministically if applicable.",
                "- Do not include secrets or tokens in any output.",
            ])
        elif cat == FailureCategory.POLICY:
            g.extend([
                "- Policy violation detected. Do not proceed.",
            ])
        elif cat == FailureCategory.GIT:
            g.extend([
                "- Git integrity issue detected. Stop and request manual intervention.",
            ])
        else:
            g.extend([
                "- Analyze logs deterministically and correct minimal surface area.",
            ])
        g.append("- Re-run validation and unit tests. Declare success only if all pass.")
        return g


__all__ = [
    "RetryConfiguration",
    "FailureCategory",
    "FailureContext",
    "RetryAttempt",
    "RetryDecision",
    "RetryReport",
    "RetryEngine",
]
