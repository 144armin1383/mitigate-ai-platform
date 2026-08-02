import json
import os
import threading
import time
import unittest
from tempfile import TemporaryDirectory

from agent.runtime.mission_queue import MissionQueue, MissionState


class MissionQueueTestCase(unittest.TestCase):
    def _queue(self, tmpdir: str) -> MissionQueue:
        path = os.path.join(tmpdir, "queue.json")
        return MissionQueue(path, default_max_retries=1)

    def test_enqueue_and_deterministic_ordering(self) -> None:
        with TemporaryDirectory() as d:
            q = self._queue(d)
            q.enqueue("C", priority=1)
            q.enqueue("A", priority=5)
            q.enqueue("B", priority=5)

            # Deterministic order: A, B, C
            m = q.claim()
            self.assertIsNotNone(m)
            self.assertEqual(m["id"], "A")
            q.complete("A")

            m = q.claim()
            self.assertIsNotNone(m)
            self.assertEqual(m["id"], "B")
            q.complete("B")

            m = q.claim()
            self.assertIsNotNone(m)
            self.assertEqual(m["id"], "C")
            q.complete("C")

            m = q.claim()
            self.assertIsNone(m)

    def test_dependency_handling(self) -> None:
        with TemporaryDirectory() as d:
            q = self._queue(d)
            q.enqueue("A", priority=1)
            q.enqueue("B", priority=10, dependencies=["A"])

            m = q.claim()
            self.assertEqual(m["id"], "A")
            q.complete("A")

            m = q.claim()
            self.assertEqual(m["id"], "B")
            q.complete("B")

            self.assertIsNone(q.claim())

    def test_circular_dependency_rejection(self) -> None:
        with TemporaryDirectory() as d:
            q = self._queue(d)
            # Two-node cycle detection
            q.enqueue("A", priority=1, dependencies=["B"])
            with self.assertRaises(ValueError):
                q.enqueue("B", priority=1, dependencies=["A"])
            # Ensure only A exists
            listed = [m["id"] for m in q.list()]
            self.assertEqual(listed, ["A"])  # A has higher seq than none others, deterministic

        with TemporaryDirectory() as d2:
            q2 = self._queue(d2)
            # Self cycle
            with self.assertRaises(ValueError):
                q2.enqueue("C", priority=1, dependencies=["C"])

        with TemporaryDirectory() as d3:
            q3 = self._queue(d3)
            q3.enqueue("A", priority=1, dependencies=["B"])
            q3.enqueue("B", priority=1, dependencies=["C"])
            with self.assertRaises(ValueError):
                q3.enqueue("C", priority=1, dependencies=["A"])  # longer cycle A->B->C->A

    def test_duplicate_identifier_rejection(self) -> None:
        with TemporaryDirectory() as d:
            q = self._queue(d)
            q.enqueue("X", priority=3)
            with self.assertRaises(ValueError):
                q.enqueue("X", priority=4)

    def test_atomic_persistence_and_reload(self) -> None:
        with TemporaryDirectory() as d:
            other = os.path.join(d, "other.txt")
            with open(other, "w", encoding="utf-8") as fh:
                fh.write("unchanged")
            q = self._queue(d)
            q.enqueue("A", priority=1)
            q.enqueue("B", priority=2, dependencies=["A"])

            queue_path = os.path.join(d, "queue.json")
            with open(queue_path, "r", encoding="utf-8") as fh:
                content1 = fh.read()

            # Reload in a new instance
            q2 = MissionQueue(queue_path, default_max_retries=1)
            listed = q2.list()
            self.assertEqual({m["id"] for m in listed}, {"A", "B"})

            with open(queue_path, "r", encoding="utf-8") as fh:
                content2 = fh.read()
            self.assertEqual(content1, content2)  # deterministic and unmodified by read-only operations

            # Unrelated file was not modified
            with open(other, "r", encoding="utf-8") as fh:
                self.assertEqual(fh.read(), "unchanged")

    def test_restart_recovery(self) -> None:
        with TemporaryDirectory() as d:
            q = self._queue(d)
            q.enqueue("A", priority=5)
            q.enqueue("B", priority=1)
            p = os.path.join(d, "queue.json")

            # Create a new instance simulating restart
            q2 = MissionQueue(p, default_max_retries=1)
            m = q2.claim()
            self.assertEqual(m["id"], "A")  # higher priority
            q2.complete("A")
            m = q2.claim()
            self.assertEqual(m["id"], "B")

    def test_retry_limits(self) -> None:
        with TemporaryDirectory() as d:
            q = MissionQueue(os.path.join(d, "queue.json"), default_max_retries=1)
            q.enqueue("M", priority=10)

            m = q.claim()
            self.assertEqual(m["id"], "M")
            q.fail("M")
            # After first fail, should be retrying
            self.assertEqual(q.get("M")["state"], MissionState.retrying.value)

            m2 = q.claim()
            self.assertIsNotNone(m2)
            self.assertEqual(m2["id"], "M")
            q.fail("M")  # no retries left -> failed
            self.assertEqual(q.get("M")["state"], MissionState.failed.value)

            self.assertIsNone(q.claim())

    def test_blocked_and_cancelled_missions(self) -> None:
        with TemporaryDirectory() as d:
            q = self._queue(d)
            q.enqueue("N", priority=5)

            q.block("N")
            self.assertEqual(q.get("N")["state"], MissionState.blocked.value)
            self.assertIsNone(q.claim())

            q.resume("N")
            self.assertEqual(q.get("N")["state"], MissionState.pending.value)
            m = q.claim()
            self.assertEqual(m["id"], "N")
            # Cancel running mission is allowed per contract (not explicitly forbidden)
            q.cancel("N")
            self.assertEqual(q.get("N")["state"], MissionState.cancelled.value)
            self.assertIsNone(q.claim())

            with self.assertRaises(ValueError):
                q.cancel("N")  # already cancelled

            # New mission to complete then attempt cancel
            q.enqueue("Z", priority=1)
            m2 = q.claim()
            q.complete("Z")
            with self.assertRaises(ValueError):
                q.cancel("Z")

    def test_concurrent_access_protection(self) -> None:
        with TemporaryDirectory() as d:
            path = os.path.join(d, "queue.json")
            q = MissionQueue(path)

            def worker(prefix: str, count: int) -> None:
                local_q = MissionQueue(path)
                for i in range(count):
                    local_q.enqueue(f"{prefix}-{i}", priority=i % 3)

            t1 = threading.Thread(target=worker, args=("T1", 25), daemon=True)
            t2 = threading.Thread(target=worker, args=("T2", 25), daemon=True)
            t1.start(); t2.start()
            t1.join(timeout=10); t2.join(timeout=10)

            # Ensure all 50 missions persisted without corruption
            listed = MissionQueue(path).list()
            self.assertEqual(len(listed), 50)
            ids = [m["id"] for m in listed]
            self.assertEqual(len(ids), len(set(ids)))

    def test_deterministic_serialization(self) -> None:
        with TemporaryDirectory() as d:
            path = os.path.join(d, "queue.json")
            q = MissionQueue(path)
            q.enqueue("a", priority=1, dependencies=["b"])  # dep not yet enqueued
            q.enqueue("b", priority=2)

            # to_json should be deterministic and equal across instances
            json1 = q.to_json()
            q2 = MissionQueue(path)
            json2 = q2.to_json()
            self.assertEqual(json1, json2)

            # Ensure JSON keys are sorted deterministically (simple check)
            data = json.loads(json1)
            self.assertIn("missions", data)
            # Missions keys sorted lexicographically
            self.assertEqual(list(data["missions"].keys()), sorted(data["missions"].keys()))

    def test_persistence_cycle_rejection_on_load(self) -> None:
        with TemporaryDirectory() as d:
            p = os.path.join(d, "queue.json")
            bad = {
                "version": 1,
                "next_seq": 4,
                "missions": {
                    "A": {
                        "id": "A",
                        "priority": 1,
                        "dependencies": ["B"],
                        "state": "pending",
                        "created_seq": 1,
                        "attempts_done": 0,
                        "max_retries": 0,
                    },
                    "B": {
                        "id": "B",
                        "priority": 1,
                        "dependencies": ["A"],
                        "state": "pending",
                        "created_seq": 2,
                        "attempts_done": 0,
                        "max_retries": 0,
                    },
                },
            }
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(bad, sort_keys=True, separators=(",", ":")))
            with self.assertRaises(ValueError):
                MissionQueue(p)  # loading should reject cycles

    def test_invalid_state_rejection_on_load(self) -> None:
        with TemporaryDirectory() as d:
            p = os.path.join(d, "queue.json")
            bad = {
                "version": 1,
                "next_seq": 2,
                "missions": {
                    "X": {
                        "id": "X",
                        "priority": 1,
                        "dependencies": [],
                        "state": "weird-state",
                        "created_seq": 1,
                        "attempts_done": 0,
                        "max_retries": 0,
                    }
                },
            }
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(bad, sort_keys=True, separators=(",", ":")))
            with self.assertRaises(ValueError):
                MissionQueue(p)

    def test_dequeue_constraints(self) -> None:
        with TemporaryDirectory() as d:
            q = MissionQueue(os.path.join(d, "queue.json"))
            q.enqueue("A", priority=1)
            q.enqueue("B", priority=1, dependencies=["A"])  # B depends on A
            # Cannot dequeue A because B depends on it
            with self.assertRaises(ValueError):
                q.dequeue("A")
            # Dequeue B first
            q.dequeue("B")
            # Now remove A
            q.dequeue("A")
            self.assertEqual(q.list(), [])

    def test_claim_requires_dependencies_completed(self) -> None:
        with TemporaryDirectory() as d:
            q = MissionQueue(os.path.join(d, "queue.json"))
            q.enqueue("A", priority=1)
            q.enqueue("B", priority=10, dependencies=["A", "C"])  # C unknown, so B not claimable
            self.assertEqual(q.claim()["id"], "A")
            q.complete("A")
            self.assertIsNone(q.claim())  # still waiting on C
            q.enqueue("C", priority=5)
            self.assertEqual(q.claim()["id"], "C")
            q.complete("C")
            self.assertEqual(q.claim()["id"], "B")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
