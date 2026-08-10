from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path

from agent.runtime.background_worker import BackgroundWorker
from agent.runtime.mission_queue import MissionQueue, MissionState


class SuccessController:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def execute(self, mission):
        self.calls.append(str(mission["id"]))
        return {"status": "success"}


class RuntimeRestartRecoveryTests(unittest.TestCase):

    def make_queue(self, root: str) -> MissionQueue:
        return MissionQueue(str(Path(root) / "missions.json"))

    def test_running_mission_is_recovered_after_restart(self):
        with tempfile.TemporaryDirectory() as td:
            q1 = self.make_queue(td)
            q1.enqueue("mission-1", priority=10, max_retries=2)

            claimed = q1.claim("worker-old")
            self.assertIsNotNone(claimed)
            self.assertEqual(
                q1.get("mission-1")["state"],
                MissionState.running.value,
            )

            # New queue instance simulates process restart.
            q2 = self.make_queue(td)
            recovered = q2.recover_stale("worker-new")

            self.assertEqual(recovered, ["mission-1"])

            mission = q2.get("mission-1")
            self.assertEqual(
                mission["state"],
                MissionState.retrying.value,
            )
            self.assertEqual(mission["attempts_done"], 0)
            self.assertEqual(mission["max_retries"], 2)

    def test_recovery_does_not_consume_existing_retry_budget(self):
        with tempfile.TemporaryDirectory() as td:
            q1 = self.make_queue(td)
            q1.enqueue("mission-1", priority=10, max_retries=2)

            q1.claim("worker-a")
            q1.fail("mission-1")

            after_failure = q1.get("mission-1")
            self.assertEqual(after_failure["attempts_done"], 1)
            self.assertEqual(
                after_failure["state"],
                MissionState.retrying.value,
            )

            q1.claim("worker-a")
            self.assertEqual(
                q1.get("mission-1")["state"],
                MissionState.running.value,
            )

            q2 = self.make_queue(td)
            recovered = q2.recover_stale("worker-b")

            self.assertEqual(recovered, ["mission-1"])

            after_recovery = q2.get("mission-1")
            self.assertEqual(after_recovery["attempts_done"], 1)
            self.assertEqual(after_recovery["max_retries"], 2)
            self.assertEqual(
                after_recovery["state"],
                MissionState.retrying.value,
            )

    def test_terminal_states_are_never_recovered(self):
        with tempfile.TemporaryDirectory() as td:
            q = self.make_queue(td)

            q.enqueue("completed", priority=5)
            q.claim("w")
            q.complete("completed")

            q.enqueue("failed", priority=4, max_retries=0)
            q.claim("w")
            q.fail("failed")

            q.enqueue("blocked", priority=3)
            q.block("blocked")

            q.enqueue("cancelled", priority=2)
            q.cancel("cancelled")

            before = {
                mid: q.get(mid)["state"]
                for mid in (
                    "completed",
                    "failed",
                    "blocked",
                    "cancelled",
                )
            }

            recovered = q.recover_stale("new-worker")

            self.assertEqual(recovered, [])

            after = {
                mid: q.get(mid)["state"]
                for mid in before
            }
            self.assertEqual(after, before)

    def test_pending_and_retrying_states_are_not_modified(self):
        with tempfile.TemporaryDirectory() as td:
            q = self.make_queue(td)

            # First put one mission into retrying state.
            q.enqueue("retrying", priority=1, max_retries=2)
            claimed = q.claim("w")
            self.assertIsNotNone(claimed)
            self.assertEqual(claimed["id"], "retrying")
            q.fail("retrying")

            # Add a separate pending mission afterwards so claim ordering
            # cannot interfere with construction of the retrying state.
            q.enqueue("pending", priority=2)

            recovered = q.recover_stale("new-worker")

            self.assertEqual(recovered, [])
            self.assertEqual(
                q.get("pending")["state"],
                MissionState.pending.value,
            )
            self.assertEqual(
                q.get("retrying")["state"],
                MissionState.retrying.value,
            )
            self.assertEqual(
                q.get("retrying")["attempts_done"],
                1,
            )

    def test_recovery_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            q = self.make_queue(td)
            q.enqueue("mission-1", priority=1, max_retries=2)
            q.claim("old-worker")

            first = q.recover_stale("new-worker")
            second = q.recover_stale("new-worker")

            self.assertEqual(first, ["mission-1"])
            self.assertEqual(second, [])
            self.assertEqual(
                q.get("mission-1")["state"],
                MissionState.retrying.value,
            )
            self.assertEqual(
                q.get("mission-1")["attempts_done"],
                0,
            )

    def test_worker_startup_recovers_then_executes_mission(self):
        with tempfile.TemporaryDirectory() as td:
            q1 = self.make_queue(td)
            q1.enqueue("mission-1", priority=1, max_retries=2)
            q1.claim("dead-worker")

            q2 = self.make_queue(td)
            controller = SuccessController()

            worker = BackgroundWorker(
                q2,
                controller,
                once=True,
                worker_id="replacement-worker",
                poll_interval=0.001,
            )
            worker.run()

            self.assertEqual(controller.calls, ["mission-1"])
            self.assertEqual(
                q2.get("mission-1")["state"],
                MissionState.completed.value,
            )
            self.assertEqual(
                q2.get("mission-1")["attempts_done"],
                0,
            )

            events = [
                (e["event"], e.get("mission_id"))
                for e in worker.events
            ]
            self.assertIn(("recovered", "mission-1"), events)
            self.assertIn(("claimed", "mission-1"), events)
            self.assertIn(("completed", "mission-1"), events)

    def test_concurrent_recovery_only_recovers_once(self):
        with tempfile.TemporaryDirectory() as td:
            q = self.make_queue(td)
            q.enqueue("mission-1", priority=1)
            q.claim("dead-worker")

            results: list[list[str]] = []
            results_lock = threading.Lock()

            def recover(worker_id: str) -> None:
                local_queue = self.make_queue(td)
                value = local_queue.recover_stale(worker_id)
                with results_lock:
                    results.append(value)

            t1 = threading.Thread(target=recover, args=("worker-a",))
            t2 = threading.Thread(target=recover, args=("worker-b",))

            t1.start()
            t2.start()
            t1.join()
            t2.join()

            flattened = [
                mission_id
                for result in results
                for mission_id in result
            ]

            self.assertEqual(flattened, ["mission-1"])

            final_queue = self.make_queue(td)
            self.assertEqual(
                final_queue.get("mission-1")["state"],
                MissionState.retrying.value,
            )

    def test_recovered_mission_can_only_be_claimed_once(self):
        with tempfile.TemporaryDirectory() as td:
            q = self.make_queue(td)
            q.enqueue("mission-1", priority=1)
            q.claim("dead-worker")

            restarted = self.make_queue(td)
            restarted.recover_stale("replacement")

            claims = []
            claims_lock = threading.Lock()

            def claim(worker_id: str) -> None:
                local_queue = self.make_queue(td)
                mission = local_queue.claim(worker_id)
                with claims_lock:
                    claims.append(mission)

            t1 = threading.Thread(target=claim, args=("worker-a",))
            t2 = threading.Thread(target=claim, args=("worker-b",))

            t1.start()
            t2.start()
            t1.join()
            t2.join()

            actual_claims = [
                mission
                for mission in claims
                if mission is not None
            ]

            self.assertEqual(len(actual_claims), 1)
            self.assertEqual(
                actual_claims[0]["id"],
                "mission-1",
            )


if __name__ == "__main__":
    unittest.main()
