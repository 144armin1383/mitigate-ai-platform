from __future__ import annotations

import os
import sys
import unittest

# Ensure the agent package (this directory's parent) is importable
CURRENT_DIR = os.path.dirname(__file__)
AGENT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if AGENT_ROOT not in sys.path:
    sys.path.insert(0, AGENT_ROOT)

from ai.code_generator import CodeGenerator, CodeGenerationResult
from providers.base import AIProvider, AIRequest, AIResponse
from services.planner import ExecutionPlan, TaskDomain, TaskPriority
from services.repository_scanner import RepositoryIndex, RepositoryFile


class FakeProvider(AIProvider):
    name = "fake"

    def is_available(self) -> bool:
        return True

    def generate(self, request: AIRequest) -> AIResponse:
        # Deterministic fake response for testing. No external calls.
        return AIResponse(
            content="FAKE_CODE",
            provider=self.name,
            model=request.model or "fake-model",
            success=True,
            usage={"prompt_chars": len(request.prompt)},
            metadata={"echo": True},
        )


class FailingProvider(AIProvider):
    name = "failing"

    def is_available(self) -> bool:
        return True

    def generate(self, request: AIRequest) -> AIResponse:
        return AIResponse(
            content="",
            provider=self.name,
            model=request.model or "fake-model",
            success=False,
            error="simulated failure",
        )


class TestCodeGenerator(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = ExecutionPlan(
            title="Implement code generator",
            description="Build a deterministic code generator using a prompt builder.",
            domain=TaskDomain.GENERAL,
            priority=TaskPriority.NORMAL,
            estimated_files=["agent/ai/"],
        )
        files = [
            RepositoryFile(path="agent/ai/self_bootstrap.py", extension=".py", size=128, category="python"),
            RepositoryFile(path="agent/services/planner.py", extension=".py", size=2048, category="python"),
        ]
        self.repo_index = RepositoryIndex(
            root="/repo",
            total_files=len(files),
            total_directories=2,
            files=files,
        )

    def test_generate_success_with_fake_provider(self) -> None:
        provider = FakeProvider()
        generator = CodeGenerator(ai_provider=provider)

        result: CodeGenerationResult = generator.generate(
            self.plan,
            self.repo_index,
            model="fake-model-1",
            temperature=0.0,
            max_tokens=512,
            request_metadata={"test": True},
        )

        self.assertTrue(result.success)
        self.assertEqual(result.content, "FAKE_CODE")
        self.assertEqual(result.provider, "fake")
        self.assertEqual(result.model, "fake-model-1")

        # Metadata should include request/response details without secrets
        self.assertIsInstance(result.metadata, dict)
        self.assertIn("request", result.metadata)
        self.assertIn("response", result.metadata)
        self.assertIn("usage", result.metadata["response"])  # from fake provider
        self.assertIn("prompt_chars", result.metadata["response"]["usage"])  # deterministic size

    def test_generate_failure_is_propagated(self) -> None:
        provider = FailingProvider()
        generator = CodeGenerator(ai_provider=provider)

        result: CodeGenerationResult = generator.generate(self.plan, self.repo_index)

        self.assertFalse(result.success)
        self.assertEqual(result.provider, "failing")
        self.assertIsNotNone(result.error)
        self.assertIn("simulated failure", result.error)


if __name__ == "__main__":
    unittest.main()
