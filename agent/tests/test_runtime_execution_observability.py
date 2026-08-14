from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agent.execution.external_openhands_runner import ExternalOpenHandsRunner
from agent.execution.openclaw_adapter import OpenClawRuntimeAdapter
from agent.execution.runtime_adapter import (
    ExecutionEvidence,
    ExecutionRequest,
    ExecutionResult,
    RuntimeStatus,
)
from agent.runtime.managed_workspace_mission_controller import ManagedWorkspaceMissionController
from agent.runtime.runtime_mcp_server_extended import _infer_task_type
from agent.runtime.workspace_production_mission_controller import WorkspaceProductionMissionController


class RuntimeExecutionObservabilityTests(unittest.TestCase):
    def _request(self, repo: Path, *, workspace: Path | None = None) -> ExecutionRequest:
        metadata = {"model": "gpt-test"}
        if workspace is not None:
            metadata["workspace_root"] = str(workspace)
        return ExecutionRequest(
            request_id="r1",
            mission_id="m1",
            objective="Fix the problem autonomously.",
            repository_root=str(repo),
            base_revision="main",
            allowed_paths=("agent",),
            timeout_seconds=60,
            metadata=metadata,
        )

    def _runner_fixture(self, root: Path) -> tuple[Path, Path, Path, ExternalOpenHandsRunner]:
        repo = root / "repo"
        workspace = root / "workspace"
        venv = root / "external-venv"
        python_path = venv / "bin" / "python"
        site_packages = venv / "lib" / "python3.12" / "site-packages"
        runner_script = repo / "agent" / "execution" / "openhands_subprocess_runner.py"
        workspace.mkdir(parents=True)
        runner_script.parent.mkdir(parents=True)
        runner_script.write_text("# runner\n", encoding="utf-8")
        python_path.parent.mkdir(parents=True)
        python_path.write_text("#!/bin/sh\n", encoding="utf-8")
        python_path.chmod(0o700)
        site_packages.mkdir(parents=True)
        return repo, workspace, runner_script, ExternalOpenHandsRunner(
            repository_root=repo,
            python_path=python_path,
        )

    @staticmethod
    def _preflight_success() -> SimpleNamespace:
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({
                "executable": "/managed/python",
                "prefix": "/managed",
                "base_prefix": "/usr",
                "sitepackages": ["/managed/site-packages"],
                "openhands_spec": "/managed/site-packages/openhands/__init__.py",
            }) + "\n",
            stderr="",
        )

    def test_managed_openhands_preserves_virtualenv_interpreter_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = root / "repo"
            workspace = root / "workspace"
            venv = root / "external-venv"
            system_bin = root / "system" / "python3.12"
            python_link = venv / "bin" / "python"
            runner_script = repo / "agent" / "execution" / "openhands_subprocess_runner.py"
            site_packages = venv / "lib" / "python3.12" / "site-packages"

            workspace.mkdir(parents=True)
            runner_script.parent.mkdir(parents=True)
            runner_script.write_text("# runner\n", encoding="utf-8")
            system_bin.parent.mkdir(parents=True)
            system_bin.write_text("#!/bin/sh\n", encoding="utf-8")
            system_bin.chmod(0o700)
            python_link.parent.mkdir(parents=True)
            python_link.symlink_to(system_bin)
            site_packages.mkdir(parents=True)

            runner = ExternalOpenHandsRunner(repository_root=repo, python_path=python_link)
            self.assertEqual(str(python_link.absolute()), str(runner.python_path))
            self.assertNotEqual(str(system_bin.resolve()), str(runner.python_path))
            self.assertEqual(str(venv.absolute()), str(runner._venv_root()))

            completed = SimpleNamespace(returncode=0, stdout='{"run_id":"run-symlink"}\n', stderr="")
            with patch(
                "agent.execution.external_openhands_runner.subprocess.run",
                return_value=self._preflight_success(),
            ) as preflight_mock, patch.object(
                runner,
                "_run_agent",
                return_value=completed,
            ) as run_mock:
                runner(request=self._request(repo), workspace=workspace)

            self.assertEqual(str(python_link.absolute()), preflight_mock.call_args.args[0][0])
            self.assertEqual(str(venv.absolute()), preflight_mock.call_args.kwargs["env"]["VIRTUAL_ENV"])
            self.assertEqual(workspace.resolve(), run_mock.call_args.kwargs["workspace"].resolve())

    def test_managed_openhands_process_runs_from_disposable_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo, workspace, _, runner = self._runner_fixture(root)
            completed = SimpleNamespace(
                returncode=0,
                stdout='{"run_id":"run-1"}\n',
                stderr="",
            )
            with patch(
                "agent.execution.external_openhands_runner.subprocess.run",
                return_value=self._preflight_success(),
            ) as preflight_mock, patch.object(
                runner,
                "_run_agent",
                return_value=completed,
            ) as run_mock:
                result = runner(request=self._request(repo), workspace=workspace)

            self.assertEqual(1, preflight_mock.call_count)
            self.assertEqual(workspace.resolve(), Path(preflight_mock.call_args.kwargs["cwd"]).resolve())
            self.assertEqual(workspace.resolve(), run_mock.call_args.kwargs["workspace"].resolve())
            self.assertNotEqual(repo.resolve(), run_mock.call_args.kwargs["workspace"].resolve())
            self.assertEqual("run-1", result.id)
            self.assertEqual(str(workspace.resolve()), result.provider_metadata["working_directory"])
            self.assertTrue(result.provider_metadata["runtime_preflight"]["openhands_spec"])

    def test_managed_openhands_child_python_environment_is_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo, workspace, _, runner = self._runner_fixture(root)
            completed = SimpleNamespace(returncode=0, stdout='{"run_id":"run-2"}\n', stderr="")
            contaminated = {
                "PYTHONHOME": "/wrong/python/home",
                "PYTHONPATH": "/wrong/python/path",
                "PYTHONUSERBASE": "/wrong/user/base",
                "__PYVENV_LAUNCHER__": "/wrong/launcher",
                "VIRTUAL_ENV": "/wrong/venv",
                "PATH": "/usr/bin",
            }
            with patch.dict(os.environ, contaminated, clear=False):
                with patch(
                    "agent.execution.external_openhands_runner.subprocess.run",
                    return_value=self._preflight_success(),
                ) as mocked, patch.object(
                    runner,
                    "_run_agent",
                    return_value=completed,
                ):
                    runner(request=self._request(repo), workspace=workspace)

            env = mocked.call_args.kwargs["env"]
            self.assertNotIn("PYTHONHOME", env)
            self.assertNotIn("PYTHONUSERBASE", env)
            self.assertNotIn("__PYVENV_LAUNCHER__", env)
            self.assertEqual(str(runner._venv_root()), env["VIRTUAL_ENV"])
            self.assertTrue(env["PATH"].startswith(str(runner.python_path.parent) + os.pathsep))
            self.assertEqual(
                str(runner._venv_root() / "lib" / "python3.12" / "site-packages"),
                env["PYTHONPATH"],
            )
            self.assertEqual("1", env["PYTHONNOUSERSITE"])
            self.assertEqual("1", env["OPENHANDS_SUPPRESS_BANNER"])

    def test_preflight_rejects_missing_openhands_before_agent_execution(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo, workspace, _, runner = self._runner_fixture(root)
            preflight = SimpleNamespace(
                returncode=0,
                stdout=json.dumps({
                    "executable": str(runner.python_path),
                    "prefix": str(runner._venv_root()),
                    "base_prefix": "/usr",
                    "sitepackages": [],
                    "openhands_spec": None,
                }) + "\n",
                stderr="",
            )
            with patch(
                "agent.execution.external_openhands_runner.subprocess.run",
                return_value=preflight,
            ) as mocked:
                with self.assertRaisesRegex(RuntimeError, "managed_openhands_runtime_incompatible"):
                    runner(request=self._request(repo), workspace=workspace)
            self.assertEqual(1, mocked.call_count)

    def test_openclaw_agent_exec_is_scoped_to_disposable_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = root / "repo"
            workspace = root / "workspace"
            binary = root / "openclaw"
            repo.mkdir()
            workspace.mkdir()
            binary.write_text("#!/bin/sh\n", encoding="utf-8")
            binary.chmod(0o700)
            adapter = OpenClawRuntimeAdapter(binary=str(binary))

            agent_result = SimpleNamespace(
                returncode=0,
                stdout='{"runId":"oc-run-1"}\n',
                stderr="",
            )
            git_result = SimpleNamespace(
                returncode=0,
                stdout=" M agent/example.py\n",
                stderr="",
            )
            with patch(
                "agent.execution.openclaw_adapter.subprocess.run",
                side_effect=[agent_result, git_result],
            ) as mocked:
                result = adapter.execute(self._request(repo, workspace=workspace))

            self.assertEqual(RuntimeStatus.succeeded, result.status)
            self.assertEqual("openclaw", result.provider)
            self.assertIn("agent/example.py", result.evidence.changed_files)
            agent_call = mocked.call_args_list[0]
            argv = agent_call.args[0]
            self.assertEqual(
                [
                    str(binary), "agent", "exec", "--message-file", "-",
                    "--cwd", str(workspace.resolve()), "--json",
                ],
                argv,
            )
            self.assertEqual(workspace.resolve(), Path(agent_call.kwargs["cwd"]).resolve())
            self.assertNotEqual(repo.resolve(), Path(agent_call.kwargs["cwd"]).resolve())

    def test_openhands_integration_failure_triggers_provider_fallback(self) -> None:
        result = ExecutionResult(
            status=RuntimeStatus.failed,
            provider="openhands",
            retryable=False,
            reason="managed_openhands_runtime_incompatible",
            evidence=ExecutionEvidence(),
        )
        self.assertTrue(
            WorkspaceProductionMissionController._should_fallback_from_openhands(result)
        )
        unrelated = ExecutionResult(
            status=RuntimeStatus.failed,
            provider="openhands",
            retryable=False,
            reason="openhands_llm_quota_exhausted",
            evidence=ExecutionEvidence(),
        )
        self.assertFalse(
            WorkspaceProductionMissionController._should_fallback_from_openhands(unrelated)
        )

    def test_failure_evidence_is_persisted_before_retry(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = root / "repo"
            data = root / "data"
            repo.mkdir()
            controller = object.__new__(ManagedWorkspaceMissionController)
            controller.data_root = data
            mission = {"id": "m123", "attempts_done": 1, "max_retries": 2}
            result = {
                "status": "retry",
                "reason": "managed_openhands_execution_failed",
                "provider": "openhands",
                "failure_class": "transient_runtime",
                "request_id": "r123",
                "task_type": "bugfix",
                "runtime_status": "failed",
                "runtime_retryable": True,
                "runtime_evidence": {
                    "provider_metadata": {
                        "returncode": 1,
                        "stderr_tail": "example failure",
                        "api_key": "must-not-persist",
                    }
                },
            }

            controller._persist_failure_evidence(mission=mission, result=result)
            path = data / "runtime" / "failure-evidence" / "m123.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual("retry", payload["status"])
            self.assertEqual("managed_openhands_execution_failed", payload["reason"])
            self.assertEqual(1, payload["runtime_evidence"]["provider_metadata"]["returncode"])
            self.assertEqual("<redacted>", payload["runtime_evidence"]["provider_metadata"]["api_key"])

    def test_primary_intent_beats_incidental_security_terms(self) -> None:
        self.assertEqual(
            "bugfix",
            _infer_task_type(
                "Find the problem with the previous mission, fix it autonomously, "
                "preserve security boundaries and complete the task."
            ),
        )
        self.assertEqual(
            "documentation",
            _infer_task_type(
                "Complete the runtime consolidation build-vs-adopt assessment with security analysis."
            ),
        )


if __name__ == "__main__":
    unittest.main()
