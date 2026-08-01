from __future__ import annotations

from dataclasses import dataclass, field

from executors.base import BaseExecutor, ExecutionResult


@dataclass
class ExecutorRegistry:
    """Register executors and route tasks to the correct executor."""

    executors: list[BaseExecutor] = field(default_factory=list)

    def register(self, executor: BaseExecutor) -> None:
        if any(item.name == executor.name for item in self.executors):
            raise ValueError(f"Executor already registered: {executor.name}")

        self.executors.append(executor)

    def find(self, task) -> BaseExecutor | None:
        for executor in self.executors:
            if executor.supports(task):
                return executor

        return None

    def execute(self, task) -> ExecutionResult:
        executor = self.find(task)

        if executor is None:
            return ExecutionResult(
                success=False,
                message=f"No executor supports task: {task.title}",
            )

        return executor.execute(task)


registry = ExecutorRegistry()
