from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from filelock import FileLock

from logger import build_logger

log = build_logger()


class Storage:
    """
    Safe JSON storage with:
    - file locking
    - automatic backup
    - atomic writes
    """

    def read(self, file_path: str | Path) -> dict[str, Any]:

        path = Path(file_path)

        if not path.exists():
            return {}

        with FileLock(str(path) + ".lock"):

            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)

    def write(self, file_path: str | Path, data: dict[str, Any]) -> None:

        path = Path(file_path)

        path.parent.mkdir(parents=True, exist_ok=True)

        backup = path.with_suffix(path.suffix + ".bak")

        if path.exists():
            shutil.copy2(path, backup)

        tmp = path.with_suffix(path.suffix + ".tmp")

        with FileLock(str(path) + ".lock"):

            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(
                    data,
                    f,
                    indent=4,
                    ensure_ascii=False,
                )

            tmp.replace(path)

        log.info("Storage updated: %s", path)


storage = Storage()
