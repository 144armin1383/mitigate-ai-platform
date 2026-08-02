from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple, Type, Union


class AdapterStatus(str, Enum):
    """Unified adapter status values for normalized results."""

    OK = "ok"
    ERROR = "error"
    BLOCKED = "blocked"


# -----------------------------
# Result models with deterministic serialization
# -----------------------------


def _sorted_dict(d: Mapping[str, Any]) -> Dict[str, Any]:
    """Return a new dict with keys sorted alphabetically for determinism."""
    return {k: d[k] for k in sorted(d.keys())}


@dataclass(frozen=True)
class RetryAdapterResult:
    status: AdapterStatus
    retryable: bool
    blocked: bool
    reason: Optional[str]
    feedback: Optional[str]
    attempts_used: int
    attempts_remaining: int

    def to_dict(self) -> Dict[str, Any]:
        # Deterministic key order
        order = (
            "status",
            "retryable",
            "blocked",
            "reason",
            "feedback",
            "attempts_used",
            "attempts_remaining",
        )
        d: Dict[str, Any] = {
            "status": self.status.value,
            "retryable": self.retryable,
            "blocked": self.blocked,
            "reason": self.reason,
            "feedback": self.feedback,
            "attempts_used": int(self.attempts_used),
            "attempts_remaining": int(self.attempts_remaining),
        }
        return {k: d[k] for k in order}


@dataclass(frozen=True)
class ValidationAdapterResult:
    status: AdapterStatus
    success: bool
    file_validation_counts: Dict[str, int]
    unittest_counts: Dict[str, int]
    errors: List[str]
    logs: List[str]

    def to_dict(self) -> Dict[str, Any]:
        order = (
            "status",
            "success",
            "file_validation_counts",
            "unittest_counts",
            "errors",
            "logs",
        )
        d: Dict[str, Any] = {
            "status": self.status.value,
            "success": self.success,
            # sort nested dict keys deterministically
            "file_validation_counts": _sorted_dict(self.file_validation_counts),
            "unittest_counts": _sorted_dict(self.unittest_counts),
            "errors": list(self.errors),
            "logs": list(self.logs),
        }
        return {k: d[k] for k in order}


@dataclass(frozen=True)
class PatchAdapterResult:
    status: AdapterStatus
    success: bool
    dry_run: bool
    changed_files: List[str]
    errors: List[str]
    logs: List[str]

    def to_dict(self) -> Dict[str, Any]:
        order = (
            "status",
            "success",
            "dry_run",
            "changed_files",
            "errors",
            "logs",
        )
        d: Dict[str, Any] = {
            "status": self.status.value,
            "success": self.success,
            "dry_run": self.dry_run,
            # Preserve original order from engine
            "changed_files": list(self.changed_files),
            "errors": list(self.errors),
            "logs": list(self.logs),
        }
        return {k: d[k] for k in order}


@dataclass(frozen=True)
class GitReviewAdapterResult:
    status: AdapterStatus
    risk_level: str
    recommendation: str
    changed_files: List[str]
    findings: List[Any]
    validation_errors: List[str]
    logs: List[str]

    def to_dict(self) -> Dict[str, Any]:
        order = (
            "status",
            "risk_level",
            "recommendation",
            "changed_files",
            "findings",
            "validation_errors",
            "logs",
        )
        d: Dict[str, Any] = {
            "status": self.status.value,
            "risk_level": self.risk_level,
            "recommendation": self.recommendation,
            # Preserve list ordering
            "changed_files": list(self.changed_files),
            "findings": list(self.findings),
            "validation_errors": list(self.validation_errors),
            "logs": list(self.logs),
        }
        return {k: d[k] for k in order}


# -----------------------------
# Adapters (wrapping existing engines)
# -----------------------------


