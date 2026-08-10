from __future__ import annotations

import os
import tempfile
import unittest

from agent.runtime.autonomous_runtime_adapter import AutonomousRuntimeAdapter
from agent.runtime.background_worker import BackgroundWorker
from agent.runtime.mission_queue import MissionQueue


class FakeController:
    def __init__(self, final_status: str, attempts: int = 1) -> None:
        self.final_status = final_status
        self.attempts = attempts
        self.calls = 0

    def run(self, mission):
        self.calls += 1
        return {
            "final_status": self.final_status,
            "attempts": self.attempts,
        }


class RuntimeWorkerIntegrationTests(unittest.TestCase):
    def make_queue(self, *, max_retries: int = 0):
        tmp = tempfile.TemporaryDirectory()
        path = os.path.join(tmp.name, "missions.json")
        queue = MissionQueue(path, default_max_retries=max_retries)
        return tmp, queue

    def test_worker_claim_protocol_accepts_worker_id(self):
        tmp, queue = self.make_queue()
        self.addCleanup(tmp.cleanup)

        queue.enqueue("m1", priority=1)

        mission = queue.claim("worker-a")

        self.assertIsNotNone(mission)
        self.assertEqual(mission["id"], "m1")
        self.assertEqual(queue.get("m1")["state"], "running")

    def test_success_completes_mission(self):
        tmp, queue = self.make_queue()
        self.addCleanup(tmp.cleanup)
        queue.enqueue("m1", priority=1)

        controller = FakeController("success")
        worker = BackgroundWorker(
            queue,
            AutonomousRuntimeAdapter(controller),
            once=True,
            worker_id="worker-a",
        )

        worker.run()

        self.assertEqual(queue.get("m1")["state"], "completed")
        self.assertEqual(controller.calls, 1)

    def test_aborted_controller_result_blocks_running_mission(self):
        tmp, queue = self.make_queue()
        self.addCleanup(tmp.cleanup)
        queue.enqueue("m1", priority=1)

        controller = FakeController("aborted")
        worker = BackgroundWorker(
            queue,
            AutonomousRuntimeAdapter(controller),
            once=True,
        )

        worker.run()

        self.assertEqual(queue.get("m1")["state"], "blocked")
        self.assertEqual(controller.calls, 1)

    def test_failed_controller_result_fails_without_queue_retry_budget(self):
        tmp, queue = self.make_queue(max_retries=0)
        self.addCleanup(tmp.cleanup)
        queue.enqueue("m1", priority=1)

        controller = FakeController("failed", attempts=3)
        worker = BackgroundWorker(
            queue,
            AutonomousRuntimeAdapter(controller),
            once=True,
        )

        worker.run()

        mission = queue.get("m1")
        self.assertEqual(mission["state"], "failed")
        self.assertEqual(mission["attempts_done"], 1)
        self.assertEqual(controller.calls, 1)

    def test_block_transition_from_running_is_atomic_and_supported(self):
        tmp, queue = self.make_queue()
        self.addCleanup(tmp.cleanup)
        queue.enqueue("m1", priority=1)

        claimed = queue.claim("worker-a")
        self.assertIsNotNone(claimed)

        queue.block("m1")

        self.assertEqual(queue.get("m1")["state"], "blocked")

    def test_unknown_adapter_result_fails_closed_to_blocked(self):
        tmp, queue = self.make_queue()
        self.addCleanup(tmp.cleanup)
        queue.enqueue("m1", priority=1)

        controller = FakeController("unexpected")
        worker = BackgroundWorker(
            queue,
            AutonomousRuntimeAdapter(controller),
            once=True,
        )

        worker.run()

        self.assertEqual(queue.get("m1")["state"], "blocked")
        self.assertEqual(controller.calls, 1)


if __name__ == "__main__":
    unittest.main()
