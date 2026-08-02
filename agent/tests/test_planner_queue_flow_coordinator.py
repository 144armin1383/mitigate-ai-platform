from __future__ import annotations

import unittest
from typing import Any, Dict, List, Mapping

from agent.orchestrator.planner_queue_flow_coordinator import (
    PlannerQueueFlowCoordinator,
)


class FakeClock:
    def __init__(self, now_value: str = "2024-01-01T00:00:00Z") -> None:
        self._now = now_value

    def now(self) -> str:
        return self._now


class FakeEventSink:
    def __init__(self) -> None:
        self.events: List[Dict[str, Any]] = []

    def emit(self, name: str, payload: Mapping[str, Any]) -> None:
        # Ensure no sensitive fields are logged
        assert "user_message" not in payload
        assert "upload_ids" not in payload
        self.events.append({"event": name, "payload": dict(payload)})


class FakePlanner:
    def __init__(self, plan_result: Any = None, should_raise: bool = False) -> None:
        self._plan_result = plan_result
        self._should_raise = should_raise
        self.last_input: Dict[str, Any] | None = None

    def plan(self, planner_input: Mapping[str, Any]) -> Any:
        self.last_input = dict(planner_input)
        if self._should_raise:
            raise RuntimeError("planner error")
        return self._plan_result


class FakeBuilder:
    def __init__(self, ok: bool = True, missions: List[Dict[str, Any]] | None = None, plan_id: str = "plan-1", plan_summary: str = "summary") -> None:
        self._ok = ok
        self._missions = missions if missions is not None else []
        self._plan_id = plan_id
        self._plan_summary = plan_summary
        self.last_approved_request: Mapping[str, Any] | None = None
        self.should_raise: bool = False

    def validate_and_build(self, plan: Any, approved_request: Mapping[str, Any]) -> Mapping[str, Any]:
        self.last_approved_request = dict(approved_request)
        if self.should_raise:
            raise RuntimeError("builder failed")
        if not self._ok:
            return {"ok": False, "reason": "invalid"}
        return {
            "ok": True,
            "missions": list(self._missions),
            "plan_id": self._plan_id,
            "plan_summary": self._plan_summary,
        }


class FakeQueueCoordinator:
    def __init__(self, result: Mapping[str, Any] | None = None) -> None:
        self._result = dict(result) if result is not None else {"ok": True}
        self.last_project_id: str | None = None
        self.last_queue_reference: str | None = None
        self.last_missions: List[Mapping[str, Any]] | None = None
        self.called: bool = False
        self.should_raise: bool = False

    def enqueue(self, *, project_id: str, queue_reference: str, missions: List[Mapping[str, Any]]) -> Mapping[str, Any]:
        self.called = True
        self.last_project_id = project_id
        self.last_queue_reference = queue_reference
        self.last_missions = list(missions)
        if self.should_raise:
            raise RuntimeError("queue failed")
        return dict(self._result)


# -------------------- Helpers --------------------


def make_valid_request() -> Dict[str, Any]:
    return {
        "accepted": True,
        "request_id": "req-1",
        "project_id": "proj-1",
        "conversation_id": "conv-1",
        "provider_id": "prov",
        "model_id": "model",
        "task_type": "content",
        "user_message": "Please write something",
        "upload_ids": ["u1", "u2"],
        "created_at": "2024-01-01T00:00:00Z",
        "warning": "",
        "project_context": {
            "project_id": "proj-1",
            "repository_root": "/repo",
            "default_branch": "main",
            "project_type": "content",
            "policy_profile": "default",
            "queue_reference": "queue-abc",
        },
    }


