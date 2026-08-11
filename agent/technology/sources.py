from __future__ import annotations

from typing import Iterable, Protocol, Tuple

from .observations import TechnologyObservation


class TechnologySource(Protocol):
    @property
    def source_id(self) -> str:
        ...

    def observe(
        self,
    ) -> Iterable[TechnologyObservation]:
        ...


class InMemoryTechnologySource:
    def __init__(
        self,
        *,
        source_id: str,
        observations: Iterable[
            TechnologyObservation
        ] = (),
        fail: bool = False,
    ) -> None:
        value = str(
            source_id
        ).strip()

        if not value:
            raise ValueError(
                "source_id is required"
            )

        self._source_id = value
        self._observations: Tuple[
            TechnologyObservation,
            ...
        ] = tuple(observations)
        self._fail = bool(fail)

    @property
    def source_id(self) -> str:
        return self._source_id

    def observe(
        self,
    ) -> Iterable[TechnologyObservation]:
        if self._fail:
            raise RuntimeError(
                "source_failed"
            )

        return tuple(
            self._observations
        )
