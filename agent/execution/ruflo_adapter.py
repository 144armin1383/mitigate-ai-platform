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


class RufloRuntimeAdapter:
    """Benchmark-gated Ruflo provider.

    Ruflo is optional. It may provide swarm, memory and coordination value, but
    it cannot own MITIGATE mission state, policy, approvals or canonical memory.
    """

    def __init__(self, *, runner: Any | None = None, binary: str = "ruflo") -> None:
        self._runner = runner
        self._binary = binary

    @property
    def name(self) -> str:
        return "ruflo"

    def capabilities(self) -> RuntimeCapabilities:
        return RuntimeCapabilities(
            mcp=True,
            skills=True,
            multi_agent=True,
            persistent_sessions=True,
            remote_execution=True,
        )

    def healthcheck(self) -> Mapping[str, Any]:
        if self._runner is not None:
            return {"available": True, "mode": "injected"}

        binary = shutil.which(self._binary)
        if not binary:
            return {"available": False, "mode": "cli", "reason": "ruflo_binary_not_found"}

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
        if not bool(request.metadata.get("benchmark_mode", False)):
            return ExecutionResult(
                status=RuntimeStatus.blocked,
                provider=self.name,
                retryable=False,
                reason="ruflo_is_benchmark_gated",
            )

        try:
            raw = (
                self._runner(request=request)
                if self._runner is not None
                else self._run_benchmark_probe(request)
            )
        except subprocess.TimeoutExpired:
            return self._failure(RuntimeStatus.timed_out, "ruflo_timeout", True)
        except Exception as exc:
            return self._failure(
                RuntimeStatus.failed,
                f"ruflo_execution_failed:{type(exc).__name__}",
                True,
            )

        return ExecutionResult(
            status=RuntimeStatus.succeeded,
            provider=self.name,
            retryable=False,
            evidence=ExecutionEvidence(
                summary="Ruflo benchmark task completed without transferring MITIGATE authority.",
                provider_run_id=self._provider_run_id(raw),
                provider_metadata=self._metadata(raw),
            ),
        )

    def cancel(self, provider_run_id: str) -> bool:
        del provider_run_id
        return False

    def _run_benchmark_probe(self, request: ExecutionRequest) -> subprocess.CompletedProcess[str]:
        binary = shutil.which(self._binary)
        if not binary:
            raise RuntimeError("ruflo_binary_not_found")
        return subprocess.run(
            [binary, "doctor", "--json"],
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
    def _metadata(raw: Any) -> Mapping[str, Any]:
        stdout = getattr(raw, "stdout", None)
        if isinstance(stdout, str) and stdout.strip():
            try:
                parsed = json.loads(stdout)
                if isinstance(parsed, dict):
                    return {"runtime": "ruflo", "response": parsed}
            except ValueError:
                return {"runtime": "ruflo", "stdout": stdout[:1000]}
        return {"runtime": "ruflo"}

    def _failure(self, status: RuntimeStatus, reason: str, retryable: bool) -> ExecutionResult:
        return ExecutionResult(
            status=status,
            provider=self.name,
            retryable=retryable,
            reason=reason[:500],
            evidence=ExecutionEvidence(provider_metadata={"runtime": "ruflo"}),
        )


__all__ = ["RufloRuntimeAdapter"]
