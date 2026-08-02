from __future__ import annotations

import json
import copy
import unittest
from typing import Any, Dict, List, Mapping, Optional, Sequence
from datetime import datetime, timezone

from agent.orchestrator.queue_enqueue_coordinator import QueueEnqueueCoordinator


# ----------------------------- Fakes ---------------------------------

class FakeClock:
    def __init__(self, fixed: Optional[datetime] = None) -> None:
        self._fixed = fixed or datetime(2024, 1, 1, 0, 0, 0, 123456, tzinfo=timezone.utc)

    def now(self) -> datetime:
        return self._fixed


class FakeEventSink:
    def __init__(self) -> None:
        self.events: List[Dict[str, Any]] = []

    def emit(self, event: Mapping[str, Any]) -> None:
        # Store a shallow copy to avoid external mutations
        self.events.append(dict(event))

    def latest(self, limit: int, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if project_id is None:
            return list(self.events[-limit:]) if limit >= 0 else []
        filtered = [e for e in self.events if e.get("project_id") == project_id]
        return filtered[-limit:] if limit >= 0 else []


class FakeQueueResolver:
    def __init__(self) -> None:
        # map of (project_id, queue_reference) -> queue instance
        self._map: Dict[tuple[str, str], Any] = {}

    def register(self, project_id: str, queue_reference: str, queue: Any) -> None:
        self._map[(project_id, queue_reference)] = queue

    def resolve(self, project_id: str, queue_reference: str) -> Any:
        key = (project_id, queue_reference)
        if key not in self._map:
            raise KeyError("queue not found")
        return self._map[key]


# Queues
class AtomicQueue:
    def __init__(self, project_id: str) -> None:
        self.project_id = project_id
        self.called: List[str] = []
        self.last_missions: Optional[Sequence[Mapping[str, Any]]] = None

    def enqueue_batch(self, missions: Sequence[Mapping[str, Any]]) -> List[str]:
        self.called.append("batch")
        self.last_missions = missions
        return [str(m["mission_id"]) for m in missions]


class NonAtomicQueue:
    def __init__(self, project_id: str) -> None:
        self.project_id = project_id
        self.called: List[str] = []
        self.enqueued: List[str] = []
        self.passed_missions: List[Mapping[str, Any]] = []

    def enqueue(self, mission: Mapping[str, Any]) -> Any:
        self.called.append("single")
        self.passed_missions.append(mission)
        mid = str(mission["mission_id"])
        self.enqueued.append(mid)
        return mid


class BothQueue(NonAtomicQueue):
    def enqueue_batch(self, missions: Sequence[Mapping[str, Any]]) -> List[str]:
        self.called.append("batch")
        return [str(m["mission_id"]) for m in missions]


class FailingBatchQueue(AtomicQueue):
    def enqueue_batch(self, missions: Sequence[Mapping[str, Any]]) -> List[str]:
        self.called.append("batch")
        # Return wrong list to simulate failure
        return ["unexpected"]


class RaisingBatchQueue(AtomicQueue):
    def enqueue_batch(self, missions: Sequence[Mapping[str, Any]]) -> List[str]:
        self.called.append("batch")
        raise RuntimeError("boom")


class FailingSingleQueue(NonAtomicQueue):
    def __init__(self, project_id: str, fail_on: Optional[str] = None) -> None:
        super().__init__(project_id)
        self.fail_on = fail_on

    def enqueue(self, mission: Mapping[str, Any]) -> Any:
        self.called.append("single")
        mid = str(mission["mission_id"]) 
        if self.fail_on is None or self.fail_on == mid:
            return False
        self.enqueued.append(mid)
        self.passed_missions.append(mission)
        return mid


class UnsupportedQueue:
    def __init__(self, project_id: str) -> None:
        self.project_id = project_id
        # No supported methods


class BatchAttrNonCallable(NonAtomicQueue):
    def __init__(self, project_id: str) -> None:
        super().__init__(project_id)
        self.enqueue_batch = "not-callable"  # type: ignore[assignment]


# -------------------------- Test Utilities ----------------------------

REQUIRED_FIELDS = (
    "mission_id",
    "project_id",
    "request_id",
    "conversation_id",
    "plan_id",
    "step_id",
    "task_type",
    "provider_id",
    "model_id",
    "dependencies",
    "priority",
    "payload",
    "status",
    "created_at",
)


def make_mission(
    mid: str,
    *,
    project_id: str = "p1",
    deps: Optional[List[str]] = None,
    status: str = "pending",
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    deps = deps or []
    payload = payload or {"x": 1, "path": "/tmp/not-used"}
    m = {
        "mission_id": mid,
        "project_id": project_id,
        "request_id": "r1",
        "conversation_id": "c1",
        "plan_id": "pl1",
        "step_id": "s1",
        "task_type": "op",
        "provider_id": "prov",
        "model_id": "m",
        "dependencies": list(deps),
        "priority": 1,
        "payload": payload,
        "status": status,
        "created_at": "2024-01-01T00:00:00Z",
    }
    assert set(m.keys()) == set(REQUIRED_FIELDS)
    return m


# ----------------------------- Tests ---------------------------------

class TestQueueEnqueueCoordinator(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock()
        self.events = FakeEventSink()
        self.resolver = FakeQueueResolver()
        self.coordinator = QueueEnqueueCoordinator(self.resolver, self.clock, self.events)

    def test_success_atomic_batch_enqueue(self) -> None:
        q = AtomicQueue(project_id="p1")
        self.resolver.register("p1", "default", q)
        missions = [
            make_mission("m1"),
            make_mission("m2", deps=["m1"]),
        ]
        result = self.coordinator.enqueue("p1", "default", missions)
        self.assertTrue(result["accepted"]) 
        self.assertTrue(result["atomic"]) 
        self.assertEqual(result["mission_ids"], ["m1", "m2"]) 
        self.assertEqual(result["enqueued_count"], 2) 
        self.assertIsNone(result["blocked_reason"]) 
        types = [e["type"] for e in self.events.events]
        self.assertIn("queue_batch_started", types)
        self.assertIn("queue_batch_completed", types)
        self.assertIn("enqueue_completed", types)

    def test_success_non_atomic_enqueue(self) -> None:
        q = NonAtomicQueue(project_id="p1")
        self.resolver.register("p1", "q1", q)
        missions = [make_mission("m1"), make_mission("m2", deps=["m1"])]
        result = self.coordinator.enqueue("p1", "q1", missions)
        self.assertTrue(result["accepted"]) 
        self.assertFalse(result["atomic"]) 
        self.assertEqual(result["mission_ids"], ["m1", "m2"]) 
        self.assertEqual(q.enqueued, ["m1", "m2"]) 
        types = [e["type"] for e in self.events.events]
        self.assertIn("queue_individual_started", types)
        self.assertEqual(types.count("mission_enqueued"), 2)

    def test_atomic_method_preferred_when_available(self) -> None:
        q = BothQueue(project_id="p1")
        self.resolver.register("p1", "q2", q)
        missions = [make_mission("m1")]
        result = self.coordinator.enqueue("p1", "q2", missions)
        self.assertTrue(result["accepted"]) 
        self.assertIn("batch", q.called)
        # Ensure no single call when batch succeeds
        self.assertNotIn("single", q.called)

    def test_non_callable_batch_attribute_ignored(self) -> None:
        q = BatchAttrNonCallable(project_id="p1")
        self.resolver.register("p1", "q3", q)
        missions = [make_mission("m1")]
        result = self.coordinator.enqueue("p1", "q3", missions)
        self.assertTrue(result["accepted"]) 
        # Non-callable attribute should be ignored and single used
        self.assertIn("single", q.called)

    def test_unsupported_queue_interface(self) -> None:
        q = UnsupportedQueue(project_id="p1")
        self.resolver.register("p1", "q4", q)
        missions = [make_mission("m1")]
        result = self.coordinator.enqueue("p1", "q4", missions)
        self.assertFalse(result["accepted"]) 
        self.assertEqual(result["blocked_reason"], "unsupported_queue_interface")

    def test_queue_resolution_failure(self) -> None:
        # Do not register queue
        missions = [make_mission("m1")]
        result = self.coordinator.enqueue("p1", "missing", missions)
        self.assertFalse(result["accepted"]) 
        self.assertEqual(result["blocked_reason"], "queue_resolution_failed")
        types = [e["type"] for e in self.events.events]
        self.assertIn("queue_resolution_started", types)
        self.assertIn("queue_resolution_failed", types)

    def test_batch_enqueue_failure(self) -> None:
        q = FailingBatchQueue(project_id="p1")
        self.resolver.register("p1", "q5", q)
        missions = [make_mission("m1"), make_mission("m2", deps=["m1"])]
        result = self.coordinator.enqueue("p1", "q5", missions)
        self.assertFalse(result["accepted"]) 
        self.assertTrue(result["atomic"]) 
        self.assertEqual(result["blocked_reason"], "queue_failed")
        self.assertEqual(result["mission_ids"], [])

    def test_batch_enqueue_exception_failure(self) -> None:
        q = RaisingBatchQueue(project_id="p1")
        self.resolver.register("p1", "q6", q)
        missions = [make_mission("m1"), make_mission("m2", deps=["m1"])]
        result = self.coordinator.enqueue("p1", "q6", missions)
        self.assertFalse(result["accepted"]) 
        self.assertEqual(result["blocked_reason"], "queue_failed")
        types = [e["type"] for e in self.events.events]
        self.assertIn("queue_failed", types)

    def test_individual_enqueue_failure_first(self) -> None:
        q = FailingSingleQueue(project_id="p1", fail_on="m1")
        self.resolver.register("p1", "q7", q)
        missions = [make_mission("m1"), make_mission("m2", deps=["m1"])]
        result = self.coordinator.enqueue("p1", "q7", missions)
        self.assertFalse(result["accepted"]) 
        self.assertEqual(result["blocked_reason"], "queue_failed")
        self.assertEqual(result["mission_ids"], [])

    def test_partial_enqueue_reporting(self) -> None:
        q = FailingSingleQueue(project_id="p1", fail_on="m2")
        # Override to succeed on m1, fail on m2
        def enqueue(m: Mapping[str, Any]) -> Any:  # type: ignore[override]
            mid = str(m["mission_id"]) 
            if mid == "m2":
                return False
            q.passed_missions.append(m)
            q.enqueued.append(mid)
            return mid
        q.enqueue = enqueue  # type: ignore[assignment]
        self.resolver.register("p1", "q8", q)
        missions = [make_mission("m1"), make_mission("m2", deps=["m1"]), make_mission("m3", deps=["m2"])]
        result = self.coordinator.enqueue("p1", "q8", missions)
        self.assertFalse(result["accepted"]) 
        self.assertEqual(result["blocked_reason"], "partial_enqueue")
        self.assertEqual(result["mission_ids"], ["m1"]) 
        types = [e["type"] for e in self.events.events]
        self.assertIn("partial_enqueue", types)

    def test_mission_order_preserved(self) -> None:
        q = NonAtomicQueue(project_id="p1")
        self.resolver.register("p1", "q9", q)
        missions = [make_mission("a"), make_mission("b", deps=["a"]), make_mission("c", deps=["a", "b"])]
        _ = self.coordinator.enqueue("p1", "q9", missions)
        self.assertEqual(q.enqueued, ["a", "b", "c"]) 

    def test_mission_identifiers_preserved(self) -> None:
        q = NonAtomicQueue(project_id="p1")
        self.resolver.register("p1", "q10", q)
        missions = [make_mission("x1"), make_mission("x2", deps=["x1"])]
        _ = self.coordinator.enqueue("p1", "q10", missions)
        self.assertEqual(q.enqueued, ["x1", "x2"]) 

    def test_dependencies_preserved(self) -> None:
        q = NonAtomicQueue(project_id="p1")
        self.resolver.register("p1", "q11", q)
        missions = [make_mission("d1"), make_mission("d2", deps=["d1"])]
        _ = self.coordinator.enqueue("p1", "q11", missions)
        # Ensure original dependency is intact in passed mission objects
        self.assertEqual(q.passed_missions[1]["dependencies"], ["d1"]) 

    def test_duplicate_mission_rejection(self) -> None:
        q = NonAtomicQueue(project_id="p1")
        self.resolver.register("p1", "q12", q)
        missions = [make_mission("dup"), make_mission("dup")]  # duplicate ids
        result = self.coordinator.enqueue("p1", "q12", missions)
        self.assertFalse(result["accepted"]) 
        self.assertEqual(result["blocked_reason"], "invalid_enqueue_request")

    def test_unknown_dependency_rejection(self) -> None:
        q = NonAtomicQueue(project_id="p1")
        self.resolver.register("p1", "q13", q)
        missions = [make_mission("m1", deps=["missing"]) , make_mission("m2", deps=["m1"])]
        result = self.coordinator.enqueue("p1", "q13", missions)
        self.assertFalse(result["accepted"]) 
        self.assertEqual(result["blocked_reason"], "invalid_enqueue_request")

    def test_self_dependency_rejection(self) -> None:
        q = NonAtomicQueue(project_id="p1")
        self.resolver.register("p1", "q14", q)
        missions = [make_mission("m1", deps=["m1"]) , make_mission("m2", deps=["m1"])]
        result = self.coordinator.enqueue("p1", "q14", missions)
        self.assertFalse(result["accepted"]) 
        self.assertEqual(result["blocked_reason"], "invalid_enqueue_request")

    def test_dependency_order_violation_rejection(self) -> None:
        q = NonAtomicQueue(project_id="p1")
        self.resolver.register("p1", "q15", q)
        # m2 depends on m1 but appears earlier
        missions = [make_mission("m2", deps=["m1"]) , make_mission("m1")]
        result = self.coordinator.enqueue("p1", "q15", missions)
        self.assertFalse(result["accepted"]) 
        self.assertEqual(result["blocked_reason"], "invalid_enqueue_request")

    def test_cross_project_mission_rejection(self) -> None:
        q = NonAtomicQueue(project_id="p1")
        self.resolver.register("p1", "q16", q)
        missions = [make_mission("m1", project_id="p2")]  # different project within mission
        result = self.coordinator.enqueue("p1", "q16", missions)
        self.assertFalse(result["accepted"]) 
        self.assertEqual(result["blocked_reason"], "cross_project_reference")

    def test_queue_reference_project_mismatch(self) -> None:
        # Register queue with another project_id value to simulate mismatch
        q = NonAtomicQueue(project_id="other_project")
        self.resolver.register("p1", "q17", q)
        missions = [make_mission("m1")]
        result = self.coordinator.enqueue("p1", "q17", missions)
        self.assertFalse(result["accepted"]) 
        self.assertEqual(result["blocked_reason"], "cross_project_reference")

    def test_pending_status_enforcement(self) -> None:
        q = NonAtomicQueue(project_id="p1")
        self.resolver.register("p1", "q18", q)
        missions = [make_mission("m1", status="running")]
        result = self.coordinator.enqueue("p1", "q18", missions)
        self.assertFalse(result["accepted"]) 
        self.assertEqual(result["blocked_reason"], "invalid_enqueue_request")

    def test_input_objects_not_mutated(self) -> None:
        q = NonAtomicQueue(project_id="p1")
        self.resolver.register("p1", "q19", q)
        missions = [make_mission("m1"), make_mission("m2", deps=["m1"]) ]
        before = copy.deepcopy(missions)
        _ = self.coordinator.enqueue("p1", "q19", missions)
        self.assertEqual(before, missions)

    def test_deterministic_result_serialization(self) -> None:
        q = NonAtomicQueue(project_id="p1")
        self.resolver.register("p1", "q20", q)
        missions = [make_mission("m1"), make_mission("m2", deps=["m1"]) ]
        result = self.coordinator.enqueue("p1", "q20", missions)
        # Deterministic JSON serialization (key order should reflect insertion)
        s1 = json.dumps(result, separators=(",", ":"))
        s2 = json.dumps(result, separators=(",", ":"))
        self.assertEqual(s1, s2)

    def test_result_redaction(self) -> None:
        q = NonAtomicQueue(project_id="p1")
        self.resolver.register("p1", "q21", q)
        missions = [make_mission("m1", payload={"secret": "do-not-leak"})]
        result = self.coordinator.enqueue("p1", "q21", missions)
        # Ensure result does not include payload data
        self.assertNotIn("payload", json.dumps(result))
        self.assertTrue(result["accepted"]) 

    def test_event_redaction(self) -> None:
        q = NonAtomicQueue(project_id="p1")
        self.resolver.register("p1", "q22", q)
        missions = [make_mission("m1", payload={"secret": "do-not-leak"})]
        _ = self.coordinator.enqueue("p1", "q22", missions)
        # Events must not contain payload or non-allowed fields
        for e in self.events.events:
            s = json.dumps(e)
            self.assertNotIn("payload", s)
            # Only allowed keys present
            for k in e.keys():
                self.assertIn(k, QueueEnqueueCoordinator._ALLOWED_EVENT_KEYS)

    def test_latest_events_redaction_and_filter(self) -> None:
        q = NonAtomicQueue(project_id="p1")
        self.resolver.register("p1", "qa", q)
        missions = [make_mission("m1"), make_mission("m2", deps=["m1"]) ]
        _ = self.coordinator.enqueue("p1", "qa", missions)
        latest = self.coordinator.latest_events(5, project_id="p1")
        self.assertIsInstance(latest, list)
        for e in latest:
            for k in e.keys():
                self.assertIn(k, QueueEnqueueCoordinator._ALLOWED_EVENT_KEYS)
        # Ensure project filter works
        none = self.coordinator.latest_events(5, project_id="unknown")
        self.assertEqual(none, [])

    def test_status(self) -> None:
        st = self.coordinator.status()
        self.assertTrue(st.get("healthy"))
        self.assertIn("timestamp", st)


if __name__ == "__main__":
    unittest.main()
