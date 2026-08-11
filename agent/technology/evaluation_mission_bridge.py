from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from .watcher import TechnologyEvaluationCandidate


@dataclass(frozen=True)
class TechnologyEvaluationRequest:
    project_id: str
    candidate: TechnologyEvaluationCandidate
    reason: str = "technology_watcher_candidate"


class TechnologyEvaluationMissionBridge:
    """
    Convert a Technology Watcher evaluation candidate into a normal
    MITIGATE mission.

    Architectural rules:
    - MITIGATE remains the system of record.
    - External technology is intelligence only.
    - Evaluation never installs or activates external technology.
    - Evaluation never creates runtime dependencies.
    - Evaluation uses the existing MITIGATE mission pipeline.
    - This bridge never executes the mission itself.
    """

    def __init__(
        self,
        *,
        queue_coordinator: Any,
        queue_reference: str,
        clock: Any | None = None,
    ) -> None:
        self._queue_coordinator = queue_coordinator
        self._queue_reference = str(
            queue_reference
        )
        self._clock = clock

    def create_mission(
        self,
        request: TechnologyEvaluationRequest,
    ) -> dict[str, Any]:
        self._validate_request(request)

        candidate = request.candidate
        score = candidate.score

        mission_id = self._mission_id(
            request
        )

        payload = {
            "technology_evaluation": {
                "technology_id":
                    candidate.technology_id,
                "observed_version":
                    candidate.observed_version,
                "reason":
                    request.reason,
                "score": {
                    "total":
                        score.total,
                    "evaluation_candidate":
                        score.evaluation_candidate,
                },
                "external_runtime_dependency_allowed":
                    False,
                "installation_allowed":
                    False,
                "activation_allowed":
                    False,
                "runtime_adoption_allowed":
                    False,
            },
            "evaluation_requirements": {
                "inspect_existing_mitigate_capabilities":
                    True,
                "identify_useful_architectural_patterns":
                    True,
                "identify_capability_gaps":
                    True,
                "identify_security_risks":
                    True,
                "identify_licensing_risks":
                    True,
                "identify_dependency_risks":
                    True,
                "preserve_existing_core":
                    True,
                "prefer_native_assimilation":
                    True,
                "require_provider_independence":
                    True,
                "require_human_review_before_adoption":
                    True,
            },
            "allowed_recommendations": [
                "reject",
                "watch",
                "sandbox",
                "assimilate_candidate",
            ],
            "prohibited_actions": [
                "install_external_runtime",
                "activate_external_runtime",
                "replace_mitigate_core",
                "create_runtime_dependency",
                "modify_mission_architecture",
                "bypass_validation",
            ],
            "deliverables": [],
        }

        return {
            "mission_id": mission_id,
            "project_id":
                request.project_id,
            "request_id": mission_id,
            "conversation_id":
                "system-technology-intelligence",
            "plan_id":
                "technology-evaluation",
            "step_id":
                candidate.technology_id,
            "title": (
                "Evaluate technology "
                f"{candidate.technology_id}"
            ),
            "description": (
                "Evaluate the observed external technology "
                f"{candidate.technology_id} as an intelligence "
                "source for MITIGATE. Identify useful capabilities, "
                "architectural patterns, risks, and opportunities "
                "for MITIGATE-native assimilation. Do not install, "
                "activate, or create a runtime dependency on the "
                "external technology."
            ),
            "task_type":
                "technology_evaluation",
            "provider_id":
                "native",
            "model_id":
                "auto",
            "dependencies": [],
            "priority": 6,
            "payload": payload,
            "status": "pending",
            "created_at":
                self._now_iso(),
        }

    def enqueue(
        self,
        request: TechnologyEvaluationRequest,
    ) -> Mapping[str, Any]:
        mission = self.create_mission(
            request
        )

        return self._queue_coordinator.enqueue(
            request.project_id,
            self._queue_reference,
            [mission],
        )

    @staticmethod
    def _validate_request(
        request: TechnologyEvaluationRequest,
    ) -> None:
        if not isinstance(
            request.project_id,
            str,
        ) or not request.project_id.strip():
            raise ValueError(
                "project_id is required"
            )

        candidate = request.candidate

        if not isinstance(
            candidate.technology_id,
            str,
        ) or not candidate.technology_id.strip():
            raise ValueError(
                "technology_id is required"
            )

        if not candidate.score.evaluation_candidate:
            raise ValueError(
                "candidate is not eligible for evaluation"
            )

        if not isinstance(
            request.reason,
            str,
        ) or not request.reason.strip():
            raise ValueError(
                "reason is required"
            )

    @staticmethod
    def _mission_id(
        request: TechnologyEvaluationRequest,
    ) -> str:
        candidate = request.candidate

        canonical = "|".join(
            (
                request.project_id.strip(),
                candidate.technology_id.strip(),
                (
                    candidate.observed_version
                    or ""
                ).strip(),
                str(candidate.score.total),
                request.reason.strip(),
            )
        )

        digest = hashlib.sha256(
            canonical.encode("utf-8")
        ).hexdigest()[:16]

        return (
            "technology-evaluation-"
            f"{digest}"
        )

    def _now_iso(self) -> str:
        if self._clock is not None:
            try:
                now = self._clock.now()

                if isinstance(
                    now,
                    datetime,
                ):
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
