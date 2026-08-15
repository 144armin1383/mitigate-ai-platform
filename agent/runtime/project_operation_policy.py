from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class ProjectOperationDecision:
    """Governance decision for project-owned runtime/deployment operations.

    Repository write scope is handled separately by ProjectScopeResolver.  This
    policy answers a different question: which *project-owned* operations may be
    planned without stopping the user for path-by-path authorization, and which
    requests still cross a protected trust boundary.
    """

    project_kind: str
    routine_operations: tuple[str, ...]
    protected_operations: tuple[str, ...]
    rationale: tuple[str, ...]

    @property
    def requires_explicit_authorization(self) -> bool:
        return bool(self.protected_operations)


class ProjectOperationPolicy:
    """Classify ordinary managed-project operations before execution.

    The contract is deliberately capability-based rather than command-based.
    External execution engines never gain arbitrary host access from this
    policy.  MITIGATE-owned Project Adapters remain responsible for translating
    an authorized capability into bounded WP-CLI/filesystem/database actions.
    """

    WORDPRESS_ROUTINE = (
        "project.repo_write",
        "wordpress.page_content",
        "wordpress.plugin_owned_schema",
        "wordpress.plugin_owned_options",
        "wordpress.plugin_activate",
        "wordpress.wp_cli_project_actions",
        "wordpress.private_project_storage",
        "project.deploy",
        "project.healthcheck",
    )

    GENERIC_ROUTINE = (
        "project.repo_write",
        "project.validate",
        "project.healthcheck",
    )

    _PROTECTED_MARKERS: tuple[tuple[str, str], ...] = (
        ("nginx", "host.nginx_global"),
        ("systemd", "host.systemd_global"),
        ("firewall", "host.firewall"),
        ("ufw", "host.firewall"),
        ("sudoers", "host.privilege"),
        ("privilege escalation", "host.privilege"),
        ("root password", "host.secrets"),
        ("api key", "host.secrets"),
        ("secret", "host.secrets"),
        ("wp-config.php", "wordpress.core_config"),
        ("wordpress core", "wordpress.core"),
        ("wp-admin", "wordpress.core"),
        ("wp-includes", "wordpress.core"),
        ("parent theme", "wordpress.parent_theme"),
        ("drop database", "database.destructive"),
        ("drop table", "database.destructive"),
        ("truncate table", "database.destructive"),
        ("delete all", "database.destructive"),
        ("mitigate governance", "mitigate.trust_boundary"),
        ("security policy", "mitigate.trust_boundary"),
    )

    _WORDPRESS_MARKERS = (
        "wordpress",
        "woocommerce",
        "wp-cli",
        "plugin",
        "shortcode",
        "job application",
        "recruitment",
        "careers",
        "martfury",
    )

    @classmethod
    def _project_kind(
        cls,
        *,
        task_type: str,
        objective: str,
        context: Mapping[str, Any],
        scope_project_kind: str | None,
    ) -> str:
        if scope_project_kind:
            return str(scope_project_kind).strip().lower()
        project_type = str(context.get("project_type") or "").strip().lower()
        if project_type in {"wordpress", "woocommerce", "wp"}:
            return "wordpress"
        lower = objective.lower()
        if any(marker in lower for marker in cls._WORDPRESS_MARKERS):
            return "wordpress"
        if task_type in {"wordpress", "content", "seo"}:
            return "wordpress"
        if "mitigate core" in lower or "mitigate runtime" in lower:
            return "mitigate-platform"
        return "generic"

    @classmethod
    def derive(
        cls,
        *,
        task_type: str,
        objective: str,
        context: Mapping[str, Any] | None = None,
        scope_project_kind: str | None = None,
    ) -> ProjectOperationDecision:
        task_type = str(task_type or "general").strip().lower()
        objective = str(objective or "")
        context = context or {}
        project_kind = cls._project_kind(
            task_type=task_type,
            objective=objective,
            context=context,
            scope_project_kind=scope_project_kind,
        )
        lower = objective.lower()

        protected: list[str] = []
        rationale: list[str] = [f"project_kind:{project_kind}"]
        for marker, capability in cls._PROTECTED_MARKERS:
            if marker in lower and capability not in protected:
                protected.append(capability)
                rationale.append(f"protected_marker:{marker}")

        if project_kind == "wordpress":
            routine = list(cls.WORDPRESS_ROUTINE)
            rationale.append("managed_wordpress_routine_operations")
        elif project_kind == "mitigate-platform":
            # Self-maintenance remains governed by the existing Core review
            # pipeline; do not silently grant host/deployment capabilities.
            routine = ["project.repo_write", "project.validate"]
            rationale.append("mitigate_self_maintenance_no_host_grant")
        else:
            routine = list(cls.GENERIC_ROUTINE)
            rationale.append("generic_project_routine_operations")

        # Protected capabilities are never simultaneously advertised as routine.
        protected_prefixes = {
            "host.",
            "database.destructive",
            "wordpress.core",
            "wordpress.core_config",
            "wordpress.parent_theme",
            "mitigate.trust_boundary",
        }
        routine = [
            item for item in routine
            if not any(item == prefix or item.startswith(prefix) for prefix in protected_prefixes)
        ]

        return ProjectOperationDecision(
            project_kind=project_kind,
            routine_operations=tuple(dict.fromkeys(routine)),
            protected_operations=tuple(dict.fromkeys(protected)),
            rationale=tuple(rationale),
        )


__all__ = ["ProjectOperationDecision", "ProjectOperationPolicy"]
