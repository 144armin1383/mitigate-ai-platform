from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from agent.runtime.mission_queue import MissionQueue


_MISSION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


class ProductionRequestQueueAdapter:
    """
    Adapter from rich planner-built missions to the production MissionQueue.

    Responsibilities:
    - enforce project ownership
    - materialize a safe Mission Runner definition file
    - enqueue the lightweight runtime record
    - preserve dependency IDs
    - never serialize secrets or executable command fields
    """

    _FORBIDDEN_PAYLOAD_KEYS = {
        "shell",
        "command",
        "cmd",
        "bash",
        "powershell",
        "subprocess",
        "executable",
        "script",
    }

    def __init__(
        self,
        *,
        project_id: str,
        queue_path: str | Path,
        repository_root: str | Path,
    ) -> None:
        project_id = str(project_id).strip()
        if not project_id:
            raise ValueError("invalid_project_id")

        self.project_id = project_id
        self.repository_root = Path(repository_root).resolve()
        self.missions_root = self.repository_root / "agent" / "missions"
        self.queue = MissionQueue(str(Path(queue_path).resolve()))

    @staticmethod
    def _valid_id(value: Any) -> str:
        text = str(value or "").strip()
        if not _MISSION_ID_RE.fullmatch(text):
            raise ValueError("invalid_mission_id")
        return text

    @classmethod
    def _validate_payload(cls, payload: Any) -> Mapping[str, Any]:
        if payload is None:
            return {}

        if not isinstance(payload, Mapping):
            raise ValueError("invalid_payload")

        stack = [payload]

        while stack:
            current = stack.pop()

            if isinstance(current, Mapping):
                for key, value in current.items():
                    if not isinstance(key, str):
                        raise ValueError("invalid_payload_key")

                    if key.lower() in cls._FORBIDDEN_PAYLOAD_KEYS:
                        raise ValueError("forbidden_payload_key")

                    if isinstance(value, (Mapping, list)):
                        stack.append(value)

            elif isinstance(current, list):
                for value in current:
                    if isinstance(value, (Mapping, list)):
                        stack.append(value)

        try:
            json.dumps(payload)
        except Exception as exc:
            raise ValueError("payload_not_json_safe") from exc

        return payload

    def _definition_path(self, mission_id: str) -> Path:
        path = (self.missions_root / f"{mission_id}.md").resolve()

        if self.missions_root.resolve() not in path.parents:
            raise ValueError("mission_path_escape")

        return path

    def _render_definition(self, mission: Mapping[str, Any]) -> str:
        mission_id = self._valid_id(mission.get("mission_id"))

        title = str(mission.get("title") or mission_id).strip()
        description = str(mission.get("description") or "").strip()
        task_type = str(mission.get("task_type") or "general").strip()
        request_id = str(
            mission.get("request_id") or ""
        ).strip()

        if not request_id:
            raise ValueError(
                "invalid_request_id"
            )

        payload = self._validate_payload(
            mission.get("payload", {})
        )

        deliverables_raw = payload.get(
            "deliverables",
            [],
        )

        if not isinstance(deliverables_raw, list):
            raise ValueError("invalid_deliverables")

        deliverables: list[str] = []

        for item in deliverables_raw:
            if not isinstance(item, str):
                raise ValueError("invalid_deliverable")

            candidate = item.strip()

            if not candidate:
                raise ValueError("invalid_deliverable")

            parts = candidate.split("/")

            if (
                candidate.startswith("/")
                or chr(92) in candidate
                or any(
                    part in {"", ".", ".."}
                    for part in parts
                )
                or parts[0] == ".git"
            ):
                raise ValueError("unsafe_deliverable")

            if candidate not in deliverables:
                deliverables.append(candidate)

        deliverables_block = "".join(
            f"- {item}\n"
            for item in deliverables
        )

        return (
            f"# {title}\n\n"
            f"Mission ID: {mission_id}\n"
            f"Request ID: {request_id}\n"
            f"Task Type: {task_type}\n\n"
            "## Objective\n\n"
            f"{description}\n\n"
            "## Deliverables\n\n"
            f"{deliverables_block}\n"
            "## Context\n\n"
            f"```json\n"
            f"{json.dumps(payload, sort_keys=True, indent=2)}\n"
            f"```\n\n"
            "## Execution Requirements\n\n"
            "- Inspect the existing repository before modifying files.\n"
            "- Keep changes limited to this mission's objective.\n"
            "- Do not expose credentials, tokens, secrets, or private keys.\n"
            "- Do not execute destructive or irreversible operations without approval.\n"
            "- Run relevant automated tests and validation.\n"
            "- Review the resulting diff before commit.\n"
            "- Use the existing Mission Runner Git branch and commit workflow.\n"
        )

    def enqueue_batch(
        self,
        missions: Sequence[Mapping[str, Any]],
    ) -> list[str]:
        if not isinstance(missions, Sequence) or isinstance(
            missions,
            (str, bytes),
        ):
            raise ValueError("missions_must_be_sequence")

        prepared: list[
            tuple[
                str,
                int,
                list[str],
                Path,
                str,
                str,
            ]
        ] = []
        ids: set[str] = set()

        for mission in missions:
            if not isinstance(mission, Mapping):
                raise ValueError("invalid_mission")

            mission_project = str(mission.get("project_id") or "").strip()
            if mission_project != self.project_id:
                raise ValueError("cross_project_reference")

            mission_id = self._valid_id(mission.get("mission_id"))

            if mission_id in ids:
                raise ValueError("duplicate_mission_id")
            ids.add(mission_id)

            priority = mission.get("priority", 0)
            if not isinstance(priority, int):
                raise ValueError("invalid_priority")

            dependencies_raw = mission.get("dependencies", [])
            if not isinstance(dependencies_raw, list):
                raise ValueError("invalid_dependencies")

            dependencies = [
                self._valid_id(dep)
                for dep in dependencies_raw
            ]

            path = self._definition_path(mission_id)

            if path.exists():
                raise ValueError("mission_definition_exists")

            content = self._render_definition(mission)

            request_id = str(
                mission.get("request_id") or ""
            ).strip()

            if not request_id:
                raise ValueError(
                    "invalid_request_id"
                )

            prepared.append(
                (
                    mission_id,
                    priority,
                    dependencies,
                    path,
                    content,
                    request_id,
                )
            )

        known_ids = set(ids)
        for _, _, dependencies, _, _, _ in prepared:
            for dependency in dependencies:
                if dependency not in known_ids:
                    existing = {
                        item["id"]
                        for item in self.queue.list()
                    }
                    if dependency not in existing:
                        raise ValueError("unknown_dependency")

        self.missions_root.mkdir(parents=True, exist_ok=True)

        written: list[Path] = []
        enqueued: list[str] = []

        try:
            # Definitions are written before queue visibility so the production
            # worker can never claim a mission without its definition existing.
            for _, _, _, path, content, _ in prepared:
                path.write_text(content, encoding="utf-8")
                written.append(path)

            for (
                mission_id,
                priority,
                dependencies,
                _,
                _,
                _,
            ) in prepared:
                self.queue.enqueue(
                    mission_id,
                    priority,
                    dependencies,
                    max_retries=0,
                )
                enqueued.append(mission_id)

        except Exception:
            # Best-effort rollback. Never remove a mission that has already
            # transitioned to running.
            for mission_id in reversed(enqueued):
                try:
                    self.queue.dequeue(mission_id)
                except Exception:
                    pass

            for path in reversed(written):
                try:
                    path.unlink(missing_ok=True)
                except Exception:
                    pass

            raise

        return enqueued

    def mission_ids_for_request(
        self,
        request_id: str,
    ) -> list[str]:
        request_id = str(
            request_id or ""
        ).strip()

        if not request_id:
            return []

        mission_ids: list[str] = []

        for mission in self.queue.list():
            mission_id = str(
                mission.get("id") or ""
            ).strip()

            if not mission_id:
                continue

            path = self._definition_path(
                mission_id
            )

            if not path.is_file():
                continue

            try:
                text = path.read_text(
                    encoding="utf-8"
                )
            except OSError:
                continue

            expected = (
                f"Request ID: {request_id}"
            )

            if expected in text:
                mission_ids.append(
                    mission_id
                )

        return mission_ids

    # Explicit aliases supported by QueueEnqueueCoordinator.
    enqueue_many = enqueue_batch
    enqueue_missions = enqueue_batch
