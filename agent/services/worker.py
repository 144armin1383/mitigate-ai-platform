from __future__ import annotations

from dataclasses import dataclass

from core.logger import build_logger
from services.task_queue import Task, queue

log = build_logger()


@dataclass
class WorkerStatus:
    running: bool = False
    current_task_id: str | None = None


class Worker:
    """Process queued MITIGATE AI tasks."""

    def __init__(self) -> None:
        self._status = WorkerStatus()

    def status(self) -> WorkerStatus:
        return self._status

    def run_once(self) -> Task | None:
        pending_tasks = queue.pending()

        if not pending_tasks:
            log.info("No pending tasks.")
            return None

        task = pending_tasks[0]

        self._status.running = True
        self._status.current_task_id = task.id

        try:
            task = queue.mark_running(task.id)

            log.info(
                "Starting task: %s [%s]",
                task.title,
                task.id,
            )

            # TODO: Execute the task using the execution engine.

            task = queue.mark_completed(task.id)

            log.info(
                "Completed task: %s [%s]",
                task.title,
                task.id,
            )

            return task

        except Exception as exc:
            log.exception(
                "Worker failed while processing task: %s [%s]",
                task.title,
                task.id,
            )

            queue.mark_failed(task.id, str(exc))
            raise

        finally:
            self._status.running = False
            self._status.current_task_id = None


worker = Worker()
