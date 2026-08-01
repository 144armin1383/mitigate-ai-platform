from __future__ import annotations

from dataclasses import dataclass

from core.logger import build_logger
from executors import register_default_executors
from executors.registry import registry
from services.task_queue import Task, queue

log = build_logger()


@dataclass
class WorkerStatus:
    running: bool = False
    current_task_id: str | None = None


class Worker:
    """Process queued MITIGATE AI tasks through the executor registry."""

    def __init__(self) -> None:
        self._status = WorkerStatus()
        register_default_executors()

    def status(self) -> WorkerStatus:
        """Return the current worker state."""
        return self._status

    def run_once(self) -> Task | None:
        """Process one pending task."""

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

            result = registry.execute(task)

            if not result.success:
                task = queue.mark_failed(
                    task.id,
                    result.message or "Executor failed without a message.",
                )

                log.error(
                    "Task failed: %s [%s] | %s",
                    task.title,
                    task.id,
                    result.message,
                )

                return task

            task.metadata["execution_result"] = {
                "message": result.message,
                "changed_files": result.changed_files,
                "metadata": result.metadata,
            }

            task = queue.mark_completed(task.id)

            log.info(
                "Completed task: %s [%s] | %s",
                task.title,
                task.id,
                result.message,
            )

            return task

        except Exception as exc:
            log.exception(
                "Worker failed while processing task: %s [%s]",
                task.title,
                task.id,
            )

            try:
                queue.mark_failed(task.id, str(exc))
            except Exception:
                log.exception(
                    "Failed to persist task failure state: %s",
                    task.id,
                )

            raise

        finally:
            self._status.running = False
            self._status.current_task_id = None


worker = Worker()
