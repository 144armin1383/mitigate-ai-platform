from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.runtime.assimilation_lifecycle_hook import (
    RuntimeAssimilationLifecycleHook,
)
from agent.runtime.production_assimilation_composition import (
    build_production_assimilation_composition,
    try_build_production_assimilation_hook,
)


class FakeQueueCoordinator:
    def __init__(self):
        self.calls = []

    def enqueue(
        self,
        project_id,
        queue_reference,
        missions,
    ):
        call = {
            "project_id": project_id,
            "queue_reference": queue_reference,
            "missions": missions,
        }

        self.calls.append(call)

        return {
            "status": "queued",
            **call,
        }


class FakeReportLookup:
    def find_by_mission_id(
        self,
        mission_id,
    ):
        return None


class ProductionAssimilationCompositionTests(
    unittest.TestCase
):
    def test_builds_complete_native_composition(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            composition = (
                build_production_assimilation_composition(
                    registry_path=(
                        Path(td)
                        / "technology"
                        / "registry.json"
                    ),
                    queue_coordinator=FakeQueueCoordinator(),
                    queue_reference="missions",
                    report_lookup=FakeReportLookup(),
                )
            )

            self.assertIsInstance(
                composition.assimilation_hook,
                RuntimeAssimilationLifecycleHook,
            )

            self.assertEqual(
                type(
                    composition.lifecycle_hook
                ).__name__,
                "ProductionLifecycleDispatcher",
            )

            self.assertIsNotNone(
                composition.registry
            )

            self.assertIsNotNone(
                composition.replacement_bridge
            )

            self.assertIsNotNone(
                composition.assimilation_bridge
            )

            self.assertIsNotNone(
                composition.reconciler
            )

    def test_registry_is_persistent(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            registry_path = (
                Path(td)
                / "technology"
                / "registry.json"
            )

            composition = (
                build_production_assimilation_composition(
                    registry_path=registry_path,
                    queue_coordinator=FakeQueueCoordinator(),
                    queue_reference="missions",
                    report_lookup=FakeReportLookup(),
                )
            )

            self.assertEqual(
                composition.registry._storage_path,
                registry_path,
            )

    def test_missing_queue_coordinator_fails_closed(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(
                ValueError
            ):
                build_production_assimilation_composition(
                    registry_path=(
                        Path(td)
                        / "registry.json"
                    ),
                    queue_coordinator=None,
                    queue_reference="missions",
                    report_lookup=FakeReportLookup(),
                )

    def test_missing_report_lookup_fails_closed(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(
                ValueError
            ):
                build_production_assimilation_composition(
                    registry_path=(
                        Path(td)
                        / "registry.json"
                    ),
                    queue_coordinator=FakeQueueCoordinator(),
                    queue_reference="missions",
                    report_lookup=None,
                )

    def test_empty_queue_reference_fails_closed(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(
                ValueError
            ):
                build_production_assimilation_composition(
                    registry_path=(
                        Path(td)
                        / "registry.json"
                    ),
                    queue_coordinator=FakeQueueCoordinator(),
                    queue_reference="",
                    report_lookup=FakeReportLookup(),
                )

    def test_best_effort_builder_returns_none_on_failure(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            hook = (
                try_build_production_assimilation_hook(
                    registry_path=(
                        Path(td)
                        / "registry.json"
                    ),
                    queue_coordinator=None,
                    queue_reference="missions",
                    report_lookup=FakeReportLookup(),
                )
            )

            self.assertIsNone(
                hook
            )

    def test_best_effort_builder_returns_hook_when_valid(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            hook = (
                try_build_production_assimilation_hook(
                    registry_path=(
                        Path(td)
                        / "registry.json"
                    ),
                    queue_coordinator=FakeQueueCoordinator(),
                    queue_reference="missions",
                    report_lookup=FakeReportLookup(),
                )
            )

            self.assertEqual(
                type(hook).__name__,
                "ProductionLifecycleDispatcher",
            )

    def test_external_runtime_not_required(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            composition = (
                build_production_assimilation_composition(
                    registry_path=(
                        Path(td)
                        / "registry.json"
                    ),
                    queue_coordinator=FakeQueueCoordinator(),
                    queue_reference="missions",
                    report_lookup=FakeReportLookup(),
                )
            )

            self.assertEqual(
                [],
                composition.registry.list(),
            )


if __name__ == "__main__":
    unittest.main()


class ProductionEvaluationLifecycleCompositionTests(
    unittest.TestCase
):

    def test_composition_exposes_evaluation_reconciler_and_dispatcher(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            queue_coordinator = FakeQueueCoordinator()
            report_lookup = FakeReportLookup()

            composition = (
                build_production_assimilation_composition(
                    registry_path=(
                        root
                        / "registry.json"
                    ),
                    queue_coordinator=(
                        queue_coordinator
                    ),
                    queue_reference="missions",
                    report_lookup=report_lookup,
                )
            )

            self.assertEqual(
                type(
                    composition
                    .evaluation_reconciler
                ).__name__,
                "TechnologyEvaluationResultReconciler",
            )

            self.assertEqual(
                type(
                    composition.lifecycle_hook
                ).__name__,
                "ProductionLifecycleDispatcher",
            )

            self.assertEqual(
                type(
                    composition.assimilation_hook
                ).__name__,
                "RuntimeAssimilationLifecycleHook",
            )
