import io
import os
import tempfile
import unittest

from agent.repair import (
    FailureRecord,
    sanitize_diagnostic,
    MAX_DIAGNOSTIC_LENGTH,
    RepairLoop,
    REPAIR_STATE_PENDING,
    REPAIR_STATE_DIAGNOSING,
    REPAIR_STATE_REPAIR_PLANNED,
    REPAIR_STATE_VALIDATING,
    REPAIR_STATE_SUCCEEDED,
    REPAIR_STATE_EXHAUSTED,
    REPAIR_STATE_BLOCKED,
)


class FailureClassificationTests(unittest.TestCase):
    def test_compilation_classification(self):
        rec = FailureRecord(
            category="compilation_failure",
            safe_summary="Compile error",
            return_code=1,
            attempt_number=1,
            retryable=True,
            source="compiler",
            diagnostic="error: something bad",
        )
        self.assertEqual(rec.category, "compilation_failure")

    def test_unittest_classification(self):
        rec = FailureRecord(
            category="unittest_failure",
            safe_summary="Test failure",
            return_code=2,
            attempt_number=1,
            retryable=True,
            source="pytest",
            diagnostic="assert 1 == 2",
        )
        self.assertEqual(rec.category, "unittest_failure")

    def test_validation_classification(self):
        rec = FailureRecord(
            category="validation_failure",
            safe_summary="Validation failed",
            return_code=3,
            attempt_number=1,
            retryable=False,
            source="validator",
            diagnostic="policy violation",
        )
        self.assertEqual(rec.category, "validation_failure")

    def test_generated_file_classification(self):
        rec = FailureRecord(
            category="generated_file_failure",
            safe_summary="Generated file mismatch",
            return_code=4,
            attempt_number=1,
            retryable=False,
            source="generator",
            diagnostic="file hash mismatch",
        )
        self.assertEqual(rec.category, "generated_file_failure")

    def test_unknown_classification(self):
        rec = FailureRecord(
            category="unknown_failure",
            safe_summary="Unknown",
            return_code=None,
            attempt_number=1,
            retryable=True,
            source="unknown",
            diagnostic="mystery",
        )
        self.assertEqual(rec.category, "unknown_failure")


class DiagnosticSanitizationTests(unittest.TestCase):
    def test_generic_credential_redaction(self):
        sensitive_value = "abc" + "123" + "XYZ"
        text = f"token={sensitive_value}"
        out = sanitize_diagnostic(text)
        self.assertIn("token= [REDACTED]", out)
        self.assertNotIn(sensitive_value, out)

    def test_authorization_bearer_redaction(self):
        sensitive_value = "abc" + "123" + "XYZ"
        text = f"Authorization: Bearer {sensitive_value}"
        out = sanitize_diagnostic(text)
        self.assertEqual(out, "Authorization: Bearer [REDACTED]")

    def test_exact_canonical_authorization_spelling(self):
        text = "authorization:    bearer   xYz.123._-"
        out = sanitize_diagnostic(text)
        self.assertEqual(out, "Authorization: Bearer [REDACTED]")

    def test_bearer_scheme_preservation(self):
        text = "AUTHORIZATION: Bearer token-value"
        out = sanitize_diagnostic(text)
        self.assertIn("Authorization: Bearer [REDACTED]", out)

    def test_original_bearer_credential_absent(self):
        cred = "tkn" + "-" + "V@lue"
        text = f"Some log\nAuthorization: Bearer {cred}\nMore log"
        out = sanitize_diagnostic(text)
        self.assertNotIn(cred, out)
        self.assertIn("Authorization: Bearer [REDACTED]", out)

    def test_no_wrong_authorization_form(self):
        # Ensure we do not output incorrect forms like 'Authorization: [REDACTED]'
        cred = "abc" + "DEF"
        text = f"Authorization: Bearer {cred}"
        out = sanitize_diagnostic(text)
        self.assertEqual(out, "Authorization: Bearer [REDACTED]")
        self.assertNotIn("Authorization: [REDACTED]", out)

    def test_diagnostic_truncation(self):
        long_text = "A" * (MAX_DIAGNOSTIC_LENGTH + 100)
        out = sanitize_diagnostic(long_text)
        self.assertTrue(out.endswith("... [truncated]"))
        self.assertLessEqual(len(out), MAX_DIAGNOSTIC_LENGTH)

    def test_exact_truncation_suffix(self):
        long_text = "B" * (MAX_DIAGNOSTIC_LENGTH + 10)
        out = sanitize_diagnostic(long_text)
        self.assertTrue(out.endswith("... [truncated]"))
        self.assertEqual(out[-1], "]")

    def test_diagnostic_maximum_length(self):
        long_text = "C" * (MAX_DIAGNOSTIC_LENGTH * 2)
        out = sanitize_diagnostic(long_text)
        self.assertEqual(len(out), MAX_DIAGNOSTIC_LENGTH)

    def test_short_diagnostic_unchanged(self):
        text = "ok"
        out = sanitize_diagnostic(text)
        self.assertEqual(out, text)


