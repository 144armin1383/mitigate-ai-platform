from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
import hashlib
import json
import os
import tempfile


@dataclass(frozen=True)
class CheckpointRecord:
    checkpoint_id: str
    project_id: str
    execution_id: str
    step_id: str
    sequence: int
    state: Mapping[str, Any]
    metadata: Mapping[str, Any]
    created_at: str


class DurableCheckpointStore:
    """
    MITIGATE-owned durable checkpoint persistence.

    Properties:
    - local
    - deterministic
    - atomic
    - replay-safe
    - provider-independent
    - no external runtime dependency
    """

    def __init__(
        self,
        storage_dir: Path | str,
    ) -> None:
        self._storage_dir = Path(
            storage_dir
        )

    def save(
        self,
        *,
        project_id: str,
        execution_id: str,
        step_id: str,
        sequence: int,
        state: Mapping[str, Any],
        metadata: Mapping[str, Any] | None = None,
    ) -> CheckpointRecord:
        self._validate_identity(
            project_id=project_id,
            execution_id=execution_id,
            step_id=step_id,
        )

        if not isinstance(sequence, int):
            raise ValueError(
                "sequence must be an integer"
            )

        if sequence < 0:
            raise ValueError(
                "sequence must be non-negative"
            )

        if not isinstance(state, Mapping):
            raise ValueError(
                "state must be a mapping"
            )

        metadata_value = (
            {}
            if metadata is None
            else dict(metadata)
        )

        checkpoint_id = self._checkpoint_id(
            project_id=project_id,
            execution_id=execution_id,
            step_id=step_id,
            sequence=sequence,
        )

        path = self._record_path(
            project_id=project_id,
            execution_id=execution_id,
            step_id=step_id,
            sequence=sequence,
        )

        created_at = datetime.now(
            timezone.utc
        ).isoformat()

        payload = {
            "checkpoint_id": checkpoint_id,
            "project_id": project_id,
            "execution_id": execution_id,
            "step_id": step_id,
            "sequence": sequence,
            "state": dict(state),
            "metadata": metadata_value,
            "created_at": created_at,
        }

        self._atomic_write(
            path,
            payload,
        )

        return CheckpointRecord(
            checkpoint_id=checkpoint_id,
            project_id=project_id,
            execution_id=execution_id,
            step_id=step_id,
            sequence=sequence,
            state=dict(state),
            metadata=metadata_value,
            created_at=created_at,
        )

    def load(
        self,
        *,
        project_id: str,
        execution_id: str,
        step_id: str,
        sequence: int,
    ) -> CheckpointRecord | None:
        path = self._record_path(
            project_id=project_id,
            execution_id=execution_id,
            step_id=step_id,
            sequence=sequence,
        )

        if not path.is_file():
            return None

        return self._read_record(
            path
        )

    def latest(
        self,
        *,
        project_id: str,
        execution_id: str,
        step_id: str,
    ) -> CheckpointRecord | None:
        directory = self._step_dir(
            project_id=project_id,
            execution_id=execution_id,
            step_id=step_id,
        )

        if not directory.is_dir():
            return None

        candidates: list[
            tuple[int, Path]
        ] = []

        for path in directory.glob(
            "*.json"
        ):
            try:
                sequence = int(
                    path.stem
                )
            except ValueError:
                continue

            candidates.append(
                (
                    sequence,
                    path,
                )
            )

        if not candidates:
            return None

        _, latest_path = max(
            candidates,
            key=lambda item: item[0],
        )

        return self._read_record(
            latest_path
        )

    def list_sequences(
        self,
        *,
        project_id: str,
        execution_id: str,
        step_id: str,
    ) -> list[int]:
        directory = self._step_dir(
            project_id=project_id,
            execution_id=execution_id,
            step_id=step_id,
        )

        if not directory.is_dir():
            return []

        sequences: list[int] = []

        for path in directory.glob(
            "*.json"
        ):
            try:
                sequences.append(
                    int(path.stem)
                )
            except ValueError:
                continue

        return sorted(
            set(sequences)
        )

    def _record_path(
        self,
        *,
        project_id: str,
        execution_id: str,
        step_id: str,
        sequence: int,
    ) -> Path:
        return (
            self._step_dir(
                project_id=project_id,
                execution_id=execution_id,
                step_id=step_id,
            )
            / f"{sequence:020d}.json"
        )

    def _step_dir(
        self,
        *,
        project_id: str,
        execution_id: str,
        step_id: str,
    ) -> Path:
        self._validate_identity(
            project_id=project_id,
            execution_id=execution_id,
            step_id=step_id,
        )

        return (
            self._storage_dir
            / self._safe_component(
                project_id
            )
            / self._safe_component(
                execution_id
            )
            / self._safe_component(
                step_id
            )
        )

    @staticmethod
    def _safe_component(
        value: str,
    ) -> str:
        cleaned = value.strip()

        if not cleaned:
            raise ValueError(
                "checkpoint identity component is required"
            )

        if (
            "/" in cleaned
            or "\\" in cleaned
            or cleaned in {".", ".."}
        ):
            raise ValueError(
                "unsafe checkpoint identity component"
            )

        return cleaned

    @classmethod
    def _validate_identity(
        cls,
        *,
        project_id: str,
        execution_id: str,
        step_id: str,
    ) -> None:
        cls._safe_component(
            project_id
        )
        cls._safe_component(
            execution_id
        )
        cls._safe_component(
            step_id
        )

    @staticmethod
    def _checkpoint_id(
        *,
        project_id: str,
        execution_id: str,
        step_id: str,
        sequence: int,
    ) -> str:
        canonical = "|".join(
            (
                project_id.strip(),
                execution_id.strip(),
                step_id.strip(),
                str(sequence),
            )
        )

        digest = hashlib.sha256(
            canonical.encode(
                "utf-8"
            )
        ).hexdigest()[:24]

        return (
            "checkpoint-"
            + digest
        )

    @staticmethod
    def _atomic_write(
        path: Path,
        payload: Mapping[str, Any],
    ) -> None:
        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        serialized = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

        descriptor, temp_name = (
            tempfile.mkstemp(
                prefix=path.name + ".",
                suffix=".tmp",
                dir=path.parent,
            )
        )

        try:
            with os.fdopen(
                descriptor,
                "w",
                encoding="utf-8",
            ) as handle:
                handle.write(
                    serialized
                )
                handle.write("\n")
                handle.flush()
                os.fsync(
                    handle.fileno()
                )

            os.replace(
                temp_name,
                path,
            )

        except Exception:
            try:
                os.unlink(
                    temp_name
                )
            except FileNotFoundError:
                pass

            raise

    @staticmethod
    def _read_record(
        path: Path,
    ) -> CheckpointRecord:
        raw = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

        required = {
            "checkpoint_id",
            "project_id",
            "execution_id",
            "step_id",
            "sequence",
            "state",
            "metadata",
            "created_at",
        }

        if set(raw) != required:
            raise ValueError(
                "invalid checkpoint record shape"
            )

        if not isinstance(
            raw["state"],
            dict,
        ):
            raise ValueError(
                "invalid checkpoint state"
            )

        if not isinstance(
            raw["metadata"],
            dict,
        ):
            raise ValueError(
                "invalid checkpoint metadata"
            )

        expected_id = (
            DurableCheckpointStore._checkpoint_id(
                project_id=raw["project_id"],
                execution_id=raw["execution_id"],
                step_id=raw["step_id"],
                sequence=raw["sequence"],
            )
        )

        if (
            raw["checkpoint_id"]
            != expected_id
        ):
            raise ValueError(
                "checkpoint identity mismatch"
            )

        return CheckpointRecord(
            checkpoint_id=raw[
                "checkpoint_id"
            ],
            project_id=raw[
                "project_id"
            ],
            execution_id=raw[
                "execution_id"
            ],
            step_id=raw[
                "step_id"
            ],
            sequence=raw[
                "sequence"
            ],
            state=raw["state"],
            metadata=raw[
                "metadata"
            ],
            created_at=raw[
                "created_at"
            ],
        )


__all__ = [
    "CheckpointRecord",
    "DurableCheckpointStore",
]
