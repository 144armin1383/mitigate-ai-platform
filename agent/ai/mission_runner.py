from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# Note on imports:
# We support both package layouts: 'ai.*' and 'agent.ai.*'. This runner
# attempts to import from 'ai' first and falls back to 'agent.ai'. This keeps
# compatibility with existing environments and tests.

def _import_ai_module(mod: str) -> Any:
    try:
        return __import__(f"ai.{mod}", fromlist=[mod])
    except Exception:
        return __import__(f"agent.ai.{mod}", fromlist=[mod])


# Typed decision model used internally to be agnostic to RetryEngine concrete shape
@dataclass(frozen=True)
class RetryDecision:
    retryable: bool
    blocked: bool
    reason: str
    feedback: str


# Failure categories used for reporting and decisioning
class FailureCategory:
    INVALID_AI_JSON = "invalid-ai-json"
    MISSING_DELIVERABLES = "missing-deliverables"
    PYTHON_SYNTAX = "python-syntax-error"
    COMPILATION = "compilation-failure"
    VALIDATION = "validation-failure"
    UNITTEST_FAILURES = "unittest-failures"
    UNITTEST_ERRORS = "unittest-errors"

    SECURITY_POLICY = "security-policy"
    FORBIDDEN_CONTENT = "forbidden-content"
    UNSAFE_PATH = "unsafe-path"
    SECRET_EXPOSURE = "secret-exposure"
    DIRTY_REPOSITORY = "dirty-repository"
    GIT_INTEGRITY = "git-integrity"

    PROVIDER_AUTH = "provider-authentication"
    PROVIDER_AUTHZ = "provider-authorization"
    PROVIDER_BILLING = "provider-billing"
    PROVIDER_UNAVAILABLE = "provider-unavailable"

    INVALID_CONFIGURATION = "invalid-configuration"
    UNKNOWN = "unknown"


NON_RETRYABLE_IMMEDIATE_STOP: set[str] = {
    FailureCategory.SECURITY_POLICY,
    FailureCategory.FORBIDDEN_CONTENT,
    FailureCategory.UNSAFE_PATH,
    FailureCategory.SECRET_EXPOSURE,
    FailureCategory.DIRTY_REPOSITORY,
    FailureCategory.GIT_INTEGRITY,
    FailureCategory.PROVIDER_AUTH,
    FailureCategory.PROVIDER_AUTHZ,
    FailureCategory.PROVIDER_BILLING,
    FailureCategory.PROVIDER_UNAVAILABLE,
    FailureCategory.INVALID_CONFIGURATION,
}

# Retryable categories per requirements
RETRYABLE_CATEGORIES: set[str] = {
    FailureCategory.INVALID_AI_JSON,
    FailureCategory.MISSING_DELIVERABLES,
    FailureCategory.PYTHON_SYNTAX,
    FailureCategory.COMPILATION,
    FailureCategory.VALIDATION,
    FailureCategory.UNITTEST_FAILURES,
    FailureCategory.UNITTEST_ERRORS,
}


@dataclass
class FailureContext:
    category: str
    message: str
    attempt: int
    mission_name: str
    mission_text: str
    execution_plan: str
    allowlist: List[str]
    failed_tests: List[str] = field(default_factory=list)
    error_summary: str = ""


@dataclass
class AttemptLog:
    attempt: int
    category: Optional[str]
    decision: Optional[str]
    status: str


@dataclass
class RetryReport:
    mission_name: str
    attempts: int
    success: bool
    logs: List[AttemptLog]
    final_category: Optional[str]
    branch: Optional[str] = None


