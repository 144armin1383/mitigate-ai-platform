#!/usr/bin/env python3

import fcntl
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

LOCK_PATH = Path(
    os.environ.get(
        "MITIGATE_UPDATE_LOCK_PATH",
        "/run/lock/mitigate-ai-managed-update.lock",
    )
)


def run(command):
    print("+", " ".join(command), flush=True)

    subprocess.run(
        command,
        check=True,
        cwd=ROOT,
    )


def save_report(result):
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    filename = (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + ".json"
    )

    (REPORT_DIR / filename).write_text(
        json.dumps(result, indent=2) + "\n",
        encoding="utf-8",
    )


def main():
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)

    with LOCK_PATH.open("w") as lock_file:
        try:
            fcntl.flock(
                lock_file,
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )
        except BlockingIOError:
            print("MANAGED_COMPONENT_UPGRADE_ALREADY_RUNNING=yes")
            return 0

        data = json.loads(
            REGISTRY.read_text(encoding="utf-8")
        )

        result = {
            "started_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "components": [],
            "status": "running",
        }

        failures = []

        try:
            run([
                "bash",
                str(
                    ROOT
                    / "agent/maintenance/ensure_host_resources.sh"
                ),
            ])

            for component in data.get("components", []):
                if not component.get("enabled", False):
                    continue

                if not component.get("auto_update", False):
                    continue

                name = component["name"]
                updater = ROOT / component["updater"]

                entry = {
                    "name": name,
                    "status": "started",
                }

                result["components"].append(entry)

                if not updater.exists():
                    entry["status"] = "failed"
                    entry["error"] = "updater_missing"
                    failures.append(name)
                    continue

                try:
                    run([
                        "bash",
                        str(updater),
                        "latest",
                    ])

                    entry["status"] = "ok"

                except Exception as exc:
                    entry["status"] = "failed"
                    entry["error"] = str(exc)
                    failures.append(name)

            try:
                run([
                    "bash",
                    str(
                        ROOT
                        / "agent/maintenance/"
                        "verify_platform_after_upgrade.sh"
                    ),
                ])

                result["platform_verify"] = "ok"

            except Exception as exc:
                result["platform_verify"] = "failed"
                result["platform_verify_error"] = str(exc)
                failures.append("platform_verify")

            result["completed_at"] = datetime.now(
                timezone.utc
            ).isoformat()

            if failures:
                result["status"] = "failed"
                result["failures"] = failures
            else:
                result["status"] = "ok"

            save_report(result)

            if failures:
                print(
                    "MANAGED_COMPONENT_UPGRADE=FAILED",
                    file=sys.stderr,
                )
                return 1

            print("MANAGED_COMPONENT_UPGRADE=OK")
            return 0

        except Exception as exc:
            result["status"] = "failed"
            result["fatal_error"] = str(exc)
            result["completed_at"] = datetime.now(
                timezone.utc
            ).isoformat()

            save_report(result)

            raise


if __name__ == "__main__":
    raise SystemExit(main())
