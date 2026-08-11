from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent.technology.registry import (
    AssimilationState,
    EvaluationState,
    TechnologyKind,
    TechnologyRecord,
    TechnologyRegistry,
    TechnologyState,
)


class FixedClock:
    def __init__(self):
        self.value = "2026-08-11T18:00:00Z"

    def __call__(self):
        return self.value


class TechnologyRegistryTests(
    unittest.TestCase
):

    def _record(
        self,
        technology_id="ruflo",
    ):
        return TechnologyRecord(
            technology_id=technology_id,
            name="Ruflo",
            kind=TechnologyKind.ORCHESTRATOR,
            state=TechnologyState.WATCHING,
            source_url="https://github.com/ruvnet/ruflo",
            external_runtime_required=False,
        )

    def test_register_and_get(self):
        registry = TechnologyRegistry()

        record = registry.register(
            self._record()
        )

        self.assertEqual(
            record.technology_id,
            "ruflo",
        )

        self.assertEqual(
            registry.get("ruflo").name,
            "Ruflo",
        )

    def test_duplicate_registration_rejected(self):
        registry = TechnologyRegistry()

        registry.register(
            self._record()
        )

        with self.assertRaises(ValueError):
            registry.register(
                self._record()
            )

    def test_invalid_identifier_rejected(self):
        registry = TechnologyRegistry()

        with self.assertRaises(ValueError):
            registry.register(
                self._record(
                    "bad/id"
                )
            )

    def test_list_is_deterministic(self):
        registry = TechnologyRegistry()

        registry.register(
            self._record("zeta")
        )

        registry.register(
            self._record("alpha")
        )

        ids = [
            item.technology_id
            for item in registry.list()
        ]

        self.assertEqual(
            ids,
            ["alpha", "zeta"],
        )

    def test_observe_version_preserves_history(self):
        registry = TechnologyRegistry()

        registry.register(
            self._record()
        )

        registry.observe_version(
            "ruflo",
            "1.0.0",
        )

        registry.observe_version(
            "ruflo",
            "1.1.0",
        )

        history = registry.history(
            "ruflo"
        )

        versions = [
            item["data"]["version"]
            for item in history
            if item["event"]
            == "version_observed"
        ]

        self.assertEqual(
            versions,
            ["1.0.0", "1.1.0"],
        )

        self.assertEqual(
            registry.get(
                "ruflo"
            ).latest_observed_version,
            "1.1.0",
        )

    def test_native_replacement_state(self):
        registry = TechnologyRegistry()

        registry.register(
            self._record()
        )

        registry.mark_native_replacement(
            "ruflo",
            True,
        )

        record = registry.get(
            "ruflo"
        )

        self.assertTrue(
            record.native_replacement_available
        )

        self.assertEqual(
            record.assimilation_state,
            AssimilationState.NATIVE_AVAILABLE,
        )

    def test_external_runtime_is_never_required_by_default(self):
        record = self._record()

        self.assertFalse(
            record.external_runtime_required
        )

    def test_update_rejects_identity_change(self):
        registry = TechnologyRegistry()

        registry.register(
            self._record()
        )

        with self.assertRaises(ValueError):
            registry.update(
                "ruflo",
                technology_id="other",
            )

    def test_update_rejects_unknown_field(self):
        registry = TechnologyRegistry()

        registry.register(
            self._record()
        )

        with self.assertRaises(ValueError):
            registry.update(
                "ruflo",
                does_not_exist=True,
            )

    def test_persistence_round_trip(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "technologies.json"

            registry = TechnologyRegistry(
                path
            )

            registry.register(
                self._record()
            )

            registry.observe_version(
                "ruflo",
                "2.0.0",
            )

            registry.mark_native_replacement(
                "ruflo",
                True,
            )

            loaded = TechnologyRegistry(
                path
            )

            record = loaded.get(
                "ruflo"
            )

            self.assertEqual(
                record.latest_observed_version,
                "2.0.0",
            )

            self.assertTrue(
                record.native_replacement_available
            )

            self.assertGreaterEqual(
                len(
                    loaded.history(
                        "ruflo"
                    )
                ),
                3,
            )

    def test_persisted_json_contains_no_runtime_dependency_requirement(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "technologies.json"

            registry = TechnologyRegistry(
                path
            )

            registry.register(
                self._record()
            )

            payload = json.loads(
                path.read_text(
                    encoding="utf-8"
                )
            )

            item = payload[
                "technologies"
            ][0]

            self.assertFalse(
                item[
                    "external_runtime_required"
                ]
            )

    def test_corrupt_schema_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "technologies.json"

            path.write_text(
                json.dumps(
                    {
                        "schema_version": 999,
                        "technologies": [],
                        "history": [],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                TechnologyRegistry(
                    path
                )

    def test_state_fields_round_trip(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "technologies.json"

            registry = TechnologyRegistry(
                path
            )

            record = self._record()
            record.state = (
                TechnologyState.EVALUATING
            )
            record.evaluation_state = (
                EvaluationState.IN_PROGRESS
            )
            record.assimilation_state = (
                AssimilationState.CANDIDATE
            )

            registry.register(record)

            loaded = TechnologyRegistry(
                path
            ).get(
                "ruflo"
            )

            self.assertEqual(
                loaded.state,
                TechnologyState.EVALUATING,
            )

            self.assertEqual(
                loaded.evaluation_state,
                EvaluationState.IN_PROGRESS,
            )

            self.assertEqual(
                loaded.assimilation_state,
                AssimilationState.CANDIDATE,
            )

    def test_history_is_technology_scoped(self):
        registry = TechnologyRegistry()

        registry.register(
            self._record("ruflo")
        )

        registry.register(
            self._record("other")
        )

        registry.observe_version(
            "ruflo",
            "3.0.0",
        )

        ruflo_history = registry.history(
            "ruflo"
        )

        self.assertTrue(
            all(
                item["technology_id"]
                == "ruflo"
                for item in ruflo_history
            )
        )


if __name__ == "__main__":
    unittest.main()
