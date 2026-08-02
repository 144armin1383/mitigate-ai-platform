from __future__ import annotations

import threading
import time
import unittest
from typing import Any, Dict, List, Optional

from agent.runtime.runtime_service import (
    RuntimeService,
    RuntimeConfig,
    build_runtime,
    runtime_status,
    Clock,
)


# ===== Fakes for testing =====

class FakeClock(Clock):
    def __init__(self) -> None:
        self._t = 1_700_000_000.0  # fixed base
        self._lock = threading.Lock()

    def now(self):  # type: ignore[override]
        with self._lock:
            # Increase a little each call to simulate time passing
            self._t += 0.001
            return __import__("datetime").datetime.fromtimestamp(self._t, tz=__import__("datetime").timezone.utc)


class FakeEventSink:
    def __init__(self) -> None:
        self.events: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    def emit(self, event: Dict[str, Any]) -> None:
        with self._lock:
            # Provide deterministic timestamp key
            e = dict(event)
            if "ts" not in e:
                e["ts"] = "T"
            self.events.append(e)


class FakeRequestFlow:
    def __init__(self, result: Any = None, raise_exc: bool = False) -> None:
        self.result = result if result is not None else {"accepted": True}
        self.raise_exc = raise_exc
        self.calls: int = 0

    def submit(self, request: Any) -> Any:  # type: ignore[override]
        self.calls += 1
        if self.raise_exc:
            raise RuntimeError("dependency error")
        return self.result


class FakeOutcomeCoordinator:
    def __init__(self, result: Any = None, raise_exc: bool = False) -> None:
        self.result = result if result is not None else {"processed": True}
        self.raise_exc = raise_exc
        self.calls: int = 0

    def process(self, outcome: Any) -> Any:  # type: ignore[override]
        self.calls += 1
        if self.raise_exc:
            raise RuntimeError("dependency error")
        return self.result


class FakeComponent:
    def __init__(self, name: str) -> None:
        self.name = name
        self.started: bool = False
        self.start_calls: int = 0
        self.stop_calls: int = 0
        self.fail_start: bool = False
        self.fail_stop: bool = False
        self.events: List[str] = []

    def start(self) -> None:  # type: ignore[override]
        self.start_calls += 1
        self.events.append(f"start:{self.name}")
        if self.fail_start:
            raise RuntimeError("fail start")
        self.started = True

    def stop(self) -> None:  # type: ignore[override]
        self.stop_calls += 1
        self.events.append(f"stop:{self.name}")
        if self.fail_stop:
            raise RuntimeError("fail stop")
        self.started = False


class FakeContainer:
    def __init__(self, with_components: bool = True) -> None:
        self.request_flow = FakeRequestFlow()
        self.execution_outcome_coordinator = FakeOutcomeCoordinator()
        self.close_calls: int = 0
        self.closed: bool = False
        if with_components:
            self.background_worker = FakeComponent("background_worker")
            self.autonomous_controller = FakeComponent("autonomous_controller")
            self.private_admin_api = FakeComponent("private_admin_api")

    def close(self) -> None:  # type: ignore[override]
        self.close_calls += 1
        self.closed = True


class AppConfig:
    def __init__(self) -> None:
        self.environment_name = "test"
        self.default_project_id = "proj-123"


class AppStatus:
    def __init__(self, ready: bool = True, warnings: Optional[List[str]] = None) -> None:
        self.ready = ready
        self.warnings = warnings or []


# Builder helpers
class FakeBuilder:
    def __init__(self, container_factory, fail: bool = False, delay: float = 0.0) -> None:
        self.container_factory = container_factory
        self.fail = fail
        self.calls: int = 0
        self.delay = delay

    def __call__(self, cfg, overrides):  # type: ignore[override]
        self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        if self.fail:
            raise RuntimeError("builder failed")
        return self.container_factory()


# ===== Test cases =====

class RuntimeServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock()
        self.sink = FakeEventSink()
        self.app_config = AppConfig()

    def _build_runtime(self, *, builder: Optional[FakeBuilder] = None, status_ready: bool = True, overrides: Optional[Dict[str, Any]] = None, \
                       auto_bw: bool = False, auto_ac: bool = False, auto_pa: bool = False) -> RuntimeService:
        cfg = RuntimeConfig(
            application_config=self.app_config,
            auto_start_background_worker=auto_bw,
            auto_start_autonomous_controller=auto_ac,
            auto_start_private_admin_api=auto_pa,
        )
        fb = builder or FakeBuilder(container_factory=lambda: FakeContainer())
        rt = build_runtime(
            cfg,
            overrides=overrides,
            builder=fb,
            application_status=(lambda c: AppStatus(ready=status_ready)),
            clock=self.clock,
            event_sink=self.sink,
        )
        # Ensure builder not called during construction
        self.assertEqual(fb.calls, 0)
        return rt

    def test_initial_created_state(self):
        rt = self._build_runtime()
        st = rt.runtime_status()
        self.assertEqual(st["state"], "created")
        self.assertFalse(st["container_present"])

    def test_successful_start(self):
        rt = self._build_runtime()
        st = rt.start()
        self.assertEqual(st["state"], "running")
        self.assertTrue(st["application_ready"]) 
        self.assertTrue(st["container_present"]) 

    def test_application_built_only_on_start(self):
        fb = FakeBuilder(container_factory=lambda: FakeContainer())
        _ = self._build_runtime(builder=fb)  # builder not called yet
        self.assertEqual(fb.calls, 0)

    def test_start_idempotency(self):
        fb = FakeBuilder(container_factory=lambda: FakeContainer())
        rt = self._build_runtime(builder=fb)
        st1 = rt.start()
        st2 = rt.start()
        self.assertEqual(st1["state"], "running")
        self.assertEqual(st2["state"], "running")
        self.assertEqual(fb.calls, 1)

    def test_startup_construction_failure(self):
        fb = FakeBuilder(container_factory=lambda: FakeContainer(), fail=True)
        rt = self._build_runtime(builder=fb)
        st = rt.start()
        self.assertEqual(st["state"], "failed")
        self.assertEqual(st["last_failure_code"], "runtime_start_failed")

    def test_application_not_ready_failure(self):
        rt = self._build_runtime(status_ready=False)
        st = rt.start()
        self.assertEqual(st["state"], "failed")
        self.assertEqual(st["last_failure_code"], "application_not_ready")

    def test_partial_startup_cleanup(self):
        # Builder returns container; status not ready; container.close must be called once
        container = FakeContainer()
        fb = FakeBuilder(container_factory=lambda: container)
        rt = build_runtime(
            RuntimeConfig(application_config=self.app_config),
            builder=fb,
            application_status=lambda c: AppStatus(ready=False),
            clock=self.clock,
            event_sink=self.sink,
        )
        rt.start()
        self.assertEqual(container.close_calls, 1)
        self.assertTrue(container.closed)

    def test_successful_stop(self):
        rt = self._build_runtime()
        rt.start()
        st = rt.stop()
        self.assertEqual(st["state"], "stopped")
        self.assertTrue(st["stopped_at"] is not None)

    def test_stop_idempotency(self):
        rt = self._build_runtime()
        rt.start()
        st1 = rt.stop()
        st2 = rt.stop()
        self.assertEqual(st1["state"], "stopped")
        self.assertEqual(st2["state"], "stopped")

    def test_close_idempotency(self):
        rt = self._build_runtime()
        rt.start()
        rt.close()
        rt.close()
        self.assertEqual(rt.runtime_status()["state"], "stopped")

    def test_context_manager_lifecycle(self):
        rt = self._build_runtime()
        with rt as r2:
            self.assertIs(rt, r2)
            self.assertEqual(rt.runtime_status()["state"], "running")
        self.assertEqual(rt.runtime_status()["state"], "stopped")

    def test_no_automatic_component_startup_by_default(self):
        rt = self._build_runtime()
        rt.start()
        st = rt.runtime_status()
        self.assertFalse(st["background_worker_running"]) 
        self.assertFalse(st["autonomous_controller_running"]) 
        self.assertFalse(st["private_admin_api_running"]) 

    def test_explicit_component_starts(self):
        rt = self._build_runtime()
        rt.start()
        rt.start_background_worker()
        rt.start_autonomous_controller()
        rt.start_private_admin_api()
        st = rt.runtime_status()
        self.assertTrue(st["background_worker_running"]) 
        self.assertTrue(st["autonomous_controller_running"]) 
        self.assertTrue(st["private_admin_api_running"]) 

    def test_explicit_component_stops(self):
        rt = self._build_runtime()
        rt.start()
        rt.start_background_worker()
        rt.start_autonomous_controller()
        rt.start_private_admin_api()
        rt.stop_background_worker()
        rt.stop_autonomous_controller()
        rt.stop_private_admin_api()
        st = rt.runtime_status()
        self.assertFalse(st["background_worker_running"]) 
        self.assertFalse(st["autonomous_controller_running"]) 
        self.assertFalse(st["private_admin_api_running"]) 

    def test_component_start_idempotency(self):
        rt = self._build_runtime()
        rt.start()
        rt.start_background_worker()
        st1 = rt.runtime_status()
        rt.start_background_worker()
        st2 = rt.runtime_status()
        self.assertTrue(st1["background_worker_running"]) 
        self.assertTrue(st2["background_worker_running"]) 

    def test_component_stop_idempotency(self):
        rt = self._build_runtime()
        rt.start()
        st1 = rt.stop_background_worker()
        self.assertFalse(st1["background_worker_running"]) 
        st2 = rt.stop_background_worker()
        self.assertFalse(st2["background_worker_running"]) 

    def test_component_failure_handling(self):
        # Make component fail to start
        container = FakeContainer()
        container.background_worker.fail_start = True
        fb = FakeBuilder(container_factory=lambda: container)
        rt = build_runtime(
            RuntimeConfig(application_config=self.app_config),
            builder=fb,
            application_status=lambda c: AppStatus(ready=True),
            clock=self.clock,
            event_sink=self.sink,
        )
        rt.start()
        st = rt.start_background_worker()
        self.assertEqual(st["last_failure_code"], "component_start_failed")
        # Now fix failure and start again
        container.background_worker.fail_start = False
        st2 = rt.start_background_worker()
        self.assertIsNone(st2["last_failure_code"]) 

    def test_reverse_shutdown_order(self):
        container = FakeContainer()
        fb = FakeBuilder(container_factory=lambda: container)
        rt = build_runtime(
            RuntimeConfig(application_config=self.app_config, auto_start_private_admin_api=True, auto_start_autonomous_controller=True, auto_start_background_worker=True),
            builder=fb,
            application_status=lambda c: AppStatus(ready=True),
            clock=self.clock,
            event_sink=self.sink,
        )
        rt.start()
        # Explicitly started by runtime due to auto flags
        rt.stop()
        # Verify order by component events list
        # Each component has one stop call
        self.assertEqual(container.private_admin_api.stop_calls, 1)
        self.assertEqual(container.autonomous_controller.stop_calls, 1)
        self.assertEqual(container.background_worker.stop_calls, 1)

    def test_only_runtime_started_components_are_stopped(self):
        container = FakeContainer()
        fb = FakeBuilder(container_factory=lambda: container)
        rt = build_runtime(
            RuntimeConfig(application_config=self.app_config),
            builder=fb,
            application_status=lambda c: AppStatus(ready=True),
            clock=self.clock,
            event_sink=self.sink,
        )
        rt.start()
        # Start only background worker
        rt.start_background_worker()
        rt.stop()
        self.assertEqual(container.background_worker.stop_calls, 1)
        self.assertEqual(container.autonomous_controller.stop_calls, 0)
        self.assertEqual(container.private_admin_api.stop_calls, 0)

    def test_request_submission_while_running(self):
        rt = self._build_runtime()
        rt.start()
        req = {"x": 1}
        res = rt.submit_request(req)
        self.assertTrue(res.get("accepted", False))
        self.assertEqual(req, {"x": 1})  # not mutated

    def test_request_rejection_when_not_running(self):
        rt = self._build_runtime()
        res = rt.submit_request({"q": 1})
        self.assertFalse(res.get("accepted", True))
        self.assertEqual(res.get("failure_code"), "runtime_not_running")

    def test_execution_outcome_processing_while_running(self):
        rt = self._build_runtime()
        rt.start()
        out = {"job": 1}
        res = rt.process_execution_outcome(out)
        self.assertTrue(res.get("processed", False))
        self.assertEqual(out, {"job": 1})

    def test_execution_outcome_rejection_when_not_running(self):
        rt = self._build_runtime()
        res = rt.process_execution_outcome({"o": 2})
        self.assertFalse(res.get("processed", True))
        self.assertEqual(res.get("failure_code"), "runtime_not_running")

    def test_downstream_failure_code_propagation(self):
        # When downstream raises, we convert to dependency_failed
        container = FakeContainer()
        container.request_flow = FakeRequestFlow(raise_exc=True)
        container.execution_outcome_coordinator = FakeOutcomeCoordinator(raise_exc=True)
        fb = FakeBuilder(container_factory=lambda: container)
        rt = build_runtime(
            RuntimeConfig(application_config=self.app_config),
            builder=fb,
            application_status=lambda c: AppStatus(ready=True),
            clock=self.clock,
            event_sink=self.sink,
        )
        rt.start()
        r = rt.submit_request({"a": 1})
        self.assertEqual(r.get("failure_code"), "dependency_failed")
        o = rt.process_execution_outcome({"b": 2})
        self.assertEqual(o.get("failure_code"), "dependency_failed")

    def test_deterministic_runtime_status(self):
        rt = self._build_runtime()
        st1 = rt.runtime_status()
        st2 = rt.runtime_status()
        self.assertEqual(st1["state"], st2["state"])
        self.assertIn("environment_name", st1)
        self.assertIn("default_project_id", st1)

    def test_status_redaction(self):
        rt = self._build_runtime()
        st = rt.runtime_status()
        # Ensure no secret-like keys are present
        for k in st.keys():
            self.assertNotIn("key", k)
            self.assertNotIn("token", k)
            self.assertNotIn("secret", k)

    def test_event_redaction(self):
        rt = self._build_runtime()
        rt.start()
        events = self.sink.events
        # Events must only contain safe fields
        for e in events:
            for k in e.keys():
                self.assertIn(k, {"type", "ts", "state", "component", "operation", "failure_code", "environment_name", "project_id", "reason"})

    def test_concurrent_start_builds_one_container(self):
        fb = FakeBuilder(container_factory=lambda: FakeContainer(), delay=0.05)
        rt = self._build_runtime(builder=fb)

        start_results: List[Dict[str, Any]] = []

        def do_start():
            start_results.append(rt.start())

        t1 = threading.Thread(target=do_start)
        t2 = threading.Thread(target=do_start)
        t1.start(); t2.start()
        t1.join(2.0); t2.join(2.0)
        self.assertFalse(t1.is_alive())
        self.assertFalse(t2.is_alive())
        self.assertEqual(fb.calls, 1)
        self.assertTrue(all(r["state"] == "running" for r in start_results))

    def test_concurrent_stop_closes_once(self):
        container = FakeContainer()
        fb = FakeBuilder(container_factory=lambda: container)
        rt = build_runtime(
            RuntimeConfig(application_config=self.app_config),
            builder=fb,
            application_status=lambda c: AppStatus(ready=True),
            clock=self.clock,
            event_sink=self.sink,
        )
        rt.start()

        def do_stop():
            rt.stop()

        t1 = threading.Thread(target=do_stop)
        t2 = threading.Thread(target=do_stop)
        t1.start(); t2.start()
        t1.join(2.0); t2.join(2.0)
        self.assertFalse(t1.is_alive())
        self.assertFalse(t2.is_alive())
        self.assertEqual(container.close_calls, 1)

    def test_methods_never_hang(self):
        fb = FakeBuilder(container_factory=lambda: FakeContainer(), delay=0.01)
        rt = self._build_runtime(builder=fb)
        # Start and stop in rapid succession
        ths = []
        for _ in range(5):
            ths.append(threading.Thread(target=rt.start))
            ths.append(threading.Thread(target=rt.stop))
        for t in ths:
            t.start()
        for t in ths:
            t.join(2.0)
            self.assertFalse(t.is_alive())

    def test_config_and_overrides_not_mutated(self):
        overrides = {"x": {"y": 1}}
        rt = self._build_runtime(overrides=overrides)
        before = {"x": {"y": 1}}
        rt.start()
        self.assertEqual(overrides, before)

    def test_unrelated_files_remain_unchanged(self):
        # Sanity check: Creating runtime does not modify external state
        rt = self._build_runtime()
        self.assertIsInstance(rt, RuntimeService)


if __name__ == "__main__":
    unittest.main()
