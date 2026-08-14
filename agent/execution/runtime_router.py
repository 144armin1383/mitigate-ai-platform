from __future__ import annotations

from dataclasses import replace
from typing import Any, Sequence

from agent.execution.runtime_adapter import (
    ExecutionEvidence,
    ExecutionRequest,
    ExecutionResult,
    RuntimeCapabilities,
    RuntimeRegistry,
    RuntimeStatus,
)
from agent.execution.workspace_manager import DisposableWorkspaceManager, WorkspaceError


class RuntimeRouter:
    """Route MITIGATE tasks to replaceable runtimes inside disposable workspaces.

    Provider failover is owned here, not by mission controllers. Every provider
    attempt receives a newly allocated disposable workspace. Failover is only
    allowed for provider/runtime integration failures; policy, quota,
    credentials and scope failures remain terminal and are never bypassed.
    """

    _FAILOVER_REASON_MARKERS = (
        "runtime_incompatible",
        "runtime_unavailable",
        "process_start_failed",
        "workspace_unavailable",
        "runtime_adapter_exception",
        "agent_exec_failed",
        "connection",
        "network",
    )
    _NO_FAILOVER_REASON_MARKERS = (
        "quota_exhausted",
        "insufficient_quota",
        "credentials_unavailable",
        "permission_denied",
        "refuses_canonical_workspace",
        "changed_paths_outside_authorized_scope",
        "canonical_repository_not_clean",
        "approval",
    )

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

    @classmethod
    def _can_failover(cls, result: ExecutionResult) -> bool:
        reason = str(result.reason or "").lower()
        if result.status == RuntimeStatus.blocked:
            return False
        if any(marker in reason for marker in cls._NO_FAILOVER_REASON_MARKERS):
            return False
        if result.status == RuntimeStatus.unavailable:
            return True
        return any(marker in reason for marker in cls._FAILOVER_REASON_MARKERS)

    @staticmethod
    def _capability_satisfied(
        adapter: Any,
        require: RuntimeCapabilities,
    ) -> bool:
        caps = adapter.capabilities()
        required_fields = (
            "coding",
            "terminal",
            "file_editing",
            "tests",
            "browser",
            "mcp",
            "skills",
            "multi_agent",
            "persistent_sessions",
            "isolated_workspace",
            "remote_execution",
        )
        return not any(
            getattr(require, field_name)
            and not getattr(caps, field_name)
            for field_name in required_fields
        )

    def _candidate_names(self, preferred: Sequence[str]) -> tuple[str, ...]:
        ordered = [
            *(str(name).strip().lower() for name in preferred),
            *self.registry.names(),
        ]
        result: list[str] = []
        for name in ordered:
            if name and name not in result:
                result.append(name)
        return tuple(result)

    @staticmethod
    def _attempt_record(
        *,
        provider: str,
        health: dict[str, Any] | None = None,
        result: ExecutionResult | None = None,
        skipped_reason: str | None = None,
    ) -> dict[str, Any]:
        record: dict[str, Any] = {"provider": provider}
        if health is not None:
            record["health"] = {
                str(key): value
                for key, value in list(health.items())[:20]
                if isinstance(value, (str, int, float, bool)) or value is None
            }
        if skipped_reason:
            record["skipped_reason"] = skipped_reason
        if result is not None:
            record.update({
                "status": result.status.value,
                "reason": result.reason,
                "retryable": bool(result.retryable),
                "provider_metadata": dict(result.evidence.provider_metadata or {}),
            })
        return record

    @staticmethod
    def _attach_attempts(
        result: ExecutionResult,
        attempts: list[dict[str, Any]],
    ) -> ExecutionResult:
        metadata = dict(result.evidence.provider_metadata or {})
        metadata["provider_attempts"] = attempts[:10]
        evidence = replace(result.evidence, provider_metadata=metadata)
        return replace(result, evidence=evidence)

    def _execute_one(
        self,
        *,
        adapter: Any,
        request: ExecutionRequest,
    ) -> ExecutionResult:
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

        return result

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

        attempts: list[dict[str, Any]] = []
        executable_candidates = 0
        last_result: ExecutionResult | None = None

        for name in self._candidate_names(preferred):
            try:
                adapter = self.registry.get(name)
            except KeyError:
                continue

            if not self._capability_satisfied(adapter, require):
                attempts.append(self._attempt_record(
                    provider=name,
                    skipped_reason="required_capabilities_not_satisfied",
                ))
                continue

            try:
                health_raw = adapter.healthcheck()
                health = dict(health_raw) if health_raw is not None else {}
            except Exception as exc:
                attempts.append(self._attempt_record(
                    provider=name,
                    health={"available": False},
                    skipped_reason=f"healthcheck_exception:{type(exc).__name__}",
                ))
                continue

            if not bool(health.get("available", False)):
                attempts.append(self._attempt_record(
                    provider=name,
                    health=health,
                    skipped_reason=str(health.get("reason") or "provider_unhealthy"),
                ))
                continue

            executable_candidates += 1
            result = self._execute_one(adapter=adapter, request=request)
            last_result = result
            attempts.append(self._attempt_record(
                provider=name,
                health=health,
                result=result,
            ))

            if not self.workspace_manager.canonical_is_clean():
                protected = ExecutionResult(
                    status=RuntimeStatus.blocked,
                    provider=adapter.name,
                    retryable=False,
                    reason="canonical_repository_changed_during_external_execution",
                    evidence=result.evidence,
                )
                return self._attach_attempts(protected, attempts)

            if result.status == RuntimeStatus.succeeded:
                return self._attach_attempts(result, attempts)

            if not self._can_failover(result):
                return self._attach_attempts(result, attempts)

        if last_result is not None:
            return self._attach_attempts(last_result, attempts)

        unavailable = ExecutionResult(
            status=RuntimeStatus.unavailable,
            provider="mitigate-router",
            retryable=True,
            reason=(
                "no_healthy_runtime_available"
                if executable_candidates == 0
                else "runtime_provider_failover_exhausted"
            ),
            evidence=ExecutionEvidence(),
        )
        return self._attach_attempts(unavailable, attempts)


__all__ = ["RuntimeRouter"]
