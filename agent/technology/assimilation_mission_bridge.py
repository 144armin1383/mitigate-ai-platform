from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from agent.resilience.replacement_mission_bridge import (
    NativeReplacementMissionBridge,
    NativeReplacementRequest,
)
from agent.technology.registry import (
    AssimilationState,
    EvaluationState,
    TechnologyRegistry,
    TechnologyState,
)


ASSIMILATE_OUTCOME = "assimilate_candidate"


@dataclass(frozen=True)
class NativeAssimilationRequest:
    project_id: str
    technology_id: str
    outcome: str
    capabilities: Sequence[str]
    reason: str


class NativeAssimilationMissionBridge:
    """
    Convert an approved technology-evaluation outcome into normal
    MITIGATE-native replacement missions.

    Architectural rules:
    - MITIGATE remains the system of record.
    - Only an explicit assimilate_candidate outcome is accepted.
    - External technology is reference material only.
    - No external runtime dependency is introduced.
    - Existing NativeReplacementMissionBridge is reused.
    - Existing mission queue/pipeline is reused.
    - This bridge does not execute missions.
    """

    def __init__(
        self,
        *,
        registry: TechnologyRegistry,
        replacement_bridge: NativeReplacementMissionBridge,
    ) -> None:
        self._registry = registry
        self._replacement_bridge = replacement_bridge

    def create_missions(
        self,
        request: NativeAssimilationRequest,
    ) -> list[dict[str, Any]]:
        capabilities = self._validate_request(
            request
        )

        record = self._registry.get(
            request.technology_id
        )

        missions: list[dict[str, Any]] = []

        for capability in capabilities:
            replacement_request = (
                NativeReplacementRequest(
                    capability=capability,
                    project_id=request.project_id.strip(),
                    reason=request.reason.strip(),
                    source_technology=record.technology_id,
                )
            )

            missions.append(
                self._replacement_bridge.create_mission(
                    replacement_request
                )
            )

        return missions

    def plan(
        self,
        request: NativeAssimilationRequest,
    ) -> list[dict[str, Any]]:
        missions = self.create_missions(
            request
        )

        record = self._registry.get(
            request.technology_id
        )

        metadata = dict(record.metadata)

        metadata["assimilation"] = {
            "project_id": request.project_id.strip(),
            "outcome": ASSIMILATE_OUTCOME,
            "reason": request.reason.strip(),
            "capabilities": [
                mission["step_id"]
                for mission in missions
            ],
            "mission_ids": [
                mission["mission_id"]
                for mission in missions
            ],
            "native_only": True,
            "external_runtime_dependency_allowed": False,
        }

        self._registry.update(
            request.technology_id,
            state=TechnologyState.ASSIMILATING,
            assimilation_state=AssimilationState.PLANNED,
            external_runtime_required=False,
            metadata=metadata,
        )

        return missions

    def enqueue(
        self,
        request: NativeAssimilationRequest,
    ) -> list[Mapping[str, Any]]:
        missions = self.plan(
            request
        )

        results: list[Mapping[str, Any]] = []

        for mission in missions:
            replacement_request = (
                NativeReplacementRequest(
                    capability=mission["step_id"],
                    project_id=request.project_id.strip(),
                    reason=request.reason.strip(),
                    source_technology=(
                        request.technology_id.strip()
                    ),
                )
            )

            results.append(
                self._replacement_bridge.enqueue(
                    replacement_request
                )
            )

        self._registry.update(
            request.technology_id,
            assimilation_state=AssimilationState.IN_PROGRESS,
        )

        return results

    def mark_native_available(
        self,
        technology_id: str,
        capability: str,
    ) -> None:
        technology_key = str(
            technology_id
        ).strip()

        capability_key = str(
            capability
        ).strip()

        if not technology_key:
            raise ValueError(
                "technology_id is required"
            )

        if not capability_key:
            raise ValueError(
                "capability is required"
            )

        record = self._registry.get(
            technology_key
        )

        adopted = list(
            record.adopted_capabilities
        )

        if capability_key not in adopted:
            adopted.append(
                capability_key
            )

        adopted.sort()

        self._registry.update(
            technology_key,
            adopted_capabilities=adopted,
            native_replacement_available=True,
            assimilation_state=(
                AssimilationState.NATIVE_AVAILABLE
            ),
            external_runtime_required=False,
        )

    def complete(
        self,
        technology_id: str,
    ) -> None:
        technology_key = str(
            technology_id
        ).strip()

        if not technology_key:
            raise ValueError(
                "technology_id is required"
            )

        record = self._registry.get(
            technology_key
        )

        expected = {
            str(item).strip()
            for item in record.capabilities
            if str(item).strip()
        }

        adopted = {
            str(item).strip()
            for item in record.adopted_capabilities
            if str(item).strip()
        }

        if not expected:
            raise ValueError(
                "technology has no capabilities"
            )

        if not expected.issubset(adopted):
            raise ValueError(
                "native capabilities are incomplete"
            )

        self._registry.update(
            technology_key,
            state=TechnologyState.NATIVE_REPLACED,
            assimilation_state=AssimilationState.COMPLETE,
            native_replacement_available=True,
            external_runtime_required=False,
        )

    def _validate_request(
        self,
        request: NativeAssimilationRequest,
    ) -> list[str]:
        if not isinstance(
            request.project_id,
            str,
        ) or not request.project_id.strip():
            raise ValueError(
                "project_id is required"
            )

        if not isinstance(
            request.technology_id,
            str,
        ) or not request.technology_id.strip():
            raise ValueError(
                "technology_id is required"
            )

        if (
            str(request.outcome).strip()
            != ASSIMILATE_OUTCOME
        ):
            raise ValueError(
                "evaluation outcome does not permit assimilation"
            )

        if not isinstance(
            request.reason,
            str,
        ) or not request.reason.strip():
            raise ValueError(
                "reason is required"
            )

        record = self._registry.get(
            request.technology_id.strip()
        )

        if (
            record.evaluation_state
            != EvaluationState.PASSED
        ):
            raise ValueError(
                "technology evaluation has not passed"
            )

        if record.external_runtime_required:
            raise ValueError(
                "external runtime dependency is not permitted"
            )

        known = {
            str(item).strip()
            for item in record.capabilities
            if str(item).strip()
        }

        normalized: list[str] = []

        for raw in request.capabilities:
            capability = str(raw).strip()

            if not capability:
                raise ValueError(
                    "capability is required"
                )

            if capability not in known:
                raise ValueError(
                    "unknown technology capability: "
                    f"{capability}"
                )

            if capability not in normalized:
                normalized.append(
                    capability
                )

        if not normalized:
            raise ValueError(
                "at least one capability is required"
            )

        normalized.sort()

        return normalized
