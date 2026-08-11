from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.technology.observations import (
    TechnologyObservation,
)
from agent.technology.registry import (
    TechnologyKind,
    TechnologyRecord,
    TechnologyRegistry,
    TechnologyState,
)
from agent.technology.scoring import (
    DeterministicTechnologyScorer,
)
from agent.technology.sources import (
    InMemoryTechnologySource,
)
from agent.technology.watcher import (
    TechnologyWatcher,
)


class FakeEventSink:
    def __init__(
        self,
        fail=False,
    ):
        self.events = []
        self.fail = fail

    def emit(
        self,
        event_type,
        payload,
    ):
        if self.fail:
            raise RuntimeError(
                "event sink failed"
            )

        self.events.append(
            (
                event_type,
                payload,
            )
        )


class TechnologyWatcherTests(
    unittest.TestCase
):

    def _observation(
        self,
        *,
        technology_id="ruflo",
        version="1.0.0",
        capabilities=(
            "swarm",
        ),
        metadata=None,
    ):
        return TechnologyObservation(
            technology_id=technology_id,
            name="Ruflo",
            kind=(
                TechnologyKind.ORCHESTRATOR
            ),
            observed_version=version,
            source_reference=(
                "source://ruflo"
            ),
            capabilities=tuple(
                capabilities
            ),
            metadata=metadata or {},
            observed_at=(
                "2026-08-11T19:00:00Z"
            ),
        )

    def _watcher(
        self,
        registry,
        observations,
        *,
        threshold=60,
        fail_source=False,
        event_sink=None,
    ):
        source = (
            InMemoryTechnologySource(
                source_id="memory-source",
                observations=observations,
                fail=fail_source,
            )
        )

        return TechnologyWatcher(
            registry=registry,
            sources=(source,),
            scorer=(
                DeterministicTechnologyScorer(
                    evaluation_threshold=(
                        threshold
                    )
                )
            ),
            event_sink=event_sink,
        )

    def test_discovers_unknown_technology(
        self,
    ):
        registry = TechnologyRegistry()

        watcher = self._watcher(
            registry,
            (
                self._observation(),
            ),
        )

        report = watcher.run_cycle()

        self.assertEqual(
            report.technologies_discovered,
            1,
        )

        record = registry.get(
            "ruflo"
        )

        self.assertEqual(
            record.state,
            TechnologyState.DISCOVERED,
        )

        self.assertFalse(
            record.external_runtime_required
        )

    def test_existing_technology_observation(
        self,
    ):
        registry = TechnologyRegistry()

        registry.register(
            TechnologyRecord(
                technology_id="ruflo",
                name="Ruflo",
                kind=(
                    TechnologyKind.ORCHESTRATOR
                ),
            )
        )

        watcher = self._watcher(
            registry,
            (
                self._observation(),
            ),
        )

        report = watcher.run_cycle()

        self.assertEqual(
            report.technologies_discovered,
            0,
        )

    def test_version_change(
        self,
    ):
        registry = TechnologyRegistry()

        watcher = self._watcher(
            registry,
            (
                self._observation(
                    version="1.0.0"
                ),
            ),
        )

        watcher.run_cycle()

        watcher2 = self._watcher(
            registry,
            (
                self._observation(
                    version="1.1.0"
                ),
            ),
        )

        report = watcher2.run_cycle()

        self.assertEqual(
            report.versions_changed,
            1,
        )

        self.assertEqual(
            registry.get(
                "ruflo"
            ).latest_observed_version,
            "1.1.0",
        )

    def test_capability_discovery(
        self,
    ):
        registry = TechnologyRegistry()

        watcher = self._watcher(
            registry,
            (
                self._observation(
                    capabilities=(
                        "swarm",
                    )
                ),
            ),
        )

        watcher.run_cycle()

        watcher2 = self._watcher(
            registry,
            (
                self._observation(
                    capabilities=(
                        "swarm",
                        "consensus",
                    )
                ),
            ),
        )

        report = watcher2.run_cycle()

        self.assertEqual(
            report.capabilities_discovered,
            1,
        )

        self.assertIn(
            "consensus",
            registry.get(
                "ruflo"
            ).capabilities,
        )

    def test_identical_observation_is_idempotent(
        self,
    ):
        registry = TechnologyRegistry()

        observation = (
            self._observation()
        )

        watcher = self._watcher(
            registry,
            (observation,),
        )

        watcher.run_cycle()

        report = watcher.run_cycle()

        self.assertEqual(
            report.technologies_discovered,
            0,
        )

        self.assertEqual(
            report.versions_changed,
            0,
        )

        self.assertEqual(
            report.capabilities_discovered,
            0,
        )

        self.assertEqual(
            report.unchanged_observations,
            1,
        )

    def test_deterministic_scoring(
        self,
    ):
        scorer = (
            DeterministicTechnologyScorer()
        )

        observation = (
            self._observation(
                capabilities=(
                    "swarm",
                    "consensus",
                ),
            )
        )

        first = scorer.score(
            observation
        )

        second = scorer.score(
            observation
        )

        self.assertEqual(
            first,
            second,
        )

    def test_evaluation_threshold_behavior(
        self,
    ):
        registry = TechnologyRegistry()

        watcher = self._watcher(
            registry,
            (
                self._observation(
                    metadata={
                        "relevance": 100,
                        "architectural_compatibility":
                            100,
                        "independence_potential":
                            100,
                        "operational_value":
                            100,
                    }
                ),
            ),
            threshold=50,
        )

        report = watcher.run_cycle()

        self.assertEqual(
            len(
                report.evaluation_candidates
            ),
            1,
        )

    def test_source_failure_isolated(
        self,
    ):
        registry = TechnologyRegistry()

        good = InMemoryTechnologySource(
            source_id="good",
            observations=(
                self._observation(),
            ),
        )

        bad = InMemoryTechnologySource(
            source_id="bad",
            fail=True,
        )

        watcher = TechnologyWatcher(
            registry=registry,
            sources=(
                bad,
                good,
            ),
            scorer=(
                DeterministicTechnologyScorer()
            ),
        )

        report = watcher.run_cycle()

        self.assertIn(
            "bad",
            report.source_failures,
        )

        self.assertEqual(
            report.technologies_discovered,
            1,
        )

    def test_event_sink_failure_isolated(
        self,
    ):
        registry = TechnologyRegistry()

        watcher = self._watcher(
            registry,
            (
                self._observation(),
            ),
            event_sink=(
                FakeEventSink(
                    fail=True
                )
            ),
        )

        report = watcher.run_cycle()

        self.assertEqual(
            report.observations_seen,
            1,
        )

    def test_registry_persistence_compatibility(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            path = (
                Path(td)
                / "technology.json"
            )

            registry = (
                TechnologyRegistry(
                    path
                )
            )

            watcher = self._watcher(
                registry,
                (
                    self._observation(),
                ),
            )

            watcher.run_cycle()

            loaded = (
                TechnologyRegistry(
                    path
                )
            )

            self.assertEqual(
                loaded.get(
                    "ruflo"
                ).latest_observed_version,
                "1.0.0",
            )

    def test_no_network_or_subprocess_imports(
        self,
    ):
        import agent.technology.watcher as watcher_module
        import agent.technology.sources as source_module

        forbidden = {
            "requests",
            "httpx",
            "aiohttp",
            "subprocess",
        }

        combined = set(
            watcher_module.__dict__
        ) | set(
            source_module.__dict__
        )

        self.assertTrue(
            forbidden.isdisjoint(
                combined
            )
        )

    def test_watcher_has_no_queue_or_mission_execution(
        self,
    ):
        import inspect

        source = inspect.getsource(
            TechnologyWatcher
        )

        self.assertNotIn(
            "BackgroundWorker",
            source,
        )

        self.assertNotIn(
            "MissionQueue",
            source,
        )

        self.assertNotIn(
            ".enqueue(",
            source,
        )

        self.assertNotIn(
            "subprocess",
            source,
        )


if __name__ == "__main__":
    unittest.main()
