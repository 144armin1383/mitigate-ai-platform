from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class ProjectScopeDecision:
    """Least-privilege repository scope derived from project and mission intent."""

    allowed_paths: tuple[str, ...]
    denied_paths: tuple[str, ...]
    project_kind: str
    rationale: tuple[str, ...]


class ProjectScopeResolver:
    """Derive repository write scope before an external runtime executes.

    The resolver deliberately grants repository paths only. Live deployment,
    database mutation, secrets, Nginx/systemd and other host operations remain
    owned by MITIGATE Core and its deployment/policy layers.
    """

    _BASE_DENIED = (".git", ".env", "secrets")
    _WORDPRESS_DENIED = (
        "agent",
        ".github",
        "wordpress/wp-admin",
        "wordpress/wp-includes",
        "wordpress/wp-config.php",
    )
    _WORDPRESS_MARKERS = (
        "wordpress",
        "woocommerce",
        "wp-cli",
        "wp-content",
        "plugin",
        "shortcode",
        "martfury",
        "recruitment form",
        "job application",
        "careers page",
    )
    _PLATFORM_MARKERS = (
        "mitigate core",
        "mitigate runtime",
        "mitigate's mission scope",
        "mitigate mission scope",
        "runtime architecture",
        "governance",
        "scope resolution",
        "scope derivation",
        "project adapter",
        "execution adapter",
    )

    @staticmethod
    def _clean_relative_path(value: str) -> str | None:
        candidate = str(value or "").strip().replace("\\", "/").rstrip("/")
        if not candidate or candidate.startswith("/"):
            return None
        if "://" in candidate:
            return None
        path = PurePosixPath(candidate)
        parts = path.parts
        if not parts or any(part in {"", ".", ".."} for part in parts):
            return None
        if parts[0] == ".git":
            return None
        return candidate

    @classmethod
    def _project_kind(
        cls,
        *,
        task_type: str,
        objective: str,
        context: Mapping[str, Any],
    ) -> tuple[str, tuple[str, ...]]:
        objective_lower = objective.lower()
        project_type = str(context.get("project_type") or "").strip().lower()
        rationale: list[str] = []

        # Explicit platform/self-maintenance intent wins over references to a
        # managed stack that merely explain the bug being fixed. This avoids a
        # Core scope-resolution mission being misclassified as WordPress just
        # because its objective mentions the WordPress request that exposed it.
        if any(marker in objective_lower for marker in cls._PLATFORM_MARKERS):
            rationale.append("objective:mitigate-platform")
            return "mitigate-platform", tuple(rationale)

        if project_type in {"wordpress", "woocommerce", "wp"}:
            rationale.append(f"project_type:{project_type}")
            return "wordpress", tuple(rationale)

        if any(marker in objective_lower for marker in cls._WORDPRESS_MARKERS):
            rationale.append("objective:wordpress")
            return "wordpress", tuple(rationale)

        if task_type in {"wordpress", "content", "seo"}:
            rationale.append(f"task_type:{task_type}")
            return "wordpress", tuple(rationale)

        rationale.append(f"task_type:{task_type or 'general'}")
        return "generic", tuple(rationale)

    @classmethod
    def derive(
        cls,
        *,
        task_type: str,
        objective: str,
        context: Mapping[str, Any] | None = None,
        deliverables: Sequence[str] = (),
    ) -> ProjectScopeDecision:
        task_type = str(task_type or "general").strip().lower()
        objective = str(objective or "")
        context = context or {}

        project_kind, rationale = cls._project_kind(
            task_type=task_type,
            objective=objective,
            context=context,
        )

        explicit = tuple(
            path
            for item in deliverables
            if (path := cls._clean_relative_path(str(item))) is not None
        )

        # Documentation remains intentionally narrow when the planner supplied
        # concrete deliverables. This preserves the existing assessment flow.
        if task_type == "documentation":
            allowed = explicit or ("docs", "README.md")
            return ProjectScopeDecision(
                allowed_paths=tuple(dict.fromkeys(allowed)),
                denied_paths=cls._BASE_DENIED,
                project_kind=project_kind,
                rationale=(*rationale, "documentation-scope"),
            )

        if project_kind == "wordpress":
            # Repository-managed WordPress source is the normal writable area.
            # We intentionally do not authorize live wp-content, host paths,
            # Nginx, systemd, secrets or database access here.
            allowed_items = ["wordpress", "docs"]
            allowed_items.extend(
                path
                for path in explicit
                if path == "wordpress" or path.startswith("wordpress/")
                or path == "docs" or path.startswith("docs/")
            )
            return ProjectScopeDecision(
                allowed_paths=tuple(dict.fromkeys(allowed_items)),
                denied_paths=tuple(dict.fromkeys((*cls._BASE_DENIED, *cls._WORDPRESS_DENIED))),
                project_kind=project_kind,
                rationale=(*rationale, "managed-wordpress-repository-scope"),
            )

        if project_kind == "mitigate-platform":
            allowed_items = ["agent", "docs", ".github"]
            allowed_items.extend(
                path
                for path in explicit
                if path == "agent" or path.startswith("agent/")
                or path == "docs" or path.startswith("docs/")
                or path == ".github" or path.startswith(".github/")
            )
            return ProjectScopeDecision(
                allowed_paths=tuple(dict.fromkeys(allowed_items)),
                denied_paths=cls._BASE_DENIED,
                project_kind=project_kind,
                rationale=(*rationale, "mitigate-self-maintenance-scope"),
            )

        defaults = {
            "github": (".github", "agent", "docs"),
            "infrastructure": ("agent", ".github", "docs"),
            "deployment": ("agent", ".github", "docs"),
            "frontend": ("wordpress", "docs"),
        }
        allowed = explicit or defaults.get(task_type, ("agent",))
        return ProjectScopeDecision(
            allowed_paths=tuple(dict.fromkeys(allowed)),
            denied_paths=cls._BASE_DENIED,
            project_kind=project_kind,
            rationale=(*rationale, "generic-backward-compatible-scope"),
        )


__all__ = ["ProjectScopeDecision", "ProjectScopeResolver"]
