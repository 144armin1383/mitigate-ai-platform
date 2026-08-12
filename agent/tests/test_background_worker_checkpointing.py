from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from agent.runtime.background_worker import (
    BackgroundWorker,
)
from agent.runtime.checkpoint_store import (
    DurableCheckpointStore,
)


class FakeQueue:
    def __init__(
        self,
        mission: dict,
    ) -> None:
        self._mission = dict(
            mission
        )
        self._claimed = False

        self.completed: list[str] = []
        self.failed: list[str] = []
        self.blocked: list[str] = []

    def claim(
        self,
        worker_id: str,
    ):
        del worker_id

        if self._claimed:
            return None

        self._claimed = True

        return dict(
            self._mission
        )

    def complete(
        self,
        mission_id: str,
    ) -> None:
        self.completed.append(
            mission_id
        )

    def retry(
        self,
        mission_id: str,
    ) -> None:
        del mission_id

    def fail(
        self,
        mission_id: str,
    ) -> None:
        self.failed.append(
            mission_id
        )

    def block(
        self,
        mission_id: str,
    ) -> None:
        self.blocked.append(
            mission_id
        )

    def recover_stale(
        self,
        worker_id: str,
    ):
        del worker_id
        return []


class SuccessController:
    def execute(
        self,
        mission: dict,
    ):
        del mission

        return {
            "status": "success",
        }


class RetryController:
    def execute(
        self,
        mission: dict,
    ):
        del mission

        return {
            "status": "retry",
        }


class RaisingCheckpointStore:
    def save(
        self,
        **kwargs,
    ):
        del kwargs
        raise OSError(
            "simulated checkpoint failure"
        )


class BackgroundWorkerCheckpointTests(
    unittest.TestCase
):
    def _mission(
        self,
        *,
        attempts_done: int = 0,
        max_retries: int = 0,
    ) -> dict:
        return {
            "id": "checkpoint-test-mission",
            "priority": 1,
            "dependencies": [],
            "state": "running",
            "created_seq": 1,
            "attempts_done": attempts_done,
            "max_retries": max_retries,
        }

    def test_success_persists_lifecycle_checkpoints(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = DurableCheckpointStore(
                Path(temp)
            )

            queue = FakeQueue(
                self._mission()
            )

            worker = BackgroundWorker(
                queue=queue,
                controller=SuccessController(),
                once=True,
                worker_id="checkpoint-worker",
                poll_interval=0.01,
                checkpoint_store=store,
                checkpoint_project_id=(
                    "mitigate-ai-platform"
                ),
            )

            worker.run()

            execution_id = (
                "runtime-checkpoint-test-mission-"
                "attempt-0"
            )

            sequences = store.list_sequences(
                project_id="mitigate-ai-platform",
                execution_id=execution_id,
                step_id="mission_execution",
            )

            self.assertEqual(
                [0, 1, 2, 3],
                sequences,
            )

            phases = [
                store.load(
                    project_id="mitigate-ai-platform",
                    execution_id=execution_id,
                    step_id="mission_execution",
                    sequence=sequence,
                ).state["phase"]
                for sequence in sequences
            ]

            self.assertEqual(
                [
                    "claimed",
                    "controller_started",
                    "controller_finished",
                    "queue_transition",
                ],
                phases,
            )

            terminal = store.load(
                project_id="mitigate-ai-platform",
                execution_id=execution_id,
                step_id="mission_execution",
                sequence=3,
            )

            self.assertEqual(
                "completed",
                terminal.state[
                    "queue_state"
                ],
            )

            self.assertEqual(
                [
                    "checkpoint-test-mission"
                ],
                queue.completed,
            )

    def test_execution_identity_uses_attempt_number(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = DurableCheckpointStore(
                Path(temp)
            )

            queue = FakeQueue(
                self._mission(
                    attempts_done=2,
                    max_retries=5,
                )
            )

            worker = BackgroundWorker(
                queue=queue,
                controller=SuccessController(),
                once=True,
                poll_interval=0.01,
                checkpoint_store=store,
                checkpoint_project_id="project",
            )

            worker.run()

            self.assertEqual(
                [0, 1, 2, 3],
                store.list_sequences(
                    project_id="project",
                    execution_id=(
                        "runtime-checkpoint-test-mission-"
                        "attempt-2"
                    ),
                    step_id="mission_execution",
                ),
            )

    def test_retry_checkpoint_records_retrying(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = DurableCheckpointStore(
                Path(temp)
            )

            queue = FakeQueue(
                self._mission(
                    attempts_done=0,
                    max_retries=2,
                )
            )

            worker = BackgroundWorker(
                queue=queue,
                controller=RetryController(),
                once=True,
                poll_interval=0.01,
                checkpoint_store=store,
                checkpoint_project_id="project",
            )

            worker.run()

            terminal = store.load(
                project_id="project",
                execution_id=(
                    "runtime-checkpoint-test-mission-"
                    "attempt-0"
                ),
                step_id="mission_execution",
                sequence=3,
            )

            self.assertEqual(
                "retrying",
                terminal.state[
                    "queue_state"
                ],
            )

            self.assertEqual(
                [
                    "checkpoint-test-mission"
                ],
                queue.failed,
            )

    def test_checkpoint_failure_does_not_crash_execution(
        self,
    ) -> None:
        queue = FakeQueue(
            self._mission()
        )

        worker = BackgroundWorker(
            queue=queue,
            controller=SuccessController(),
            once=True,
            poll_interval=0.01,
            checkpoint_store=(
                RaisingCheckpointStore()
            ),
            checkpoint_project_id="project",
        )

        worker.run()

        self.assertEqual(
            [
                "checkpoint-test-mission"
            ],
            queue.completed,
        )

        checkpoint_failures = [
            event
            for event in worker.events
            if event["event"]
            == "checkpoint_failed"
        ]

        self.assertEqual(
            4,
            len(
                checkpoint_failures
            ),
        )

    def test_checkpointing_is_disabled_by_default(
        self,
    ) -> None:
        queue = FakeQueue(
            self._mission()
        )

        worker = BackgroundWorker(
            queue=queue,
            controller=SuccessController(),
            once=True,
            poll_interval=0.01,
        )

        worker.run()

        checkpoint_events = [
            event
            for event in worker.events
            if event["event"].startswith(
                "checkpoint_"
            )
        ]

        self.assertEqual(
            [],
            checkpoint_events,
        )

        self.assertEqual(
            [
                "checkpoint-test-mission"
            ],
            queue.completed,
        )

    def test_checkpoint_store_requires_project_id(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            BackgroundWorker(
                queue=FakeQueue(
                    self._mission()
                ),
                controller=SuccessController(),
                once=True,
                poll_interval=0.01,
                checkpoint_store=(
                    RaisingCheckpointStore()
                ),
            )

    def test_checkpoint_cli_argument_exists(
        self,
    ) -> None:
        parser = (
            BackgroundWorker.build_arg_parser()
        )

        args = parser.parse_args(
            [
                "--queue-path",
                "/tmp/missions.json",
                "--checkpoint-dir",
                "/tmp/checkpoints",
                "--project-id",
                "project",
            ]
        )

        self.assertEqual(
            "/tmp/checkpoints",
            args.checkpoint_dir,
        )


if __name__ == "__main__":
    unittest.main()
