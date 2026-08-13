from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence

from agent.execution.openclaw_adapter import OpenClawRuntimeAdapter
from agent.execution.openhands_adapter import OpenHandsRuntimeAdapter
from agent.execution.ruflo_adapter import RufloRuntimeAdapter
from agent.execution.runtime_adapter import (
    ExecutionRequest,
    RuntimeCapabilities,
    RuntimeRegistry,
    RuntimeStatus,
)
from agent.execution.runtime_branch_publisher import RuntimeBranchPublisher
from agent.execution.runtime_router import RuntimeRouter
from agent.execution.workspace_manager import DisposableWorkspaceManager
from agent.runtime.production_mission_controller import ProductionMissionController


class _ExternalOpenHandsRunner:
    def __init__(self, *, repository_root: Path, python_binary: Path) -> None:
        self.repository_root = repository_root
        self.python_binary = python_binary

    def __call__(self, *, request: ExecutionRequest, workspace: Path) -> Any:
        helper = self.repository_root / "agent" / "execution" / "openhands_subprocess_runner.py"
        payload = {
            "model": request.metadata.get("model"),
            "api_key_env": request.metadata.get("api_key_env", "OPENAI_API_KEY"),
            "prompt": self._prompt(request),
        }
        env = dict(os.environ)
        env["MITIGATE_OPENHANDS_REQUEST_JSON"] = json.dumps(payload)
        env["PYTHONPATH"] = os.pathsep.join(
            [str(self.repository_root), str(self.repository_root / "agent")]
        )
        proc = subprocess.run(
            [str(self.python_binary), str(helper), "--workspace", str(workspace)],
            cwd=workspace,
            text=True,
            capture_output=True,
            check=False,
            timeout=request.timeout_seconds,
            env=env,
        )
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout).strip()[-1000:]
            raise RuntimeError(f"openhands_subprocess_failed:{detail}")
        try:
            data = json.loads((proc.stdout or "{}").splitlines()[-1])
        except Exception:
            data = {}
        return type("OpenHandsRun", (), {"id": data.get("run_id")})()

    @staticmethod
    def _prompt(request: ExecutionRequest) -> str:
        allowed = "\n".join(f"- {p}" for p in request.allowed_paths) or "- none"
        denied = "\n".join(f"- {p}" for p in request.denied_paths) or "- none"
        criteria = "\n".join(f"- {p}" for p in request.acceptance_criteria) or "- none"
        return (
            "Execute the authorized MITIGATE software-engineering task inside this disposable workspace.\n\n"
            f"Objective:\n{request.objective}\n\nAllowed paths:\n{allowed}\n\nDenied paths:\n{denied}\n\n"
            f"Acceptance criteria:\n{criteria}\n\n"
            "Do not commit, push, merge, deploy, access secrets, or modify files outside the authorized scope. "
            "Run relevant tests and leave workspace changes for MITIGATE governance to publish."
        )


