from __future__ import annotations

from core.bootstrap import run_bootstrap
from core.logger import build_logger

log = build_logger()


def main() -> int:
    """
    MITIGATE AI Agent entry point.
    """

    log.info("Starting MITIGATE AI Agent...")

    result = run_bootstrap()

    if not result.healthy:
        log.error("Bootstrap failed.")
        return 1

    log.info("Bootstrap completed successfully.")
    log.info("Agent is ready.")

    # Future startup sequence
    # - Load Configuration
    # - Start Scheduler
    # - Start Task Queue
    # - Start GitHub Manager
    # - Start WordPress Manager
    # - Start Update Engine

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
