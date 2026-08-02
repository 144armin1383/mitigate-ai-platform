from __future__ import annotations

import unittest
from typing import Any, Dict, List

from agent.ai.autonomous_controller import (
    AutonomousController,
    GitReviewRejected,
    SecurityViolation,
    StageFailure,
    ValidationFailure,
    StructuredLogger,
)


# Mock engine implementations for deterministic testing
class MockPlanningEngine:
    def plan(self, mission: Dict[str, Any]) -> Dict[str, Any]:
        return {"objective": mission.get("title", "objective"), "strategy": "default"}


class MockRepoScanner:
    def __init__(self, fail_first_attempt: bool = False):
        self.fail_first_attempt = fail_first_attempt
        self.calls = 0

    def scan(self, plan: Dict[str, Any], mission: Dict[str, Any]) -> Dict[str, Any]:
        self.calls += 1
        if self.fail_first_attempt and self.calls == 1:
            raise RuntimeError("transient scan error")
        return {"files": ["a.py", "b.py"], "summary": "ok"}


class MockCodeGenerator:
    def generate(self, scan: Dict[str, Any], plan: Dict[str, Any], mission: Dict[str, Any]) -> Dict[str, Any]:
        return {"units": ["module_a"], "quality": "high"}


class MockPatchGenerator:
    def generate(self, code: Dict[str, Any], scan: Dict[str, Any], plan: Dict[str, Any], mission: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [
            {"file": "a.py", "diff": "+print('hello')\n", "type": "modify"},
        ]


class MockValidationEngine:
    def __init__(self, *, pre_ok: bool = True, post_ok_attempts: List[bool] | None = None, security_violation: bool = False):
        self.pre_ok = pre_ok
        self.post_ok_attempts = post_ok_attempts or [True]
        self.security_violation = security_violation
        self.post_calls = 0

    def pre_apply(self, patches: List[Dict[str, Any]], context: Dict[str, Any]) -> Dict[str, Any]:
        if self.security_violation:
            raise SecurityViolation("unsafe operation detected")
        if not self.pre_ok:
            raise ValidationFailure("pre-apply validation failed")
        return {"ok": True, "checked": len(patches)}

    def post_apply(self, context: Dict[str, Any]) -> Dict[str, Any]:
        self.post_calls += 1
        ok = True
        if self.post_calls <= len(self.post_ok_attempts):
            ok = self.post_ok_attempts[self.post_calls - 1]
        if not ok:
            raise ValidationFailure("post-apply validation failed")
        return {"ok": True}


class MockPatchApplier:
    def __init__(self):
        self.apply_calls = 0

    def apply(self, patches: List[Dict[str, Any]], context: Dict[str, Any]) -> Dict[str, Any]:
        self.apply_calls += 1
        return {"applied": len(patches), "status": "done"}


class MockRetryEngine:
    def __init__(self, max_attempts: int = 2):
        self.max_attempts = max_attempts

    def should_retry(self, context: Dict[str, Any], attempt: int, error: Exception) -> bool:
        # Retry up to max_attempts for StageFailure or ValidationFailure or generic RuntimeError
        retryable_types = (StageFailure, ValidationFailure, RuntimeError, GitReviewRejected)
        if not isinstance(error, retryable_types):
            return False
        return attempt < self.max_attempts


class MockGitReviewEngine:
    def __init__(self, approvals: List[bool] | None = None):
        self.approvals = approvals or [True]
        self.calls = 0

    def review(self, context: Dict[str, Any]) -> Dict[str, Any]:
        self.calls += 1
        idx = min(self.calls - 1, len(self.approvals) - 1)
        approved = self.approvals[idx]
        return {"approved": approved, "reason": None if approved else "policy block"}


class MockCommitEngine:
    def __init__(self):
        self.commits = 0

    def commit(self, context: Dict[str, Any]) -> Dict[str, Any]:
        self.commits += 1
        branch = context["mission"]["branch"]
        return {"commit_id": f"deadbeef{self.commits}", "branch": branch}


class MockPushEngine:
    def __init__(self):
        self.pushes = 0

    def push(self, context: Dict[str, Any]) -> Dict[str, Any]:
        self.pushes += 1
        return {"pushed": True, "count": self.pushes}


def build_controller(**overrides: Any) -> tuple[AutonomousController, Dict[str, Any]]:
    engines: Dict[str, Any] = {
        "planning_engine": MockPlanningEngine(),
        "repo_scanner": MockRepoScanner(),
        "code_generator": MockCodeGenerator(),
        "patch_generator": MockPatchGenerator(),
        "validation_engine": MockValidationEngine(),
        "patch_applier": MockPatchApplier(),
        "retry_engine": MockRetryEngine(max_attempts=3),
        "git_review_engine": MockGitReviewEngine(),
        "commit_engine": MockCommitEngine(),
        "push_engine": MockPushEngine(),
        "logger": StructuredLogger(),
    }
    engines.update(overrides)
    controller = AutonomousController(**engines)
    return controller, engines


class TestAutonomousController(unittest.TestCase):
    def test_successful_mission_completes(self) -> None:
        controller, engines = build_controller()
        mission = {"id": "m1", "title": "Test Mission", "domain": "github", "branch": "feature/auto-1"}
        report = controller.run(mission)

        self.assertEqual(report["final_status"], "success")
        self.assertEqual(report["attempts"], 1)
        self.assertTrue(any(s["stage"] == "commit" for s in report["attempt_reports"][0]["stages"]))
        self.assertTrue(any(s["stage"] == "push" for s in report["attempt_reports"][0]["stages"]))
        self.assertEqual(engines["commit_engine"].commits, 1)
        self.assertEqual(engines["push_engine"].pushes, 1)
        # Ensure validation and review are present
        stages = [s["stage"] for s in report["attempt_reports"][0]["stages"]]
        self.assertIn("validation_pre_apply", stages)
        self.assertIn("validation_post_apply", stages)
        self.assertIn("git_review", stages)

    def test_retryable_failure_retried_then_success(self) -> None:
        # Post-apply validation fails first attempt, then succeeds
        validation_engine = MockValidationEngine(post_ok_attempts=[False, True])
        controller, engines = build_controller(validation_engine=validation_engine)
        mission = {"id": "m2", "title": "Retry Mission", "domain": "github", "branch": "feature/retry-1"}

        report = controller.run(mission)
        self.assertEqual(report["final_status"], "success")
        self.assertEqual(report["attempts"], 2)
        # Ensure we only committed/pushed once after success
        self.assertEqual(engines["commit_engine"].commits, 1)
        self.assertEqual(engines["push_engine"].pushes, 1)
        # Ensure patch application was attempted twice
        self.assertEqual(engines["patch_applier"].apply_calls, 2)

    def test_non_retryable_git_review_rejection_aborts_commit(self) -> None:
        git_review_engine = MockGitReviewEngine(approvals=[False])
        # Retry engine will allow retry for GitReviewRejected but max_attempts=1 forces stop
        retry_engine = MockRetryEngine(max_attempts=1)
        controller, engines = build_controller(git_review_engine=git_review_engine, retry_engine=retry_engine)
        mission = {"id": "m3", "title": "No Review", "domain": "github", "branch": "feature/no-review"}

        report = controller.run(mission)
        self.assertEqual(report["final_status"], "failed")
        self.assertEqual(report["attempts"], 1)
        # No commit or push should happen
        self.assertEqual(engines["commit_engine"].commits, 0)
        self.assertEqual(engines["push_engine"].pushes, 0)
        # Ensure git_review stage exists and indicates success=false in details
        stages = report["attempt_reports"][0]["stages"]
        self.assertTrue(any(s["stage"] == "git_review" for s in stages))

    def test_security_violation_aborts_immediately(self) -> None:
        validation_engine = MockValidationEngine(security_violation=True)
        controller, engines = build_controller(validation_engine=validation_engine)
        mission = {"id": "m4", "title": "Unsafe Mission", "domain": "github", "branch": "feature/unsafe"}

        report = controller.run(mission)
        self.assertEqual(report["final_status"], "aborted")
        # No commit or push
        self.assertEqual(engines["commit_engine"].commits, 0)
        self.assertEqual(engines["push_engine"].pushes, 0)
        # Ensure pipeline stopped before patch application
        stages = [s["stage"] for s in report["attempt_reports"][0]["stages"]]
        self.assertIn("validation_pre_apply", stages)
        self.assertNotIn("patch_application", stages)

    def test_prevent_merge_to_main(self) -> None:
        controller, _ = build_controller()
        mission = {"id": "m5", "title": "Main Blocked", "domain": "github", "branch": "main"}
        with self.assertRaises(SecurityViolation):
            controller.run(mission)

    def test_retry_state_survives_internal_exceptions(self) -> None:
        # Repo scanner fails first attempt, then succeeds; controller should retry and complete
        repo_scanner = MockRepoScanner(fail_first_attempt=True)
        controller, engines = build_controller(repo_scanner=repo_scanner)
        mission = {"id": "m6", "title": "Transient Error", "domain": "github", "branch": "feature/transient"}

        report = controller.run(mission)
        self.assertEqual(report["final_status"], "success")
        self.assertEqual(report["attempts"], 2)
        self.assertEqual(engines["commit_engine"].commits, 1)
        self.assertEqual(engines["push_engine"].pushes, 1)
        # Ensure repo scan was called twice
        self.assertEqual(repo_scanner.calls, 2)


if __name__ == "__main__":
    unittest.main()
