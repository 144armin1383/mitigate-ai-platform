from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from agent.runtime.production_request_queue_adapter import (
    ProductionRequestQueueAdapter,
)


class IsolatedProductionRequestQueueAdapter(ProductionRequestQueueAdapter):
    """Persist runtime-generated mission definitions outside canonical Git.

    Planner-created mission definitions are runtime state, not canonical checkout
    inputs. They are kept under the runtime data root and materialized into a
    disposable execution worktree by the production workspace controller.

    On startup, the adapter also performs a narrow migration of legacy generated
    definitions. Only untracked ``agent/missions/<queued-mission-id>.md`` files
    are eligible. Tracked files and unrelated untracked files are never removed.
    """

    def __init__(
        self,
        *,
        project_id: str,
        queue_path: str | Path,
        repository_root: str | Path,
    ) -> None:
        super().__init__(
            project_id=project_id,
            queue_path=queue_path,
            repository_root=repository_root,
        )

        self.legacy_missions_root = (
            self.repository_root / "agent" / "missions"
        )

        configured = os.environ.get(
            "MITIGATE_AI_MISSION_DEFINITION_ROOT",
            "",
        ).strip()

        if configured:
            definition_root = Path(configured)
        else:
            definition_root = (
                Path(queue_path).expanduser().resolve().parent
                / "mission-definitions"
            )

        self.missions_root = definition_root.expanduser().resolve()
        self.missions_root.mkdir(parents=True, exist_ok=True)
        self._migrate_legacy_generated_definitions()

    def _is_untracked_legacy_definition(self, path: Path) -> bool:
        try:
            relative = path.resolve().relative_to(
                self.repository_root
            ).as_posix()
        except ValueError:
            return False

        result = subprocess.run(
            [
                "git",
                "status",
                "--porcelain",
                "--untracked-files=all",
                "--",
                relative,
            ],
            cwd=self.repository_root,
            text=True,
            capture_output=True,
            check=False,
        )

        if result.returncode != 0:
            return False

        lines = [
            line
            for line in result.stdout.splitlines()
            if line.strip()
        ]
        return lines == [f"?? {relative}"]

    def _migrate_legacy_generated_definitions(self) -> None:
        queued_ids = {
            str(item.get("id") or "").strip()
            for item in self.queue.list()
            if str(item.get("id") or "").strip()
        }

        for mission_id in sorted(queued_ids):
            try:
                mission_id = self._valid_id(mission_id)
            except ValueError:
                continue

            legacy = (
                self.legacy_missions_root
                / f"{mission_id}.md"
            ).resolve()
            target = self._definition_path(mission_id)

            if not legacy.is_file():
                continue

            if not self._is_untracked_legacy_definition(legacy):
                continue

            target.parent.mkdir(parents=True, exist_ok=True)

            if target.exists():
                try:
                    same_content = (
                        target.read_bytes() == legacy.read_bytes()
                    )
                except OSError:
                    same_content = False

                if not same_content:
                    # Fail closed: never discard divergent runtime evidence.
                    continue
            else:
                temporary = target.with_suffix(
                    target.suffix + ".migrating"
                )
                shutil.copyfile(legacy, temporary)
                os.replace(temporary, target)

            # Eligibility was already constrained to a queued mission ID and an
            # exact Git-untracked generated definition path.
            legacy.unlink(missing_ok=True)


__all__ = ["IsolatedProductionRequestQueueAdapter"]
