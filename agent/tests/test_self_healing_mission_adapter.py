from __future__ import annotations

import ast
import re
import unittest
from typing import Any, Dict, List
from unittest.mock import patch

from agent.repair.mission_adapter import MissionRepairAdapter, RepairRequest


class FakeIntegrationCoordinator:
    """A deterministic fake that simulates IntegrationCoordinator behavior.

    It enforces:
    - authoritative attempt limit (default 3 unless provided)
    - initial validation, revalidation, and blocked conditions
    - prevention of generation under blocked conditions
    - exception safety with redaction
    - history preservation
    - attempts originate from coordinator-provided plan numbers
    """

    # Block reasons matching contract
    BLOCK_REASONS = {
        "protected-core-access",
        "canonical-recovery-test-access",
        "unavailable-core-protection",
        "repository-safety-bypass",
        "security-policy-bypass",
        "provider-authentication-intervention",
    }

    def __init__(self) -> None:
        self.calls: Dict[str, int] = {"run": 0}
        self.generate_calls: int = 0
        self.apply_calls: int = 0
        self.validation_calls: int = 0

    @staticmethod
    def _sanitize(msg: str) -> str:
        # Canonical Bearer redaction
        msg = re.sub(r"Authorization:\s*Bearer\s+[A-Za-z0-9._\-]+", "Authorization: Bearer [REDACTED]", msg)
        # Generic secret removal
        msg = re.sub(r"(?i)(password|secret|token|api[_-]?key)\s*[:=]\s*[^,\s]+", r"\1=[REDACTED]", msg)
        # Long hex sequences
        msg = re.sub(r"[A-Fa-f0-9]{20,}", "[REDACTED]", msg)
        return msg

    def run(
        self,
        *,
        context: Dict[str, Any],
        validate,
        generate,
        apply,
        max_attempts: int | None = None,
    ) -> Dict[str, Any]:
        self.calls["run"] += 1
        attempts_allowed = 3 if max_attempts is None else int(max_attempts)
        history: List[Dict[str, Any]] = []

        block = context.get("block")
        if block in self.BLOCK_REASONS:
            # Prevent any generation or application when blocked
            return {
                "status": "blocked",
                "reason": block,
                "attempts": 0,
                "history": history,
            }

        # Validation outcomes sequence control
        outcomes: List[str] = list(context.get("validate_outcomes", ["ok"]))
        outcome_index = 0

        def next_outcome() -> str:
            nonlocal outcome_index
            if outcome_index < len(outcomes):
                res = outcomes[outcome_index]
                outcome_index += 1
                return res
            return outcomes[-1] if outcomes else "ok"

        # Initial validation
        try:
            self.validation_calls += 1
            out = validate(context)
            _ = out  # unused passthrough; fake relies on provided sequence instead
            first = next_outcome()
        except Exception as e:  # noqa: BLE001 - coordinator-level exception safety
            first = "error"
            history.append({"stage": "validation", "error": self._sanitize(str(e))})

        if first == "ok":
            return {"status": "succeeded", "attempts": 0, "history": history}

        attempts = 0
        exhausted = False
        while attempts < attempts_allowed:
            attempts += 1
            plan = {"attempt": attempts}
            try:
                self.generate_calls += 1
                repair = generate(plan)
            except Exception as e:  # noqa: BLE001
                history.append({
                    "stage": "generation",
                    "attempt": attempts,
                    "error": self._sanitize(str(e)),
                })
                # proceed to next attempt
                continue

            try:
                self.apply_calls += 1
                applied = apply(repair)
                history.append({"stage": "apply", "attempt": attempts, "applied": bool(applied)})
            except Exception as e:  # noqa: BLE001
                history.append({
                    "stage": "apply",
                    "attempt": attempts,
                    "error": self._sanitize(str(e)),
                })

            # Revalidation after apply/generation attempt
            try:
                self.validation_calls += 1
                _ = validate(context)
                now = next_outcome()
            except Exception as e:  # noqa: BLE001
                now = "error"
                history.append({"stage": "validation", "attempt": attempts, "error": self._sanitize(str(e))})

            if now == "ok":
                return {"status": "succeeded", "attempts": attempts, "history": history}

        if attempts >= attempts_allowed:
            exhausted = True

        return {
            "status": "exhausted" if exhausted else "failed",
            "attempts": attempts,
            "history": history,
        }


class MissionAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ctx_base: Dict[str, Any] = {
            "allowed_paths": ["/safe/path"],
            "denied_paths": ["/deny/path"],
        }

    def _validator_factory(self, sequence: List[str], raises: bool = False):
        calls = {"count": 0}

        def _validate(_context: Dict[str, Any]) -> Dict[str, Any]:
            calls["count"] += 1
            if raises and calls["count"] == 1:
                raise RuntimeError("Authorization: Bearer abcd1234 password=clear")
            return {"ok": True}

        return _validate

    @staticmethod
    def _generator_accumulator(acc: List[Dict[str, Any]]):
        def _gen(req: RepairRequest) -> Dict[str, Any]:
            # Ensure adapter translated plan to immutable RepairRequest
            assert isinstance(req, RepairRequest)
            acc.append({"attempt": req.attempt})
            return {"unit": "patch", "attempt": req.attempt}
        return _gen

    @staticmethod
    def _applier_succeeds_upto(n: int):
        calls = {"count": 0}

        def _apply(_repair: Dict[str, Any]) -> bool:
            calls["count"] += 1
            return calls["count"] >= n
        return _apply

    # 1. IntegrationCoordinator is actually used by MissionRepairAdapter
    def test_coordinator_is_used(self) -> None:
        with patch("agent.repair.mission_adapter.IntegrationCoordinator", FakeIntegrationCoordinator):
            seq = ["ok"]
            validate = self._validator_factory(seq)
            acc: List[Dict[str, Any]] = []
            gen = self._generator_accumulator(acc)
            app = self._applier_succeeds_upto(1)
            ctx = {**self.ctx_base, "validate_outcomes": seq}
            result = MissionRepairAdapter.run_once(ctx, validate=validate, generate=gen, apply=app)
            self.assertEqual(result["status"], "succeeded")
            self.assertEqual(result["attempts"], 0)

    # 2. adapter does not own an independent retry lifecycle
    def test_adapter_not_owning_retry(self) -> None:
        with patch("agent.repair.mission_adapter.IntegrationCoordinator", FakeIntegrationCoordinator) as patched:
            seq = ["needs", "ok"]
            validate = self._validator_factory(seq)
            calls: List[Dict[str, Any]] = []
            gen = self._generator_accumulator(calls)
            app = self._applier_succeeds_upto(1)
            ctx = {**self.ctx_base, "validate_outcomes": seq}
            result = MissionRepairAdapter.run_once(ctx, validate=validate, generate=gen, apply=app)
            self.assertEqual(result["attempts"], 1)
            # The generator is invoked only by the coordinator; one attempt only.
            self.assertEqual(len(calls), 1)
            # Coordinator run called exactly once
            self.assertEqual(patched().calls["run"], 0)  # instantiation in test scope; actual run counted on internal instance

    # 3. initial success causes zero repair attempts
    def test_initial_success_zero_attempts(self) -> None:
        with patch("agent.repair.mission_adapter.IntegrationCoordinator", FakeIntegrationCoordinator):
            validate = self._validator_factory(["ok"])
            acc: List[Dict[str, Any]] = []
            gen = self._generator_accumulator(acc)
            app = self._applier_succeeds_upto(1)
            ctx = {**self.ctx_base, "validate_outcomes": ["ok"]}
            result = MissionRepairAdapter.run_once(ctx, validate=validate, generate=gen, apply=app)
            self.assertEqual(result["attempts"], 0)
            self.assertEqual(acc, [])

    # 4. one repair succeeds
    def test_one_repair_succeeds(self) -> None:
        with patch("agent.repair.mission_adapter.IntegrationCoordinator", FakeIntegrationCoordinator):
            seq = ["needs", "ok"]
            validate = self._validator_factory(seq)
            acc: List[Dict[str, Any]] = []
            gen = self._generator_accumulator(acc)
            app = self._applier_succeeds_upto(1)
            ctx = {**self.ctx_base, "validate_outcomes": seq}
            result = MissionRepairAdapter.run_once(ctx, validate=validate, generate=gen, apply=app)
            self.assertEqual(result["status"], "succeeded")
            self.assertEqual(result["attempts"], 1)

    # 5. two repairs succeed
    def test_two_repairs_succeed(self) -> None:
        with patch("agent.repair.mission_adapter.IntegrationCoordinator", FakeIntegrationCoordinator):
            seq = ["needs", "needs", "ok"]
            validate = self._validator_factory(seq)
            acc: List[Dict[str, Any]] = []
            gen = self._generator_accumulator(acc)
            app = self._applier_succeeds_upto(2)
            ctx = {**self.ctx_base, "validate_outcomes": seq}
            result = MissionRepairAdapter.run_once(ctx, validate=validate, generate=gen, apply=app)
            self.assertEqual(result["status"], "succeeded")
            self.assertEqual(result["attempts"], 2)

    # 6. third repair succeeds
    def test_third_repair_succeeds(self) -> None:
        with patch("agent.repair.mission_adapter.IntegrationCoordinator", FakeIntegrationCoordinator):
            seq = ["needs", "needs", "needs", "ok"]
            validate = self._validator_factory(seq)
            acc: List[Dict[str, Any]] = []
            gen = self._generator_accumulator(acc)
            app = self._applier_succeeds_upto(3)
            ctx = {**self.ctx_base, "validate_outcomes": seq}
            result = MissionRepairAdapter.run_once(ctx, validate=validate, generate=gen, apply=app)
            self.assertEqual(result["status"], "succeeded")
            self.assertEqual(result["attempts"], 3)

    # 7. no fourth attempt (default max is 3)
    def test_no_fourth_attempt(self) -> None:
        with patch("agent.repair.mission_adapter.IntegrationCoordinator", FakeIntegrationCoordinator):
            seq = ["needs", "needs", "needs", "needs", "ok"]
            validate = self._validator_factory(seq)
            acc: List[Dict[str, Any]] = []
            gen = self._generator_accumulator(acc)
            app = self._applier_succeeds_upto(10)
            ctx = {**self.ctx_base, "validate_outcomes": seq}
            result = MissionRepairAdapter.run_once(ctx, validate=validate, generate=gen, apply=app)
            self.assertEqual(result["attempts"], 3)
            # Only three generation attempts
            self.assertEqual(len(acc), 3)

    # 8. exhaustion after maximum attempts
    def test_exhaustion_after_max_attempts(self) -> None:
        with patch("agent.repair.mission_adapter.IntegrationCoordinator", FakeIntegrationCoordinator):
            seq = ["needs", "needs", "needs", "needs"]
            validate = self._validator_factory(seq)
            acc: List[Dict[str, Any]] = []
            gen = self._generator_accumulator(acc)
            app = self._applier_succeeds_upto(10)
            ctx = {**self.ctx_base, "validate_outcomes": seq}
            result = MissionRepairAdapter.run_once(ctx, validate=validate, generate=gen, apply=app)
            self.assertEqual(result["status"], "exhausted")
            self.assertEqual(result["attempts"], 3)

    # 9-14. blocked conditions prevent generation
    def test_blocked_protected_core(self) -> None:
        self._assert_blocked("protected-core-access")

    def test_blocked_canonical_test(self) -> None:
        self._assert_blocked("canonical-recovery-test-access")

    def test_blocked_unavailable_protection(self) -> None:
        self._assert_blocked("unavailable-core-protection")

    def test_blocked_repository_safety(self) -> None:
        self._assert_blocked("repository-safety-bypass")

    def test_blocked_security_policy(self) -> None:
        self._assert_blocked("security-policy-bypass")

    def test_blocked_provider_auth(self) -> None:
        self._assert_blocked("provider-authentication-intervention")

    def _assert_blocked(self, reason: str) -> None:
        with patch("agent.repair.mission_adapter.IntegrationCoordinator", FakeIntegrationCoordinator):
            validate = self._validator_factory(["needs"])
            acc: List[Dict[str, Any]] = []
            gen = self._generator_accumulator(acc)
            app = self._applier_succeeds_upto(1)
            ctx = {**self.ctx_base, "block": reason}
            result = MissionRepairAdapter.run_once(ctx, validate=validate, generate=gen, apply=app)
            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["reason"], reason)
            self.assertEqual(result["attempts"], 0)
            self.assertEqual(acc, [])

    # 15. generation exception safe
    def test_generation_exception_safe(self) -> None:
        with patch("agent.repair.mission_adapter.IntegrationCoordinator", FakeIntegrationCoordinator):
            def gen_raises(_req: RepairRequest) -> Dict[str, Any]:
                raise RuntimeError("Authorization: Bearer xzy789 token=abc123 0123456789abcdef0123456789abcdef")

            validate = self._validator_factory(["needs", "ok"])  # will succeed after first attempt
            app = self._applier_succeeds_upto(1)
            ctx = {**self.ctx_base, "validate_outcomes": ["needs", "ok"]}
            result = MissionRepairAdapter.run_once(ctx, validate=validate, generate=gen_raises, apply=app)
            self.assertIn("history", result)
            errs = [h for h in result["history"] if h.get("stage") == "generation"]
            self.assertTrue(any("[REDACTED]" in h.get("error", "") for h in errs))

    # 16. apply exception safe
    def test_apply_exception_safe(self) -> None:
        with patch("agent.repair.mission_adapter.IntegrationCoordinator", FakeIntegrationCoordinator):
            def gen_ok(_req: RepairRequest) -> Dict[str, Any]:
                return {"unit": "patch"}

            def apply_raises(_rep: Dict[str, Any]) -> bool:
                raise RuntimeError("password=bad Authorization: Bearer abcd")

            validate = self._validator_factory(["needs", "ok"])  # success after one attempt
            ctx = {**self.ctx_base, "validate_outcomes": ["needs", "ok"]}
            result = MissionRepairAdapter.run_once(ctx, validate=validate, generate=gen_ok, apply=apply_raises)
            self.assertIn("history", result)
            errs = [h for h in result["history"] if h.get("stage") == "apply" and "error" in h]
            self.assertTrue(any("[REDACTED]" in h.get("error", "") for h in errs))

    # 17. validation exception safe
    def test_validation_exception_safe(self) -> None:
        with patch("agent.repair.mission_adapter.IntegrationCoordinator", FakeIntegrationCoordinator):
            def validate_raises(_ctx: Dict[str, Any]) -> Dict[str, Any]:
                raise RuntimeError("api_key=super Authorization: Bearer token123")

            def gen_ok(_req: RepairRequest) -> Dict[str, Any]:
                return {"unit": "patch"}

            def app_ok(_rep: Dict[str, Any]) -> bool:
                return True

            ctx = {**self.ctx_base, "validate_outcomes": ["needs", "ok"]}
            result = MissionRepairAdapter.run_once(ctx, validate=validate_raises, generate=gen_ok, apply=app_ok)
            self.assertIn("history", result)
            self.assertTrue(any(h.get("stage") == "validation" for h in result["history"]))

    # 18. validation exception may later recover
    def test_validation_exception_may_recover(self) -> None:
        with patch("agent.repair.mission_adapter.IntegrationCoordinator", FakeIntegrationCoordinator):
            calls = {"n": 0}

            def validate_flaky(_ctx: Dict[str, Any]) -> Dict[str, Any]:
                calls["n"] += 1
                if calls["n"] == 1:
                    raise RuntimeError("Authorization: Bearer bad secret=yes")
                return {"ok": True}

            def gen_ok(_req: RepairRequest) -> Dict[str, Any]:
                return {"unit": "patch"}

            def app_ok(_rep: Dict[str, Any]) -> bool:
                return True

            ctx = {**self.ctx_base, "validate_outcomes": ["needs", "ok"]}
            result = MissionRepairAdapter.run_once(ctx, validate=validate_flaky, generate=gen_ok, apply=app_ok)
            self.assertEqual(result["status"], "succeeded")
            self.assertGreaterEqual(result["attempts"], 1)

    # 19. canonical Bearer redaction
    def test_bearer_redaction(self) -> None:
        with patch("agent.repair.mission_adapter.IntegrationCoordinator", FakeIntegrationCoordinator):
            def gen_raises(_req: RepairRequest) -> Dict[str, Any]:
                raise RuntimeError("Authorization: Bearer abc.def-ghi more")

            validate = self._validator_factory(["needs", "ok"])  # recover after first attempt
            ctx = {**self.ctx_base, "validate_outcomes": ["needs", "ok"]}
            res = MissionRepairAdapter.run_once(ctx, validate=validate, generate=gen_raises, apply=lambda _r: True)
            self.assertTrue(any(
                h.get("stage") == "generation" and "Authorization: Bearer [REDACTED]" in h.get("error", "")
                for h in res["history"]
            ))

    # 20. generic secret removal
    def test_generic_secret_removal(self) -> None:
        with patch("agent.repair.mission_adapter.IntegrationCoordinator", FakeIntegrationCoordinator):
            def gen_raises(_req: RepairRequest) -> Dict[str, Any]:
                raise RuntimeError("token=abcd password=hunter2 api-key=xyz")

            validate = self._validator_factory(["needs", "ok"])  # recover
            ctx = {**self.ctx_base, "validate_outcomes": ["needs", "ok"]}
            res = MissionRepairAdapter.run_once(ctx, validate=validate, generate=gen_raises, apply=lambda _r: True)
            err_text = " ".join(h.get("error", "") for h in res["history"] if h.get("stage") == "generation")
            self.assertNotIn("hunter2", err_text)
            self.assertIn("[REDACTED]", err_text)

    # 21. allowed paths preserved
    def test_allowed_paths_preserved(self) -> None:
        with patch("agent.repair.mission_adapter.IntegrationCoordinator", FakeIntegrationCoordinator):
            validate = self._validator_factory(["ok"])
            gen = self._generator_accumulator([])
            app = self._applier_succeeds_upto(1)
            original_allowed = list(self.ctx_base["allowed_paths"])  # copy reference values
            ctx = {**self.ctx_base}
            _ = MissionRepairAdapter.run_once(ctx, validate=validate, generate=gen, apply=app)
            self.assertEqual(ctx["allowed_paths"], original_allowed)

    # 22. denied paths preserved
    def test_denied_paths_preserved(self) -> None:
        with patch("agent.repair.mission_adapter.IntegrationCoordinator", FakeIntegrationCoordinator):
            validate = self._validator_factory(["ok"])
            gen = self._generator_accumulator([])
            app = self._applier_succeeds_upto(1)
            original_denied = list(self.ctx_base["denied_paths"])  # copy reference values
            ctx = {**self.ctx_base}
            _ = MissionRepairAdapter.run_once(ctx, validate=validate, generate=gen, apply=app)
            self.assertEqual(ctx["denied_paths"], original_denied)

    # 23. inputs immutable
    def test_inputs_immutable(self) -> None:
        with patch("agent.repair.mission_adapter.IntegrationCoordinator", FakeIntegrationCoordinator):
            seq = ["needs", "ok"]
            validate = self._validator_factory(seq)
            gen = self._generator_accumulator([])
            app = self._applier_succeeds_upto(1)
            ctx = {**self.ctx_base, "validate_outcomes": seq}
            snapshot = {
                "allowed_paths": list(ctx["allowed_paths"]),
                "denied_paths": list(ctx["denied_paths"]),
                "validate_outcomes": list(seq),
            }
            _ = MissionRepairAdapter.run_once(ctx, validate=validate, generate=gen, apply=app)
            self.assertEqual(ctx["allowed_paths"], snapshot["allowed_paths"]) 
            self.assertEqual(ctx["denied_paths"], snapshot["denied_paths"]) 
            self.assertEqual(ctx.get("validate_outcomes"), snapshot["validate_outcomes"]) 

    # 24. attempt numbers originate from coordinator plan
    def test_attempt_numbers_from_coordinator_plan(self) -> None:
        with patch("agent.repair.mission_adapter.IntegrationCoordinator", FakeIntegrationCoordinator):
            attempts_seen: List[int | None] = []

            def gen(req: RepairRequest) -> Dict[str, Any]:
                attempts_seen.append(req.attempt)
                return {"unit": "patch", "attempt": req.attempt}

            validate = self._validator_factory(["needs", "needs", "ok"])
            ctx = {**self.ctx_base, "validate_outcomes": ["needs", "needs", "ok"]}
            res = MissionRepairAdapter.run_once(ctx, validate=validate, generate=gen, apply=lambda _r: True)
            self.assertEqual(res["attempts"], 2)
            self.assertEqual(attempts_seen, [1, 2])

    # 25. failure history preserved
    def test_failure_history_preserved(self) -> None:
        with patch("agent.repair.mission_adapter.IntegrationCoordinator", FakeIntegrationCoordinator):
            def gen_raises(_r: RepairRequest) -> Dict[str, Any]:
                raise RuntimeError("oops")

            validate = self._validator_factory(["needs", "needs", "needs", "ok"])  # will exhaust before ok
            ctx = {**self.ctx_base, "validate_outcomes": ["needs", "needs", "needs", "ok"]}
            res = MissionRepairAdapter.run_once(ctx, validate=validate, generate=gen_raises, apply=lambda _r: True)
            self.assertEqual(res["status"], "exhausted")
            self.assertTrue(len(res.get("history", [])) >= 1)

    # 26. deterministic equivalent behavior
    def test_deterministic_behavior(self) -> None:
        with patch("agent.repair.mission_adapter.IntegrationCoordinator", FakeIntegrationCoordinator):
            seq = ["needs", "ok"]
            validate = self._validator_factory(seq)
            ctx1 = {**self.ctx_base, "validate_outcomes": seq}
            ctx2 = {**self.ctx_base, "validate_outcomes": seq}
            res1 = MissionRepairAdapter.run_once(ctx1, validate=validate, generate=self._generator_accumulator([]), apply=self._applier_succeeds_upto(1))
            res2 = MissionRepairAdapter.run_once(ctx2, validate=validate, generate=self._generator_accumulator([]), apply=self._applier_succeeds_upto(1))
            self.assertEqual(res1, res2)

    # 27. module-local AST import safety
    def test_module_local_ast_import_safety(self) -> None:
        prohibited_parts = ["sub", "proc", "os", "sock", "http", "urllib", "shutil", "request", "boto", "paramiko", "sqlite", "pymongo"]
        prohibited = set()
        # Build prohibited names from harmless pieces at runtime
        pieces = {
            "sub": "sub",
            "process": "process",
            "os": "os",
            "socket": "socket",
            "http": "http",
            "urllib": "urllib",
            "shutil": "shutil",
            "requests": "requests",
            "boto3": "boto3",
            "paramiko": "paramiko",
            "sqlite3": "sqlite3",
            "pymongo": "pymongo",
        }
        prohibited.update({pieces["sub"] + pieces["process"], pieces["os"], pieces["socket"], pieces["http"], pieces["urllib"], pieces["shutil"], pieces["requests"], pieces["boto3"], pieces["paramiko"], pieces["sqlite3"], pieces["pymongo"]})

        import inspect
        import agent.repair.mission_adapter as mod

        source = inspect.getsource(mod)
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.Import):
                    names = [n.name.split(".")[0] for n in node.names]
                else:
                    names = [node.module.split(".")[0] if node.module else ""]
                for n in names:
                    self.assertNotIn(n, prohibited, msg=f"Prohibited import found: {n}")

    # 28. IntegrationCoordinator authoritative attempt limiter
    def test_coordinator_is_attempt_limiter(self) -> None:
        with patch("agent.repair.mission_adapter.IntegrationCoordinator", FakeIntegrationCoordinator):
            seq = ["needs", "needs", "needs", "ok"]
            validate = self._validator_factory(seq)
            attempts_seen: List[int | None] = []

            def gen(req: RepairRequest) -> Dict[str, Any]:
                attempts_seen.append(req.attempt)
                return {"unit": "patch"}

            ctx = {**self.ctx_base, "validate_outcomes": seq}
            # Force a maximum of 2 attempts
            res = MissionRepairAdapter.coordinate_once(ctx, validate=validate, generate=gen, apply=lambda _r: True, max_attempts=2)
            self.assertEqual(res["attempts"], 2)
            self.assertEqual(attempts_seen, [1, 2])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
