from __future__ import annotations

import sys
from typing import Any

from agent.runtime import background_worker as _background_worker
from agent.runtime.mission_queue import MissionQueue
from agent.runtime.runtime_consolidation_controller import RuntimeConsolidationController


def _construct_runtime_queue_and_controller(
    queue_path: str,
    controller_mode: str = "noop",
) -> tuple[Any, Any]:
    """Reuse the production worker lifecycle while replacing only execution routing.

    The existing systemd command can retain --controller-mode mission-runner;
    this dedicated module interprets that production mode as the consolidated
    MITIGATE controller. Queue semantics, reporting, checkpoints and lifecycle
    hooks remain owned by the existing BackgroundWorker implementation.
    """
    if controller_mode == "mission-runner":
        return MissionQueue(queue_path), RuntimeConsolidationController()
    return _ORIGINAL_CONSTRUCT(queue_path, controller_mode)


_ORIGINAL_CONSTRUCT = _background_worker._construct_queue_and_controller


def cli_main(argv: list[str] | None = None) -> int:
    original = _background_worker._construct_queue_and_controller
    try:
        _background_worker._construct_queue_and_controller = _construct_runtime_queue_and_controller
        return _background_worker.cli_main(argv)
    finally:
        _background_worker._construct_queue_and_controller = original


if __name__ == "__main__":
    sys.exit(cli_main())