class RuntimeConsolidationController:
    """MITIGATE-owned controller that routes opted-in missions to external runtimes.

    Missions without an explicit runtime_execution block continue through the
    existing ProductionMissionController unchanged.
    """

    def __init__(
        self,
        *,
        repository_root: str | Path | None = None,
        external_runtime_root: str | Path | None = None,
        timeout_seconds: int = 1800,
    ) -> None:
        if repository_root is None:
            repository_root = Path(__file__).resolve().parents[2]
        self.repository_root = Path(repository_root).resolve()
        self.agent_root = self.repository_root / "agent"
        self.timeout_seconds = int(timeout_seconds)
        self.external_runtime_root = Path(
            external_runtime_root
            or os.environ.get("MITIGATE_EXTERNAL_RUNTIME_ROOT")
            or "/srv/mitigate/external-runtimes"
        ).resolve()
        self.legacy = ProductionMissionController(
            repository_root=self.repository_root,
            timeout_seconds=self.timeout_seconds,
        )
        self.router = self._build_router()

    def execute(self, mission: Dict[str, Any]) -> Dict[str, Any]:
        mission_id = str(mission.get("id") or "").strip()
        context, content = self._mission_context(mission_id)
        execution = context.get("runtime_execution") if isinstance(context, dict) else None
        if not isinstance(execution, dict) or not bool(execution.get("enabled", False)):
            return self.legacy.execute(mission)

        request = self._execution_request(mission_id, content, context, execution)
        require = self._capabilities(execution.get("require", {}))
        preferred = self._preferred(execution.get("preferred", ()))
        result = self.router.execute(request, require=require, preferred=preferred)
        return self._normalize_result(result)

    def _build_router(self) -> RuntimeRouter:
        npm_bin = self.external_runtime_root / "npm" / "node_modules" / ".bin"
        openhands_python = self.external_runtime_root / "venv" / "bin" / "python"

        adapters = []
        if openhands_python.exists():
            adapters.append(
                OpenHandsRuntimeAdapter(
                    runner=_ExternalOpenHandsRunner(
                        repository_root=self.repository_root,
                        python_binary=openhands_python,
                    )
                )
            )
        adapters.append(OpenClawRuntimeAdapter(binary=str(npm_bin / "openclaw")))
        adapters.append(RufloRuntimeAdapter(binary=str(npm_bin / "ruflo")))

        return RuntimeRouter(
            RuntimeRegistry(adapters),
            DisposableWorkspaceManager(self.repository_root),
            publisher=RuntimeBranchPublisher(self.repository_root),
        )

    def _mission_context(self, mission_id: str) -> tuple[Mapping[str, Any], str]:
        path = self.agent_root / "missions" / f"{mission_id}.md"
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            return {}, ""
        match = re.search(r"## Context\s*\n\s*```json\s*\n(.*?)\n```", content, re.DOTALL)
        if not match:
            return {}, content
        try:
            data = json.loads(match.group(1))
        except Exception:
            return {}, content
        return (data if isinstance(data, dict) else {}), content

    def _execution_request(
        self,
        mission_id: str,
        content: str,
        context: Mapping[str, Any],
        execution: Mapping[str, Any],
    ) -> ExecutionRequest:
        objective = str(context.get("objective") or "").strip() or self._heading_text(content, "Objective")
        deliverables = self._string_tuple(context.get("deliverables", ()))
        denied = self._string_tuple(context.get("denied_paths", ()))
        criteria = self._string_tuple(context.get("acceptance_criteria", ()))
        metadata = dict(execution.get("metadata") or {})
        metadata.setdefault("openclaw_capability_task", bool(execution.get("openclaw_capability_task", False)))
        metadata.setdefault("benchmark_mode", bool(execution.get("benchmark_mode", False)))
        return ExecutionRequest(
            request_id=str(context.get("request_id") or mission_id),
            mission_id=mission_id,
            objective=objective,
            repository_root=str(self.repository_root),
            base_revision=str(execution.get("base_revision") or "main"),
            allowed_paths=deliverables,
            denied_paths=denied,
            acceptance_criteria=criteria,
            timeout_seconds=int(execution.get("timeout_seconds") or self.timeout_seconds),
            metadata=metadata,
        )

    @staticmethod
    def _heading_text(content: str, heading: str) -> str:
        match = re.search(rf"^## {re.escape(heading)}\s*$\n(.*?)(?=^## |\Z)", content, re.MULTILINE | re.DOTALL)
        return match.group(1).strip() if match else ""

    @staticmethod
    def _string_tuple(value: Any) -> tuple[str, ...]:
        if not isinstance(value, (list, tuple)):
            return ()
        return tuple(str(item).strip() for item in value if str(item).strip())

    @staticmethod
    def _preferred(value: Any) -> Sequence[str]:
        if isinstance(value, str):
            return (value,)
        if isinstance(value, (list, tuple)):
            return tuple(str(item) for item in value)
        return ()

    @staticmethod
    def _capabilities(raw: Any) -> RuntimeCapabilities:
        data = raw if isinstance(raw, dict) else {}
        names = RuntimeCapabilities.__dataclass_fields__.keys()
        return RuntimeCapabilities(**{name: bool(data.get(name, False)) for name in names})

    @staticmethod
    def _normalize_result(result: Any) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "provider": result.provider,
            "reason": result.reason,
            "retryable": bool(result.retryable),
            "changed_files": list(result.evidence.changed_files),
            "branch": result.evidence.branch,
            "git_commit": result.evidence.commit_sha,
            "provider_run_id": result.evidence.provider_run_id,
        }
        if result.status == RuntimeStatus.succeeded:
            payload["status"] = "success"
        elif result.status == RuntimeStatus.blocked:
            payload["status"] = "blocked"
        elif result.status in (RuntimeStatus.timed_out, RuntimeStatus.failed, RuntimeStatus.unavailable):
            payload["status"] = "retry" if result.retryable else "exhausted"
        else:
            payload["status"] = "blocked"
        return payload


__all__ = ["RuntimeConsolidationController"]
