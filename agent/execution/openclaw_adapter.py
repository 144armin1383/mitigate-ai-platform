from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Mapping

from agent.execution.runtime_adapter import (
    ExecutionEvidence,
    ExecutionRequest,
    ExecutionResult,
    RuntimeCapabilities,
    RuntimeStatus,
)
from agent.runtime.provider_secret_store import load_provider_secret


class OpenClawRuntimeAdapter:
    """OpenClaw capability and coding provider behind the MITIGATE contract.

    MITIGATE remains authoritative for mission state, policy, approvals,
    disposable workspace allocation, publication, project memory and canonical
    Git history. For governed software work OpenClaw is invoked through its
    documented headless ``agent exec`` entry point and is restricted to the
    MITIGATE-provided disposable workspace via ``--cwd``.
    """

    def __init__(self, *, runner: Any | None = None, binary: str = "openclaw") -> None:
        self._runner = runner
        self._binary = binary

    @property
    def name(self) -> str:
        return "openclaw"

    def capabilities(self) -> RuntimeCapabilities:
        return RuntimeCapabilities(
            coding=True,
            terminal=True,
            file_editing=True,
            tests=True,
            browser=True,
            mcp=True,
            skills=True,
            persistent_sessions=True,
            isolated_workspace=True,
            remote_execution=True,
        )

    def _binary_path(self) -> str | None:
        configured = str(self._binary or "").strip()
        if not configured:
            return None
        if os.path.isabs(configured):
            path = Path(configured)
            return str(path) if path.is_file() and os.access(path, os.X_OK) else None
        return shutil.which(configured)

    def healthcheck(self) -> Mapping[str, Any]:
        if self._runner is not None:
            return {"available": True, "mode": "injected"}

        binary = self._binary_path()
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
        managed = load_provider_secret("opencode")
        return {
            "available": probe.returncode == 0,
            "mode": "cli",
            "binary": binary,
            "version": (probe.stdout or probe.stderr).strip()[:200],
            "managed_llm_provider": "opencode" if managed else None,
            "managed_llm_model": str(managed.get("model") or "") if managed else None,
        }

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        capability_task = bool(request.metadata.get("openclaw_capability_task", False))
        try:
            if self._runner is not None:
                raw = self._runner(request=request)
                if capability_task:
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
                return self._normalize_injected_coding_result(raw, request)

            if capability_task:
                raw = self._run_mcp_probe(request)
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
            return self._run_agent_exec(request)
        except subprocess.TimeoutExpired:
            return self._failure(RuntimeStatus.timed_out, "openclaw_timeout", True)
        except Exception as exc:
            return self._failure(
                RuntimeStatus.failed,
                f"openclaw_execution_failed:{type(exc).__name__}",
                True,
            )

    def cancel(self, provider_run_id: str) -> bool:
        del provider_run_id
        return False

    def _run_mcp_probe(self, request: ExecutionRequest) -> subprocess.CompletedProcess[str]:
        binary = self._binary_path()
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
    def _managed_opencode_exec_config() -> tuple[str | None, dict[str, str]]:
        secret = load_provider_secret("opencode")
        model = str(secret.get("model") or "").strip()
        api_key = str(secret.get("api_key") or "").strip()
        if not model or not api_key or not model.startswith("opencode/"):
            return None, {}
        return model, {"OPENCODE_API_KEY": api_key, "OPENCODE_ZEN_API_KEY": api_key}

    def _run_agent_exec(self, request: ExecutionRequest) -> ExecutionResult:
        binary = self._binary_path()
        if not binary:
            return self._failure(RuntimeStatus.unavailable, "openclaw_binary_not_found", True)

        workspace_raw = str(request.metadata.get("workspace_root") or "").strip()
        if not workspace_raw:
            return self._failure(RuntimeStatus.blocked, "openclaw_workspace_required", False)
        workspace = Path(workspace_raw).expanduser().resolve()
        canonical = Path(request.repository_root).expanduser().resolve()
        if not workspace.is_dir():
            return self._failure(RuntimeStatus.blocked, "openclaw_workspace_unavailable", False)
        if workspace == canonical:
            return self._failure(RuntimeStatus.blocked, "openclaw_refuses_canonical_workspace", False)

        prompt = self._coding_prompt(request)
        managed_model, managed_env = self._managed_opencode_exec_config()
        command = [
            binary,
            "agent",
            "exec",
            "--message-file",
            "-",
            "--cwd",
            str(workspace),
        ]
        if managed_model:
            command.extend(["--model", managed_model, "--auth-env-only"])
        command.append("--json")

        proc = subprocess.run(
            command,
            input=prompt,
            cwd=workspace,
            text=True,
            capture_output=True,
            check=False,
            timeout=max(30, int(request.timeout_seconds)),
            env={**os.environ, **managed_env, "OPENHANDS_SUPPRESS_BANNER": "1"},
        )

        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        if proc.returncode != 0:
            detail = (stderr or stdout).lower()
            if "insufficient_quota" in detail or "credit_balance_exhausted" in detail or "quota_exhausted" in detail:
                reason = "openclaw_llm_quota_exhausted"
                retryable = False
            elif "api key" in detail and any(marker in detail for marker in ("missing", "unavailable", "required", "invalid")):
                reason = "openclaw_llm_credentials_unavailable"
                retryable = False
            elif "permission denied" in detail:
                reason = "openclaw_permission_denied"
                retryable = False
            else:
                reason = "openclaw_agent_exec_failed"
                retryable = True
            return ExecutionResult(
                status=RuntimeStatus.failed,
                provider=self.name,
                retryable=retryable,
                reason=reason,
                evidence=ExecutionEvidence(
                    provider_metadata={
                        "runtime": "openclaw",
                        "mode": "agent-exec",
                        "working_directory": str(workspace),
                        "returncode": proc.returncode,
                        "managed_llm_provider": "opencode" if managed_model else None,
                        "managed_llm_model": managed_model,
                        "stdout_tail": stdout[-3000:],
                        "stderr_tail": stderr[-3000:],
                    },
                ),
            )

        changed_files = self._changed_files(workspace)
        response = self._parse_json(stdout)
        return ExecutionResult(
            status=RuntimeStatus.succeeded,
            provider=self.name,
            retryable=False,
            evidence=ExecutionEvidence(
                summary="OpenClaw agent exec completed in a MITIGATE disposable workspace.",
                changed_files=tuple(changed_files),
                provider_run_id=self._json_run_id(response),
                provider_metadata={
                    "runtime": "openclaw",
                    "mode": "agent-exec",
                    "working_directory": str(workspace),
                    "returncode": proc.returncode,
                    "managed_llm_provider": "opencode" if managed_model else None,
                    "managed_llm_model": managed_model,
                    "response": response,
                    "stdout_tail": stdout[-2000:],
                    "stderr_tail": stderr[-2000:],
                },
            ),
        )

    @staticmethod
    def _coding_prompt(request: ExecutionRequest) -> str:
        allowed = ", ".join(request.allowed_paths) if request.allowed_paths else "repository-scoped paths authorized by MITIGATE"
        denied = ", ".join(request.denied_paths) if request.denied_paths else ".git, secrets"
        criteria = "\n".join(f"- {item}" for item in request.acceptance_criteria)
        return (
            "You are an execution runtime underneath MITIGATE Core. MITIGATE owns policy, approvals, "
            "mission state and Git publication. Work only in the provided disposable workspace. "
            "Do not commit, push, merge, alter remotes, or escape the workspace.\n\n"
            f"Mission: {request.mission_id}\nObjective:\n{request.objective}\n\n"
            f"Allowed paths: {allowed}\nDenied paths: {denied}\n\n"
            f"Acceptance criteria:\n{criteria}\n"
            "Inspect the repository, implement the smallest safe solution, and run relevant tests."
        )

    @staticmethod
    def _changed_files(workspace: Path) -> list[str]:
        proc = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=workspace,
            text=True,
            capture_output=True,
            check=False,
            timeout=15,
            env={**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"},
        )
        if proc.returncode != 0:
            return []
        result: list[str] = []
        for raw in (proc.stdout or "").splitlines():
            if len(raw) < 4:
                continue
            path = raw[3:].strip()
            if " -> " in path:
                path = path.split(" -> ", 1)[1].strip()
            if path and path not in result:
                result.append(path)
            if len(result) >= 500:
                break
        return result

    @staticmethod
    def _parse_json(stdout: str) -> Mapping[str, Any]:
        text = str(stdout or "").strip()
        if not text:
            return {}
        for line in reversed(text.splitlines()):
            candidate = line.strip()
            if not candidate:
                continue
            try:
                parsed = json.loads(candidate)
            except ValueError:
                continue
            if isinstance(parsed, dict):
                return parsed
        try:
            parsed = json.loads(text)
        except ValueError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _json_run_id(value: Mapping[str, Any]) -> str | None:
        for key in ("runId", "run_id", "id", "sessionId", "session_id"):
            candidate = value.get(key)
            if candidate is not None:
                return str(candidate)
        return None

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

    def _normalize_injected_coding_result(self, raw: Any, request: ExecutionRequest) -> ExecutionResult:
        workspace = Path(str(request.metadata.get("workspace_root") or "")).expanduser().resolve()
        return ExecutionResult(
            status=RuntimeStatus.succeeded,
            provider=self.name,
            retryable=False,
            evidence=ExecutionEvidence(
                summary="Injected OpenClaw coding runner completed.",
                changed_files=tuple(self._changed_files(workspace)) if workspace.is_dir() else (),
                provider_run_id=self._provider_run_id(raw),
                provider_metadata={"runtime": "openclaw", "mode": "injected", "working_directory": str(workspace)},
            ),
        )

    def _failure(self, status: RuntimeStatus, reason: str, retryable: bool) -> ExecutionResult:
        return ExecutionResult(
            status=status,
            provider=self.name,
            retryable=retryable,
            reason=reason[:500],
            evidence=ExecutionEvidence(provider_metadata={"runtime": "openclaw"}),
        )


__all__ = ["OpenClawRuntimeAdapter"]
