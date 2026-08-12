from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from agent.runtime.flowspec import (
    FLOWSPEC_SCHEMA_VERSION,
)
from agent.runtime.flowspec_materializer import (
    MaterializedFlow,
)


class FlowExecutionContractError(
    ValueError
):
    pass


@dataclass(frozen=True)
class ValidatedFlowExecution:
    flow_id: str
    project_id: str
    mission_ids: tuple[str, ...]


class FlowSpecExecutionContractValidator:
    """
    Validate a materialized FlowSpec batch against the
    existing MITIGATE mission execution contract.

    This class has no queue mutation, execution, Git,
    network, or external-runtime authority.
    """

    REQUIRED_FIELDS = frozenset(
        {
            "mission_id",
            "request_id",
            "project_id",
            "plan_id",
            "step_id",
            "task_type",
            "provider_id",
            "status",
            "priority",
            "dependencies",
            "max_retries",
            "payload",
            "metadata",
        }
    )

    @classmethod
    def validate(
        cls,
        flow: MaterializedFlow,
    ) -> ValidatedFlowExecution:
        flow_id = cls._required_string(
            flow.flow_id,
            "flow_id",
        )

        project_id = cls._required_string(
            flow.project_id,
            "project_id",
        )

        missions = flow.missions

        if not isinstance(
            missions,
            Sequence,
        ):
            raise FlowExecutionContractError(
                "missions must be a sequence"
            )

        if not missions:
            raise FlowExecutionContractError(
                "missions must not be empty"
            )

        mission_ids: list[str] = []

        for mission in missions:
            if not isinstance(
                mission,
                Mapping,
            ):
                raise FlowExecutionContractError(
                    "every mission must be an object"
                )

            mission_id = cls._required_mapping_string(
                mission,
                "mission_id",
            )

            mission_ids.append(
                mission_id
            )

        if len(
            mission_ids
        ) != len(
            set(
                mission_ids
            )
        ):
            raise FlowExecutionContractError(
                "mission_id values must be unique"
            )

        mission_id_set = set(
            mission_ids
        )

        seen: set[str] = set()

        for mission in missions:
            cls._validate_mission(
                mission=mission,
                flow_id=flow_id,
                project_id=project_id,
                mission_id_set=mission_id_set,
                seen=seen,
            )

            seen.add(
                str(
                    mission[
                        "mission_id"
                    ]
                )
            )

        return ValidatedFlowExecution(
            flow_id=flow_id,
            project_id=project_id,
            mission_ids=tuple(
                mission_ids
            ),
        )

    @classmethod
    def _validate_mission(
        cls,
        *,
        mission: Mapping[str, Any],
        flow_id: str,
        project_id: str,
        mission_id_set: set[str],
        seen: set[str],
    ) -> None:
        keys = set(
            mission.keys()
        )

        missing = (
            cls.REQUIRED_FIELDS
            - keys
        )

        if missing:
            raise FlowExecutionContractError(
                "missing mission fields: "
                + ", ".join(
                    sorted(
                        missing
                    )
                )
            )

        unknown = (
            keys
            - cls.REQUIRED_FIELDS
        )

        if unknown:
            raise FlowExecutionContractError(
                "unknown mission fields: "
                + ", ".join(
                    sorted(
                        str(item)
                        for item in unknown
                    )
                )
            )

        mission_id = (
            cls._required_mapping_string(
                mission,
                "mission_id",
            )
        )

        request_id = (
            cls._required_mapping_string(
                mission,
                "request_id",
            )
        )

        if request_id != mission_id:
            raise FlowExecutionContractError(
                "request_id must equal mission_id"
            )

        mission_project = (
            cls._required_mapping_string(
                mission,
                "project_id",
            )
        )

        if mission_project != project_id:
            raise FlowExecutionContractError(
                "mission project_id mismatch"
            )

        plan_id = (
            cls._required_mapping_string(
                mission,
                "plan_id",
            )
        )

        if plan_id != flow_id:
            raise FlowExecutionContractError(
                "mission plan_id mismatch"
            )

        cls._required_mapping_string(
            mission,
            "step_id",
        )

        cls._required_mapping_string(
            mission,
            "task_type",
        )

        provider_id = (
            cls._required_mapping_string(
                mission,
                "provider_id",
            )
        )

        if provider_id != "native":
            raise FlowExecutionContractError(
                "FlowSpec missions must use "
                "provider_id=native"
            )

        status = (
            cls._required_mapping_string(
                mission,
                "status",
            )
        )

        if status != "pending":
            raise FlowExecutionContractError(
                "FlowSpec preview mission "
                "status must be pending"
            )

        priority = mission[
            "priority"
        ]

        if type(priority) is not int:
            raise FlowExecutionContractError(
                "mission priority must be an integer"
            )

        max_retries = mission[
            "max_retries"
        ]

        if type(max_retries) is not int:
            raise FlowExecutionContractError(
                "max_retries must be an integer"
            )

        if max_retries < 0:
            raise FlowExecutionContractError(
                "max_retries must be non-negative"
            )

        dependencies = mission[
            "dependencies"
        ]

        if not isinstance(
            dependencies,
            list,
        ):
            raise FlowExecutionContractError(
                "dependencies must be a list"
            )

        if len(
            dependencies
        ) != len(
            set(
                dependencies
            )
        ):
            raise FlowExecutionContractError(
                "dependencies must be unique"
            )

        for dependency in dependencies:
            if not isinstance(
                dependency,
                str,
            ) or not dependency.strip():
                raise FlowExecutionContractError(
                    "dependency must be "
                    "a non-empty string"
                )

            if dependency == mission_id:
                raise FlowExecutionContractError(
                    "mission cannot depend on itself"
                )

            if dependency not in mission_id_set:
                raise FlowExecutionContractError(
                    "dependency is outside "
                    "the materialized flow"
                )

            if dependency not in seen:
                raise FlowExecutionContractError(
                    "mission batch is not "
                    "topologically ordered"
                )

        payload = mission[
            "payload"
        ]

        if not isinstance(
            payload,
            Mapping,
        ):
            raise FlowExecutionContractError(
                "payload must be an object"
            )

        metadata = mission[
            "metadata"
        ]

        if not isinstance(
            metadata,
            Mapping,
        ):
            raise FlowExecutionContractError(
                "metadata must be an object"
            )

        if metadata.get(
            "source"
        ) != "flowspec_v1":
            raise FlowExecutionContractError(
                "invalid FlowSpec source provenance"
            )

        if metadata.get(
            "flow_id"
        ) != flow_id:
            raise FlowExecutionContractError(
                "metadata flow_id mismatch"
            )

        if metadata.get(
            "schema_version"
        ) != FLOWSPEC_SCHEMA_VERSION:
            raise FlowExecutionContractError(
                "metadata schema_version mismatch"
            )

    @staticmethod
    def _required_string(
        value: Any,
        field: str,
    ) -> str:
        if not isinstance(
            value,
            str,
        ):
            raise FlowExecutionContractError(
                f"{field} must be a string"
            )

        cleaned = value.strip()

        if not cleaned:
            raise FlowExecutionContractError(
                f"{field} is required"
            )

        return cleaned

    @classmethod
    def _required_mapping_string(
        cls,
        mapping: Mapping[str, Any],
        field: str,
    ) -> str:
        return cls._required_string(
            mapping.get(
                field
            ),
            field,
        )


__all__ = [
    "FlowExecutionContractError",
    "FlowSpecExecutionContractValidator",
    "ValidatedFlowExecution",
]
