from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.runtime.background_worker import BackgroundWorker


class IdleQueue:
    def claim(self, worker_id):
        return None

    def complete(self, mission_id):
        raise AssertionError("unexpected complete")

    def retry(self, mission_id):
        raise AssertionError("unexpected retry")

    def fail(self, mission_id):
        raise AssertionError("unexpected fail")

    def block(self, mission_id):
        raise AssertionError("unexpected block")

    def recover_stale(self, worker_id):
        return []


class NoOpController:
    def execute(self, mission):
        raise AssertionError("controller should not execute")


class BackgroundWorkerHeartbeatTests(unittest.TestCase):
    def test_heartbeat_written_in_once_mode(self):
        with tempfile.TemporaryDirectory() as td:
            heartbeat = Path(td) / "worker.heartbeat"

            worker = BackgroundWorker(
                queue=IdleQueue(),
                controller=NoOpController(),
                once=True,
                heartbeat_path=str(heartbeat),
            )

            worker.run()

            self.assertTrue(heartbeat.exists())
            self.assertTrue(heartbeat.read_text(encoding="utf-8").strip())

    def test_heartbeat_parent_directory_is_created(self):
        with tempfile.TemporaryDirectory() as td:
            heartbeat = Path(td) / "runtime" / "worker.heartbeat"

            worker = BackgroundWorker(
                queue=IdleQueue(),
                controller=NoOpController(),
                once=True,
                heartbeat_path=str(heartbeat),
            )

            worker.run()

            self.assertTrue(heartbeat.exists())

    def test_heartbeat_is_optional(self):
        worker = BackgroundWorker(
            queue=IdleQueue(),
            controller=NoOpController(),
            once=True,
        )

        worker.run()

        self.assertFalse(
            any(event["event"] == "heartbeat_failed" for event in worker.events)
        )

    def test_heartbeat_failure_does_not_stop_worker(self):
        with tempfile.TemporaryDirectory() as td:
            blocker = Path(td) / "not-a-directory"
            blocker.write_text("x", encoding="utf-8")

            heartbeat = blocker / "worker.heartbeat"

            worker = BackgroundWorker(
                queue=IdleQueue(),
                controller=NoOpController(),
                once=True,
                heartbeat_path=str(heartbeat),
            )

            worker.run()

            self.assertTrue(
                any(event["event"] == "heartbeat_failed" for event in worker.events)
            )


if __name__ == "__main__":
    unittest.main()
