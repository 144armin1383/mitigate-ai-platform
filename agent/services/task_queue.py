from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import uuid4

from core.storage import storage


AGENT_ROOT = Path(__file__).resolve().parent.parent
QUEUE_FILE = AGENT_ROOT / "tasks" / "queue.json"


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Task:
    id: str
    title: str
    priority: TaskPriority
    status: TaskStatus = TaskStatus.PENDING
    created_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    started_at: str | None = None
    finished_at: str | None = None
    retries: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "priority": self.priority.value,
            "status": self.status.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "retries": self.retries,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Task":
        return cls(
            id=data["id"],
            title=data["title"],
            priority=TaskPriority(data["priority"]),
            status=TaskStatus(data["status"]),
            created_at=data["created_at"],
            started_at=data.get("started_at"),
            finished_at=data.get("finished_at"),
            retries=int(data.get("retries", 0)),
            metadata=data.get("metadata", {}),
        )


class TaskQueue:
    def __init__(self, queue_file: Path = QUEUE_FILE) -> None:
        self.queue_file = queue_file
        self.tasks: list[Task] = []
        self.load()

    def load(self) -> None:
        data = storage.read(self.queue_file)

        task_records: list[dict[str, Any]] = []

        for status in TaskStatus:
            for item in data.get(status.value, []):
                item["status"] = status.value
                task_records.append(item)

        self.tasks = [Task.from_dict(item) for item in task_records]

    def save(self) -> None:
        data: dict[str, Any] = {
            "version": 1,
            "pending": [],
            "running": [],
            "completed": [],
            "failed": [],
        }

        for task in self.tasks:
            data[task.status.value].append(task.to_dict())

        storage.write(self.queue_file, data)

    def add(
        self,
        title: str,
        priority: TaskPriority = TaskPriority.NORMAL,
        metadata: dict[str, Any] | None = None,
    ) -> Task:
        task = Task(
            id=str(uuid4()),
            title=title,
            priority=priority,
            metadata=metadata or {},
        )

        self.tasks.append(task)
        self.save()

        return task

    def by_status(self, status: TaskStatus) -> list[Task]:
        return [task for task in self.tasks if task.status == status]

    def pending(self) -> list[Task]:
        return self.by_status(TaskStatus.PENDING)

    def running(self) -> list[Task]:
        return self.by_status(TaskStatus.RUNNING)

    def completed(self) -> list[Task]:
        return self.by_status(TaskStatus.COMPLETED)

    def failed(self) -> list[Task]:
        return self.by_status(TaskStatus.FAILED)
    def get(self, task_id: str) -> Task | None:
        for task in self.tasks:
            if task.id == task_id:
                return task

        return None

    def mark_running(self, task_id: str) -> Task:
        task = self.get(task_id)

        if task is None:
            raise KeyError(f"Task not found: {task_id}")

        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now(UTC).isoformat()
        task.finished_at = None

        self.save()
        return task

    def mark_completed(self, task_id: str) -> Task:
        task = self.get(task_id)

        if task is None:
            raise KeyError(f"Task not found: {task_id}")

        task.status = TaskStatus.COMPLETED
        task.finished_at = datetime.now(UTC).isoformat()

        self.save()
        return task

    def mark_failed(self, task_id: str, error: str) -> Task:
        task = self.get(task_id)

        if task is None:
            raise KeyError(f"Task not found: {task_id}")

        task.status = TaskStatus.FAILED
        task.finished_at = datetime.now(UTC).isoformat()
        task.retries += 1
        task.metadata["last_error"] = error

        self.save()
        return task

queue = TaskQueue()
