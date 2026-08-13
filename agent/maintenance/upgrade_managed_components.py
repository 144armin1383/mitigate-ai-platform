#!/usr/bin/env python3

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(
    os.environ.get(
        "MITIGATE_ROOT",
        "/srv/mitigate/mitigate-ai-platform",
    )
)

REGISTRY = ROOT / "agent/config/managed-components.json"
REPORT_DIR = Path(
    os.environ.get(
        "MITIGATE_UPDATE_REPORT_DIR",
        "/srv/mitigate/data/runtime/update-reports",
    )
)


def run(command):
    print("+", " ".join(command), flush=True)
    subprocess.run(command, check=True, cwd=ROOT)


def main():
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))

    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    result = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "components": [],
    }

    run([
        "bash",
        str(ROOT / "agent/maintenance/ensure_host_resources.sh"),
    ])

    for component in data.get("components", []):
        if not component.get("enabled", False):
            continue

        if not component.get("auto_update", False):
            continue

        name = component["name"]
        updater = ROOT / component["updater"]

        if not updater.exists():
            raise RuntimeError(
                f"Updater missing for managed component {name}: {updater}"
            )

        entry = {
            "name": name,
            "status": "started",
        }

        result["components"].append(entry)

        try:
            run(["bash", str(updater), "latest"])
            entry["status"] = "ok"
        except Exception as exc:
            entry["status"] = "failed"
            entry["error"] = str(exc)
            raise

    run([
        "bash",
        str(ROOT / "agent/maintenance/verify_platform_after_upgrade.sh"),
    ])

    result["completed_at"] = datetime.now(timezone.utc).isoformat()
    result["status"] = "ok"

    path = REPORT_DIR / (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + ".json"
    )

    path.write_text(
        json.dumps(result, indent=2) + "\n",
        encoding="utf-8",
    )

    print("MANAGED_COMPONENT_UPGRADE=OK")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(
            f"MANAGED_COMPONENT_UPGRADE=FAILED: {exc}",
            file=sys.stderr,
        )
        raise
