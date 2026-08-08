from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple
import copy
import re

from .integration import (
    IntegrationCoordinator,
    RepairExecutionResult,
    ValidationResult,
)


@dataclass(frozen=True)
class RepairRequest:
    """
    Immutable and safe request passed to the repair generation callback.

    Notes
    - allowed_paths and denied_paths are tuples to guarantee immutability.
    - failure_summary and objective are redacted prior to construction to
      avoid leaking raw unsanitized diagnostics.
    """
    mission_name: str
    attempt_number: int
    objective: str
    failure_category: str
    failure_summary: str
    allowed_paths: Tuple[str, ...]
    denied_paths: Tuple[str, ...]
    validation_required: bool


class MissionRepairAdapter:
    """
    Orchestrates validation, repair generation, and repair application with
    strict safety, determinism, and bounded attempts.

    All side effects are injected via callbacks. This adapter does not perform
    any process execution, network calls, Git operations, deployment, or file
    system mutation.
    """

    # Exactly three bounded attempts
    MAX_ATTEMPTS: int = 3

    # Policy block reasons that prevent generation/apply
    _POLICY_BLOCKS: Tuple[str, ...] = (
        "protected-core-access",
        "canonical-recovery-test-access",
        "unavailable-core-protection",
        "repository-safety-bypass",
        "security-policy-bypass",
        "provider-authentication-intervention",
    )

    def __init__(
        self,
        integration_coordinator: Optional[Any] = None,
        validate_callback: Optional[Callable[[], Any]] = None,
        generate_callback: Optional[Callable[[RepairRequest], Any]] = None,
        apply_callback: Optional[Callable[[Any], Any]] = None,
    ) -> None:
        self._integration_coordinator = integration_coordinator
        self._validate_callback = validate_callback
        self._generate_callback = generate_callback
        self._apply_callback = apply_callback

    # --------------------------- Public API ---------------------------

    def run(
        self,
        *,
        mission_name: str,
        objective: str,
        failure_category: str,
        failure_summary: str,
        allowed_paths: Sequence[str],
        denied_paths: Sequence[str],
        validation_required: bool = True,
        policy_blocks: Optional[Iterable[str]] = None,
    ) -> Dict[str, Any]:
        """
        Execute the mission repair lifecycle through IntegrationCoordinator.

        IntegrationCoordinator is the single authority for:
        validation, bounded attempts, retry progression, revalidation,
        blocked state, succeeded state, and exhausted state.

        This method preserves the existing MissionRepairAdapter public result
        contract while delegating lifecycle control to the coordinator.
        """
        original_allowed = list(allowed_paths)
        original_denied = list(denied_paths)

        allowed_tuple = tuple(original_allowed)
        denied_tuple = tuple(original_denied)

        blocked_reasons = [
            item
            for item in self._POLICY_BLOCKS
            if item in {str(v) for v in (policy_blocks or ())}
        ]

        result: Dict[str, Any] = {
            "status": "",
            "attempts": 0,
            "initial_validation": {
                "success": None,
                "error": None,
            },
            "history": [],
            "failures": [],
            "blocked_reasons": [],
        }

        validation_count = 0

        def coordinator_validate() -> ValidationResult:
            nonlocal validation_count

            success, error = self._call_validation()
            validation_count += 1

            safe_error = self._redact_text(error) if error else None

            if validation_count == 1:
                result["initial_validation"] = {
                    "success": success,
                    "error": safe_error,
                }
            elif result["history"]:
                result["history"][-1]["validation"] = {
                    "success": success,
                    "error": safe_error,
                }

            if error is not None:
                result["failures"].append(
                    {
                        "stage": "validation",
                        "attempt": max(0, validation_count - 1),
                        "message": safe_error,
                    }
                )

            if success is True:
                return ValidationResult(
                    success=True,
                    category=None,
                    summary="validation succeeded",
                    diagnostic=None,
                    source=mission_name,
                )

            if blocked_reasons:
                reason = blocked_reasons[0]
                return ValidationResult(
                    success=False,
                    category=reason,
                    summary="blocked by policy or protection",
                    diagnostic=None,
                    source=mission_name,
                    blocking_condition=reason,
                )

            if validation_required is False and success is not False:
                return ValidationResult(
                    success=True,
                    category=None,
                    summary="validation not required",
                    diagnostic=None,
                    source=mission_name,
                )

            return ValidationResult(
                success=False,
                category=failure_category or "validation-failure",
                summary=self._redact_text(failure_summary),
                diagnostic=safe_error,
                source=mission_name,
            )

        def coordinator_repair(plan: Any) -> RepairExecutionResult:
            request = RepairRequest(
                mission_name=mission_name,
                attempt_number=int(plan.attempt_number),
                objective=self._redact_text(objective),
                failure_category=(
                    str(plan.failure_category)
                    if plan.failure_category is not None
                    else failure_category
                ),
                failure_summary=self._redact_text(
                    plan.failure_summary or failure_summary
                ),
                allowed_paths=allowed_tuple,
                denied_paths=denied_tuple,
                validation_required=validation_required,
            )

            gen_success, gen_payload, gen_error = self._call_generate(request)

            attempt_record: Dict[str, Any] = {
                "attempt": int(plan.attempt_number),
                "generation": {
                    "success": gen_success,
                    "error": (
                        self._redact_text(gen_error)
                        if gen_error
                        else None
                    ),
                },
                "apply": {
                    "success": None,
                    "error": None,
                },
                "validation": {
                    "success": None,
                    "error": None,
                },
            }

            result["history"].append(attempt_record)

            if gen_error is not None:
                result["failures"].append(
                    {
                        "stage": "generation",
                        "attempt": int(plan.attempt_number),
                        "message": self._redact_text(gen_error),
                    }
                )

            if not gen_success:
                return RepairExecutionResult(
                    success=False,
                    summary="Repair generation failed",
                )

            apply_success, apply_error = self._call_apply(gen_payload)

            attempt_record["apply"] = {
                "success": apply_success,
                "error": (
                    self._redact_text(apply_error)
                    if apply_error
                    else None
                ),
            }

            if apply_error is not None:
                result["failures"].append(
                    {
                        "stage": "apply",
                        "attempt": int(plan.attempt_number),
                        "message": self._redact_text(apply_error),
                    }
                )

            if not apply_success:
                return RepairExecutionResult(
                    success=False,
                    summary="Repair application failed",
                )

            return RepairExecutionResult(
                success=True,
                summary="repair generated and applied",
            )

        coordinator = IntegrationCoordinator(
            max_attempts=self.MAX_ATTEMPTS
        )

        integration_result = coordinator.run(
            objective=self._redact_text(objective),
            allowed_paths=allowed_tuple,
            denied_paths=denied_tuple,
            constraints={
                "mission_name": mission_name,
                "validation_required": validation_required,
            },
            validate_callback=coordinator_validate,
            repair_callback=coordinator_repair,
            source=mission_name,
        )

        result["status"] = integration_result.final_state
        result["attempts"] = integration_result.attempts

        if integration_result.final_state == "blocked":
            reason = None

            for failure in reversed(
                integration_result.failure_history
            ):
                if (
                    isinstance(failure.blocking_condition, str)
                    and failure.blocking_condition
                ):
                    reason = failure.blocking_condition
                    break

                if failure.category in self._POLICY_BLOCKS:
                    reason = failure.category
                    break

            if reason is not None:
                result["blocked_reasons"] = [reason]
            else:
                result["blocked_reasons"] = list(blocked_reasons)

        return self._freeze_result(result)

    # --------------------------- Internal helpers ---------------------------

    def _call_validation(self) -> Tuple[Optional[bool], Optional[str]]:
        """
        Safely invoke validation callback.
        Returns (success, error_message). Exceptions are converted to failure events.
        """
        if self._validate_callback is None:
            # If no validator provided, treat as unknown (not failure)
            return None, None
        try:
            outcome = self._validate_callback()
            success, _ = self._normalize_outcome(outcome)
            return success, None
        except Exception as exc:  # Do not catch BaseException
            return False, f"Validation error: {self._stringify_exception(exc)}"

    def _call_generate(self, request: RepairRequest) -> Tuple[bool, Any, Optional[str]]:
        """
        Safely invoke generation callback. Returns (success, payload, error_message).
        """
        if self._generate_callback is None:
            return False, None, "Generation callback unavailable"
        try:
            outcome = self._generate_callback(request)
            success, payload = self._normalize_outcome(outcome)
            if success:
                return True, payload, None
            return False, None, "Repair generation failed"
        except Exception as exc:  # Do not catch BaseException
            return False, None, f"Generation exception: {self._stringify_exception(exc)}"

    def _call_apply(self, payload: Any) -> Tuple[bool, Optional[str]]:
        """
        Safely invoke apply callback. Returns (success, error_message).
        """
        if self._apply_callback is None:
            return False, "Apply callback unavailable"
        try:
            outcome = self._apply_callback(payload)
            success, _ = self._normalize_outcome(outcome)
            if success:
                return True, None
            return False, "Repair application failed"
        except Exception as exc:  # Do not catch BaseException
            return False, f"Apply exception: {self._stringify_exception(exc)}"

    @staticmethod
    def _normalize_outcome(outcome: Any) -> Tuple[bool, Any]:
        """
        Normalize callback outcomes into a (success, payload) tuple.
        Rules:
        - If dict with 'success' key: use its boolean value and return the dict as payload
        - If strictly True/False: success is that value; payload is outcome
        - If None or falsy (not False) like empty: treat as failure
        - Otherwise: treat as success with payload=outcome
        """
        if isinstance(outcome, dict) and "success" in outcome:
            return bool(outcome.get("success")), outcome
        if isinstance(outcome, bool):
            return outcome, outcome
        if outcome is None:
            return False, None
        # Empty containers are treated as failure
        if isinstance(outcome, (list, tuple, set, dict)) and not outcome:
            return False, outcome
        # Non-empty/non-None/non-bool truthy => success
        return True, outcome

    @staticmethod
    def _stringify_exception(exc: Exception) -> str:
        cls = type(exc).__name__
        msg = str(exc)
        return f"{cls}: {msg}" if msg else cls

    @classmethod
    def _redact_text(cls, text: Optional[str]) -> str:
        """
        Redact secrets from arbitrary text while preserving readable context.
        - Generic credentials: replace value with [REDACTED]
        - Authorization Bearer: canonicalize to 'Authorization: Bearer [REDACTED]'
        """
        if text is None:
            return ""
        s = str(text)

        # Canonicalize Bearer tokens (case-insensitive)
        # Replace the entire header with canonical capitalization
        bearer_pattern = re.compile(r"(?i)authorization\s*:\s*bearer\s+([^\s]+)")
        s = bearer_pattern.sub("Authorization: Bearer [REDACTED]", s)

        # Generic key=value redaction
        keys = [
            "password",
            "passwd",
            "pwd",
            "secret",
            "api_key",
            "api-key",
            "token",
            "access_token",
            "access-token",
            "refresh_token",
            "refresh-token",
            "private_key",
            "private-key",
        ]
        # Build regex to match key[:=]value with optional quotes around value
        key_alt = "|".join(re.escape(k) for k in keys)
        # Example matches: password: value | password="value" | api_key=value
        generic_re = re.compile(
            rf"(?i)\b({key_alt})\b\s*[:=]\s*(\"|\'|)([^\"\'\s;,:]+)\2"
        )
        def _sub_cred(m: re.Match[str]) -> str:
            # Preserve the key label, normalize separator to ':' for readability
            key = m.group(1)
            return f"{key}: [REDACTED]"
        s = generic_re.sub(_sub_cred, s)

        return s

    @staticmethod
    def _freeze_result(result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Return a deterministic deep-copied result limited to JSON-safe primitives.
        """
        # Convert any None placeholders for stages to consistent dicts
        frozen = copy.deepcopy(result)
        for rec in frozen.get("history", []):
            if rec.get("apply") is None:
                rec["apply"] = {"success": None, "error": None}
            if rec.get("validation") is None:
                rec["validation"] = {"success": None, "error": None}
        # Ensure blocked_reasons ordering is deterministic as defined in policy list
        if "blocked_reasons" in frozen and isinstance(frozen["blocked_reasons"], list):
            order = {name: idx for idx, name in enumerate(MissionRepairAdapter._POLICY_BLOCKS)}
            frozen["blocked_reasons"].sort(key=lambda n: order.get(n, len(order)))
        return frozen


__all__ = [
    "MissionRepairAdapter",
    "RepairRequest",
]
