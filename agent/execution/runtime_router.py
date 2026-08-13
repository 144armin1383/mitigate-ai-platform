from __future__ import annotations

from dataclasses import replace
from typing import Any, Sequence

from agent.execution.runtime_adapter import (
    ExecutionRequest,
    ExecutionResult,
    RuntimeCapabilities,
    RuntimeRegistry,
    RuntimeStatus,
)
from agent.execution.workspace_manager import DisposableWorkspaceManager, WorkspaceError


class RuntimeRouter:
    """Route MITIGATE tasks to replaceable runtimes inside disposable workspaces."""

    def __init__(
        self,
        registry: RuntimeRegistry,
        workspace_manager: DisposableWorkspaceManager,
        *,
        publisher: Any | None = None,
    ) -> None:
        self.registry = registry
        self.workspace_manager = workspace_manager
        self.publisher = publisher

    def execute(
        self,
        request: ExecutionRequest,
        *,
        require: RuntimeCapabilities,
        preferred: Sequence[str] = (),
    ) -> ExecutionResult:
        if not self.workspace_manager.canonical_is_clean():
            return ExecutionResult(
                status=RuntimeStatus.blocked,
                provider="mitigate-router",
                retryable=False,
                reason="canonical_repository_not_clean",
            )

        try:
            adapter = self.registry.choose(require=require, preferred=preferred)
        except LookupError:
            return ExecutionResult(
                status=RuntimeStatus.unavailable,
                provider="mitigate-router",
                retryable=True,
                reason="no_healthy_runtime_available",
            )

        try:
            workspace = self.workspace_manager.create(
                mission_id=request.mission_id,
                base_revision=request.base_revision,
            )
        except WorkspaceError as exc:
            return ExecutionResult(
                status=RuntimeStatus.failed,
                provider="mitigate-router",
                retryable=True,
                reason=str(exc),
            )

        routed_request = replace(
            request,
            metadata={
                **dict(request.metadata),
                "workspace_root": str(workspace.path),
                "runtime_provider": adapter.name,
            },
        )

        try:
            result = adapter.execute(routed_request)

            if (
                self.publisher is not None
                and result.status == RuntimeStatus.succeeded
                and result.evidence.changed_files
            ):
                result = self.publisher.publish(
                    workspace=workspace,
                    request=routed_request,
                    result=result,
                )

        except Exception as exc:
            result = ExecutionResult(
                status=RuntimeStatus.failed,
                provider=adapter.name,
                retryable=True,
                reason=f"runtime_adapter_exception:{type(exc).__name__}",
            )
        finally:
            try:
                self.workspace_manager.remove(workspace)
            except WorkspaceError:
                if "result" in locals() and result.status == RuntimeStatus.succeeded:
                    result = ExecutionResult(
                        status=RuntimeStatus.failed,
                        provider=adapter.name,
                        retryable=True,
                        reason="disposable_workspace_cleanup_failed",
                        evidence=result.evidence,
                    )

        if not self.workspace_manager.canonical_is_clean():
            return ExecutionResult(
                status=RuntimeStatus.blocked,
                provider=adapter.name,
                retryable=False,
                reason="canonical_repository_changed_during_external_execution",
                evidence=result.evidence,
            )

        return result


__all__ = ["RuntimeRouter"]
