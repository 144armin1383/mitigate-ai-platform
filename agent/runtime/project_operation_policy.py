from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class ProjectOperationDecision:
    """Governance decision for project-owned runtime/deployment operations.

    Repository write scope is handled separately by ProjectScopeResolver. This
    policy answers which project-owned operations may be planned without
    interrupting the operator for path-by-path authorization, and which requests
    still cross a protected trust boundary.
    """

    project_kind: str
    routine_operations: tuple[str, ...]
    protected_operations: tuple[str, ...]
    rationale: tuple[str, ...]

    @property
    def requires_explicit_authorization(self) -> bool:
        return bool(self.protected_operations)


class ProjectOperationPolicy:
    """Classify routine managed-project operations before execution.

    The policy grants named capabilities, never arbitrary commands. External
    execution engines still receive only disposable repository workspaces.
    MITIGATE-owned Project Adapters are responsible for translating a routine
    capability into bounded host, WP-CLI, filesystem or database operations.
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

    _PROTECTED_ACTIONS: tuple[tuple[str, str], ...] = (
        (r"\b(?:modify|change|edit|configure|reload|restart|install|update|disable|enable)\b.{0,40}\bnginx\b", "host.nginx_global"),
        (r"\bnginx\b.{0,40}\b(?:modify|change|edit|configure|reload|restart|install|update|disable|enable)\b", "host.nginx_global"),
        (r"\b(?:modify|change|edit|configure|reload|restart|install|update|disable|enable|reconfigure)\b.{0,40}\bsystemd\b", "host.systemd_global"),
        (r"\bsystemd\b.{0,40}\b(?:modify|change|edit|configure|reload|restart|install|update|disable|enable|reconfigure)\b", "host.systemd_global"),
        (r"\b(?:modify|change|edit|configure|disable|enable)\b.{0,40}\b(?:firewall|ufw)\b", "host.firewall"),
        (r"\b(?:firewall|ufw)\b.{0,40}\b(?:modify|change|edit|configure|disable|enable)\b", "host.firewall"),
        (r"\b(?:modify|change|edit)\b.{0,40}\bsudoers\b", "host.privilege"),
        (r"\bprivilege escalation\b", "host.privilege"),
        (r"\b(?:read|show|print|expose|change|rotate|replace)\b.{0,40}\b(?:root password|api key|secret|credential)\b", "host.secrets"),
        (r"\b(?:modify|change|edit|replace)\b.{0,40}\bwp-config\.php\b", "wordpress.core_config"),
        (r"\b(?:modify|change|edit|patch|replace|update)\b.{0,40}\bwordpress core\b", "wordpress.core"),
        (r"\b(?:modify|change|edit|patch|replace)\b.{0,40}\b(?:wp-admin|wp-includes)\b", "wordpress.core"),
        (r"\b(?:modify|change|edit|patch|replace|update)\b.{0,40}\bparent theme\b", "wordpress.parent_theme"),
        (r"\bdrop\s+database\b", "database.destructive"),
        (r"\bdrop\s+table\b", "database.destructive"),
        (r"\btruncate\s+table\b", "database.destructive"),
        (r"\bdelete\s+all\b.{0,40}\b(?:records|rows|data|users|orders|posts)\b", "database.destructive"),
        (r"\b(?:modify|change|weaken|disable|bypass)\b.{0,50}\bmitigate governance\b", "mitigate.trust_boundary"),
        (r"\b(?:modify|change|weaken|disable|bypass)\b.{0,50}\bsecurity policy\b", "mitigate.trust_boundary"),
    )

    _NEGATION_MARKERS = (
        "do not ",
        "don't ",
        "must not ",
        "should not ",
        "without ",
        "never ",
        "avoid ",
        "no ",
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

    @staticmethod
    def _clauses(text: str) -> tuple[str, ...]:
        # Punctuation is a reliable boundary for the natural-language request
        # forms used by the planner. Keep conjunctions inside a clause so
        # compound requests such as "restart and reconfigure systemd" remain
        # detectable, while comma-separated prohibitions stay isolated.
        return tuple(
            part.strip()
            for part in re.split(r"[.;,\n]+", text.lower())
            if part.strip()
        )

    @classmethod
    def _protected_operations(cls, objective: str) -> tuple[tuple[str, str], ...]:
        found: list[tuple[str, str]] = []
        for clause in cls._clauses(objective):
            if any(marker in clause for marker in cls._NEGATION_MARKERS):
                continue
            for pattern, capability in cls._PROTECTED_ACTIONS:
                if not re.search(pattern, clause, re.DOTALL):
                    continue
                item = (pattern, capability)
                if item not in found:
                    found.append(item)
        return tuple(found)

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
        if "mitigate core" in lower or "mitigate runtime" in lower:
            return "mitigate-platform"
        if any(marker in lower for marker in cls._WORDPRESS_MARKERS):
            return "wordpress"
        if task_type in {"wordpress", "content", "seo"}:
            return "wordpress"
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

        protected: list[str] = []
        rationale: list[str] = [f"project_kind:{project_kind}"]
        for _pattern, capability in cls._protected_operations(objective):
            if capability not in protected:
                protected.append(capability)
                rationale.append(f"protected_action:{capability}")

        if project_kind == "wordpress":
            routine = list(cls.WORDPRESS_ROUTINE)
            rationale.append("managed_wordpress_routine_operations")
        elif project_kind == "mitigate-platform":
            routine = ["project.repo_write", "project.validate"]
            rationale.append("mitigate_self_maintenance_no_host_grant")
        else:
            routine = list(cls.GENERIC_ROUTINE)
            rationale.append("generic_project_routine_operations")

        return ProjectOperationDecision(
            project_kind=project_kind,
            routine_operations=tuple(dict.fromkeys(routine)),
            protected_operations=tuple(dict.fromkeys(protected)),
            rationale=tuple(rationale),
        )


__all__ = ["ProjectOperationDecision", "ProjectOperationPolicy"]
