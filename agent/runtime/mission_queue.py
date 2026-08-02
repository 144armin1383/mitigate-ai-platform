from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# Cross-platform file lock using only Python standard library
try:
    import fcntl  # type: ignore[attr-defined]
    _HAS_FCNTL = True
except Exception:  # pragma: no cover - platform-specific
    fcntl = None  # type: ignore[assignment]
    _HAS_FCNTL = False

try:
    import msvcrt  # type: ignore[attr-defined]
    _HAS_MSVCRT = True
except Exception:  # pragma: no cover - platform-specific
    msvcrt = None  # type: ignore[assignment]
    _HAS_MSVCRT = False


class MissionState(str, Enum):
    pending = "pending"
    running = "running"
    retrying = "retrying"
    completed = "completed"
    failed = "failed"
    blocked = "blocked"
    cancelled = "cancelled"


@dataclass
class Mission:
    id: str
    priority: int
    dependencies: List[str] = field(default_factory=list)
    state: MissionState = MissionState.pending
    created_seq: int = 0
    attempts_done: int = 0
    max_retries: int = 0

    def to_dict(self) -> Dict[str, Any]:
        # Deterministic dict suitable for JSON serialization
        # Dependencies kept sorted for deterministic output
        return {
            "id": self.id,
            "priority": self.priority,
            "dependencies": list(sorted(self.dependencies)),
            "state": self.state.value,
            "created_seq": self.created_seq,
            "attempts_done": self.attempts_done,
            "max_retries": self.max_retries,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> Mission:
        # Validate and deserialize deterministically
        try:
            state = MissionState(str(d["state"]))
        except Exception as exc:
            raise ValueError(f"Invalid mission state: {d.get('state')!r}") from exc
        deps_raw = d.get("dependencies", [])
        if not isinstance(deps_raw, list) or not all(isinstance(x, str) for x in deps_raw):
            raise ValueError("dependencies must be a list of strings")
        return Mission(
            id=str(d["id"]),
            priority=int(d["priority"]),
            dependencies=list(deps_raw),
            state=state,
            created_seq=int(d.get("created_seq", 0)),
            attempts_done=int(d.get("attempts_done", 0)),
            max_retries=int(d.get("max_retries", 0)),
        )


class _FileLock:
    def __init__(self, path: str) -> None:
        self._path = path
        self._fh: Optional[Any] = None

    def acquire(self) -> None:
        # Ensure lock directory exists
        d = os.path.dirname(os.path.abspath(self._path))
        if d and not os.path.exists(d):
            os.makedirs(d, exist_ok=True)
        fh = open(self._path, "a+b")
        try:
            if _HAS_FCNTL:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            elif _HAS_MSVCRT:  # pragma: no cover - Windows
                # Lock the entire file by seeking to start and locking a large region
                fh.seek(0)
                try:
                    # Use LK_LOCK for blocking exclusive lock
                    msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
                except OSError:
                    fh.close()
                    raise
            else:  # pragma: no cover - very rare platforms
                # Fallback: no-op (not ideal, but keeps API)
                pass
        except Exception:
            fh.close()
            raise
        self._fh = fh

    def release(self) -> None:
        fh = self._fh
        if fh is None:
            return
        try:
            if _HAS_FCNTL:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            elif _HAS_MSVCRT:  # pragma: no cover - Windows
                fh.seek(0)
                try:
                    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
        finally:
            try:
                fh.close()
            finally:
                self._fh = None

    def __enter__(self) -> _FileLock:
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


class MissionQueue:
    """
    Persistent mission queue with deterministic ordering, atomic JSON persistence,
    and robust dependency management suitable for an Autonomous Controller.

    - Only Python standard library used.
    - Fully typed and Python 3.12 compatible.
    - File-based persistence with exclusive file locking to prevent corruption.
    """

    def __init__(self, path: str, default_max_retries: int = 0) -> None:
        self._path = os.path.abspath(path)
        self._lock_path = self._path + ".lock"
        self._default_max_retries = int(default_max_retries)
        # In-memory state, always reloaded within lock before mutation
        self._missions: Dict[str, Mission] = {}
        self._next_seq: int = 1
        # Load existing state (validates cycles)
        if os.path.exists(self._path):
            # Load without holding a lock here; methods always lock before mutating.
            # This allows constructor in read-only contexts; actual operations will re-load under lock.
            self._load()

    # --------------- Public API ---------------

    def enqueue(
        self,
        mission_id: str,
        priority: int,
        dependencies: Sequence[str] | None = None,
        *,
        max_retries: Optional[int] = None,
    ) -> None:
        """Add a new mission. Prevent duplicate identifiers. Validate circular dependencies atomically."""
        deps = list(dict.fromkeys((dependencies or [])))  # de-duplicate preserving order
        # Sort dependencies for deterministic persistence (dependency semantics are set-like)
        deps_sorted = sorted(deps)
        with _FileLock(self._lock_path):
            self._load()
            if mission_id in self._missions:
                raise ValueError(f"Mission with id {mission_id!r} already exists")
            created_seq = self._next_seq
            self._next_seq += 1
            mission = Mission(
                id=mission_id,
                priority=int(priority),
                dependencies=deps_sorted,
                state=MissionState.pending,
                created_seq=created_seq,
                attempts_done=0,
                max_retries=int(self._default_max_retries if max_retries is None else max_retries),
            )
            # Tentatively add and validate cycles
            self._missions[mission_id] = mission
            try:
                self._validate_no_cycles()
            except Exception:
                # Revert
                del self._missions[mission_id]
                self._next_seq -= 1
                raise
            self._save()

    def dequeue(self, mission_id: str) -> None:
        """Remove a mission from the queue.
        - Must not remove running missions.
        - Must not remove missions that are dependencies of other missions.
        """
        with _FileLock(self._lock_path):
            self._load()
            m = self._get_mission_or_raise(mission_id)
            if m.state == MissionState.running:
                raise ValueError("Cannot dequeue a running mission")
            # Check if any other mission depends on this one
            for other in self._missions.values():
                if other.id != mission_id and mission_id in set(other.dependencies):
                    raise ValueError("Cannot dequeue a mission that is a dependency of others")
            del self._missions[mission_id]
            self._validate_no_cycles()  # graph changed (node removed), keep invariant
            self._save()

    def claim(self) -> Optional[Dict[str, Any]]:
        """Atomically select the next runnable mission and mark it running.
        Returns the mission dict or None if none are claimable.
        Only pending or retrying missions with all dependencies completed are eligible.
        Deterministic ordering by priority (descending), created_seq (ascending), id (ascending).
        """
        with _FileLock(self._lock_path):
            self._load()
            eligible = [
                m
                for m in self._missions.values()
                if m.state in (MissionState.pending, MissionState.retrying)
                and self._deps_completed(m)
            ]
            if not eligible:
                return None
            # Deterministic sort: -priority, created_seq, id
            eligible.sort(key=lambda m: (-m.priority, m.created_seq, m.id))
            chosen = eligible[0]
            chosen.state = MissionState.running
            self._save()
            return chosen.to_dict()

    def complete(self, mission_id: str) -> None:
        with _FileLock(self._lock_path):
            self._load()
            m = self._get_mission_or_raise(mission_id)
            if m.state != MissionState.running:
                raise ValueError("complete() requires mission to be running")
            m.state = MissionState.completed
            self._validate_no_cycles()  # state change doesn't alter deps but keep invariant step
            self._save()

    def fail(self, mission_id: str) -> None:
        with _FileLock(self._lock_path):
            self._load()
            m = self._get_mission_or_raise(mission_id)
            if m.state != MissionState.running:
                raise ValueError("fail() requires mission to be running")
            m.attempts_done += 1
            if m.attempts_done <= m.max_retries:
                m.state = MissionState.retrying
            else:
                m.state = MissionState.failed
            self._validate_no_cycles()
            self._save()

    def retry(self, mission_id: str) -> None:
        """Explicitly move a failed mission back to retrying if retry budget remains.
        Note: fail() already transitions to retrying when budget remains; this is a manual override.
        """
        with _FileLock(self._lock_path):
            self._load()
            m = self._get_mission_or_raise(mission_id)
            if m.state != MissionState.failed:
                raise ValueError("retry() requires mission to be in failed state")
            if m.attempts_done >= m.max_retries:
                raise ValueError("No retry attempts remaining")
            m.state = MissionState.retrying
            self._validate_no_cycles()
            self._save()

    def block(self, mission_id: str) -> None:
        with _FileLock(self._lock_path):
            self._load()
            m = self._get_mission_or_raise(mission_id)
            if m.state == MissionState.running:
                # Disallow transitioning a running mission to blocked to avoid mid-flight inconsistencies
                raise ValueError("Cannot block a running mission")
            m.state = MissionState.blocked
            self._validate_no_cycles()
            self._save()

    def cancel(self, mission_id: str) -> None:
        with _FileLock(self._lock_path):
            self._load()
            m = self._get_mission_or_raise(mission_id)
            if m.state in (MissionState.completed, MissionState.failed, MissionState.cancelled):
                raise ValueError("Cannot cancel a completed, failed, or already cancelled mission")
            m.state = MissionState.cancelled
            self._validate_no_cycles()
            self._save()

    def resume(self, mission_id: str) -> None:
        """Resume a blocked or cancelled mission back to pending."""
        with _FileLock(self._lock_path):
            self._load()
            m = self._get_mission_or_raise(mission_id)
            if m.state not in (MissionState.blocked, MissionState.cancelled):
                raise ValueError("resume() allowed only for blocked or cancelled missions")
            m.state = MissionState.pending
            self._validate_no_cycles()
            self._save()

    def list(self) -> List[Dict[str, Any]]:
        """Return all missions as list of dicts, deterministically ordered by priority, creation seq, id."""
        # No need to persist; read-only
        with _FileLock(self._lock_path):
            self._load()
            items = list(self._missions.values())
            items.sort(key=lambda m: (-m.priority, m.created_seq, m.id))
            return [m.to_dict() for m in items]

    def get(self, mission_id: str) -> Dict[str, Any]:
        with _FileLock(self._lock_path):
            self._load()
            return self._get_mission_or_raise(mission_id).to_dict()

    def to_json(self) -> str:
        """Deterministic JSON serialization of the current persisted state (without modifying it)."""
        with _FileLock(self._lock_path):
            self._load()
            data = self._serialize_state()
            return json.dumps(data, sort_keys=True, separators=(",", ":"))

    # --------------- Internal helpers ---------------

    def _get_mission_or_raise(self, mission_id: str) -> Mission:
        m = self._missions.get(mission_id)
        if m is None:
            raise KeyError(mission_id)
        return m

    def _deps_completed(self, mission: Mission) -> bool:
        # All dependencies must exist and be completed
        if not mission.dependencies:
            return True
        for dep_id in mission.dependencies:
            dep = self._missions.get(dep_id)
            if dep is None:
                return False
            if dep.state != MissionState.completed:
                return False
        return True

    def _state_path_dir(self) -> str:
        return os.path.dirname(os.path.abspath(self._path)) or os.getcwd()

    def _serialize_state(self) -> Dict[str, Any]:
        # Deterministic state structure.
        return {
            "version": 1,
            "next_seq": int(self._next_seq),
            "missions": {k: v.to_dict() for k, v in sorted(self._missions.items(), key=lambda kv: kv[0])},
        }

    def _save(self) -> None:
        data = self._serialize_state()
        content = json.dumps(data, sort_keys=True, separators=(",", ":"))
        d = self._state_path_dir()
        base = os.path.basename(self._path)
        # Use NamedTemporaryFile for atomic replace
        with tempfile.NamedTemporaryFile("w", dir=d, prefix=base + ".", suffix=".tmp", delete=False, encoding="utf-8") as tf:
            tmp_path = tf.name
            tf.write(content)
            tf.flush()
            os.fsync(tf.fileno())
        # Atomic replace
        os.replace(tmp_path, self._path)

    def _load(self) -> None:
        if not os.path.exists(self._path):
            self._missions = {}
            self._next_seq = 1
            return
        with open(self._path, "r", encoding="utf-8") as fh:
            try:
                raw = json.load(fh)
            except json.JSONDecodeError as exc:
                raise ValueError("Persisted mission queue is not valid JSON") from exc
        if not isinstance(raw, dict):
            raise ValueError("Persisted mission queue root must be an object")
        version = int(raw.get("version", 1))
        if version != 1:
            raise ValueError("Unsupported mission queue version")
        next_seq = int(raw.get("next_seq", 1))
        missions_raw = raw.get("missions", {})
        if not isinstance(missions_raw, dict):
            raise ValueError("Persisted missions must be a mapping")
        missions: Dict[str, Mission] = {}
        for mid, md in missions_raw.items():
            if not isinstance(mid, str) or not isinstance(md, dict):
                raise ValueError("Invalid mission entry in persistence")
            m = Mission.from_dict(md)
            if m.id != mid:
                raise ValueError("Mission id mismatch in persistence")
            if mid in missions:
                raise ValueError("Duplicate mission id in persistence")
            missions[mid] = m
        self._missions = missions
        self._next_seq = max(1, next_seq)
        # Validate dependency graph on load (reject cycles)
        self._validate_no_cycles()

    def _validate_no_cycles(self) -> None:
        # Build adjacency list among known missions only
        graph: Dict[str, List[str]] = {}
        for mid, m in self._missions.items():
            # Self-dependency immediate rejection
            if mid in m.dependencies:
                raise ValueError(f"Circular dependency detected: {mid} depends on itself")
            # Consider only dependencies that exist in the queue for cycle detection
            graph[mid] = sorted([d for d in m.dependencies if d in self._missions])
        # Deterministic DFS with color marking
        WHITE, GRAY, BLACK = 0, 1, 2
        color: Dict[str, int] = {k: WHITE for k in sorted(graph.keys())}

        def dfs(u: str, stack: Tuple[str, ...]) -> None:
            color[u] = GRAY
            for v in graph.get(u, []):
                if color[v] == WHITE:
                    dfs(v, stack + (v,))
                elif color[v] == GRAY:
                    # Back edge: cycle
                    raise ValueError("Circular dependency detected: " + " -> ".join(stack + (v,)))
            color[u] = BLACK

        for node in sorted(graph.keys()):
            if color[node] == WHITE:
                dfs(node, (node,))

    # --------------- Planner/Controller integration helpers ---------------

    def enqueue_from_planner(self, missions: Iterable[Dict[str, Any]]) -> None:
        """Bulk enqueue missions coming from an AI Planner output.
        Each item must include: id (str), priority (int), and optional dependencies (list[str]) and max_retries (int).
        This method is atomic at the mission level: failures abort the batch at first invalid mission, leaving queue unchanged for remaining items.
        """
        # We do not support transactional all-or-nothing batches to keep implementation simple and deterministic.
        for item in missions:
            self.enqueue(
                mission_id=str(item["id"]),
                priority=int(item["priority"]),
                dependencies=list(item.get("dependencies", [])),
                max_retries=int(item.get("max_retries", self._default_max_retries)),
            )


__all__ = [
    "MissionQueue",
    "MissionState",
]
