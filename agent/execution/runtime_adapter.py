from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Protocol, Sequence


class RuntimeStatus(str, Enum):
    """Normalized execution states owned by MITIGATE, not by any provider."""

    succeeded = "succeeded"
    failed = "failed"
    blocked = "blocked"
    cancelled = "cancelled"
    timed_out = "timed_out"
    unavailable = "unavailable"


@dataclass(frozen=True)
class RuntimeCapabilities:
    """Provider capabilities used by the MITIGATE routing layer."""

    coding: bool = False
    terminal: bool = False
    file_editing: bool = False
    tests: bool = False
    browser: bool = False
    mcp: bool = False
    skills: bool = False
    multi_agent: bool = False
    persistent_sessions: bool = False
    isolated_workspace: bool = False
    remote_execution: bool = False


@dataclass(frozen=True)
class ExecutionRequest:
    """
    Provider-neutral task request.

    This object deliberately contains mission intent and execution boundaries,
    but no provider-specific session identifiers or configuration. MITIGATE
    remains the authority for scope, policy and acceptance criteria.
    """

    request_id: str
    mission_id: str
    objective: str
    repository_root: str
    base_revision: str
    allowed_paths: tuple[str, ...] = ()
    denied_paths: tuple[str, ...] = ()
    acceptance_criteria: tuple[str, ...] = ()
    timeout_seconds: int = 1800
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExecutionEvidence:
    """Bounded, provider-neutral evidence returned to MITIGATE."""

    summary: str = ""
    diagnostics: tuple[str, ...] = ()
    tests_run: tuple[str, ...] = ()
    test_results: tuple[str, ...] = ()
    changed_files: tuple[str, ...] = ()
    commit_sha: str | None = None
    branch: str | None = None
    provider_run_id: str | None = None
    provider_metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExecutionResult:
    """Normalized result consumed by MITIGATE governance and review."""

    status: RuntimeStatus
    provider: str
    evidence: ExecutionEvidence = field(default_factory=ExecutionEvidence)
    retryable: bool = False
    reason: str | None = None


class RuntimeAdapter(Protocol):
    """
    Replaceable execution-provider contract.

    Implementations may use OpenHands, OpenClaw, Ruflo or another runtime, but
    must not own MITIGATE mission state, approval policy, project memory or the
    canonical Git history.
    """

    @property
    def name(self) -> str:
        ...

    def capabilities(self) -> RuntimeCapabilities:
        ...

    def healthcheck(self) -> Mapping[str, Any]:
        ...

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        ...

    def cancel(self, provider_run_id: str) -> bool:
        ...


class RuntimeRegistry:
    """Small provider registry that keeps external runtimes optional."""

    def __init__(self, adapters: Sequence[RuntimeAdapter] = ()) -> None:
        self._adapters: dict[str, RuntimeAdapter] = {}
        for adapter in adapters:
            self.register(adapter)

    def register(self, adapter: RuntimeAdapter) -> None:
        name = str(adapter.name).strip().lower()
        if not name:
            raise ValueError("runtime adapter name must not be empty")
        if name in self._adapters:
            raise ValueError(f"runtime adapter already registered: {name}")
        self._adapters[name] = adapter

    def get(self, name: str) -> RuntimeAdapter:
        key = str(name).strip().lower()
        try:
            return self._adapters[key]
        except KeyError as exc:
            raise KeyError(f"unknown runtime adapter: {key}") from exc

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._adapters))

    def choose(
        self,
        *,
        require: RuntimeCapabilities,
        preferred: Sequence[str] = (),
    ) -> RuntimeAdapter:
        """Choose a healthy adapter satisfying every requested capability."""

        ordered_names = [
            *(str(name).strip().lower() for name in preferred),
            *self.names(),
        ]

        seen: set[str] = set()

        for name in ordered_names:
            if not name or name in seen or name not in self._adapters:
                continue
            seen.add(name)

            adapter = self._adapters[name]
            caps = adapter.capabilities()

            required_fields = (
                "coding",
                "terminal",
                "file_editing",
                "tests",
                "browser",
                "mcp",
                "skills",
                "multi_agent",
                "persistent_sessions",
                "isolated_workspace",
                "remote_execution",
            )

            if any(
                getattr(require, field_name)
                and not getattr(caps, field_name)
                for field_name in required_fields
            ):
                continue

            health = adapter.healthcheck()
            if bool(health.get("available", False)):
                return adapter

        raise LookupError("no healthy runtime adapter satisfies requirements")


__all__ = [
    "ExecutionEvidence",
    "ExecutionRequest",
    "ExecutionResult",
    "RuntimeAdapter",
    "RuntimeCapabilities",
    "RuntimeRegistry",
    "RuntimeStatus",
]