class TestPlannerQueueFlowCoordinator(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock()
        self.sink = FakeEventSink()

    def make_coordinator(self, planner: Any, builder: Any, queue: Any) -> PlannerQueueFlowCoordinator:
        return PlannerQueueFlowCoordinator(
            planner=planner,
            builder=builder,
            queue_coordinator=queue,
            clock=self.clock,
            event_sink=self.sink,
        )

    # Test successful end-to-end planner-to-queue flow
    def test_success_end_to_end(self) -> None:
        req = make_valid_request()
        planner = FakePlanner(plan_result={"steps": ["a", "b"], "id": "plan-1", "summary": "S"})
        missions = [{"mission_id": "m1"}, {"mission_id": "m2"}]
        builder = FakeBuilder(ok=True, missions=missions, plan_id="plan-1", plan_summary="S")
        queue = FakeQueueCoordinator(result={"ok": True})
        coord = self.make_coordinator(planner, builder, queue)
        res = coord.process(req)
        self.assertTrue(res["accepted"])  # accepted true only on queue success
        self.assertEqual(res["request_id"], req["request_id"])
        self.assertEqual(res["project_id"], req["project_id"])
        self.assertEqual(res["conversation_id"], req["conversation_id"])
        self.assertEqual(res["provider_id"], req["provider_id"])
        self.assertEqual(res["model_id"], req["model_id"])
        self.assertEqual(res["task_type"], req["task_type"])
        self.assertEqual(res["plan_id"], "plan-1")
        self.assertEqual(res["plan_summary"], "S")
        self.assertEqual(res["mission_ids"], ["m1", "m2"])
        self.assertEqual(res["blocked_reason"], "")

        # Completed event must exist
        events = coord.latest_events(10)
        self.assertTrue(any(e.get("event") == coord.EVT_FLOW_COMPLETED for e in events))

    # Test approved=false rejection
    def test_reject_when_not_accepted(self) -> None:
        req = make_valid_request()
        req["accepted"] = False
        planner = FakePlanner(plan_result={"steps": ["a"]})
        builder = FakeBuilder()
        queue = FakeQueueCoordinator()
        coord = self.make_coordinator(planner, builder, queue)
        res = coord.process(req)
        self.assertFalse(res["accepted"])
        self.assertEqual(res["blocked_reason"], PlannerQueueFlowCoordinator.INVALID_APPROVED_REQUEST)
        self.assertIsNone(planner.last_input)
        self.assertFalse(queue.called)

    # Test unknown-field rejection
    def test_unknown_field_rejection(self) -> None:
        req = make_valid_request()
        req["unknown"] = "x"  # type: ignore[typeddict-item]
        planner = FakePlanner(plan_result={"steps": ["a"]})
        builder = FakeBuilder()
        queue = FakeQueueCoordinator()
        coord = self.make_coordinator(planner, builder, queue)
        res = coord.process(req)
        self.assertFalse(res["accepted"])
        self.assertEqual(res["blocked_reason"], PlannerQueueFlowCoordinator.INVALID_APPROVED_REQUEST)
        self.assertFalse(queue.called)

    # Test missing project context rejection
    def test_missing_project_context_rejection(self) -> None:
        req = make_valid_request()
        del req["project_context"]
        planner = FakePlanner(plan_result={"steps": ["a"]})
        builder = FakeBuilder()
        queue = FakeQueueCoordinator()
        coord = self.make_coordinator(planner, builder, queue)
        res = coord.process(req)
        self.assertFalse(res["accepted"])
        self.assertEqual(res["blocked_reason"], PlannerQueueFlowCoordinator.INVALID_APPROVED_REQUEST)
        self.assertFalse(queue.called)

    # Test project-context mismatch rejection
    def test_project_context_mismatch(self) -> None:
        req = make_valid_request()
        req["project_context"]["project_id"] = "other"
        planner = FakePlanner(plan_result={"steps": ["a"]})
        builder = FakeBuilder()
        queue = FakeQueueCoordinator()
        coord = self.make_coordinator(planner, builder, queue)
        res = coord.process(req)
        self.assertFalse(res["accepted"])
        self.assertEqual(res["blocked_reason"], PlannerQueueFlowCoordinator.INVALID_APPROVED_REQUEST)
        self.assertFalse(queue.called)

    # Test deterministic Planner input
    def test_deterministic_planner_input(self) -> None:
        req = make_valid_request()
        expected_input = {
            "request_id": req["request_id"],
            "project_id": req["project_id"],
            "conversation_id": req["conversation_id"],
            "repository_root": req["project_context"]["repository_root"],
            "default_branch": req["project_context"]["default_branch"],
            "project_type": req["project_context"]["project_type"],
            "policy_profile": req["project_context"]["policy_profile"],
            "provider_id": req["provider_id"],
            "model_id": req["model_id"],
            "task_type": req["task_type"],
            "user_message": req["user_message"],
            "upload_ids": req["upload_ids"],
        }
        planner = FakePlanner(plan_result={"steps": ["a"], "id": "p1", "summary": "s"})
        builder = FakeBuilder(ok=True, missions=[{"mission_id": "m1"}], plan_id="p1", plan_summary="s")
        queue = FakeQueueCoordinator(result={"ok": True})
        coord = self.make_coordinator(planner, builder, queue)
        _ = coord.process(req)
        self.assertEqual(planner.last_input, expected_input)

    # Test Planner failure
    def test_planner_failure(self) -> None:
        req = make_valid_request()
        planner = FakePlanner(should_raise=True)
        builder = FakeBuilder()
        queue = FakeQueueCoordinator()
        coord = self.make_coordinator(planner, builder, queue)
        res = coord.process(req)
        self.assertFalse(res["accepted"])
        self.assertEqual(res["blocked_reason"], PlannerQueueFlowCoordinator.PLANNER_FAILED)
        self.assertFalse(queue.called)

    # Test empty Planner result
    def test_empty_planner_result(self) -> None:
        req = make_valid_request()
        planner = FakePlanner(plan_result={})
        builder = FakeBuilder()
        queue = FakeQueueCoordinator()
        coord = self.make_coordinator(planner, builder, queue)
        res = coord.process(req)
        self.assertFalse(res["accepted"])
        self.assertEqual(res["blocked_reason"], PlannerQueueFlowCoordinator.INVALID_PLAN)
        self.assertFalse(queue.called)

    # Test builder validation failure
    def test_builder_validation_failure(self) -> None:
        req = make_valid_request()
        planner = FakePlanner(plan_result={"steps": ["a"]})
        builder = FakeBuilder(ok=False)
        queue = FakeQueueCoordinator()
        coord = self.make_coordinator(planner, builder, queue)
        res = coord.process(req)
        self.assertFalse(res["accepted"])
        self.assertEqual(res["blocked_reason"], PlannerQueueFlowCoordinator.INVALID_PLAN)
        self.assertFalse(queue.called)

    # Test builder receives correct approved request
    def test_builder_receives_correct_request(self) -> None:
        req = make_valid_request()
        planner = FakePlanner(plan_result={"steps": ["a"], "id": "p1", "summary": "s"})
        builder = FakeBuilder(ok=True, missions=[{"mission_id": "m1"}], plan_id="p1", plan_summary="s")
        queue = FakeQueueCoordinator(result={"ok": True})
        coord = self.make_coordinator(planner, builder, queue)
        _ = coord.process(req)
        self.assertIsNotNone(builder.last_approved_request)
        # Ensure the builder receives full approved_request context and not arbitrary extra fields
        self.assertEqual(builder.last_approved_request["project_id"], req["project_id"])  # type: ignore[index]
        self.assertIn("project_context", builder.last_approved_request)  # type: ignore[operator]

    # Test mission ordering remains unchanged
    def test_mission_ordering_preserved(self) -> None:
        req = make_valid_request()
        planner = FakePlanner(plan_result={"steps": ["a"]})
        missions = [{"mission_id": "x"}, {"mission_id": "a"}, {"mission_id": "b"}]
        builder = FakeBuilder(ok=True, missions=missions, plan_id="p1", plan_summary="s")
        queue = FakeQueueCoordinator(result={"ok": True})
        coord = self.make_coordinator(planner, builder, queue)
        res = coord.process(req)
        self.assertEqual(res["mission_ids"], ["x", "a", "b"])  # preserve order

    # Test mission identifiers remain unchanged
    def test_mission_identifiers_unchanged(self) -> None:
        req = make_valid_request()
        missions = [{"mission_id": "m-001"}]
        builder = FakeBuilder(ok=True, missions=missions, plan_id="p1", plan_summary="s")
        planner = FakePlanner(plan_result={"steps": ["a"]})
        queue = FakeQueueCoordinator(result={"ok": True})
        coord = self.make_coordinator(planner, builder, queue)
        res = coord.process(req)
        self.assertEqual(res["mission_ids"], ["m-001"])  # unchanged

    # Test queue coordinator receives correct project_id and queue_reference
    def test_queue_receives_correct_project_and_queue(self) -> None:
        req = make_valid_request()
        missions = [{"mission_id": "m1"}]
        builder = FakeBuilder(ok=True, missions=missions, plan_id="p1", plan_summary="s")
        planner = FakePlanner(plan_result={"steps": ["do"]})
        queue = FakeQueueCoordinator(result={"ok": True})
        coord = self.make_coordinator(planner, builder, queue)
        _ = coord.process(req)
        self.assertEqual(queue.last_project_id, req["project_id"])  # type: ignore[index]
        self.assertEqual(queue.last_queue_reference, req["project_context"]["queue_reference"])  # type: ignore[index]

    # Test queue success
    def test_queue_success(self) -> None:
        req = make_valid_request()
        missions = [{"mission_id": "m1"}]
        builder = FakeBuilder(ok=True, missions=missions)
        planner = FakePlanner(plan_result={"steps": ["do"]})
        queue = FakeQueueCoordinator(result={"ok": True})
        coord = self.make_coordinator(planner, builder, queue)
        res = coord.process(req)
        self.assertTrue(res["accepted"])
        self.assertEqual(res["blocked_reason"], "")

    # Test queue resolution failure boundary contract
    def test_queue_resolution_failure(self) -> None:
        req = make_valid_request()
        missions = [{"mission_id": "m1"}]
        builder = FakeBuilder(ok=True, missions=missions)
        planner = FakePlanner(plan_result={"steps": ["do"]})
        queue = FakeQueueCoordinator(result={"ok": False, "code": PlannerQueueFlowCoordinator.QUEUE_RESOLUTION_FAILED})
        coord = self.make_coordinator(planner, builder, queue)
        res = coord.process(req)
        self.assertFalse(res["accepted"])
        self.assertEqual(res["blocked_reason"], PlannerQueueFlowCoordinator.QUEUE_RESOLUTION_FAILED)

    # Test unsupported queue interface result
    def test_unsupported_queue_interface(self) -> None:
        req = make_valid_request()
        planner = FakePlanner(plan_result={"steps": ["a"]})
        builder = FakeBuilder(ok=True, missions=[{"mission_id": "m1"}])
        queue = FakeQueueCoordinator(result={"ok": False, "code": PlannerQueueFlowCoordinator.UNSUPPORTED_QUEUE_INTERFACE})
        coord = self.make_coordinator(planner, builder, queue)
        res = coord.process(req)
        self.assertFalse(res["accepted"])
        self.assertEqual(res["blocked_reason"], PlannerQueueFlowCoordinator.UNSUPPORTED_QUEUE_INTERFACE)

    # Test queue failure
    def test_queue_failure(self) -> None:
        req = make_valid_request()
        planner = FakePlanner(plan_result={"steps": ["a"]})
        builder = FakeBuilder(ok=True, missions=[{"mission_id": "m1"}])
        queue = FakeQueueCoordinator(result={"ok": False, "code": PlannerQueueFlowCoordinator.QUEUE_FAILED})
        coord = self.make_coordinator(planner, builder, queue)
        res = coord.process(req)
        self.assertFalse(res["accepted"])
        self.assertEqual(res["blocked_reason"], PlannerQueueFlowCoordinator.QUEUE_FAILED)

    # Test partial enqueue result
    def test_partial_enqueue(self) -> None:
        req = make_valid_request()
        planner = FakePlanner(plan_result={"steps": ["a"]})
        builder = FakeBuilder(ok=True, missions=[{"mission_id": "m1"}, {"mission_id": "m2"}])
        queue = FakeQueueCoordinator(result={"ok": False, "code": PlannerQueueFlowCoordinator.PARTIAL_ENQUEUE})
        coord = self.make_coordinator(planner, builder, queue)
        res = coord.process(req)
        self.assertFalse(res["accepted"])
        self.assertEqual(res["blocked_reason"], PlannerQueueFlowCoordinator.PARTIAL_ENQUEUE)

    # Test no enqueue after Planner failure
    def test_no_enqueue_after_planner_failure(self) -> None:
        req = make_valid_request()
        planner = FakePlanner(should_raise=True)
        builder = FakeBuilder(ok=True, missions=[{"mission_id": "m1"}])
        queue = FakeQueueCoordinator(result={"ok": True})
        coord = self.make_coordinator(planner, builder, queue)
        _ = coord.process(req)
        self.assertFalse(queue.called)

    # Test no enqueue after builder failure
    def test_no_enqueue_after_builder_failure(self) -> None:
        req = make_valid_request()
        planner = FakePlanner(plan_result={"steps": ["a"]})
        builder = FakeBuilder(ok=False)
        queue = FakeQueueCoordinator(result={"ok": True})
        coord = self.make_coordinator(planner, builder, queue)
        _ = coord.process(req)
        self.assertFalse(queue.called)

    # Test deterministic success result
    def test_deterministic_success_result(self) -> None:
        req = make_valid_request()
        missions = [{"mission_id": "m1"}, {"mission_id": "m2"}]
        builder = FakeBuilder(ok=True, missions=missions, plan_id="p1", plan_summary="sum")
        planner = FakePlanner(plan_result={"steps": ["a"], "id": "p1", "summary": "sum"})
        queue = FakeQueueCoordinator(result={"ok": True})
        coord = self.make_coordinator(planner, builder, queue)
        res1 = coord.process(req)
        res2 = coord.process(req)
        self.assertEqual(res1, res2)

    # Test result redaction
    def test_result_redaction(self) -> None:
        req = make_valid_request()
        planner = FakePlanner(plan_result={"steps": ["a"]})
        builder = FakeBuilder(ok=True, missions=[{"mission_id": "m1"}], plan_id="p1", plan_summary="sum")
        queue = FakeQueueCoordinator(result={"ok": True})
        coord = self.make_coordinator(planner, builder, queue)
        res = coord.process(req)
        # Ensure sensitive fields are not present in result structure beyond allowed ones
        self.assertIn("warning", res)
        self.assertIn("plan_summary", res)
        self.assertNotIn("user_message", res)
        self.assertNotIn("upload_ids", res)

    # Test event redaction
    def test_event_redaction(self) -> None:
        req = make_valid_request()
        planner = FakePlanner(plan_result={"steps": ["a"]})
        builder = FakeBuilder(ok=True, missions=[{"mission_id": "m1"}])
        queue = FakeQueueCoordinator(result={"ok": True})
        coord = self.make_coordinator(planner, builder, queue)
        _ = coord.process(req)
        for e in coord.latest_events(100):
            payload = e.get("payload", {})
            self.assertNotIn("user_message", payload)
            self.assertNotIn("upload_ids", payload)

    # Test validate_approved_request boundary: syntactically valid queue_reference must pass
    def test_validate_only_schema_not_resolution(self) -> None:
        req = make_valid_request()
        # Keep syntactically valid queue_reference
        builder = FakeBuilder()
        planner = FakePlanner(plan_result={"steps": ["a"]})
        queue = FakeQueueCoordinator(result={"ok": False, "code": PlannerQueueFlowCoordinator.QUEUE_RESOLUTION_FAILED})
        coord = self.make_coordinator(planner, builder, queue)
        valid, _ = coord.validate_approved_request(req)
        self.assertTrue(valid)
        # Process leads to queue_resolution_failed, not invalid_approved_request
        res = coord.process(req)
        self.assertEqual(res["blocked_reason"], PlannerQueueFlowCoordinator.QUEUE_RESOLUTION_FAILED)

    # Test unrelated files remain unchanged (placeholder: ensure coordinator does not alter request dict)
    def test_input_not_mutated(self) -> None:
        req = make_valid_request()
        req_copy = dict(req)
        req_copy_ctx = dict(req["project_context"])  # deep copy of context
        req_copy["project_context"] = req_copy_ctx
        planner = FakePlanner(plan_result={"steps": ["a"]})
        builder = FakeBuilder(ok=True, missions=[{"mission_id": "m1"}], plan_id="p1", plan_summary="s")
        queue = FakeQueueCoordinator(result={"ok": True})
        coord = self.make_coordinator(planner, builder, queue)
        _ = coord.process(req_copy)
        # Compare to original make_valid_request to ensure no mutation
        self.assertEqual(req_copy, req)


if __name__ == "__main__":
    unittest.main()
