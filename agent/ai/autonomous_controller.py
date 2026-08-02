from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Protocol, Tuple, runtime_checkable


# Exceptions used by the controller orchestration
class ControllerError(Exception):
    """Base exception for controller errors."""


class SecurityViolation(ControllerError):
    """Raised for immediate abort-worthy security violations."""


class ValidationFailure(ControllerError):
    """Raised when validation fails and may be retryable depending on the RetryEngine."""


class GitReviewRejected(ControllerError):
    """Raised when Git Review rejects the changes."""


class StageFailure(ControllerError):
    """Generic wrapper for stage failures that are not security violations."""
    def __init__(self, stage: str, error: Exception):
        super().__init__(f"Stage '{stage}' failed: {error.__class__.__name__}: {error}")
        self.stage = stage
        self.original = error


# Protocols define the required signatures for dependency injection
@runtime_checkable
class PlanningEngine(Protocol):
    def plan(self, mission: Dict[str, Any]) -> Dict[str, Any]: ...


@runtime_checkable
class RepoScanner(Protocol):
    def scan(self, plan: Dict[str, Any], mission: Dict[str, Any]) -> Dict[str, Any]: ...


@runtime_checkable
class CodeGenerator(Protocol):
    def generate(self, scan: Dict[str, Any], plan: Dict[str, Any], mission: Dict[str, Any]) -> Dict[str, Any]: ...


@runtime_checkable
class PatchGenerator(Protocol):
    def generate(self, code: Dict[str, Any], scan: Dict[str, Any], plan: Dict[str, Any], mission: Dict[str, Any]) -> List[Dict[str, Any]]: ...


@runtime_checkable
class ValidationEngine(Protocol):
    def pre_apply(self, patches: List[Dict[str, Any]], context: Dict[str, Any]) -> Dict[str, Any]: ...
    def post_apply(self, context: Dict[str, Any]) -> Dict[str, Any]: ...


@runtime_checkable
class PatchApplier(Protocol):
    def apply(self, patches: List[Dict[str, Any]], context: Dict[str, Any]) -> Dict[str, Any]: ...


@runtime_checkable
class RetryEngine(Protocol):
    def should_retry(self, context: Dict[str, Any], attempt: int, error: Exception) -> bool: ...


@runtime_checkable
class GitReviewEngine(Protocol):
    def review(self, context: Dict[str, Any]) -> Dict[str, Any]: ...


@runtime_checkable
class CommitEngine(Protocol):
    def commit(self, context: Dict[str, Any]) -> Dict[str, Any]: ...


@runtime_checkable
class PushEngine(Protocol):
    def push(self, context: Dict[str, Any]) -> Dict[str, Any]: ...


@dataclass(slots=True)
class StructuredLogger:
    """Simple structured logger that records deterministic log entries."""
    entries: List[Dict[str, Any]] = field(default_factory=list)

    def log(self, *, stage: str, event: str, message: str, data: Optional[Dict[str, Any]] = None) -> None:
        self.entries.append({
            "stage": stage,
            "event": event,
            "message": message,
            "data": data or {},
        })


