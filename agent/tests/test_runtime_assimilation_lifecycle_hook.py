from __future__ import annotations

import unittest

from agent.runtime.assimilation_lifecycle_hook import (
    RuntimeAssimilationLifecycleHook,
)


class FakeResult:
    def __init__(
        self,
        status="in_progress",
    ):
        self.status = status


class FakeReconciler:
    def __init__(self):
        self.calls = []

    def reconcile(
        self,
        technology_id,
    ):
        self.calls.append(
            technology_id
        )

        return FakeResult()


class RuntimeAssimilationLifecycleHookTests(
    unittest.TestCase
):
    def _mission(self):
        return {
            "id": "native-replacement-123",
            "task_type":
                "native_capability_replacement",
            "payload": {
                "resilience": {
                    "mode":
                        "native_replacement",
                    "capability":
                        "agent_orchestration",
                    "native_only":
                        True,
                    "external_runtime_dependency_allowed":
                        False,
                    "source_context": {
                        "technology":
                            "ruflo",
                    },
                },
            },
        }

    def _report(self):
        return {
            "mission_id":
                "native-replacement-123",
            "status":
                "completed",
            "success":
                True,
            "validation_status":
                "validated",
            "metadata": {
                "merged_to_main":
                    True,
            },
        }

    def test_native_replacement_is_reconciled(
        self,
    ):
        reconciler = FakeReconciler()

        hook = (
            RuntimeAssimilationLifecycleHook(
                reconciler=reconciler
            )
        )

        result = hook.after_persist(
            mission=self._mission(),
            report=self._report(),
        )

        self.assertTrue(
            result["handled"]
        )

        self.assertEqual(
            ["ruflo"],
            reconciler.calls,
        )

    def test_ordinary_mission_is_ignored(
        self,
    ):
        reconciler = FakeReconciler()

        hook = (
            RuntimeAssimilationLifecycleHook(
                reconciler=reconciler
            )
        )

        mission = self._mission()
        mission["task_type"] = (
            "documentation"
        )

        result = hook.after_persist(
            mission=mission,
            report=self._report(),
        )

        self.assertFalse(
            result["handled"]
        )

        self.assertEqual(
            [],
            reconciler.calls,
        )

    def test_missing_technology_is_ignored(
        self,
    ):
        reconciler = FakeReconciler()

        hook = (
            RuntimeAssimilationLifecycleHook(
                reconciler=reconciler
            )
        )

        mission = self._mission()

        mission[
            "payload"
        ][
            "resilience"
        ][
            "source_context"
        ] = {}

        result = hook.after_persist(
            mission=mission,
            report=self._report(),
        )

        self.assertFalse(
            result["handled"]
        )

        self.assertEqual(
            [],
            reconciler.calls,
        )

    def test_report_mismatch_is_rejected(
        self,
    ):
        reconciler = FakeReconciler()

        hook = (
            RuntimeAssimilationLifecycleHook(
                reconciler=reconciler
            )
        )

        report = self._report()
        report["mission_id"] = (
            "different-mission"
        )

        result = hook.after_persist(
            mission=self._mission(),
            report=report,
        )

        self.assertFalse(
            result["handled"]
        )

        self.assertEqual(
            [],
            reconciler.calls,
        )


if __name__ == "__main__":
    unittest.main()
