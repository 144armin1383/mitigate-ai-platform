from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent.technology.evaluation_result_reconciler import (
    TechnologyEvaluationResultReconciler,
)
from agent.technology.registry import (
    AssimilationState,
    EvaluationState,
    TechnologyKind,
    TechnologyRecord,
    TechnologyRegistry,
    TechnologyState,
)


class TechnologyEvaluationResultReconcilerTests(
    unittest.TestCase
):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(
            self.tmp.name
        )

        self.registry = TechnologyRegistry(
            storage_path=(
                self.root
                / "registry.json"
            ),
            clock=lambda:
                "2026-08-12T00:00:00Z",
        )

        self.registry.register(
            TechnologyRecord(
                technology_id="ruflo",
                name="Ruflo",
                kind=TechnologyKind.ORCHESTRATOR,
                state=TechnologyState.WATCHING,
                evaluation_state=(
                    EvaluationState.NOT_EVALUATED
                ),
                assimilation_state=(
                    AssimilationState.NONE
                ),
                latest_observed_version="3.37.0",
                external_runtime_required=False,
                capabilities=[
                    "flow_spec",
                    "retry_policy",
                ],
                metadata={
                    "existing": {
                        "preserved": True
                    }
                },
            )
        )

        self.reconciler = (
            TechnologyEvaluationResultReconciler(
                registry=self.registry,
                repository_root=self.root,
                clock=lambda:
                    "2026-08-12T00:00:01Z",
            )
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def mission(
        self,
    ) -> dict:
        return {
            "mission_id":
                "technology-evaluation-test",
            "request_id":
                "technology-evaluation-test",
            "project_id":
                "mitigate-ai-platform",
            "task_type":
                "technology_evaluation",
            "payload": {
                "technology_evaluation": {
                    "technology_id":
                        "ruflo",
                    "observed_version":
                        "3.37.0",
                },
                "evaluation_requirements": {
                    "require_human_review_before_adoption":
                        True,
                },
                "deliverables": [
                    (
                        "docs/technology/evaluations/"
                        "ruflo/3.37.0.json"
                    )
                ],
            },
        }

    def report(
        self,
    ) -> dict:
        return {
            "mission_id":
                "technology-evaluation-test",
            "request_id":
                "technology-evaluation-test",
            "project_id":
                "mitigate-ai-platform",
            "task_type":
                "technology_evaluation",
            "status":
                "completed",
            "success":
                True,
            "validation_status":
                "validated",
            "execution_id":
                "exec-test",
            "metadata": {
                "merged_to_main":
                    True,
            },
        }

    def write_artifact(
        self,
        *,
        recommendation: str = (
            "assimilate_candidate"
        ),
        mission_id: str = (
            "technology-evaluation-test"
        ),
        technology_id: str = "ruflo",
        observed_version: str = "3.37.0",
    ) -> None:
        path = (
            self.root
            / "docs/technology/evaluations/"
            / "ruflo/3.37.0.json"
        )

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        path.write_text(
            json.dumps(
                {
                    "metadata": {
                        "mission_id":
                            mission_id,
                        "request_id":
                            mission_id,
                        "technology_id":
                            technology_id,
                        "observed_version":
                            observed_version,
                    },
                    "recommendation": {
                        "value":
                            recommendation,
                        "confidence":
                            0.72,
                    },
                    "adoption_policy": {
                        "activation_allowed":
                            False,
                        "external_runtime_dependency_allowed":
                            False,
                        "installation_allowed":
                            False,
                        "runtime_adoption_allowed":
                            False,
                    },
                }
            ),
            encoding="utf-8",
        )

    def test_valid_completed_evaluation_passes(
        self,
    ) -> None:
        self.write_artifact()

        result = self.reconciler.reconcile(
            mission=self.mission(),
            report=self.report(),
        )

        record = self.registry.get(
            "ruflo"
        )

        self.assertTrue(
            result.handled
        )

        self.assertEqual(
            record.evaluation_state,
            EvaluationState.PASSED,
        )

    def test_assimilate_candidate_becomes_candidate(
        self,
    ) -> None:
        self.write_artifact()

        self.reconciler.reconcile(
            mission=self.mission(),
            report=self.report(),
        )

        record = self.registry.get(
            "ruflo"
        )

        self.assertEqual(
            record.assimilation_state,
            AssimilationState.CANDIDATE,
        )

        self.assertEqual(
            record.state,
            TechnologyState.WATCHING,
        )

    def test_repeated_reconciliation_is_idempotent(
        self,
    ) -> None:
        self.write_artifact()

        first = self.reconciler.reconcile(
            mission=self.mission(),
            report=self.report(),
        )

        second = self.reconciler.reconcile(
            mission=self.mission(),
            report=self.report(),
        )

        self.assertFalse(
            first.idempotent
        )

        self.assertTrue(
            second.idempotent
        )

    def test_failed_report_is_rejected(
        self,
    ) -> None:
        self.write_artifact()

        report = self.report()
        report["status"] = "failed"
        report["success"] = False

        with self.assertRaises(
            ValueError
        ):
            self.reconciler.reconcile(
                mission=self.mission(),
                report=report,
            )

    def test_unvalidated_report_is_rejected(
        self,
    ) -> None:
        self.write_artifact()

        report = self.report()
        report[
            "validation_status"
        ] = "failed"

        with self.assertRaises(
            ValueError
        ):
            self.reconciler.reconcile(
                mission=self.mission(),
                report=report,
            )

    def test_unmerged_report_is_rejected(
        self,
    ) -> None:
        self.write_artifact()

        report = self.report()
        report["metadata"][
            "merged_to_main"
        ] = False

        with self.assertRaises(
            ValueError
        ):
            self.reconciler.reconcile(
                mission=self.mission(),
                report=report,
            )

    def test_mission_report_mismatch_rejected(
        self,
    ) -> None:
        self.write_artifact()

        report = self.report()
        report[
            "mission_id"
        ] = "other-mission"

        with self.assertRaises(
            ValueError
        ):
            self.reconciler.reconcile(
                mission=self.mission(),
                report=report,
            )

    def test_artifact_technology_mismatch_rejected(
        self,
    ) -> None:
        self.write_artifact(
            technology_id="other"
        )

        with self.assertRaises(
            ValueError
        ):
            self.reconciler.reconcile(
                mission=self.mission(),
                report=self.report(),
            )

    def test_artifact_mission_mismatch_rejected(
        self,
    ) -> None:
        self.write_artifact(
            mission_id="other-mission"
        )

        with self.assertRaises(
            ValueError
        ):
            self.reconciler.reconcile(
                mission=self.mission(),
                report=self.report(),
            )

    def test_artifact_version_mismatch_rejected(
        self,
    ) -> None:
        self.write_artifact(
            observed_version="9.9.9"
        )

        with self.assertRaises(
            ValueError
        ):
            self.reconciler.reconcile(
                mission=self.mission(),
                report=self.report(),
            )

    def test_unknown_recommendation_rejected(
        self,
    ) -> None:
        self.write_artifact(
            recommendation="install"
        )

        with self.assertRaises(
            ValueError
        ):
            self.reconciler.reconcile(
                mission=self.mission(),
                report=self.report(),
            )

    def test_malformed_artifact_rejected(
        self,
    ) -> None:
        path = (
            self.root
            / "docs/technology/evaluations/"
            / "ruflo/3.37.0.json"
        )

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        path.write_text(
            "{invalid",
            encoding="utf-8",
        )

        with self.assertRaises(
            ValueError
        ):
            self.reconciler.reconcile(
                mission=self.mission(),
                report=self.report(),
            )

    def test_reject_marks_technology_rejected(
        self,
    ) -> None:
        self.write_artifact(
            recommendation="reject"
        )

        self.reconciler.reconcile(
            mission=self.mission(),
            report=self.report(),
        )

        record = self.registry.get(
            "ruflo"
        )

        self.assertEqual(
            record.evaluation_state,
            EvaluationState.PASSED,
        )

        self.assertEqual(
            record.state,
            TechnologyState.REJECTED,
        )

        self.assertEqual(
            record.assimilation_state,
            AssimilationState.NONE,
        )

    def test_watch_remains_non_assimilating(
        self,
    ) -> None:
        self.write_artifact(
            recommendation="watch"
        )

        self.reconciler.reconcile(
            mission=self.mission(),
            report=self.report(),
        )

        record = self.registry.get(
            "ruflo"
        )

        self.assertEqual(
            record.evaluation_state,
            EvaluationState.PASSED,
        )

        self.assertEqual(
            record.assimilation_state,
            AssimilationState.NONE,
        )

        self.assertEqual(
            record.state,
            TechnologyState.WATCHING,
        )

    def test_sandbox_remains_non_assimilating(
        self,
    ) -> None:
        self.write_artifact(
            recommendation="sandbox"
        )

        self.reconciler.reconcile(
            mission=self.mission(),
            report=self.report(),
        )

        record = self.registry.get(
            "ruflo"
        )

        self.assertEqual(
            record.evaluation_state,
            EvaluationState.PASSED,
        )

        self.assertEqual(
            record.assimilation_state,
            AssimilationState.NONE,
        )

    def test_existing_metadata_is_preserved(
        self,
    ) -> None:
        self.write_artifact()

        self.reconciler.reconcile(
            mission=self.mission(),
            report=self.report(),
        )

        metadata = self.registry.get(
            "ruflo"
        ).metadata

        self.assertEqual(
            metadata["existing"],
            {
                "preserved": True
            },
        )

        self.assertEqual(
            metadata["evaluation"][
                "recommendation"
            ],
            "assimilate_candidate",
        )

        self.assertTrue(
            metadata["evaluation"][
                "human_review_required"
            ]
        )

        self.assertFalse(
            metadata["evaluation"][
                "assimilation_auto_enqueue"
            ]
        )

    def test_external_runtime_remains_false(
        self,
    ) -> None:
        self.write_artifact()

        self.reconciler.reconcile(
            mission=self.mission(),
            report=self.report(),
        )

        self.assertFalse(
            self.registry.get(
                "ruflo"
            ).external_runtime_required
        )

    def test_ordinary_mission_is_ignored(
        self,
    ) -> None:
        mission = self.mission()
        mission[
            "task_type"
        ] = "general"

        result = self.reconciler.reconcile(
            mission=mission,
            report=self.report(),
        )

        self.assertFalse(
            result.handled
        )

        self.assertEqual(
            result.reason,
            "not_technology_evaluation",
        )

        self.assertEqual(
            self.registry.get(
                "ruflo"
            ).evaluation_state,
            EvaluationState.NOT_EVALUATED,
        )


if __name__ == "__main__":
    unittest.main()
