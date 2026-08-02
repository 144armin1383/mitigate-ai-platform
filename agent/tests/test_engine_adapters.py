from __future__ import annotations

import io
import os
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Sequence

from agent.ai.engine_adapters import (
    AdapterStatus,
    GitReviewAdapter,
    GitReviewAdapterResult,
    PatchAdapter,
    PatchAdapterResult,
    RetryAdapter,
    RetryAdapterResult,
    ValidationAdapter,
    ValidationAdapterResult,
)


# -----------------------------
# Dummy engines and models for testing
# -----------------------------


@dataclass
class DummyRetryConfiguration:
    max_attempts: int
    redaction_secrets: Sequence[str]
    truncation_limit: Optional[int]


@dataclass
class DummyFailureContext:
    message: str
    error_type: str
    attempts_used: int
    feedback: Optional[str]


class DummyRetryEngine:
    def __init__(self, config: DummyRetryConfiguration) -> None:
        self.config = config
        self.last_context: Optional[DummyFailureContext] = None
        self.last_config: Optional[DummyRetryConfiguration] = None

    def evaluate(self, context: DummyFailureContext, config: Optional[DummyRetryConfiguration] = None) -> Any:
        # Capture for assertion
        self.last_context = context
        self.last_config = config or self.config
        # Simulate decision: retryable if attempts remaining > 0 and not SyntaxError
        if context.error_type == "AlwaysRetry":
            retryable = True
            blocked = False
            reason = "transient"
        elif context.error_type == "NeverRetry":
            retryable = False
            blocked = True
            reason = "policy"
        else:
            retryable = (self.config.max_attempts - context.attempts_used) > 0
            blocked = not retryable
            reason = None
        return SimpleNamespace(
            retryable=retryable,
            blocked=blocked,
            reason=reason,
            feedback=context.feedback,
            attempts_used=context.attempts_used,
        )


class DummyValidationEngine:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def validate(self, files: Optional[Sequence[str]] = None, run_tests: bool = True) -> Any:
        files = list(files or [])
        file_counts = {"checked": len(files), "skipped": 0}
        unit_counts = {"run": 5 if run_tests else 0, "failures": 0}
        return SimpleNamespace(
            success=True,
            file_validation_counts=file_counts,
            unittest_counts=unit_counts,
            errors=[],
            logs=[f"Validated {len(files)} files", f"Run tests: {run_tests}"],
        )


class DummyValidationEngineFailure:
    def __init__(self, root: Path) -> None:  # pragma: no cover - simple constructor
        self.root = Path(root)

    def validate(self, files: Optional[Sequence[str]] = None, run_tests: bool = True) -> Any:
        raise RuntimeError("validation failed")


class DummyPatchEngine:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def apply(self, diff: str, *args: Any, **kwargs: Any) -> Any:
        # Determine dry_run from kwargs or args
        dry_run = kwargs.get("dry_run") if "dry_run" in kwargs else (args[-1] if args else False)
        changed: List[str] = []
        for line in diff.splitlines():
            if line.startswith("+++ b/"):
                changed.append(line[6:].strip())
        logs = ["Parsed diff", f"Dry run: {bool(dry_run)}"]
        return {
            "success": True,
            "changed_files": changed,
            "errors": [],
            "logs": logs,
        }