class RetryAdapter:
    """Compatibility adapter for RetryEngine with normalized results.

    This adapter avoids side effects and preserves the underlying engine's
    redaction and truncation behavior by passing configuration values through.
    """

    def __init__(
        self,
        *,
        max_attempts: int,
        redaction_secrets: Optional[Sequence[str]] = None,
        truncation_limit: Optional[int] = None,
        non_retryable_error_types: Optional[Iterable[str]] = None,
        _engine_cls: Optional[type] = None,
        _config_cls: Optional[type] = None,
        _context_cls: Optional[type] = None,
    ) -> None:
        self._max_attempts = int(max_attempts)
        if self._max_attempts < 0:
            self._max_attempts = 0
        self._secrets = tuple(redaction_secrets or ())
        self._truncation_limit = int(truncation_limit) if truncation_limit is not None else None
        self._non_retryable_types = set(non_retryable_error_types or ())

        if _engine_cls is None or _config_cls is None or _context_cls is None:
            # Lazy import to avoid hard dependency during tests; preserves API
            try:
                from agent.ai.retry_engine import (
                    RetryEngine as _RealRetryEngine,
                    RetryConfiguration as _RealRetryConfiguration,
                    FailureContext as _RealFailureContext,
                )
            except Exception:  # pragma: no cover - tests inject dummies
                _RealRetryEngine = None  # type: ignore[assignment]
                _RealRetryConfiguration = None  # type: ignore[assignment]
                _RealFailureContext = None  # type: ignore[assignment]
            self._engine_cls = _engine_cls or _RealRetryEngine
            self._config_cls = _config_cls or _RealRetryConfiguration
            self._context_cls = _context_cls or _RealFailureContext
        else:
            self._engine_cls = _engine_cls
            self._config_cls = _config_cls
            self._context_cls = _context_cls

    @property
    def max_attempts(self) -> int:
        return self._max_attempts

    def _make_config(self) -> Any:
        if self._config_cls is None:
            # Fallback minimal object
            return SimpleNamespace(
                max_attempts=self._max_attempts,
                redaction_secrets=self._secrets,
                truncation_limit=self._truncation_limit,
            )
        try:
            # Prefer keyword arguments to be explicit and typed
            return self._config_cls(
                max_attempts=self._max_attempts,
                redaction_secrets=self._secrets,
                truncation_limit=self._truncation_limit,
            )
        except TypeError:
            # Attempt positional construction if engine expects ordered args
            return self._config_cls(self._max_attempts, self._secrets, self._truncation_limit)

    def _make_context(
        self, *, message: str, error_type: str, attempts_used: int, feedback: Optional[str]
    ) -> Any:
        if self._context_cls is None:
            return SimpleNamespace(
                message=message,
                error_type=error_type,
                attempts_used=attempts_used,
                feedback=feedback,
            )
        try:
            return self._context_cls(
                message=message,
                error_type=error_type,
                attempts_used=attempts_used,
                feedback=feedback,
            )
        except TypeError:
            return self._context_cls(message, error_type, attempts_used, feedback)

    def _call_engine(self, engine: Any, context: Any, config: Any) -> Any:
        # Try common method signatures conservatively
        if hasattr(engine, "evaluate"):
            try:
                return engine.evaluate(context, config)
            except TypeError:
                return engine.evaluate(context)
        # Fallback no-op result
        return SimpleNamespace(
            retryable=False,
            blocked=True,
            reason="No evaluate method",
            feedback=None,
            attempts_used=getattr(context, "attempts_used", 0),
        )

    def evaluate(
        self, *, error_message: str, error_type: str, attempts_used: int, feedback: Optional[str] = None
    ) -> RetryAdapterResult:
        # Enforce non-retryable protection at adapter level
        remaining = max(0, self._max_attempts - int(attempts_used))
        if error_type in self._non_retryable_types:
            reason = f"non-retryable error type: {error_type}"
            return RetryAdapterResult(
                status=AdapterStatus.BLOCKED,
                retryable=False,
                blocked=True,
                reason=reason,
                feedback=feedback,
                attempts_used=int(attempts_used),
                attempts_remaining=remaining,
            )

        try:
            config = self._make_config()
            context = self._make_context(
                message=error_message,
                error_type=error_type,
                attempts_used=int(attempts_used),
                feedback=feedback,
            )

            if self._engine_cls is None:
                # No engine available; treat as blocked error deterministically
                return RetryAdapterResult(
                    status=AdapterStatus.ERROR,
                    retryable=False,
                    blocked=True,
                    reason="RetryEngine unavailable",
                    feedback=feedback,
                    attempts_used=int(attempts_used),
                    attempts_remaining=remaining,
                )

            try:
                engine = self._engine_cls(config)
            except TypeError:
                engine = self._engine_cls()

            raw = self._call_engine(engine, context, config)

            # Normalize output defensively
            retryable = bool(getattr(raw, "retryable", False))
            blocked = bool(getattr(raw, "blocked", False))
            reason_val = getattr(raw, "reason", None)
            feedback_val = getattr(raw, "feedback", feedback)
            used = int(getattr(raw, "attempts_used", attempts_used))
            remaining_calc = max(0, self._max_attempts - used)

            # Never retry if remaining is zero
            if remaining_calc <= 0:
                retryable = False
                blocked = True or blocked

            status = AdapterStatus.OK
            if blocked and not retryable:
                status = AdapterStatus.BLOCKED

            return RetryAdapterResult(
                status=status,
                retryable=retryable,
                blocked=blocked,
                reason=reason_val,
                feedback=feedback_val,
                attempts_used=used,
                attempts_remaining=remaining_calc,
            )
        except Exception as exc:  # Preserve security: do not include secrets; we only include str(exc)
            return RetryAdapterResult(
                status=AdapterStatus.ERROR,
                retryable=False,
                blocked=True,
                reason=str(exc),
                feedback=feedback,
                attempts_used=int(attempts_used),
                attempts_remaining=remaining,
            )


