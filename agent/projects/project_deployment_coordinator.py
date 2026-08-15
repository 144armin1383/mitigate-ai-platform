from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

from agent.projects.project_adapter import (
    ProjectAdapterRegistry,
    ProjectDeploymentRequest,
    ProjectDeploymentResult,
)
from agent.projects.wordpress_project_adapter import WordPressProjectAdapter


class ProjectDeploymentCoordinator:
    """Run an accepted revision through the matching MITIGATE Project Adapter."""

    def __init__(
        self,
        *,
        repository_root: str | Path,
        registry: ProjectAdapterRegistry | None = None,
    ) -> None:
        self.repository_root = Path(repository_root).expanduser().resolve()
        self.registry = registry or ProjectAdapterRegistry(
            [WordPressProjectAdapter()]
        )

    def deploy(
        self,
        *,
        project_id: str,
        project_type: str,
        revision: str,
        changed_files: tuple[str, ...],
        routine_operations: tuple[str, ...],
        deployment_target: str = "",
        metadata: Mapping[str, object] | None = None,
    ) -> ProjectDeploymentResult:
        adapter = self.registry.choose(project_type)
        return adapter.deploy(
            ProjectDeploymentRequest(
                project_id=str(project_id or "").strip() or "default",
                repository_root=str(self.repository_root),
                revision=revision,
                changed_files=changed_files,
                routine_operations=routine_operations,
                deployment_target=(
                    str(deployment_target or "").strip()
                    or os.environ.get("MITIGATE_WORDPRESS_HEALTH_URL", "")
                ),
                metadata=dict(metadata or {}),
            )
        )


__all__ = ["ProjectDeploymentCoordinator"]