class DummyPatchEngineFailure:
    def __init__(self, root: Path) -> None:  # pragma: no cover
        self.root = Path(root)

    def apply(self, diff: str, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("patch failed")


class DummyGitReviewEngine:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def review(self, *args: Any) -> Any:
        if len(args) == 2:
            base, target = args
        else:
            _, base, target = args
        # Decide risk level by target name for determinism
        if target == "feature/low":
            risk = "low"
            rec = "Proceed"
        elif target == "feature/high":
            risk = "high"
            rec = "Needs attention"
        else:
            risk = "critical"
            rec = "Block merge"
        return SimpleNamespace(
            risk_level=risk,
            recommendation=rec,
            changed_files=["app.py", "README.md"],
            findings=[{"file": "app.py", "issue": "complexity"}],
            validation_errors=[],
            logs=[f"Compared {base}..{target}"],
        )


class DummyGitReviewEngineFailure:
    def __init__(self, root: Path) -> None:  # pragma: no cover
        self.root = Path(root)

    def review(self, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("git review failed")


# -----------------------------
# Tests
# -----------------------------


class TestRetryAdapter(unittest.TestCase):
    def test_retry_engine_construction(self) -> None:
        adapter = RetryAdapter(
            max_attempts=3,
            redaction_secrets=["SECRET"],
            truncation_limit=128,
            _engine_cls=DummyRetryEngine,
            _config_cls=DummyRetryConfiguration,
            _context_cls=DummyFailureContext,
        )
        result = adapter.evaluate(
            error_message="Boom",
            error_type="AlwaysRetry",
            attempts_used=1,
            feedback="note",
        )
        self.assertIsInstance(result, RetryAdapterResult)
        # Verify engine captured proper construction values
        engine = DummyRetryEngine(adapter._make_config())
        engine.evaluate(DummyFailureContext("m", "t", 0, None))  # touch methods
        # Real captured ones are inside adapter's engine; re-initialize to assert via config type
        # Instead, reconstruct and assert adapter-level invariants
        self.assertEqual(adapter.max_attempts, 3)
        self.assertEqual(result.attempts_remaining, 2)

        # Ensure non-retryable not applied here
        self.assertTrue(result.retryable)
        self.assertFalse(result.blocked)

    def test_retryable_and_blocked_decisions(self) -> None:
        # Retryable path
        adapter = RetryAdapter(
            max_attempts=3,
            _engine_cls=DummyRetryEngine,
            _config_cls=DummyRetryConfiguration,
            _context_cls=DummyFailureContext,
        )
        r1 = adapter.evaluate(error_message="x", error_type="AlwaysRetry", attempts_used=1)
        self.assertTrue(r1.retryable)
        self.assertFalse(r1.blocked)
        self.assertEqual(r1.attempts_remaining, 2)

        # Blocked by non-retryable type regardless of engine decision
        adapter_nr = RetryAdapter(
            max_attempts=3,
            non_retryable_error_types={"SyntaxError", "NeverRetry"},
            _engine_cls=DummyRetryEngine,
            _config_cls=DummyRetryConfiguration,
            _context_cls=DummyFailureContext,
        )
        r2 = adapter_nr.evaluate(error_message="y", error_type="NeverRetry", attempts_used=1)
        self.assertFalse(r2.retryable)
        self.assertTrue(r2.blocked)
        self.assertIn("non-retryable", r2.reason or "")
        self.assertEqual(r2.attempts_remaining, 2)

        # Exhausted attempts must be blocked
        r3 = adapter.evaluate(error_message="z", error_type="Anything", attempts_used=3)
        self.assertFalse(r3.retryable)
        self.assertTrue(r3.blocked)
        self.assertEqual(r3.attempts_remaining, 0)


class TestValidationAdapter(unittest.TestCase):
    def test_validation_success_normalization(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            adapter = ValidationAdapter(root, _engine_cls=DummyValidationEngine)
            res = adapter.evaluate(selected_files=["a.py", "b.py"], run_tests=True)
            self.assertIsInstance(res, ValidationAdapterResult)
            self.assertTrue(res.success)
            d = res.to_dict()
            self.assertEqual(d["status"], AdapterStatus.OK.value)
            self.assertEqual(d["file_validation_counts"].get("checked"), 2)
            self.assertEqual(d["unittest_counts"].get("run"), 5)
            # Deterministic key order
            self.assertEqual(list(d.keys()), [
                "status",
                "success",
                "file_validation_counts",
                "unittest_counts",
                "errors",
                "logs",
            ])

    def test_validation_failure_normalization(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            adapter = ValidationAdapter(td, _engine_cls=DummyValidationEngineFailure)
            res = adapter.evaluate(selected_files=["c.py"], run_tests=False)
            self.assertFalse(res.success)
            self.assertEqual(res.status, AdapterStatus.ERROR)
            self.assertTrue(any("validation failed" in e for e in res.errors))


class TestPatchAdapter(unittest.TestCase):
    def _sample_diff(self) -> str:
        return "\n".join([
            "diff --git a/app.py b/app.py",
            "index 83db48f..f735c50 100644",
            "--- a/app.py",
            "+++ b/app.py",
            "@@ -1,3 +1,3 @@",
            "-print('hello')",
            "+print('hello world')",
        ])

    def test_patch_dry_run_normalization(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            adapter = PatchAdapter(root, _engine_cls=DummyPatchEngine)
            res = adapter.apply(unified_diff=self._sample_diff(), dry_run=True)
            self.assertIsInstance(res, PatchAdapterResult)
            self.assertTrue(res.success)
            self.assertTrue(res.dry_run)
            self.assertIn("app.py", res.changed_files)
            d = res.to_dict()
            self.assertEqual(list(d.keys()), [
                "status",
                "success",
                "dry_run",
                "changed_files",
                "errors",
                "logs",
            ])

    def test_patch_apply_normalization_and_error(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            adapter_ok = PatchAdapter(root, _engine_cls=DummyPatchEngine)
            res_ok = adapter_ok.apply(unified_diff=self._sample_diff(), dry_run=False)
            self.assertTrue(res_ok.success)
            self.assertFalse(res_ok.dry_run)

            adapter_fail = PatchAdapter(root, _engine_cls=DummyPatchEngineFailure)
            res_fail = adapter_fail.apply(unified_diff=self._sample_diff(), dry_run=False)
            self.assertFalse(res_fail.success)
            self.assertEqual(res_fail.status, AdapterStatus.ERROR)
            self.assertTrue(any("patch failed" in e for e in res_fail.errors))


class TestGitReviewAdapter(unittest.TestCase):
    def test_risk_levels_normalization(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            adapter = GitReviewAdapter(root, _engine_cls=DummyGitReviewEngine)

            low = adapter.review(base_ref="main", target_ref="feature/low")
            self.assertEqual(low.risk_level, "low")
            self.assertEqual(low.status, AdapterStatus.OK)

            high = adapter.review(base_ref="main", target_ref="feature/high")
            self.assertEqual(high.risk_level, "high")
            self.assertEqual(high.status, AdapterStatus.ERROR)

            crit = adapter.review(base_ref="main", target_ref="feature/critical")
            self.assertEqual(crit.risk_level, "critical")
            self.assertEqual(crit.status, AdapterStatus.ERROR)

    def test_git_review_error_handling(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            adapter = GitReviewAdapter(td, _engine_cls=DummyGitReviewEngineFailure)
            res = adapter.review(base_ref="main", target_ref="feature/x")
            self.assertEqual(res.status, AdapterStatus.ERROR)
            self.assertTrue(any("git review failed" in e for e in res.validation_errors))


class TestDeterministicSerialization(unittest.TestCase):
    def test_retry_result_serialization_order(self) -> None:
        r = RetryAdapterResult(
            status=AdapterStatus.BLOCKED,
            retryable=False,
            blocked=True,
            reason="x",
            feedback=None,
            attempts_used=2,
            attempts_remaining=1,
        )
        d = r.to_dict()
        self.assertEqual(list(d.keys()), [
            "status",
            "retryable",
            "blocked",
            "reason",
            "feedback",
            "attempts_used",
            "attempts_remaining",
        ])

    def test_validation_result_serialization_sorting(self) -> None:
        v = ValidationAdapterResult(
            status=AdapterStatus.OK,
            success=True,
            file_validation_counts={"b": 1, "a": 2},
            unittest_counts={"y": 3, "x": 4},
            errors=["e1"],
            logs=["l1"],
        )
        d = v.to_dict()
        self.assertEqual(list(d["file_validation_counts"].keys()), ["a", "b"])  # sorted
        self.assertEqual(list(d["unittest_counts"].keys()), ["x", "y"])  # sorted


class TestNoSideEffects(unittest.TestCase):
    def test_adapters_do_not_modify_unrelated_files(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            sentinel = root / "SENTINEL.txt"
            sentinel.write_text("content", encoding="utf-8")
            sentinel_mtime = sentinel.stat().st_mtime

            # Run all adapters
            ra = RetryAdapter(
                max_attempts=2,
                _engine_cls=DummyRetryEngine,
                _config_cls=DummyRetryConfiguration,
                _context_cls=DummyFailureContext,
            )
            _ = ra.evaluate(error_message="e", error_type="AlwaysRetry", attempts_used=0)

            va = ValidationAdapter(root, _engine_cls=DummyValidationEngine)
            _ = va.evaluate(selected_files=["a.py"], run_tests=False)

            pa = PatchAdapter(root, _engine_cls=DummyPatchEngine)
            _ = pa.apply(unified_diff="""diff --git a/a b/a\n--- a/a\n+++ b/a\n@@\n-old\n+new\n""", dry_run=True)

            ga = GitReviewAdapter(root, _engine_cls=DummyGitReviewEngine)
            _ = ga.review(base_ref="main", target_ref="feature/low")

            # Ensure no changes to sentinel
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "content")
            self.assertEqual(sentinel_mtime, sentinel.stat().st_mtime)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
