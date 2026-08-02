from __future__ import annotations

import json
import os
import stat
import sys
import types
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Utilities to install fake ai modules compatible with both import paths

def install_fake_module(module_name: str, obj: Any) -> None:
    sys.modules[module_name] = obj


def ensure_ai_package_roots() -> None:
    # Create namespace packages if needed
    if "ai" not in sys.modules:
        ai_pkg = types.ModuleType("ai")
        ai_pkg.__path__ = []  # type: ignore[attr-defined]
        sys.modules["ai"] = ai_pkg
    if "agent" not in sys.modules:
        agent_pkg = types.ModuleType("agent")
        agent_pkg.__path__ = []  # type: ignore[attr-defined]
        sys.modules["agent"] = agent_pkg
    if "agent.ai" not in sys.modules:
        agent_ai_pkg = types.ModuleType("agent.ai")
        agent_ai_pkg.__path__ = []  # type: ignore[attr-defined]
        sys.modules["agent.ai"] = agent_ai_pkg


class FakePromptBuilder:
    def __init__(self) -> None:
        self.scans: List[Path] = []
        self.prompts: List[str] = []
        self.spec: Dict[str, Any] = {
            "mission_text": "Do the thing",
            "execution_plan": "1) plan A 2) plan B",
            "allowlist": [],
        }

    def prepare(self, mission_name: str, repo_root: Path) -> Dict[str, Any]:
        # Return fixed spec by default
        return dict(self.spec)

    def scan_repository(self, repo_root: Path) -> Dict[str, Any]:
        self.scans.append(repo_root)
        return {"files": []}

    def build_prompt(self, base: Dict[str, Any]) -> str:
        # Capture prompt used
        s = json.dumps(base, sort_keys=True)
        self.prompts.append(s)
        return s


class FakeCodeGenerator:
    def __init__(self) -> None:
        self.prompts: List[str] = []
        self.responses: List[Any] = []
        self.raise_on_generate: Optional[BaseException] = None

    def queue_responses(self, *responses: Any) -> None:
        self.responses.extend(list(responses))

    def generate(self, prompt: str) -> Any:
        self.prompts.append(prompt)
        if self.raise_on_generate:
            raise self.raise_on_generate
        if not self.responses:
            raise RuntimeError("No queued responses for generator")
        return self.responses.pop(0)


class FakeValidationResult:
    def __init__(self, passed: bool, category: Optional[str] = None, failed_tests: Optional[List[str]] = None, error_summary: Optional[str] = None) -> None:
        self.passed = passed
        self.category = category
        self.failed_tests = failed_tests or []
        self.error_summary = error_summary or ""


class FakeValidationEngine:
    def __init__(self) -> None:
        self.results: List[Any] = []
        self.calls: List[Tuple[Path, List[Path]]] = []

    def queue_results(self, *results: Any) -> None:
        self.results.extend(list(results))

    def validate(self, repo_root: Path, changed_paths: List[Path]) -> Any:
        self.calls.append((repo_root, changed_paths))
        if not self.results:
            return FakeValidationResult(True)
        return self.results.pop(0)


class FakePatchEngine:
    def __init__(self) -> None:
        self.commits: List[Tuple[List[str], str]] = []
        self.pushed: int = 0
        self.branches: List[str] = []

    def stage_and_commit(self, paths: List[str], message: str) -> None:
        self.commits.append((paths, message))

    def push(self) -> None:
        self.pushed += 1

    def ensure_branch(self, branch_name: str) -> None:
        self.branches.append(branch_name)


class FakeReviewEngine:
    pass


class FakeRetryDecision:
    def __init__(self, retryable: bool, blocked: bool, reason: str = "", feedback: str = "") -> None:
        self.retryable = retryable
        self.blocked = blocked
        self.reason = reason
        self.feedback = feedback


