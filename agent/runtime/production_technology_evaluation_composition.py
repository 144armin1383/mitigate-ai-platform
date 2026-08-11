from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agent.runtime.production_request_queue_adapter import (
    ProductionRequestQueueAdapter,
)
from agent.runtime.production_technology_evaluation_coordinator import (
    ProductionTechnologyEvaluationCoordinator,
)
from agent.technology.evaluation_mission_bridge import (
    TechnologyEvaluationMissionBridge,
)


@dataclass(frozen=True)
class ProductionTechnologyEvaluationComposition:
    request_queue_adapter: (
        ProductionRequestQueueAdapter
    )
    coordinator: (
        ProductionTechnologyEvaluationCoordinator
    )
    bridge: (
        TechnologyEvaluationMissionBridge
    )


def build_production_technology_evaluation_composition(
    *,
    project_id: str,
    queue_path: str | Path,
    repository_root: str | Path,
    queue_reference: str = "missions",
) -> ProductionTechnologyEvaluationComposition:
    """
    Build the MITIGATE-native technology evaluation enqueue path.

    The existing production request adapter remains responsible for:
    - mission definition materialization
    - payload safety validation
    - queue persistence

    No external technology runtime is required.
    """

    adapter = (
        ProductionRequestQueueAdapter(
            project_id=project_id,
            queue_path=queue_path,
            repository_root=repository_root,
        )
    )

    coordinator = (
        ProductionTechnologyEvaluationCoordinator(
            request_queue_adapter=adapter,
            project_id=project_id,
            queue_reference=queue_reference,
        )
    )

    bridge = (
        TechnologyEvaluationMissionBridge(
            queue_coordinator=coordinator,
            queue_reference=queue_reference,
        )
    )

    return (
        ProductionTechnologyEvaluationComposition(
            request_queue_adapter=adapter,
            coordinator=coordinator,
            bridge=bridge,
        )
    )


__all__ = [
    "ProductionTechnologyEvaluationComposition",
    "build_production_technology_evaluation_composition",
]
