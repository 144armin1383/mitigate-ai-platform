from executors.noop import noop_executor
from executors.registry import registry


def register_default_executors() -> None:
    """Register the built-in MITIGATE AI executors."""

    if not any(
        executor.name == noop_executor.name
        for executor in registry.executors
    ):
        registry.register(noop_executor)
