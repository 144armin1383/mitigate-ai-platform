from __future__ import annotations

import argparse
import os
import signal
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from agent.api.runtime_private_api import (
    RuntimeAPIConfig,
    build_runtime_private_api,
)
from agent.runtime.production_request_composition import (
    build_production_request_composition,
)
from agent.runtime.mission_queue import MissionQueue
from agent.runtime.production_execution_reporter import (
    ProductionExecutionReporter,
)
from agent.orchestrator.request_gate_selector import (
    ModelInfo,
)


class ProductionRuntimeFacade:
    """
    Minimal runtime facade exposed to RuntimePrivateAPI.

    Keeps the already-running production BackgroundWorker independent.
    This process owns only request ingress and production request composition.
    """

    def __init__(
        self,
        request_flow: Any,
        *,
        queue: Optional[MissionQueue] = None,
        execution_reporter: Optional[
            ProductionExecutionReporter
        ] = None,
        request_queue_adapter: Any = None,
    ) -> None:
        self._request_flow = request_flow
        self._queue = queue
        self._execution_reporter = execution_reporter
        self._request_queue_adapter = (
            request_queue_adapter
        )
        self._running = False

    def start(self) -> dict[str, Any]:
        self._running = True
        return self.runtime_status()

    def stop(self) -> dict[str, Any]:
        self._running = False
        return self.runtime_status()

    def close(self) -> None:
        self.stop()

    def submit_request(
        self,
        request: Any,
    ) -> Any:
        if not self._running:
            return {
                "accepted": False,
                "failure_code": "runtime_not_running",
                "blocked_reason": "runtime_not_running",
            }

        return self._request_flow.submit(
            request
        )

    def get_mission(
        self,
        mission_id: str,
    ) -> dict[str, Any]:
        if self._queue is None:
            raise RuntimeError(
                "queue_resolution_failed"
            )

        try:
            return self._queue.get(
                mission_id
            )
        except KeyError as exc:
            raise KeyError(
                "mission_not_found"
            ) from exc

    def get_execution(
        self,
        execution_id: str,
    ) -> dict[str, Any]:
        if self._execution_reporter is None:
            raise RuntimeError(
                "report_persistence_failed"
            )

        try:
            return (
                self._execution_reporter
                .get_report(execution_id)
            )
        except Exception as exc:
            if "not found" in str(exc).lower():
                raise KeyError(
                    "execution_not_found"
                ) from exc
            raise

    def get_request_status(
        self,
        request_id: str,
    ) -> dict[str, Any]:
        if self._queue is None:
            raise RuntimeError(
                "queue_resolution_failed"
            )

        if self._execution_reporter is None:
            raise RuntimeError(
                "report_persistence_failed"
            )

        if self._request_queue_adapter is None:
            raise RuntimeError(
                "queue_resolution_failed"
            )

        mission_ids = (
            self._request_queue_adapter
            .mission_ids_for_request(
                request_id
            )
        )

        if not mission_ids:
            raise KeyError(
                "request_not_found"
            )

        reports = (
            self._execution_reporter
            .find_by_request_id(request_id)
        )

        report_by_mission = {
            str(report.get("mission_id")): report
            for report in reports
            if report.get("mission_id")
        }

        missions = []

        for mission_id in mission_ids:
            try:
                mission = self._queue.get(
                    mission_id
                )
            except KeyError:
                continue

            missions.append(
                {
                    "mission": mission,
                    "execution": (
                        report_by_mission.get(
                            mission_id
                        )
                    ),
                }
            )

        if not missions:
            raise KeyError(
                "request_not_found"
            )

        states = [
            str(
                item["mission"].get(
                    "state",
                    "",
                )
            ).lower()
            for item in missions
        ]

        if states and all(
            state == "completed"
            for state in states
        ):
            status = "completed"
        elif any(
            state == "running"
            for state in states
        ):
            status = "running"
        elif any(
            state == "retrying"
            for state in states
        ):
            status = "retrying"
        elif any(
            state == "failed"
            for state in states
        ):
            status = "failed"
        elif any(
            state == "blocked"
            for state in states
        ):
            status = "blocked"
        elif any(
            state == "cancelled"
            for state in states
        ):
            status = "cancelled"
        else:
            status = "pending"

        return {
            "request_id": request_id,
            "status": status,
            "missions": missions,
        }

    def list_executions(
        self,
        limit: int = 20,
    ) -> dict[str, Any]:
        if self._execution_reporter is None:
            raise RuntimeError(
                "report_persistence_failed"
            )

        reports = (
            self._execution_reporter
            .list_reports(limit)
        )

        return {
            "items": reports,
            "limit": limit,
            "count": len(reports),
        }

    def list_requests(
        self,
        limit: int = 20,
    ) -> dict[str, Any]:
        if self._execution_reporter is None:
            raise RuntimeError(
                "report_persistence_failed"
            )

        if self._request_queue_adapter is None:
            raise RuntimeError(
                "queue_resolution_failed"
            )

        if self._queue is None:
            raise RuntimeError(
                "queue_resolution_failed"
            )

        if (
            not isinstance(limit, int)
            or isinstance(limit, bool)
            or limit < 1
            or limit > 100
        ):
            raise ValueError("invalid_limit")

        reports = (
            self._execution_reporter
            .list_reports(100)
        )

        reports_by_request: dict[
            str,
            list[dict[str, Any]],
        ] = {}

        report_request_ids: list[str] = []

        for report in reports:
            request_id = str(
                report.get(
                    "request_id",
                    "",
                )
            ).strip()

            if not request_id:
                continue

            reports_by_request.setdefault(
                request_id,
                [],
            ).append(report)

            if request_id not in report_request_ids:
                report_request_ids.append(
                    request_id
                )

        live_request_ids: list[str] = []

        if hasattr(
            self._request_queue_adapter,
            "list_request_ids",
        ):
            live_request_ids = list(
                self._request_queue_adapter
                .list_request_ids()
            )

        request_ids: list[str] = []
        seen: set[str] = set()

        # Live / queue-visible requests come first.
        # Historical-only requests then follow in
        # execution completion order.
        for request_id in (
            live_request_ids
            + report_request_ids
        ):
            request_id = str(
                request_id
            ).strip()

            if (
                not request_id
                or request_id in seen
            ):
                continue

            seen.add(request_id)
            request_ids.append(
                request_id
            )

        items: list[dict[str, Any]] = []

        for request_id in request_ids:
            try:
                item = self.get_request_status(
                    request_id
                )
            except KeyError:
                # Legacy request: execution report exists,
                # but its mission definition predates the
                # explicit Request ID correlation contract.
                request_reports = (
                    reports_by_request.get(
                        request_id,
                        [],
                    )
                )

                if not request_reports:
                    continue

                missions: list[
                    dict[str, Any]
                ] = []

                states: list[str] = []

                for report in request_reports:
                    mission_id = str(
                        report.get(
                            "mission_id",
                            "",
                        )
                    ).strip()

                    mission = None

                    if mission_id:
                        try:
                            mission = (
                                self._queue.get(
                                    mission_id
                                )
                            )
                        except KeyError:
                            mission = None

                    report_status = str(
                        report.get(
                            "status",
                            "",
                        )
                    ).lower()

                    if mission is None:
                        mission = {
                            "id": mission_id,
                            "state": (
                                report_status
                                or "completed"
                            ),
                        }

                    state = str(
                        mission.get(
                            "state",
                            report_status,
                        )
                    ).lower()

                    states.append(state)

                    missions.append(
                        {
                            "mission": mission,
                            "execution": report,
                        }
                    )

                if states and all(
                    state == "completed"
                    for state in states
                ):
                    status = "completed"
                elif any(
                    state == "running"
                    for state in states
                ):
                    status = "running"
                elif any(
                    state == "retrying"
                    for state in states
                ):
                    status = "retrying"
                elif any(
                    state == "failed"
                    for state in states
                ):
                    status = "failed"
                elif any(
                    state == "blocked"
                    for state in states
                ):
                    status = "blocked"
                elif any(
                    state == "cancelled"
                    for state in states
                ):
                    status = "cancelled"
                else:
                    status = "pending"

                item = {
                    "request_id": request_id,
                    "status": status,
                    "missions": missions,
                }

            items.append(item)

            if len(items) >= limit:
                break

        return {
            "items": items,
            "limit": limit,
            "count": len(items),
        }

    def runtime_status(
        self,
    ) -> dict[str, Any]:
        return {
            "state": (
                "running"
                if self._running
                else "stopped"
            ),
            "application_ready": (
                self._running
            ),
            "container_present": (
                self._running
            ),
            "background_worker_running": True,
            "autonomous_controller_running": True,
            "private_admin_api_running": (
                self._running
            ),
            "last_failure_code": None,
            "warnings": [],
        }

    def status(self) -> dict[str, Any]:
        """Compatibility status interface used by RuntimePrivateAPI."""
        return self.runtime_status()

    def latest_events(
        self,
        limit: int,
    ) -> list[dict[str, Any]]:
        if hasattr(
            self._request_flow,
            "latest_events",
        ):
            return self._request_flow.latest_events(
                limit
            )

        return []


