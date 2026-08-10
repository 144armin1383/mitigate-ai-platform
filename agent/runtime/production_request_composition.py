from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent.orchestrator.plan_validator_mission_builder import (
    PlanValidatorMissionBuilder,
)
from agent.orchestrator.planner_queue_flow_coordinator import (
    PlannerQueueFlowCoordinator,
)
from agent.orchestrator.queue_enqueue_coordinator import (
    QueueEnqueueCoordinator,
)
from agent.orchestrator.request_gate_selector import (
    RequestGateSelector,
)
from agent.orchestrator.unified_request_flow_service import (
    UnifiedRequestFlowService,
)
from agent.runtime.production_planner_contract_adapter import (
    ProductionPlannerContractAdapter,
)
from agent.runtime.production_request_queue_adapter import (
    ProductionRequestQueueAdapter,
)


class _SystemClock:
    @staticmethod
    def now() -> str:
        from datetime import datetime, timezone

        return datetime.now(
            timezone.utc
        ).isoformat()


class _EventSink:
    def __init__(self) -> None:
        self._events: list[
            dict[str, Any]
        ] = []

    def emit(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        if len(args) == 1:
            event = args[0]
            if isinstance(event, dict):
                self._events.append(
                    dict(event)
                )
            return

        if len(args) >= 2:
            name = str(args[0])
            payload = args[1]

            if isinstance(
                payload,
                dict,
            ):
                self._events.append(
                    {
                        "type": name,
                        **dict(payload),
                    }
                )
            return

        if kwargs:
            self._events.append(
                dict(kwargs)
            )

    def latest(
        self,
        limit: int,
        project_id: str | None = None,
    ) -> list[dict[str, Any]]:
        events = self._events

        if project_id is not None:
            events = [
                e
                for e in events
                if e.get("project_id")
                == project_id
            ]

        return [
            dict(e)
            for e in events[-limit:]
        ]


class _SingleProductionQueueResolver:
    def __init__(
        self,
        *,
        project_id: str,
        queue_reference: str,
        queue: Any,
    ) -> None:
        self.project_id = project_id
        self.queue_reference = (
            queue_reference
        )
        self.queue = queue

    def resolve(
        self,
        project_id: str,
        queue_reference: str,
    ) -> Any:
        if (
            project_id
            != self.project_id
        ):
            raise ValueError(
                "unknown_project"
            )

        if (
            queue_reference
            != self.queue_reference
        ):
            raise ValueError(
                "unknown_queue"
            )

        return self.queue


@dataclass
class ProductionRequestComposition:
    request_flow: UnifiedRequestFlowService
    request_gate: RequestGateSelector
    planner_queue_flow: PlannerQueueFlowCoordinator
    queue_coordinator: QueueEnqueueCoordinator
    planner: ProductionPlannerContractAdapter
    queue_adapter: ProductionRequestQueueAdapter
    event_sink: Any


def build_production_request_composition(
    *,
    project_id: str,
    queue_reference: str,
    queue_path: str | Path,
    repository_root: str | Path,
    project_registry: Any,
    provider_registry: Any,
    budget_evaluator: Any,
    rate_limiter: Any,
    clock: Any | None = None,
    event_sink: Any | None = None,
) -> ProductionRequestComposition:

    if not isinstance(
        project_id,
        str,
    ) or not project_id.strip():
        raise ValueError(
            "invalid_project_id"
        )

    if not isinstance(
        queue_reference,
        str,
    ) or not queue_reference.strip():
        raise ValueError(
            "invalid_queue_reference"
        )

    clock = clock or _SystemClock()
    event_sink = (
        event_sink
        or _EventSink()
    )

    queue_adapter = (
        ProductionRequestQueueAdapter(
            project_id=project_id,
            queue_path=queue_path,
            repository_root=repository_root,
        )
    )

    queue_resolver = (
        _SingleProductionQueueResolver(
            project_id=project_id,
            queue_reference=queue_reference,
            queue=queue_adapter,
        )
    )

    queue_coordinator = (
        QueueEnqueueCoordinator(
            queue_resolver=queue_resolver,
            clock=clock,
            event_sink=event_sink,
        )
    )

    planner = (
        ProductionPlannerContractAdapter()
    )

    builder = (
        PlanValidatorMissionBuilder()
    )

    planner_queue_flow = (
        PlannerQueueFlowCoordinator(
            planner=planner,
            builder=builder,
            queue_coordinator=queue_coordinator,
            clock=clock,
            event_sink=event_sink,
        )
    )

    request_gate = (
        RequestGateSelector(
            project_registry=project_registry,
            provider_registry=provider_registry,
            budget_evaluator=budget_evaluator,
            rate_limiter=rate_limiter,
            clock=clock,
            event_sink=event_sink,
        )
    )

    request_flow = (
        UnifiedRequestFlowService(
            request_gate_selector=request_gate,
            planner_queue_flow_coordinator=planner_queue_flow,
            clock=clock,
            event_sink=event_sink,
        )
    )

    return ProductionRequestComposition(
        request_flow=request_flow,
        request_gate=request_gate,
        planner_queue_flow=planner_queue_flow,
        queue_coordinator=queue_coordinator,
        planner=planner,
        queue_adapter=queue_adapter,
        event_sink=event_sink,
    )


__all__ = [
    "ProductionRequestComposition",
    "build_production_request_composition",
]
