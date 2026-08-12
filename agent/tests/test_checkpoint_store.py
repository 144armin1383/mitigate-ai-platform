from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from agent.runtime.checkpoint_store import (
    DurableCheckpointStore,
)


class DurableCheckpointStoreTests(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.temp = (
            tempfile.TemporaryDirectory()
        )

        self.root = Path(
            self.temp.name
        )

        self.store = (
            DurableCheckpointStore(
                self.root
            )
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_save_and_load(
        self,
    ) -> None:
        record = self.store.save(
            project_id="mitigate-ai-platform",
            execution_id="exec-1",
            step_id="step-a",
            sequence=1,
            state={
                "status": "running",
            },
            metadata={
                "source": "test",
            },
        )

        loaded = self.store.load(
            project_id="mitigate-ai-platform",
            execution_id="exec-1",
            step_id="step-a",
            sequence=1,
        )

        self.assertIsNotNone(
            loaded
        )

        self.assertEqual(
            record.checkpoint_id,
            loaded.checkpoint_id,
        )

        self.assertEqual(
            {
                "status": "running",
            },
            loaded.state,
        )

    def test_latest_returns_highest_sequence(
        self,
    ) -> None:
        for sequence in (
            1,
            3,
            2,
        ):
            self.store.save(
                project_id="project",
                execution_id="exec",
                step_id="step",
                sequence=sequence,
                state={
                    "sequence":
                        sequence,
                },
            )

        latest = self.store.latest(
            project_id="project",
            execution_id="exec",
            step_id="step",
        )

        self.assertIsNotNone(
            latest
        )

        self.assertEqual(
            3,
            latest.sequence,
        )

    def test_sequences_are_sorted(
        self,
    ) -> None:
        for sequence in (
            7,
            2,
            5,
        ):
            self.store.save(
                project_id="project",
                execution_id="exec",
                step_id="step",
                sequence=sequence,
                state={},
            )

        self.assertEqual(
            [
                2,
                5,
                7,
            ],
            self.store.list_sequences(
                project_id="project",
                execution_id="exec",
                step_id="step",
            ),
        )

    def test_checkpoint_id_is_deterministic(
        self,
    ) -> None:
        first = self.store.save(
            project_id="project",
            execution_id="exec",
            step_id="step",
            sequence=4,
            state={
                "value": 1,
            },
        )

        second = self.store.save(
            project_id="project",
            execution_id="exec",
            step_id="step",
            sequence=4,
            state={
                "value": 2,
            },
        )

        self.assertEqual(
            first.checkpoint_id,
            second.checkpoint_id,
        )

    def test_path_traversal_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            self.store.save(
                project_id="project",
                execution_id="../exec",
                step_id="step",
                sequence=1,
                state={},
            )

    def test_negative_sequence_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            self.store.save(
                project_id="project",
                execution_id="exec",
                step_id="step",
                sequence=-1,
                state={},
            )

    def test_missing_checkpoint_returns_none(
        self,
    ) -> None:
        result = self.store.load(
            project_id="project",
            execution_id="exec",
            step_id="step",
            sequence=99,
        )

        self.assertIsNone(
            result
        )

    def test_corrupted_identity_fails_closed(
        self,
    ) -> None:
        self.store.save(
            project_id="project",
            execution_id="exec",
            step_id="step",
            sequence=1,
            state={},
        )

        files = list(
            self.root.rglob(
                "*.json"
            )
        )

        self.assertEqual(
            1,
            len(files),
        )

        data = json.loads(
            files[0].read_text(
                encoding="utf-8"
            )
        )

        data[
            "checkpoint_id"
        ] = "tampered"

        files[0].write_text(
            json.dumps(data),
            encoding="utf-8",
        )

        with self.assertRaises(
            ValueError
        ):
            self.store.load(
                project_id="project",
                execution_id="exec",
                step_id="step",
                sequence=1,
            )


if __name__ == "__main__":
    unittest.main()
