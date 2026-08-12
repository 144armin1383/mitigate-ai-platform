import json
import socket
import unittest
from unittest.mock import patch

from agent.resilience.retry_execution_adapter import project_retry_execution_event


class TestRetryExecutionAdapter(unittest.TestCase):
    def test_retryable_classification_projection(self):
        mission_id = "m-123"
        execution_id = "e-abc"
        classification = {"kind": "retryable", "reason": "transient", "category": "network"}
        budget = {"eligible": True, "remaining": 3, "limit": 5}
        queue_proj = {"attempts_done": 1, "max_attempts": 5}

        event = project_retry_execution_event(
            mission_id=mission_id,
            execution_id=execution_id,
            attempt=1,
            classification_result=classification,
            retry_budget_projection=budget,
            mission_queue_projection=queue_proj,
            checkpoint_id="chk-1",
            idempotency_key="idem-1",
            metadata={"note": "ok", "tags": ["a", "b"]},
        )

        self.assertEqual(event["mission"]["id"], mission_id)
        self.assertEqual(event["execution"]["id"], execution_id)
        self.assertEqual(event["execution"]["attempt"], 1)
        self.assertEqual(event["retry"]["authority"], "MissionQueue")
        self.assertEqual(event["retry"]["classification"]["kind"], "retryable")
        self.assertTrue(event["retry"]["classification"]["retryable"]) 
        self.assertIn("budget", event["retry"])
        self.assertTrue(event["retry"]["budget"]["eligible"]) 
        self.assertEqual(event["retry"]["budget"]["remaining"], 3)
        self.assertEqual(event["retry"]["budget"]["limit"], 5)
        self.assertEqual(event["retry"]["budget"]["source"], "RetryBudgetQueueAdapter")
        self.assertIn("checkpoint", event)
        self.assertEqual(event["checkpoint"]["id"], "chk-1")
        self.assertEqual(event["execution"]["idempotency_key"], "idem-1")
        self.assertIn("safe_metadata", event)
        self.assertEqual(event["safe_metadata"].get("note"), "ok")

        # JSON serializable
        json.dumps(event)

    def test_non_retryable_classification_projection(self):
        classification = {"retryable": False, "reason": "client_error"}
        event = project_retry_execution_event(
            mission_id="m-1",
            execution_id="e-1",
            attempt=None,
            classification_result=classification,
        )
        self.assertEqual(event["retry"]["classification"]["kind"], "non_retryable")
        self.assertFalse(event["retry"]["classification"]["retryable"]) 
        self.assertNotIn("attempt", event["execution"])  # attempt omitted when None

    def test_exhausted_classification_projection(self):
        classification = {"exhausted": True, "reason": "budget_exhausted"}
        event = project_retry_execution_event(
            mission_id="m-2",
            execution_id="e-2",
            attempt=5,
            classification_result=classification,
            retry_budget_projection={"eligible": False, "remaining": 0, "limit": 5, "exhausted": True},
        )
        self.assertEqual(event["retry"]["classification"]["kind"], "exhausted")
        self.assertFalse(event["retry"]["classification"]["retryable"]) 
        self.assertTrue(event["retry"]["budget"]["exhausted"]) 

    def test_cancelled_classification_projection(self):
        classification = {"cancelled": True}
        event = project_retry_execution_event(
            mission_id="m-3",
            execution_id="e-3",
            attempt=2,
            classification_result=classification,
        )
        self.assertEqual(event["retry"]["classification"]["kind"], "cancelled")
        self.assertFalse(event["retry"]["classification"]["retryable"]) 

    def test_deadline_exceeded_classification_projection(self):
        classification = {"deadline_exceeded": True}
        event = project_retry_execution_event(
            mission_id="m-4",
            execution_id="e-4",
            attempt=2,
            classification_result=classification,
        )
        self.assertEqual(event["retry"]["classification"]["kind"], "deadline_exceeded")
        self.assertFalse(event["retry"]["classification"]["retryable"]) 

    def test_deterministic_output_and_no_input_mutation(self):
        classification = {"kind": "retryable", "reason": "transient"}
        budget = {"eligible": True, "remaining": 1, "limit": 3}
        queue = {"attempts_done": 2, "max_attempts": 3}
        meta = {"note": "keep", "nested": {"a": 1}}

        # Copies to ensure no mutation
        classification_copy = json.loads(json.dumps(classification))
        budget_copy = json.loads(json.dumps(budget))
        queue_copy = json.loads(json.dumps(queue))
        meta_copy = json.loads(json.dumps(meta))

        e1 = project_retry_execution_event(
            mission_id="m-x",
            execution_id="e-x",
            attempt=2,
            classification_result=classification,
            retry_budget_projection=budget,
            mission_queue_projection=queue,
            metadata=meta,
        )
        e2 = project_retry_execution_event(
            mission_id="m-x",
            execution_id="e-x",
            attempt=2,
            classification_result=classification,
            retry_budget_projection=budget,
            mission_queue_projection=queue,
            metadata=meta,
        )
        self.assertEqual(e1, e2)  # deterministic
        # inputs unchanged
        self.assertEqual(classification, classification_copy)
        self.assertEqual(budget, budget_copy)
        self.assertEqual(queue, queue_copy)
        self.assertEqual(meta, meta_copy)
        # JSON serializable
        json.dumps(e1)

    def test_safe_optional_metadata_and_sanitization(self):
        metadata = {
            "note": "hello",
            "tags": ["x", "y", "z"],
            "exception": "ValueError: secret details",  # should be dropped
            "token": "abcd",  # should be dropped
            "nested": {
                "password": "p",  # should be dropped
                "details": "all good",
            },
        }
        event = project_retry_execution_event(
            mission_id="m-5",
            execution_id="e-5",
            attempt=0,
            classification_result={"retryable": True},
            metadata=metadata,
        )
        md = event.get("safe_metadata", {})
        self.assertIn("note", md)
        self.assertIn("tags", md)
        self.assertIn("nested", md)
        self.assertIn("details", md["nested"])  # retained
        # Sensitive keys removed
        self.assertNotIn("exception", md)
        self.assertNotIn("token", md)
        self.assertNotIn("password", md.get("nested", {}))

    def test_retry_state_authority(self):
        event = project_retry_execution_event(
            mission_id="m-6",
            execution_id="e-6",
            attempt=1,
            classification_result={"kind": "retryable"},
            retry_budget_projection={"eligible": True, "remaining": 2, "limit": 3},
        )
        self.assertEqual(event["retry"]["authority"], "MissionQueue")
        self.assertTrue(event["integration"]["retry_classification_integrated"]) 
        self.assertTrue(event["integration"]["retry_budget_projection_integrated"]) 

    def test_no_sleep_no_retry_loop_no_network(self):
        classification = {"kind": "retryable"}
        with patch("time.sleep") as mocked_sleep, \
             patch.object(socket, "socket", wraps=socket.socket) as mocked_socket:
            event = project_retry_execution_event(
                mission_id="m-7",
                execution_id="e-7",
                attempt=1,
                classification_result=classification,
            )
            # This adapter never calls sleep or touches network
            mocked_sleep.assert_not_called()
            mocked_socket.assert_not_called()
            # Also confirm JSON serializable and minimal fields exist
            json.dumps(event)

    def test_no_queue_or_counter_mutation(self):
        queue = {"attempts_done": 5, "max_attempts": 5}
        budget = {"eligible": False, "remaining": 0, "limit": 5}
        queue_before = json.loads(json.dumps(queue))
        budget_before = json.loads(json.dumps(budget))

        _ = project_retry_execution_event(
            mission_id="m-8",
            execution_id="e-8",
            attempt=5,
            classification_result={"exhausted": True},
            mission_queue_projection=queue,
            retry_budget_projection=budget,
        )
        # Ensure inputs unchanged
        self.assertEqual(queue, queue_before)
        self.assertEqual(budget, budget_before)


if __name__ == "__main__":
    unittest.main()
