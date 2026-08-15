from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Protocol, Sequence


@dataclass(frozen=True)
class ProjectDeploymentRequest:
    project_id: str
    repository_root: str
    revision: str
    changed_files: tuple[str, ...] = ()
    routine_operations: tuple[str, ...] = ()
    deployment_target: str = ""
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ProjectDeploymentResult:
    success: bool
    adapter: str
    deployed_revision: str
    changed_files: tuple[str, ...] = ()
    actions: tuple[str, ...] = ()
    health_ok: bool | None = None
    health_url: str | None = None
    diagnostics: tuple[str, ...] = ()
    rollback_revision: str | None = None


class ProjectAdapter(Protocol):
    """MITIGATE-owned managed-project operations boundary.

    Execution providers author code in disposable workspaces. Project adapters
    own bounded deployment/runtime operations after Git governance has accepted
    a revision. Adapters never accept raw shell commands from a mission.
    """

    @property
    def name(self) -> str:
        ...

    def supports(self, project_type: str) -> bool:
        ...

    def deploy(self, request: ProjectDeploymentRequest) -> ProjectDeploymentResult:
        ...

    def verify_health(self, request: ProjectDeploymentRequest) -> ProjectDeploymentResult:
        ...

    def rollback(self, request: ProjectDeploymentRequest, revision: str) -> ProjectDeploymentResult:
        ...


class ProjectAdapterRegistry:
    def __init__(self, adapters: Sequence[ProjectAdapter] = ()) -> None:
        self._adapters = list(adapters)

    def register(self, adapter: ProjectAdapter) -> None:
        self._adapters.append(adapter)

    def choose(self, project_type: str) -> ProjectAdapter:
        for adapter in self._adapters:
            if adapter.supports(project_type):
                return adapter
        raise LookupError(f"no project adapter for type: {project_type}")


__all__ = [
    "ProjectAdapter",
    "ProjectAdapterRegistry",
    "ProjectDeploymentRequest",
    "ProjectDeploymentResult",
]