@dataclass
class StaticProjectRegistry:
    project_id: str
    repository_root: str
    default_branch: str
    project_type: str
    policy_profile: str
    queue_reference: str

    def resolve_project(
        self,
        project_id: str,
    ) -> Optional[dict[str, Any]]:
        if project_id != self.project_id:
            return None

        return {
            "project_id": self.project_id,
            "repository_root": (
                self.repository_root
            ),
            "default_branch": (
                self.default_branch
            ),
            "project_type": (
                self.project_type
            ),
            "policy_profile": (
                self.policy_profile
            ),
            "queue_reference": (
                self.queue_reference
            ),
        }

    def conversation_belongs_to_project(
        self,
        conversation_id: str,
        project_id: str,
    ) -> bool:
        return (
            project_id == self.project_id
            and isinstance(conversation_id, str)
            and bool(conversation_id.strip())
        )

    def upload_belongs_to_project(
        self,
        upload_id: str,
        project_id: str,
    ) -> bool:
        return (
            project_id == self.project_id
            and isinstance(upload_id, str)
            and bool(upload_id.strip())
        )


@dataclass
class StaticProviderRegistry:
    project_id: str
    provider_id: str
    model_id: str

    _SUPPORTED_TASK_TYPES = {
        "general",
        "wordpress",
        "github",
        "deployment",
        "seo",
        "content",
        "infrastructure",
        "inspection",
        "testing",
        "documentation",
        "api",
        "backend",
        "frontend",
        "security",
        "database",
    }

    def is_task_supported(
        self,
        project_id: str,
        task_type: str,
    ) -> bool:
        return (
            project_id == self.project_id
            and task_type in self._SUPPORTED_TASK_TYPES
        )

    def requires_tools(
        self,
        task_type: str,
    ) -> bool:
        return False

    def _model_info(self) -> ModelInfo:
        return ModelInfo(
            project_id=self.project_id,
            provider_id=self.provider_id,
            model_id=self.model_id,
            supports_vision=True,
            supports_tools=True,
            enabled=True,
            available=True,
            deprecated=False,
        )

    def explicit_model_allowed(
        self,
        project_id: str,
        task_type: str,
        provider_id: str,
        model_id: str,
    ) -> Optional[ModelInfo]:
        if not self.is_task_supported(
            project_id,
            task_type,
        ):
            return None

        if provider_id != self.provider_id:
            return None

        if model_id != self.model_id:
            return None

        return self._model_info()

    def select_default_model(
        self,
        project_id: str,
        task_type: str,
        requires_vision: bool,
        requires_tools: bool,
        requested_provider_id: Optional[str] = None,
    ) -> Optional[ModelInfo]:
        if not self.is_task_supported(
            project_id,
            task_type,
        ):
            return None

        if (
            requested_provider_id is not None
            and requested_provider_id
            != self.provider_id
        ):
            return None

        model = self._model_info()

        if (
            requires_vision
            and not model.supports_vision
        ):
            return None

        if (
            requires_tools
            and not model.supports_tools
        ):
            return None

        return model

    def select_model(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> dict[str, str]:
        return {
            "provider_id": self.provider_id,
            "model_id": self.model_id,
        }

    def resolve_model(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> dict[str, str]:
        return {
            "provider_id": self.provider_id,
            "model_id": self.model_id,
        }


class AllowBudgetEvaluator:
    def preflight(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> dict[str, str]:
        return {
            "status": "allow",
        }

    def evaluate(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> dict[str, bool]:
        return {
            "allowed": True,
        }


class AllowRateLimiter:
    def check_and_register(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> dict[str, bool]:
        return {
            "allowed": True,
        }

    def allow(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> bool:
        return True

    def check(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> dict[str, bool]:
        return {
            "allowed": True,
        }


def build_production_runtime(
    *,
    project_id: str,
    queue_path: str | Path,
    repository_root: str | Path,
    queue_reference: str = "production",
    provider_id: str = "production",
    model_id: str = "production",
    default_branch: str = "main",
    project_type: str = "wordpress",
    policy_profile: str = "default",
) -> ProductionRuntimeFacade:

    project_registry = (
        StaticProjectRegistry(
            project_id=project_id,
            repository_root=str(
                Path(
                    repository_root
                ).resolve()
            ),
            default_branch=default_branch,
            project_type=project_type,
            policy_profile=policy_profile,
            queue_reference=queue_reference,
        )
    )

    provider_registry = (
        StaticProviderRegistry(
            project_id=project_id,
            provider_id=provider_id,
            model_id=model_id,
        )
    )

    composition = (
        build_production_request_composition(
            project_id=project_id,
            queue_reference=queue_reference,
            queue_path=queue_path,
            repository_root=repository_root,
            project_registry=project_registry,
            provider_registry=provider_registry,
            budget_evaluator=AllowBudgetEvaluator(),
            rate_limiter=AllowRateLimiter(),
        )
    )

    queue = MissionQueue(
        str(
            Path(queue_path).resolve()
        )
    )

    execution_reporter = (
        ProductionExecutionReporter(
            storage_dir=(
                Path(queue_path)
                .resolve()
                .parent
                / "execution-reports"
            ),
            project_id=project_id,
        )
    )

    return ProductionRuntimeFacade(
        composition.request_flow,
        queue=queue,
        execution_reporter=(
            execution_reporter
        ),
        request_queue_adapter=(
            composition.queue_adapter
        ),
    )


def main(
    argv: Optional[list[str]] = None,
) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "MITIGATE AI Production Runtime API"
        )
    )

    parser.add_argument(
        "--host",
        default=os.getenv(
            "MITIGATE_AI_HOST",
            "127.0.0.1",
        ),
    )

    parser.add_argument(
        "--port",
        type=int,
        default=int(
            os.getenv(
                "MITIGATE_AI_PORT",
                "8765",
            )
        ),
    )

    parser.add_argument(
        "--repository-root",
        default=os.getenv(
            "MITIGATE_AI_REPOSITORY_ROOT",
            (
                "/srv/mitigate/"
                "mitigate-ai-platform"
            ),
        ),
    )

    parser.add_argument(
        "--queue-path",
        default=os.getenv(
            "MITIGATE_AI_QUEUE_PATH",
            (
                "/srv/mitigate/data/"
                "runtime/missions.json"
            ),
        ),
    )

    parser.add_argument(
        "--project-id",
        default=os.getenv(
            "MITIGATE_AI_DEFAULT_PROJECT_ID",
            "mitigate",
        ),
    )

    parser.add_argument(
        "--auth-token-env",
        default=os.getenv(
            "MITIGATE_AI_AUTH_TOKEN_ENV",
            "MITIGATE_AI_API_TOKEN",
        ),
    )

    args = parser.parse_args(
        argv
    )

    runtime = build_production_runtime(
        project_id=args.project_id,
        queue_path=args.queue_path,
        repository_root=(
            args.repository_root
        ),
    )

    runtime.start()

    api_config = RuntimeAPIConfig(
        host=args.host,
        port=args.port,
        auth_token_reference=(
            args.auth_token_env
        ),
        enable_lifecycle_endpoints=False,
    )

    api = build_runtime_private_api(
        api_config,
        runtime=runtime,
    )

    api.start()

    stop_event = threading.Event()

    def handle_signal(
        signum: int,
        frame: Any,
    ) -> None:
        del signum
        del frame
        stop_event.set()

    signal.signal(
        signal.SIGINT,
        handle_signal,
    )

    if hasattr(
        signal,
        "SIGTERM",
    ):
        signal.signal(
            signal.SIGTERM,
            handle_signal,
        )

    try:
        stop_event.wait()
    finally:
        api.stop()
        api.close()
        runtime.stop()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
