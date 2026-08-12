from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence
import json


FLOWSPEC_SCHEMA_VERSION = "1.0.0"


@dataclass(frozen=True)
class FlowStep:
    step_id: str
    task_type: str
    dependencies: tuple[str, ...]
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class FlowSpec:
    schema_version: str
    flow_id: str
    project_id: str
    steps: tuple[FlowStep, ...]
    metadata: Mapping[str, Any]


class FlowSpecValidationError(ValueError):
    pass


class FlowSpecValidator:
    """
    MITIGATE-owned FlowSpec v1 validator.

    Properties:
    - deterministic
    - provider-independent
    - no external runtime dependency
    - no execution authority
    - no queue mutation
    """

    @classmethod
    def parse(
        cls,
        document: Mapping[str, Any],
    ) -> FlowSpec:
        if not isinstance(document, Mapping):
            raise FlowSpecValidationError(
                "FlowSpec root must be an object"
            )

        allowed_root = {
            "schema_version",
            "flow_id",
            "project_id",
            "steps",
            "metadata",
        }

        unknown_root = (
            set(document.keys())
            - allowed_root
        )

        if unknown_root:
            raise FlowSpecValidationError(
                "Unknown FlowSpec fields: "
                + ", ".join(
                    sorted(
                        str(item)
                        for item in unknown_root
                    )
                )
            )

        schema_version = cls._required_string(
            document,
            "schema_version",
        )

        if schema_version != FLOWSPEC_SCHEMA_VERSION:
            raise FlowSpecValidationError(
                "Unsupported FlowSpec schema_version: "
                + schema_version
            )

        flow_id = cls._safe_identifier(
            cls._required_string(
                document,
                "flow_id",
            ),
            field="flow_id",
        )

        project_id = cls._safe_identifier(
            cls._required_string(
                document,
                "project_id",
            ),
            field="project_id",
        )

        raw_steps = document.get(
            "steps"
        )

        if not isinstance(
            raw_steps,
            Sequence,
        ) or isinstance(
            raw_steps,
            (
                str,
                bytes,
                bytearray,
            ),
        ):
            raise FlowSpecValidationError(
                "steps must be an array"
            )

        if not raw_steps:
            raise FlowSpecValidationError(
                "steps must not be empty"
            )

        metadata_raw = document.get(
            "metadata",
            {},
        )

        if not isinstance(
            metadata_raw,
            Mapping,
        ):
            raise FlowSpecValidationError(
                "metadata must be an object"
            )

        steps = tuple(
            cls._parse_step(
                raw_step
            )
            for raw_step in raw_steps
        )

        cls._validate_unique_step_ids(
            steps
        )

        cls._validate_dependencies(
            steps
        )

        cls._validate_acyclic(
            steps
        )

        return FlowSpec(
            schema_version=schema_version,
            flow_id=flow_id,
            project_id=project_id,
            steps=steps,
            metadata=dict(
                metadata_raw
            ),
        )

    @classmethod
    def parse_json(
        cls,
        content: str,
    ) -> FlowSpec:
        try:
            data = json.loads(
                content
            )
        except json.JSONDecodeError as exc:
            raise FlowSpecValidationError(
                "FlowSpec is not valid JSON"
            ) from exc

        if not isinstance(
            data,
            Mapping,
        ):
            raise FlowSpecValidationError(
                "FlowSpec root must be an object"
            )

        return cls.parse(
            data
        )

    @classmethod
    def canonical_document(
        cls,
        spec: FlowSpec,
    ) -> dict[str, Any]:
        ordered_steps = (
            cls.topological_steps(
                spec
            )
        )

        return {
            "schema_version":
                spec.schema_version,
            "flow_id":
                spec.flow_id,
            "project_id":
                spec.project_id,
            "steps": [
                {
                    "step_id":
                        step.step_id,
                    "task_type":
                        step.task_type,
                    "dependencies":
                        list(
                            step.dependencies
                        ),
                    "payload":
                        dict(
                            step.payload
                        ),
                }
                for step in ordered_steps
            ],
            "metadata":
                dict(
                    spec.metadata
                ),
        }

    @classmethod
    def canonical_json(
        cls,
        spec: FlowSpec,
    ) -> str:
        return json.dumps(
            cls.canonical_document(
                spec
            ),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    @classmethod
    def topological_steps(
        cls,
        spec: FlowSpec,
    ) -> tuple[FlowStep, ...]:
        steps_by_id = {
            step.step_id: step
            for step in spec.steps
        }

        indegree = {
            step.step_id:
                len(
                    step.dependencies
                )
            for step in spec.steps
        }

        dependents: dict[
            str,
            set[str],
        ] = {
            step.step_id: set()
            for step in spec.steps
        }

        for step in spec.steps:
            for dependency in (
                step.dependencies
            ):
                dependents[
                    dependency
                ].add(
                    step.step_id
                )

        ready = sorted(
            step_id
            for step_id, degree
            in indegree.items()
            if degree == 0
        )

        ordered: list[
            FlowStep
        ] = []

        while ready:
            current = ready.pop(0)

            ordered.append(
                steps_by_id[
                    current
                ]
            )

            for dependent in sorted(
                dependents[
                    current
                ]
            ):
                indegree[
                    dependent
                ] -= 1

                if (
                    indegree[
                        dependent
                    ]
                    == 0
                ):
                    ready.append(
                        dependent
                    )
                    ready.sort()

        if len(ordered) != len(
            spec.steps
        ):
            raise FlowSpecValidationError(
                "FlowSpec contains a dependency cycle"
            )

        return tuple(
            ordered
        )

    @classmethod
    def _parse_step(
        cls,
        raw: Any,
    ) -> FlowStep:
        if not isinstance(
            raw,
            Mapping,
        ):
            raise FlowSpecValidationError(
                "Every step must be an object"
            )

        allowed = {
            "step_id",
            "task_type",
            "dependencies",
            "payload",
        }

        unknown = (
            set(raw.keys())
            - allowed
        )

        if unknown:
            raise FlowSpecValidationError(
                "Unknown step fields: "
                + ", ".join(
                    sorted(
                        str(item)
                        for item in unknown
                    )
                )
            )

        step_id = cls._safe_identifier(
            cls._required_string(
                raw,
                "step_id",
            ),
            field="step_id",
        )

        task_type = cls._safe_identifier(
            cls._required_string(
                raw,
                "task_type",
            ),
            field="task_type",
        )

        dependencies_raw = raw.get(
            "dependencies",
            [],
        )

        if not isinstance(
            dependencies_raw,
            Sequence,
        ) or isinstance(
            dependencies_raw,
            (
                str,
                bytes,
                bytearray,
            ),
        ):
            raise FlowSpecValidationError(
                "step dependencies must be an array"
            )

        dependencies: list[str] = []

        for dependency in (
            dependencies_raw
        ):
            if not isinstance(
                dependency,
                str,
            ):
                raise FlowSpecValidationError(
                    "step dependency must be a string"
                )

            dependencies.append(
                cls._safe_identifier(
                    dependency,
                    field="dependency",
                )
            )

        if len(
            dependencies
        ) != len(
            set(
                dependencies
            )
        ):
            raise FlowSpecValidationError(
                "step dependencies must be unique"
            )

        payload = raw.get(
            "payload",
            {},
        )

        if not isinstance(
            payload,
            Mapping,
        ):
            raise FlowSpecValidationError(
                "step payload must be an object"
            )

        return FlowStep(
            step_id=step_id,
            task_type=task_type,
            dependencies=tuple(
                sorted(
                    dependencies
                )
            ),
            payload=dict(
                payload
            ),
        )

    @staticmethod
    def _required_string(
        mapping: Mapping[str, Any],
        field: str,
    ) -> str:
        value = mapping.get(
            field
        )

        if not isinstance(
            value,
            str,
        ):
            raise FlowSpecValidationError(
                f"{field} must be a string"
            )

        cleaned = value.strip()

        if not cleaned:
            raise FlowSpecValidationError(
                f"{field} is required"
            )

        return cleaned

    @staticmethod
    def _safe_identifier(
        value: str,
        *,
        field: str,
    ) -> str:
        cleaned = value.strip()

        if (
            "/" in cleaned
            or "\\" in cleaned
            or cleaned in {".", ".."}
        ):
            raise FlowSpecValidationError(
                f"unsafe {field}"
            )

        return cleaned

    @staticmethod
    def _validate_unique_step_ids(
        steps: Sequence[FlowStep],
    ) -> None:
        step_ids = [
            step.step_id
            for step in steps
        ]

        if len(
            step_ids
        ) != len(
            set(
                step_ids
            )
        ):
            raise FlowSpecValidationError(
                "step_id values must be unique"
            )

    @staticmethod
    def _validate_dependencies(
        steps: Sequence[FlowStep],
    ) -> None:
        step_ids = {
            step.step_id
            for step in steps
        }

        for step in steps:
            for dependency in (
                step.dependencies
            ):
                if dependency == (
                    step.step_id
                ):
                    raise FlowSpecValidationError(
                        "step cannot depend on itself"
                    )

                if dependency not in (
                    step_ids
                ):
                    raise FlowSpecValidationError(
                        "unknown dependency "
                        + dependency
                        + " for step "
                        + step.step_id
                    )

    @classmethod
    def _validate_acyclic(
        cls,
        steps: Sequence[FlowStep],
    ) -> None:
        temporary = FlowSpec(
            schema_version=(
                FLOWSPEC_SCHEMA_VERSION
            ),
            flow_id="validation",
            project_id="validation",
            steps=tuple(
                steps
            ),
            metadata={},
        )

        cls.topological_steps(
            temporary
        )


__all__ = [
    "FLOWSPEC_SCHEMA_VERSION",
    "FlowSpec",
    "FlowSpecValidationError",
    "FlowSpecValidator",
    "FlowStep",
]