class MissionRunner:
    def __init__(
        self,
        repo_root: Optional[Path] = None,
        *,
        max_attempts: int = 3,
        retry_engine: Optional[Any] = None,
    ) -> None:
        if max_attempts < 1 or max_attempts > 5:
            raise ValueError("max_attempts must be between 1 and 5 inclusive")
        self.max_attempts = max_attempts
        self.repo_root: Path = Path(repo_root) if repo_root is not None else Path.cwd()
        self.repo_root = self.repo_root.resolve()

        # Lazy import to avoid hard dependency shape and enable testing fakes
        code_gen_mod = _import_ai_module("code_generator")
        prompt_mod = _import_ai_module("prompt_builder")
        validation_mod = _import_ai_module("validation_engine")
        patch_mod = _import_ai_module("patch_engine")
        review_mod = _import_ai_module("review_engine")
        retry_mod = _import_ai_module("retry_engine")

        # Instantiate components (tests can monkeypatch classes on these modules)
        self._CodeGenerator = getattr(code_gen_mod, "CodeGenerator")
        self._PromptBuilder = getattr(prompt_mod, "PromptBuilder")
        self._ValidationEngine = getattr(validation_mod, "ValidationEngine")
        self._PatchEngine = getattr(patch_mod, "PatchEngine")
        self._ReviewEngine = getattr(review_mod, "ReviewEngine")
        self._RetryEngineClass = getattr(retry_mod, "RetryEngine")

        self.code_generator = self._CodeGenerator()
        self.prompt_builder = self._PromptBuilder()
        self.validation_engine = self._ValidationEngine()
        self.patch_engine = self._PatchEngine()
        self.review_engine = self._ReviewEngine()
        self.retry_engine = retry_engine if retry_engine is not None else self._RetryEngineClass()

        # Track deliverables and originals for precise cleanup
        self._original_files: Dict[Path, Tuple[bytes, int]] = {}
        self._generated_last_attempt: List[Path] = []
        self._allowlist: List[str] = []

    # ========== Public API ==========
    def run(self, mission_name: str) -> RetryReport:
        logs: List[AttemptLog] = []
        mission_text, execution_plan, allowlist = self._prepare_mission(mission_name)
        self._allowlist = allowlist[:]  # copy exact deliverable allowlist

        # Keep all attempts on the same isolated mission branch (delegated to patch engine as needed)
        branch_name: Optional[str] = self._ensure_mission_branch(mission_name)

        # Preserve repository state knowledge prior to attempts
        base_repo_scan = self._rescan_repository()

        last_category: Optional[str] = None
        feedback: Optional[str] = None

        for attempt in range(1, self.max_attempts + 1):
            # Rescan before new generation attempt
            repo_scan = self._rescan_repository()
            if attempt > 1:
                self._cleanup_deliverables()  # atomic deterministic cleanup

            # Build prompt, include corrective feedback if present
            prompt = self._build_prompt(
                mission_text=mission_text,
                execution_plan=execution_plan,
                allowlist=allowlist,
                repo_scan=repo_scan,
                corrective_feedback=feedback,
            )

            # Generate candidate files JSON
            try:
                generated_json = self.code_generator.generate(prompt)
            except Exception as gen_exc:  # provider failures or config issues etc.
                category = self._map_exception_category(gen_exc)
                ctx = self._make_failure_context(
                    category=category,
                    message=self._safe_error_message(gen_exc),
                    attempt=attempt,
                    mission_name=mission_name,
                    mission_text=mission_text,
                    execution_plan=execution_plan,
                    allowlist=allowlist,
                    failed_tests=[],
                )
                decision = self._decide_retry(ctx)
                logs.append(AttemptLog(attempt=attempt, category=category, decision=self._decision_label(decision), status="failed"))

                if category in NON_RETRYABLE_IMMEDIATE_STOP or decision.blocked or not decision.retryable or attempt >= self.max_attempts:
                    return RetryReport(mission_name=mission_name, attempts=attempt, success=False, logs=logs, final_category=category, branch=branch_name)
                feedback = decision.feedback
                last_category = category
                continue

            # Parse JSON and validate deliverables
            try:
                payload = self._parse_json_payload(generated_json)
            except Exception as json_exc:
                category = FailureCategory.INVALID_AI_JSON
                ctx = self._make_failure_context(
                    category=category,
                    message=self._safe_error_message(json_exc),
                    attempt=attempt,
                    mission_name=mission_name,
                    mission_text=mission_text,
                    execution_plan=execution_plan,
                    allowlist=allowlist,
                    failed_tests=[],
                )
                decision = self._decide_retry(ctx)
                logs.append(AttemptLog(attempt=attempt, category=category, decision=self._decision_label(decision), status="failed"))
                if decision.blocked or not decision.retryable or attempt >= self.max_attempts:
                    return RetryReport(mission_name=mission_name, attempts=attempt, success=False, logs=logs, final_category=category, branch=branch_name)
                feedback = decision.feedback
                last_category = category
                continue

            try:
                # Validate and write deliverables to disk
                paths_written = self._write_deliverables(payload, allowlist)
                # Compile/validate/unit tests orchestrated by validation engine
                vresult = self._validate_repo(paths_written)
                if not vresult[0]:
                    category = vresult[1] or FailureCategory.UNKNOWN
                    failed_tests = vresult[2] or []
                    errsum = vresult[3] or ""
                    ctx = self._make_failure_context(
                        category=category,
                        message=errsum or f"Validation failure: {category}",
                        attempt=attempt,
                        mission_name=mission_name,
                        mission_text=mission_text,
                        execution_plan=execution_plan,
                        allowlist=allowlist,
                        failed_tests=failed_tests,
                    )
                    decision = self._decide_retry(ctx)
                    logs.append(AttemptLog(attempt=attempt, category=category, decision=self._decision_label(decision), status="failed"))
                    if category in NON_RETRYABLE_IMMEDIATE_STOP or decision.blocked or not decision.retryable or attempt >= self.max_attempts:
                        # Ensure cleanup before returning failure
                        self._cleanup_deliverables()
                        return RetryReport(mission_name=mission_name, attempts=attempt, success=False, logs=logs, final_category=category, branch=branch_name)
                    feedback = decision.feedback
                    last_category = category
                    continue
            except Exception as wexc:
                # Treat as compilation/validation generic failure
                category = FailureCategory.COMPILATION
                ctx = self._make_failure_context(
                    category=category,
                    message=self._safe_error_message(wexc),
                    attempt=attempt,
                    mission_name=mission_name,
                    mission_text=mission_text,
                    execution_plan=execution_plan,
                    allowlist=allowlist,
                    failed_tests=[],
                )
                decision = self._decide_retry(ctx)
                logs.append(AttemptLog(attempt=attempt, category=category, decision=self._decision_label(decision), status="failed"))
                if decision.blocked or not decision.retryable or attempt >= self.max_attempts:
                    self._cleanup_deliverables()
                    return RetryReport(mission_name=mission_name, attempts=attempt, success=False, logs=logs, final_category=category, branch=branch_name)
                feedback = decision.feedback
                last_category = category
                continue

            # All checks passed: commit and push
            self._commit_and_push(self._generated_last_attempt, mission_name, attempt)
            logs.append(AttemptLog(attempt=attempt, category=None, decision=None, status="success"))
            return RetryReport(mission_name=mission_name, attempts=attempt, success=True, logs=logs, final_category=None, branch=branch_name)

        # Exhausted attempts (should not reach due to early returns)
        return RetryReport(mission_name=mission_name, attempts=self.max_attempts, success=False, logs=logs, final_category=last_category, branch=None)

    # ========== Internal helpers ==========
    def _prepare_mission(self, mission_name: str) -> Tuple[str, str, List[str]]:
        # The PromptBuilder interface may vary across environments; support a few forms.
        # Expected to return (mission_text, execution_plan, allowlist)
        pb = self.prompt_builder
        # Try 'prepare' API first
        if hasattr(pb, "prepare"):
            spec = pb.prepare(mission_name, self.repo_root)
            mission_text = spec.get("mission_text") if isinstance(spec, dict) else getattr(spec, "mission_text", str(mission_name))
            execution_plan = spec.get("execution_plan") if isinstance(spec, dict) else getattr(spec, "execution_plan", "")
            allowlist = spec.get("allowlist") if isinstance(spec, dict) else getattr(spec, "allowlist", [])
            return str(mission_text or mission_name), str(execution_plan or ""), list(allowlist or [])
        # Try 'build'
        if hasattr(pb, "build"):
            built = pb.build(mission_name, self.repo_root)
            if isinstance(built, tuple) and len(built) == 3:
                mt, ep, al = built
                return str(mt or mission_name), str(ep or ""), list(al or [])
        # Fallback: Treat mission_name as mission text, empty plan, empty allowlist
        return str(mission_name), "", []

    def _rescan_repository(self) -> Dict[str, Any]:
        # Allow PromptBuilder or ValidationEngine to scan repo; ignore details
        scan: Dict[str, Any] = {}
        if hasattr(self.prompt_builder, "scan_repository"):
            try:
                scan = self.prompt_builder.scan_repository(self.repo_root) or {}
            except Exception:
                scan = {}
        return scan

    def _build_prompt(
        self,
        *,
        mission_text: str,
        execution_plan: str,
        allowlist: List[str],
        repo_scan: Dict[str, Any],
        corrective_feedback: Optional[str],
    ) -> str:
        # Always include original mission, plan, and allowlist.
        base: Dict[str, Any] = {
            "mission_text": mission_text,
            "execution_plan": execution_plan,
            "deliverable_allowlist": allowlist,
            "repo_scan": repo_scan,
        }
        if corrective_feedback:
            # Retry Prompt Requirements enforcement
            base["previous_failure_feedback"] = corrective_feedback
            base["constraints_reminder"] = (
                "All previous mission constraints still apply. Return the complete JSON files payload again."
            )
        # Prefer prompt builder if it knows how to build a string prompt
        if hasattr(self.prompt_builder, "build_prompt"):
            try:
                return str(self.prompt_builder.build_prompt(base))
            except Exception:
                pass
        # Default: JSON-encode the prompt object deterministically
        return json.dumps(base, sort_keys=True)

    def _parse_json_payload(self, generated_json: Any) -> Dict[str, Any]:
        if isinstance(generated_json, dict):
            payload = generated_json
        else:
            payload = json.loads(str(generated_json))
        if not isinstance(payload, dict):
            raise ValueError("Generated payload must be a JSON object")
        if "files" not in payload or not isinstance(payload["files"], list):
            raise ValueError("Generated payload must include a 'files' array")
        # Ensure shape is list of {path, content}
        for item in payload["files"]:
            if not isinstance(item, dict) or "path" not in item or "content" not in item:
                raise ValueError("Each file entry must include 'path' and 'content'")
        return payload

    def _normalize_and_validate_path(self, path_str: str) -> Path:
        # Absolute paths that resolve inside repo root are valid; normalize to repo-relative
        # Reject only those that resolve outside repo root
        p = Path(path_str)
        if not p.is_absolute():
            resolved = (self.repo_root / p).resolve()
        else:
            resolved = p.resolve()
        try:
            resolved.relative_to(self.repo_root)
        except Exception:
            raise ValueError(f"Absolute path outside repository root is not allowed: {path_str}")
        return resolved

    def _write_deliverables(self, payload: Dict[str, Any], allowlist: List[str]) -> List[Path]:
        # Build normalized allowlist set of repo-internal relative paths
        norm_allow: set[Path] = set()
        for entry in allowlist:
            norm_allow.add(self._normalize_and_validate_path(entry))
        files_spec: List[Dict[str, str]] = list(payload["files"])  # type: ignore[assignment]

        # Ensure only allowed files are touched and all required are present
        provided_paths: List[Path] = []
        for f in files_spec:
            rp = self._normalize_and_validate_path(str(f["path"]))
            provided_paths.append(rp)
            if norm_allow and rp not in norm_allow:
                raise ValueError(f"Generated path not in deliverable allowlist: {rp}")
        missing: List[Path] = []
        if norm_allow:
            for ap in norm_allow:
                if ap not in provided_paths:
                    missing.append(ap)
        if missing:
            raise RuntimeError(f"Missing required deliverables: {', '.join(str(m) for m in sorted(missing))}")

        # Before first write, capture originals for all allowlist entries
        if not self._original_files:
            for ap in (norm_allow or set(provided_paths)):
                if ap.exists():
                    b = ap.read_bytes()
                    st_mode = ap.stat().st_mode & 0o777
                    self._original_files[ap] = (b, st_mode)

        # Write files
        written: List[Path] = []
        for spec, rp in zip(files_spec, provided_paths):
            rp.parent.mkdir(parents=True, exist_ok=True)
            data = spec["content"].encode("utf-8") if isinstance(spec["content"], str) else bytes(spec["content"])  # type: ignore[arg-type]
            with open(rp, "wb") as f:
                f.write(data)
            # Preserve permissions: if file had original, set to that; else 0o644 default
            if rp in self._original_files:
                os.chmod(rp, self._original_files[rp][1])
            else:
                os.chmod(rp, 0o644)
            written.append(rp)
        self._generated_last_attempt = written
        return written

    def _validate_repo(self, changed_paths: List[Path]) -> Tuple[bool, Optional[str], Optional[List[str]], Optional[str]]:
        # Expected interface: validate(repo_root, changed_paths) -> result object or tuple
        ve = self.validation_engine
        res = None
        if hasattr(ve, "validate"):
            res = ve.validate(self.repo_root, changed_paths)
        elif hasattr(ve, "run"):
            res = ve.run(self.repo_root, changed_paths)
        else:
            # Default pass-through if no validator
            return True, None, None, None
        # Normalize result forms
        if isinstance(res, tuple):
            # (passed, category, failed_tests, error_summary)
            passed, category, failed_tests, error_summary = res + (None,) * (4 - len(res))  # type: ignore[operator]
            return bool(passed), category, failed_tests, error_summary
        if isinstance(res, dict):
            return bool(res.get("passed", False)), res.get("category"), res.get("failed_tests"), res.get("error_summary")
        # Object with attributes
        passed = bool(getattr(res, "passed", False))
        category = getattr(res, "category", None)
        failed_tests = getattr(res, "failed_tests", None)
        error_summary = getattr(res, "error_summary", None)
        return passed, category, failed_tests, error_summary

    def _commit_and_push(self, changed_paths: List[Path], mission_name: str, attempt: int) -> None:
        # Only commit after all validations pass
        message = f"Mission {mission_name}: deliverables after attempt {attempt}"
        if hasattr(self.patch_engine, "stage_and_commit"):
            self.patch_engine.stage_and_commit([str(p.relative_to(self.repo_root)) for p in changed_paths], message)
        elif hasattr(self.patch_engine, "commit"):
            self.patch_engine.commit([str(p) for p in changed_paths], message)
        if hasattr(self.patch_engine, "push"):
            self.patch_engine.push()

    def _cleanup_deliverables(self) -> None:
        # Deterministic cleanup affecting only the exact mission deliverables
        # - If a deliverable existed before the mission, restore its original bytes and permissions
        # - If a deliverable was new, remove it
        # - Never touch non-allowlist files
        targets = set(self._generated_last_attempt)
        for p in sorted(targets):
            try:
                if p in self._original_files:
                    # Restore original content and mode
                    data, mode = self._original_files[p]
                    p.parent.mkdir(parents=True, exist_ok=True)
                    with open(p, "wb") as f:
                        f.write(data)
                    os.chmod(p, mode)
                else:
                    if p.exists():
                        p.unlink()
            except Exception:
                # Cleanup must be deterministic; on error, continue to next to avoid partial state
                raise
        # Reset last attempt record
        self._generated_last_attempt = []

    def _make_failure_context(
        self,
        *,
        category: str,
        message: str,
        attempt: int,
        mission_name: str,
        mission_text: str,
        execution_plan: str,
        allowlist: List[str],
        failed_tests: List[str],
    ) -> FailureContext:
        summary = self._redact_and_limit(message)
        return FailureContext(
            category=category,
            message=message,
            attempt=attempt,
            mission_name=mission_name,
            mission_text=mission_text,
            execution_plan=execution_plan,
            allowlist=allowlist[:],
            failed_tests=failed_tests[:],
            error_summary=summary,
        )

    def _decide_retry(self, ctx: FailureContext) -> RetryDecision:
        # Ask RetryEngine whether retryable; support various interfaces
        re = self.retry_engine
        fb = ""
        retryable = ctx.category in RETRYABLE_CATEGORIES
        blocked = ctx.category in NON_RETRYABLE_IMMEDIATE_STOP
        reason = ctx.category
        # If retry engine provides decision method that returns decision+feedback
        if hasattr(re, "decide"):
            d = re.decide(ctx)  # type: ignore[call-arg]
            # Normalize
            retryable = bool(getattr(d, "retryable", retryable))
            blocked = bool(getattr(d, "blocked", blocked))
            fb = str(getattr(d, "feedback", fb) or "")
            reason = str(getattr(d, "reason", reason) or reason)
        elif hasattr(re, "is_retryable"):
            try:
                is_ret = re.is_retryable(ctx)  # type: ignore[call-arg]
                if isinstance(is_ret, tuple):
                    retryable, blocked, fb = bool(is_ret[0]), bool(is_ret[1]), str(is_ret[2] or "")
                else:
                    retryable = bool(getattr(is_ret, "retryable", retryable))
                    blocked = bool(getattr(is_ret, "blocked", blocked))
                    fb = str(getattr(is_ret, "feedback", fb) or "")
            except Exception:
                pass
        # Always build corrective feedback if engine offers it, and include retry prompt requirements
        if hasattr(re, "build_feedback"):
            try:
                built = re.build_feedback(ctx)  # type: ignore[call-arg]
                if built:
                    fb = str(built)
            except Exception:
                pass
        # Ensure retry feedback includes mandatory elements
        fb = self._augment_feedback_with_requirements(ctx, fb)
        return RetryDecision(retryable=retryable, blocked=blocked, reason=reason, feedback=fb)

    def _augment_feedback_with_requirements(self, ctx: FailureContext, fb: str) -> str:
        # Construct a deterministic instruction block satisfying retry prompt requirements
        parts: List[str] = []
        parts.append("Original mission text:\n" + ctx.mission_text)
        parts.append("Original execution plan:\n" + ctx.execution_plan)
        parts.append("Exact deliverable allowlist:\n" + json.dumps(ctx.allowlist, sort_keys=True))
        parts.append("Previous failure category:\n" + ctx.category)
        parts.append("Redacted error summary (size-limited):\n" + self._redact_and_limit(ctx.error_summary))
        if ctx.failed_tests:
            parts.append("Failed test names:\n" + ", ".join(sorted(ctx.failed_tests)))
        else:
            parts.append("Failed test names:\nNone available")
        parts.append(
            "Corrective instructions:\nFocus only on fixing the specific causes of the failure. Keep paths exactly in the deliverable allowlist."
        )
        parts.append("All previous mission constraints still apply.")
        parts.append("Return the complete JSON files payload again in the same format with all deliverables.")
        if fb:
            parts.append("Additional engine feedback:\n" + fb)
        return "\n\n".join(parts)

    def _map_exception_category(self, exc: Exception) -> str:
        # External providers and config errors should stop immediately
        # If an exception exposes a 'category' attribute, use it
        cat = getattr(exc, "category", None)
        if isinstance(cat, str) and cat:
            return cat
        name = exc.__class__.__name__.lower()
        if "auth" in name and "provider" in name:
            return FailureCategory.PROVIDER_AUTH
        if "quota" in name or "billing" in name:
            return FailureCategory.PROVIDER_BILLING
        if "unavailable" in name or "timeout" in name:
            return FailureCategory.PROVIDER_UNAVAILABLE
        if "configuration" in name or "config" in name:
            return FailureCategory.INVALID_CONFIGURATION
        return FailureCategory.UNKNOWN

    def _redact_and_limit(self, text: str, limit: int = 4096) -> str:
        if not text:
            return ""
        # Simple redaction of lines that may contain secrets or credentials
        redacted_lines: List[str] = []
        markers = ("key=", "token=", "password=", "secret=", "authorization:", "bearer ")
        for raw_line in str(text).splitlines():
            line = raw_line
            low = line.lower()
            for mk in markers:
                if mk in low:
                    # Remove value after marker
                    idx = low.find(mk)
                    prefix = line[: idx + len(mk)]
                    line = prefix + "[REDACTED]"
                    break
            redacted_lines.append(line)
        out = "\n".join(redacted_lines)
        if len(out) > limit:
            return out[:limit]
        return out

    def _safe_error_message(self, exc: Exception) -> str:
        tb = "".join(traceback.format_exception_only(exc.__class__, exc)).strip()
        return tb

    def _decision_label(self, d: RetryDecision) -> str:
        if d.blocked:
            return "blocked"
        return "retry" if d.retryable else "stop"

    def _ensure_mission_branch(self, mission_name: str) -> Optional[str]:
        # Keep compatibility; if patch engine supports branch isolation, use it
        pe = self.patch_engine
        branch_name = f"mission/{mission_name}"
        created = False
        try:
            if hasattr(pe, "ensure_branch"):
                pe.ensure_branch(branch_name)
                created = True
            elif hasattr(pe, "create_branch"):
                pe.create_branch(branch_name)
                created = True
        except Exception:
            # If branch operations fail, proceed without changing branches (do not modify working tree)
            return None
        return branch_name if created else None


# ========== CLI support ==========

def _parse_args(argv: Optional[Sequence[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mission Runner with Automatic Retry Engine")
    parser.add_argument("mission_name", help="Name of the mission to run")
    parser.add_argument("--max-attempts", type=int, default=3, help="Maximum retry attempts (1-5). Default: 3")
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.max_attempts < 1:
        raise SystemExit("--max-attempts must be at least 1")
    if args.max_attempts > 5:
        raise SystemExit("--max-attempts must be at most 5")
    return args


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)
    runner = MissionRunner(max_attempts=args.max_attempts)
    report = runner.run(args.mission_name)
    # Deterministic final retry report printing (stdout)
    final = {
        "mission_name": report.mission_name,
        "attempts": report.attempts,
        "success": report.success,
        "final_category": report.final_category,
        "logs": [
            {"attempt": l.attempt, "category": l.category, "decision": l.decision, "status": l.status}
            for l in report.logs
        ],
    }
    sys.stdout.write(json.dumps(final, sort_keys=True) + "\n")
    return 0 if report.success else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
