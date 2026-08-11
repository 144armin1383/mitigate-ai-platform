from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any
import json
import os
import tempfile
import threading
from datetime import datetime, timezone


class TechnologyKind(str, Enum):
    FRAMEWORK = "framework"
    ORCHESTRATOR = "orchestrator"
    AGENT_SYSTEM = "agent_system"
    MODEL = "model"
    LIBRARY = "library"
    PLATFORM = "platform"
    TOOL = "tool"
    INFRASTRUCTURE = "infrastructure"
    OTHER = "other"


class TechnologyState(str, Enum):
    WATCHING = "watching"
    DISCOVERED = "discovered"
    EVALUATING = "evaluating"
    CONNECTED = "connected"
    ACTIVE_ACCELERATOR = "active_accelerator"
    ASSIMILATING = "assimilating"
    NATIVE_REPLACED = "native_replaced"
    RETIRED = "retired"
    REJECTED = "rejected"


class EvaluationState(str, Enum):
    NOT_EVALUATED = "not_evaluated"
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    PASSED = "passed"
    FAILED = "failed"


class AssimilationState(str, Enum):
    NONE = "none"
    CANDIDATE = "candidate"
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    NATIVE_AVAILABLE = "native_available"
    COMPLETE = "complete"


@dataclass
class TechnologyRecord:
    technology_id: str
    name: str
    kind: TechnologyKind
    state: TechnologyState = TechnologyState.WATCHING
    evaluation_state: EvaluationState = EvaluationState.NOT_EVALUATED
    assimilation_state: AssimilationState = AssimilationState.NONE
    source_url: str | None = None
    installed_version: str | None = None
    latest_observed_version: str | None = None
    certified_version: str | None = None
    external_runtime_required: bool = False
    native_replacement_available: bool = False
    capabilities: list[str] = field(default_factory=list)
    adopted_capabilities: list[str] = field(default_factory=list)
    rejected_capabilities: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None