@dataclass(slots=True)
class AutonomousController:
    """Top-level controller coordinating autonomous development lifecycle.

    The controller orchestrates the following pipeline deterministically:
      Mission -> Planning -> Repository Scan -> Code Generation -> Patch Generation
      -> Validation (pre-apply) -> Patch Application -> Validation (post-apply)
      -> Retry (if retryable) -> Git Review -> Commit -> Push

    Safety Guarantees:
    - Abort immediately on security violations.
    - Never bypass Validation Engine.
    - Patch Engine applies only validated patches.
    - Never bypass Git Review.
    - Never bypass Retry Engine.
    - Never merge to main/master.
    - Each stage writes structured logs and deterministic JSON reports.
    """

    planning_engine: PlanningEngine
    repo_scanner: RepoScanner
    code_generator: CodeGenerator
    patch_generator: PatchGenerator
    validation_engine: ValidationEngine
    patch_applier: PatchApplier
    retry_engine: RetryEngine
    git_review_engine: GitReviewEngine
    commit_engine: CommitEngine
    push_engine: PushEngine
    logger: StructuredLogger = field(default_factory=StructuredLogger)

    SAFE_BRANCH_DENYLIST: Tuple[str, ...] = ("main", "master")

    def run(self, mission: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a mission end-to-end with retries and safety checks.

        Returns a deterministic JSON-serializable report.
        """
        mission_id = str(mission.get("id") or "mission")
        domain = mission.get("domain") or "github"
        context: Dict[str, Any] = {
            "mission": mission,
            "mission_id": mission_id,
            "domain": domain,
        }

        attempt = 0
        attempts_reports: List[Dict[str, Any]] = []
        final_status: str = "failed"
        last_error: Optional[Exception] = None

        # Ensure branch is explicitly provided and safe; avoid accidental merges to main/master
        self._ensure_safe_branch_precondition(mission)

        while True:
            attempt += 1
            attempt_report: Dict[str, Any] = {"attempt": attempt, "stages": []}
            # snapshot attempt-specific context to avoid cross-attempt contamination
            # (We keep top-level mission and immutable fields constant)
            ctx: Dict[str, Any] = {**context, "attempt": attempt}

            try:
                # Planning
                plan = self._run_stage(
                    name="planning",
                    report=attempt_report,
                    runner=lambda: self.planning_engine.plan(mission),
                )
                ctx["plan"] = plan

                # Repository Scan
                scan = self._run_stage(
                    name="repository_scan",
                    report=attempt_report,
                    runner=lambda: self.repo_scanner.scan(plan, mission),
                )
                ctx["scan"] = scan

                # Code Generation
                code = self._run_stage(
                    name="code_generation",
                    report=attempt_report,
                    runner=lambda: self.code_generator.generate(scan, plan, mission),
                )
                ctx["code"] = code

                # Patch Generation
                patches = self._run_stage(
                    name="patch_generation",
                    report=attempt_report,
                    runner=lambda: self.patch_generator.generate(code, scan, plan, mission),
                )
                ctx["patches"] = patches

                # Validation (pre-apply). Patch Engine applies only validated patches.
                pre_val = self._run_stage(
                    name="validation_pre_apply",
                    report=attempt_report,
                    runner=lambda: self.validation_engine.pre_apply(patches, ctx),
                )
                ctx["validation_pre_apply"] = pre_val

                # Apply Patches
                applied = self._run_stage(
                    name="patch_application",
                    report=attempt_report,
                    runner=lambda: self.patch_applier.apply(patches, ctx),
                )
                ctx["patch_application"] = applied

                # Validation (post-apply)
                post_val = self._run_stage(
                    name="validation_post_apply",
                    report=attempt_report,
                    runner=lambda: self.validation_engine.post_apply(ctx),
                )
                ctx["validation_post_apply"] = post_val

                # Git Review (final safety gate before commit)
                review = self._run_stage(
                    name="git_review",
                    report=attempt_report,
                    runner=lambda: self.git_review_engine.review(ctx),
                )
                ctx["git_review"] = review

                approved = bool(review.get("approved"))
                if not approved:
                    # Git Review decides final safety; prevent commits.
                    raise GitReviewRejected(review.get("reason") or "Git review not approved")

                # Commit (enforce branch safety again before commit)
                self._ensure_safe_branch_pre_commit(mission)
                commit = self._run_stage(
                    name="commit",
                    report=attempt_report,
                    runner=lambda: self.commit_engine.commit(ctx),
                )
                ctx["commit"] = commit

                # Push (never a merge to main/master; commit_engine must have used safe branch)
                push = self._run_stage(
                    name="push",
                    report=attempt_report,
                    runner=lambda: self.push_engine.push(ctx),
                )
                ctx["push"] = push

                final_status = "success"
                last_error = None
                attempts_reports.append(attempt_report)
                break

            except SecurityViolation as sv:
                # Immediate abort on security issues; do not retry
                self._log(stage="controller", event="abort", message="Security violation encountered; aborting mission", data={"attempt": attempt, "error": type(sv).__name__})
                self._append_stage_failure_if_missing(attempt_report, stage_name_hint="security", error=sv)
                attempts_reports.append(attempt_report)
                final_status = "aborted"
                last_error = sv
                break

            except GitReviewRejected as grj:
                # Do not allow retry unless RetryEngine explicitly allows (still consult RetryEngine)
                self._log(stage="controller", event="review_rejected", message="Git review rejected changes", data={"attempt": attempt})
                attempts_reports.append(attempt_report)
                last_error = grj
                if self._should_retry(context=context, attempt=attempt, error=grj):
                    continue
                final_status = "failed"
                break

            except ValidationFailure as vf:
                # Validation failures prevent commits; ask RetryEngine whether to retry
                self._log(stage="controller", event="validation_failed", message="Validation failed", data={"attempt": attempt})
                attempts_reports.append(attempt_report)
                last_error = vf
                if self._should_retry(context=context, attempt=attempt, error=vf):
                    continue
                final_status = "failed"
                break

            except StageFailure as sf:
                # Generic stage failure; check retry policy
                self._log(stage="controller", event="stage_failed", message=f"Stage failed: {sf.stage}", data={"attempt": attempt})
                attempts_reports.append(attempt_report)
                last_error = sf
                if self._should_retry(context=context, attempt=attempt, error=sf):
                    continue
                final_status = "failed"
                break

            except Exception as ex:  # noqa: BLE001 - catch-all to consult RetryEngine
                # Unexpected failure; rely on RetryEngine
                self._log(stage="controller", event="unexpected_exception", message="Unexpected exception during attempt", data={"attempt": attempt, "error": type(ex).__name__})
                # Record as a controller-level stage failure for visibility
                self._append_stage_failure_if_missing(attempt_report, stage_name_hint="unexpected", error=ex)
                attempts_reports.append(attempt_report)
                last_error = ex
                if self._should_retry(context=context, attempt=attempt, error=ex):
                    continue
                final_status = "failed"
                break

        report: Dict[str, Any] = {
            "mission_id": mission_id,
            "domain": domain,
            "attempts": attempt,
            "final_status": final_status,
            "attempt_reports": attempts_reports,
            "logs": list(self.logger.entries),
        }
        return report

    # Internal helpers
    def _run_stage(self, name: str, report: Dict[str, Any], runner: Callable[[], Any]) -> Any:
        self._log(stage=name, event="start", message=f"Starting stage: {name}")
        stage_report: Dict[str, Any] = {"stage": name, "status": "running", "details": {}, "errors": []}
        try:
            result = runner()
            # Expect JSON-serializable results; store under details
            stage_report["status"] = "success"
            stage_report["details"] = self._safe_json(result)
            self._log(stage=name, event="success", message=f"Completed stage: {name}")
            report["stages"].append(stage_report)
            return result
        except SecurityViolation as sv:
            stage_report["status"] = "security_violation"
            stage_report["errors"].append({"type": type(sv).__name__, "message": str(sv)})
            report["stages"].append(stage_report)
            self._log(stage=name, event="security_violation", message=f"Security violation in stage: {name}")
            raise
        except ValidationFailure as vf:
            stage_report["status"] = "failed"
            stage_report["errors"].append({"type": type(vf).__name__, "message": str(vf)})
            report["stages"].append(stage_report)
            self._log(stage=name, event="validation_failed", message=f"Validation failed in stage: {name}")
            raise
        except GitReviewRejected:
            # Should not occur inside _run_stage typically as review result is inspected externally;
            # still capture if thrown by runner.
            raise
        except Exception as ex:  # noqa: BLE001
            stage_report["status"] = "failed"
            stage_report["errors"].append({"type": type(ex).__name__, "message": str(ex)})
            report["stages"].append(stage_report)
            self._log(stage=name, event="failed", message=f"Stage failed: {name}")
            raise StageFailure(stage=name, error=ex) from ex

    def _ensure_safe_branch_precondition(self, mission: Dict[str, Any]) -> None:
        branch = (mission.get("branch") or "").strip()
        if not branch:
            raise SecurityViolation("Target branch must be explicitly provided and non-empty")
        if branch in self.SAFE_BRANCH_DENYLIST:
            raise SecurityViolation(f"Operations on protected branch '{branch}' are not allowed")

    def _ensure_safe_branch_pre_commit(self, mission: Dict[str, Any]) -> None:
        # Re-validate just before committing
        self._ensure_safe_branch_precondition(mission)

    def _should_retry(self, context: Dict[str, Any], attempt: int, error: Exception) -> bool:
        try:
            return bool(self.retry_engine.should_retry(context, attempt, error))
        except Exception:
            # Retry Engine must not be bypassed; if it fails, default to no retry for safety
            return False

    def _log(self, *, stage: str, event: str, message: str, data: Optional[Dict[str, Any]] = None) -> None:
        self.logger.log(stage=stage, event=event, message=message, data=data)

    def _append_stage_failure_if_missing(self, attempt_report: Dict[str, Any], stage_name_hint: str, error: Exception) -> None:
        # If last stage already captured failure, we do not duplicate; else, record a generic failure entry.
        if attempt_report.get("stages"):
            last = attempt_report["stages"][-1]
            if last.get("status") in {"failed", "security_violation"}:
                return
        attempt_report.setdefault("stages", []).append({
            "stage": stage_name_hint,
            "status": "failed",
            "details": {},
            "errors": [{"type": type(error).__name__, "message": str(error)}],
        })

    def _safe_json(self, value: Any) -> Any:
        # Ensure deterministic, JSON-serializable structure; convert non-serializable values to strings.
        if value is None or isinstance(value, (bool, int, float, str)):
            return value
        if isinstance(value, (list, tuple)):
            return [self._safe_json(v) for v in value]
        if isinstance(value, dict):
            # Sort keys for determinism
            return {str(k): self._safe_json(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
        # Fallback to string representation
        return str(value)


__all__ = [
    "AutonomousController",
    "StructuredLogger",
    "ControllerError",
    "SecurityViolation",
    "ValidationFailure",
    "GitReviewRejected",
    "StageFailure",
]
