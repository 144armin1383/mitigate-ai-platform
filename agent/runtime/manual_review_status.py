from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from agent.runtime.manual_review_approval import (
    ManualReviewApprovalService,
)
from agent.runtime.production_runtime_api import ProductionRuntimeFacade


_SAFE_MISSION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,159}$")
_MANUAL_REVIEW_REASON = "manual_review_required"
_PUBLIC_STATE = "awaiting_approval"


def _data_root() -> Path:
    return Path(
        os.environ.get("MITIGATE_AI_DATA_ROOT", "/srv/mitigate/data")
    ).expanduser().resolve()


def _failure_evidence(mission_id: str) -> dict[str, Any]:
    mission_id = str(mission_id or "").strip()
    if not _SAFE_MISSION_ID.fullmatch(mission_id):
        return {}

    path = _data_root() / "runtime" / "failure-evidence" / f"{mission_id}.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def normalize_mission_status(mission: dict[str, Any]) -> dict[str, Any]:
    """Expose a manual-review gate as awaiting approval, not as a failure.

    The durable queue remains fail-closed with state=blocked for backward
    compatibility. Public API consumers receive the semantic state together
    with the underlying queue state so no safety boundary is weakened or hidden.
    """
    result = dict(mission or {})
    state = str(result.get("state") or "").strip().lower()
    if state != "blocked":
        return result

    evidence = _failure_evidence(str(result.get("id") or ""))
    reason = str(evidence.get("reason") or "").strip().lower()
    if reason != _MANUAL_REVIEW_REASON:
        return result

    result["queue_state"] = "blocked"
    result["state"] = _PUBLIC_STATE
    result["status_reason"] = _MANUAL_REVIEW_REASON
    result["requires_action"] = "manual_review"
    return result


def normalize_request_status(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload or {})
    items = result.get("missions")
    if not isinstance(items, list):
        return result

    normalized_items: list[dict[str, Any]] = []
    states: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        normalized_item = dict(item)
        mission = normalized_item.get("mission")
        if isinstance(mission, dict):
            public_mission = normalize_mission_status(mission)
            normalized_item["mission"] = public_mission
            states.append(str(public_mission.get("state") or "").lower())
        normalized_items.append(normalized_item)

    result["missions"] = normalized_items
    if any(state == _PUBLIC_STATE for state in states):
        result["status"] = _PUBLIC_STATE
        result["status_reason"] = _MANUAL_REVIEW_REASON
        result["requires_action"] = "manual_review"
    return result


class ManualReviewAwareProductionRuntimeFacade(ProductionRuntimeFacade):
    """Production facade with truthful manual-review and approval semantics."""

    def get_mission(self, mission_id: str) -> dict[str, Any]:
        return normalize_mission_status(super().get_mission(mission_id))

    def get_request_status(self, request_id: str) -> dict[str, Any]:
        return normalize_request_status(super().get_request_status(request_id))

    def list_requests(self, limit: int = 20) -> dict[str, Any]:
        result = dict(super().list_requests(limit))
        items = result.get("items")
        if isinstance(items, list):
            result["items"] = [
                normalize_request_status(item)
                if isinstance(item, dict)
                else item
                for item in items
            ]
        return result

    def process_execution_outcome(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Handle the bounded human approval action exposed by the panel.

        RuntimePrivateAPI already authenticates this endpoint. The panel adds the
        authenticated panel username server-side, so the browser cannot choose
        an arbitrary approver identity.
        """
        if not isinstance(payload, dict):
            raise ValueError("invalid_execution_outcome")
        action = str(payload.get("action") or "").strip().lower()
        if action != "approve_manual_review":
            raise ValueError("invalid_execution_outcome")
        mission_id = str(payload.get("mission_id") or "").strip()
        approved_by = str(payload.get("approved_by") or "").strip()
        if self._queue is None:
            raise RuntimeError("queue_resolution_failed")

        service = ManualReviewApprovalService(
            queue=self._queue,
        )
        return service.approve(
            mission_id,
            approved_by=approved_by,
        )
