import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


AGENT_ROOT = Path(__file__).resolve().parents[1]

if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

import ai.mission_runner as mr


class MissionRunnerSelfHealingManualTests(unittest.TestCase):

    def test_successful_repair_path(self):
        repo_root = mr.REPOSITORY_ROOT
        mission_path = (
            repo_root / "agent/missions/smoke_self_healing.md"
        )
        written = [
            repo_root / "agent/smoke_generated.py"
        ]
        deliverables = {
            "agent/smoke_generated.py"
        }

        calls = {
            "validate": 0,
            "generate": 0,
            "write": 0,
        }

        original_validate = mr.validate_generated_files
        original_write = mr.write_generated_files

        def fake_validate(files):
            calls["validate"] += 1

            if calls["validate"] <= 2:
                raise subprocess.CalledProcessError(
                    1,
                    ["python", "-m", "unittest"],
                )

        def fake_write(data, allowed, mission_text):
            calls["write"] += 1
            self.assertEqual(allowed, deliverables)
            return written

        class FakeGenerator:
            def generate(self, *args, **kwargs):
                calls["generate"] += 1

                return SimpleNamespace(
                    success=True,
                    content=(
                        '{"files": ['
                        '{"path": "agent/smoke_generated.py", '
                        '"content": "x = 1\\n"}'
                        '], "summary": "repair"}'
                    ),
                    error=None,
                )

        try:
            mr.validate_generated_files = fake_validate
            mr.write_generated_files = fake_write

            result = mr.validate_with_self_healing(
                mission_path=mission_path,
                mission="Smoke mission",
                deliverables=deliverables,
                written=written,
                repository_index=SimpleNamespace(),
                generator=FakeGenerator(),
            )

            self.assertEqual(result, written)
            self.assertEqual(calls["validate"], 3)
            self.assertEqual(calls["generate"], 1)
            self.assertEqual(calls["write"], 1)

        finally:
            mr.validate_generated_files = original_validate
            mr.write_generated_files = original_write

    def test_core_path_locked_is_terminal(self):
        repo_root = mr.REPOSITORY_ROOT

        original_validate = mr.validate_generated_files
        original_adapter = mr.MissionRepairAdapter

        class ForbiddenAdapter:
            def __init__(self, *args, **kwargs):
                raise AssertionError(
                    "Repair adapter must not be invoked "
                    "for CORE_PATH_LOCKED"
                )

        def blocked_validation(files):
            raise mr.MissionError("CORE_PATH_LOCKED")

        try:
            mr.validate_generated_files = blocked_validation
            mr.MissionRepairAdapter = ForbiddenAdapter

            with self.assertRaisesRegex(
                mr.MissionError,
                "^CORE_PATH_LOCKED$",
            ):
                mr.validate_with_self_healing(
                    mission_path=(
                        repo_root
                        / "agent/missions/core_block_smoke.md"
                    ),
                    mission="CORE_MAINTENANCE_APPROVED",
                    deliverables={
                        "agent/ai/example.py"
                    },
                    written=[
                        repo_root / "agent/ai/example.py"
                    ],
                    repository_index=SimpleNamespace(),
                    generator=SimpleNamespace(),
                )

        finally:
            mr.validate_generated_files = original_validate
            mr.MissionRepairAdapter = original_adapter


if __name__ == "__main__":
    unittest.main()
