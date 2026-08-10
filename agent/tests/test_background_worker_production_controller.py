from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.runtime.background_worker import (
    _NoOpController,
    _construct_queue_and_controller,
)
from agent.runtime.mission_queue import MissionQueue
from agent.runtime.production_mission_controller import (
    ProductionMissionController,
)


class BackgroundWorkerProductionControllerTests(unittest.TestCase):

    def test_production_mode_uses_real_queue_and_controller(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            queue_path = str(
                Path(td) / "missions.json"
            )

            queue, controller = _construct_queue_and_controller(
                queue_path,
                controller_mode="mission-runner",
            )

            self.assertIsInstance(queue, MissionQueue)
            self.assertIsInstance(
                controller,
                ProductionMissionController,
            )

    def test_default_mode_remains_noop_for_maintenance(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            _, controller = _construct_queue_and_controller(
                str(Path(td) / "missions.json"),
            )

            self.assertIsInstance(
                controller,
                _NoOpController,
            )

    def test_unknown_controller_mode_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                _construct_queue_and_controller(
                    str(Path(td) / "missions.json"),
                    controller_mode="unknown",
                )


if __name__ == "__main__":
    unittest.main()
