from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple
import copy
import re


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
        Execute validation and at most three bounded self-healing repair attempts.

        Parameters are not mutated. Allowed/denied paths are preserved and not expanded.
        Exceptions from callbacks are converted to safe failure events with redaction.
        """
        # Copy inputs to guarantee immutability of caller-provided objects
        original_allowed = list(allowed_paths)
        original_denied = list(denied_paths)

        # Prepare result container
        result: Dict[str, Any] = {
            "status": "",
            "attempts": 0,
            "initial_validation": {"success": None, "error": None},
            "history": [],  # one entry per attempt
            "failures": [],  # flattened failures across stages
            "blocked_reasons": [],
        }

        # Run initial validation (exception is a failure event; does not force final failure)
        initial_success, initial_err = self._call_validation()
        result["initial_validation"] = {
            "success": initial_success,
            "error": self._redact_text(initial_err) if initial_err else None,
        }
        if initial_err is not None:
            result["failures"].append(
                {
                    "stage": "validation",
                    "attempt": 0,
                    "message": self._redact_text(initial_err),
                }
            )

        # If already valid or validation not required, succeed early
        if (initial_success is True) or (validation_required is False and initial_success is not False):
            result["status"] = "succeeded"
            result["attempts"] = 0
            return self._freeze_result(result)

        # Check safety policy blocks prior to generation/apply
        blocks = set(str(b) for b in (policy_blocks or ()))
        blocked_reasons = [b for b in self._POLICY_BLOCKS if b in blocks]
        if blocked_reasons:
            # Do not call generation/apply when blocked.
            result["status"] = "blocked"
            result["attempts"] = 0
            result["blocked_reasons"] = blocked_reasons
            return self._freeze_result(result)

        # Prepare immutable redacted request base fields
        redacted_objective = self._redact_text(objective)
        redacted_summary = self._redact_text(failure_summary)

        # Do not expand or mutate paths; store as tuples for immutability
        allowed_tuple = tuple(original_allowed)
        denied_tuple = tuple(original_denied)

        # Attempt up to MAX_ATTEMPTS repairs
        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            # Build request (immutable)
            request = RepairRequest(
                mission_name=mission_name,
                attempt_number=attempt,
                objective=redacted_objective,
                failure_category=failure_category,
                failure_summary=redacted_summary,
                allowed_paths=allowed_tuple,
                denied_paths=denied_tuple,
                validation_required=validation_required,
            )

            # Generation step
            gen_success, gen_payload, gen_err = self._call_generate(request)
            attempt_rec: Dict[str, Any] = {
                "attempt": attempt,
                "generation": {
                    "success": gen_success,
                    "error": self._redact_text(gen_err) if gen_err else None,
                },
                "apply": None,
                "validation": None,
            }
            if gen_err is not None:
                result["failures"].append(
                    {
                        "stage": "generation",
                        "attempt": attempt,
                        "message": self._redact_text(gen_err),
                    }
                )
            result["history"].append(attempt_rec)

            if not gen_success:
                # Proceed to next attempt
                result["attempts"] = attempt
                if attempt == self.MAX_ATTEMPTS:
                    result["status"] = "exhausted"
                continue

            # Apply step
            app_success, app_err = self._call_apply(gen_payload)
            attempt_rec["apply"] = {
                "success": app_success,
                "error": self._redact_text(app_err) if app_err else None,
            }
            if app_err is not None:
                result["failures"].append(
                    {
                        "stage": "apply",
                        "attempt": attempt,
                        "message": self._redact_text(app_err),
                    }
                )
            result["attempts"] = attempt

            if not app_success:
                if attempt == self.MAX_ATTEMPTS:
                    result["status"] = "exhausted"
                continue

            # Post-apply validation
            val_success, val_err = self._call_validation()
            attempt_rec["validation"] = {
                "success": val_success,
                "error": self._redact_text(val_err) if val_err else None,
            }
            if val_err is not None:
                result["failures"].append(
                    {
                        "stage": "validation",
                        "attempt": attempt,
                        "message": self._redact_text(val_err),
                    }
                )

            if val_success:
                result["status"] = "succeeded"
                return self._freeze_result(result)

            # Otherwise continue to next attempt
            if attempt == self.MAX_ATTEMPTS:
                result["status"] = "exhausted"

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
