from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExecutionResult:
    success: bool
    message: str = ""
    changed_files: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseExecutor(ABC):
    """
    Base class for all executors.

    Every executor (Git, WordPress, Python, Shell, AI...)
    must inherit from this class.
    """

    name: str = "base"

    @abstractmethod
    def supports(self, task) -> bool:
        """
        Return True if this executor can execute the task.
        """
        raise NotImplementedError

    @abstractmethod
    def execute(self, task) -> ExecutionResult:
        """
        Execute a task.
        """
        raise NotImplementedError
