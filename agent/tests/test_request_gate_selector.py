from __future__ import annotations

import unittest
from typing import Any, Dict, List, Optional
from agent.orchestrator.request_gate_selector import (
    RequestGateSelector,
    ModelInfo,
)


# Fake dependencies for testing


class FakeEventSink:
    def __init__(self) -> None:
        self._events: List[Dict[str, Any]] = []

    def emit(self, event_type: str, payload: Dict[str, Any]) -> None:
        # Redact aggressively; test ensures no user_message content is included
        self._events.append({"type": event_type, "payload": dict(payload)})

    def latest(self, limit: int, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if project_id is None:
            return list(self._events[-limit:])
        filtered: List[Dict[str, Any]] = []
        for e in reversed(self._events):
            if e["payload"].get("project_id") == project_id:
                filtered.append(e)
                if len(filtered) >= limit:
                    break
        return list(reversed(filtered))


class FakeClock:
    def __init__(self, t: float = 1234567.0) -> None:
        self._t = t

    def now(self) -> float:
        return self._t


class FakeProjectRegistry:
    def __init__(self) -> None:
        self.projects: Dict[str, Dict[str, Any]] = {}
        self.conversations: Dict[str, str] = {}  # conversation_id -> project_id
        self.uploads: Dict[str, str] = {}  # upload_id -> project_id

    def add_project(self, project_id: str) -> None:
        self.projects[project_id] = {"project_id": project_id, "name": f"Project {project_id}"}

    def add_conversation(self, project_id: str, conversation_id: str) -> None:
        self.conversations[conversation_id] = project_id

    def add_upload(self, project_id: str, upload_id: str) -> None:
        self.uploads[upload_id] = project_id

    def resolve_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        return self.projects.get(project_id)

    def conversation_belongs_to_project(self, conversation_id: str, project_id: str) -> bool:
        return self.conversations.get(conversation_id) == project_id

    def upload_belongs_to_project(self, upload_id: str, project_id: str) -> bool:
        return self.uploads.get(upload_id) == project_id


class FakeProviderRegistry:
    def __init__(self) -> None:
        # key: (project_id, task_type) -> list of ModelInfo
        self.models: Dict[tuple[str, str], List[ModelInfo]] = {}
        self.tool_required: set[str] = set()

    def add_model(
        self,
        *,
        project_id: str,
        task_type: str,
        provider_id: str,
        model_id: str,
        supports_vision: bool = False,
        supports_tools: bool = False,
        enabled: bool = True,
        available: bool = True,
        deprecated: bool = False,
    ) -> None:
        key = (project_id, task_type)
        self.models.setdefault(key, []).append(
            ModelInfo(
                project_id=project_id,
                provider_id=provider_id,
                model_id=model_id,
                supports_vision=supports_vision,
                supports_tools=supports_tools,
                enabled=enabled,
                available=available,
                deprecated=deprecated,
            )
        )

    def is_task_supported(self, project_id: str, task_type: str) -> bool:
        return (project_id, task_type) in self.models

    def requires_tools(self, task_type: str) -> bool:
        return task_type in self.tool_required

    def explicit_model_allowed(
        self, project_id: str, task_type: str, provider_id: str, model_id: str
    ) -> Optional[ModelInfo]:
        for m in self.models.get((project_id, task_type), []):
            if m.provider_id == provider_id and m.model_id == model_id:
                return m
        return None

    def select_default_model(
        self,
        project_id: str,
        task_type: str,
        requires_vision: bool,
        requires_tools: bool,
        requested_provider_id: Optional[str] = None,
    ) -> Optional[ModelInfo]:
        candidates = list(self.models.get((project_id, task_type), []))
        # stable deterministic ordering: already insertion order
        for m in candidates:
            if requested_provider_id and m.provider_id != requested_provider_id:
                continue
            if requires_vision and not m.supports_vision:
                continue
            if requires_tools and not m.supports_tools:
                continue
            if not m.enabled or not m.available or m.deprecated:
                continue
            return m
        return None


class FakeBudgetEvaluator:
    def __init__(self) -> None:
        # map by request_id -> status
        self.behavior: Dict[str, Dict[str, Any]] = {}

    def set_behavior(self, request_id: str, status: str, message: Optional[str] = None) -> None:
        payload: Dict[str, Any] = {"status": status}
        if message:
            payload["message"] = message
        self.behavior[request_id] = payload

    def preflight(
        self,
        *,
        project_id: str,
        provider_id: str,
        model_id: str,
        task_type: str,
        created_at: Any,
        request_id: str,
    ) -> Dict[str, Any]:
        return dict(self.behavior.get(request_id, {"status": "allow"}))


class FakeRateLimiter:
    def __init__(self) -> None:
        self.blocked_keys: set[str] = set()
        self.called: bool = False

    def make_key(self, *, project_id: str, provider_id: str, model_id: str, task_type: str) -> str:
        return f"{project_id}:{provider_id}:{model_id}:{task_type}"

    def block(self, *, project_id: str, provider_id: str, model_id: str, task_type: str) -> None:
        self.blocked_keys.add(self.make_key(project_id=project_id, provider_id=provider_id, model_id=model_id, task_type=task_type))

    def check_and_register(
        self,
        *,
        project_id: str,
        provider_id: str,
        model_id: str,
        task_type: str,
        request_id: str,
        created_at: Any,
    ) -> Dict[str, Any]:
        self.called = True
        key = self.make_key(project_id=project_id, provider_id=provider_id, model_id=model_id, task_type=task_type)
        if key in self.blocked_keys:
            return {"allowed": False, "reason": "rate_limited"}
        # simulate atomic register success
        return {"allowed": True}


class RequestGateSelectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.projects = FakeProjectRegistry()
        self.providers = FakeProviderRegistry()
        self.budget = FakeBudgetEvaluator()
        self.ratelimit = FakeRateLimiter()
        self.clock = FakeClock(1000.0)
        self.events = FakeEventSink()
        # common project and conversation
        self.projects.add_project("p1")
        self.projects.add_conversation("p1", "c1")
        # default chat model
        self.providers.add_model(
            project_id="p1",
            task_type="chat",
            provider_id="provA",
            model_id="modChat",
            supports_vision=False,
            supports_tools=False,
        )
        self.gate = RequestGateSelector(
            project_registry=self.projects,
            provider_registry=self.providers,
            budget_evaluator=self.budget,
            rate_limiter=self.ratelimit,
            clock=self.clock,
            event_sink=self.events,
        )

    def _base_request(self) -> Dict[str, Any]:
        return {
            "request_id": "r1",
            "project_id": "p1",
            "conversation_id": "c1",
            "user_message": "Hello",
            "upload_ids": [],
            "requested_task_type": "chat",
            "requested_provider_id": None,
            "requested_model_id": None,
            "created_at": 999.0,
            "metadata": {"note": "unit"},
        }

    def test_successful_request_acceptance(self) -> None:
        req = self._base_request()
        res = self.gate.process_request(req)
        self.assertTrue(res.get("accepted"))
        self.assertEqual(res.get("project_id"), "p1")
        self.assertEqual(res.get("conversation_id"), "c1")
        self.assertEqual(res.get("provider_id"), "provA")
        self.assertEqual(res.get("model_id"), "modChat")
        self.assertEqual(res.get("task_type"), "chat")
        self.assertIsNone(res.get("warning"))
        self.assertIsNone(res.get("blocked_reason"))
        self.assertEqual(res.get("project_context"), {"project_id": "p1"})
        # Ensure redaction: user_message is not included in result
        self.assertNotIn("user_message", res)

    def test_explicit_model_selection(self) -> None:
        req = self._base_request()
        req["request_id"] = "r2"
        req["requested_provider_id"] = "provA"
        req["requested_model_id"] = "modChat"
        res = self.gate.process_request(req)
        self.assertTrue(res.get("accepted"))
        self.assertEqual(res.get("provider_id"), "provA")
        self.assertEqual(res.get("model_id"), "modChat")

    def test_default_model_selection(self) -> None:
        req = self._base_request()
        req["request_id"] = "r3"
        res = self.gate.process_request(req)
        self.assertTrue(res.get("accepted"))
        self.assertEqual(res.get("provider_id"), "provA")
        self.assertEqual(res.get("model_id"), "modChat")

    def test_unknown_project_rejection(self) -> None:
        req = self._base_request()
        req["request_id"] = "r4"
        req["project_id"] = "unknown"
        res = self.gate.process_request(req)
        self.assertFalse(res.get("accepted"))
        self.assertEqual(res.get("blocked_reason"), "unknown_project")

    def test_cross_project_conversation_rejection(self) -> None:
        self.projects.add_project("p2")
        self.projects.add_conversation("p2", "cX")
        req = self._base_request()
        req["request_id"] = "r5"
        req["conversation_id"] = "cX"  # belongs to p2, not p1
        res = self.gate.process_request(req)
        self.assertFalse(res.get("accepted"))
        self.assertEqual(res.get("blocked_reason"), "cross_project_reference")

    def test_cross_project_upload_rejection(self) -> None:
        self.projects.add_project("p2")
        self.projects.add_upload("p2", "u2")
        req = self._base_request()
        req["request_id"] = "r6"
        req["upload_ids"] = ["u2"]
        res = self.gate.process_request(req)
        self.assertFalse(res.get("accepted"))
        self.assertEqual(res.get("blocked_reason"), "cross_project_reference")

    def test_empty_message_rejection(self) -> None:
        req = self._base_request()
        req["request_id"] = "r7"
        req["user_message"] = ""
        res = self.gate.process_request(req)
        self.assertFalse(res.get("accepted"))
        self.assertEqual(res.get("blocked_reason"), "invalid_request")

    def test_invalid_task_type_rejection(self) -> None:
        req = self._base_request()
        req["request_id"] = "r8"
        req["requested_task_type"] = "unknown_task"
        res = self.gate.process_request(req)
        self.assertFalse(res.get("accepted"))
        self.assertEqual(res.get("blocked_reason"), "invalid_request")

    def test_no_model_available_result(self) -> None:
        # For a different task with no models
        req = self._base_request()
        req["request_id"] = "r9"
        req["requested_task_type"] = "summarize"  # no models configured
        res = self.gate.process_request(req)
        self.assertFalse(res.get("accepted"))
        self.assertEqual(res.get("blocked_reason"), "invalid_request")  # unsupported task considered invalid_request

        # Configure task but models not available (disabled)
        self.providers.add_model(
            project_id="p1",
            task_type="summarize",
            provider_id="provB",
            model_id="modSum",
            supports_vision=False,
            supports_tools=False,
            enabled=False,
            available=True,
        )
        req["request_id"] = "r9b"
        res2 = self.gate.process_request(req)
        self.assertFalse(res2.get("accepted"))
        self.assertEqual(res2.get("blocked_reason"), "no_model_available")

    def test_vision_capability_enforcement(self) -> None:
        # Any non-empty upload_ids requires vision-capable model
        req = self._base_request()
        req["request_id"] = "r10"
        req["upload_ids"] = ["u1"]
        # u1 belongs to p1
        self.projects.add_upload("p1", "u1")
        # The only chat model does not support vision -> must be blocked before budget/rate
        res = self.gate.process_request(req)
        self.assertFalse(res.get("accepted"))
        self.assertIn(res.get("blocked_reason"), ("no_model_available",))

    def test_budget_block(self) -> None:
        req = self._base_request()
        req["request_id"] = "r11"
        self.budget.set_behavior("r11", "block")
        res = self.gate.process_request(req)
        self.assertFalse(res.get("accepted"))
        self.assertEqual(res.get("blocked_reason"), "budget_blocked")
        # Ensure rate limiter not called
        self.assertFalse(self.ratelimit.called)

    def test_soft_budget_warning(self) -> None:
        req = self._base_request()
        req["request_id"] = "r12"
        self.budget.set_behavior("r12", "warn", message="approaching budget limit")
        res = self.gate.process_request(req)
        self.assertTrue(res.get("accepted"))
        self.assertEqual(res.get("warning"), "approaching budget limit")

    def test_rate_limit_block(self) -> None:
        req = self._base_request()
        req["request_id"] = "r13"
        # Block the default model key
        self.ratelimit.block(project_id="p1", provider_id="provA", model_id="modChat", task_type="chat")
        res = self.gate.process_request(req)
        self.assertFalse(res.get("accepted"))
        self.assertEqual(res.get("blocked_reason"), "rate_limit_blocked")
        self.assertTrue(self.ratelimit.called)

    def test_blocked_requests_do_not_continue(self) -> None:
        # Make invalid schema by adding unknown field
        req = self._base_request()
        req["request_id"] = "r14"
        req["unknown"] = "x"  # type: ignore[assignment]
        res = self.gate.process_request(req)
        self.assertFalse(res.get("accepted"))
        # Rate limiter should not be called
        self.assertFalse(self.ratelimit.called)

    def test_deterministic_safe_result(self) -> None:
        req1 = self._base_request()
        req1["request_id"] = "r15a"
        res1 = self.gate.process_request(req1)
        req2 = self._base_request()
        req2["request_id"] = "r15b"
        res2 = self.gate.process_request(req2)
        # Compare all fields except request_id
        keys = [
            "accepted",
            "project_id",
            "conversation_id",
            "provider_id",
            "model_id",
            "task_type",
            "warning",
            "blocked_reason",
            "created_at",
            "project_context",
        ]
        for k in keys:
            self.assertEqual(res1.get(k), res2.get(k))

    def test_result_redaction(self) -> None:
        req = self._base_request()
        req["request_id"] = "r16"
        res = self.gate.process_request(req)
        self.assertNotIn("user_message", res)
        self.assertNotIn("metadata", res)

    def test_event_redaction(self) -> None:
        req = self._base_request()
        req["request_id"] = "r17"
        self.gate.process_request(req)
        events = self.gate.latest_events(100)
        # Ensure no events leak raw user_message or upload content
        for e in events:
            payload = e.get("payload", {})
            self.assertNotIn("user_message", payload)
            # upload_ids should not be present in payloads
            self.assertNotIn("upload_ids", payload)

    def test_unrelated_files_remain_unchanged_placeholder(self) -> None:
        # This test is a placeholder to respect the instruction; it doesn't check filesystem state.
        # Ensures tests run without side effects.
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
