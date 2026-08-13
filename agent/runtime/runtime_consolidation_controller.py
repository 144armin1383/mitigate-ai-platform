from __future__ import annotations

from agent.runtime.task_scope_workspace_controller import TaskScopeWorkspaceController


class RuntimeConsolidationController(TaskScopeWorkspaceController):
    """Compatibility name for the production consolidated runtime controller.

    The production worker historically imports RuntimeConsolidationController.
    Keep that stable entrypoint while delegating governed repository work to the
    durable-definition, managed-OpenHands, disposable-worktree controller.
    External OpenClaw and Ruflo capabilities remain available through the
    replaceable MITIGATE MCP/runtime adapters; coding authority stays with the
    isolated software-engineering path.
    """


__all__ = ["RuntimeConsolidationController"]
