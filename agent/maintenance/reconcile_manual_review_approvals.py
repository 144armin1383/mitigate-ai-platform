from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from agent.runtime.autonomous_mission_queue import AutonomousMissionQueue
from agent.runtime.manual_review_approval import ManualReviewApprovalService


def _queue_path(data_root: Path) -> Path:
    return data_root / "runtime" / "missions.json"


def _manual_review_blocked_ids(queue: AutonomousMissionQueue) -> list[str]:
    queue._load()
    items: list[str] = []
    for mission_id, mission in queue._missions.items():
        if str(mission.state.value).lower() != "blocked":
            continue
        items.append(str(mission_id))
    return items


def reconcile_one(
    service: ManualReviewApprovalService,
    mission_id: str,
    *,
    reconciled_by: str = "system-reconciler",
) -> dict[str, Any]:
    mission, evidence = service._validate_manual_review(mission_id, reconciled_by)
    if str(mission.get("state") or "").lower() == "completed":
        return {"mission_id": mission_id, "reconciled": True, "state": "completed", "idempotent": True}

    if service._git("branch", "--show-current").stdout.strip() != "main":
        raise RuntimeError("reconciliation_canonical_not_on_main")
    if service._git("status", "--porcelain").stdout.strip():
        raise RuntimeError("reconciliation_canonical_not_clean")

    service._git("fetch", "origin", "main", timeout=60)
    before = service._git("rev-parse", "HEAD").stdout.strip()
    origin_main = service._git("rev-parse", "origin/main").stdout.strip()
    if before != origin_main:
        raise RuntimeError("reconciliation_main_not_synced")

    branch, commit = service._mission_ref(mission_id)
    changed_files = service._changed_files(branch)
    ancestor = service._git(
        "merge-base", "--is-ancestor", commit, "main", check=False
    ).returncode == 0

    content_equivalent = False
    if not ancestor:
        args = ["diff", "--quiet", "main", branch, "--", *changed_files]
        diff = service._git(*args, check=False)
        if diff.returncode not in {0, 1}:
            raise RuntimeError("reconciliation_content_check_failed")
        content_equivalent = diff.returncode == 0

    if not ancestor and not content_equivalent:
        return {
            "mission_id": mission_id,
            "reconciled": False,
            "state": str(mission.get("state") or ""),
            "reason": "mission_output_not_satisfied_on_main",
            "branch": branch,
            "commit": commit,
            "changed_files": changed_files,
        }

    record = service._write_decision_record(
        mission_id=mission_id,
        decided_by=reconciled_by,
        decision="reconciled",
        request_id=str(evidence.get("request_id") or ""),
        branch=branch,
        commit=commit,
        before=before,
        after=before,
        changed_files=changed_files,
        already_merged=ancestor,
        result_state="completed",
    )
    service.queue.approve_manual_review(mission_id)
    return {
        "mission_id": mission_id,
        "reconciled": True,
        "state": "completed",
        "satisfaction": "commit_ancestor" if ancestor else "content_equivalent",
        "branch": branch,
        "commit": commit,
        "changed_files": changed_files,
        "decision_record": str(record),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile stale manual-review approvals already satisfied by main")
    parser.add_argument("mission_ids", nargs="*")
    parser.add_argument("--actor", default="system-reconciler")
    args = parser.parse_args()

    data_root = Path(os.environ.get("MITIGATE_AI_DATA_ROOT", "/srv/mitigate/data")).expanduser().resolve()
    queue = AutonomousMissionQueue(str(_queue_path(data_root)))
    service = ManualReviewApprovalService(queue=queue, data_root=data_root)
    mission_ids = args.mission_ids or _manual_review_blocked_ids(queue)

    results = []
    for mission_id in mission_ids:
        try:
            results.append(reconcile_one(service, mission_id, reconciled_by=args.actor))
        except RuntimeError as exc:
            results.append({"mission_id": mission_id, "reconciled": False, "error": str(exc)})

    print(json.dumps({"results": results}, indent=2, sort_keys=True))
    return 0 if all(item.get("reconciled") for item in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