class ValidationAdapter:
    """Compatibility adapter for ValidationEngine with normalized results.

    This adapter ensures repository files are not modified by the adapter layer.
    Any file changes are solely the responsibility of the underlying engine.
    """

    def __init__(self, repo_root: Union[str, Path], *, _engine_cls: Optional[type] = None) -> None:
        self._root = Path(repo_root)
        if _engine_cls is None:
            try:
                from agent.validators.validation_engine import ValidationEngine as _RealValidationEngine
            except Exception:  # pragma: no cover - tests inject dummies
                _RealValidationEngine = None  # type: ignore[assignment]
            self._engine_cls = _RealValidationEngine
        else:
            self._engine_cls = _engine_cls

    def evaluate(
        self, *, selected_files: Optional[Sequence[str]] = None, run_tests: bool = True
    ) -> ValidationAdapterResult:
        try:
            if self._engine_cls is None:
                return ValidationAdapterResult(
                    status=AdapterStatus.ERROR,
                    success=False,
                    file_validation_counts={},
                    unittest_counts={},
                    errors=["ValidationEngine unavailable"],
                    logs=[],
                )

            try:
                engine = self._engine_cls(self._root)
            except TypeError:
                engine = self._engine_cls()

            # Try common signatures
            if hasattr(engine, "validate"):
                try:
                    raw = engine.validate(files=selected_files, run_tests=run_tests)
                except TypeError:
                    raw = engine.validate(selected_files, run_tests)
            elif hasattr(engine, "run"):
                try:
                    raw = engine.run(files=selected_files, run_tests=run_tests)
                except TypeError:
                    raw = engine.run(selected_files, run_tests)
            else:
                raise RuntimeError("ValidationEngine does not support validate/run")

            # Normalize result
            success = bool(getattr(raw, "success", False) if not isinstance(raw, dict) else raw.get("success", False))
            file_counts = (
                getattr(raw, "file_validation_counts", {}) if not isinstance(raw, dict) else raw.get("file_validation_counts", {})
            )
            unit_counts = (
                getattr(raw, "unittest_counts", {}) if not isinstance(raw, dict) else raw.get("unittest_counts", {})
            )
            errors = list(
                getattr(raw, "errors", []) if not isinstance(raw, dict) else raw.get("errors", [])
            )
            logs = list(getattr(raw, "logs", []) if not isinstance(raw, dict) else raw.get("logs", []))

            return ValidationAdapterResult(
                status=AdapterStatus.OK if success else AdapterStatus.ERROR,
                success=success,
                file_validation_counts={str(k): int(v) for k, v in dict(file_counts).items()},
                unittest_counts={str(k): int(v) for k, v in dict(unit_counts).items()},
                errors=[str(e) for e in errors],
                logs=[str(l) for l in logs],
            )
        except Exception as exc:
            return ValidationAdapterResult(
                status=AdapterStatus.ERROR,
                success=False,
                file_validation_counts={},
                unittest_counts={},
                errors=[str(exc)],
                logs=[],
            )


