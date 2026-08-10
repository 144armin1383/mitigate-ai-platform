from __future__ import annotations

import hashlib
import re
from typing import Any, Mapping


_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


class ProductionPlannerContractAdapter:
    """
    Production planner adapter for PlannerQueueFlowCoordinator.

    Input:
        approved planner_input mapping

    Output:
        strict plan mapping accepted by PlanValidatorMissionBuilder
    """

    _ALLOWED_TASK_TYPES = {
        "general",
        "wordpress",
        "github",
        "deployment",
        "seo",
        "content",
        "infrastructure",
        "testing",
        "documentation",
        "api",
        "backend",
        "frontend",
        "security",
        "database",
    }

    def __init__(self) -> None:
        pass

    @staticmethod
    def _require_text(
        mapping: Mapping[str, Any],
        key: str,
    ) -> str:
        value = mapping.get(key)

        if not isinstance(value, str):
            raise ValueError(f"invalid_{key}")

        value = value.strip()

        if not value:
            raise ValueError(f"invalid_{key}")

        return value

    @staticmethod
    def _valid_identifier(value: str) -> str:
        if not _ID_RE.fullmatch(value):
            raise ValueError("invalid_identifier")
        return value

    @classmethod
    def _normalize_task_type(cls, value: str) -> str:
        task_type = value.strip().lower()

        aliases = {
            "website": "wordpress",
            "woocommerce": "wordpress",
            "server": "infrastructure",
            "infra": "infrastructure",
            "code": "general",
        }

        task_type = aliases.get(
            task_type,
            task_type,
        )

        if task_type not in cls._ALLOWED_TASK_TYPES:
            return "general"

        return task_type

    @staticmethod
    def _extract_deliverables(
        user_message: str,
    ) -> list[str]:
        """Extract explicit safe repository-relative file paths."""

        pattern = re.compile(
            r"(?<![A-Za-z0-9_.\\/-])"
            r"([A-Za-z0-9_.-]+"
            r"(?:/[A-Za-z0-9_.-]+)+)"
        )

        deliverables: list[str] = []

        for match in pattern.finditer(user_message):
            candidate = (
                match.group(1)
                .strip()
                .rstrip(".,;:!?")
            )
            parts = candidate.split("/")

            if (
                candidate.startswith("/")
                or any(
                    part in {"", ".", ".."}
                    for part in parts
                )
                or parts[0] == ".git"
            ):
                continue

            if candidate not in deliverables:
                deliverables.append(candidate)

        return deliverables

    @staticmethod
    def _priority_for(task_type: str) -> int:
        priorities = {
            "security": 0,
            "database": 1,
            "backend": 2,
            "api": 2,
            "infrastructure": 2,
            "deployment": 3,
            "wordpress": 4,
            "frontend": 4,
            "seo": 5,
            "content": 6,
            "testing": 7,
            "documentation": 8,
            "github": 5,
            "general": 5,
        }

        return priorities.get(
            task_type,
            5,
        )

    @staticmethod
    def _plan_id(
        request_id: str,
        user_message: str,
    ) -> str:
        digest = hashlib.sha256(
            (
                request_id
                + "\0"
                + user_message
            ).encode("utf-8")
        ).hexdigest()[:16]

        return f"plan-{digest}"

    @staticmethod
    def _step_id(
        request_id: str,
    ) -> str:
        digest = hashlib.sha256(
            request_id.encode("utf-8")
        ).hexdigest()[:12]

        return f"step-{digest}"

    def plan(
        self,
        planner_input: Mapping[str, Any],
    ) -> dict[str, Any]:

        if not isinstance(
            planner_input,
            Mapping,
        ):
            raise ValueError(
                "invalid_planner_input"
            )

        request_id = self._valid_identifier(
            self._require_text(
                planner_input,
                "request_id",
            )
        )

        project_id = self._valid_identifier(
            self._require_text(
                planner_input,
                "project_id",
            )
        )

        self._valid_identifier(
            self._require_text(
                planner_input,
                "conversation_id",
            )
        )

        user_message = self._require_text(
            planner_input,
            "user_message",
        )

        task_type = self._normalize_task_type(
            self._require_text(
                planner_input,
                "task_type",
            )
        )

        upload_ids = planner_input.get(
            "upload_ids",
            [],
        )

        if not isinstance(
            upload_ids,
            list,
        ):
            raise ValueError(
                "invalid_upload_ids"
            )

        if not all(
            isinstance(item, str)
            for item in upload_ids
        ):
            raise ValueError(
                "invalid_upload_ids"
            )

        repository_root = self._require_text(
            planner_input,
            "repository_root",
        )

        default_branch = self._require_text(
            planner_input,
            "default_branch",
        )

        project_type = self._require_text(
            planner_input,
            "project_type",
        )

        policy_profile = self._require_text(
            planner_input,
            "policy_profile",
        )

        plan_id = self._plan_id(
            request_id,
            user_message,
        )

        step_id = self._step_id(
            request_id,
        )

        payload = {
            "request_id": request_id,
            "project_id": project_id,
            "repository_root": repository_root,
            "default_branch": default_branch,
            "project_type": project_type,
            "policy_profile": policy_profile,
            "user_request": user_message,
            "upload_ids": list(upload_ids),
            "deliverables": self._extract_deliverables(
                user_message
            ),
        }

        return {
            "plan_id": plan_id,
            "request_id": request_id,
            "project_id": project_id,
            "summary": user_message[:500],
            "steps": [
                {
                    "step_id": step_id,
                    "title": user_message[:120],
                    "description": user_message,
                    "dependencies": [],
                    "priority": self._priority_for(
                        task_type
                    ),
                    "task_type": task_type,
                    "payload": payload,
                }
            ],
        }


__all__ = [
    "ProductionPlannerContractAdapter",
]
