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


class ProductionRuntimeFacade:
    """
    Minimal runtime facade exposed to RuntimePrivateAPI.

    Keeps the already-running production BackgroundWorker independent.
    This process owns only request ingress and production request composition.
    """

    def __init__(self, request_flow: Any) -> None:
        self._request_flow = request_flow
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


@dataclass
class StaticProviderRegistry:
    provider_id: str
    model_id: str

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
    def evaluate(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> dict[str, bool]:
        return {
            "allowed": True,
        }


class AllowRateLimiter:
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

    return ProductionRuntimeFacade(
        composition.request_flow
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
