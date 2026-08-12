from __future__ import annotations

import unittest
from dataclasses import dataclass

from agent.runtime.production_lifecycle_dispatcher import (
    ProductionLifecycleDispatcher,
)


@dataclass
class FakeEvaluationResult:
    handled: bool = True
    technology_id: str | None = "ruflo"
    recommendation: str | None = (
        "assimilate_candidate"
    )
    evaluation_state: str | None = "passed"
    assimilation_state: str | None = (
        "candidate"
    )
    reason: str | None = None
    idempotent: bool = False


class FakeEvaluationReconciler:

    def __init__(
        self,
        *,
        fail: bool = False,
    ) -> None:
        self.calls = []
        self.fail = fail

    def reconcile(
        self,
        *,
        mission,
        report,
    ):
        self.calls.append(
            (
                mission,
                report,
            )
        )

        if self.fail:
            raise ValueError(
                "evaluation failure"
            )

        return FakeEvaluationResult()


class FakeAssimilationHook:

    def __init__(self) -> None:
        self.calls = []

    def after_persist(
        self,
        *,
        mission,
        report,
    ):
        self.calls.append(
            (
                mission,
                report,
            )
        )

        return {
            "handled": True,
            "technology_id": "ruflo",
            "status": "complete",
        }


class ProductionLifecycleDispatcherTests(
    unittest.TestCase
):

    def make_dispatcher(
        self,
        *,
        evaluation=None,
        assimilation=None,
    ):
        return ProductionLifecycleDispatcher(
            evaluation_reconciler=(
                evaluation
                or FakeEvaluationReconciler()
            ),
            assimilation_hook=(
                assimilation
                or FakeAssimilationHook()
            ),
        )

    def test_technology_evaluation_routes_to_reconciler(
        self,
    ) -> None:
        evaluation = (
            FakeEvaluationReconciler()
        )

        assimilation = (
            FakeAssimilationHook()
        )

        dispatcher = self.make_dispatcher(
            evaluation=evaluation,
            assimilation=assimilation,
        )

        mission = {
            "task_type":
                "technology_evaluation",
        }

        report = {
            "status":
                "completed",
        }

        result = dispatcher.after_persist(
            mission=mission,
            report=report,
        )

        self.assertTrue(
            result["handled"]
        )

        self.assertEqual(
            result["lifecycle"],
            "technology_evaluation",
        )

        self.assertEqual(
            result["technology_id"],
            "ruflo",
        )

        self.assertEqual(
            result["evaluation_state"],
            "passed",
        )

        self.assertEqual(
            result["assimilation_state"],
            "candidate",
        )

        self.assertEqual(
            len(evaluation.calls),
            1,
        )

        self.assertEqual(
            assimilation.calls,
            [],
        )

    def test_native_replacement_routes_to_existing_hook(
        self,
    ) -> None:
        evaluation = (
            FakeEvaluationReconciler()
        )

        assimilation = (
            FakeAssimilationHook()
        )

        dispatcher = self.make_dispatcher(
            evaluation=evaluation,
            assimilation=assimilation,
        )

        result = dispatcher.after_persist(
            mission={
                "task_type":
                    "native_capability_replacement",
            },
            report={
                "status":
                    "completed",
            },
        )

        self.assertTrue(
            result["handled"]
        )

        self.assertEqual(
            result["lifecycle"],
            "native_assimilation",
        )

        self.assertEqual(
            evaluation.calls,
            [],
        )

        self.assertEqual(
            len(assimilation.calls),
            1,
        )

    def test_ordinary_mission_is_ignored(
        self,
    ) -> None:
        evaluation = (
            FakeEvaluationReconciler()
        )

        assimilation = (
            FakeAssimilationHook()
        )

        dispatcher = self.make_dispatcher(
            evaluation=evaluation,
            assimilation=assimilation,
        )

        result = dispatcher.after_persist(
            mission={
                "task_type":
                    "general",
            },
            report={},
        )

        self.assertFalse(
            result["handled"]
        )

        self.assertEqual(
            result["reason"],
            "unsupported_task_type",
        )

        self.assertEqual(
            evaluation.calls,
            [],
        )

        self.assertEqual(
            assimilation.calls,
            [],
        )

    def test_invalid_mission_is_ignored(
        self,
    ) -> None:
        dispatcher = self.make_dispatcher()

        result = dispatcher.after_persist(
            mission=None,
            report={},
        )

        self.assertFalse(
            result["handled"]
        )

        self.assertEqual(
            result["reason"],
            "invalid_mission",
        )

    def test_evaluation_failure_propagates_to_worker_boundary(
        self,
    ) -> None:
        dispatcher = self.make_dispatcher(
            evaluation=(
                FakeEvaluationReconciler(
                    fail=True
                )
            )
        )

        with self.assertRaises(
            ValueError
        ):
            dispatcher.after_persist(
                mission={
                    "task_type":
                        "technology_evaluation",
                },
                report={},
            )


if __name__ == "__main__":
    unittest.main()
