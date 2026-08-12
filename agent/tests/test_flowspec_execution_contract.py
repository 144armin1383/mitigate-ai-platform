from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from agent.runtime.flowspec import (
    FLOWSPEC_SCHEMA_VERSION,
)
from agent.runtime.flowspec_execution_contract import (
    FlowExecutionContractError,
    FlowSpecExecutionContractValidator,
)
from agent.runtime.flowspec_materializer import (
    FlowSpecMissionMaterializer,
    MaterializedFlow,
)
from agent.runtime.mission_queue import (
    MissionQueue,
)
from agent.runtime.production_queue_coordinator_adapter import (
    ProductionQueueCoordinatorAdapter,
)


class FlowSpecExecutionContractTests(
    unittest.TestCase
):
    def _flow(
        self,
    ) -> MaterializedFlow:
        return (
            FlowSpecMissionMaterializer
            .preview_document(
                {
                    "schema_version":
                        FLOWSPEC_SCHEMA_VERSION,
                    "flow_id":
                        "execution-contract",
                    "project_id":
                        "mitigate-ai-platform",
                    "steps": [
                        {
                            "step_id":
                                "prepare",
                            "task_type":
                                "prepare",
                            "dependencies":
                                [],
                            "payload":
                                {},
                        },
                        {
                            "step_id":
                                "execute",
                            "task_type":
                                "execute",
                            "dependencies":
                                [
                                    "prepare"
                                ],
                            "payload":
                                {},
                        },
                    ],
                }
            )
        )

    def _mutate(
        self,
        *,
        index: int,
        field: str,
        value,
    ) -> MaterializedFlow:
        source = self._flow()

        missions = [
            dict(
                mission
            )
            for mission
            in source.missions
        ]

        missions[
            index
        ][
            field
        ] = value

        return MaterializedFlow(
            flow_id=source.flow_id,
            project_id=source.project_id,
            missions=tuple(
                missions
            ),
        )

    def test_valid_materialized_flow_passes(
        self,
    ) -> None:
        result = (
            FlowSpecExecutionContractValidator
            .validate(
                self._flow()
            )
        )

        self.assertEqual(
            "execution-contract",
            result.flow_id,
        )

        self.assertEqual(
            2,
            len(
                result.mission_ids
            ),
        )

    def test_duplicate_mission_id_rejected(
        self,
    ) -> None:
        flow = self._flow()

        duplicate = (
            flow.missions[
                0
            ][
                "mission_id"
            ]
        )

        mutated = self._mutate(
            index=1,
            field="mission_id",
            value=duplicate,
        )

        with self.assertRaises(
            FlowExecutionContractError
        ):
            (
                FlowSpecExecutionContractValidator
                .validate(
                    mutated
                )
            )

    def test_request_identity_mismatch_rejected(
        self,
    ) -> None:
        mutated = self._mutate(
            index=0,
            field="request_id",
            value="different",
        )

        with self.assertRaises(
            FlowExecutionContractError
        ):
            (
                FlowSpecExecutionContractValidator
                .validate(
                    mutated
                )
            )

    def test_project_mismatch_rejected(
        self,
    ) -> None:
        mutated = self._mutate(
            index=0,
            field="project_id",
            value="other-project",
        )

        with self.assertRaises(
            FlowExecutionContractError
        ):
            (
                FlowSpecExecutionContractValidator
                .validate(
                    mutated
                )
            )

    def test_plan_mismatch_rejected(
        self,
    ) -> None:
        mutated = self._mutate(
            index=0,
            field="plan_id",
            value="other-flow",
        )

        with self.assertRaises(
            FlowExecutionContractError
        ):
            (
                FlowSpecExecutionContractValidator
                .validate(
                    mutated
                )
            )

    def test_non_native_provider_rejected(
        self,
    ) -> None:
        mutated = self._mutate(
            index=0,
            field="provider_id",
            value="external",
        )

        with self.assertRaises(
            FlowExecutionContractError
        ):
            (
                FlowSpecExecutionContractValidator
                .validate(
                    mutated
                )
            )

    def test_non_pending_status_rejected(
        self,
    ) -> None:
        mutated = self._mutate(
            index=0,
            field="status",
            value="running",
        )

        with self.assertRaises(
            FlowExecutionContractError
        ):
            (
                FlowSpecExecutionContractValidator
                .validate(
                    mutated
                )
            )

    def test_unknown_dependency_rejected(
        self,
    ) -> None:
        mutated = self._mutate(
            index=1,
            field="dependencies",
            value=[
                "missing"
            ],
        )

        with self.assertRaises(
            FlowExecutionContractError
        ):
            (
                FlowSpecExecutionContractValidator
                .validate(
                    mutated
                )
            )

    def test_forward_dependency_rejected(
        self,
    ) -> None:
        flow = self._flow()

        missions = [
            dict(
                mission
            )
            for mission
            in reversed(
                flow.missions
            )
        ]

        mutated = MaterializedFlow(
            flow_id=flow.flow_id,
            project_id=flow.project_id,
            missions=tuple(
                missions
            ),
        )

        with self.assertRaises(
            FlowExecutionContractError
        ):
            (
                FlowSpecExecutionContractValidator
                .validate(
                    mutated
                )
            )

    def test_negative_retry_budget_rejected(
        self,
    ) -> None:
        mutated = self._mutate(
            index=0,
            field="max_retries",
            value=-1,
        )

        with self.assertRaises(
            FlowExecutionContractError
        ):
            (
                FlowSpecExecutionContractValidator
                .validate(
                    mutated
                )
            )

    def test_invalid_provenance_rejected(
        self,
    ) -> None:
        flow = self._flow()

        missions = [
            dict(
                mission
            )
            for mission
            in flow.missions
        ]

        metadata = dict(
            missions[
                0
            ][
                "metadata"
            ]
        )

        metadata[
            "source"
        ] = "external"

        missions[
            0
        ][
            "metadata"
        ] = metadata

        mutated = MaterializedFlow(
            flow_id=flow.flow_id,
            project_id=flow.project_id,
            missions=tuple(
                missions
            ),
        )

        with self.assertRaises(
            FlowExecutionContractError
        ):
            (
                FlowSpecExecutionContractValidator
                .validate(
                    mutated
                )
            )

    def test_temporary_production_queue_contract(
        self,
    ) -> None:
        flow = self._flow()

        (
            FlowSpecExecutionContractValidator
            .validate(
                flow
            )
        )

        with tempfile.TemporaryDirectory() as temp:
            queue = MissionQueue(
                str(
                    Path(
                        temp
                    )
                    / "missions.json"
                )
            )

            adapter = (
                ProductionQueueCoordinatorAdapter(
                    queue=queue,
                    project_id=(
                        "mitigate-ai-platform"
                    ),
                    queue_reference=(
                        "missions"
                    ),
                )
            )

            result = adapter.enqueue(
                "mitigate-ai-platform",
                "missions",
                flow.missions,
            )

            self.assertEqual(
                "queued",
                result[
                    "status"
                ],
            )

            first = queue.claim(
                "test-worker"
            )

            self.assertIsNotNone(
                first
            )

            self.assertEqual(
                flow.missions[
                    0
                ][
                    "mission_id"
                ],
                first[
                    "id"
                ],
            )

            queue.complete(
                first[
                    "id"
                ]
            )

            second = queue.claim(
                "test-worker"
            )

            self.assertIsNotNone(
                second
            )

            self.assertEqual(
                flow.missions[
                    1
                ][
                    "mission_id"
                ],
                second[
                    "id"
                ],
            )


if __name__ == "__main__":
    unittest.main()
