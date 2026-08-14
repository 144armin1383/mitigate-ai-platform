from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from agent.execution.external_openhands_runner import ExternalOpenHandsRunner
from agent.runtime.autonomous_mission_diagnostics import collect_autonomous_mission_diagnostics
from agent.runtime.autonomous_mission_queue import AutonomousMissionQueue
from agent.runtime.mission_diagnostics import collect_mission_diagnostics
from agent.runtime.runtime_mcp_server_extended import _infer_task_type


class AutonomousOperatorRuntimeTests(unittest.TestCase):
    def test_legacy_zero_retry_value_uses_bounded_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "missions.json"
            queue = AutonomousMissionQueue(str(path), default_max_retries=2)
            queue.enqueue("m1", 1, [], max_retries=0)
            item = queue.get("m1")
            self.assertEqual(item["max_retries"], 2)

    def test_natural_language_task_type_inference(self) -> None:
        self.assertEqual(_infer_task_type("fix this backend bug"), "backend")
        self.assertEqual(_infer_task_type("prepare architecture assessment"), "documentation")
        self.assertEqual(_infer_task_type("check systemd runtime service"), "infrastructure")
        self.assertEqual(_infer_task_type("repair the React UI"), "frontend")

    def test_managed_openhands_runtime_path_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            python_path = root / "python"
            runner_script = root / "agent" / "execution" / "openhands_subprocess_runner.py"
            python_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            python_path.chmod(0o700)
            runner_script.parent.mkdir(parents=True)
            runner_script.write_text("# managed runner\n", encoding="utf-8")
            runner = ExternalOpenHandsRunner(
                repository_root=root,
                python_path=python_path,
            )
            self.assertTrue(runner.available())
            self.assertEqual(runner.python_path, python_path.resolve())
            self.assertEqual(runner.runner_script, runner_script.resolve())

    def test_diagnostics_read_durable_definition_outside_git(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            data = root / "data"
            repo.mkdir()
            os.system(f"git -C {repo} init -q")
            definitions = data / "runtime" / "mission-definitions"
            definitions.mkdir(parents=True)
            definition = definitions / "m1.md"
            definition.write_text(
                "# Mission\n\nMission ID: m1\nRequest ID: r1\nTask Type: backend\n\n"
                "## Objective\n\nFix the bug autonomously.\n\n## Context\n\n```json\n{}\n```\n",
                encoding="utf-8",
            )
            result = collect_autonomous_mission_diagnostics(
                "m1",
                repository_root=repo,
                data_root=data,
            )
            durable = result["durable_mission_definition"]
            self.assertTrue(durable["exists"])
            self.assertEqual(durable["task_type"], "backend")
            self.assertEqual(durable["objective"], "Fix the bug autonomously.")

    def test_mission_diagnostics_expose_bounded_failure_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            data = root / "data"
            repo.mkdir()
            os.system(f"git -C {repo} init -q")
            evidence_dir = data / "runtime" / "failure-evidence"
            evidence_dir.mkdir(parents=True)
            (evidence_dir / "m1.json").write_text(
                json.dumps({
                    "status": "exhausted",
                    "failure_class": "runtime_integration_defect",
                    "reason": "managed_openhands_runtime_incompatible",
                    "provider": "openhands",
                    "runtime_status": "failed",
                    "runtime_retryable": False,
                    "attempts_done": 2,
                    "max_retries": 2,
                    "runtime_evidence": {
                        "diagnostics": ["managed_openhands_failure:managed_openhands_runtime_incompatible"],
                        "provider_metadata": {
                            "error_code": "managed_openhands_runtime_incompatible",
                            "runtime": "openhands",
                            "returncode": 0,
                            "stdout_tail": '{"executable":"/usr/bin/python3.12","openhands_spec":null}',
                            "stderr_tail": "",
                            "runtime_preflight": {
                                "executable": "/usr/bin/python3.12",
                                "prefix": "/usr",
                                "base_prefix": "/usr",
                                "sitepackages": ["/usr/lib/python3/dist-packages"],
                                "openhands_spec": None,
                            },
                            "api_key": "must-not-leak",
                        },
                    },
                }),
                encoding="utf-8",
            )
            result = collect_mission_diagnostics(
                "m1",
                repository_root=repo,
                data_root=data,
            )
            evidence = result["failure_evidence"]
            self.assertTrue(evidence["exists"])
            self.assertEqual(evidence["reason"], "managed_openhands_runtime_incompatible")
            metadata = evidence["provider_metadata"]
            self.assertEqual(metadata["runtime_preflight"]["prefix"], "/usr")
            self.assertIn("openhands_spec", metadata["runtime_preflight"])
            self.assertNotIn("api_key", metadata)


if __name__ == "__main__":
    unittest.main()
