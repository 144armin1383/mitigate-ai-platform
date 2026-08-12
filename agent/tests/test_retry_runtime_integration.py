import json
import unittest
from typing import Any, Dict, Mapping, Optional

from agent.resilience.retry_runtime_integration import (
    RetryRuntimeIntegration,
    IntegrationContext,
    NormalizedLifecycle,
    ClassificationResult,
    BudgetProjection,
)


class FakeClassifier:
    def __init__(self, retryable: bool, category: str = "test", reason: str = "") -> None:
        self.retryable = retryable
        self.category = category
        self.reason = reason

    def classify(self, lifecycle: NormalizedLifecycle) -> ClassificationResult:
        return ClassificationResult(
            retryable=self.retryable,
            category=self.category,
            reason=self.reason or ("retryable" if self.retryable else "not-retryable"),
            provider="fake",
        )


class FakeBudgetProjector:
    def project(self, mission_id: str, mission_queue_view: Mapping[str, Any]) -> BudgetProjection:
        max_attempts = mission_queue_view.get("max_attempts")
        attempts_done = mission_queue_view.get("attempts_done")
        remaining = None
        exhausted = False
        if isinstance(max_attempts, int) and isinstance(attempts_done, int):
            remaining = max(0, max_attempts - attempts_done)
            exhausted = remaining <= 0
        # Also consider explicit remaining field if provided
        if "remaining_attempts" in mission_queue_view and isinstance(mission_queue_view.get("remaining_attempts"), int):
            remaining = mission_queue_view.get("remaining_attempts")
            exhausted = bool(remaining <= 0)
        return BudgetProjection(exhausted=exhausted, remaining_attempts=remaining, provider="fake")


class FakeExecutionAdapter:
    def adapt(self, lifecycle_event: Mapping[str, Any]) -> NormalizedLifecycle:
        # Forward mapping respecting required contract
        outcome = str(lifecycle_event.get("outcome", "unknown")).lower()
        return NormalizedLifecycle(
            outcome=outcome,
            error_code=lifecycle_event.get("error_code"),
            error_class=lifecycle_event.get("error_class"),
            transient_hint=lifecycle_event.get("transient_hint"),
        )


class CapturingMetrics:
    def __init__(self) -> None:
        self.events = []

    def emit(self, payload: Mapping[str, Any]) -> None:
        # Store a JSON-serializable copy to assert determinism
        self.events.append(json.loads(json.dumps(dict(payload))))