class FakeRetryEngine:
    def __init__(self) -> None:
        self.contexts: List[Any] = []
        self.decisions: List[FakeRetryDecision] = []

    def decide(self, ctx: Any) -> Any:
        self.contexts.append(ctx)
        if self.decisions:
            return self.decisions.pop(0)
        # Default mirrors category policy
        cat = getattr(ctx, "category", "")
        retryable = cat in {
            "invalid-ai-json",
            "missing-deliverables",
            "python-syntax-error",
            "compilation-failure",
            "validation-failure",
            "unittest-failures",
            "unittest-errors",
        }
        blocked = cat in {
            "security-policy",
            "forbidden-content",
            "unsafe-path",
            "secret-exposure",
            "dirty-repository",
            "git-integrity",
            "provider-authentication",
            "provider-authorization",
            "provider-billing",
            "provider-unavailable",
            "invalid-configuration",
        }
        return FakeRetryDecision(retryable=retryable, blocked=blocked, reason=cat, feedback=f"Fix: {cat}")

    def build_feedback(self, ctx: Any) -> str:
        return f"Please resolve: {getattr(ctx, 'category', 'unknown')}"


def install_fakes() -> Dict[str, Any]:
    ensure_ai_package_roots()
    modules = {}
    # ai modules
    modules["ai.prompt_builder"] = types.ModuleType("ai.prompt_builder")
    modules["ai.prompt_builder"].PromptBuilder = FakePromptBuilder  # type: ignore[attr-defined]
    modules["ai.code_generator"] = types.ModuleType("ai.code_generator")
    modules["ai.code_generator"].CodeGenerator = FakeCodeGenerator  # type: ignore[attr-defined]
    modules["ai.validation_engine"] = types.ModuleType("ai.validation_engine")
    modules["ai.validation_engine"].ValidationEngine = FakeValidationEngine  # type: ignore[attr-defined]
    modules["ai.patch_engine"] = types.ModuleType("ai.patch_engine")
    modules["ai.patch_engine"].PatchEngine = FakePatchEngine  # type: ignore[attr-defined]
    modules["ai.review_engine"] = types.ModuleType("ai.review_engine")
    modules["ai.review_engine"].ReviewEngine = FakeReviewEngine  # type: ignore[attr-defined]
    modules["ai.retry_engine"] = types.ModuleType("ai.retry_engine")
    modules["ai.retry_engine"].RetryEngine = FakeRetryEngine  # type: ignore[attr-defined]

    # agent.ai mirrors
    for name, mod in list(modules.items()):
        agent_name = name.replace("ai.", "agent.ai.")
        sys.modules[name] = mod
        sys.modules[agent_name] = mod
    return modules


class MissionRunnerRetryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.modules = install_fakes()
        # Import mission runner after fakes installed
        from agent.ai import mission_runner as mr  # type: ignore
        self.mr = mr

        # Create temp workspace
        self.tmp = Path(os.getcwd()) / "tmp_mission_runner_tests"
        if self.tmp.exists():
            for root, dirs, files in os.walk(self.tmp, topdown=False):
                for f in files:
                    Path(root, f).unlink()
                for d in dirs:
                    Path(root, d).rmdir()
            self.tmp.rmdir()
        self.tmp.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        # Cleanup temp dir
        if self.tmp.exists():
            for root, dirs, files in os.walk(self.tmp, topdown=False):
                for f in files:
                    Path(root, f).unlink()
                for d in dirs:
                    Path(root, d).rmdir()
            self.tmp.rmdir()

    def _new_runner(self, max_attempts: int = 3) -> Any:
        return self.mr.MissionRunner(repo_root=self.tmp, max_attempts=max_attempts)

    def test_default_max_attempts_is_3(self) -> None:
        r = self._new_runner()
        self.assertEqual(r.max_attempts, 3)

    def test_cli_parsing_and_limits(self) -> None:
        from agent.ai import mission_runner as mr  # type: ignore
        with self.assertRaises(SystemExit):
            mr._parse_args(["mission", "--max-attempts", "0"])
        with self.assertRaises(SystemExit):
            mr._parse_args(["mission", "--max-attempts", "6"])
        ns = mr._parse_args(["mission", "--max-attempts", "5"])  # edge accepted
        self.assertEqual(ns.max_attempts, 5)

    def test_success_on_first_attempt(self) -> None:
        r = self._new_runner()
        # Configure allowlist
        pb: FakePromptBuilder = r.prompt_builder  # type: ignore[assignment]
        allow_path = str(self.tmp / "out.py")
        pb.spec["allowlist"] = [allow_path]

        cg: FakeCodeGenerator = r.code_generator  # type: ignore[assignment]
        payload = {"files": [{"path": allow_path, "content": "print('ok')\n"}]}
        cg.queue_responses(json.dumps(payload))

        ve: FakeValidationEngine = r.validation_engine  # type: ignore[assignment]
        ve.queue_results(FakeValidationResult(True))

        pe: FakePatchEngine = r.patch_engine  # type: ignore[assignment]

        report = r.run("mission-1")
        self.assertTrue(report.success)
        self.assertEqual(report.attempts, 1)
        # Commit happened
        self.assertEqual(len(pe.commits), 1)
        self.assertTrue((self.tmp / "out.py").exists())

    def test_invalid_json_then_success(self) -> None:
        r = self._new_runner()
        pb: FakePromptBuilder = r.prompt_builder  # type: ignore
        allow_path = str(self.tmp / "f1.txt")
        pb.spec["allowlist"] = [allow_path]

        cg: FakeCodeGenerator = r.code_generator  # type: ignore
        # First invalid JSON, then valid
        cg.queue_responses("not-json", json.dumps({"files": [{"path": allow_path, "content": "data"}]}))
        ve: FakeValidationEngine = r.validation_engine  # type: ignore
        ve.queue_results(FakeValidationResult(True))

        re: FakeRetryEngine = r.retry_engine  # type: ignore

        report = r.run("mission-json-retry")
        self.assertTrue(report.success)
        self.assertEqual(report.attempts, 2)
        # Prompt for second attempt must include required items
        self.assertGreaterEqual(len(pb.prompts), 2)
        retry_prompt = pb.prompts[-1]
        self.assertIn("mission_text", retry_prompt)
        self.assertIn("execution_plan", retry_prompt)
        self.assertIn("deliverable_allowlist", retry_prompt)
        self.assertIn("previous_failure_feedback", retry_prompt)

    def test_compilation_failure_then_success(self) -> None:
        r = self._new_runner()
        pb: FakePromptBuilder = r.prompt_builder  # type: ignore
        path1 = str(self.tmp / "c1.py")
        pb.spec["allowlist"] = [path1]

        cg: FakeCodeGenerator = r.code_generator  # type: ignore
        cg.queue_responses(json.dumps({"files": [{"path": path1, "content": "bad code"}]}),
                           json.dumps({"files": [{"path": path1, "content": "print('fixed')\n"}]}))

        ve: FakeValidationEngine = r.validation_engine  # type: ignore
        ve.queue_results(FakeValidationResult(False, category="compilation-failure", error_summary="E: syntax error"),
                         FakeValidationResult(True))

        report = r.run("mission-compile-retry")
        self.assertTrue(report.success)
        self.assertEqual(report.attempts, 2)

    def test_unittest_failure_then_success(self) -> None:
        r = self._new_runner()
        pb: FakePromptBuilder = r.prompt_builder  # type: ignore
        path1 = str(self.tmp / "mod.py")
        pb.spec["allowlist"] = [path1]

        cg: FakeCodeGenerator = r.code_generator  # type: ignore
        cg.queue_responses(json.dumps({"files": [{"path": path1, "content": "def f():\n return 0\n"}]}),
                           json.dumps({"files": [{"path": path1, "content": "def f():\n return 1\n"}]}))

        ve: FakeValidationEngine = r.validation_engine  # type: ignore
        ve.queue_results(FakeValidationResult(False, category="unittest-failures", failed_tests=["tests.test_a::test_x"], error_summary="AssertionError: 0 != 1"),
                         FakeValidationResult(True))

        report = r.run("mission-tests-retry")
        self.assertTrue(report.success)
        self.assertEqual(report.attempts, 2)

    def test_max_attempts_exhaustion(self) -> None:
        r = self._new_runner(max_attempts=3)
        pb: FakePromptBuilder = r.prompt_builder  # type: ignore
        path1 = str(self.tmp / "file.txt")
        pb.spec["allowlist"] = [path1]

        cg: FakeCodeGenerator = r.code_generator  # type: ignore
        bad_payload = json.dumps({"files": [{"path": path1, "content": "oops"}]})
        cg.queue_responses(bad_payload, bad_payload, bad_payload)

        ve: FakeValidationEngine = r.validation_engine  # type: ignore
        ve.queue_results(FakeValidationResult(False, category="validation-failure", error_summary="deterministic failure"),
                         FakeValidationResult(False, category="validation-failure", error_summary="deterministic failure"),
                         FakeValidationResult(False, category="validation-failure", error_summary="deterministic failure"))

        report = r.run("mission-exhaust")
        self.assertFalse(report.success)
        self.assertEqual(report.attempts, 3)
        self.assertEqual(report.final_category, "validation-failure")

    def test_non_retryable_security_stops_immediately(self) -> None:
        r = self._new_runner(max_attempts=3)
        pb: FakePromptBuilder = r.prompt_builder  # type: ignore
        path1 = str(self.tmp / "sec.txt")
        pb.spec["allowlist"] = [path1]

        cg: FakeCodeGenerator = r.code_generator  # type: ignore
        cg.queue_responses(json.dumps({"files": [{"path": path1, "content": "data"}]}))

        ve: FakeValidationEngine = r.validation_engine  # type: ignore
        ve.queue_results(FakeValidationResult(False, category="security-policy", error_summary="blocked"))

        report = r.run("mission-security")
        self.assertFalse(report.success)
        self.assertEqual(report.attempts, 1)
        self.assertEqual(report.final_category, "security-policy")

    def test_provider_auth_failure_stops_immediately(self) -> None:
        r = self._new_runner(max_attempts=3)
        pb: FakePromptBuilder = r.prompt_builder  # type: ignore
        path1 = str(self.tmp / "auth.txt")
        pb.spec["allowlist"] = [path1]

        cg: FakeCodeGenerator = r.code_generator  # type: ignore
        class ProviderAuthError(Exception):
            category = "provider-authentication"
        cg.raise_on_generate = ProviderAuthError("no auth")

        report = r.run("mission-auth")
        self.assertFalse(report.success)
        self.assertEqual(report.attempts, 1)
        self.assertEqual(report.final_category, "provider-authentication")

    def test_cleanup_new_deliverables_between_attempts(self) -> None:
        r = self._new_runner(max_attempts=3)
        pb: FakePromptBuilder = r.prompt_builder  # type: ignore
        p = self.tmp / "new.txt"
        pb.spec["allowlist"] = [str(p)]

        cg: FakeCodeGenerator = r.code_generator  # type: ignore
        cg.queue_responses(json.dumps({"files": [{"path": str(p), "content": "v1"}]}),
                           json.dumps({"files": [{"path": str(p), "content": "v2"}]}))
        ve: FakeValidationEngine = r.validation_engine  # type: ignore
        ve.queue_results(FakeValidationResult(False, category="validation-failure", error_summary="try again"),
                         FakeValidationResult(True))

        self.assertFalse(p.exists())
        report = r.run("mission-clean-new")
        # After failure but before second attempt, file should have been cleaned and recreated
        self.assertTrue(p.exists())
        self.assertTrue(report.success)
        with open(p, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertEqual(content, "v2")

    def test_restoration_of_preexisting_deliverables_and_permissions(self) -> None:
        r = self._new_runner(max_attempts=3)
        pb: FakePromptBuilder = r.prompt_builder  # type: ignore
        p = self.tmp / "pre.txt"
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write("ORIGINAL")
        os.chmod(p, 0o750)
        pb.spec["allowlist"] = [str(p)]

        cg: FakeCodeGenerator = r.code_generator  # type: ignore
        cg.queue_responses(json.dumps({"files": [{"path": str(p), "content": "MODIFIED"}]}),
                           json.dumps({"files": [{"path": str(p), "content": "FIXED"}]}))
        ve: FakeValidationEngine = r.validation_engine  # type: ignore
        ve.queue_results(FakeValidationResult(False, category="validation-failure", error_summary="try again"),
                         FakeValidationResult(True))

        report = r.run("mission-restore-pre")
        self.assertTrue(report.success)
        # Permissions should match original (0o750)
        st = p.stat()
        self.assertEqual(stat.S_IMODE(st.st_mode), 0o750)

    def test_unrelated_files_never_changed(self) -> None:
        r = self._new_runner(max_attempts=2)
        pb: FakePromptBuilder = r.prompt_builder  # type: ignore
        deliver = self.tmp / "deliver.txt"
        unrelated = self.tmp / "unrelated.txt"
        unrelated.write_text("KEEP")
        pb.spec["allowlist"] = [str(deliver)]

        cg: FakeCodeGenerator = r.code_generator  # type: ignore
        cg.queue_responses(json.dumps({"files": [{"path": str(deliver), "content": "X"}]}),
                           json.dumps({"files": [{"path": str(deliver), "content": "Y"}]}))
        ve: FakeValidationEngine = r.validation_engine  # type: ignore
        ve.queue_results(FakeValidationResult(False, category="validation-failure", error_summary="try again"),
                         FakeValidationResult(True))

        report = r.run("mission-unrelated")
        self.assertTrue(report.success)
        self.assertEqual(unrelated.read_text(), "KEEP")

    def test_final_failure_leaves_working_tree_clean(self) -> None:
        r = self._new_runner(max_attempts=2)
        pb: FakePromptBuilder = r.prompt_builder  # type: ignore
        deliver = self.tmp / "final.txt"
        pb.spec["allowlist"] = [str(deliver)]

        cg: FakeCodeGenerator = r.code_generator  # type: ignore
        cg.queue_responses(json.dumps({"files": [{"path": str(deliver), "content": "X"}]}),
                           json.dumps({"files": [{"path": str(deliver), "content": "Y"}]}))
        ve: FakeValidationEngine = r.validation_engine  # type: ignore
        ve.queue_results(FakeValidationResult(False, category="validation-failure", error_summary="try again"),
                         FakeValidationResult(False, category="validation-failure", error_summary="try again"))

        report = r.run("mission-final-clean")
        self.assertFalse(report.success)
        # File should be removed/cleaned
        self.assertFalse(deliver.exists())

    def test_absolute_paths_inside_repo_are_normalized(self) -> None:
        r = self._new_runner(max_attempts=1)
        pb: FakePromptBuilder = r.prompt_builder  # type: ignore
        abs_path = str(self.tmp / "abs.txt")
        pb.spec["allowlist"] = [abs_path]
        cg: FakeCodeGenerator = r.code_generator  # type: ignore
        cg.queue_responses(json.dumps({"files": [{"path": abs_path, "content": "ABS"}]}))
        ve: FakeValidationEngine = r.validation_engine  # type: ignore
        ve.queue_results(FakeValidationResult(True))
        report = r.run("mission-abs")
        self.assertTrue(report.success)
        self.assertTrue((self.tmp / "abs.txt").exists())

    def test_existing_one_attempt_success_behavior_compatible(self) -> None:
        # Success on first attempt should commit and finish; extra attempts unused
        r = self._new_runner(max_attempts=3)
        pb: FakePromptBuilder = r.prompt_builder  # type: ignore
        p = self.tmp / "compat.py"
        pb.spec["allowlist"] = [str(p)]
        cg: FakeCodeGenerator = r.code_generator  # type: ignore
        cg.queue_responses(json.dumps({"files": [{"path": str(p), "content": "print('ok')\n"}]}))
        ve: FakeValidationEngine = r.validation_engine  # type: ignore
        ve.queue_results(FakeValidationResult(True))
        pe: FakePatchEngine = r.patch_engine  # type: ignore
        report = r.run("mission-compat")
        self.assertTrue(report.success)
        self.assertEqual(report.attempts, 1)
        self.assertEqual(len(pe.commits), 1)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
