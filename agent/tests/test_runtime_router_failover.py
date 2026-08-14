from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.execution.runtime_adapter import (
    ExecutionEvidence,
    ExecutionRequest,
    ExecutionResult,
    RuntimeCapabilities,
    RuntimeRegistry,
    RuntimeStatus,
)
from agent.execution.runtime_router import RuntimeRouter
from agent.execution.workspace_manager import ExecutionWorkspace


class _WorkspaceManager:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.created: list[Path] = []
        self.removed: list[Path] = []

    def canonical_is_clean(self) -> bool:
        return True

    def create(self, *, mission_id: str, base_revision: str) -> ExecutionWorkspace:
        path = self.root / f"workspace-{len(self.created) + 1}"
        path.mkdir()
        self.created.append(path)
        return ExecutionWorkspace(path=path, base_revision=base_revision)

    def remove(self, workspace: ExecutionWorkspace) -> None:
        self.removed.append(workspace.path)


class _Adapter:
    def __init__(self, name: str, result: ExecutionResult) -> None:
        self._name = name
        self._result = result
        self.workspaces: list[str] = []

    @property
    def name(self) -> str:
        return self._name

    def capabilities(self) -> RuntimeCapabilities:
        return RuntimeCapabilities(
            coding=True,
            terminal=True,
            file_editing=True,
            tests=True,
            isolated_workspace=True,
        )

    def healthcheck(self) -> dict[str, object]:
        return {"available": True, "mode": "test"}

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        self.workspaces.append(str(request.metadata.get("workspace_root") or ""))
        return self._result

    def cancel(self, provider_run_id: str) -> bool:
        return False


class RuntimeRouterFailoverTests(unittest.TestCase):
    @staticmethod
    def _request(repo: Path) -> ExecutionRequest:
        return ExecutionRequest(
            request_id="r1",
            mission_id="m1",
            objective="Fix the runtime integration defect.",
            repository_root=str(repo),
            base_revision="main",
            allowed_paths=("agent",),
            denied_paths=(".git",),
            timeout_seconds=60,
        )

    @staticmethod
    def _requirements() -> RuntimeCapabilities:
        return RuntimeCapabilities(
            coding=True,
            terminal=True,
            file_editing=True,
            tests=True,
            isolated_workspace=True,
        )

    def test_openhands_incompatible_fails_over_to_openclaw_in_fresh_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = root / "repo"
            repo.mkdir()
            manager = _WorkspaceManager(root)
            openhands = _Adapter(
                "openhands",
                ExecutionResult(
                    status=RuntimeStatus.failed,
                    provider="openhands",
                    retryable=False,
                    reason="managed_openhands_runtime_incompatible",
                    evidence=ExecutionEvidence(
                        provider_metadata={"runtime": "openhands"},
                    ),
                ),
            )
            openclaw = _Adapter(
                "openclaw",
                ExecutionResult(
                    status=RuntimeStatus.succeeded,
                    provider="openclaw",
                    retryable=False,
                    evidence=ExecutionEvidence(
                        summary="fallback succeeded",
                        changed_files=("agent/fix.py",),
                        provider_metadata={"runtime": "openclaw"},
                    ),
                ),
            )
            router = RuntimeRouter(
                RuntimeRegistry([openhands, openclaw]),
                manager,
            )

            result = router.execute(
                self._request(repo),
                require=self._requirements(),
                preferred=("openhands", "openclaw"),
            )

            self.assertEqual(RuntimeStatus.succeeded, result.status)
            self.assertEqual("openclaw", result.provider)
            self.assertEqual(1, len(openhands.workspaces))
            self.assertEqual(1, len(openclaw.workspaces))
            self.assertNotEqual(openhands.workspaces[0], openclaw.workspaces[0])
            self.assertEqual(2, len(manager.created))
            self.assertEqual(manager.created, manager.removed)
            attempts = result.evidence.provider_metadata["provider_attempts"]
            self.assertEqual(["openhands", "openclaw"], [item["provider"] for item in attempts])
            self.assertEqual("managed_openhands_runtime_incompatible", attempts[0]["reason"])
            self.assertEqual("succeeded", attempts[1]["status"])

    def test_quota_failure_does_not_fail_over(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = root / "repo"
            repo.mkdir()
            manager = _WorkspaceManager(root)
            openhands = _Adapter(
                "openhands",
                ExecutionResult(
                    status=RuntimeStatus.blocked,
                    provider="openhands",
                    retryable=False,
                    reason="openhands_llm_quota_exhausted",
                ),
            )
            openclaw = _Adapter(
                "openclaw",
                ExecutionResult(
                    status=RuntimeStatus.succeeded,
                    provider="openclaw",
                    evidence=ExecutionEvidence(changed_files=("agent/fix.py",)),
                ),
            )
            router = RuntimeRouter(RuntimeRegistry([openhands, openclaw]), manager)

            result = router.execute(
                self._request(repo),
                require=self._requirements(),
                preferred=("openhands", "openclaw"),
            )

            self.assertEqual(RuntimeStatus.blocked, result.status)
            self.assertEqual("openhands", result.provider)
            self.assertEqual([], openclaw.workspaces)
            self.assertEqual(1, len(manager.created))


if __name__ == "__main__":
    unittest.main()
