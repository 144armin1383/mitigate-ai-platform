from __future__ import annotations

import argparse
import json
import os
import re
import urllib.parse
from pathlib import Path
from typing import Any

from agent.web import panel_server as base


_SAFE_MISSION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,159}$")
_MANUAL_REVIEW_REASON = "manual_review_required"


def _data_root() -> Path:
    return Path(
        os.environ.get("MITIGATE_AI_DATA_ROOT", "/srv/mitigate/data")
    ).expanduser().resolve()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _mission_records(queue: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize supported durable queue shapes into mission dictionaries."""
    missions = queue.get("missions")

    if isinstance(missions, list):
        return [item for item in missions if isinstance(item, dict)]

    if isinstance(missions, dict):
        records: list[dict[str, Any]] = []
        for mission_id, value in missions.items():
            if not isinstance(value, dict):
                continue
            record = dict(value)
            record.setdefault("id", str(mission_id))
            records.append(record)
        return records

    # Compatibility with queue files whose top-level mapping is keyed directly
    # by mission id. Ignore ordinary queue metadata scalars/dicts without a
    # recognizable mission state.
    records = []
    for mission_id, value in queue.items():
        if not isinstance(value, dict):
            continue
        if "state" not in value and "id" not in value:
            continue
        record = dict(value)
        record.setdefault("id", str(mission_id))
        records.append(record)
    return records


def _approval_queue_items() -> list[dict[str, Any]]:
    """Return only durable manual-review gates without scanning request history.

    The Canvas approval control used to poll the general /v1/requests endpoint.
    That endpoint reconstructs historical request state and can outlive the UI
    polling timeout. Approval state is much smaller and is already durable in
    missions.json plus per-mission failure evidence, so expose it directly.
    """
    root = _data_root() / "runtime"
    queue = _load_json(root / "missions.json")
    missions = _mission_records(queue)

    items: list[dict[str, Any]] = []
    for mission in missions:
        mission_id = str(mission.get("id") or "").strip()
        if (
            not _SAFE_MISSION_ID.fullmatch(mission_id)
            or str(mission.get("state") or "").strip().lower() != "blocked"
        ):
            continue

        evidence = _load_json(
            root / "failure-evidence" / f"{mission_id}.json"
        )
        reason = str(evidence.get("reason") or "").strip().lower()
        if reason != _MANUAL_REVIEW_REASON:
            continue

        items.append(
            {
                "request_id": str(evidence.get("request_id") or "").strip(),
                "mission_id": mission_id,
                "status": "awaiting_approval",
                "reason": _MANUAL_REVIEW_REASON,
                "created_seq": int(mission.get("created_seq") or 0),
                "attempts_done": int(mission.get("attempts_done") or 0),
            }
        )

    items.sort(key=lambda item: item["created_seq"], reverse=True)
    return items


class ApprovalPanelServer(base.PanelServer):
    """Loopback-only Canvas API with governed manual-review actions."""

    def handler(self):
        parent = super().handler()
        outer = self

        class Handler(parent):
            def do_GET(self) -> None:
                parsed = urllib.parse.urlsplit(self.path)
                if parsed.path == "/api/approvals":
                    if not self._require_auth():
                        return
                    items = _approval_queue_items()
                    self._json(
                        200,
                        {
                            "ok": True,
                            "status": 200,
                            "data": {
                                "items": items,
                                "count": len(items),
                            },
                        },
                    )
                    return
                super().do_GET()

            def do_POST(self) -> None:
                parsed = urllib.parse.urlsplit(self.path)
                parts = [
                    urllib.parse.unquote(part)
                    for part in parsed.path.split("/")
                    if part
                ]
                if (
                    len(parts) == 4
                    and parts[0] == "api"
                    and parts[1] == "missions"
                    and parts[3] in {"approve", "reject"}
                ):
                    if not self._require_auth():
                        return
                    mission_id = parts[2]
                    if not _SAFE_MISSION_ID.fullmatch(mission_id):
                        self._json(
                            400,
                            {
                                "ok": False,
                                "error": {
                                    "code": "invalid_mission_id",
                                    "message": "Invalid mission id",
                                },
                            },
                        )
                        return
                    decision = parts[3]
                    if decision == "approve":
                        payload = {
                            "action": "approve_manual_review",
                            "mission_id": mission_id,
                            "approved_by": outer.config.username,
                        }
                    else:
                        payload = {
                            "action": "reject_manual_review",
                            "mission_id": mission_id,
                            "rejected_by": outer.config.username,
                        }
                    self._proxy(
                        "/v1/execution-outcomes",
                        method="POST",
                        payload=payload,
                    )
                    return
                super().do_POST()

        return Handler


def main() -> int:
    parser = argparse.ArgumentParser(
        description="MITIGATE loopback API for Agent Canvas overlays"
    )
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    args = parser.parse_args()
    cfg = base.build_config_from_env()
    if args.host or args.port:
        cfg = base.PanelConfig(
            host=args.host or cfg.host,
            port=args.port or cfg.port,
            runtime_base_url=cfg.runtime_base_url,
            project_id=cfg.project_id,
            username=cfg.username,
            password=cfg.password,
            api_token=cfg.api_token,
        )
    cfg.validate()
    ApprovalPanelServer(cfg).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
