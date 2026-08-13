from __future__ import annotations

import importlib.util
import os
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


class OpenHandsRuntimeAdapter:
    """Optional OpenHands execution provider behind the MITIGATE adapter contract.

    MITIGATE remains authoritative for mission state, policy, approvals and Git.
    This adapter refuses to execute in the canonical repository checkout: callers
    must provide a disposable workspace via request.metadata['workspace_root'].
    """

    def __init__(self, *, runner: Any | None = None) -> None:
        self._runner = runner

    @property
    def name(self) -> str:
        return "openhands"

    def capabilities(self) -> RuntimeCapabilities:
        return RuntimeCapabilities(
            coding=True,
            terminal=True,
            file_editing=True,
            tests=True,
            mcp=True,
            skills=True,
            multi_agent=True,
            isolated_workspace=True,
            remote_execution=True,
        )

    def healthcheck(self) -> Mapping[str, Any]:
        if self._runner is not None:
            return {"available": True, "mode": "injected"}

        try:
            available = importlib.util.find_spec("openhands.sdk") is not None
        except (ImportError, ModuleNotFoundError, ValueError):
            available = False

        return {
            "available": available,
            "mode": "sdk-local",
            "dependency": "OpenHands Software Agent SDK",
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
            if self._runner is not None:
                raw = self._runner(request=request, workspace=workspace)
            else:
                raw = self._run_sdk(request=request, workspace=workspace)
        except TimeoutError as exc:
            return self._failure(RuntimeStatus.timed_out, str(exc), retryable=True)
        except Exception as exc:  # provider exceptions are normalized at boundary
            return self._failure(
                RuntimeStatus.failed,
                f"openhands_execution_failed:{type(exc).__name__}",
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
                    diagnostics=tuple(f"scope_violation:{path}" for path in violations),
                    changed_files=changed_files,
                    provider_run_id=self._provider_run_id(raw),
                    provider_metadata={"runtime": "openhands"},
                ),
            )

        return ExecutionResult(
            status=RuntimeStatus.succeeded,
            provider=self.name,
            retryable=False,
            evidence=ExecutionEvidence(
                summary="OpenHands execution completed in a disposable workspace.",
                changed_files=changed_files,
                provider_run_id=self._provider_run_id(raw),
                provider_metadata={"runtime": "openhands"},
            ),
        )

    def cancel(self, provider_run_id: str) -> bool:
        # Local SDK conversations do not expose a stable cross-process cancel
        # contract here. Remote Agent Server cancellation will be added as a
        # separate transport without changing the MITIGATE adapter interface.
        del provider_run_id
        return False

    def _validated_workspace(self, request: ExecutionRequest) -> Path:
        value = str(request.metadata.get("workspace_root") or "").strip()
        if not value:
            raise ValueError("openhands_requires_disposable_workspace")

        workspace = Path(value).expanduser().resolve()
        canonical = Path(request.repository_root).expanduser().resolve()

        if workspace == canonical:
            raise ValueError("openhands_refuses_canonical_repository_workspace")
        if not workspace.is_dir():
            raise ValueError("openhands_workspace_not_found")
        if not (workspace / ".git").exists():
            raise ValueError("openhands_workspace_must_be_git_checkout")
        return workspace

    def _run_sdk(self, *, request: ExecutionRequest, workspace: Path) -> Any:
        from openhands.sdk import Agent, Conversation, LLM, Tool
        from openhands.tools.file_editor import FileEditorTool
        from openhands.tools.task_tracker import TaskTrackerTool
        from openhands.tools.terminal import TerminalTool

        model = str(
            request.metadata.get("model")
            or os.environ.get("MITIGATE_OPENHANDS_MODEL")
            or "gpt-5.5"
        )
        api_key_env = str(request.metadata.get("api_key_env") or "OPENAI_API_KEY")
        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise RuntimeError("configured_llm_api_key_is_unavailable")

        llm = LLM(model=model, api_key=api_key)
        agent = Agent(
            llm=llm,
            tools=[
                Tool(name=TerminalTool.name),
                Tool(name=FileEditorTool.name),
                Tool(name=TaskTrackerTool.name),
            ],
        )
        conversation = Conversation(agent=agent, workspace=str(workspace))
        conversation.send_message(self._prompt(request))
        conversation.run()
        return conversation

    @staticmethod
    def _prompt(request: ExecutionRequest) -> str:
        allowed = "\n".join(f"- {path}" for path in request.allowed_paths) or "- none"
        denied = "\n".join(f"- {path}" for path in request.denied_paths) or "- none"
        criteria = "\n".join(f"- {item}" for item in request.acceptance_criteria) or "- none"
        return (
            "Execute the authorized MITIGATE software-engineering task inside this disposable workspace.\n\n"
            f"Objective:\n{request.objective}\n\n"
            f"Allowed paths:\n{allowed}\n\n"
            f"Denied paths:\n{denied}\n\n"
            f"Acceptance criteria:\n{criteria}\n\n"
            "Do not commit, push, merge, deploy, access secrets, or modify files outside the authorized scope. "
            "Run relevant tests and leave the workspace changes for MITIGATE to review."
        )

    @staticmethod
    def _changed_files(workspace: Path, base_revision: str) -> tuple[str, ...]:
        changed: set[str] = set()
        if base_revision:
            result = subprocess.run(
                ["git", "diff", "--name-only", base_revision, "--"],
                cwd=workspace,
                text=True,
                capture_output=True,
                check=False,
            )
            if result.returncode == 0:
                changed.update(line.strip() for line in result.stdout.splitlines() if line.strip())

        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=workspace,
            text=True,
            capture_output=True,
            check=False,
        )
        if untracked.returncode == 0:
            changed.update(line.strip() for line in untracked.stdout.splitlines() if line.strip())
        return tuple(sorted(changed))

    @staticmethod
    def _scope_violations(request: ExecutionRequest, changed_files: tuple[str, ...]) -> tuple[str, ...]:
        allowed = tuple(path.rstrip("/") for path in request.allowed_paths if path)
        denied = tuple(path.rstrip("/") for path in request.denied_paths if path)

        def under(path: str, root: str) -> bool:
            return path == root or path.startswith(root + "/")

        violations: list[str] = []
        for path in changed_files:
            if any(under(path, root) for root in denied):
                violations.append(path)
                continue
            if allowed and not any(under(path, root) for root in allowed):
                violations.append(path)
        return tuple(sorted(set(violations)))

    @staticmethod
    def _provider_run_id(raw: Any) -> str | None:
        value = getattr(raw, "id", None) or getattr(raw, "conversation_id", None)
        return str(value) if value is not None else None

    def _failure(self, status: RuntimeStatus, reason: str, *, retryable: bool) -> ExecutionResult:
        return ExecutionResult(
            status=status,
            provider=self.name,
            retryable=retryable,
            reason=reason[:500],
            evidence=ExecutionEvidence(provider_metadata={"runtime": "openhands"}),
        )


__all__ = ["OpenHandsRuntimeAdapter"]
