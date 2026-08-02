from __future__ import annotations

import unittest
from typing import Any, Dict, List, Optional
from copy import deepcopy

from agent.orchestrator.unified_request_flow_service import UnifiedRequestFlowService


class FakeClock:
    def now(self):  # not used directly in service outputs; retained for DI completeness
        class _T:
            def isoformat(self):
                return "2024-01-01T00:00:00+00:00"
        return _T()


class FakeEventSink:
    def __init__(self) -> None:
        self.events: List[Dict[str, Any]] = []

    def emit(self, name: str, payload: Dict[str, Any]) -> None:
        # Store deterministic copy
        self.events.append({"name": name, "payload": deepcopy(payload)})


class FakeGate:
    def __init__(self, *, mode: str = "accept", blocked_reason: Optional[str] = None, accept_result: Optional[Dict[str, Any]] = None) -> None:
        self.mode = mode
        self.blocked_reason = blocked_reason
        self.accept_result = accept_result
        self.calls: int = 0

    def process_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        self.calls += 1
        if self.mode == "exception":
            raise RuntimeError("unexpected gate failure")
        if self.mode == "block":
            # Return a blocked result with provided reason (must be from allowed gate list)
            base = {
                "accepted": False,
                "blocked_reason": self.blocked_reason,
                "request_id": request.get("request_id"),
                "project_id": request.get("project_id"),
                "conversation_id": request.get("conversation_id"),
                # provider/model may be absent in block cases
                "created_at": "2024-01-01T00:00:00Z",
            }
            return base
        # accept
        if self.accept_result is not None:
            return deepcopy(self.accept_result)
        # default accept result
        return {
            "accepted": True,
            "request_id": request.get("request_id"),
            "project_id": request.get("project_id"),
            "conversation_id": request.get("conversation_id"),
            "provider_id": "provA",
            "model_id": "modB",
            "task_type": request.get("task_type", "chat"),
            "created_at": "2024-01-01T00:00:00Z",
            "warning": None,
            "project_context": {"scope": "default"},
        }


class FakePlanner:
    def __init__(self, *, mode: str = "success", blocked_reason: Optional[str] = None) -> None:
        self.mode = mode
        self.blocked_reason = blocked_reason
        self.calls: int = 0
        self.last_approved_request: Optional[Dict[str, Any]] = None

    def process(self, approved_request: Dict[str, Any]) -> Dict[str, Any]:
        self.calls += 1
        self.last_approved_request = deepcopy(approved_request)
        if self.mode == "exception":
            raise RuntimeError("unexpected planner failure")
        if self.mode == "failure":
            return {
                "accepted": False,
                "blocked_reason": self.blocked_reason,
            }
        # success
        return {
            "accepted": True,
            "plan_id": "plan-001",
            "plan_summary": "summary: proceed",
            "mission_ids": ["m-1", "m-2"],
        }


class UnifiedRequestFlowServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock()
        self.event_sink = FakeEventSink()

    def _default_request(self) -> Dict[str, Any]:
        return {
            "request_id": "req-123",
            "project_id": "proj-1",
            "conversation_id": "conv-9",
            "task_type": "chat",
            "user_message": "Top secret message that must not appear in logs or status",
            "upload_ids": ["upl-1", "upl-2"],
        }

    def _default_gate_accept(self) -> Dict[str, Any]:
        return {
            "accepted": True,
            "request_id": "req-123",
            "project_id": "proj-1",
            "conversation_id": "conv-9",
            "provider_id": "provA",
            "model_id": "modB",
            "task_type": "chat",
            "created_at": "2024-01-01T00:00:00Z",
            "warning": "caution",
            "project_context": {"k": "v"},
        }

    def _build_service(self, gate: FakeGate, planner: FakePlanner) -> UnifiedRequestFlowService:
        return UnifiedRequestFlowService(
            request_gate_selector=gate,
            planner_queue_flow_coordinator=planner,
            clock=self.clock,
            event_sink=self.event_sink,
        )

    # 1. Test successful complete request flow.
    def test_successful_complete_request_flow(self) -> None:
        gate = FakeGate(accept_result=self._default_gate_accept())
        planner = FakePlanner(mode="success")
        service = self._build_service(gate, planner)
        req = self._default_request()
        result = service.submit(req)

        self.assertTrue(result.get("accepted"))
        self.assertEqual(result.get("request_id"), "req-123")
        self.assertEqual(result.get("project_id"), "proj-1")
        self.assertEqual(result.get("conversation_id"), "conv-9")
        self.assertEqual(result.get("provider_id"), "provA")
        self.assertEqual(result.get("model_id"), "modB")
        self.assertEqual(result.get("task_type"), "chat")
        self.assertEqual(result.get("plan_id"), "plan-001")
        self.assertEqual(result.get("plan_summary"), "summary: proceed")
        self.assertEqual(result.get("mission_ids"), ["m-1", "m-2"])
        self.assertEqual(result.get("warning"), "caution")
        self.assertEqual(result.get("created_at"), "2024-01-01T00:00:00Z")
        # user_message must not be present
        self.assertNotIn("user_message", result)

    # 2. Test gate rejection stops downstream processing.
    def test_gate_rejection_stops_downstream_processing(self) -> None:
        gate = FakeGate(mode="block", blocked_reason="invalid_request")
        planner = FakePlanner(mode="success")
        service = self._build_service(gate, planner)
        res = service.submit(self._default_request())
        self.assertFalse(res.get("accepted", False))
        self.assertEqual(res.get("blocked_reason"), "invalid_request")
        self.assertEqual(planner.calls, 0)

    # 3. Test budget block propagation.
    def test_budget_block_propagation(self) -> None:
        gate = FakeGate(mode="block", blocked_reason="budget_blocked")
        planner = FakePlanner()
        service = self._build_service(gate, planner)
        res = service.submit(self._default_request())
        self.assertEqual(res.get("blocked_reason"), "budget_blocked")
        self.assertEqual(planner.calls, 0)

    # 4. Test rate-limit block propagation.
    def test_rate_limit_block_propagation(self) -> None:
        gate = FakeGate(mode="block", blocked_reason="rate_limit_blocked")
        planner = FakePlanner()
        service = self._build_service(gate, planner)
        res = service.submit(self._default_request())
        self.assertEqual(res.get("blocked_reason"), "rate_limit_blocked")
        self.assertEqual(planner.calls, 0)

    # 5. Test unknown-project propagation.
    def test_unknown_project_propagation(self) -> None:
        gate = FakeGate(mode="block", blocked_reason="unknown_project")
        planner = FakePlanner()
        service = self._build_service(gate, planner)
        res = service.submit(self._default_request())
        self.assertEqual(res.get("blocked_reason"), "unknown_project")
        self.assertEqual(planner.calls, 0)

    # 6. Test no-model-available propagation.
    def test_no_model_available_propagation(self) -> None:
        gate = FakeGate(mode="block", blocked_reason="no_model_available")
        planner = FakePlanner()
        service = self._build_service(gate, planner)
        res = service.submit(self._default_request())
        self.assertEqual(res.get("blocked_reason"), "no_model_available")
        self.assertEqual(planner.calls, 0)

    # 7. Test approved-request field mapping.
    def test_approved_request_field_mapping(self) -> None:
        gate_accept = self._default_gate_accept()
        gate = FakeGate(accept_result=gate_accept)
        planner = FakePlanner(mode="success")
        service = self._build_service(gate, planner)
        req = self._default_request()
        _ = service.submit(req)

        approved = planner.last_approved_request
        self.assertIsNotNone(approved)
        assert approved is not None
        # From gate
        self.assertTrue(approved.get("accepted"))
        self.assertEqual(approved.get("request_id"), gate_accept["request_id"])
        self.assertEqual(approved.get("project_id"), gate_accept["project_id"])
        self.assertEqual(approved.get("conversation_id"), gate_accept["conversation_id"])
        self.assertEqual(approved.get("provider_id"), gate_accept["provider_id"])
        self.assertEqual(approved.get("model_id"), gate_accept["model_id"])
        self.assertEqual(approved.get("task_type"), gate_accept["task_type"])
        self.assertEqual(approved.get("created_at"), gate_accept["created_at"])
        self.assertEqual(approved.get("warning"), gate_accept["warning"])
        self.assertEqual(approved.get("project_context"), gate_accept["project_context"])
        # From original request
        self.assertEqual(approved.get("user_message"), req["user_message"])  # passed downstream only
        self.assertEqual(approved.get("upload_ids"), req["upload_ids"])  # passed downstream only

    # 8. Test selected provider and model preservation.
    def test_selected_provider_and_model_preservation(self) -> None:
        gate_accept = self._default_gate_accept()
        gate_accept.update({"provider_id": "provider-X", "model_id": "model-Y"})
        gate = FakeGate(accept_result=gate_accept)
        planner = FakePlanner(mode="success")
        service = self._build_service(gate, planner)
        res = service.submit(self._default_request())
        self.assertEqual(res.get("provider_id"), "provider-X")
        self.assertEqual(res.get("model_id"), "model-Y")

    # 9. Test warning preservation.
    def test_warning_preservation(self) -> None:
        gate_accept = self._default_gate_accept()
        gate_accept["warning"] = "warn-me"
        gate = FakeGate(accept_result=gate_accept)
        planner = FakePlanner(mode="success")
        service = self._build_service(gate, planner)
        res = service.submit(self._default_request())
        self.assertEqual(res.get("warning"), "warn-me")

    # 10. Test Planner failure propagation.
    def test_planner_failure_propagation(self) -> None:
        gate = FakeGate(accept_result=self._default_gate_accept())
        planner = FakePlanner(mode="failure", blocked_reason="planner_failed")
        service = self._build_service(gate, planner)
        res = service.submit(self._default_request())
        self.assertFalse(res.get("accepted"))
        self.assertEqual(res.get("blocked_reason"), "planner_failed")

    # 11. Test invalid-plan propagation.
    def test_invalid_plan_propagation(self) -> None:
        gate = FakeGate(accept_result=self._default_gate_accept())
        planner = FakePlanner(mode="failure", blocked_reason="invalid_plan")
        service = self._build_service(gate, planner)
        res = service.submit(self._default_request())
        self.assertEqual(res.get("blocked_reason"), "invalid_plan")

    # 12. Test queue-resolution failure propagation.
    def test_queue_resolution_failure_propagation(self) -> None:
        gate = FakeGate(accept_result=self._default_gate_accept())
        planner = FakePlanner(mode="failure", blocked_reason="queue_resolution_failed")
        service = self._build_service(gate, planner)
        res = service.submit(self._default_request())
        self.assertEqual(res.get("blocked_reason"), "queue_resolution_failed")

    # 13. Test queue failure propagation.
    def test_queue_failure_propagation(self) -> None:
        gate = FakeGate(accept_result=self._default_gate_accept())
        planner = FakePlanner(mode="failure", blocked_reason="queue_failed")
        service = self._build_service(gate, planner)
        res = service.submit(self._default_request())
        self.assertEqual(res.get("blocked_reason"), "queue_failed")

    # 14. Test partial-enqueue propagation.
    def test_partial_enqueue_propagation(self) -> None:
        gate = FakeGate(accept_result=self._default_gate_accept())
        planner = FakePlanner(mode="failure", blocked_reason="partial_enqueue")
        service = self._build_service(gate, planner)
        res = service.submit(self._default_request())
        self.assertEqual(res.get("blocked_reason"), "partial_enqueue")

    # 15. Test unexpected gate exception conversion.
    def test_unexpected_gate_exception_conversion(self) -> None:
        gate = FakeGate(mode="exception")
        planner = FakePlanner(mode="success")
        service = self._build_service(gate, planner)
        res = service.submit(self._default_request())
        self.assertFalse(res.get("accepted", False))
        self.assertEqual(res.get("blocked_reason"), "dependency_failed")
        # Planner must not be called when gate errored
        self.assertEqual(planner.calls, 0)

    # 16. Test unexpected downstream exception conversion.
    def test_unexpected_downstream_exception_conversion(self) -> None:
        gate = FakeGate(accept_result=self._default_gate_accept())
        planner = FakePlanner(mode="exception")
        service = self._build_service(gate, planner)
        res = service.submit(self._default_request())
        self.assertFalse(res.get("accepted", True))
        self.assertEqual(res.get("blocked_reason"), "dependency_failed")

    # 17. Test original request is not mutated.
    def test_original_request_not_mutated(self) -> None:
        gate = FakeGate(accept_result=self._default_gate_accept())
        planner = FakePlanner(mode="success")
        service = self._build_service(gate, planner)
        req = self._default_request()
        req_copy = deepcopy(req)
        _ = service.submit(req)
        self.assertEqual(req, req_copy)

    # 18. Test deterministic success result.
    def test_deterministic_success_result(self) -> None:
        gate = FakeGate(accept_result=self._default_gate_accept())
        planner = FakePlanner(mode="success")
        service = self._build_service(gate, planner)
        req = self._default_request()
        r1 = service.submit(req)
        r2 = service.submit(req)
        self.assertEqual(r1, r2)

    # 19. Test result redaction.
    def test_result_redaction(self) -> None:
        gate = FakeGate(accept_result=self._default_gate_accept())
        planner = FakePlanner(mode="success")
        service = self._build_service(gate, planner)
        res = service.submit(self._default_request())
        # Ensure no sensitive fields are present
        self.assertNotIn("user_message", res)
        # Ensure only expected keys (subset check)
        allowed_keys = {
            "accepted",
            "request_id",
            "project_id",
            "conversation_id",
            "provider_id",
            "model_id",
            "task_type",
            "plan_id",
            "plan_summary",
            "mission_ids",
            "warning",
            "blocked_reason",
            "created_at",
        }
        self.assertTrue(set(res.keys()).issubset(allowed_keys))

    # 20. Test event redaction.
    def test_event_redaction(self) -> None:
        gate = FakeGate(accept_result=self._default_gate_accept())
        planner = FakePlanner(mode="success")
        service = self._build_service(gate, planner)
        _ = service.submit(self._default_request())
        events = service.latest_events(100)
        for ev in events:
            payload = ev.get("payload", {})
            self.assertNotIn("user_message", payload)

    # 21. Test full user message is absent from events and status.
    def test_full_user_message_absent_from_events_and_status(self) -> None:
        gate = FakeGate(accept_result=self._default_gate_accept())
        planner = FakePlanner(mode="success")
        service = self._build_service(gate, planner)
        req = self._default_request()
        _ = service.submit(req)
        # Status redaction
        status = service.status()
        assert status is not None
        self.assertNotIn("user_message", status)
        # Events redaction
        for ev in service.latest_events(50):
            self.assertNotIn("user_message", ev.get("payload", {}))


if __name__ == "__main__":
    unittest.main()
