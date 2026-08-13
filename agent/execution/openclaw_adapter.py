from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any, Mapping

from agent.execution.runtime_adapter import (
    ExecutionEvidence,
    ExecutionRequest,
    ExecutionResult,
    RuntimeCapabilities,
    RuntimeStatus,
)


class OpenClawRuntimeAdapter:
    """OpenClaw capability provider behind the MITIGATE runtime contract.

    OpenClaw is used for skills, typed tools, MCP, sessions and selected
    integrations. MITIGATE remains authoritative for mission state, policy,
    approvals, canonical project memory and Git history.
    """

    def __init__(self, *, runner: Any | None = None, binary: str = "openclaw") -> None:
        self._runner = runner
        self._binary = binary

    @property
    def name(self) -> str:
        return "openclaw"

    def capabilities(self) -> RuntimeCapabilities:
        return RuntimeCapabilities(
            terminal=True,
            file_editing=True,
            browser=True,
            mcp=True,
            skills=True,
            persistent_sessions=True,
            isolated_workspace=True,
            remote_execution=True,
        )

    def healthcheck(self) -> Mapping[str, Any]:
        if self._runner is not None:
            return {"available": True, "mode": "injected"}

        binary = shutil.which(self._binary)
        if not binary:
            return {
                "available": False,
                "mode": "cli",
                "reason": "openclaw_binary_not_found",
            }

        probe = subprocess.run(
            [binary, "--version"],
            text=True,
            capture_output=True,
            check=False,
            timeout=15,
        )
        return {
            "available": probe.returncode == 0,
            "mode": "cli",
            "binary": binary,
            "version": (probe.stdout or probe.stderr).strip()[:200],
        }

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        if not bool(request.metadata.get("openclaw_capability_task", False)):
            return ExecutionResult(
                status=RuntimeStatus.blocked,
                provider=self.name,
                reason="openclaw_requires_explicit_capability_task",
                retryable=False,
            )

        try:
            if self._runner is not None:
                raw = self._runner(request=request)
            else:
                raw = self._run_mcp_probe(request)
        except subprocess.TimeoutExpired:
            return self._failure(RuntimeStatus.timed_out, "openclaw_timeout", True)
        except Exception as exc:
            return self._failure(
                RuntimeStatus.failed,
                f"openclaw_execution_failed:{type(exc).__name__}",
                True,
            )

        metadata = self._normalize_metadata(raw)
        return ExecutionResult(
            status=RuntimeStatus.succeeded,
            provider=self.name,
            retryable=False,
            evidence=ExecutionEvidence(
                summary="OpenClaw capability task completed behind the MITIGATE adapter boundary.",
                provider_run_id=self._provider_run_id(raw),
                provider_metadata=metadata,
            ),
        )

    def cancel(self, provider_run_id: str) -> bool:
        del provider_run_id
        return False

    def _run_mcp_probe(self, request: ExecutionRequest) -> subprocess.CompletedProcess[str]:
        binary = shutil.which(self._binary)
        if not binary:
            raise RuntimeError("openclaw_binary_not_found")

        action = str(request.metadata.get("openclaw_action") or "mcp_status")
        if action != "mcp_status":
            raise ValueError("unsupported_openclaw_action")

        return subprocess.run(
            [binary, "mcp", "status", "--json"],
            text=True,
            capture_output=True,
            check=True,
            timeout=min(request.timeout_seconds, 60),
        )

    @staticmethod
    def _provider_run_id(raw: Any) -> str | None:
        value = getattr(raw, "id", None) or getattr(raw, "session_id", None)
        return str(value) if value is not None else None

    @staticmethod
    def _normalize_metadata(raw: Any) -> Mapping[str, Any]:
        stdout = getattr(raw, "stdout", None)
        if isinstance(stdout, str) and stdout.strip():
            try:
                parsed = json.loads(stdout)
                if isinstance(parsed, dict):
                    return {"runtime": "openclaw", "response": parsed}
            except ValueError:
                return {"runtime": "openclaw", "stdout": stdout[:1000]}
        return {"runtime": "openclaw"}

    def _failure(self, status: RuntimeStatus, reason: str, retryable: bool) -> ExecutionResult:
        return ExecutionResult(
            status=status,
            provider=self.name,
            retryable=retryable,
            reason=reason[:500],
            evidence=ExecutionEvidence(provider_metadata={"runtime": "openclaw"}),
        )


__all__ = ["OpenClawRuntimeAdapter"]
