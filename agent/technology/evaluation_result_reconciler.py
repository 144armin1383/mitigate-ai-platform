from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
import json

from agent.technology.registry import (
    AssimilationState,
    EvaluationState,
    TechnologyRegistry,
    TechnologyState,
)


TECHNOLOGY_EVALUATION_TASK_TYPE = "technology_evaluation"

SUPPORTED_RECOMMENDATIONS = {
    "reject",
    "watch",
    "sandbox",
    "assimilate_candidate",
}


@dataclass(frozen=True)
class TechnologyEvaluationReconciliationResult:
    handled: bool
    technology_id: str | None
    recommendation: str | None
    evaluation_state: str | None
    assimilation_state: str | None
    reason: str | None = None
    idempotent: bool = False


class TechnologyEvaluationResultReconciler:
    """
    Reconcile a persisted technology evaluation result into the
    MITIGATE-owned TechnologyRegistry.

    This component:
    - performs no mission execution
    - performs no enqueue
    - performs no scheduling
    - performs no network access
    - never installs or activates external technology
    - never introduces an external runtime dependency
    """

    def __init__(
        self,
        *,
        registry: TechnologyRegistry,
        repository_root: str | Path,
        clock: Any | None = None,
    ) -> None:
        if registry is None:
            raise ValueError(
                "registry is required"
            )

        root = Path(
            repository_root
        ).resolve()

        self._registry = registry
        self._repository_root = root
        self._clock = clock

    def reconcile(
        self,
        *,
        mission: Mapping[str, Any],
        report: Mapping[str, Any],
    ) -> TechnologyEvaluationReconciliationResult:
        if not isinstance(
            mission,
            Mapping,
        ):
            return self._ignored(
                "invalid_mission"
            )

        task_type = str(
            mission.get(
                "task_type",
                "",
            )
        ).strip()

        if (
            task_type
            != TECHNOLOGY_EVALUATION_TASK_TYPE
        ):
            return self._ignored(
                "not_technology_evaluation"
            )

        if not isinstance(
            report,
            Mapping,
        ):
            raise ValueError(
                "invalid execution report"
            )

        mission_id = str(
            mission.get(
                "mission_id"
            )
            or mission.get(
                "id"
            )
            or ""
        ).strip()

        request_id = str(
            mission.get(
                "request_id"
            )
            or mission_id
        ).strip()

        project_id = str(
            mission.get(
                "project_id",
                "",
            )
        ).strip()

        if not mission_id:
            raise ValueError(
                "mission_id is required"
            )

        if not request_id:
            raise ValueError(
                "request_id is required"
            )

        if not project_id:
            raise ValueError(
                "project_id is required"
            )

        self._validate_success_report(
            report=report,
            mission_id=mission_id,
            request_id=request_id,
            project_id=project_id,
        )

        payload = mission.get(
            "payload"
        )

        if not isinstance(
            payload,
            Mapping,
        ):
            raise ValueError(
                "technology evaluation payload is required"
            )

        evaluation = payload.get(
            "technology_evaluation"
        )

        if not isinstance(
            evaluation,
            Mapping,
        ):
            raise ValueError(
                "technology_evaluation context is required"
            )

        technology_id = str(
            evaluation.get(
                "technology_id",
                "",
            )
        ).strip()

        observed_version = str(
            evaluation.get(
                "observed_version",
                "",
            )
            or ""
        ).strip()

        if not technology_id:
            raise ValueError(
                "technology_id is required"
            )

        if not observed_version:
            raise ValueError(
                "observed_version is required"
            )

        deliverables = payload.get(
            "deliverables"
        )

        if (
            not isinstance(
                deliverables,
                list,
            )
            or len(deliverables) != 1
        ):
            raise ValueError(
                "exactly one evaluation deliverable is required"
            )

        artifact_path = str(
            deliverables[0]
            or ""
        ).strip()

        self._validate_artifact_path(
            artifact_path=artifact_path,
            technology_id=technology_id,
            observed_version=observed_version,
        )

        artifact = self._load_artifact(
            artifact_path
        )

        recommendation, confidence = (
            self._validate_artifact_identity(
                artifact=artifact,
                mission_id=mission_id,
                request_id=request_id,
                technology_id=technology_id,
                observed_version=observed_version,
            )
        )

        self._validate_human_review_boundary(
            mission=mission,
            artifact=artifact,
        )

        record = self._registry.get(
            technology_id
        )

        if (
            record.external_runtime_required
        ):
            raise ValueError(
                "external runtime dependency is not permitted"
            )

        existing_evaluation = (
            record.metadata.get(
                "evaluation"
            )
            if isinstance(
                record.metadata,
                Mapping,
            )
            else None
        )

        if isinstance(
            existing_evaluation,
            Mapping,
        ):
            existing_mission_id = str(
                existing_evaluation.get(
                    "mission_id",
                    "",
                )
            ).strip()

            existing_recommendation = str(
                existing_evaluation.get(
                    "recommendation",
                    "",
                )
            ).strip()

            if (
                existing_mission_id
                == mission_id
                and existing_recommendation
                == recommendation
            ):
                return (
                    TechnologyEvaluationReconciliationResult(
                        handled=True,
                        technology_id=technology_id,
                        recommendation=recommendation,
                        evaluation_state=(
                            record.evaluation_state.value
                        ),
                        assimilation_state=(
                            record.assimilation_state.value
                        ),
                        reason=None,
                        idempotent=True,
                    )
                )

        metadata = dict(
            record.metadata
        )

        metadata["evaluation"] = {
            "project_id":
                project_id,
            "mission_id":
                mission_id,
            "request_id":
                request_id,
            "execution_id":
                str(
                    report.get(
                        "execution_id",
                        "",
                    )
                ).strip()
                or None,
            "observed_version":
                observed_version,
            "artifact_path":
                artifact_path,
            "recommendation":
                recommendation,
            "recommendation_confidence":
                confidence,
            "human_review_required":
                True,
            "assimilation_auto_enqueue":
                False,
            "reconciled_at":
                self._now_iso(),
        }

        changes: dict[str, Any] = {
            "evaluation_state":
                EvaluationState.PASSED,
            "external_runtime_required":
                False,
            "metadata":
                metadata,
        }

        if (
            recommendation
            == "assimilate_candidate"
        ):
            changes[
                "assimilation_state"
            ] = AssimilationState.CANDIDATE

        elif recommendation == "reject":
            changes[
                "state"
            ] = TechnologyState.REJECTED
            changes[
                "assimilation_state"
            ] = AssimilationState.NONE

        elif recommendation in {
            "watch",
            "sandbox",
        }:
            changes[
                "assimilation_state"
            ] = AssimilationState.NONE

        else:
            raise ValueError(
                "unsupported recommendation"
            )

        updated = self._registry.update(
            technology_id,
            **changes,
        )

        return TechnologyEvaluationReconciliationResult(
            handled=True,
            technology_id=technology_id,
            recommendation=recommendation,
            evaluation_state=(
                updated.evaluation_state.value
            ),
            assimilation_state=(
                updated.assimilation_state.value
            ),
            reason=None,
            idempotent=False,
        )

    @staticmethod
    def _validate_success_report(
        *,
        report: Mapping[str, Any],
        mission_id: str,
        request_id: str,
        project_id: str,
    ) -> None:
        if (
            str(
                report.get(
                    "task_type",
                    "",
                )
            ).strip()
            != TECHNOLOGY_EVALUATION_TASK_TYPE
        ):
            raise ValueError(
                "execution report task_type mismatch"
            )

        if (
            str(
                report.get(
                    "status",
                    "",
                )
            ).strip().lower()
            != "completed"
        ):
            raise ValueError(
                "technology evaluation did not complete"
            )

        if (
            report.get(
                "success"
            )
            is not True
        ):
            raise ValueError(
                "technology evaluation was not successful"
            )

        if (
            str(
                report.get(
                    "validation_status",
                    "",
                )
            ).strip().lower()
            != "validated"
        ):
            raise ValueError(
                "technology evaluation was not validated"
            )

        metadata = report.get(
            "metadata"
        )

        if not isinstance(
            metadata,
            Mapping,
        ):
            raise ValueError(
                "execution report metadata is required"
            )

        if (
            metadata.get(
                "merged_to_main"
            )
            is not True
        ):
            raise ValueError(
                "technology evaluation was not merged to main"
            )

        if (
            str(
                report.get(
                    "mission_id",
                    "",
                )
            ).strip()
            != mission_id
        ):
            raise ValueError(
                "mission/report mismatch"
            )

        report_request_id = str(
            report.get(
                "request_id",
                "",
            )
        ).strip()

        if (
            report_request_id
            and report_request_id
            != request_id
        ):
            raise ValueError(
                "request/report mismatch"
            )

        if (
            str(
                report.get(
                    "project_id",
                    "",
                )
            ).strip()
            != project_id
        ):
            raise ValueError(
                "project/report mismatch"
            )

    def _validate_artifact_path(
        self,
        *,
        artifact_path: str,
        technology_id: str,
        observed_version: str,
    ) -> None:
        if not artifact_path:
            raise ValueError(
                "artifact_path is required"
            )

        path = Path(
            artifact_path
        )

        if (
            path.is_absolute()
            or ".." in path.parts
        ):
            raise ValueError(
                "invalid artifact path"
            )

        expected = (
            "docs/technology/evaluations/"
            f"{technology_id.lower()}/"
            f"{observed_version}.json"
        )

        if artifact_path != expected:
            raise ValueError(
                "unexpected evaluation artifact path"
            )

        resolved = (
            self._repository_root
            / path
        ).resolve()

        if (
            self._repository_root
            not in resolved.parents
        ):
            raise ValueError(
                "evaluation artifact escapes repository"
            )

    def _load_artifact(
        self,
        artifact_path: str,
    ) -> Mapping[str, Any]:
        path = (
            self._repository_root
            / artifact_path
        )

        try:
            data = json.loads(
                path.read_text(
                    encoding="utf-8"
                )
            )
        except (
            OSError,
            json.JSONDecodeError,
        ) as exc:
            raise ValueError(
                "invalid evaluation artifact"
            ) from exc

        if not isinstance(
            data,
            Mapping,
        ):
            raise ValueError(
                "evaluation artifact root must be an object"
            )

        return data

    @staticmethod
    def _validate_artifact_identity(
        *,
        artifact: Mapping[str, Any],
        mission_id: str,
        request_id: str,
        technology_id: str,
        observed_version: str,
    ) -> tuple[str, float | int | None]:
        metadata = artifact.get(
            "metadata"
        )

        if not isinstance(
            metadata,
            Mapping,
        ):
            raise ValueError(
                "evaluation artifact metadata is required"
            )

        if (
            str(
                metadata.get(
                    "mission_id",
                    "",
                )
            ).strip()
            != mission_id
        ):
            raise ValueError(
                "artifact mission mismatch"
            )

        artifact_request_id = str(
            metadata.get(
                "request_id",
                "",
            )
        ).strip()

        if (
            artifact_request_id
            and artifact_request_id
            != request_id
        ):
            raise ValueError(
                "artifact request mismatch"
            )

        if (
            str(
                metadata.get(
                    "technology_id",
                    "",
                )
            ).strip()
            != technology_id
        ):
            raise ValueError(
                "artifact technology mismatch"
            )

        if (
            str(
                metadata.get(
                    "observed_version",
                    "",
                )
            ).strip()
            != observed_version
        ):
            raise ValueError(
                "artifact version mismatch"
            )

        recommendation = artifact.get(
            "recommendation"
        )

        if not isinstance(
            recommendation,
            Mapping,
        ):
            raise ValueError(
                "evaluation recommendation is required"
            )

        value = str(
            recommendation.get(
                "value",
                "",
            )
        ).strip()

        if (
            value
            not in SUPPORTED_RECOMMENDATIONS
        ):
            raise ValueError(
                "unsupported evaluation recommendation"
            )

        confidence = recommendation.get(
            "confidence"
        )

        if (
            confidence is not None
            and not isinstance(
                confidence,
                (int, float),
            )
        ):
            raise ValueError(
                "invalid recommendation confidence"
            )

        return value, confidence

    @staticmethod
    def _validate_human_review_boundary(
        *,
        mission: Mapping[str, Any],
        artifact: Mapping[str, Any],
    ) -> None:
        payload = mission.get(
            "payload"
        )

        requirements = (
            payload.get(
                "evaluation_requirements"
            )
            if isinstance(
                payload,
                Mapping,
            )
            else None
        )

        if (
            not isinstance(
                requirements,
                Mapping,
            )
            or requirements.get(
                "require_human_review_before_adoption"
            )
            is not True
        ):
            raise ValueError(
                "human review requirement is missing"
            )

        adoption_policy = artifact.get(
            "adoption_policy"
        )

        if not isinstance(
            adoption_policy,
            Mapping,
        ):
            raise ValueError(
                "adoption policy is required"
            )

        prohibited = (
            "activation_allowed",
            "external_runtime_dependency_allowed",
            "installation_allowed",
            "runtime_adoption_allowed",
        )

        for key in prohibited:
            if (
                adoption_policy.get(
                    key
                )
                is not False
            ):
                raise ValueError(
                    "external technology adoption is not permitted"
                )

    def _now_iso(self) -> str:
        if self._clock is not None:
            value = self._clock()

            if isinstance(
                value,
                str,
            ):
                return value

            if isinstance(
                value,
                datetime,
            ):
                if (
                    value.tzinfo
                    is None
                ):
                    value = value.replace(
                        tzinfo=timezone.utc
                    )

                return value.isoformat()

        return datetime.now(
            timezone.utc
        ).isoformat()

    @staticmethod
    def _ignored(
        reason: str,
    ) -> TechnologyEvaluationReconciliationResult:
        return TechnologyEvaluationReconciliationResult(
            handled=False,
            technology_id=None,
            recommendation=None,
            evaluation_state=None,
            assimilation_state=None,
            reason=reason,
            idempotent=False,
        )


__all__ = [
    "SUPPORTED_RECOMMENDATIONS",
    "TECHNOLOGY_EVALUATION_TASK_TYPE",
    "TechnologyEvaluationReconciliationResult",
    "TechnologyEvaluationResultReconciler",
]
