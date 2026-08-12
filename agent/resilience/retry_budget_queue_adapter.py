# Copyright (c) MITIGATE
# SPDX-License-Identifier: Apache-2.0
#
# Adapter: MissionQueue retry state -> RetryBudget semantics (projection only)
# - No persistence
# - No mutation of inputs
# - No background execution
# - Provider independent
# - Deterministic and side-effect-free
#
# MissionQueue remains the authoritative owner of retry state. This adapter
# computes a read-only view that maps the existing MissionQueue fields to
# RetryBudget-friendly semantics without introducing a new counter or any
# consumption authority.

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Tuple

__all__ = [
    "RetryBudgetProjectionError",
    "RetryStateView",
    "project_retry_budget",
]


class RetryBudgetProjectionError(ValueError):
    """Raised when mission retry fields are malformed.

    The adapter fails closed on malformed values to avoid accidentally
    granting retry authority due to coercion or permissive normalization.
    """


# The adapter recognizes several common mission state keys and values while
# remaining projection-safe for legacy and recovery-shaped records.
_STATE_KEYS = (
    "state",
    "status",
    "phase",
    "mission_state",
    "lifecycle_state",
    "queue_state",
)

# Canonical state groups for gating retry eligibility.
_COMPLETED_STATES = {"completed", "success", "succeeded", "done"}
_FAILED_STATES = {"failed", "error", "errored", "failure"}
_RETRYING_STATES = {"retrying", "retry", "needs_retry", "backoff"}
_BLOCKED_STATES = {"blocked", "paused", "on_hold", "hold", "waiting"}
_RUNNING_STATES = {"running", "in_progress", "executing"}
_QUEUED_STATES = {"queued", "pending", "ready"}
_CANCELLED_STATES = {"cancelled", "canceled", "aborted"}
_STALE_RUNNING_STATES = {"stale-running", "stale_running", "orphaned"}


def _is_bool_like(value: Any) -> bool:
    # In Python, bool is a subclass of int. We must reject booleans explicitly
    # to avoid semantic confusion (e.g., True == 1, False == 0) as per mission
    # requirements.
    return isinstance(value, bool)


def _validated_non_negative_int(name: str, value: Any, default: int | None = None) -> int:
    """Validate a non-negative integer retry field.

    - Missing or None -> default if provided, else error
    - Reject booleans even though they are ints
    - Reject negative values
    - Reject non-integer types
    """
    if value is None:
        if default is not None:
            return default
        raise RetryBudgetProjectionError(f"{name} is required")

    if _is_bool_like(value):
        raise RetryBudgetProjectionError(f"{name} must be a non-negative integer, not a boolean")

    if not isinstance(value, int):
        raise RetryBudgetProjectionError(f"{name} must be a non-negative integer")

    if value < 0:
        raise RetryBudgetProjectionError(f"{name} must be non-negative")

    return int(value)


def _extract_state(mission: Mapping[str, Any] | Any) -> Tuple[str, Optional[str]]:
    """Extract a best-effort, projection-safe mission state.

    The adapter consumes a mapping-like object or any object with attributes.
    It recognizes multiple key names to preserve compatibility with legacy or
    provider-specific shapes. Returns a tuple of (canonical_state, raw_value).
    canonical_state may be one of: completed, failed, retrying, blocked,
    running, queued, cancelled, stale-running, or unknown.
    """
    raw: Optional[str] = None

    # Try mapping-like access first.
    if isinstance(mission, Mapping):
        for k in _STATE_KEYS:
            if k in mission:
                raw = mission.get(k)
                break
    else:
        # Fallback to attribute access for simple mission objects
        for k in _STATE_KEYS:
            if hasattr(mission, k):
                raw = getattr(mission, k)
                break

    raw_norm: Optional[str] = str(raw).strip().lower() if isinstance(raw, str) else None

    if not raw_norm:
        return ("unknown", raw)

    if raw_norm in _COMPLETED_STATES:
        return ("completed", raw)
    if raw_norm in _FAILED_STATES:
        return ("failed", raw)
    if raw_norm in _RETRYING_STATES:
        return ("retrying", raw)
    if raw_norm in _BLOCKED_STATES:
        return ("blocked", raw)
    if raw_norm in _RUNNING_STATES:
        return ("running", raw)
    if raw_norm in _QUEUED_STATES:
        return ("queued", raw)
    if raw_norm in _CANCELLED_STATES:
        return ("cancelled", raw)
    if raw_norm in _STALE_RUNNING_STATES:
        return ("stale-running", raw)

    return ("unknown", raw)


