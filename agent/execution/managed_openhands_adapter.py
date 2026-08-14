from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from agent.execution.external_openhands_runner import (
    ExternalOpenHandsRunner,
    ManagedOpenHandsProcessError,
)
from agent.execution.openhands_adapter import OpenHandsRuntimeAdapter
from agent.execution.runtime_adapter import (
    ExecutionEvidence,
    ExecutionRequest,
    ExecutionResult,
    RuntimeCapabilities,
    RuntimeStatus,
)


class ManagedOpenHandsRuntimeAdapter(OpenHandsRuntimeAdapter):
    """OpenHands adapter backed by MITIGATE's independently managed SDK venv."""

    def __init__(self, *, repository_root: str | Path) -> None:
        self._managed_runner = ExternalOpenHandsRunner(
            repository_root=repository_root,
        )
        super().__init__(runner=self._managed_runner)

    def healthcheck(self) -> Mapping[str, Any]:
        return {
            "available": self._managed_runner.available(),
            "mode": "managed-external-venv",
            "python": str(self._managed_runner.python_path),
            "runner_script": str(self._managed_runner.runner_script),
        }

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        try:
            workspace = self._validated_workspace(request)
        except ValueError as exc:
            return ExecutionResult(
                status=RuntimeStatus.blocked,
                provider=self.name,
                retryable=False,
                reason=str(exc),
            )

        try:
            raw = self._managed_runner(request=request, workspace=workspace)
        except TimeoutError:
            return self._managed_failure(
                RuntimeStatus.timed_out,
                "openhands_timeout",
                retryable=True,
            )
        except ManagedOpenHandsProcessError as exc:
            code = exc.code
            if code == "openhands_llm_quota_exhausted":
                status = RuntimeStatus.blocked
                retryable = False
            elif code == "openhands_llm_credentials_unavailable":
                status = RuntimeStatus.blocked
                retryable = False
            elif code in {
                "managed_openhands_runtime_unavailable",
                "managed_openhands_process_start_failed",
            }:
                status = RuntimeStatus.unavailable
                retryable = True
            elif code in {
                "managed_openhands_runtime_incompatible",
                "managed_openhands_permission_denied",
                "managed_openhands_refuses_canonical_workspace",
                "managed_openhands_workspace_unavailable",
            }:
                status = RuntimeStatus.failed
                retryable = False
            else:
                status = RuntimeStatus.failed
                retryable = True
            return self._managed_failure(
                status,
                code,
                retryable=retryable,
                metadata=exc.evidence(),
            )
        except Exception as exc:
            return self._managed_failure(
                RuntimeStatus.failed,
                "managed_openhands_adapter_exception:" + type(exc).__name__,
                retryable=True,
                metadata={"exception_type": type(exc).__name__},
            )

        changed_files = self._changed_files(workspace, request.base_revision)
        violations = self._scope_violations(request, changed_files)
        if violations:
            return ExecutionResult(
                status=RuntimeStatus.blocked,
                provider=self.name,
                retryable=False,
                reason="runtime_changed_paths_outside_authorized_scope",
                evidence=ExecutionEvidence(
                    summary="OpenHands produced changes outside MITIGATE-authorized scope.",
                    diagnostics=tuple(
                        f"scope_violation:{path}" for path in violations
                    ),
                    changed_files=changed_files,
                    provider_run_id=self._provider_run_id(raw),
                    provider_metadata={
                        "runtime": "openhands",
                        "mode": "managed",
                        **dict(getattr(raw, "provider_metadata", {}) or {}),
                    },
                ),
            )

        return ExecutionResult(
            status=RuntimeStatus.succeeded,
            provider=self.name,
            retryable=False,
            evidence=ExecutionEvidence(
                summary="OpenHands completed governed execution in a disposable worktree.",
                changed_files=changed_files,
                provider_run_id=self._provider_run_id(raw),
                provider_metadata={
                    "runtime": "openhands",
                    "mode": "managed",
                    **dict(getattr(raw, "provider_metadata", {}) or {}),
                },
            ),
        )

    def _managed_failure(
        self,
        status: RuntimeStatus,
        reason: str,
        *,
        retryable: bool,
        metadata: Mapping[str, Any] | None = None,
    ) -> ExecutionResult:
        return ExecutionResult(
            status=status,
            provider=self.name,
            retryable=retryable,
            reason=reason[:1000],
            evidence=ExecutionEvidence(
                diagnostics=(f"managed_openhands_failure:{reason[:500]}",),
                provider_metadata={
                    "runtime": "openhands",
                    "mode": "managed",
                    **dict(metadata or {}),
                },
            ),
        )


__all__ = ["ManagedOpenHandsRuntimeAdapter"]
