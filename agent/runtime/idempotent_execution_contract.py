from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class IdempotentExecutionContractError(ValueError):
    pass


class IdempotencyDecision(str, Enum):
    NEW = "new"
    REPLAY = "replay"
    CONFLICT = "conflict"


@dataclass(frozen=True)
class IdempotentExecutionIdentity:
    project_id: str
    request_id: str
    mission_id: str
    execution_id: str
    attempts_done: int


@dataclass(frozen=True)
class IdempotencyResult:
    decision: IdempotencyDecision
    reason: str


class IdempotentExecutionContract:
    """
    MITIGATE-native deterministic execution idempotency contract.

    This component is intentionally side-effect free.

    It does not:
    - persist state
    - enqueue missions
    - execute missions
    - write reports
    - write checkpoints
    - perform network calls

    Existing MITIGATE runtime components remain responsible for
    enforcing persistence-level duplicate and replay guarantees.
    """

    @classmethod
    def validate_identity(
        cls,
        identity: IdempotentExecutionIdentity,
    ) -> IdempotentExecutionIdentity:
        project_id = cls._required_string(
            identity.project_id,
            "project_id",
        )

        request_id = cls._required_string(
            identity.request_id,
            "request_id",
        )

        mission_id = cls._required_string(
            identity.mission_id,
            "mission_id",
        )

        execution_id = cls._required_string(
            identity.execution_id,
            "execution_id",
        )

        attempts_done = identity.attempts_done

        if type(attempts_done) is not int:
            raise IdempotentExecutionContractError(
                "attempts_done must be an integer"
            )

        if attempts_done < 0:
            raise IdempotentExecutionContractError(
                "attempts_done must be non-negative"
            )

        return IdempotentExecutionIdentity(
            project_id=project_id,
            request_id=request_id,
            mission_id=mission_id,
            execution_id=execution_id,
            attempts_done=attempts_done,
        )

    @classmethod
    def worker_attempt_execution_id(
        cls,
        *,
        mission_id: str,
        attempts_done: int,
    ) -> str:
        mission_id = cls._required_string(
            mission_id,
            "mission_id",
        )

        if type(attempts_done) is not int:
            raise IdempotentExecutionContractError(
                "attempts_done must be an integer"
            )

        if attempts_done < 0:
            raise IdempotentExecutionContractError(
                "attempts_done must be non-negative"
            )

        return (
            f"runtime-{mission_id}-"
            f"attempt-{attempts_done}"
        )

    @classmethod
    def classify(
        cls,
        incoming: IdempotentExecutionIdentity,
        existing: Mapping[str, Any] | None,
    ) -> IdempotencyResult:
        incoming = cls.validate_identity(
            incoming
        )

        if existing is None:
            return IdempotencyResult(
                decision=IdempotencyDecision.NEW,
                reason="execution_identity_not_seen",
            )

        if not isinstance(existing, Mapping):
            raise IdempotentExecutionContractError(
                "existing execution identity must be a mapping"
            )

        existing_execution_id = cls._mapping_string(
            existing,
            "execution_id",
        )

        if existing_execution_id != incoming.execution_id:
            return IdempotencyResult(
                decision=IdempotencyDecision.NEW,
                reason="different_execution_identity",
            )

        existing_project_id = cls._mapping_string(
            existing,
            "project_id",
        )

        existing_request_id = cls._mapping_string(
            existing,
            "request_id",
        )

        existing_mission_id = cls._mapping_string(
            existing,
            "mission_id",
        )

        if existing_project_id != incoming.project_id:
            return IdempotencyResult(
                decision=IdempotencyDecision.CONFLICT,
                reason="execution_id_project_conflict",
            )

        if existing_request_id != incoming.request_id:
            return IdempotencyResult(
                decision=IdempotencyDecision.CONFLICT,
                reason="execution_id_request_conflict",
            )

        if existing_mission_id != incoming.mission_id:
            return IdempotencyResult(
                decision=IdempotencyDecision.CONFLICT,
                reason="execution_id_mission_conflict",
            )

        return IdempotencyResult(
            decision=IdempotencyDecision.REPLAY,
            reason="same_logical_execution",
        )

    @staticmethod
    def _required_string(
        value: Any,
        field: str,
    ) -> str:
        if not isinstance(value, str):
            raise IdempotentExecutionContractError(
                f"{field} must be a string"
            )

        value = value.strip()

        if not value:
            raise IdempotentExecutionContractError(
                f"{field} is required"
            )

        return value

    @classmethod
    def _mapping_string(
        cls,
        mapping: Mapping[str, Any],
        field: str,
    ) -> str:
        return cls._required_string(
            mapping.get(field),
            field,
        )


__all__ = [
    "IdempotencyDecision",
    "IdempotencyResult",
    "IdempotentExecutionContract",
    "IdempotentExecutionContractError",
    "IdempotentExecutionIdentity",
]
