from __future__ import annotations

import os
import signal
import threading
import time
import types
import unittest
import tempfile
from typing import Any, Dict, List, Optional

from agent.runtime.background_worker import BackgroundWorker, cli_main


class FakeMissionQueue:
    """
    In-memory fake mission queue with exclusive claim semantics and dependency handling.
    States: pending -> running -> (completed|failed|blocked) or retry->pending
    """

    def __init__(self, missions: Optional[List[Dict[str, Any]]] = None) -> None:
        # Each mission record: {id, outcome, deps, retries, state, owner, attempts}
        self._lock = threading.Lock()
        self._missions: Dict[str, Dict[str, Any]] = {}
        if missions:
            for m in missions:
                mid = str(m["id"])  # ensure string id deterministically
                self._missions[mid] = {
                    "id": mid,
                    "outcome": m.get("outcome", "success"),
                    "deps": list(m.get("deps", [])),
                    "max_retries": int(m.get("max_retries", 0)),
                    "state": m.get("state", "pending"),
                    "owner": None,
                    "attempts": int(m.get("attempts", 0)),
                }

    def _deps_completed(self, rec: Dict[str, Any]) -> bool:
        for dep_id in rec.get("deps", []):
            dep = self._missions.get(str(dep_id))
            if not dep or dep.get("state") != "completed":
                return False
        return True

    def claim(self, worker_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            # Deterministic order by mission id
            for mid in sorted(self._missions.keys()):
                rec = self._missions[mid]
                if rec["state"] == "pending" and self._deps_completed(rec):
                    rec["state"] = "running"
                    rec["owner"] = worker_id
                    # Return minimal mission view
                    return {"id": rec["id"]}
            return None

    def complete(self, mission_id: str) -> None:
        with self._lock:
            rec = self._missions[mission_id]
            assert rec["state"] == "running"
            rec["state"] = "completed"
            rec["owner"] = None

    def retry(self, mission_id: str) -> None:
        with self._lock:
            rec = self._missions[mission_id]
            assert rec["state"] == "running"
            rec["state"] = "pending"
            rec["owner"] = None
            # No direct retry budget enforcement here; controller decides outcome next attempt

    def fail(self, mission_id: str) -> None:
        with self._lock:
            rec = self._missions[mission_id]
            assert rec["state"] == "running"
            rec["state"] = "failed"
            rec["owner"] = None

    def block(self, mission_id: str) -> None:
        with self._lock:
            rec = self._missions[mission_id]
            assert rec["state"] == "running"
            rec["state"] = "blocked"
            rec["owner"] = None

    def recover_stale(self, worker_id: str) -> List[str]:
        with self._lock:
            recovered: List[str] = []
            for mid in sorted(self._missions.keys()):
                rec = self._missions[mid]
                if rec["state"] == "running":
                    rec["state"] = "pending"
                    rec["owner"] = None
                    recovered.append(mid)
            return recovered

    # Test helpers
    def get_state(self, mission_id: str) -> str:
        return self._missions[str(mission_id)]["state"]

    def increment_attempt(self, mission_id: str) -> int:
        with self._lock:
            self._missions[mission_id]["attempts"] += 1
            return self._missions[mission_id]["attempts"]

    def get_max_retries(self, mission_id: str) -> int:
        return self._missions[mission_id]["max_retries"]

    def get_outcome(self, mission_id: str) -> str:
        return self._missions[mission_id]["outcome"]


class FakeController:
    """
    Fake controller decides outcome deterministically from the queue's mission records.
    - outcome == "success" -> success on first attempt
    - outcome == "retryable" with max_retries N -> returns 'retry' up to N times, then 'exhausted'
    - outcome == "exhausted" -> immediate 'exhausted'
    - outcome == "blocked" -> immediate 'blocked'
    """

    def __init__(self, queue: FakeMissionQueue) -> None:
        self._queue = queue

    def execute(self, mission: Dict[str, Any]) -> str:
        mid = str(mission["id"])
        outcome = self._queue.get_outcome(mid)
        if outcome == "success":
            return "success"
        if outcome == "blocked":
            return "blocked"
        if outcome == "exhausted":
            return "exhausted"
        if outcome == "retryable":
            attempt = self._queue.increment_attempt(mid)
            if attempt <= self._queue.get_max_retries(mid):
                return "retry"
            return "exhausted"
        # Unknown -> treat as retry
        return "retry"


class BackgroundWorkerTests(unittest.TestCase):
    def test_successful_mission_execution(self) -> None:
        queue = FakeMissionQueue([
            {"id": "1", "outcome": "success"},
        ])
        controller = FakeController(queue)
        worker = BackgroundWorker(queue=queue, controller=controller, once=True, poll_interval=0.01)
        worker.run()
        self.assertEqual(queue.get_state("1"), "completed")
        # Check event order: claimed -> completed
        events = [e["event"] for e in worker.events]
        self.assertIn("claimed", events)
        self.assertIn("completed", events)

    def test_retryable_failure_handling(self) -> None:
        queue = FakeMissionQueue([
            {"id": "2", "outcome": "retryable", "max_retries": 1},
        ])
        controller = FakeController(queue)
        # First run should schedule retry
        worker = BackgroundWorker(queue=queue, controller=controller, once=True, poll_interval=0.01)
        worker.run()
        self.assertEqual(queue.get_state("2"), "pending")
        events = [e["event"] for e in worker.events]
        self.assertIn("claimed", events)
        self.assertIn("retrying", events)

    def test_exhausted_failure_handling(self) -> None:
        queue = FakeMissionQueue([
            {"id": "3", "outcome": "exhausted"},
        ])
        controller = FakeController(queue)
        worker = BackgroundWorker(queue=queue, controller=controller, once=True, poll_interval=0.01)
        worker.run()
        self.assertEqual(queue.get_state("3"), "failed")
        events = [e["event"] for e in worker.events]
        self.assertIn("claimed", events)
        self.assertIn("failed", events)

    def test_blocked_security_failure_handling(self) -> None:
        queue = FakeMissionQueue([
            {"id": "4", "outcome": "blocked"},
        ])
        controller = FakeController(queue)
        worker = BackgroundWorker(queue=queue, controller=controller, once=True, poll_interval=0.01)
        worker.run()
        self.assertEqual(queue.get_state("4"), "blocked")
        # Failed event with reason=blocked
        found = False
        for e in worker.events:
            if e["event"] == "failed" and e.get("mission_id") == "4" and e.get("reason") == "blocked":
                found = True
                break
        self.assertTrue(found)

    def test_graceful_shutdown(self) -> None:
        queue = FakeMissionQueue([])
        controller = FakeController(queue)
        worker = BackgroundWorker(queue=queue, controller=controller, once=False, poll_interval=0.05)

        def run_worker() -> None:
            worker.run()

        t = threading.Thread(target=run_worker)
        t.start()

        # Wait for at least one idle emission
        for _ in range(50):
            if any(e["event"] == "idle" for e in worker.events):
                break
            time.sleep(0.01)
        # Request shutdown via direct API to avoid signal side-effects in CI
        worker.request_shutdown()
        t.join(timeout=5.0)
        self.assertFalse(t.is_alive())

        # Verify both idle and shutdown events present and in deterministic order
        events = [e["event"] for e in worker.events]
        self.assertIn("idle", events)
        self.assertIn("shutdown", events)
        # shutdown should occur after at least one idle
        self.assertLess(events.index("idle"), events.index("shutdown"))

    def test_restart_recovery(self) -> None:
        # Preload a running mission (simulating unexpected shutdown)
        queue = FakeMissionQueue([
            {"id": "5", "outcome": "success", "state": "running"},
        ])
        controller = FakeController(queue)
        worker = BackgroundWorker(queue=queue, controller=controller, once=True, poll_interval=0.01)
        # Recovery occurs at startup
        worker.run()
        # Recovery event emitted before processing (if any processing happens later)
        recovered_events = [e for e in worker.events if e["event"] == "recovered" and e.get("mission_id") == "5"]
        self.assertTrue(recovered_events)

    def test_prevent_duplicate_processing(self) -> None:
        queue = FakeMissionQueue([
            {"id": "6", "outcome": "success"},
        ])
        controller_a = FakeController(queue)
        controller_b = FakeController(queue)
        worker_a = BackgroundWorker(queue=queue, controller=controller_a, once=True, worker_id="A", poll_interval=0.01)
        worker_b = BackgroundWorker(queue=queue, controller=controller_b, once=True, worker_id="B", poll_interval=0.01)

        t1 = threading.Thread(target=worker_a.run)
        t2 = threading.Thread(target=worker_b.run)
        t1.start(); t2.start()
        t1.join(timeout=3.0); t2.join(timeout=3.0)
        self.assertFalse(t1.is_alive())
        self.assertFalse(t2.is_alive())

        # Exactly one worker should have claimed and completed; the other was idle
        self.assertEqual(queue.get_state("6"), "completed")
        events_a = [e["event"] for e in worker_a.events]
        events_b = [e["event"] for e in worker_b.events]
        all_events = events_a + events_b
        self.assertIn("claimed", all_events)
        self.assertIn("completed", all_events)
        # Ensure at least one idle from the other worker
        self.assertIn("idle", all_events)

    def test_single_run_mode(self) -> None:
        queue = FakeMissionQueue([])
        controller = FakeController(queue)
        worker = BackgroundWorker(queue=queue, controller=controller, once=True, poll_interval=0.01)
        worker.run()
        # Exactly one idle event expected
        self.assertEqual([e["event"] for e in worker.events].count("idle"), 1)

    def test_idle_polling_behavior(self) -> None:
        queue = FakeMissionQueue([])
        controller = FakeController(queue)
        worker = BackgroundWorker(queue=queue, controller=controller, once=False, poll_interval=0.01, max_idle_cycles=3)
        worker.run()
        events = [e["event"] for e in worker.events]
        self.assertEqual(events, ["idle", "idle", "idle"])  # deterministic order and count

    def test_deterministic_structured_logs(self) -> None:
        queue = FakeMissionQueue([
            {"id": "7", "outcome": "success"},
        ])
        controller = FakeController(queue)
        worker = BackgroundWorker(queue=queue, controller=controller, once=True, poll_interval=0.01)
        worker.run()
        for event in worker.events:
            self.assertIn("event", event)
            self.assertIn("timestamp", event)
            # Timestamp must be a non-empty string in ISO-8601 with Z
            self.assertIsInstance(event["timestamp"], str)
            self.assertTrue(event["timestamp"].endswith("Z"))
            # mission_id present for mission-related events
            if event["event"] in {"claimed", "completed", "retrying", "failed", "recovered"}:
                self.assertIn("mission_id", event)

    def test_cli_parsing(self) -> None:
        # Use a temp directory as a benign queue path
        with tempfile.TemporaryDirectory() as tmp:
            # Expect successful return code 0 in single-run mode (idle)
            rc = cli_main(["--queue-path", tmp, "--once", "--poll-interval", "5"])  # default safe deterministic interval
            self.assertEqual(rc, 0)

    def test_invalid_cli_arguments(self) -> None:
        with self.assertRaises(SystemExit):
            # Missing required --queue-path
            cli_main(["--once"])  # argparse should raise SystemExit
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit):
                # Non-positive poll interval should raise
                cli_main(["--queue-path", tmp, "--once", "--poll-interval", "0"])  # SystemExit
            with self.assertRaises(SystemExit):
                cli_main(["--queue-path", tmp, "--once", "--max-idle-cycles", "-1"])  # SystemExit

    def test_unrelated_files_remain_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            # Create a sentinel file
            path = os.path.join(tmp, "sentinel.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write("keep")
            before_mtime = os.stat(path).st_mtime
            # Run CLI single-run mode which should not modify any files
            rc = cli_main(["--queue-path", tmp, "--once"])  # idle queue
            self.assertEqual(rc, 0)
            after_mtime = os.stat(path).st_mtime
            self.assertEqual(before_mtime, after_mtime)


if __name__ == "__main__":
    unittest.main(verbosity=2)
