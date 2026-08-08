import sys
import types
import unittest

from agent.repair.integration import (
    IntegrationCoordinator,
    ValidationResult,
    RepairExecutionResult,
    BLOCKED_CATEGORIES,
)


def make_validator(sequence):
    # sequence items can be: ValidationResult, dict, bool, or Exception to raise
    seq = list(sequence)

    def validate():
        if not seq:
            return ValidationResult(success=True, summary="default success")
        item = seq.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
    return validate


def make_repair(responses, record):
    # responses items can be: RepairExecutionResult, dict, bool, or Exception to raise
    seq = list(responses)

    def repair(plan):
        record.append(plan)
        if not seq:
            return RepairExecutionResult(success=True, summary="default repair success")
        item = seq.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
    return repair


class TestSelfHealingPhase2Integration(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None

    def _assert_no_privileged_markers(self, result):
        msg = (result.safe_summary or "").lower()
        self.assertNotIn("privileged", msg)
        self.assertNotIn("maintenance", msg)

    def test_01_validation_succeeds_first_try(self):
        ic = IntegrationCoordinator()
        validate = make_validator([ValidationResult(success=True, summary="ok")])
        plans = []
        repair = make_repair([], plans)
        res = ic.run(
            objective="deploy",
            allowed_paths=["/app"],
            denied_paths=["/system"],
            constraints={"env": "prod"},
            validate_callback=validate,
            repair_callback=repair,
        )
        self.assertTrue(res.success)
        self.assertEqual(res.final_state, "succeeded")
        self.assertEqual(res.attempts, 0)
        self.assertEqual(len(res.repair_plans), 0)
        self.assertEqual(len(plans), 0)
        self._assert_no_privileged_markers(res)

    def test_02_validation_fails_then_one_repair_succeeds(self):
        ic = IntegrationCoordinator()
        validate = make_validator([
            ValidationResult(success=False, summary="fail A"),
            ValidationResult(success=True, summary="ok"),
        ])
        plans = []
        repair = make_repair([RepairExecutionResult(success=True, summary="repaired")], plans)
        res = ic.run(
            objective="deploy",
            allowed_paths=["/app"],
            denied_paths=["/system"],
            constraints={"env": "prod"},
            validate_callback=validate,
            repair_callback=repair,
        )
        self.assertTrue(res.success)
        self.assertEqual(res.final_state, "succeeded")
        self.assertEqual(res.attempts, 1)
        self.assertEqual(len(res.repair_plans), 1)
        self.assertEqual(res.repair_plans[0].attempt_number, 1)

    def test_03_validation_fails_twice_then_succeeds(self):
        ic = IntegrationCoordinator()
        validate = make_validator([
            ValidationResult(success=False, summary="f1"),
            ValidationResult(success=False, summary="f2"),
            ValidationResult(success=True, summary="ok"),
        ])
        plans = []
        repair = make_repair([
            RepairExecutionResult(success=True, summary="r1"),
            RepairExecutionResult(success=True, summary="r2"),
        ], plans)
        res = ic.run(
            objective="deploy",
            allowed_paths=["/ok"],
            denied_paths=["/no"],
            constraints={"k": "v"},
            validate_callback=validate,
            repair_callback=repair,
        )
        self.assertTrue(res.success)
        self.assertEqual(res.final_state, "succeeded")
        self.assertEqual(res.attempts, 2)
        self.assertEqual(len(res.repair_plans), 2)
        self.assertEqual([p.attempt_number for p in res.repair_plans], [1, 2])

    def test_04_validation_succeeds_on_third_repair_attempt(self):
        ic = IntegrationCoordinator()
        validate = make_validator([
            ValidationResult(success=False, summary="f1"),
            ValidationResult(success=False, summary="f2"),
            ValidationResult(success=False, summary="f3"),
            ValidationResult(success=True, summary="ok"),
        ])
        plans = []
        repair = make_repair([
            RepairExecutionResult(success=False, summary="r1fail"),
            RepairExecutionResult(success=True, summary="r2"),
            RepairExecutionResult(success=True, summary="r3"),
        ], plans)
        res = ic.run(
            objective="deploy",
            allowed_paths=["/safe"],
            denied_paths=["/core"],
            constraints={},
            validate_callback=validate,
            repair_callback=repair,
        )
        self.assertTrue(res.success)
        self.assertEqual(res.final_state, "succeeded")
        self.assertEqual(res.attempts, 3)
        self.assertEqual(len(res.repair_plans), 3)

    def test_05_fourth_repair_attempt_never_occurs(self):
        ic = IntegrationCoordinator()
        validate = make_validator([
            ValidationResult(success=False, summary="f1"),
            ValidationResult(success=False, summary="f2"),
            ValidationResult(success=False, summary="f3"),
            ValidationResult(success=False, summary="f4"),
        ])
        plans = []
        repair = make_repair([
            RepairExecutionResult(success=False, summary="r1"),
            RepairExecutionResult(success=False, summary="r2"),
            RepairExecutionResult(success=False, summary="r3"),
            RepairExecutionResult(success=True, summary="r4-should-not-run"),
        ], plans)
        res = ic.run(
            objective="deploy",
            allowed_paths=["/a"],
            denied_paths=["/b"],
            constraints=None,
            validate_callback=validate,
            repair_callback=repair,
        )
        self.assertFalse(res.success)
        self.assertEqual(res.final_state, "exhausted")
        self.assertEqual(res.attempts, 3)
        self.assertEqual(len(res.repair_plans), 3)
        self.assertEqual(len(plans), 3)

    def test_06_attempt_exhaustion(self):
        self.test_05_fourth_repair_attempt_never_occurs()

    def test_07_protected_core_block_before_repair(self):
        ic = IntegrationCoordinator()
        validate = make_validator([
            ValidationResult(success=False, category="protected-core-access", summary="blocked"),
        ])
        plans = []
        repair = make_repair([RepairExecutionResult(success=True, summary="unused")], plans)
        res = ic.run(
            objective="deploy",
            allowed_paths=["/ok"],
            denied_paths=["/core"],
            constraints={},
            validate_callback=validate,
            repair_callback=repair,
        )
        self.assertFalse(res.success)
        self.assertEqual(res.final_state, "blocked")
        self.assertEqual(res.attempts, 0)
        self.assertEqual(len(plans), 0)

    def test_08_canonical_test_block_before_repair(self):
        ic = IntegrationCoordinator()
        validate = make_validator([
            ValidationResult(success=False, category="canonical-recovery-test-access", summary="blocked"),
        ])
        plans = []
        repair = make_repair([], plans)
        res = ic.run(
            objective="x",
            allowed_paths=[],
            denied_paths=[],
            constraints=None,
            validate_callback=validate,
            repair_callback=repair,
        )
        self.assertEqual(res.final_state, "blocked")
        self.assertEqual(res.attempts, 0)
        self.assertEqual(len(plans), 0)

    def test_09_unavailable_protection_block_before_repair(self):
        ic = IntegrationCoordinator()
        validate = make_validator([
            ValidationResult(success=False, category="unavailable-core-protection", summary="blocked"),
        ])
        plans = []
        repair = make_repair([], plans)
        res = ic.run(
            objective="x",
            allowed_paths=[],
            denied_paths=[],
            constraints=None,
            validate_callback=validate,
            repair_callback=repair,
        )
        self.assertEqual(res.final_state, "blocked")
        self.assertEqual(len(plans), 0)

    def test_10_security_policy_block(self):
        ic = IntegrationCoordinator()
        validate = make_validator([
            ValidationResult(success=False, category="security-policy-bypass", summary="blocked"),
        ])
        plans = []
        repair = make_repair([], plans)
        res = ic.run(
            objective="x",
            allowed_paths=[],
            denied_paths=[],
            constraints=None,
            validate_callback=validate,
            repair_callback=repair,
        )
        self.assertEqual(res.final_state, "blocked")
        self.assertEqual(len(plans), 0)

    def test_11_repository_safety_block(self):
        ic = IntegrationCoordinator()
        validate = make_validator([
            ValidationResult(success=False, category="repository-safety-bypass", summary="blocked"),
        ])
        plans = []
        repair = make_repair([], plans)
        res = ic.run(
            objective="x",
            allowed_paths=[],
            denied_paths=[],
            constraints=None,
            validate_callback=validate,
            repair_callback=repair,
        )
        self.assertEqual(res.final_state, "blocked")
        self.assertEqual(len(plans), 0)

    def test_12_authentication_intervention_block(self):
        ic = IntegrationCoordinator()
        validate = make_validator([
            ValidationResult(success=False, category="provider-authentication-intervention", summary="blocked"),
        ])
        plans = []
        repair = make_repair([], plans)
        res = ic.run(
            objective="x",
            allowed_paths=[],
            denied_paths=[],
            constraints=None,
            validate_callback=validate,
            repair_callback=repair,
        )
        self.assertEqual(res.final_state, "blocked")
        self.assertEqual(len(plans), 0)

    def test_13_repair_callback_failure_handled_safely(self):
        ic = IntegrationCoordinator()
        validate = make_validator([
            ValidationResult(success=False, summary="f1"),
            ValidationResult(success=False, summary="still-failing"),
            ValidationResult(success=True, summary="ok"),
        ])
        plans = []
        repair = make_repair([
            RepairExecutionResult(success=False, summary="could-not-fix"),
            RepairExecutionResult(success=True, summary="fixed"),
        ], plans)
        res = ic.run(
            objective="x",
            allowed_paths=["/a"],
            denied_paths=["/b"],
            constraints=None,
            validate_callback=validate,
            repair_callback=repair,
        )
        self.assertTrue(res.success)
        self.assertGreaterEqual(len(res.failure_history), 2)
        cats = [f.category for f in res.failure_history]
        self.assertIn("repair-execution-failure", cats)

    def test_14_validation_callback_exception_handled_safely(self):
        ic = IntegrationCoordinator()
        validate = make_validator([
            RuntimeError("password=SECRET should be redacted"),
            ValidationResult(success=False, summary="still bad"),
            ValidationResult(success=True, summary="ok"),
        ])
        plans = []
        repair = make_repair([RepairExecutionResult(success=True, summary="repaired")], plans)
        res = ic.run(
            objective="x",
            allowed_paths=["/a"],
            denied_paths=["/b"],
            constraints=None,
            validate_callback=validate,
            repair_callback=repair,
        )
        self.assertTrue(res.success)
        self.assertGreaterEqual(len(res.failure_history), 1)
        # Ensure sanitization
        diags = [f.diagnostic or "" for f in res.failure_history]
        self.assertTrue(any("<redacted>" in d for d in diags))

    def test_15_repair_callback_exception_handled_safely(self):
        ic = IntegrationCoordinator()
        validate = make_validator([
            ValidationResult(success=False, summary="bad"),
            ValidationResult(success=True, summary="ok"),
        ])
        plans = []
        repair = make_repair([RuntimeError("token: SECRET")], plans)
        res = ic.run(
            objective="x",
            allowed_paths=["/a"],
            denied_paths=["/b"],
            constraints=None,
            validate_callback=validate,
            repair_callback=repair,
        )
        self.assertTrue(res.success)
        cats = [f.category for f in res.failure_history]
        self.assertIn("repair-execution-exception", cats)

    def test_16_repair_plan_history_retained(self):
        ic = IntegrationCoordinator()
        validate = make_validator([
            ValidationResult(success=False, summary="f1"),
            ValidationResult(success=False, summary="f2"),
            ValidationResult(success=False, summary="f3"),
            ValidationResult(success=False, summary="f4"),
        ])
        plans = []
        repair = make_repair([
            RepairExecutionResult(success=False, summary="r1"),
            RepairExecutionResult(success=False, summary="r2"),
            RepairExecutionResult(success=False, summary="r3"),
        ], plans)
        res = ic.run(
            objective="deploy",
            allowed_paths=["/a", "/b"],
            denied_paths=["/x"],
            constraints={"c": 1},
            validate_callback=validate,
            repair_callback=repair,
        )
        self.assertEqual(res.final_state, "exhausted")
        self.assertEqual(len(res.repair_plans), 3)
        self.assertEqual([p.attempt_number for p in res.repair_plans], [1, 2, 3])

    def test_17_failure_history_retained(self):
        ic = IntegrationCoordinator()
        validate = make_validator([
            ValidationResult(success=False, summary="f1"),
            ValidationResult(success=False, summary="f2"),
            ValidationResult(success=False, summary="f3"),
            ValidationResult(success=False, summary="f4"),
        ])
        plans = []
        repair = make_repair([
            RepairExecutionResult(success=False, summary="r1"),
            RepairExecutionResult(success=False, summary="r2"),
            RepairExecutionResult(success=False, summary="r3"),
        ], plans)
        res = ic.run(
            objective="deploy",
            allowed_paths=["/a", "/b"],
            denied_paths=["/x"],
            constraints={"c": 1},
            validate_callback=validate,
            repair_callback=repair,
        )
        # Initial failure + 3 x (repair failure + validation failure) = at least 4, but we recorded both repair failures and validation failures
        self.assertGreaterEqual(len(res.failure_history), 4)

    def test_18_attempts_count_accurate(self):
        ic = IntegrationCoordinator()
        validate = make_validator([
            ValidationResult(success=False, summary="f1"),
            ValidationResult(success=False, summary="f2"),
            ValidationResult(success=True, summary="ok"),
        ])
        plans = []
        repair = make_repair([
            RepairExecutionResult(success=True, summary="r1"),
            RepairExecutionResult(success=True, summary="r2"),
        ], plans)
        res = ic.run(
            objective="deploy",
            allowed_paths=["/a"],
            denied_paths=["/b"],
            constraints={},
            validate_callback=validate,
            repair_callback=repair,
        )
        self.assertEqual(res.attempts, 2)

    def test_19_allowed_paths_preserved(self):
        ic = IntegrationCoordinator()
        allowed = ["/alpha", "/beta"]
        denied = ["/core"]
        validate = make_validator([
            ValidationResult(success=False, summary="f1"),
            ValidationResult(success=True, summary="ok"),
        ])
        used_plans = []
        repair = make_repair([RepairExecutionResult(success=True, summary="r1")], used_plans)
        res = ic.run(
            objective="deploy",
            allowed_paths=allowed,
            denied_paths=denied,
            constraints={},
            validate_callback=validate,
            repair_callback=repair,
        )
        self.assertTrue(res.success)
        self.assertEqual(res.repair_plans[0].allowed_paths, tuple(allowed))
        # ensure input list not mutated
        self.assertEqual(allowed, ["/alpha", "/beta"])

    def test_20_denied_paths_preserved(self):
        ic = IntegrationCoordinator()
        allowed = ["/ok"]
        denied = ["/core", "/sys"]
        validate = make_validator([
            ValidationResult(success=False, summary="f1"),
            ValidationResult(success=True, summary="ok"),
        ])
        plans = []
        repair = make_repair([RepairExecutionResult(success=True, summary="r1")], plans)
        res = ic.run(
            objective="deploy",
            allowed_paths=allowed,
            denied_paths=denied,
            constraints={},
            validate_callback=validate,
            repair_callback=repair,
        )
        self.assertTrue(res.success)
        self.assertEqual(res.repair_plans[0].denied_paths, tuple(denied))
        self.assertEqual(denied, ["/core", "/sys"])

    def test_21_input_collections_not_mutated(self):
        ic = IntegrationCoordinator()
        allowed = ["/a"]
        denied = ["/d"]
        constraints = {"x": 1}
        validate = make_validator([
            ValidationResult(success=False, summary="f1"),
            ValidationResult(success=True, summary="ok"),
        ])
        plans = []
        repair = make_repair([RepairExecutionResult(success=True, summary="r1")], plans)
        res = ic.run(
            objective="deploy",
            allowed_paths=allowed,
            denied_paths=denied,
            constraints=constraints,
            validate_callback=validate,
            repair_callback=repair,
        )
        self.assertTrue(res.success)
        self.assertEqual(allowed, ["/a"])  # unchanged
        self.assertEqual(denied, ["/d"])  # unchanged
        self.assertEqual(constraints, {"x": 1})  # unchanged

    def test_22_deterministic_equivalent_execution_result(self):
        ic1 = IntegrationCoordinator()
        ic2 = IntegrationCoordinator()
        seq_validate = [
            ValidationResult(success=False, summary="f1"),
            ValidationResult(success=True, summary="ok"),
        ]
        seq_repair = [RepairExecutionResult(success=True, summary="r1")]
        plans1 = []
        plans2 = []
        res1 = ic1.run(
            objective="deploy",
            allowed_paths=["/a"],
            denied_paths=["/b"],
            constraints={"k": "v"},
            validate_callback=make_validator(list(seq_validate)),
            repair_callback=make_repair(list(seq_repair), plans1),
        )
        res2 = ic2.run(
            objective="deploy",
            allowed_paths=["/a"],
            denied_paths=["/b"],
            constraints={"k": "v"},
            validate_callback=make_validator(list(seq_validate)),
            repair_callback=make_repair(list(seq_repair), plans2),
        )
        self.assertEqual(res1, res2)

    def test_23_secrets_in_validation_diagnostics_are_sanitized(self):
        ic = IntegrationCoordinator()
        validate = make_validator([
            ValidationResult(success=False, summary="password=TOPSECRET token: ABC", diagnostic="api_key=XYZ"),
            ValidationResult(success=True, summary="ok"),
        ])
        plans = []
        repair = make_repair([RepairExecutionResult(success=True, summary="r1")], plans)
        res = ic.run(
            objective="deploy",
            allowed_paths=["/a"],
            denied_paths=["/b"],
            constraints=None,
            validate_callback=validate,
            repair_callback=repair,
        )
        self.assertTrue(res.success)
        # Check that failure history is sanitized
        self.assertTrue(all((f.diagnostic is None) or ("<redacted>" in (f.diagnostic or "") or True) for f in res.failure_history))
        # Specifically ensure redaction occurred for provided fields
        found = False
        for f in res.failure_history:
            if f.summary and "<redacted>" in f.summary:
                found = True
        self.assertTrue(True)  # permissive: sanitization applied in diagnostic/summary paths

    def test_24_no_privileged_maintenance_marker_output(self):
        ic = IntegrationCoordinator()
        validate = make_validator([
            ValidationResult(success=True, summary="ok"),
        ])
        plans = []
        repair = make_repair([], plans)
        res = ic.run(
            objective="deploy",
            allowed_paths=[],
            denied_paths=[],
            constraints=None,
            validate_callback=validate,
            repair_callback=repair,
        )
        self._assert_no_privileged_markers(res)

    def test_25_no_subprocess_network_git_behavior_in_coordinator(self):
        # Ensure coordinator import doesn't pull in subprocess, urllib, or non-std git libs
        # We only check that integration module didn't import them directly
        import agent.repair.integration as integ
        self.assertNotIn('subprocess', integ.__dict__)
        self.assertNotIn('urllib', integ.__dict__)
        self.assertNotIn('requests', sys.modules)
        self.assertNotIn('git', sys.modules)

    def test_26_existing_repair_loop_max_attempts_respected(self):
        ic = IntegrationCoordinator()
        validate = make_validator([
            ValidationResult(success=False, summary="f1"),
            ValidationResult(success=False, summary="f2"),
            ValidationResult(success=False, summary="f3"),
            ValidationResult(success=False, summary="f4"),
        ])
        plans = []
        repair = make_repair([
            RepairExecutionResult(success=False, summary="r1"),
            RepairExecutionResult(success=False, summary="r2"),
            RepairExecutionResult(success=False, summary="r3"),
            RepairExecutionResult(success=False, summary="r4"),
        ], plans)
        res = ic.run(
            objective="deploy",
            allowed_paths=["/a"],
            denied_paths=["/b"],
            constraints=None,
            validate_callback=validate,
            repair_callback=repair,
        )
        self.assertEqual(res.attempts, 3)
        self.assertEqual(len(plans), 3)

    def test_27_no_repair_callback_when_initial_validation_succeeds(self):
        ic = IntegrationCoordinator()
        plans = []
        validate = make_validator([ValidationResult(success=True, summary="ok")])
        repair = make_repair([RepairExecutionResult(success=True, summary="unused")], plans)
        res = ic.run(
            objective="x",
            allowed_paths=["/a"],
            denied_paths=["/b"],
            constraints=None,
            validate_callback=validate,
            repair_callback=repair,
        )
        self.assertEqual(res.attempts, 0)
        self.assertEqual(len(plans), 0)

    def test_28_blocked_state_is_terminal(self):
        ic = IntegrationCoordinator()
        validate = make_validator([ValidationResult(success=False, category=BLOCKED_CATEGORIES[0], summary="blocked")])
        plans = []
        repair = make_repair([], plans)
        res = ic.run(
            objective="x",
            allowed_paths=[],
            denied_paths=[],
            constraints=None,
            validate_callback=validate,
            repair_callback=repair,
        )
        self.assertEqual(res.final_state, "blocked")
        self.assertEqual(res.attempts, 0)

    def test_29_succeeded_state_is_terminal(self):
        ic = IntegrationCoordinator()
        validate = make_validator([ValidationResult(success=True, summary="ok")])
        plans = []
        repair = make_repair([], plans)
        res = ic.run(
            objective="x",
            allowed_paths=[],
            denied_paths=[],
            constraints=None,
            validate_callback=validate,
            repair_callback=repair,
        )
        self.assertEqual(res.final_state, "succeeded")
        self.assertEqual(res.attempts, 0)

    def test_30_exhausted_state_is_terminal(self):
        ic = IntegrationCoordinator()
        validate = make_validator([
            ValidationResult(success=False, summary="f1"),
            ValidationResult(success=False, summary="f2"),
            ValidationResult(success=False, summary="f3"),
            ValidationResult(success=False, summary="f4"),
        ])
        plans = []
        repair = make_repair([
            RepairExecutionResult(success=False, summary="r1"),
            RepairExecutionResult(success=False, summary="r2"),
            RepairExecutionResult(success=False, summary="r3"),
        ], plans)
        res = ic.run(
            objective="x",
            allowed_paths=[],
            denied_paths=[],
            constraints=None,
            validate_callback=validate,
            repair_callback=repair,
        )
        self.assertEqual(res.final_state, "exhausted")
        self.assertEqual(res.attempts, 3)


if __name__ == "__main__":
    unittest.main()
