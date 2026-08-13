from __future__ import annotations

from agent.runtime import production_request_composition
from agent.runtime import production_request_queue_adapter
from agent.runtime import production_runtime_api
from agent.runtime.autonomous_mission_queue import AutonomousMissionQueue
from agent.runtime.isolated_request_queue_adapter import (
    IsolatedProductionRequestQueueAdapter,
)


# Keep the existing request governance path intact while replacing generic
# persistence with isolated runtime state and a bounded retry policy.
production_request_queue_adapter.MissionQueue = AutonomousMissionQueue
production_request_composition.ProductionRequestQueueAdapter = (
    IsolatedProductionRequestQueueAdapter
)
production_runtime_api.MissionQueue = AutonomousMissionQueue

from agent.runtime.production_runtime_api import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