class PatchAdapter:
    """Compatibility adapter for PatchEngine with normalized results.

    Supports dry-run and apply modes. All path protections and rollback behavior
    remain within the PatchEngine; the adapter does not modify files directly.
    """

    def __init__(self, repo_root: Union[str, Path], *, _engine_cls: Optional[type] = None) -> None:
        self._root = Path(repo_root)
        if _engine_cls is None:
            try:
                from agent.git.patch_engine import PatchEngine as _RealPatchEngine
            except Exception:  # pragma: no cover - tests inject dummies
                _RealPatchEngine = None  # type: ignore[assignment]
            self._engine_cls = _RealPatchEngine
        else:
            self._engine_cls = _engine_cls

    def apply(self, *, unified_diff: str, dry_run: bool = True) -> PatchAdapterResult:
        try:
            if self._engine_cls is None:
                return PatchAdapterResult(
                    status=AdapterStatus.ERROR,
                    success=False,
                    dry_run=dry_run,
                    changed_files=[],
                    errors=["PatchEngine unavailable"],
                    logs=[],
                )

            try:
                engine = self._engine_cls(self._root)
            except TypeError:
                engine = self._engine_cls()

            raw: Any
            # Try common signatures: apply(diff, dry_run=bool) or apply(diff, repo_root, dry_run)
            if hasattr(engine, "apply"):
                try:
                    raw = engine.apply(unified_diff, dry_run=dry_run)
                except TypeError:
                    try:
                        raw = engine.apply(unified_diff, self._root, dry_run)
                    except TypeError:
                        raw = engine.apply(unified_diff)
            elif hasattr(engine, "dry_run") and dry_run:
                raw = engine.dry_run(unified_diff)
            else:
                raise RuntimeError("PatchEngine does not support apply/dry_run")

            success = bool(getattr(raw, "success", False) if not isinstance(raw, dict) else raw.get("success", False))
            changed_files = (
                getattr(raw, "changed_files", []) if not isinstance(raw, dict) else raw.get("changed_files", [])
            )
            errors = list(
                getattr(raw, "errors", []) if not isinstance(raw, dict) else raw.get("errors", [])
            )
            logs = list(getattr(raw, "logs", []) if not isinstance(raw, dict) else raw.get("logs", []))

            return PatchAdapterResult(
                status=AdapterStatus.OK if success else AdapterStatus.ERROR,
                success=success,
                dry_run=dry_run,
                changed_files=[str(p) for p in changed_files],
                errors=[str(e) for e in errors],
                logs=[str(l) for l in logs],
            )
        except Exception as exc:
            return PatchAdapterResult(
                status=AdapterStatus.ERROR,
                success=False,
                dry_run=dry_run,
                changed_files=[],
                errors=[str(exc)],
                logs=[],
            )


class GitReviewAdapter:
    """Compatibility adapter for GitReviewEngine with normalized results.

    The adapter never mutates the Git state; any such behavior resides in the
    underlying engine which is invoked read-only where supported.
    """

    def __init__(self, repo_root: Union[str, Path], *, _engine_cls: Optional[type] = None) -> None:
        self._root = Path(repo_root)
        if _engine_cls is None:
            try:
                from agent.git.review_engine import GitReviewEngine as _RealGitReviewEngine
            except Exception:  # pragma: no cover - tests inject dummies
                _RealGitReviewEngine = None  # type: ignore[assignment]
            self._engine_cls = _RealGitReviewEngine
        else:
            self._engine_cls = _engine_cls

    def review(self, *, base_ref: str, target_ref: str) -> GitReviewAdapterResult:
        try:
            if self._engine_cls is None:
                return GitReviewAdapterResult(
                    status=AdapterStatus.ERROR,
                    risk_level="unknown",
                    recommendation="GitReviewEngine unavailable",
                    changed_files=[],
                    findings=[],
                    validation_errors=["GitReviewEngine unavailable"],
                    logs=[],
                )

            try:
                engine = self._engine_cls(self._root)
            except TypeError:
                engine = self._engine_cls()

            # Try common signatures: review(base, target) or review(root, base, target)
            if hasattr(engine, "review"):
                try:
                    raw = engine.review(base_ref, target_ref)
                except TypeError:
                    raw = engine.review(self._root, base_ref, target_ref)
            else:
                raise RuntimeError("GitReviewEngine does not support review")

            # Normalize
            if isinstance(raw, dict):
                risk_level = str(raw.get("risk_level", "unknown"))
                recommendation = str(raw.get("recommendation", ""))
                changed_files = list(raw.get("changed_files", []))
                findings = list(raw.get("findings", []))
                validation_errors = list(raw.get("validation_errors", []))
                logs = list(raw.get("logs", []))
            else:
                risk_level = str(getattr(raw, "risk_level", "unknown"))
                recommendation = str(getattr(raw, "recommendation", ""))
                changed_files = list(getattr(raw, "changed_files", []))
                findings = list(getattr(raw, "findings", []))
                validation_errors = list(getattr(raw, "validation_errors", []))
                logs = list(getattr(raw, "logs", []))

            status = AdapterStatus.OK
            if risk_level.lower() in {"high", "critical"}:
                status = AdapterStatus.ERROR  # elevated status for risky reviews

            return GitReviewAdapterResult(
                status=status,
                risk_level=risk_level,
                recommendation=recommendation,
                changed_files=[str(p) for p in changed_files],
                findings=findings,
                validation_errors=[str(e) for e in validation_errors],
                logs=[str(l) for l in logs],
            )
        except Exception as exc:
            return GitReviewAdapterResult(
                status=AdapterStatus.ERROR,
                risk_level="unknown",
                recommendation=str(exc),
                changed_files=[],
                findings=[],
                validation_errors=[str(exc)],
                logs=[],
            )
