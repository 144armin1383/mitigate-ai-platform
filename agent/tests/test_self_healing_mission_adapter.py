import ast
import io
import unittest
from contextlib import redirect_stdout
from typing import Any, Dict, List

from agent.repair.mission_adapter import MissionRepairAdapter, RepairRequest


class TestMissionRepairAdapter(unittest.TestCase):
    # Utility helpers
    def _make_adapter(self, *, validate, generate, apply):
        return MissionRepairAdapter(
            integration_coordinator=object(),
            validate_callback=validate,
            generate_callback=generate,
            apply_callback=apply,
        )

    def test_01_initial_validation_success(self):
        calls = {"gen": 0, "app": 0}

        def validate():
            return True

        def generate(_req):
            calls["gen"] += 1
            return {"success": True, "plan": "fix"}

        def apply(_payload):
            calls["app"] += 1
            return {"success": True}

        adapter = self._make_adapter(validate=validate, generate=generate, apply=apply)
        out = adapter.run(
            mission_name="m1",
            objective="stabilize",
            failure_category="unit-test",
            failure_summary="none",
            allowed_paths=[".", "src"],
            denied_paths=["/etc"],
        )
        self.assertEqual(out["status"], "succeeded")
        self.assertEqual(out["attempts"], 0)
        self.assertEqual(calls["gen"], 0)
        self.assertEqual(calls["app"], 0)

    def test_02_one_repair_success(self):
        applied = {"count": 0}

        def validate():
            # success after first apply
            return applied["count"] >= 1

        def generate(req: RepairRequest):
            self.assertIsInstance(req, RepairRequest)
            return {"success": True, "plan": f"fix-{req.attempt_number}"}

        def apply(_payload):
            applied["count"] += 1
            return True

        adapter = self._make_adapter(validate=validate, generate=generate, apply=apply)
        out = adapter.run(
            mission_name="m2",
            objective="stabilize",
            failure_category="unit-test",
            failure_summary="x",
            allowed_paths=["proj"],
            denied_paths=["/bin"],
        )
        self.assertEqual(out["status"], "succeeded")
        self.assertEqual(out["attempts"], 1)

    def test_03_two_repairs_success(self):
        applied = {"count": 0}

        def validate():
            return applied["count"] >= 2

        def generate(req: RepairRequest):
            return {"success": True, "plan": f"fix-{req.attempt_number}"}

        def apply(_payload):
            applied["count"] += 1
            return {"success": True}

        adapter = self._make_adapter(validate=validate, generate=generate, apply=apply)
        out = adapter.run(
            mission_name="m3",
            objective="stabilize",
            failure_category="unit-test",
            failure_summary="x",
            allowed_paths=["proj"],
            denied_paths=["/bin"],
        )
        self.assertEqual(out["status"], "succeeded")
        self.assertEqual(out["attempts"], 2)

    def test_04_third_repair_success(self):
        applied = {"count": 0}

        def validate():
            return applied["count"] >= 3

        def generate(req: RepairRequest):
            return {"success": True, "plan": f"fix-{req.attempt_number}"}

        def apply(_payload):
            applied["count"] += 1
            return True

        adapter = self._make_adapter(validate=validate, generate=generate, apply=apply)
        out = adapter.run(
            mission_name="m4",
            objective="stabilize",
            failure_category="unit-test",
            failure_summary="x",
            allowed_paths=["proj"],
            denied_paths=["/bin"],
        )
        self.assertEqual(out["status"], "succeeded")
        self.assertEqual(out["attempts"], 3)

    def test_05_no_fourth_attempt(self):
        # Always fail validation => 3 attempts max
        gen_calls = {"n": 0}

        def validate():
            return False

        def generate(_req: RepairRequest):
            gen_calls["n"] += 1
            return {"success": True, "plan": "x"}

        def apply(_payload):
            return {"success": True}

        adapter = self._make_adapter(validate=validate, generate=generate, apply=apply)
        out = adapter.run(
            mission_name="m5",
            objective="stabilize",
            failure_category="unit-test",
            failure_summary="x",
            allowed_paths=["proj"],
            denied_paths=["/bin"],
        )
        self.assertEqual(out["attempts"], 3)
        self.assertEqual(gen_calls["n"], 3)
        self.assertEqual(out["status"], "exhausted")

    def test_06_exhaustion(self):
        # Generation succeeds, apply succeeds, validation always fails
        def validate():
            return False

        def generate(_req: RepairRequest):
            return {"success": True, "plan": "p"}

        def apply(_payload):
            return True

        adapter = self._make_adapter(validate=validate, generate=generate, apply=apply)
        out = adapter.run(
            mission_name="m6",
            objective="stabilize",
            failure_category="unit-test",
            failure_summary="x",
            allowed_paths=["proj"],
            denied_paths=["/bin"],
        )
        self.assertEqual(out["status"], "exhausted")
        self.assertEqual(len(out["history"]), 3)

    def test_07_exactly_three_generation_calls_on_failures(self):
        calls = {"gen": 0, "app": 0}

        def validate():
            return False

        def generate(_req: RepairRequest):
            calls["gen"] += 1
            return {"success": False}

        def apply(_payload):
            calls["app"] += 1
            return False

        adapter = self._make_adapter(validate=validate, generate=generate, apply=apply)
        out = adapter.run(
            mission_name="m7",
            objective="stabilize",
            failure_category="unit-test",
            failure_summary="x",
            allowed_paths=["proj"],
            denied_paths=["/bin"],
        )
        self.assertEqual(calls["gen"], 3)
        self.assertEqual(calls["app"], 0)
        self.assertEqual(out["status"], "exhausted")

    def _blocked_common(self, reason: str):
        calls = {"gen": 0, "app": 0}

        def validate():
            return False

        def generate(_req: RepairRequest):
            calls["gen"] += 1
            return {"success": True, "plan": "p"}

        def apply(_payload):
            calls["app"] += 1
            return True

        adapter = self._make_adapter(validate=validate, generate=generate, apply=apply)
        out = adapter.run(
            mission_name="mb",
            objective="stabilize",
            failure_category="unit-test",
            failure_summary="x",
            allowed_paths=["a"],
            denied_paths=["d"],
            policy_blocks=[reason],
        )
        self.assertEqual(out["status"], "blocked")
        self.assertIn(reason, out["blocked_reasons"])
        self.assertEqual(calls["gen"], 0)
        self.assertEqual(calls["app"], 0)

    def test_08_protected_core_block(self):
        self._blocked_common("protected-core-access")

    def test_09_canonical_test_block(self):
        self._blocked_common("canonical-recovery-test-access")

    def test_10_unavailable_core_protection_block(self):
        self._blocked_common("unavailable-core-protection")

    def test_11_repository_safety_block(self):
        self._blocked_common("repository-safety-bypass")

    def test_12_security_policy_block(self):
        self._blocked_common("security-policy-bypass")

    def test_13_provider_authentication_block(self):
        self._blocked_common("provider-authentication-intervention")

    def test_14_generation_failure(self):
        def validate():
            return False

        def generate(_req: RepairRequest):
            return {"success": False, "error": "bad plan"}

        def apply(_payload):
            return True

        adapter = self._make_adapter(validate=validate, generate=generate, apply=apply)
        out = adapter.run(
            mission_name="m14",
            objective="stabilize",
            failure_category="unit-test",
            failure_summary="x",
            allowed_paths=["a"],
            denied_paths=["d"],
        )
        # First attempt recorded with generation failure
        self.assertEqual(out["history"][0]["generation"]["success"], False)
        self.assertIn({"stage": "generation", "attempt": 1, "message": "Repair generation failed"}, out["failures"])  # message normalized

    def test_15_generation_exception_sanitized(self):
        secret = "supersecret-token"

        def validate():
            return False

        def generate(_req: RepairRequest):
            raise RuntimeError(f"password: {secret}; Authorization: Bearer BEAR123")

        def apply(_payload):
            return True

        adapter = self._make_adapter(validate=validate, generate=generate, apply=apply)
        out = adapter.run(
            mission_name="m15",
            objective="stabilize",
            failure_category="unit-test",
            failure_summary="x",
            allowed_paths=["a"],
            denied_paths=["d"],
        )
        # Ensure redaction
        failures = " ".join(f["message"] for f in out["failures"] if f["stage"] == "generation")
        self.assertIn("[REDACTED]", failures)
        self.assertNotIn(secret, failures)
        # Bearer canonical form must be present
        self.assertIn("Authorization: Bearer [REDACTED]", failures)

    def test_16_apply_failure(self):
        def validate():
            return False

        def generate(_req: RepairRequest):
            return {"success": True, "plan": "x"}

        def apply(_payload):
            return {"success": False}

        adapter = self._make_adapter(validate=validate, generate=generate, apply=apply)
        out = adapter.run(
            mission_name="m16",
            objective="stabilize",
            failure_category="unit-test",
            failure_summary="x",
            allowed_paths=["a"],
            denied_paths=["d"],
        )
        apps = [r for r in out["history"] if r["apply"]["success"] is False]
        self.assertTrue(len(apps) >= 1)
        failures = [f for f in out["failures"] if f["stage"] == "apply"]
        self.assertTrue(any("Repair application failed" in f["message"] for f in failures))

    def test_17_apply_exception_sanitized(self):
        secret = "abc123XYZ"

        def validate():
            return False

        def generate(_req: RepairRequest):
            return {"success": True, "plan": "p"}

        def apply(_payload):
            raise ValueError(f"api_key={secret}; something else")

        adapter = self._make_adapter(validate=validate, generate=generate, apply=apply)
        out = adapter.run(
            mission_name="m17",
            objective="stabilize",
            failure_category="unit-test",
            failure_summary="x",
            allowed_paths=["a"],
            denied_paths=["d"],
        )
        failures = " ".join(f["message"] for f in out["failures"] if f["stage"] == "apply")
        self.assertIn("[REDACTED]", failures)
        self.assertNotIn(secret, failures)

    def test_18_validation_exception_safely_recorded(self):
        def validate():
            raise RuntimeError("password: should_not_leak")

        def generate(_req: RepairRequest):
            return {"success": False}

        def apply(_payload):
            return True

        adapter = self._make_adapter(validate=validate, generate=generate, apply=apply)
        out = adapter.run(
            mission_name="m18",
            objective="stabilize",
            failure_category="unit-test",
            failure_summary="x",
            allowed_paths=["a"],
            denied_paths=["d"],
        )
        self.assertEqual(out["initial_validation"]["success"], False)
        self.assertIn("[REDACTED]", out["initial_validation"]["error"])

    def test_19_validation_exception_followed_by_later_success(self):
        stage = {"applied": 0}

        def validate():
            if stage["applied"] == 0:
                raise RuntimeError("token=topsecret")
            return True

        def generate(_req: RepairRequest):
            return {"success": True, "plan": "p"}

        def apply(_payload):
            stage["applied"] += 1
            return True

        adapter = self._make_adapter(validate=validate, generate=generate, apply=apply)
        out = adapter.run(
            mission_name="m19",
            objective="stabilize",
            failure_category="unit-test",
            failure_summary="x",
            allowed_paths=["a"],
            denied_paths=["d"],
        )
        self.assertEqual(out["status"], "succeeded")
        # Ensure initial failure recorded and redacted
        self.assertIn("[REDACTED]", out["initial_validation"]["error"])

    def test_20_validation_exception_followed_by_continued_failure(self):
        def validate():
            raise RuntimeError("password='keepme' not")

        def generate(_req: RepairRequest):
            return {"success": True, "plan": "p"}

        def apply(_payload):
            return True

        adapter = self._make_adapter(validate=validate, generate=generate, apply=apply)
        out = adapter.run(
            mission_name="m20",
            objective="stabilize",
            failure_category="unit-test",
            failure_summary="x",
            allowed_paths=["a"],
            denied_paths=["d"],
        )
        self.assertEqual(out["status"], "exhausted")
        # Validate redaction
        all_fail_msgs = " ".join(f["message"] for f in out["failures"] if f["stage"] == "validation")
        self.assertIn("[REDACTED]", all_fail_msgs)
        self.assertNotIn("keepme", all_fail_msgs)

    def test_21_bearer_canonical_redaction(self):
        def validate():
            return False

        def generate(_req: RepairRequest):
            raise RuntimeError("authorization: bearer AbC.DeF")

        def apply(_payload):
            return True

        adapter = self._make_adapter(validate=validate, generate=generate, apply=apply)
        out = adapter.run(
            mission_name="m21",
            objective="stabilize",
            failure_category="unit-test",
            failure_summary="x",
            allowed_paths=["a"],
            denied_paths=["d"],
        )
        failures = " ".join(f["message"] for f in out["failures"] if f["stage"] == "generation")
        self.assertIn("Authorization: Bearer [REDACTED]", failures)

    def test_22_bearer_secret_absence(self):
        secret = "AbC.DeF.GhI"

        def validate():
            return False

        def generate(_req: RepairRequest):
            raise RuntimeError(f"Authorization: Bearer {secret}")

        def apply(_payload):
            return True

        adapter = self._make_adapter(validate=validate, generate=generate, apply=apply)
        out = adapter.run(
            mission_name="m22",
            objective="stabilize",
            failure_category="unit-test",
            failure_summary="x",
            allowed_paths=["a"],
            denied_paths=["d"],
        )
        failures = " ".join(f["message"] for f in out["failures"] if f["stage"] == "generation")
        self.assertNotIn(secret, failures)
        self.assertIn("[REDACTED]", failures)

    def test_23_generic_secret_removal(self):
        secret = "abc123"

        def validate():
            return False

        def generate(_req: RepairRequest):
            raise RuntimeError(f"password=\"{secret}\"")

        def apply(_payload):
            return True

        adapter = self._make_adapter(validate=validate, generate=generate, apply=apply)
        out = adapter.run(
            mission_name="m23",
            objective="stabilize",
            failure_category="unit-test",
            failure_summary="x",
            allowed_paths=["a"],
            denied_paths=["d"],
        )
        failures = " ".join(f["message"] for f in out["failures"] if f["stage"] == "generation")
        self.assertIn("[REDACTED]", failures)
        self.assertNotIn(secret, failures)
        # No requirement to preserve quotes format

    def test_24_allowed_paths_preserved(self):
        seen: List[RepairRequest] = []

        def validate():
            return False

        def generate(req: RepairRequest):
            seen.append(req)
            return {"success": False}

        def apply(_payload):
            return True

        allowed = ["src/app", "."]
        denied = ["/etc", "/root"]

        adapter = self._make_adapter(validate=validate, generate=generate, apply=apply)
        adapter.run(
            mission_name="m24",
            objective="stabilize",
            failure_category="unit-test",
            failure_summary="summary",
            allowed_paths=allowed,
            denied_paths=denied,
        )
        for req in seen:
            self.assertEqual(list(req.allowed_paths), allowed)

    def test_25_denied_paths_preserved(self):
        seen: List[RepairRequest] = []

        def validate():
            return False

        def generate(req: RepairRequest):
            seen.append(req)
            return {"success": False}

        def apply(_payload):
            return True

        allowed = ["src"]
        denied = ["/etc", "/var/secret"]
        adapter = self._make_adapter(validate=validate, generate=generate, apply=apply)
        adapter.run(
            mission_name="m25",
            objective="stabilize",
            failure_category="unit-test",
            failure_summary="summary",
            allowed_paths=allowed,
            denied_paths=denied,
        )
        for req in seen:
            self.assertEqual(list(req.denied_paths), denied)

    def test_26_allowed_paths_not_expanded(self):
        captured: List[RepairRequest] = []

        def validate():
            return False

        def generate(req: RepairRequest):
            captured.append(req)
            return {"success": False}

        def apply(_payload):
            return True

        allowed = [".", "rel/path"]
        denied = ["/do/not/touch"]
        adapter = self._make_adapter(validate=validate, generate=generate, apply=apply)
        adapter.run(
            mission_name="m26",
            objective="stabilize",
            failure_category="unit-test",
            failure_summary="summary",
            allowed_paths=allowed,
            denied_paths=denied,
        )
        for req in captured:
            self.assertEqual(list(req.allowed_paths), allowed)
            # ensure not absolute expansion (heuristic check)
            self.assertTrue(any(p == "." for p in req.allowed_paths))

    def test_27_denied_paths_not_removed(self):
        captured: List[RepairRequest] = []

        def validate():
            return False

        def generate(req: RepairRequest):
            captured.append(req)
            return {"success": False}

        def apply(_payload):
            return True

        allowed = ["src"]
        denied = ["/etc", "/forbidden"]
        adapter = self._make_adapter(validate=validate, generate=generate, apply=apply)
        adapter.run(
            mission_name="m27",
            objective="stabilize",
            failure_category="unit-test",
            failure_summary="summary",
            allowed_paths=allowed,
            denied_paths=denied,
        )
        for req in captured:
            self.assertEqual(list(req.denied_paths), denied)

    def test_28_input_immutability(self):
        seen: List[RepairRequest] = []

        def validate():
            return False

        def generate(req: RepairRequest):
            # Try to mutate internal tuples (should be impossible due to immutability)
            seen.append(req)
            return {"success": False}

        def apply(_payload):
            return True

        allowed = ["a1", "a2"]
        denied = ["d1", "d2"]
        before_allowed_id = id(allowed)
        before_denied_id = id(denied)

        adapter = self._make_adapter(validate=validate, generate=generate, apply=apply)
        adapter.run(
            mission_name="m28",
            objective="stabilize",
            failure_category="unit-test",
            failure_summary="summary",
            allowed_paths=allowed,
            denied_paths=denied,
        )
        self.assertEqual(id(allowed), before_allowed_id)
        self.assertEqual(id(denied), before_denied_id)
        self.assertEqual(allowed, ["a1", "a2"])  # unchanged
        self.assertEqual(denied, ["d1", "d2"])  # unchanged
        # Ensure request values are tuples (immutable)
        for req in seen:
            self.assertIsInstance(req.allowed_paths, tuple)
            self.assertIsInstance(req.denied_paths, tuple)

    def test_29_repair_history_retained(self):
        # Fail generation on first, succeed next and validate fails, then fail apply third
        seq = {"i": 0}

        def validate():
            return False

        def generate(_req: RepairRequest):
            seq["i"] += 1
            if seq["i"] == 1:
                return {"success": False}
            return {"success": True, "plan": f"p{seq['i']}"}

        def apply(_payload):
            # succeed on second attempt only
            return seq["i"] == 2

        adapter = self._make_adapter(validate=validate, generate=generate, apply=apply)
        out = adapter.run(
            mission_name="m29",
            objective="stabilize",
            failure_category="unit-test",
            failure_summary="summary",
            allowed_paths=["a"],
            denied_paths=["d"],
        )
        self.assertEqual(len(out["history"]), 3)
        # First: generation failed
        self.assertEqual(out["history"][0]["generation"]["success"], False)
        # Second: apply succeeded, validation failed
        self.assertEqual(out["history"][1]["apply"]["success"], True)
        self.assertEqual(out["history"][1]["validation"]["success"], False)
        # Third: apply failed
        self.assertEqual(out["history"][2]["apply"]["success"], False)

    def test_30_failure_history_retained(self):
        # Cause failures in each stage
        steps = {"i": 0}

        def validate():
            steps["i"] += 1
            if steps["i"] == 1:
                raise RuntimeError("password: hidden")
            return False

        def generate(_req: RepairRequest):
            return {"success": False}

        def apply(_payload):
            raise ValueError("Authorization: Bearer tok")

        adapter = self._make_adapter(validate=validate, generate=generate, apply=apply)
        out = adapter.run(
            mission_name="m30",
            objective="stabilize",
            failure_category="unit-test",
            failure_summary="summary",
            allowed_paths=["a"],
            denied_paths=["d"],
        )
        stages = [f["stage"] for f in out["failures"]]
        self.assertIn("validation", stages)
        self.assertIn("generation", stages)
        # Apply never called because generation always fails, so apply failure won't exist here

    def test_31_deterministic_equivalent_result(self):
        def validate():
            return False

        def generate(_req: RepairRequest):
            return {"success": True, "plan": "p"}

        def apply(_payload):
            return {"success": False}

        a1 = self._make_adapter(validate=validate, generate=generate, apply=apply)
        a2 = self._make_adapter(validate=validate, generate=generate, apply=apply)

        out1 = a1.run(
            mission_name="m31",
            objective="stabilize",
            failure_category="unit-test",
            failure_summary="sum",
            allowed_paths=["a"],
            denied_paths=["d"],
        )
        out2 = a2.run(
            mission_name="m31",
            objective="stabilize",
            failure_category="unit-test",
            failure_summary="sum",
            allowed_paths=["a"],
            denied_paths=["d"],
        )
        self.assertEqual(out1, out2)

    def test_32_no_privileged_maintenance_output(self):
        buf = io.StringIO()

        def validate():
            return True

        def generate(_req: RepairRequest):
            return {"success": True, "plan": "x"}

        def apply(_payload):
            return {"success": True}

        adapter = self._make_adapter(validate=validate, generate=generate, apply=apply)
        with redirect_stdout(buf):
            _ = adapter.run(
                mission_name="m32",
                objective="stabilize",
                failure_category="unit-test",
                failure_summary="x",
                allowed_paths=["a"],
                denied_paths=["d"],
            )
        self.assertEqual(buf.getvalue(), "")

    def test_33_ast_module_local_import_safety(self):
        # Only inspect mission_adapter.py; ensure prohibited imports absent
        path = "agent/repair/mission_adapter.py"
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
        tree = ast.parse(src, filename=path)

        # Build prohibited module names from string pieces to avoid accidental literal patterns
        procs = ["sub", "process"]
        net1 = ["urlli", "b"]
        net2 = ["sock", "et"]
        net3 = ["http"]
        dv1 = ["para", "miko"]
        dv2 = ["fab", "ric"]
        gitm = ["gi", "t"]
        cloud1 = ["bo", "to", "3"]
        dock = ["doc", "ker"]
        kube = ["kuber", "netes"]
        reqs = ["re", "quests"]
        forb = {
            "".join(procs),
            "".join(net1),
            "".join(net2),
            "".join(net3),
            "".join(dv1),
            "".join(dv2),
            "".join(gitm),
            "".join(cloud1),
            "".join(dock),
            "".join(kube),
            "".join(reqs),
        }

        bad: List[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name.split(".")[0]
                    if name in forb:
                        bad.append(name)
            elif isinstance(node, ast.ImportFrom):
                name = (node.module or "").split(".")[0]
                if name in forb:
                    bad.append(name)
        self.assertEqual(bad, [], msg=f"Prohibited imports present: {bad}")

    def test_34_max_attempts_exactly_three(self):
        calls = {"gen": 0}

        def validate():
            return False

        def generate(_req: RepairRequest):
            calls["gen"] += 1
            return {"success": False}

        def apply(_payload):
            return False

        adapter = self._make_adapter(validate=validate, generate=generate, apply=apply)
        out = adapter.run(
            mission_name="m34",
            objective="stabilize",
            failure_category="unit-test",
            failure_summary="summary",
            allowed_paths=["a"],
            denied_paths=["d"],
        )
        self.assertEqual(calls["gen"], 3)
        self.assertEqual(out["attempts"], 3)
        self.assertEqual(out["status"], "exhausted")


if __name__ == "__main__":
    unittest.main()
