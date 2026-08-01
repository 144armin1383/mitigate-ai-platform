from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class TaskDomain(StrEnum):
    GENERAL = "general"
    WORDPRESS = "wordpress"
    GITHUB = "github"
    DEPLOYMENT = "deployment"
    SEO = "seo"
    CONTENT = "content"
    INFRASTRUCTURE = "infrastructure"


class TaskPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ExecutionPlan:
    title: str
    description: str
    domain: TaskDomain
    priority: TaskPriority = TaskPriority.NORMAL
    requires_tests: bool = True
    requires_backup: bool = True
    requires_commit: bool = True
    requires_owner_approval: bool = False
    estimated_files: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class Planner:
    """Convert a request into a structured execution plan."""

    def create_plan(self, request: str) -> ExecutionPlan:
        normalized = request.strip()

        if not normalized:
            raise ValueError("Task request cannot be empty.")

        lowered = normalized.lower()
        domain = self._detect_domain(lowered)
        priority = self._detect_priority(lowered)

        return ExecutionPlan(
            title=normalized[:80],
            description=normalized,
            domain=domain,
            priority=priority,
            requires_tests=True,
            requires_backup=True,
            requires_commit=True,
            requires_owner_approval=priority is TaskPriority.CRITICAL,
            estimated_files=self._estimate_files(domain),
            steps=self._build_steps(domain),
        )

    @staticmethod
    def _detect_domain(request: str) -> TaskDomain:
        if any(word in request for word in ("wordpress", "woocommerce", "plugin", "theme")):
            return TaskDomain.WORDPRESS

        if any(word in request for word in ("github", "commit", "push", "pull request")):
            return TaskDomain.GITHUB

        if any(word in request for word in ("deploy", "rollback", "release")):
            return TaskDomain.DEPLOYMENT

        if any(word in request for word in ("seo", "ranking", "meta description")):
            return TaskDomain.SEO

        if any(word in request for word in ("content", "article", "product description")):
            return TaskDomain.CONTENT

        if any(word in request for word in ("nginx", "server", "ubuntu", "database", "redis")):
            return TaskDomain.INFRASTRUCTURE

        return TaskDomain.GENERAL

    @staticmethod
    def _detect_priority(request: str) -> TaskPriority:
        if any(word in request for word in ("emergency", "critical", "site down")):
            return TaskPriority.CRITICAL

        if any(word in request for word in ("urgent", "high priority")):
            return TaskPriority.HIGH

        return TaskPriority.NORMAL

    @staticmethod
    def _estimate_files(domain: TaskDomain) -> list[str]:
        mapping = {
            TaskDomain.WORDPRESS: [
                "wordpress/martfury-child/functions.php",
                "wordpress/martfury-child/inc/",
            ],
            TaskDomain.GITHUB: [
                ".github/workflows/",
                "agent/services/github.py",
            ],
            TaskDomain.DEPLOYMENT: [
                "agent/services/deployment.py",
                "scripts/",
            ],
            TaskDomain.SEO: [
                "agent/services/seo.py",
            ],
            TaskDomain.CONTENT: [
                "agent/services/content.py",
            ],
            TaskDomain.INFRASTRUCTURE: [
                "infrastructure/",
            ],
            TaskDomain.GENERAL: [],
        }

        return mapping[domain]

    @staticmethod
    def _build_steps(domain: TaskDomain) -> list[str]:
        return [
            "Inspect current project state",
            f"Prepare {domain.value} implementation plan",
            "Create backup or recovery point",
            "Apply changes in an isolated working area",
            "Run validation and automated tests",
            "Review the resulting diff",
            "Commit approved changes to Git",
        ]


planner = Planner()
