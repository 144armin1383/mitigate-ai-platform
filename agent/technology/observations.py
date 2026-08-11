from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Tuple

from .registry import TechnologyKind


def validate_technology_id(value: str) -> None:
    if not value:
        raise ValueError("technology_id is required")

    allowed = set(
        "abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "0123456789-_"
    )

    if any(ch not in allowed for ch in value):
        raise ValueError(
            "technology_id contains invalid characters"
        )


@dataclass(frozen=True)
class TechnologyObservation:
    technology_id: str
    name: str
    kind: TechnologyKind
    observed_version: str | None = None
    source_reference: str | None = None
    capabilities: Tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )
    observed_at: str | None = None

    def __post_init__(self) -> None:
        validate_technology_id(
            self.technology_id
        )

        if not self.name.strip():
            raise ValueError(
                "name is required"
            )

        if self.observed_version is not None:
            if not str(
                self.observed_version
            ).strip():
                raise ValueError(
                    "observed_version cannot be empty"
                )

        clean_caps = []

        for capability in self.capabilities:
            value = str(
                capability
            ).strip()

            if not value:
                raise ValueError(
                    "capabilities cannot contain empty values"
                )

            clean_caps.append(value)

        object.__setattr__(
            self,
            "capabilities",
            tuple(
                dict.fromkeys(
                    clean_caps
                )
            ),
        )