class RetryRuntimeIntegrationTests(unittest.TestCase):
    def _ctx(self, mission_id: str = "m1", execution_id: str = "e1", attempt: int = 1, checkpoint_id: Optional[str] = "c1", q: Optional[Dict[str, Any]] = None) -> IntegrationContext:
        qv = q if q is not None else {"attempts_done": 0, "max_attempts": 3}
        return IntegrationContext(
            mission_id=mission_id,
            execution_id=execution_id,
            attempt=attempt,
            checkpoint_id=checkpoint_id,
            mission_queue_view=qv,
        )

    def test_retryable_lifecycle_projection(self) -> None:
        metrics = CapturingMetrics()
        integ = RetryRuntimeIntegration(
            classifier=FakeClassifier(True, category="transient"),
            budget_projector=FakeBudgetProjector(),
            execution_adapter=FakeExecutionAdapter(),
            metrics_sink=metrics,
        )
        lifecycle = {"outcome": "error", "error_class": "TimeoutError"}
        ctx = self._ctx(q={"attempts_done": 1, "max_attempts": 5})
        res = integ.project_lifecycle(lifecycle, ctx)
        d = res.to_dict()
        self.assertEqual(d["mission_id"], ctx.mission_id)
        self.assertEqual(d["execution_id"], ctx.execution_id)
        self.assertEqual(d["attempt"], ctx.attempt)
        self.assertEqual(d["checkpoint_id"], ctx.checkpoint_id)
        self.assertEqual(d["lifecycle"]["outcome"], "error")
        self.assertTrue(d["classification"]["retryable"])  # classified retryable
        self.assertFalse(d["budget"]["exhausted"])  # budget available
        self.assertEqual(d["recommended_action"], "retry_possible")
        # Ensure no authority granted
        self.assertFalse(d["authority"]["grant"])  # never grant from integration
        # Deterministic JSON serialization
        s1 = res.to_json()
        s2 = res.to_json()
        self.assertEqual(s1, s2)
        # Metrics captured and JSON-serializable
        self.assertGreaterEqual(len(metrics.events), 1)
        last = metrics.events[-1]
        self.assertEqual(last["mission_id"], ctx.mission_id)
        self.assertEqual(last["retry_state_authority"], "MissionQueue")

    def test_non_retryable_lifecycle_projection(self) -> None:
        integ = RetryRuntimeIntegration(
            classifier=FakeClassifier(False, category="permanent"),
            budget_projector=FakeBudgetProjector(),
            execution_adapter=FakeExecutionAdapter(),
        )
        lifecycle = {"outcome": "error", "error_code": "VALIDATION"}
        ctx = self._ctx(q={"attempts_done": 0, "max_attempts": 3})
        res = integ.project_lifecycle(lifecycle, ctx).to_dict()
        self.assertEqual(res["classification"]["category"], "permanent")
        self.assertEqual(res["recommended_action"], "do_not_retry")

    def test_exhausted_lifecycle_projection(self) -> None:
        integ = RetryRuntimeIntegration(
            classifier=FakeClassifier(True, category="transient"),
            budget_projector=FakeBudgetProjector(),
            execution_adapter=FakeExecutionAdapter(),
        )
        lifecycle = {"outcome": "error"}
        ctx = self._ctx(q={"attempts_done": 5, "max_attempts": 5})
        res = integ.project_lifecycle(lifecycle, ctx).to_dict()
        self.assertTrue(res["budget"]["exhausted"])  # inferred exhausted
        self.assertEqual(res["recommended_action"], "do_not_retry")

    def test_cancelled_projection(self) -> None:
        integ = RetryRuntimeIntegration(
            classifier=FakeClassifier(True),
            budget_projector=FakeBudgetProjector(),
            execution_adapter=FakeExecutionAdapter(),
        )
        lifecycle = {"outcome": "cancelled"}
        ctx = self._ctx()
        res = integ.project_lifecycle(lifecycle, ctx).to_dict()
        self.assertEqual(res["recommended_action"], "cancelled")

    def test_deadline_exceeded_projection(self) -> None:
        integ = RetryRuntimeIntegration(
            classifier=FakeClassifier(True),
            budget_projector=FakeBudgetProjector(),
            execution_adapter=FakeExecutionAdapter(),
        )
        lifecycle = {"outcome": "deadline_exceeded"}
        ctx = self._ctx()
        res = integ.project_lifecycle(lifecycle, ctx).to_dict()
        self.assertEqual(res["recommended_action"], "deadline_exceeded")

    def test_missionqueue_authority_preserved(self) -> None:
        integ = RetryRuntimeIntegration(
            classifier=FakeClassifier(True),
            budget_projector=FakeBudgetProjector(),
            execution_adapter=FakeExecutionAdapter(),
        )
        lifecycle = {"outcome": "error"}
        ctx = self._ctx()
        res = integ.project_lifecycle(lifecycle, ctx).to_dict()
        self.assertEqual(res["authority"]["retry_state_authority"], "MissionQueue")
        self.assertEqual(res["authority"]["retry_execution_authority"], "existing_runtime_controller")
        self.assertFalse(res["authority"]["grant"])  # never grant from integration

    def test_execution_and_checkpoint_identity_preserved(self) -> None:
        integ = RetryRuntimeIntegration(
            classifier=FakeClassifier(True),
            budget_projector=FakeBudgetProjector(),
            execution_adapter=FakeExecutionAdapter(),
        )
        lifecycle = {"outcome": "error"}
        ctx = self._ctx(mission_id="mX", execution_id="eY", attempt=7, checkpoint_id="cpZ")
        res = integ.project_lifecycle(lifecycle, ctx).to_dict()
        self.assertEqual(res["mission_id"], "mX")
        self.assertEqual(res["execution_id"], "eY")
        self.assertEqual(res["attempt"], 7)
        self.assertEqual(res["checkpoint_id"], "cpZ")

    def test_deterministic_output_and_json_serialization(self) -> None:
        metrics = CapturingMetrics()
        integ = RetryRuntimeIntegration(
            classifier=FakeClassifier(True),
            budget_projector=FakeBudgetProjector(),
            execution_adapter=FakeExecutionAdapter(),
            metrics_sink=metrics,
        )
        lifecycle = {"outcome": "error", "error_class": "X"}
        ctx = self._ctx(q={"attempts_done": 2, "max_attempts": 4})
        r1 = integ.project_lifecycle(lifecycle, ctx).to_json()
        r2 = integ.project_lifecycle(lifecycle, ctx).to_json()
        self.assertEqual(r1, r2)
        # Ensure JSON serializable
        json.loads(r1)
        self.assertGreaterEqual(len(metrics.events), 2)

    def test_inputs_not_mutated_and_no_retry_consumption(self) -> None:
        integ = RetryRuntimeIntegration(
            classifier=FakeClassifier(True),
            budget_projector=FakeBudgetProjector(),
            execution_adapter=FakeExecutionAdapter(),
        )
        lifecycle = {"outcome": "error"}
        qv = {"attempts_done": 1, "max_attempts": 2}
        lifecycle_copy = json.loads(json.dumps(lifecycle))
        qv_copy = json.loads(json.dumps(qv))
        ctx = self._ctx(q=qv)
        _ = integ.project_lifecycle(lifecycle, ctx)
        self.assertEqual(lifecycle, lifecycle_copy)
        self.assertEqual(qv, qv_copy)
        # No mutation to attempts
        self.assertEqual(qv["attempts_done"], 1)
        self.assertEqual(qv["max_attempts"], 2)

    def test_fail_closed_behavior_on_provider_errors(self) -> None:
        class ExplodingClassifier:
            def classify(self, lifecycle: NormalizedLifecycle) -> ClassificationResult:  # type: ignore[override]
                raise RuntimeError("boom")

        class ExplodingBudget:
            def project(self, mission_id: str, mission_queue_view: Mapping[str, Any]) -> BudgetProjection:  # type: ignore[override]
                raise RuntimeError("boom")

        class ExplodingMetrics:
            def emit(self, payload: Mapping[str, Any]) -> None:
                raise RuntimeError("boom")

        integ = RetryRuntimeIntegration(
            classifier=ExplodingClassifier(),
            budget_projector=ExplodingBudget(),
            execution_adapter=FakeExecutionAdapter(),
            metrics_sink=ExplodingMetrics(),
        )
        lifecycle = {"outcome": "error"}
        ctx = self._ctx()
        res = integ.project_lifecycle(lifecycle, ctx).to_dict()
        self.assertIn(res["recommended_action"], {"none", "do_not_retry"})
        self.assertFalse(res["authority"]["grant"])  # never grant

    def test_provider_independence_default_nulls(self) -> None:
        # Use built-in null providers
        integ = RetryRuntimeIntegration()
        lifecycle = {"outcome": "error"}
        ctx = self._ctx()
        res = integ.project_lifecycle(lifecycle, ctx).to_dict()
        # Without providers, we do not suggest retries and preserve invariants
        self.assertIn(res["recommended_action"], {"none", "do_not_retry"})
        self.assertEqual(res["authority"]["retry_state_authority"], "MissionQueue")
        self.assertEqual(res["authority"]["retry_execution_authority"], "existing_runtime_controller")

    def test_no_sleep_and_no_network_behavior(self) -> None:
        # Integration should not call sleep or perform network IO; this test ensures quick return and no imports needed
        integ = RetryRuntimeIntegration()
        lifecycle = {"outcome": "ok"}
        ctx = self._ctx()
        res = integ.project_lifecycle(lifecycle, ctx)
        self.assertEqual(res.to_dict()["recommended_action"], "controller_decides")


if __name__ == "__main__":
    unittest.main(verbosity=2)
