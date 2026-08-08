from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Iterable, Mapping, Optional, Tuple

from .failure_capture import FailureRecord

# Repair states
REPAIR_STATE_PENDING = "pending"
REPAIR_STATE_DIAGNOSING = "diagnosing"
REPAIR_STATE_REPAIR_PLANNED = "repair_planned"
REPAIR_STATE_VALIDATING = "validating"
REPAIR_STATE_SUCCEEDED = "succeeded"
REPAIR_STATE_EXHAUSTED = "exhausted"
REPAIR_STATE_BLOCKED = "blocked"

# Blocking flags for immediate block conditions (strings)
_BLOCKING_FLAGS = {
    "protected_core_access",
    "canonical_recovery_test_access",
    "unavailable_core_protection",
    "security_policy_bypass",
    "repository_safety_bypass",
    "provider_auth_intervention",
}


def _deep_freeze(obj: Any) -> Any:
    """Convert mutable containers into immutable equivalents for safe storage."""
    if isinstance(obj, dict):
        # Represent dicts as sorted tuples of (key, frozen_value)
        return tuple((k, _deep_freeze(obj[k])) for k in sorted(obj.keys()))
    if isinstance(obj, (list, tuple, set)):
        # Preserve order for tuples/lists; sets are sorted for determinism
        if isinstance(obj, set):
            return tuple(sorted((_deep_freeze(v) for v in obj), key=lambda x: json.dumps(x, sort_keys=True, separators=(",", ":"))))
        return tuple(_deep_freeze(v) for v in obj)
    return obj


def _canonicalize(obj: Any) -> Any:
    """Canonicalize structure for deterministic serialization.

    - Dicts: sorted by key, values canonicalized.
    - Lists/Tuples/Sets: sorted by their JSON representation for stable order.
    - Primitives: unchanged.
    """
    if isinstance(obj, dict):
        return {k: _canonicalize(obj[k]) for k in sorted(obj.keys())}
    if isinstance(obj, (list, tuple, set)):
        items = list(obj) if not isinstance(obj, set) else list(obj)
        can_items = [_canonicalize(v) for v in items]
        # Sort deterministically by JSON representation
        can_items.sort(key=lambda x: json.dumps(x, sort_keys=True, separators=(",", ":")))
        return can_items
    return obj


def _deterministic_digest(payload: Any) -> str:
    canonical = _canonicalize(payload)
    data = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _has_blocking_flag(obj: Any) -> bool:
    # Recursively check containers for any blocking flag
    if obj is None:
        return False
    if isinstance(obj, str):
        return obj in _BLOCKING_FLAGS
    if isinstance(obj, Mapping):
        return any(_has_blocking_flag(k) or _has_blocking_flag(v) for k, v in obj.items())
    if isinstance(obj, (list, tuple, set)):
        return any(_has_blocking_flag(v) for v in obj)
    return False


@dataclass(frozen=True)
class RepairPlan:
    repair_id: str
    attempt_number: int
    failure_category: str
    objective: str
    constraints: Tuple[Any, ...]
    allowed_paths: Tuple[str, ...]
    denied_paths: Tuple[str, ...]
    validation_required: bool


class RepairLoop:
    """Pure logic self-healing repair loop with bounded retries and blocking safeguards."""

    def __init__(self, max_attempts: int = 3) -> None:
        if not isinstance(max_attempts, int) or max_attempts <= 0:
            raise ValueError("max_attempts must be a positive integer")
        self._max_attempts = int(max_attempts)
        self._state = REPAIR_STATE_PENDING
        self._attempt_number = 0
        self._history: list[FailureRecord] = []

    @property
    def state(self) -> str:
        return self._state

    @property
    def max_attempts(self) -> int:
        return self._max_attempts

    @property
    def attempt_number(self) -> int:
        return self._attempt_number

    @property
    def history(self) -> Tuple[FailureRecord, ...]:
        return tuple(self._history)

    def record_failure(self, failure: FailureRecord) -> None:
        # Pure recording; does not execute any side effects
        self._history.append(failure)
        self._state = REPAIR_STATE_DIAGNOSING

    def _compute_repair_id(
        self,
        failure_category: str,
        attempt_number: int,
        objective: str,
        constraints: Any,
        allowed_paths: Iterable[str],
        denied_paths: Iterable[str],
        validation_required: bool,
    ) -> str:
        # For deterministic IDs, use canonical normalized inputs. For lists, use sorted representation.
        payload = {
            "failure_category": failure_category,
            "attempt_number": attempt_number,
            "objective": objective,
            "constraints": constraints,
            "allowed_paths": list(sorted(list(allowed_paths))),
            "denied_paths": list(sorted(list(denied_paths))),
            "validation_required": bool(validation_required),
        }
        return _deterministic_digest(payload)

    def plan_repair(
        self,
        failure: FailureRecord,
        *,
        objective: str,
        constraints: Optional[Mapping[str, Any] | Iterable[Any]] = None,
        allowed_paths: Optional[Iterable[str]] = None,
        denied_paths: Optional[Iterable[str]] = None,
        validation_required: bool = True,
    ) -> Optional[RepairPlan]:
        # Immediate block on protected conditions
        if _has_blocking_flag(constraints):
            self._state = REPAIR_STATE_BLOCKED
            return None

        # Exhaustion check before incrementing attempt
        if self._attempt_number >= self._max_attempts:
            self._state = REPAIR_STATE_EXHAUSTED
            return None

        # Bump attempt
        self._attempt_number += 1

        apaths = tuple(list(allowed_paths) if allowed_paths is not None else [])
        dpaths = tuple(list(denied_paths) if denied_paths is not None else [])
        frozen_constraints = _deep_freeze(constraints if constraints is not None else ())

        rid = self._compute_repair_id(
            failure_category=failure.category,
            attempt_number=self._attempt_number,
            objective=str(objective),
            constraints=constraints if constraints is not None else (),
            allowed_paths=apaths,
            denied_paths=dpaths,
            validation_required=validation_required,
        )

        plan = RepairPlan(
            repair_id=rid,
            attempt_number=self._attempt_number,
            failure_category=failure.category,
            objective=str(objective),
            constraints=frozen_constraints,
            allowed_paths=apaths,
            denied_paths=dpaths,
            validation_required=bool(validation_required),
        )
        self._state = REPAIR_STATE_REPAIR_PLANNED
        return plan

    def mark_validating(self) -> None:
        # Transition to validating state without side effects
        self._state = REPAIR_STATE_VALIDATING

    def mark_succeeded(self) -> None:
        self._state = REPAIR_STATE_SUCCEEDED

    def can_retry(self) -> bool:
        return self._attempt_number < self._max_attempts and self._state not in (
            REPAIR_STATE_BLOCKED,
            REPAIR_STATE_SUCCEEDED,
        )

    def maybe_exhaust(self) -> None:
        if self._attempt_number >= self._max_attempts and self._state not in (
            REPAIR_STATE_BLOCKED,
            REPAIR_STATE_SUCCEEDED,
        ):
            self._state = REPAIR_STATE_EXHAUSTED
