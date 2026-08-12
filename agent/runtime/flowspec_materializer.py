from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Mapping

from agent.runtime.flowspec import (
    FlowSpec,
    FlowSpecValidator,
)


@dataclass(frozen=True)
class MaterializedFlow:
    flow_id: str
    project_id: str
    missions: tuple[Mapping[str, Any], ...]


class FlowSpecMissionMaterializer:
    """
    Convert a validated MITIGATE FlowSpec into deterministic
    mission preview records.

    This component has no queue, worker, execution, Git,
    network, or external-runtime authority.
    """

    @classmethod
    def preview(
        cls,
        spec: FlowSpec,
    ) -> MaterializedFlow:
        ordered_steps = (
            FlowSpecValidator.topological_steps(
                spec
            )
        )

        mission_ids = {
            step.step_id:
                cls._mission_id(
                    flow_id=spec.flow_id,
                    step_id=step.step_id,
                )
            for step in ordered_steps
        }

        missions: list[
            Mapping[str, Any]
        ] = []

        for step in ordered_steps:
            dependencies = [
                mission_ids[
                    dependency
                ]
                for dependency
                in step.dependencies
            ]

            missions.append(
                {
                    "mission_id":
                        mission_ids[
                            step.step_id
                        ],
                    "request_id":
                        mission_ids[
                            step.step_id
                        ],
                    "project_id":
                        spec.project_id,
                    "plan_id":
                        spec.flow_id,
                    "step_id":
                        step.step_id,
                    "task_type":
                        step.task_type,
                    "provider_id":
                        "native",
                    "status":
                        "pending",
                    "priority":
                        100,
                    "dependencies":
                        dependencies,
                    "max_retries":
                        0,
                    "payload":
                        dict(
                            step.payload
                        ),
                    "metadata": {
                        "source":
                            "flowspec_v1",
                        "flow_id":
                            spec.flow_id,
                        "schema_version":
                            spec.schema_version,
                    },
                }
            )

        return MaterializedFlow(
            flow_id=spec.flow_id,
            project_id=spec.project_id,
            missions=tuple(
                missions
            ),
        )

    @classmethod
    def preview_document(
        cls,
        document: Mapping[str, Any],
    ) -> MaterializedFlow:
        spec = FlowSpecValidator.parse(
            document
        )

        return cls.preview(
            spec
        )

    @staticmethod
    def _mission_id(
        *,
        flow_id: str,
        step_id: str,
    ) -> str:
        canonical = (
            flow_id.strip()
            + "|"
            + step_id.strip()
        )

        digest = sha256(
            canonical.encode(
                "utf-8"
            )
        ).hexdigest()[:16]

        return (
            "flow-"
            + digest
        )


__all__ = [
    "FlowSpecMissionMaterializer",
    "MaterializedFlow",
]
