from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict

from agent.app.application import ApplicationConfig, build_application
from agent.runtime.background_worker import BackgroundWorker
from agent.runtime.mission_queue import MissionQueue


class FakeAutonomousController:
    def __init__(self, final_status: str = "success") -> None:
        self.final_status = final_status
        self.calls = []

    def run(self, mission: Dict[str, Any]) -> Dict[str, Any]:
        self.calls.append(dict(mission))
        return {
            "mission_id": str(mission.get("id")),
            "attempts": 1,
            "final_status": self.final_status,
        }


def make_config(root: Path) -> ApplicationConfig:
    data = root / "data"
    repo = root / "repo"

    data.mkdir(parents=True, exist_ok=True)
    repo.mkdir(parents=True, exist_ok=True)

    return ApplicationConfig(
        data_root=data,
        repository_root=repo,
        default_project_id="default",
        default_branch="develop",
        environment_name="test",
        provider_registry_path=data / "providers.json",
        project_registry_path=data / "projects.json",
        usage_ledger_path=data / "usage.json",
        budget_store_path=data / "budget.json",
        rate_limiter_path=data / "rate.json",
        execution_report_path=data / "reports",
        queue_root=data / "queue",
        event_root=data / "events",
        log_level="INFO",
    )


def persisted_mission_state(queue: MissionQueue, mission_id: str) -> str:
    with open(queue._path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    missions = payload.get("missions", {})

    if isinstance(missions, dict):
        record = missions[mission_id]
    else:
        record = next(
            item for item in missions
            if str(item.get("id")) == mission_id
        )

    return str(record["state"])


class ApplicationRuntimeWiringTests(unittest.TestCase):
    def test_controller_override_builds_real_background_worker(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cfg = make_config(Path(td))
            controller = FakeAutonomousController()

            container = build_application(
                cfg,
                overrides={"autonomous_controller": controller},
            )

            self.assertIs(container.autonomous_controller, controller)
            self.assertIsInstance(container.background_worker, BackgroundWorker)

    def test_build_does_not_start_worker(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cfg = make_config(Path(td))
            controller = FakeAutonomousController()

            container = build_application(
                cfg,
                overrides={"autonomous_controller": controller},
            )

            self.assertEqual(controller.calls, [])
            self.assertEqual(container.background_worker.events, [])

    def test_real_queue_adapter_worker_success_path(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cfg = make_config(Path(td))
            controller = FakeAutonomousController("success")

            container = build_application(
                cfg,
                overrides={"autonomous_controller": controller},
            )

            worker = container.background_worker
            queue = worker._queue

            self.assertIsInstance(queue, MissionQueue)

            queue.enqueue(
                "runtime-success",
                priority=10,
                max_retries=0,
            )

            worker.once = True
            worker.run()

            self.assertEqual(persisted_mission_state(queue, "runtime-success"), "completed")
            self.assertEqual(len(controller.calls), 1)

    def test_real_queue_adapter_worker_failed_path(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cfg = make_config(Path(td))
            controller = FakeAutonomousController("failed")

            container = build_application(
                cfg,
                overrides={"autonomous_controller": controller},
            )

            worker = container.background_worker
            queue = worker._queue

            queue.enqueue(
                "runtime-failed",
                priority=10,
                max_retries=0,
            )

            worker.once = True
            worker.run()

            self.assertEqual(persisted_mission_state(queue, "runtime-failed"), "failed")
            self.assertEqual(len(controller.calls), 1)

    def test_real_queue_adapter_worker_aborted_path(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cfg = make_config(Path(td))
            controller = FakeAutonomousController("aborted")

            container = build_application(
                cfg,
                overrides={"autonomous_controller": controller},
            )

            worker = container.background_worker
            queue = worker._queue

            queue.enqueue(
                "runtime-aborted",
                priority=10,
                max_retries=0,
            )

            worker.once = True
            worker.run()

            self.assertEqual(persisted_mission_state(queue, "runtime-aborted"), "blocked")
            self.assertEqual(len(controller.calls), 1)

    def test_explicit_worker_override_still_wins(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cfg = make_config(Path(td))
            controller = FakeAutonomousController()
            custom_worker = object()

            container = build_application(
                cfg,
                overrides={
                    "autonomous_controller": controller,
                    "background_worker": custom_worker,
                },
            )

            self.assertIs(container.background_worker, custom_worker)
            self.assertIs(container.autonomous_controller, controller)


if __name__ == "__main__":
    unittest.main()
