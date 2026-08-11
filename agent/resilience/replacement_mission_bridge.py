from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping


@dataclass(frozen=True)
class NativeReplacementRequest:
    capability: str
    project_id: str
    reason: str
    source_provider: str | None = None
    source_technology: str | None = None


class NativeReplacementMissionBridge:
    """
    Convert a detected native capability gap into a normal MITIGATE mission.

    Architectural rules:
    - MITIGATE remains the system of record.
    - Replacement missions are always native-only.
    - External technologies may be studied as references.
    - External providers must never become runtime dependencies.
    - This bridge does not execute code or bypass the normal mission pipeline.
    """

    def __init__(
        self,
        *,
        queue_coordinator: Any,
        queue_reference: str,
        clock: Any | None = None,
    ) -> None:
        self._queue_coordinator = queue_coordinator
        self._queue_reference = str(queue_reference)
        self._clock = clock

    def create_mission(
        self,
        request: NativeReplacementRequest,
    ) -> dict[str, Any]:
        self._validate_request(request)

        created_at = self._now_iso()
        mission_id = self._mission_id(request)

        source_context: dict[str, str] = {}

        if request.source_provider:
            source_context["provider"] = request.source_provider

        if request.source_technology:
            source_context["technology"] = request.source_technology

        payload = {
            "resilience": {
                "mode": "native_replacement",
                "capability": request.capability,
                "reason": request.reason,
                "native_only": True,
                "external_runtime_dependency_allowed": False,
                "source_context": source_context,
            },
            "implementation_requirements": {
                "preserve_existing_core": True,
                "use_existing_mission_pipeline": True,
                "require_validation": True,
                "require_regression_tests": True,
                "require_safe_fallback": True,
                "require_provider_independence": True,
            },
        }

        return {
            "mission_id": mission_id,
            "project_id": request.project_id,
            "request_id": mission_id,
            "conversation_id": "system-resilience",
            "plan_id": "native-capability-replacement",
            "step_id": request.capability,
            "title": (
                f"Build native replacement for "
                f"{request.capability}"
            ),
            "description": (
                "Implement and validate a MITIGATE-native "
                f"replacement for capability "
                f"{request.capability}. External technology "
                "may be studied for architectural knowledge, "
                "but the resulting runtime capability must "
                "remain independently owned and executable "
                "by MITIGATE."
            ),
            "task_type": "native_capability_replacement",
            "provider_id": "native",
            "model_id": "auto",
            "dependencies": [],
            "priority": 9,
            "payload": payload,
            "status": "pending",
            "created_at": created_at,
        }

    def enqueue(
        self,
        request: NativeReplacementRequest,
    ) -> Mapping[str, Any]:
        mission = self.create_mission(request)

        return self._queue_coordinator.enqueue(
            request.project_id,
            self._queue_reference,
            [mission],
        )

    @staticmethod
    def _validate_request(
        request: NativeReplacementRequest,
    ) -> None:
        if not request.capability.strip():
            raise ValueError("capability is required")

        if not request.project_id.strip():
            raise ValueError("project_id is required")

        if not request.reason.strip():
            raise ValueError("reason is required")

    @staticmethod
    def _mission_id(
        request: NativeReplacementRequest,
    ) -> str:
        canonical = "|".join(
            (
                request.project_id.strip(),
                request.capability.strip(),
                request.reason.strip(),
                (request.source_provider or "").strip(),
                (request.source_technology or "").strip(),
            )
        )

        digest = hashlib.sha256(
            canonical.encode("utf-8")
        ).hexdigest()[:16]

        return f"native-replacement-{digest}"

    def _now_iso(self) -> str:
        if self._clock is not None:
            try:
                now = self._clock.now()
                if isinstance(now, datetime):
                    if now.tzinfo is None:
                        now = now.replace(
                            tzinfo=timezone.utc
                        )
                    return now.isoformat()
            except Exception:
                pass

        return datetime.now(
            timezone.utc
        ).isoformat()