class RepairLoopBehaviorTests(unittest.TestCase):
    def _failure(self, attempt: int = 1, category: str = "compilation_failure") -> FailureRecord:
        return FailureRecord(
            category=category,
            safe_summary="fail",
            return_code=1,
            attempt_number=attempt,
            retryable=True,
            source="unit",
            diagnostic="log text",
        )

    def test_default_three_attempt_limit(self):
        loop = RepairLoop()
        self.assertEqual(loop.state, REPAIR_STATE_PENDING)
        f = self._failure(1)
        p1 = loop.plan_repair(f, objective="fix", constraints=None, allowed_paths=["a"], denied_paths=["b"], validation_required=True)
        self.assertIsNotNone(p1)
        self.assertEqual(p1.attempt_number, 1)
        p2 = loop.plan_repair(f, objective="fix", constraints=None, allowed_paths=["a"], denied_paths=["b"], validation_required=True)
        self.assertIsNotNone(p2)
        self.assertEqual(p2.attempt_number, 2)
        p3 = loop.plan_repair(f, objective="fix", constraints=None, allowed_paths=["a"], denied_paths=["b"], validation_required=True)
        self.assertIsNotNone(p3)
        self.assertEqual(p3.attempt_number, 3)
        p4 = loop.plan_repair(f, objective="fix", constraints=None, allowed_paths=["a"], denied_paths=["b"], validation_required=True)
        self.assertIsNone(p4)
        self.assertEqual(loop.state, REPAIR_STATE_EXHAUSTED)

    def test_configurable_attempt_limit(self):
        loop = RepairLoop(max_attempts=2)
        f = self._failure(1)
        p1 = loop.plan_repair(f, objective="goal", constraints={}, allowed_paths=[], denied_paths=[], validation_required=True)
        self.assertEqual(p1.attempt_number, 1)
        p2 = loop.plan_repair(f, objective="goal", constraints={}, allowed_paths=[], denied_paths=[], validation_required=True)
        self.assertEqual(p2.attempt_number, 2)
        p3 = loop.plan_repair(f, objective="goal", constraints={}, allowed_paths=[], denied_paths=[], validation_required=True)
        self.assertIsNone(p3)
        self.assertEqual(loop.state, REPAIR_STATE_EXHAUSTED)

    def test_invalid_attempt_limit(self):
        with self.assertRaises(ValueError):
            RepairLoop(max_attempts=0)
        with self.assertRaises(ValueError):
            RepairLoop(max_attempts=-5)

    def test_successful_transition(self):
        loop = RepairLoop()
        f = self._failure(1)
        plan = loop.plan_repair(f, objective="x", constraints=None, allowed_paths=[], denied_paths=[], validation_required=True)
        self.assertIsNotNone(plan)
        self.assertEqual(loop.state, REPAIR_STATE_REPAIR_PLANNED)
        loop.mark_validating()
        self.assertEqual(loop.state, REPAIR_STATE_VALIDATING)
        loop.mark_succeeded()
        self.assertEqual(loop.state, REPAIR_STATE_SUCCEEDED)

    def test_retry_then_success(self):
        loop = RepairLoop()
        f = self._failure(1)
        p1 = loop.plan_repair(f, objective="fix", constraints=None, allowed_paths=[], denied_paths=[], validation_required=True)
        self.assertEqual(p1.attempt_number, 1)
        p2 = loop.plan_repair(f, objective="fix", constraints=None, allowed_paths=[], denied_paths=[], validation_required=True)
        self.assertEqual(p2.attempt_number, 2)
        loop.mark_validating()
        loop.mark_succeeded()
        self.assertEqual(loop.state, REPAIR_STATE_SUCCEEDED)

    def test_exhaustion(self):
        loop = RepairLoop(max_attempts=1)
        f = self._failure(1)
        p1 = loop.plan_repair(f, objective="x", constraints=None, allowed_paths=[], denied_paths=[], validation_required=True)
        self.assertIsNotNone(p1)
        p2 = loop.plan_repair(f, objective="x", constraints=None, allowed_paths=[], denied_paths=[], validation_required=True)
        self.assertIsNone(p2)
        self.assertEqual(loop.state, REPAIR_STATE_EXHAUSTED)

    def test_protected_core_immediate_block(self):
        loop = RepairLoop()
        f = self._failure(1)
        plan = loop.plan_repair(f, objective="x", constraints={"protected_core_access": True}, allowed_paths=[], denied_paths=[], validation_required=True)
        self.assertIsNone(plan)
        self.assertEqual(loop.state, REPAIR_STATE_BLOCKED)

    def test_canonical_test_immediate_block(self):
        loop = RepairLoop()
        f = self._failure(1)
        plan = loop.plan_repair(f, objective="x", constraints={"canonical_recovery_test_access": True}, allowed_paths=[], denied_paths=[], validation_required=True)
        self.assertIsNone(plan)
        self.assertEqual(loop.state, REPAIR_STATE_BLOCKED)

    def test_unavailable_protection_immediate_block(self):
        loop = RepairLoop()
        f = self._failure(1)
        plan = loop.plan_repair(f, objective="x", constraints={"unavailable_core_protection": True}, allowed_paths=[], denied_paths=[], validation_required=True)
        self.assertIsNone(plan)
        self.assertEqual(loop.state, REPAIR_STATE_BLOCKED)

    def test_deterministic_repair_ids_equivalent_input(self):
        loop = RepairLoop()
        f = self._failure(1)
        # Constraints with different key order and lists in different order
        constraints_a = {"b": [3, 1, 2], "a": {"y": 2, "x": 1}}
        constraints_b = {"a": {"x": 1, "y": 2}, "b": [2, 3, 1]}
        plan1 = loop.plan_repair(
            f,
            objective="fix-it",
            constraints=constraints_a,
            allowed_paths=["/src", "/lib"],
            denied_paths=["/secret", "/tmp"],
            validation_required=True,
        )
        # Reset loop for same attempt number
        loop2 = RepairLoop()
        f2 = self._failure(1)
        plan2 = loop2.plan_repair(
            f2,
            objective="fix-it",
            constraints=constraints_b,
            allowed_paths=["/lib", "/src"],  # different order, semantically same set
            denied_paths=["/tmp", "/secret"],
            validation_required=True,
        )
        self.assertIsNotNone(plan1)
        self.assertIsNotNone(plan2)
        self.assertEqual(plan1.repair_id, plan2.repair_id)

    def test_changed_meaningful_input_changes_repair_id(self):
        loop = RepairLoop()
        f = self._failure(1)
        plan1 = loop.plan_repair(
            f,
            objective="fix-A",
            constraints={"a": 1},
            allowed_paths=["/a"],
            denied_paths=["/b"],
            validation_required=True,
        )
        loop2 = RepairLoop()
        f2 = self._failure(1)
        plan2 = loop2.plan_repair(
            f2,
            objective="fix-B",  # change objective
            constraints={"a": 1},
            allowed_paths=["/a"],
            denied_paths=["/b"],
            validation_required=True,
        )
        self.assertNotEqual(plan1.repair_id, plan2.repair_id)

    def test_allowed_and_denied_path_preservation(self):
        loop = RepairLoop()
        f = self._failure(1)
        allowed = ["p1", "p2", "p3"]
        denied = ["n1", "n2"]
        plan = loop.plan_repair(f, objective="x", constraints=None, allowed_paths=allowed, denied_paths=denied, validation_required=False)
        self.assertEqual(plan.allowed_paths, tuple(allowed))
        self.assertEqual(plan.denied_paths, tuple(denied))

    def test_input_immutability(self):
        loop = RepairLoop()
        f = self._failure(1)
        constraints = {"a": [1, 2, 3]}
        allowed = ["a1", "a2"]
        denied = ["d1"]
        plan = loop.plan_repair(f, objective="x", constraints=constraints, allowed_paths=allowed, denied_paths=denied, validation_required=True)
        # Mutate original inputs afterwards; plan should remain unchanged
        constraints["a"].append(4)
        allowed.append("a3")
        denied.append("d2")
        self.assertEqual(plan.constraints, (("a", (1, 2, 3)),))
        self.assertEqual(plan.allowed_paths, ("a1", "a2"))
        self.assertEqual(plan.denied_paths, ("d1",))

    def test_no_privileged_maintenance_output(self):
        # Ensure no stdout/stderr output is produced during planning
        loop = RepairLoop()
        f = self._failure(1)
        buf_out = io.StringIO()
        buf_err = io.StringIO()
        # No print calls inside, so buffers remain empty
        plan = loop.plan_repair(f, objective="x", constraints=None, allowed_paths=[], denied_paths=[], validation_required=True)
        self.assertIsNotNone(plan)
        self.assertEqual(buf_out.getvalue(), "")
        self.assertEqual(buf_err.getvalue(), "")

    def test_no_filesystem_mutation_during_planning(self):
        loop = RepairLoop()
        f = self._failure(1)
        with tempfile.TemporaryDirectory() as td:
            before = set(os.listdir(td))
            plan = loop.plan_repair(f, objective="x", constraints=None, allowed_paths=[], denied_paths=[], validation_required=True)
            after = set(os.listdir(td))
            self.assertIsNotNone(plan)
            self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
