from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent.resilience.replacement_mission_bridge import (
    NativeReplacementMissionBridge,
)
from agent.runtime.assimilation_lifecycle_hook import (
    RuntimeAssimilationLifecycleHook,
)
from agent.runtime.production_lifecycle_dispatcher import (
    ProductionLifecycleDispatcher,
)
from agent.technology.assimilation_mission_bridge import (
    NativeAssimilationMissionBridge,
)
from agent.technology.assimilation_reconciler import (
    AssimilationLifecycleReconciler,
)
from agent.technology.evaluation_result_reconciler import (
    TechnologyEvaluationResultReconciler,
)
from agent.technology.registry import (
    TechnologyRegistry,
)


@dataclass(frozen=True)
class ProductionAssimilationComposition:
    """
    MITIGATE-owned production assimilation composition.

    All dependencies remain native to MITIGATE.
    External technologies are never required to construct this object.
    """

    registry: TechnologyRegistry
    replacement_bridge: NativeReplacementMissionBridge
    assimilation_bridge: NativeAssimilationMissionBridge
    reconciler: AssimilationLifecycleReconciler
    evaluation_reconciler: TechnologyEvaluationResultReconciler
    assimilation_hook: RuntimeAssimilationLifecycleHook
    lifecycle_hook: ProductionLifecycleDispatcher


def build_production_assimilation_composition(
    *,
    registry_path: str | Path,
    queue_coordinator: Any,
    queue_reference: str,
    report_lookup: Any,
) -> ProductionAssimilationComposition:
    """
    Build the local MITIGATE assimilation lifecycle.

    This composition:
    - does not create a worker
    - does not create a scheduler
    - does not create a queue
    - does not create a report store
    - does not access the network
    - does not require any external technology runtime

    Queue and report dependencies are injected from the existing
    MITIGATE production runtime.
    """

    queue_key = str(
        queue_reference
    ).strip()

    if not queue_key:
        raise ValueError(
            "queue_reference is required"
        )

    if queue_coordinator is None:
        raise ValueError(
            "queue_coordinator is required"
        )

    if report_lookup is None:
        raise ValueError(
            "report_lookup is required"
        )

    registry = TechnologyRegistry(
        storage_path=Path(
            registry_path
        ),
    )

    replacement_bridge = (
        NativeReplacementMissionBridge(
            queue_coordinator=queue_coordinator,
            queue_reference=queue_key,
        )
    )

    assimilation_bridge = (
        NativeAssimilationMissionBridge(
            registry=registry,
            replacement_bridge=replacement_bridge,
        )
    )

    reconciler = (
        AssimilationLifecycleReconciler(
            registry=registry,
            assimilation_bridge=assimilation_bridge,
            report_lookup=report_lookup,
        )
    )

    assimilation_hook = (
        RuntimeAssimilationLifecycleHook(
            reconciler=reconciler,
        )
    )

    evaluation_reconciler = (
        TechnologyEvaluationResultReconciler(
            registry=registry,
            repository_root=(
                Path(__file__).resolve().parents[2]
            ),
        )
    )

    lifecycle_hook = (
        ProductionLifecycleDispatcher(
            evaluation_reconciler=(
                evaluation_reconciler
            ),
            assimilation_hook=(
                assimilation_hook
            ),
        )
    )

    return ProductionAssimilationComposition(
        registry=registry,
        replacement_bridge=replacement_bridge,
        assimilation_bridge=assimilation_bridge,
        reconciler=reconciler,
        evaluation_reconciler=(
            evaluation_reconciler
        ),
        assimilation_hook=assimilation_hook,
        lifecycle_hook=lifecycle_hook,
    )


def try_build_production_assimilation_hook(
    *,
    registry_path: str | Path,
    queue_coordinator: Any,
    queue_reference: str,
    report_lookup: Any,
) -> RuntimeAssimilationLifecycleHook | None:
    """
    Best-effort production boundary.

    Any assimilation-layer initialization failure disables the optional
    lifecycle hook while leaving normal MITIGATE mission execution intact.
    """

    try:
        composition = (
            build_production_assimilation_composition(
                registry_path=registry_path,
                queue_coordinator=queue_coordinator,
                queue_reference=queue_reference,
                report_lookup=report_lookup,
            )
        )
    except Exception:
        return None

    return composition.lifecycle_hook


__all__ = [
    "ProductionAssimilationComposition",
    "build_production_assimilation_composition",
    "try_build_production_assimilation_hook",
]
