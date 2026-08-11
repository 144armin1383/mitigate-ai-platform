from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.runtime.mission_queue import (
    MissionQueue,
)
from agent.runtime.production_technology_evaluation_composition import (
    build_production_technology_evaluation_composition,
)
from agent.technology.evaluation_mission_bridge import (
    TechnologyEvaluationRequest,
)
from agent.technology.scoring import (
    TechnologyScore,
)
from agent.technology.watcher import (
    TechnologyEvaluationCandidate,
)


class ProductionTechnologyEvaluationWiringTests(
    unittest.TestCase
):
    def _candidate(self):
        return TechnologyEvaluationCandidate(
            technology_id="ruflo",
            observed_version="3.37.0",
            score=TechnologyScore(
                relevance=70,
                capability_novelty=100,
                architectural_compatibility=70,
                independence_potential=80,
                operational_value=60,
                security_risk_penalty=0,
                external_dependency_penalty=0,
                total=76,
                evaluation_candidate=True,
            ),
        )

    def test_definition_is_created_before_queue_visibility(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            composition = (
                build_production_technology_evaluation_composition(
                    project_id=(
                        "mitigate-ai-platform"
                    ),
                    queue_path=(
                        root
                        / "data"
                        / "missions.json"
                    ),
                    repository_root=root,
                    queue_reference="missions",
                )
            )

            result = (
                composition.bridge.enqueue(
                    TechnologyEvaluationRequest(
                        project_id=(
                            "mitigate-ai-platform"
                        ),
                        candidate=(
                            self._candidate()
                        ),
                    )
                )
            )

            self.assertTrue(
                result["accepted"]
            )

            self.assertEqual(
                1,
                result["enqueued_count"],
            )

            mission_id = (
                result["mission_ids"][0]
            )

            definition = (
                root
                / "agent"
                / "missions"
                / f"{mission_id}.md"
            )

            self.assertTrue(
                definition.is_file()
            )

            queue = MissionQueue(
                str(
                    root
                    / "data"
                    / "missions.json"
                )
            )

            queued = queue.get(
                mission_id
            )

            self.assertEqual(
                "pending",
                queued["state"],
            )

    def test_definition_contains_evaluation_guardrails(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            composition = (
                build_production_technology_evaluation_composition(
                    project_id=(
                        "mitigate-ai-platform"
                    ),
                    queue_path=(
                        root
                        / "missions.json"
                    ),
                    repository_root=root,
                )
            )

            result = (
                composition.bridge.enqueue(
                    TechnologyEvaluationRequest(
                        project_id=(
                            "mitigate-ai-platform"
                        ),
                        candidate=(
                            self._candidate()
                        ),
                    )
                )
            )

            mission_id = (
                result["mission_ids"][0]
            )

            text = (
                root
                / "agent"
                / "missions"
                / f"{mission_id}.md"
            ).read_text(
                encoding="utf-8"
            )

            self.assertIn(
                '"installation_allowed": false',
                text,
            )

            self.assertIn(
                '"activation_allowed": false',
                text,
            )

            self.assertIn(
                '"runtime_adoption_allowed": false',
                text,
            )

            self.assertIn(
                '"external_runtime_dependency_allowed": false',
                text,
            )

            self.assertIn(
                "assimilate_candidate",
                text,
            )

            self.assertIn(
                "require_human_review_before_adoption",
                text,
            )

    def test_duplicate_definition_is_rejected(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            composition = (
                build_production_technology_evaluation_composition(
                    project_id=(
                        "mitigate-ai-platform"
                    ),
                    queue_path=(
                        root
                        / "missions.json"
                    ),
                    repository_root=root,
                )
            )

            request = (
                TechnologyEvaluationRequest(
                    project_id=(
                        "mitigate-ai-platform"
                    ),
                    candidate=(
                        self._candidate()
                    ),
                )
            )

            composition.bridge.enqueue(
                request
            )

            with self.assertRaisesRegex(
                ValueError,
                "mission_definition_exists",
            ):
                composition.bridge.enqueue(
                    request
                )

    def test_external_runtime_is_never_required(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            composition = (
                build_production_technology_evaluation_composition(
                    project_id=(
                        "mitigate-ai-platform"
                    ),
                    queue_path=(
                        root
                        / "missions.json"
                    ),
                    repository_root=root,
                )
            )

            mission = (
                composition.bridge.create_mission(
                    TechnologyEvaluationRequest(
                        project_id=(
                            "mitigate-ai-platform"
                        ),
                        candidate=(
                            self._candidate()
                        ),
                    )
                )
            )

            evaluation = (
                mission["payload"][
                    "technology_evaluation"
                ]
            )

            self.assertFalse(
                evaluation[
                    "external_runtime_dependency_allowed"
                ]
            )

            self.assertFalse(
                evaluation[
                    "installation_allowed"
                ]
            )

            self.assertFalse(
                evaluation[
                    "activation_allowed"
                ]
            )

            self.assertFalse(
                evaluation[
                    "runtime_adoption_allowed"
                ]
            )


if __name__ == "__main__":
    unittest.main()
