from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from agent.technology.assimilation_mission_bridge import (
    NativeAssimilationMissionBridge,
)
from agent.technology.registry import (
    AssimilationState,
    TechnologyRegistry,
    TechnologyState,
)


class ExecutionReportLookup(Protocol):
    def find_by_mission_id(
        self,
        mission_id: str,
    ) -> Mapping[str, Any] | None:
        ...


@dataclass(frozen=True)
class AssimilationMissionResult:
    mission_id: str
    capability: str
    state: str
    execution_id: str | None = None
    safe_error_code: str | None = None


@dataclass(frozen=True)
class AssimilationReconciliationResult:
    technology_id: str
    status: str
    total_missions: int
    successful_missions: int
    pending_missions: int
    failed_missions: int
    native_capabilities: tuple[str, ...]
    pending_capabilities: tuple[str, ...]
    failed_capabilities: tuple[str, ...]
    mission_results: tuple[
        AssimilationMissionResult,
        ...
    ]


class AssimilationLifecycleReconciler:
    """
    Reconcile persisted execution reports into MITIGATE technology
    assimilation lifecycle state.

    This class has no mission execution, enqueue, retry, scheduler,
    external process, network, or queue mutation authority.
    """

    def __init__(
        self,
        *,
        registry: TechnologyRegistry,
        assimilation_bridge: NativeAssimilationMissionBridge,
        report_lookup: ExecutionReportLookup,
    ) -> None:
        self._registry = registry
        self._assimilation_bridge = assimilation_bridge
        self._report_lookup = report_lookup

    def reconcile(
        self,
        technology_id: str,
    ) -> AssimilationReconciliationResult:
        technology_key = str(
            technology_id
        ).strip()

        if not technology_key:
            raise ValueError(
                "technology_id is required"
            )

        record = self._registry.get(
            technology_key
        )

        if (
            record.assimilation_state
            == AssimilationState.COMPLETE
            and record.state
            == TechnologyState.NATIVE_REPLACED
        ):
            adopted = tuple(
                sorted(
                    {
                        str(item).strip()
                        for item in record.adopted_capabilities
                        if str(item).strip()
                    }
                )
            )

            return AssimilationReconciliationResult(
                technology_id=technology_key,
                status="complete",
                total_missions=0,
                successful_missions=0,
                pending_missions=0,
                failed_missions=0,
                native_capabilities=adopted,
                pending_capabilities=(),
                failed_capabilities=(),
                mission_results=(),
            )

        assimilation = self._assimilation_metadata(
            record.metadata
        )

        capabilities = assimilation[
            "capabilities"
        ]
        mission_ids = assimilation[
            "mission_ids"
        ]

        expected_project_id = str(
            assimilation.get(
                "project_id",
                "",
            )
        ).strip()

        if not expected_project_id:
            raise ValueError(
                "assimilation project_id is required"
            )

        mission_results: list[
            AssimilationMissionResult
        ] = []

        successful_capabilities: list[str] = []
        pending_capabilities: list[str] = []
        failed_capabilities: list[str] = []

        for capability, mission_id in zip(
            capabilities,
            mission_ids,
        ):
            report = (
                self._report_lookup
                .find_by_mission_id(
                    mission_id
                )
            )

            if report is None:
                pending_capabilities.append(
                    capability
                )

                mission_results.append(
                    AssimilationMissionResult(
                        mission_id=mission_id,
                        capability=capability,
                        state="pending",
                    )
                )

                continue

            result = self._classify_report(
                report=report,
                expected_project_id=(
                    expected_project_id
                ),
                expected_mission_id=mission_id,
                capability=capability,
            )

            mission_results.append(
                result
            )

            if result.state == "successful":
                successful_capabilities.append(
                    capability
                )

            elif result.state == "pending":
                pending_capabilities.append(
                    capability
                )

            else:
                failed_capabilities.append(
                    capability
                )

        for capability in (
            successful_capabilities
        ):
            if capability not in (
                record.adopted_capabilities
            ):
                self._assimilation_bridge.mark_native_available(
                    technology_key,
                    capability,
                )

        successful_count = len(
            successful_capabilities
        )
        pending_count = len(
            pending_capabilities
        )
        failed_count = len(
            failed_capabilities
        )

        if failed_count:
            status = "failed"

        elif pending_count:
            if successful_count:
                status = "in_progress"
            else:
                status = "pending"

        else:
            self._assimilation_bridge.complete(
                technology_key
            )
            status = "complete"

        self._persist_diagnostics(
            technology_key=technology_key,
            status=status,
            successful_capabilities=(
                successful_capabilities
            ),
            pending_capabilities=(
                pending_capabilities
            ),
            failed_capabilities=(
                failed_capabilities
            ),
        )

        refreshed = self._registry.get(
            technology_key
        )

        native_capabilities = tuple(
            sorted(
                {
                    str(item).strip()
                    for item in refreshed.adopted_capabilities
                    if str(item).strip()
                }
            )
        )

        return AssimilationReconciliationResult(
            technology_id=technology_key,
            status=status,
            total_missions=len(
                mission_ids
            ),
            successful_missions=(
                successful_count
            ),
            pending_missions=pending_count,
            failed_missions=failed_count,
            native_capabilities=(
                native_capabilities
            ),
            pending_capabilities=tuple(
                pending_capabilities
            ),
            failed_capabilities=tuple(
                failed_capabilities
            ),
            mission_results=tuple(
                mission_results
            ),
        )

    @staticmethod
    def _assimilation_metadata(
        metadata: Mapping[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(
            metadata,
            Mapping,
        ):
            raise ValueError(
                "invalid technology metadata"
            )

        assimilation = metadata.get(
            "assimilation"
        )

        if not isinstance(
            assimilation,
            Mapping,
        ):
            raise ValueError(
                "assimilation metadata is required"
            )

        capabilities = assimilation.get(
            "capabilities"
        )
        mission_ids = assimilation.get(
            "mission_ids"
        )

        if not isinstance(
            capabilities,
            list,
        ):
            raise ValueError(
                "assimilation capabilities must be a list"
            )

        if not isinstance(
            mission_ids,
            list,
        ):
            raise ValueError(
                "assimilation mission_ids must be a list"
            )

        if not capabilities:
            raise ValueError(
                "assimilation capabilities are required"
            )

        if not mission_ids:
            raise ValueError(
                "assimilation mission_ids are required"
            )

        if len(capabilities) != len(
            mission_ids
        ):
            raise ValueError(
                "assimilation capability/mission mapping mismatch"
            )

        normalized_capabilities = []
        normalized_mission_ids = []

        for capability in capabilities:
            value = str(
                capability
            ).strip()

            if not value:
                raise ValueError(
                    "assimilation capability is required"
                )

            normalized_capabilities.append(
                value
            )

        for mission_id in mission_ids:
            value = str(
                mission_id
            ).strip()

            if not value:
                raise ValueError(
                    "assimilation mission_id is required"
                )

            normalized_mission_ids.append(
                value
            )

        return {
            **dict(assimilation),
            "capabilities":
                normalized_capabilities,
            "mission_ids":
                normalized_mission_ids,
        }

    @staticmethod
    def _classify_report(
        *,
        report: Mapping[str, Any],
        expected_project_id: str,
        expected_mission_id: str,
        capability: str,
    ) -> AssimilationMissionResult:
        project_id = str(
            report.get(
                "project_id",
                "",
            )
        ).strip()

        mission_id = str(
            report.get(
                "mission_id",
                "",
            )
        ).strip()

        execution_id = str(
            report.get(
                "execution_id",
                "",
            )
        ).strip() or None

        safe_error_code = str(
            report.get(
                "safe_error_code",
                "",
            )
        ).strip() or None

        if project_id != expected_project_id:
            return AssimilationMissionResult(
                mission_id=(
                    expected_mission_id
                ),
                capability=capability,
                state="failed",
                execution_id=execution_id,
                safe_error_code=(
                    "project_id_mismatch"
                ),
            )

        if mission_id != expected_mission_id:
            return AssimilationMissionResult(
                mission_id=(
                    expected_mission_id
                ),
                capability=capability,
                state="failed",
                execution_id=execution_id,
                safe_error_code=(
                    "mission_id_mismatch"
                ),
            )

        status = str(
            report.get(
                "status",
                "",
            )
        ).strip().lower()

        if status == "retrying":
            return AssimilationMissionResult(
                mission_id=(
                    expected_mission_id
                ),
                capability=capability,
                state="pending",
                execution_id=execution_id,
                safe_error_code=(
                    safe_error_code
                ),
            )

        if status in {
            "failed",
            "blocked",
            "cancelled",
        }:
            return AssimilationMissionResult(
                mission_id=(
                    expected_mission_id
                ),
                capability=capability,
                state="failed",
                execution_id=execution_id,
                safe_error_code=(
                    safe_error_code
                    or status
                ),
            )

        metadata = report.get(
            "metadata"
        )

        if not isinstance(
            metadata,
            Mapping,
        ):
            metadata = {}

        success_contract = (
            status == "completed"
            and report.get(
                "success"
            ) is True
            and str(
                report.get(
                    "validation_status",
                    "",
                )
            ).strip().lower()
            == "validated"
            and metadata.get(
                "merged_to_main"
            ) is True
        )

        if success_contract:
            return AssimilationMissionResult(
                mission_id=(
                    expected_mission_id
                ),
                capability=capability,
                state="successful",
                execution_id=execution_id,
            )

        return AssimilationMissionResult(
            mission_id=(
                expected_mission_id
            ),
            capability=capability,
            state="failed",
            execution_id=execution_id,
            safe_error_code=(
                safe_error_code
                or "assimilation_validation_failed"
            ),
        )

    def _persist_diagnostics(
        self,
        *,
        technology_key: str,
        status: str,
        successful_capabilities: list[str],
        pending_capabilities: list[str],
        failed_capabilities: list[str],
    ) -> None:
        record = self._registry.get(
            technology_key
        )

        metadata = dict(
            record.metadata
        )

        assimilation = dict(
            metadata.get(
                "assimilation",
                {},
            )
        )

        assimilation[
            "reconciliation"
        ] = {
            "status": status,
            "successful_capabilities":
                sorted(
                    successful_capabilities
                ),
            "pending_capabilities":
                sorted(
                    pending_capabilities
                ),
            "failed_capabilities":
                sorted(
                    failed_capabilities
                ),
        }

        metadata[
            "assimilation"
        ] = assimilation

        self._registry.update(
            technology_key,
            metadata=metadata,
            external_runtime_required=False,
        )