class TechnologyRegistry:
    """MITIGATE-owned registry of observed and adopted technologies.

    External technologies are references and accelerators only.
    The registry itself has no dependency on any external technology.
    """

    def __init__(
        self,
        storage_path: str | Path | None = None,
        clock=None,
    ):
        self._storage_path = Path(storage_path) if storage_path else None
        self._clock = clock or self._utc_now
        self._lock = threading.RLock()
        self._records: dict[str, TechnologyRecord] = {}
        self._history: list[dict[str, Any]] = []

        if self._storage_path and self._storage_path.exists():
            self._load()

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _validate_id(technology_id: str) -> None:
        if not technology_id:
            raise ValueError("technology_id is required")

        allowed = set(
            "abcdefghijklmnopqrstuvwxyz"
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            "0123456789-_"
        )

        if any(ch not in allowed for ch in technology_id):
            raise ValueError("technology_id contains invalid characters")

    def register(self, record: TechnologyRecord) -> TechnologyRecord:
        self._validate_id(record.technology_id)

        with self._lock:
            if record.technology_id in self._records:
                raise ValueError(
                    f"Technology already registered: {record.technology_id}"
                )

            now = self._clock()
            record.created_at = record.created_at or now
            record.updated_at = now

            self._records[record.technology_id] = record
            self._append_history(
                record.technology_id,
                "registered",
                {"state": record.state.value},
            )
            self._persist()
            return record

    def get(self, technology_id: str) -> TechnologyRecord:
        with self._lock:
            try:
                return self._records[technology_id]
            except KeyError as exc:
                raise KeyError(
                    f"Unknown technology: {technology_id}"
                ) from exc

    def list(self) -> list[TechnologyRecord]:
        with self._lock:
            return sorted(
                self._records.values(),
                key=lambda item: item.technology_id,
            )

    def update(
        self,
        technology_key: str,
        **changes: Any,
    ) -> TechnologyRecord:
        with self._lock:
            record = self.get(technology_key)

            protected = {
                "technology_id",
                "created_at",
            }

            for key, value in changes.items():
                if key in protected:
                    raise ValueError(
                        f"Field cannot be changed: {key}"
                    )

                if not hasattr(record, key):
                    raise ValueError(
                        f"Unknown TechnologyRecord field: {key}"
                    )

                setattr(record, key, value)

            record.updated_at = self._clock()

            self._append_history(
                technology_key,
                "updated",
                changes,
            )
            self._persist()
            return record

    def observe_version(
        self,
        technology_id: str,
        version: str,
        metadata: dict[str, Any] | None = None,
    ) -> TechnologyRecord:
        if not version:
            raise ValueError("version is required")

        with self._lock:
            record = self.get(technology_id)
            previous = record.latest_observed_version
            record.latest_observed_version = version
            record.updated_at = self._clock()

            self._append_history(
                technology_id,
                "version_observed",
                {
                    "previous_version": previous,
                    "version": version,
                    "metadata": metadata or {},
                },
            )

            self._persist()
            return record

    def mark_native_replacement(
        self,
        technology_id: str,
        available: bool = True,
    ) -> TechnologyRecord:
        with self._lock:
            record = self.get(technology_id)
            record.native_replacement_available = available
            record.updated_at = self._clock()

            if available:
                record.assimilation_state = (
                    AssimilationState.NATIVE_AVAILABLE
                )

            self._append_history(
                technology_id,
                "native_replacement_changed",
                {"available": available},
            )

            self._persist()
            return record

    def history(
        self,
        technology_id: str | None = None,
    ) -> list[dict[str, Any]]:
        with self._lock:
            if technology_id is None:
                return list(self._history)

            return [
                item
                for item in self._history
                if item["technology_id"] == technology_id
            ]

    def _append_history(
        self,
        technology_id: str,
        event: str,
        data: dict[str, Any],
    ) -> None:
        self._history.append(
            {
                "technology_id": technology_id,
                "event": event,
                "timestamp": self._clock(),
                "data": self._json_safe(data),
            }
        )

    @staticmethod
    def _json_safe(value: Any) -> Any:
        if isinstance(value, Enum):
            return value.value

        if isinstance(value, dict):
            return {
                key: TechnologyRegistry._json_safe(item)
                for key, item in value.items()
            }

        if isinstance(value, list):
            return [
                TechnologyRegistry._json_safe(item)
                for item in value
            ]

        return value

    def _serialize_record(
        self,
        record: TechnologyRecord,
    ) -> dict[str, Any]:
        return self._json_safe(asdict(record))

    def _persist(self) -> None:
        if self._storage_path is None:
            return

        self._storage_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        payload = {
            "schema_version": 1,
            "technologies": [
                self._serialize_record(record)
                for record in self.list()
            ],
            "history": self._history,
        }

        fd, tmp_name = tempfile.mkstemp(
            prefix=".technology-registry-",
            suffix=".tmp",
            dir=str(self._storage_path.parent),
        )

        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(
                    payload,
                    handle,
                    indent=2,
                    sort_keys=True,
                )
                handle.flush()
                os.fsync(handle.fileno())

            os.replace(
                tmp_name,
                self._storage_path,
            )
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

    def _load(self) -> None:
        with self._storage_path.open(
            "r",
            encoding="utf-8",
        ) as handle:
            payload = json.load(handle)

        if payload.get("schema_version") != 1:
            raise ValueError(
                "Unsupported technology registry schema version"
            )

        records: dict[str, TechnologyRecord] = {}

        for raw in payload.get("technologies", []):
            record = TechnologyRecord(
                technology_id=raw["technology_id"],
                name=raw["name"],
                kind=TechnologyKind(raw["kind"]),
                state=TechnologyState(raw["state"]),
                evaluation_state=EvaluationState(
                    raw["evaluation_state"]
                ),
                assimilation_state=AssimilationState(
                    raw["assimilation_state"]
                ),
                source_url=raw.get("source_url"),
                installed_version=raw.get("installed_version"),
                latest_observed_version=raw.get(
                    "latest_observed_version"
                ),
                certified_version=raw.get("certified_version"),
                external_runtime_required=raw.get(
                    "external_runtime_required",
                    False,
                ),
                native_replacement_available=raw.get(
                    "native_replacement_available",
                    False,
                ),
                capabilities=list(raw.get("capabilities", [])),
                adopted_capabilities=list(
                    raw.get("adopted_capabilities", [])
                ),
                rejected_capabilities=list(
                    raw.get("rejected_capabilities", [])
                ),
                metadata=dict(raw.get("metadata", {})),
                created_at=raw.get("created_at"),
                updated_at=raw.get("updated_at"),
            )

            self._validate_id(record.technology_id)
            records[record.technology_id] = record

        self._records = records
        self._history = list(payload.get("history", []))
