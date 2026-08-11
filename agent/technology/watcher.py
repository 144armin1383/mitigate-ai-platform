from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from .observations import (
    TechnologyObservation,
)
from .registry import (
    TechnologyRecord,
    TechnologyRegistry,
    TechnologyState,
)
from .scoring import (
    DeterministicTechnologyScorer,
    TechnologyScore,
)
from .sources import TechnologySource


@dataclass(frozen=True)
class TechnologyChange:
    technology_id: str
    change_type: str
    detail: str


@dataclass(frozen=True)
class TechnologyEvaluationCandidate:
    technology_id: str
    score: TechnologyScore
    observed_version: str | None


@dataclass(frozen=True)
class TechnologyWatchReport:
    observations_seen: int
    technologies_discovered: int
    versions_changed: int
    capabilities_discovered: int
    unchanged_observations: int
    source_failures: tuple[str, ...]
    changes: tuple[
        TechnologyChange,
        ...
    ]
    evaluation_candidates: tuple[
        TechnologyEvaluationCandidate,
        ...
    ]


class TechnologyWatcher:
    def __init__(
        self,
        *,
        registry: TechnologyRegistry,
        sources: Iterable[
            TechnologySource
        ],
        scorer: (
            DeterministicTechnologyScorer
        ),
        event_sink: Any | None = None,
        clock: Any | None = None,
    ) -> None:
        self._registry = registry
        self._sources = tuple(
            sources
        )
        self._scorer = scorer
        self._event_sink = (
            event_sink
        )
        self._clock = clock

    def _now(self) -> str:
        if (
            self._clock is not None
            and hasattr(
                self._clock,
                "now",
            )
        ):
            value = (
                self._clock.now()
            )

            if isinstance(
                value,
                datetime,
            ):
                if (
                    value.tzinfo
                    is None
                ):
                    value = (
                        value.replace(
                            tzinfo=timezone.utc
                        )
                    )

                return (
                    value
                    .astimezone(
                        timezone.utc
                    )
                    .isoformat()
                    .replace(
                        "+00:00",
                        "Z",
                    )
                )

            return str(value)

        return (
            datetime.now(
                timezone.utc
            )
            .isoformat()
            .replace(
                "+00:00",
                "Z",
            )
        )

    def _emit(
        self,
        event_type: str,
        **payload: Any,
    ) -> None:
        if self._event_sink is None:
            return

        safe = {}

        allowed = {
            "technology_id",
            "source_id",
            "change_type",
            "score",
            "count",
        }

        for key, value in (
            payload.items()
        ):
            if key in allowed:
                safe[key] = value

        try:
            self._event_sink.emit(
                event_type,
                safe,
            )
        except Exception:
            pass

    def run_cycle(
        self,
    ) -> TechnologyWatchReport:

        self._emit(
            "technology_watch_cycle_started"
        )

        observations_seen = 0
        technologies_discovered = 0
        versions_changed = 0
        capabilities_discovered = 0
        unchanged_observations = 0

        source_failures = []
        changes = []
        evaluation_candidates = []

        for source in self._sources:

            source_id = str(
                source.source_id
            )

            try:
                observations = tuple(
                    source.observe()
                )
            except Exception:
                source_failures.append(
                    source_id
                )

                self._emit(
                    "technology_source_failed",
                    source_id=source_id,
                )

                continue

            for observation in (
                observations
            ):
                observations_seen += 1

                result = (
                    self._process_observation(
                        observation
                    )
                )

                technologies_discovered += (
                    result[
                        "technologies_discovered"
                    ]
                )

                versions_changed += (
                    result[
                        "versions_changed"
                    ]
                )

                capabilities_discovered += (
                    result[
                        "capabilities_discovered"
                    ]
                )

                unchanged_observations += (
                    result[
                        "unchanged_observations"
                    ]
                )

                changes.extend(
                    result["changes"]
                )

                candidate = result.get(
                    "evaluation_candidate"
                )

                if candidate is not None:
                    evaluation_candidates.append(
                        candidate
                    )

        report = TechnologyWatchReport(
            observations_seen=(
                observations_seen
            ),
            technologies_discovered=(
                technologies_discovered
            ),
            versions_changed=(
                versions_changed
            ),
            capabilities_discovered=(
                capabilities_discovered
            ),
            unchanged_observations=(
                unchanged_observations
            ),
            source_failures=tuple(
                source_failures
            ),
            changes=tuple(
                changes
            ),
            evaluation_candidates=tuple(
                evaluation_candidates
            ),
        )

        self._emit(
            "technology_watch_cycle_completed",
            count=observations_seen,
        )

        return report

    def _process_observation(
        self,
        observation: TechnologyObservation,
    ) -> dict[str, Any]:

        discovered = 0
        version_changes = 0
        capability_changes = 0
        unchanged = 0
        changes = []

        try:
            record = self._registry.get(
                observation.technology_id
            )
            new_technology = False
        except KeyError:
            new_technology = True

            record = TechnologyRecord(
                technology_id=(
                    observation.technology_id
                ),
                name=observation.name,
                kind=observation.kind,
                state=(
                    TechnologyState.DISCOVERED
                ),
                source_url=(
                    observation
                    .source_reference
                ),
                external_runtime_required=False,
                capabilities=list(
                    observation.capabilities
                ),
                metadata={
                    "first_observed_at":
                        observation.observed_at
                        or self._now(),
                },
            )

            self._registry.register(
                record
            )

            discovered = 1

            changes.append(
                TechnologyChange(
                    technology_id=(
                        observation
                        .technology_id
                    ),
                    change_type=(
                        "technology_discovered"
                    ),
                    detail="discovered",
                )
            )

            self._emit(
                "technology_discovered",
                technology_id=(
                    observation
                    .technology_id
                ),
            )

        previous_version = (
            record.latest_observed_version
        )

        if (
            observation.observed_version
            is not None
            and (
                previous_version
                != observation.observed_version
            )
        ):
            self._registry.observe_version(
                observation.technology_id,
                observation.observed_version,
                metadata={
                    "source_reference":
                        observation
                        .source_reference,
                },
            )

            version_changes = 1

            changes.append(
                TechnologyChange(
                    technology_id=(
                        observation
                        .technology_id
                    ),
                    change_type=(
                        "version_observed"
                    ),
                    detail=(
                        observation
                        .observed_version
                    ),
                )
            )

            self._emit(
                "technology_version_observed",
                technology_id=(
                    observation
                    .technology_id
                ),
            )

        current_capabilities = set(
            record.capabilities
        )

        observed_capabilities = set(
            observation.capabilities
        )

        newly_discovered = sorted(
            observed_capabilities
            - current_capabilities
        )

        if newly_discovered:
            merged = sorted(
                current_capabilities
                | observed_capabilities
            )

            self._registry.update(
                observation.technology_id,
                capabilities=merged,
            )

            capability_changes = len(
                newly_discovered
            )

            for capability in (
                newly_discovered
            ):
                changes.append(
                    TechnologyChange(
                        technology_id=(
                            observation
                            .technology_id
                        ),
                        change_type=(
                            "capability_discovered"
                        ),
                        detail=capability,
                    )
                )

                self._emit(
                    "technology_capability_discovered",
                    technology_id=(
                        observation
                        .technology_id
                    ),
                )

        if (
            not new_technology
            and version_changes == 0
            and capability_changes == 0
        ):
            unchanged = 1

        refreshed = self._registry.get(
            observation.technology_id
        )

        score = self._scorer.score(
            observation,
            known_capabilities=tuple(
                refreshed
                .adopted_capabilities
            ),
        )

        candidate = None

        if score.evaluation_candidate:
            candidate = (
                TechnologyEvaluationCandidate(
                    technology_id=(
                        observation
                        .technology_id
                    ),
                    score=score,
                    observed_version=(
                        observation
                        .observed_version
                    ),
                )
            )

            self._emit(
                "technology_evaluation_candidate",
                technology_id=(
                    observation
                    .technology_id
                ),
                score=score.total,
            )

        return {
            "technologies_discovered":
                discovered,
            "versions_changed":
                version_changes,
            "capabilities_discovered":
                capability_changes,
            "unchanged_observations":
                unchanged,
            "changes":
                changes,
            "evaluation_candidate":
                candidate,
        }
