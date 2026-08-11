from __future__ import annotations

import unittest

from agent.resilience.replacement_mission_bridge import (
    NativeReplacementMissionBridge,
)
from agent.technology.assimilation_mission_bridge import (
    NativeAssimilationMissionBridge,
    NativeAssimilationRequest,
)
from agent.technology.assimilation_reconciler import (
    AssimilationLifecycleReconciler,
)
from agent.technology.registry import (
    AssimilationState,
    EvaluationState,
    TechnologyKind,
    TechnologyRecord,
    TechnologyRegistry,
    TechnologyState,
)


class FakeQueue:
    def enqueue(
        self,
        project_id,
        queue_reference,
        missions,
    ):
        return {
            "project_id": project_id,
            "queue_reference": queue_reference,
            "missions": missions,
        }


class FakeReportLookup:
    def __init__(
        self,
        reports=None,
    ):
        self.reports = dict(
            reports or {}
        )
        self.calls = []

    def find_by_mission_id(
        self,
        mission_id,
    ):
        self.calls.append(
            mission_id
        )

        return self.reports.get(
            mission_id
        )


class AssimilationLifecycleReconcilerTests(
    unittest.TestCase
):
    def setUp(self):
        self.registry = TechnologyRegistry()

        self.registry.register(
            TechnologyRecord(
                technology_id="ruflo",
                name="Ruflo",
                kind=TechnologyKind.ORCHESTRATOR,
                state=TechnologyState.EVALUATING,
                evaluation_state=EvaluationState.PASSED,
                assimilation_state=(
                    AssimilationState.CANDIDATE
                ),
                capabilities=[
                    "agent_orchestration",
                    "workflow_coordination",
                ],
            )
        )

        replacement_bridge = (
            NativeReplacementMissionBridge(
                queue_coordinator=FakeQueue(),
                queue_reference="missions",
            )
        )

        self.assimilation_bridge = (
            NativeAssimilationMissionBridge(
                registry=self.registry,
                replacement_bridge=(
                    replacement_bridge
                ),
            )
        )

        self.missions = (
            self.assimilation_bridge.plan(
                NativeAssimilationRequest(
                    project_id=(
                        "mitigate-ai-platform"
                    ),
                    technology_id="ruflo",
                    outcome=(
                        "assimilate_candidate"
                    ),
                    capabilities=[
                        "agent_orchestration",
                        "workflow_coordination",
                    ],
                    reason="native assimilation",
                )
            )
        )

        self.registry.update(
            "ruflo",
            assimilation_state=(
                AssimilationState.IN_PROGRESS
            ),
        )

    def _report(
        self,
        mission,
        *,
        status="completed",
        success=True,
        validation_status="validated",
        merged_to_main=True,
        project_id="mitigate-ai-platform",
        mission_id=None,
        safe_error_code=None,
    ):
        return {
            "execution_id":
                "exec-" + mission["mission_id"],
            "project_id": project_id,
            "mission_id": (
                mission_id
                or mission["mission_id"]
            ),
            "status": status,
            "success": success,
            "validation_status":
                validation_status,
            "safe_error_code":
                safe_error_code,
            "metadata": {
                "merged_to_main":
                    merged_to_main,
            },
        }

    def _reconciler(
        self,
        reports=None,
    ):
        return AssimilationLifecycleReconciler(
            registry=self.registry,
            assimilation_bridge=(
                self.assimilation_bridge
            ),
            report_lookup=(
                FakeReportLookup(
                    reports
                )
            ),
        )

    def test_missing_report_remains_pending(self):
        result = (
            self._reconciler()
            .reconcile(
                "ruflo"
            )
        )

        self.assertEqual(
            "pending",
            result.status,
        )

        self.assertEqual(
            2,
            result.pending_missions,
        )

    def test_retrying_report_remains_pending(self):
        mission = self.missions[0]

        result = self._reconciler(
            {
                mission["mission_id"]:
                    self._report(
                        mission,
                        status="retrying",
                        success=False,
                        validation_status=None,
                        merged_to_main=False,
                    )
            }
        ).reconcile(
            "ruflo"
        )

        self.assertGreaterEqual(
            result.pending_missions,
            1,
        )

    def test_valid_completed_report_marks_native(self):
        first = self.missions[0]

        result = self._reconciler(
            {
                first["mission_id"]:
                    self._report(first),
            }
        ).reconcile(
            "ruflo"
        )

        self.assertIn(
            first["step_id"],
            result.native_capabilities,
        )

    def test_completed_without_validation_fails(self):
        first = self.missions[0]

        result = self._reconciler(
            {
                first["mission_id"]:
                    self._report(
                        first,
                        validation_status=None,
                    ),
            }
        ).reconcile(
            "ruflo"
        )

        self.assertEqual(
            1,
            result.failed_missions,
        )

    def test_completed_without_merge_fails(self):
        first = self.missions[0]

        result = self._reconciler(
            {
                first["mission_id"]:
                    self._report(
                        first,
                        merged_to_main=False,
                    ),
            }
        ).reconcile(
            "ruflo"
        )

        self.assertEqual(
            1,
            result.failed_missions,
        )

    def test_failed_report_fails(self):
        first = self.missions[0]

        result = self._reconciler(
            {
                first["mission_id"]:
                    self._report(
                        first,
                        status="failed",
                        success=False,
                        validation_status=None,
                        merged_to_main=False,
                    ),
            }
        ).reconcile(
            "ruflo"
        )

        self.assertEqual(
            "failed",
            result.status,
        )

    def test_blocked_report_fails(self):
        first = self.missions[0]

        result = self._reconciler(
            {
                first["mission_id"]:
                    self._report(
                        first,
                        status="blocked",
                        success=False,
                        validation_status=None,
                        merged_to_main=False,
                    ),
            }
        ).reconcile(
            "ruflo"
        )

        self.assertEqual(
            "failed",
            result.status,
        )

    def test_cancelled_report_fails(self):
        first = self.missions[0]

        result = self._reconciler(
            {
                first["mission_id"]:
                    self._report(
                        first,
                        status="cancelled",
                        success=False,
                        validation_status=None,
                        merged_to_main=False,
                    ),
            }
        ).reconcile(
            "ruflo"
        )

        self.assertEqual(
            "failed",
            result.status,
        )

    def test_mixed_success_pending_is_in_progress(self):
        first = self.missions[0]

        result = self._reconciler(
            {
                first["mission_id"]:
                    self._report(first),
            }
        ).reconcile(
            "ruflo"
        )

        self.assertEqual(
            "in_progress",
            result.status,
        )

    def test_mixed_success_failure_does_not_complete(self):
        first = self.missions[0]
        second = self.missions[1]

        result = self._reconciler(
            {
                first["mission_id"]:
                    self._report(first),
                second["mission_id"]:
                    self._report(
                        second,
                        status="failed",
                        success=False,
                        validation_status=None,
                        merged_to_main=False,
                    ),
            }
        ).reconcile(
            "ruflo"
        )

        self.assertEqual(
            "failed",
            result.status,
        )

        self.assertNotEqual(
            AssimilationState.COMPLETE,
            self.registry.get(
                "ruflo"
            ).assimilation_state,
        )

    def test_all_successful_completes_assimilation(self):
        reports = {
            mission["mission_id"]:
                self._report(
                    mission
                )
            for mission in self.missions
        }

        result = self._reconciler(
            reports
        ).reconcile(
            "ruflo"
        )

        self.assertEqual(
            "complete",
            result.status,
        )

        record = self.registry.get(
            "ruflo"
        )

        self.assertEqual(
            TechnologyState.NATIVE_REPLACED,
            record.state,
        )

        self.assertEqual(
            AssimilationState.COMPLETE,
            record.assimilation_state,
        )

    def test_project_id_mismatch_fails_closed(self):
        first = self.missions[0]

        result = self._reconciler(
            {
                first["mission_id"]:
                    self._report(
                        first,
                        project_id="other-project",
                    ),
            }
        ).reconcile(
            "ruflo"
        )

        self.assertEqual(
            1,
            result.failed_missions,
        )

    def test_mission_id_mismatch_fails_closed(self):
        first = self.missions[0]

        result = self._reconciler(
            {
                first["mission_id"]:
                    self._report(
                        first,
                        mission_id="other-mission",
                    ),
            }
        ).reconcile(
            "ruflo"
        )

        self.assertEqual(
            1,
            result.failed_missions,
        )

    def test_malformed_metadata_fails_closed(self):
        record = self.registry.get(
            "ruflo"
        )

        self.registry.update(
            "ruflo",
            metadata={},
        )

        with self.assertRaises(
            ValueError
        ):
            self._reconciler().reconcile(
                "ruflo"
            )

    def test_mismatched_lists_fail_closed(self):
        record = self.registry.get(
            "ruflo"
        )

        metadata = dict(
            record.metadata
        )

        assimilation = dict(
            metadata["assimilation"]
        )

        assimilation[
            "mission_ids"
        ] = assimilation[
            "mission_ids"
        ][:1]

        metadata[
            "assimilation"
        ] = assimilation

        self.registry.update(
            "ruflo",
            metadata=metadata,
        )

        with self.assertRaises(
            ValueError
        ):
            self._reconciler().reconcile(
                "ruflo"
            )

    def test_repeated_reconciliation_is_idempotent(self):
        reports = {
            mission["mission_id"]:
                self._report(
                    mission
                )
            for mission in self.missions
        }

        reconciler = self._reconciler(
            reports
        )

        first = reconciler.reconcile(
            "ruflo"
        )

        second = reconciler.reconcile(
            "ruflo"
        )

        self.assertEqual(
            "complete",
            first.status,
        )

        self.assertEqual(
            "complete",
            second.status,
        )

        adopted = self.registry.get(
            "ruflo"
        ).adopted_capabilities

        self.assertEqual(
            len(adopted),
            len(set(adopted)),
        )

    def test_already_complete_remains_complete(self):
        self.registry.update(
            "ruflo",
            state=(
                TechnologyState.NATIVE_REPLACED
            ),
            assimilation_state=(
                AssimilationState.COMPLETE
            ),
            adopted_capabilities=[
                "agent_orchestration",
                "workflow_coordination",
            ],
            native_replacement_available=True,
            external_runtime_required=False,
        )

        result = self._reconciler().reconcile(
            "ruflo"
        )

        self.assertEqual(
            "complete",
            result.status,
        )

    def test_no_execution_authority_introduced(self):
        import inspect
        from agent.technology.assimilation_reconciler import (
            AssimilationLifecycleReconciler,
        )

        source = inspect.getsource(
            AssimilationLifecycleReconciler
        )

        forbidden = (
            ".enqueue(",
            "subprocess",
            "BackgroundWorker",
            "MissionQueue",
            "retry(",
        )

        for marker in forbidden:
            self.assertNotIn(
                marker,
                source,
            )

    def test_external_runtime_remains_false(self):
        first = self.missions[0]

        self._reconciler(
            {
                first["mission_id"]:
                    self._report(
                        first
                    )
            }
        ).reconcile(
            "ruflo"
        )

        self.assertFalse(
            self.registry.get(
                "ruflo"
            ).external_runtime_required
        )

    def test_completion_invariant_is_preserved(self):
        first = self.missions[0]

        result = self._reconciler(
            {
                first["mission_id"]:
                    self._report(
                        first
                    )
            }
        ).reconcile(
            "ruflo"
        )

        self.assertNotEqual(
            "complete",
            result.status,
        )


if __name__ == "__main__":
    unittest.main()
