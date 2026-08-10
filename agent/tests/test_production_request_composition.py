import tempfile
import unittest
from pathlib import Path

from agent.runtime.production_request_composition import (
    build_production_request_composition,
)


class FakeProjectRegistry:
    def __init__(self, root: Path):
        self.root = root

    def resolve_project(
        self,
        project_id,
    ):
        if project_id != "mitigate":
            return None

        return {
            "project_id": "mitigate",
            "repository_root": str(
                self.root
            ),
            "default_branch": "main",
            "project_type": "wordpress",
            "policy_profile": "default",
            "queue_reference": (
                "production"
            ),
        }


class FakeProviderRegistry:
    def resolve_model(
        self,
        *args,
        **kwargs,
    ):
        return {
            "provider_id": "provider",
            "model_id": "model",
        }

    def select_model(
        self,
        *args,
        **kwargs,
    ):
        return {
            "provider_id": "provider",
            "model_id": "model",
        }


class FakeBudgetEvaluator:
    def evaluate(
        self,
        *args,
        **kwargs,
    ):
        return {
            "allowed": True,
        }


class FakeRateLimiter:
    def allow(
        self,
        *args,
        **kwargs,
    ):
        return True

    def check(
        self,
        *args,
        **kwargs,
    ):
        return {
            "allowed": True,
        }


class FakeClock:
    def now(self):
        return (
            "2026-08-10T12:00:00+00:00"
        )


class ProductionRequestCompositionTests(
    unittest.TestCase
):

    def test_builds_real_components(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            composition = (
                build_production_request_composition(
                    project_id="mitigate",
                    queue_reference="production",
                    queue_path=(
                        root
                        / "data"
                        / "missions.json"
                    ),
                    repository_root=root,
                    project_registry=(
                        FakeProjectRegistry(
                            root
                        )
                    ),
                    provider_registry=(
                        FakeProviderRegistry()
                    ),
                    budget_evaluator=(
                        FakeBudgetEvaluator()
                    ),
                    rate_limiter=(
                        FakeRateLimiter()
                    ),
                    clock=FakeClock(),
                )
            )

            self.assertIsNotNone(
                composition.request_flow
            )

            self.assertIsNotNone(
                composition.request_gate
            )

            self.assertIsNotNone(
                composition.planner
            )

            self.assertIsNotNone(
                composition.queue_adapter
            )

    def test_queue_adapter_points_to_runtime_queue(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            queue_path = (
                root
                / "data"
                / "missions.json"
            )

            composition = (
                build_production_request_composition(
                    project_id="mitigate",
                    queue_reference="production",
                    queue_path=queue_path,
                    repository_root=root,
                    project_registry=(
                        FakeProjectRegistry(
                            root
                        )
                    ),
                    provider_registry=(
                        FakeProviderRegistry()
                    ),
                    budget_evaluator=(
                        FakeBudgetEvaluator()
                    ),
                    rate_limiter=(
                        FakeRateLimiter()
                    ),
                    clock=FakeClock(),
                )
            )

            self.assertEqual(
                composition
                .queue_adapter
                .queue
                ._path,
                str(
                    queue_path.resolve()
                ),
            )

    def test_invalid_project_id_rejected(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            with self.assertRaisesRegex(
                ValueError,
                "invalid_project_id",
            ):
                build_production_request_composition(
                    project_id="",
                    queue_reference="production",
                    queue_path=(
                        root
                        / "data"
                        / "missions.json"
                    ),
                    repository_root=root,
                    project_registry=(
                        FakeProjectRegistry(
                            root
                        )
                    ),
                    provider_registry=(
                        FakeProviderRegistry()
                    ),
                    budget_evaluator=(
                        FakeBudgetEvaluator()
                    ),
                    rate_limiter=(
                        FakeRateLimiter()
                    ),
                    clock=FakeClock(),
                )


if __name__ == "__main__":
    unittest.main()
