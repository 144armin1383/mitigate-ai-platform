from __future__ import annotations

import json
from pathlib import Path
import unittest

from agent.runtime.flowspec import (
    FLOWSPEC_SCHEMA_VERSION,
    FlowSpecValidationError,
    FlowSpecValidator,
)


class FlowSpecV1Tests(
    unittest.TestCase
):
    def _document(
        self,
    ):
        return {
            "schema_version":
                FLOWSPEC_SCHEMA_VERSION,
            "flow_id":
                "flow-a",
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
                        {
                            "value": 1
                        },
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
            "metadata": {
                "source":
                    "test"
            },
        }

    def test_valid_flowspec_parses(
        self,
    ):
        spec = FlowSpecValidator.parse(
            self._document()
        )

        self.assertEqual(
            "flow-a",
            spec.flow_id,
        )

        self.assertEqual(
            2,
            len(spec.steps),
        )

    def test_topological_order_is_deterministic(
        self,
    ):
        document = (
            self._document()
        )

        document["steps"] = [
            {
                "step_id": "z",
                "task_type": "task",
                "dependencies": [],
            },
            {
                "step_id": "a",
                "task_type": "task",
                "dependencies": [],
            },
            {
                "step_id": "final",
                "task_type": "task",
                "dependencies": [
                    "z",
                    "a",
                ],
            },
        ]

        spec = FlowSpecValidator.parse(
            document
        )

        ordered = (
            FlowSpecValidator
            .topological_steps(
                spec
            )
        )

        self.assertEqual(
            [
                "a",
                "z",
                "final",
            ],
            [
                step.step_id
                for step in ordered
            ],
        )

    def test_cycle_is_rejected(
        self,
    ):
        document = (
            self._document()
        )

        document["steps"] = [
            {
                "step_id": "a",
                "task_type": "task",
                "dependencies": [
                    "b"
                ],
            },
            {
                "step_id": "b",
                "task_type": "task",
                "dependencies": [
                    "a"
                ],
            },
        ]

        with self.assertRaises(
            FlowSpecValidationError
        ):
            FlowSpecValidator.parse(
                document
            )

    def test_unknown_dependency_is_rejected(
        self,
    ):
        document = (
            self._document()
        )

        document[
            "steps"
        ][0][
            "dependencies"
        ] = [
            "missing"
        ]

        with self.assertRaises(
            FlowSpecValidationError
        ):
            FlowSpecValidator.parse(
                document
            )

    def test_duplicate_step_id_is_rejected(
        self,
    ):
        document = (
            self._document()
        )

        document["steps"][1][
            "step_id"
        ] = "prepare"

        with self.assertRaises(
            FlowSpecValidationError
        ):
            FlowSpecValidator.parse(
                document
            )

    def test_self_dependency_is_rejected(
        self,
    ):
        document = (
            self._document()
        )

        document["steps"][0][
            "dependencies"
        ] = [
            "prepare"
        ]

        with self.assertRaises(
            FlowSpecValidationError
        ):
            FlowSpecValidator.parse(
                document
            )

    def test_unknown_root_field_is_rejected(
        self,
    ):
        document = (
            self._document()
        )

        document[
            "unexpected"
        ] = True

        with self.assertRaises(
            FlowSpecValidationError
        ):
            FlowSpecValidator.parse(
                document
            )

    def test_unknown_step_field_is_rejected(
        self,
    ):
        document = (
            self._document()
        )

        document["steps"][0][
            "unexpected"
        ] = True

        with self.assertRaises(
            FlowSpecValidationError
        ):
            FlowSpecValidator.parse(
                document
            )

    def test_unsupported_version_is_rejected(
        self,
    ):
        document = (
            self._document()
        )

        document[
            "schema_version"
        ] = "2.0.0"

        with self.assertRaises(
            FlowSpecValidationError
        ):
            FlowSpecValidator.parse(
                document
            )

    def test_json_parser_rejects_invalid_json(
        self,
    ):
        with self.assertRaises(
            FlowSpecValidationError
        ):
            FlowSpecValidator.parse_json(
                "{invalid"
            )

    def test_canonical_json_is_deterministic(
        self,
    ):
        spec = FlowSpecValidator.parse(
            self._document()
        )

        first = (
            FlowSpecValidator
            .canonical_json(
                spec
            )
        )

        second = (
            FlowSpecValidator
            .canonical_json(
                spec
            )
        )

        self.assertEqual(
            first,
            second,
        )

        decoded = json.loads(
            first
        )

        self.assertEqual(
            [
                "prepare",
                "execute",
            ],
            [
                step["step_id"]
                for step in decoded[
                    "steps"
                ]
            ],
        )

    def test_schema_file_exists(
        self,
    ):
        schema_path = Path(
            "agent/schemas/"
            "flowspec-v1.schema.json"
        )

        self.assertTrue(
            schema_path.is_file()
        )

        schema = json.loads(
            schema_path.read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(
            "MITIGATE FlowSpec v1",
            schema["title"],
        )

        self.assertFalse(
            schema[
                "additionalProperties"
            ]
        )


if __name__ == "__main__":
    unittest.main()
