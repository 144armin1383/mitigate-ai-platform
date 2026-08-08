from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, List, Mapping, Optional, Sequence, Tuple, Union, Dict
import re

# Note: This coordinator is deterministic, side-effect-free, and uses only standard library.
# It accepts injected validation and repair callbacks and does not perform any I/O, subprocess,
# network, Git, or filesystem mutation. All side effects must be performed via the injected callables.


# Blocking categories for immediate termination prior to any repair execution.
BLOCKED_CATEGORIES: Tuple[str, ...] = (
    "protected-core-access",
    "canonical-recovery-test-access",
    "unavailable-core-protection",
    "repository-safety-bypass",
    "security-policy-bypass",
    "provider-authentication-intervention",
)


def _to_immutable_sequence(values: Optional[Sequence[str]]) -> Tuple[str, ...]:
    if not values:
        return tuple()
    # Return a new tuple to avoid mutating original sequences
    return tuple(values)


def _immutable_constraints(constraints: Optional[Mapping[str, Any]]) -> Tuple[Tuple[str, Any], ...]:
    if not constraints:
        return tuple()
    # Create deterministic, immutable representation sorted by key.
    # Do not deeply copy values (side-effect free, but store as-is for determinism of equality given same inputs).
    items = list(constraints.items())
    items.sort(key=lambda kv: str(kv[0]))
    return tuple((k, v) for k, v in items)


_SECRET_KEYWORDS = (
    "password",
    "token",
    "secret",
    "api_key",
    "apikey",
    "authorization",
    "bearer",
)


