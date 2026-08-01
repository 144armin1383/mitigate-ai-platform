from __future__ import annotations

from executors.base import BaseExecutor, ExecutionResult


class NoOpExecutor(BaseExecutor):
    """
    Safe executor used for testing the execution pipeline.

    It performs no real action and always succeeds.
    """

    name = "noop"

    def supports(self, task) -> bool:
        return True

    def execute(self, task) -> ExecutionResult:

        return ExecutionResult(
            success=True,
            message=f"Task '{task.title}' executed by NoOp Executor.",
            changed_files=[],
            metadata={
                "executor": self.name,
            },
        )


noop_executor = NoOpExecutor()
