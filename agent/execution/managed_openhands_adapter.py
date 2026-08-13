from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from agent.execution.external_openhands_runner import ExternalOpenHandsRunner
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
        except Exception as exc:
            detail = str(exc).strip()[:1000]
            lowered = detail.lower()
            if "quota_exhausted" in lowered or "insufficient_quota" in lowered:
                return self._managed_failure(
                    RuntimeStatus.blocked,
                    "openhands_llm_quota_exhausted",
                    retryable=False,
                )
            if "credentials_unavailable" in lowered:
                return self._managed_failure(
                    RuntimeStatus.blocked,
                    "openhands_llm_credentials_unavailable",
                    retryable=False,
                )
            if "python_unavailable" in lowered or "runtime_unavailable" in lowered:
                return self._managed_failure(
                    RuntimeStatus.unavailable,
                    "managed_openhands_runtime_unavailable",
                    retryable=True,
                )
            return self._managed_failure(
                RuntimeStatus.failed,
                "managed_openhands_execution_failed:" + detail,
                retryable=True,
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
                    provider_metadata={"runtime": "openhands", "mode": "managed"},
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
                provider_metadata={"runtime": "openhands", "mode": "managed"},
            ),
        )

    def _managed_failure(
        self,
        status: RuntimeStatus,
        reason: str,
        *,
        retryable: bool,
    ) -> ExecutionResult:
        return ExecutionResult(
            status=status,
            provider=self.name,
            retryable=retryable,
            reason=reason[:1000],
            evidence=ExecutionEvidence(
                provider_metadata={"runtime": "openhands", "mode": "managed"}
            ),
        )


__all__ = ["ManagedOpenHandsRuntimeAdapter"]
