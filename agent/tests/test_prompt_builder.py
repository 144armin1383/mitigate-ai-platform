from __future__ import annotations

import os
import sys
import unittest

# Ensure the agent package (this directory's parent) is importable
CURRENT_DIR = os.path.dirname(__file__)
AGENT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if AGENT_ROOT not in sys.path:
    sys.path.insert(0, AGENT_ROOT)

from ai.prompt_builder import PromptBuilder
from services.planner import ExecutionPlan, TaskDomain, TaskPriority
from services.repository_scanner import RepositoryIndex, RepositoryFile


class TestPromptBuilder(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = ExecutionPlan(
            title="Add robust code generation module",
            description="Implement a deterministic prompt builder and code generator.",
            domain=TaskDomain.GENERAL,
            priority=TaskPriority.HIGH,
            requires_tests=True,
            requires_backup=True,
            requires_commit=True,
            requires_owner_approval=False,
            estimated_files=[
                "agent/ai/",
                "agent/services/planner.py",
            ],
            steps=[
                "Inspect current project state",
                "Design prompt contract",
                "Implement builder and generator",
                "Write unit tests",
            ],
            metadata={},
        )

        files = [
            RepositoryFile(path="agent/ai/self_bootstrap.py", extension=".py", size=128, category="python"),
            RepositoryFile(path="agent/services/planner.py", extension=".py", size=2048, category="python"),
            RepositoryFile(path="agent/services/repository_scanner.py", extension=".py", size=3072, category="python"),
            RepositoryFile(path="README.md", extension=".md", size=4096, category="documentation"),
        ]

        self.repo_index = RepositoryIndex(
            root="/srv/mitigate/mitigate-ai-platform",
            total_files=len(files),
            total_directories=10,
            files=files,
        )

    def test_build_contains_required_sections(self) -> None:
        builder = PromptBuilder(self.plan, self.repo_index)
        built = builder.build()

        self.assertIn("MITIGATE AI Agent - Software Engineering Task", built.user)

        # Task details
        self.assertIn("- Title: Add robust code generation module", built.user)
        self.assertIn("- Description: Implement a deterministic prompt builder and code generator.", built.user)
        self.assertIn(f"- Domain: {self.plan.domain.value}", built.user)
        self.assertIn(f"- Priority: {self.plan.priority.value}", built.user)

        # Repository summary must include totals
        self.assertIn("Repository Summary", built.user)
        self.assertIn("- Total files: 4", built.user)
        self.assertIn("- Total directories: 10", built.user)

        # Candidate files must include resolved paths and hints
        self.assertIn("Candidate Files", built.user)
        self.assertIn("- agent/ai/", built.user)
        self.assertIn("- agent/ai/self_bootstrap.py", built.user)
        self.assertIn("- agent/services/planner.py", built.user)

        # Safety constraints
        self.assertIn("Never access or mention .env contents.", built.user)
        self.assertIn("Never output API keys, tokens, credentials, or secrets.", built.user)
        self.assertIn("Do not write files, run shell commands, or access external networks.", built.user)
        self.assertIn("Keep all source code and comments entirely in English.", built.user)

        # Required Output Format must mention JSON contract
        self.assertIn("Required Output Format", built.user)
        self.assertIn('"summary"', built.user)
        self.assertIn('"files"', built.user)
        self.assertIn('"path"', built.user)
        self.assertIn('"content"', built.user)

        # System prompt should be stable and in English
        self.assertIn("MITIGATE AI software engineering agent", built.system)
        self.assertIn("Always respond in English", built.system)


if __name__ == "__main__":
    unittest.main()