def _sanitize_text(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    # Redact common secret patterns: key=value or key: value
    sanitized = text
    # Build a regex that finds key[\s]*[:=][^\r\n]* for each key, case-insensitive
    for key in _SECRET_KEYWORDS:
        pattern = re.compile(rf"(?i)({re.escape(key)})\s*[:=]\s*([^\r\n]+)")
        sanitized = pattern.sub(lambda m: f"{m.group(1)}=<redacted>", sanitized)
    # Also redact any token-like long base64/hex segments following 'Bearer' or 'Token'
    sanitized = re.sub(r"(?i)\b(Bearer|Token)\s+[A-Za-z0-9._\-+/=]{6,}\b", r"\1 <redacted>", sanitized)
    return sanitized


@dataclass(frozen=True)
class ValidationResult:
    success: bool
    category: Optional[str] = None
    summary: str = ""
    diagnostic: Optional[str] = None
    return_code: Optional[int] = None
    source: Optional[str] = None
    # blocking_condition can be a string code matching BLOCKED_CATEGORIES or a truthy value for generic block
    blocking_condition: Optional[Union[str, bool]] = None

    def sanitized(self) -> "ValidationResult":
        return ValidationResult(
            success=self.success,
            category=self.category,
            summary=_sanitize_text(self.summary) or "",
            diagnostic=_sanitize_text(self.diagnostic),
            return_code=self.return_code,
            source=self.source,
            blocking_condition=self.blocking_condition,
        )


@dataclass(frozen=True)
class RepairExecutionResult:
    success: bool
    summary: str = ""


@dataclass(frozen=True)
class FailureRecord:
    category: Optional[str]
    summary: str
    diagnostic: Optional[str]
    return_code: Optional[int]
    source: Optional[str]
    blocking_condition: Optional[Union[str, bool]]


@dataclass(frozen=True)
class RepairPlan:
    objective: str
    constraints: Tuple[Tuple[str, Any], ...]
    allowed_paths: Tuple[str, ...]
    denied_paths: Tuple[str, ...]
    attempt_number: int  # 1-based repair attempt counter
    failure_category: Optional[str]
    failure_summary: str


@dataclass(frozen=True)
class IntegrationResult:
    success: bool
    final_state: str  # 'succeeded' | 'blocked' | 'exhausted'
    attempts: int  # number of repair attempts executed
    repair_plans: Tuple[RepairPlan, ...]
    failure_history: Tuple[FailureRecord, ...]
    safe_summary: str


def _is_blocked_condition(v: ValidationResult) -> bool:
    # If blocking_condition provided as str and known, or truthy bool, or category is in blocked categories
    if isinstance(v.blocking_condition, str) and v.blocking_condition in BLOCKED_CATEGORIES:
        return True
    if isinstance(v.blocking_condition, bool) and v.blocking_condition:
        return True
    if v.category in BLOCKED_CATEGORIES:
        return True
    return False


def _coerce_validation_result(value: Any) -> ValidationResult:
    # Accept bool, ValidationResult, or dict-like structures
    if isinstance(value, ValidationResult):
        return value.sanitized()
    if isinstance(value, bool):
        return ValidationResult(success=value, summary="validation returned boolean").sanitized()
    if isinstance(value, Mapping):
        # Extract safely known fields
        vr = ValidationResult(
            success=bool(value.get("success", False)),
            category=value.get("category"),
            summary=str(value.get("summary", "")),
            diagnostic=str(value.get("diagnostic")) if value.get("diagnostic") is not None else None,
            return_code=int(value.get("return_code")) if value.get("return_code") is not None else None,
            source=str(value.get("source")) if value.get("source") is not None else None,
            blocking_condition=value.get("blocking_condition"),
        )
        return vr.sanitized()
    # Fallback: treat as failure, store a minimal summary
    return ValidationResult(success=False, summary="validation returned unsupported type").sanitized()


def _coerce_repair_result(value: Any) -> RepairExecutionResult:
    if isinstance(value, RepairExecutionResult):
        return value
    if isinstance(value, bool):
        return RepairExecutionResult(success=value, summary="repair returned boolean")
    if isinstance(value, Mapping):
        return RepairExecutionResult(success=bool(value.get("success", False)), summary=str(value.get("summary", "")))
    # Unsupported - treat as failure
    return RepairExecutionResult(success=False, summary="repair returned unsupported type")


class IntegrationCoordinator:
    def __init__(self, max_attempts: int = 3) -> None:
        # Enforce ceiling: no more than 3 repair attempts
        self._max_attempts = int(max(0, min(max_attempts, 3)))

    @property
    def max_attempts(self) -> int:
        return self._max_attempts

    def run(
        self,
        objective: str,
        *,
        allowed_paths: Optional[Sequence[str]] = None,
        denied_paths: Optional[Sequence[str]] = None,
        constraints: Optional[Mapping[str, Any]] = None,
        validate_callback: Optional[Callable[[], Any]] = None,
        repair_callback: Optional[Callable[[RepairPlan], Any]] = None,
        source: Optional[str] = None,
    ) -> IntegrationResult:
        if validate_callback is None:
            raise ValueError("validate_callback is required")
        if repair_callback is None:
            # We accept a dummy repair callback that is never called if validation succeeds initially.
            # However, to avoid surprises, enforce presence.
            raise ValueError("repair_callback is required")

        immutable_allowed = _to_immutable_sequence(allowed_paths)
        immutable_denied = _to_immutable_sequence(denied_paths)
        immutable_constraints = _immutable_constraints(constraints)

        repair_plans: List[RepairPlan] = []
        failures: List[FailureRecord] = []
        attempts = 0  # count repair attempts only

        def call_validate_safely() -> ValidationResult:
            try:
                value = validate_callback()
                return _coerce_validation_result(value)
            except Exception as exc:  # Do not catch BaseException
                # Convert to safe failure result
                msg = _sanitize_text(str(exc)) or "validation exception"
                return ValidationResult(
                    success=False,
                    category="validation-exception",
                    summary="validation raised exception",
                    diagnostic=msg,
                    source=source,
                ).sanitized()

        # Initial validation
        vres = call_validate_safely()
        if vres.success:
            return IntegrationResult(
                success=True,
                final_state="succeeded",
                attempts=attempts,
                repair_plans=tuple(repair_plans),
                failure_history=tuple(failures),
                safe_summary="initial validation succeeded",
            )

        # Record initial failure
        first_failure = FailureRecord(
            category=vres.category,
            summary=vres.summary,
            diagnostic=vres.diagnostic,
            return_code=vres.return_code,
            source=vres.source or source,
            blocking_condition=vres.blocking_condition,
        )
        failures.append(first_failure)

        # Blocked? stop before repair
        if _is_blocked_condition(vres):
            return IntegrationResult(
                success=False,
                final_state="blocked",
                attempts=attempts,
                repair_plans=tuple(repair_plans),
                failure_history=tuple(failures),
                safe_summary="blocked by policy or protection",
            )

        # Attempt bounded repairs
        for attempt in range(1, self._max_attempts + 1):
            plan = RepairPlan(
                objective=objective,
                constraints=immutable_constraints,
                allowed_paths=immutable_allowed,
                denied_paths=immutable_denied,
                attempt_number=attempt,
                failure_category=vres.category,
                failure_summary=vres.summary,
            )
            repair_plans.append(plan)
            attempts += 1

            # Execute repair safely
            rres: RepairExecutionResult
            try:
                rres = _coerce_repair_result(repair_callback(plan))
            except Exception as exc:  # Do not catch BaseException
                rres = RepairExecutionResult(success=False, summary=f"repair raised exception: {_sanitize_text(str(exc)) or ''}")
                # Record as a failure event as well for traceability (using FailureRecord structure)
                failures.append(
                    FailureRecord(
                        category="repair-execution-exception",
                        summary="repair callback raised exception",
                        diagnostic=_sanitize_text(str(exc)),
                        return_code=None,
                        source=source,
                        blocking_condition=None,
                    )
                )

            if not rres.success:
                # Record repair failure as a failure record for history
                failures.append(
                    FailureRecord(
                        category="repair-execution-failure",
                        summary=rres.summary or "repair execution reported failure",
                        diagnostic=None,
                        return_code=None,
                        source=source,
                        blocking_condition=None,
                    )
                )

            # Re-validate after repair attempt
            vres = call_validate_safely()
            if vres.success:
                return IntegrationResult(
                    success=True,
                    final_state="succeeded",
                    attempts=attempts,
                    repair_plans=tuple(repair_plans),
                    failure_history=tuple(failures),
                    safe_summary=f"succeeded after {attempts} repair attempt(s)",
                )

            # Record validation failure after attempt
            failures.append(
                FailureRecord(
                    category=vres.category,
                    summary=vres.summary,
                    diagnostic=vres.diagnostic,
                    return_code=vres.return_code,
                    source=vres.source or source,
                    blocking_condition=vres.blocking_condition,
                )
            )

            if _is_blocked_condition(vres):
                return IntegrationResult(
                    success=False,
                    final_state="blocked",
                    attempts=attempts,
                    repair_plans=tuple(repair_plans),
                    failure_history=tuple(failures),
                    safe_summary="blocked by policy or protection",
                )

        # Exhausted attempts
        return IntegrationResult(
            success=False,
            final_state="exhausted",
            attempts=attempts,
            repair_plans=tuple(repair_plans),
            failure_history=tuple(failures),
            safe_summary=f"exhausted {attempts} repair attempt(s) without success",
        )


__all__ = [
    "ValidationResult",
    "RepairExecutionResult",
    "FailureRecord",
    "RepairPlan",
    "IntegrationResult",
    "IntegrationCoordinator",
    "BLOCKED_CATEGORIES",
]
