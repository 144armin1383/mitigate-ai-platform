from __future__ import annotations

import unittest

from agent.runtime.flowspec import (
    FLOWSPEC_SCHEMA_VERSION,
    FlowSpecValidator,
)
from agent.runtime.flowspec_materializer import (
    FlowSpecMissionMaterializer,
)


class FlowSpecMissionMaterializerTests(
    unittest.TestCase
):
    def _document(
        self,
    ) -> dict:
        return {
            "schema_version":
                FLOWSPEC_SCHEMA_VERSION,
            "flow_id":
                "example-flow",
            "project_id":
                "mitigate-ai-platform",
            "steps": [
                {
                    "step_id":
                        "prepare",
                    "task_type":
                        "prepare_task",
                    "dependencies":
                        [],
                    "payload": {
                        "value": 1,
                    },
                },
                {
                    "step_id":
                        "execute",
                    "task_type":
                        "execute_task",
                    "dependencies": [
                        "prepare"
                    ],
                    "payload": {
                        "value": 2,
                    },
                },
            ],
            "metadata": {},
        }

    def test_preview_materializes_all_steps(
        self,
    ) -> None:
        result = (
            FlowSpecMissionMaterializer
            .preview_document(
                self._document()
            )
        )

        self.assertEqual(
            2,
            len(result.missions),
        )

        self.assertEqual(
            [
                "prepare",
                "execute",
            ],
            [
                mission["step_id"]
                for mission
                in result.missions
            ],
        )

    def test_mission_ids_are_deterministic(
        self,
    ) -> None:
        first = (
            FlowSpecMissionMaterializer
            .preview_document(
                self._document()
            )
        )

        second = (
            FlowSpecMissionMaterializer
            .preview_document(
                self._document()
            )
        )

        self.assertEqual(
            [
                mission["mission_id"]
                for mission
                in first.missions
            ],
            [
                mission["mission_id"]
                for mission
                in second.missions
            ],
        )

    def test_dependency_maps_to_mission_id(
        self,
    ) -> None:
        result = (
            FlowSpecMissionMaterializer
            .preview_document(
                self._document()
            )
        )

        prepare = result.missions[0]
        execute = result.missions[1]

        self.assertEqual(
            [],
            prepare["dependencies"],
        )

        self.assertEqual(
            [
                prepare["mission_id"]
            ],
            execute["dependencies"],
        )

    def test_preview_is_topological(
        self,
    ) -> None:
        document = (
            self._document()
        )

        document["steps"] = [
            document["steps"][1],
            document["steps"][0],
        ]

        result = (
            FlowSpecMissionMaterializer
            .preview_document(
                document
            )
        )

        self.assertEqual(
            [
                "prepare",
                "execute",
            ],
            [
                mission["step_id"]
                for mission
                in result.missions
            ],
        )

    def test_payload_is_preserved(
        self,
    ) -> None:
        result = (
            FlowSpecMissionMaterializer
            .preview_document(
                self._document()
            )
        )

        self.assertEqual(
            {
                "value": 1,
            },
            result.missions[0][
                "payload"
            ],
        )

    def test_project_identity_preserved(
        self,
    ) -> None:
        result = (
            FlowSpecMissionMaterializer
            .preview_document(
                self._document()
            )
        )

        for mission in (
            result.missions
        ):
            self.assertEqual(
                "mitigate-ai-platform",
                mission[
                    "project_id"
                ],
            )

    def test_provider_is_native(
        self,
    ) -> None:
        result = (
            FlowSpecMissionMaterializer
            .preview_document(
                self._document()
            )
        )

        for mission in (
            result.missions
        ):
            self.assertEqual(
                "native",
                mission[
                    "provider_id"
                ],
            )

    def test_default_retry_budget_is_zero(
        self,
    ) -> None:
        result = (
            FlowSpecMissionMaterializer
            .preview_document(
                self._document()
            )
        )

        for mission in (
            result.missions
        ):
            self.assertEqual(
                0,
                mission[
                    "max_retries"
                ],
            )

    def test_preview_does_not_require_queue(
        self,
    ) -> None:
        spec = (
            FlowSpecValidator.parse(
                self._document()
            )
        )

        result = (
            FlowSpecMissionMaterializer
            .preview(
                spec
            )
        )

        self.assertEqual(
            "example-flow",
            result.flow_id,
        )


if __name__ == "__main__":
    unittest.main()
