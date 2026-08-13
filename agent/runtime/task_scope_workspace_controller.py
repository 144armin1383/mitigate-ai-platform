from __future__ import annotations

from typing import Any, Mapping

from agent.runtime.managed_workspace_mission_controller import (
    ManagedWorkspaceMissionController,
)


_DEFAULT_SCOPES: dict[str, list[str]] = {
    "backend": ["agent"],
    "api": ["agent"],
    "testing": ["agent"],
    "test": ["agent"],
    "tests": ["agent"],
    "bugfix": ["agent"],
    "maintenance": ["agent"],
    "refactor": ["agent"],
    "security": ["agent"],
    "database": ["agent"],
    "fullstack": ["agent"],
    "infrastructure": ["agent"],
    "documentation": ["docs"],
    "frontend": ["agent", "wordpress"],
    "wordpress": ["wordpress"],
    "seo": ["wordpress", "docs"],
    "content": ["wordpress", "docs"],
    "github": [".github", "docs", "agent"],
}


class TaskScopeWorkspaceController(ManagedWorkspaceMissionController):
    """Apply conservative task-type scopes when the planner names no files."""

    @classmethod
    def _context(cls, text: str) -> Mapping[str, Any]:
        context = dict(super()._context(text))
        deliverables = context.get("deliverables")
        if isinstance(deliverables, list) and any(
            isinstance(item, str) and item.strip()
            for item in deliverables
        ):
            return context

        task_type = cls._field(text, "Task Type").strip().lower()
        defaults = _DEFAULT_SCOPES.get(task_type)
        if defaults:
            context["deliverables"] = list(defaults)
        return context


__all__ = ["TaskScopeWorkspaceController"]
