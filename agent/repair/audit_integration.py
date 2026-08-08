from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# Phase 3A observability API: use exactly as specified
from .observability import (
    RepairAttemptEvent,
    SelfHealingAuditBuilder,
    SelfHealingAuditRecord,
)

__all__ = [
    "SelfHealingAuditIntegration",
    "build_audit_from_mission_result",
]


_ACCEPTED_FINAL_STATES: Tuple[str, ...] = ("succeeded", "exhausted", "blocked", "failed")


def _status_from_success_flag(flag: Optional[bool]) -> Optional[str]:
    if flag is True:
        return "succeeded"
    if flag is False:
        return "failed"
    return None


def _snapshot_paths(paths: Optional[Iterable[str]]) -> Tuple[str, ...]:
    if paths is None:
        return ()
    # Defensive snapshot: ensure tuple copy and string items only
    return tuple(str(p) for p in paths)


def build_audit_from_mission_result(
    mission_name: str,
    repair_id: str,
    mission_result: Dict[str, Any],
    *,
    allowed_paths: Optional[Iterable[str]] = None,
    denied_paths: Optional[Iterable[str]] = None,
    initial_failure_category: Optional[str] = None,
    initial_safe_summary: Optional[str] = None,
    started_at: Any = None,
    completed_at: Any = None,
) -> SelfHealingAuditRecord:
    """
    Passive translator from a mission repair result structure into the Phase 3A
    observability audit model.

    This function does not execute any repair logic or perform any side effects.
    It strictly translates provided state into SelfHealingAuditRecord using the
    existing Phase 3A builder and event classes.
    """
    if not mission_name:
        raise ValueError("mission_name is required")
    if not repair_id:
        raise ValueError("repair_id is required")

    status = mission_result.get("status")
    if status not in _ACCEPTED_FINAL_STATES:
        raise ValueError(f"Unsupported final state: {status!r}")

    history: Sequence[Dict[str, Any]] = mission_result.get("history") or []

    # Defensive snapshots for global allowed/denied paths
    global_allowed = _snapshot_paths(allowed_paths)
    global_denied = _snapshot_paths(denied_paths)

    builder = SelfHealingAuditBuilder(
        mission_name=mission_name,
        repair_id=repair_id,
        initial_failure_category=initial_failure_category,
        initial_safe_summary=initial_safe_summary,
        started_at=started_at,
    )

    seen_attempts: set[int] = set()

    for entry in history:
        if not isinstance(entry, dict):
            raise ValueError("Each history entry must be a mapping/dict")

        if "attempt" not in entry:
            raise ValueError("History entry is missing required 'attempt' number")
        attempt_number = entry.get("attempt")
        if not isinstance(attempt_number, int):
            raise ValueError("Attempt number must be an integer")
        if attempt_number <= 0:
            raise ValueError("Attempt number must be a positive integer")
        if attempt_number in seen_attempts:
            raise ValueError(f"Duplicate attempt number detected: {attempt_number}")
        seen_attempts.add(attempt_number)

        gen_block = entry.get("generation") or {}
        apply_block = entry.get("apply") or {}
        val_block = entry.get("validation") or {}

        generation_status = _status_from_success_flag(gen_block.get("success"))
        application_status = _status_from_success_flag(apply_block.get("success"))
        validation_status = _status_from_success_flag(val_block.get("success"))

        # Allow per-attempt safe path values if explicitly provided.
        per_attempt_allowed = _snapshot_paths(entry.get("allowed_paths")) if "allowed_paths" in entry else global_allowed
        per_attempt_denied = _snapshot_paths(entry.get("denied_paths")) if "denied_paths" in entry else global_denied

        # Do not copy raw error strings or exception objects into the audit event.
        # Attempt-level failure_category and safe_failure_summary are provided only if
        # already-sanitized; default to None for passive translation.
        event = RepairAttemptEvent(
            mission_name=mission_name,
            repair_id=repair_id,
            attempt_number=attempt_number,
            failure_category=None,
            safe_failure_summary=None,
            allowed_paths=per_attempt_allowed,
            denied_paths=per_attempt_denied,
            generation_status=generation_status,
            application_status=application_status,
            validation_status=validation_status,
            started_at=None,
            completed_at=None,
        )
        builder.add_attempt(event)

    blocked_reasons = mission_result.get("blocked_reasons") or []
    blocked_condition = None
    if status == "blocked" and isinstance(blocked_reasons, list) and blocked_reasons:
        blocked_condition = blocked_reasons[0]

    record = builder.finalize(
        final_state=status,
        completed_at=completed_at,
        blocked_condition=blocked_condition,
    )

    # Passive contract: do not mutate inputs; return the constructed record.
    return record


class SelfHealingAuditIntegration:
    """
    Phase 3B-1 integration adapter facade for Self-Healing repair audit
    translation. Provides a minimal interface to build an audit record from a
    mission result using the existing Phase 3A observability model.
    """

    @staticmethod
    def build_audit_from_mission_result(
        mission_name: str,
        repair_id: str,
        mission_result: Dict[str, Any],
        *,
        allowed_paths: Optional[Iterable[str]] = None,
        denied_paths: Optional[Iterable[str]] = None,
        initial_failure_category: Optional[str] = None,
        initial_safe_summary: Optional[str] = None,
        started_at: Any = None,
        completed_at: Any = None,
    ) -> SelfHealingAuditRecord:
        return build_audit_from_mission_result(
            mission_name=mission_name,
            repair_id=repair_id,
            mission_result=mission_result,
            allowed_paths=allowed_paths,
            denied_paths=denied_paths,
            initial_failure_category=initial_failure_category,
            initial_safe_summary=initial_safe_summary,
            started_at=started_at,
            completed_at=completed_at,
        )
