from __future__ import annotations

from agent.runtime import production_request_composition
from agent.runtime.isolated_request_queue_adapter import (
    IsolatedProductionRequestQueueAdapter,
)


# Keep the existing request composition and governance path intact while
# replacing only the persistence adapter used for runtime-generated mission
# definitions.
production_request_composition.ProductionRequestQueueAdapter = (
    IsolatedProductionRequestQueueAdapter
)

from agent.runtime.production_runtime_api import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
