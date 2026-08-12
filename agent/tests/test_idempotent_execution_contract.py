from __future__ import annotations

import unittest

from agent.runtime.idempotent_execution_contract import (
    IdempotencyDecision,
    IdempotentExecutionContract,
    IdempotentExecutionContractError,
    IdempotentExecutionIdentity,
)


class IdempotentExecutionContractTests(unittest.TestCase):

    def _identity(
        self,
        **overrides,
    ) -> IdempotentExecutionIdentity:
        values = {
            "project_id": "mitigate-ai-platform",
            "request_id": "mission-a",
            "mission_id": "mission-a",
            "execution_id": "runtime-mission-a-attempt-0",
            "attempts_done": 0,
        }

        values.update(overrides)

        return IdempotentExecutionIdentity(
            **values
        )

    def _existing(
        self,
        **overrides,
    ):
        values = {
            "project_id": "mitigate-ai-platform",
            "request_id": "mission-a",
            "mission_id": "mission-a",
            "execution_id": "runtime-mission-a-attempt-0",
        }

        values.update(overrides)

        return values

    def test_valid_identity_accepted(self):
        result = (
            IdempotentExecutionContract
            .validate_identity(
                self._identity()
            )
        )

        self.assertEqual(
            "mission-a",
            result.mission_id,
        )

    def test_empty_project_id_rejected(self):
        with self.assertRaises(
            IdempotentExecutionContractError
        ):
            (
                IdempotentExecutionContract
                .validate_identity(
                    self._identity(
                        project_id=""
                    )
                )
            )

    def test_empty_request_id_rejected(self):
        with self.assertRaises(
            IdempotentExecutionContractError
        ):
            (
                IdempotentExecutionContract
                .validate_identity(
                    self._identity(
                        request_id=""
                    )
                )
            )

    def test_empty_mission_id_rejected(self):
        with self.assertRaises(
            IdempotentExecutionContractError
        ):
            (
                IdempotentExecutionContract
                .validate_identity(
                    self._identity(
                        mission_id=""
                    )
                )
            )

    def test_empty_execution_id_rejected(self):
        with self.assertRaises(
            IdempotentExecutionContractError
        ):
            (
                IdempotentExecutionContract
                .validate_identity(
                    self._identity(
                        execution_id=""
                    )
                )
            )

    def test_negative_attempt_rejected(self):
        with self.assertRaises(
            IdempotentExecutionContractError
        ):
            (
                IdempotentExecutionContract
                .validate_identity(
                    self._identity(
                        attempts_done=-1
                    )
                )
            )

    def test_bool_attempt_rejected(self):
        with self.assertRaises(
            IdempotentExecutionContractError
        ):
            (
                IdempotentExecutionContract
                .validate_identity(
                    self._identity(
                        attempts_done=True
                    )
                )
            )

    def test_attempt_execution_id_deterministic(self):
        first = (
            IdempotentExecutionContract
            .worker_attempt_execution_id(
                mission_id="mission-a",
                attempts_done=0,
            )
        )

        second = (
            IdempotentExecutionContract
            .worker_attempt_execution_id(
                mission_id="mission-a",
                attempts_done=0,
            )
        )

        self.assertEqual(
            first,
            second,
        )

        self.assertEqual(
            "runtime-mission-a-attempt-0",
            first,
        )

    def test_different_attempts_different_execution_ids(self):
        first = (
            IdempotentExecutionContract
            .worker_attempt_execution_id(
                mission_id="mission-a",
                attempts_done=0,
            )
        )

        second = (
            IdempotentExecutionContract
            .worker_attempt_execution_id(
                mission_id="mission-a",
                attempts_done=1,
            )
        )

        self.assertNotEqual(
            first,
            second,
        )

    def test_no_existing_is_new(self):
        result = (
            IdempotentExecutionContract
            .classify(
                self._identity(),
                None,
            )
        )

        self.assertEqual(
            IdempotencyDecision.NEW,
            result.decision,
        )

    def test_exact_duplicate_is_replay(self):
        result = (
            IdempotentExecutionContract
            .classify(
                self._identity(),
                self._existing(),
            )
        )

        self.assertEqual(
            IdempotencyDecision.REPLAY,
            result.decision,
        )

    def test_project_conflict(self):
        result = (
            IdempotentExecutionContract
            .classify(
                self._identity(),
                self._existing(
                    project_id="other"
                ),
            )
        )

        self.assertEqual(
            IdempotencyDecision.CONFLICT,
            result.decision,
        )

    def test_request_conflict(self):
        result = (
            IdempotentExecutionContract
            .classify(
                self._identity(),
                self._existing(
                    request_id="other"
                ),
            )
        )

        self.assertEqual(
            IdempotencyDecision.CONFLICT,
            result.decision,
        )

    def test_mission_conflict(self):
        result = (
            IdempotentExecutionContract
            .classify(
                self._identity(),
                self._existing(
                    mission_id="other"
                ),
            )
        )

        self.assertEqual(
            IdempotencyDecision.CONFLICT,
            result.decision,
        )

    def test_flowspec_identity_relationship_accepted(self):
        identity = self._identity(
            request_id="flow-123",
            mission_id="flow-123",
            execution_id=(
                "runtime-flow-123-attempt-0"
            ),
        )

        result = (
            IdempotentExecutionContract
            .validate_identity(
                identity
            )
        )

        self.assertEqual(
            result.request_id,
            result.mission_id,
        )

    def test_existing_mapping_not_mutated(self):
        existing = self._existing()
        original = dict(existing)

        (
            IdempotentExecutionContract
            .classify(
                self._identity(),
                existing,
            )
        )

        self.assertEqual(
            original,
            existing,
        )

    def test_decision_is_deterministic(self):
        first = (
            IdempotentExecutionContract
            .classify(
                self._identity(),
                self._existing(),
            )
        )

        second = (
            IdempotentExecutionContract
            .classify(
                self._identity(),
                self._existing(),
            )
        )

        self.assertEqual(
            first,
            second,
        )


if __name__ == "__main__":
    unittest.main()
