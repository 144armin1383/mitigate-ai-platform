from __future__ import annotations

from dataclasses import dataclass

from .observations import TechnologyObservation


@dataclass(frozen=True)
class TechnologyScore:
    relevance: int
    capability_novelty: int
    architectural_compatibility: int
    independence_potential: int
    operational_value: int
    security_risk_penalty: int
    external_dependency_penalty: int
    total: int
    evaluation_candidate: bool


class DeterministicTechnologyScorer:
    def __init__(
        self,
        *,
        evaluation_threshold: int = 60,
    ) -> None:
        if not (
            0
            <= evaluation_threshold
            <= 100
        ):
            raise ValueError(
                "invalid_evaluation_threshold"
            )

        self.evaluation_threshold = (
            evaluation_threshold
        )

    @staticmethod
    def _clamp(
        value: int,
    ) -> int:
        return max(
            0,
            min(
                100,
                int(value),
            ),
        )

    def score(
        self,
        observation: TechnologyObservation,
        *,
        known_capabilities: tuple[
            str,
            ...
        ] = (),
    ) -> TechnologyScore:

        metadata = dict(
            observation.metadata
        )

        known = set(
            known_capabilities
        )

        observed = set(
            observation.capabilities
        )

        novel = observed - known

        relevance = self._clamp(
            int(
                metadata.get(
                    "relevance",
                    70 if observed else 40,
                )
            )
        )

        capability_novelty = (
            self._clamp(
                min(
                    100,
                    len(novel) * 25,
                )
            )
        )

        architectural_compatibility = (
            self._clamp(
                int(
                    metadata.get(
                        "architectural_compatibility",
                        70,
                    )
                )
            )
        )

        independence_potential = (
            self._clamp(
                int(
                    metadata.get(
                        "independence_potential",
                        80,
                    )
                )
            )
        )

        operational_value = self._clamp(
            int(
                metadata.get(
                    "operational_value",
                    60,
                )
            )
        )

        security_risk_penalty = (
            self._clamp(
                int(
                    metadata.get(
                        "security_risk_penalty",
                        0,
                    )
                )
            )
        )

        external_dependency_penalty = (
            self._clamp(
                int(
                    metadata.get(
                        "external_dependency_penalty",
                        0,
                    )
                )
            )
        )

        positive = (
            relevance * 25
            + capability_novelty * 20
            + architectural_compatibility * 20
            + independence_potential * 20
            + operational_value * 15
        ) / 100

        penalties = (
            security_risk_penalty * 0.5
            + external_dependency_penalty * 0.5
        )

        total = self._clamp(
            round(
                positive
                - penalties
            )
        )

        return TechnologyScore(
            relevance=relevance,
            capability_novelty=(
                capability_novelty
            ),
            architectural_compatibility=(
                architectural_compatibility
            ),
            independence_potential=(
                independence_potential
            ),
            operational_value=(
                operational_value
            ),
            security_risk_penalty=(
                security_risk_penalty
            ),
            external_dependency_penalty=(
                external_dependency_penalty
            ),
            total=total,
            evaluation_candidate=(
                total
                >= self.evaluation_threshold
            ),
        )