@dataclass(frozen=True, slots=True)
class RetryStateView:
    """Read-only projection of MissionQueue retry state.

    Fields:
    - attempts_done: total retries performed so far (MissionQueue authoritative)
    - max_retries: maximum allowed retries (MissionQueue authoritative)
    - retries_remaining: max(0, max_retries - attempts_done)
    - exhausted: True iff retries_remaining == 0
    - eligible: True iff not exhausted and mission in a retry-permitting state
    - canonical_state: normalized mission state string for gating
    - raw_state: original state value, if available

    The adapter never mutates inputs and keeps no internal consumption state.
    """

    attempts_done: int
    max_retries: int
    retries_remaining: int
    exhausted: bool
    eligible: bool
    canonical_state: str
    raw_state: Optional[str]

    def to_dict(self) -> Mapping[str, Any]:
        return {
            "attempts_done": self.attempts_done,
            "max_retries": self.max_retries,
            "retries_remaining": self.retries_remaining,
            "exhausted": self.exhausted,
            "eligible": self.eligible,
            "canonical_state": self.canonical_state,
            "raw_state": self.raw_state,
        }


def _compute_retries_remaining(attempts_done: int, max_retries: int) -> int:
    # Deterministic, clamps to 0 if attempts_done exceeds max_retries.
    remaining = max_retries - attempts_done
    return remaining if remaining > 0 else 0


def _compute_retry_eligibility(canonical_state: str, exhausted: bool) -> bool:
    # Fail closed: only permit retry if explicitly failed or in retrying state.
    # All other states (including running, queued, completed, blocked, cancelled,
    # stale-running, unknown) are not eligible.
    if exhausted:
        return False
    if canonical_state in ("failed", "retrying"):
        return True
    return False


def project_retry_budget(mission: Mapping[str, Any] | Any) -> RetryStateView:
    """Project MissionQueue retry fields to a read-only RetryBudget view.

    Inputs:
    - mission: mapping-like or object with attributes. Recognized fields:
      attempts_done (int >= 0), max_retries (int >= 0), and an optional state
      key among: state, status, phase, mission_state, lifecycle_state, queue_state.

    Behavior:
    - Does not mutate mission
    - Fails closed on malformed values (type errors, negatives, bools)
    - Missing attempts_done or max_retries default to 0 (legacy-safe)
    - Eligibility is granted only when state is failed/retrying and budget
      remains; never grants authority in completed/blocked/etc. states.
    """
    # Extract raw values without mutation.
    attempts_val: Any = None
    max_retries_val: Any = None

    if isinstance(mission, Mapping):
        attempts_val = mission.get("attempts_done")
        max_retries_val = mission.get("max_retries")
    else:
        attempts_val = getattr(mission, "attempts_done", None)
        max_retries_val = getattr(mission, "max_retries", None)

    attempts_done = _validated_non_negative_int("attempts_done", attempts_val, default=0)
    max_retries = _validated_non_negative_int("max_retries", max_retries_val, default=0)

    retries_remaining = _compute_retries_remaining(attempts_done, max_retries)

    canonical_state, raw_state = _extract_state(mission)
    exhausted = retries_remaining == 0
    eligible = _compute_retry_eligibility(canonical_state, exhausted)

    return RetryStateView(
        attempts_done=attempts_done,
        max_retries=max_retries,
        retries_remaining=retries_remaining,
        exhausted=exhausted,
        eligible=eligible,
        canonical_state=canonical_state,
        raw_state=raw_state if isinstance(raw_state, str) else None,
    )
