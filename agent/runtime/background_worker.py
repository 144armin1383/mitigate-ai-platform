from __future__ import annotations

import argparse
import signal
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Protocol, Union


# Protocols for dependency injection
class MissionQueueProtocol(Protocol):
    def claim(self, worker_id: str) -> Optional[Dict[str, Any]]:  # returns mission dict with at least 'id'
        ...

    def complete(self, mission_id: str) -> None:
        ...

    def retry(self, mission_id: str) -> None:
        ...

    def fail(self, mission_id: str) -> None:
        ...

    def block(self, mission_id: str) -> None:
        ...

    def recover_stale(self, worker_id: str) -> List[str]:  # returns recovered mission_ids
        ...


class AutonomousControllerProtocol(Protocol):
    def execute(self, mission: Dict[str, Any]) -> Union[str, Dict[str, Any]]:
        ...


@dataclass(frozen=True)
class ExecutionResult:
    status: str  # "success" | "retry" | "exhausted" | "blocked"


# Minimal directory-backed queue used by CLI fallback. It does nothing (always idle),
# ensuring no filesystem mutations occur during single-run maintenance.
class _DirectoryIdleQueue:
    def __init__(self, path: str) -> None:
        self._path = path

    def claim(self, worker_id: str) -> Optional[Dict[str, Any]]:  # type: ignore[override]
        return None

    def complete(self, mission_id: str) -> None:  # type: ignore[override]
        return None

    def retry(self, mission_id: str) -> None:  # type: ignore[override]
        return None

    def fail(self, mission_id: str) -> None:  # type: ignore[override]
        return None

    def block(self, mission_id: str) -> None:  # type: ignore[override]
        return None

    def recover_stale(self, worker_id: str) -> List[str]:  # type: ignore[override]
        return []


# Minimal no-op controller used by CLI fallback
class _NoOpController:
    def execute(self, mission: Dict[str, Any]) -> Union[str, Dict[str, Any]]:
        return "success"


def _utc_timestamp() -> str:
    # ISO-8601 UTC with seconds precision for deterministic formatting
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time()))


class BackgroundWorker:
    """
    Persistent background worker that polls a mission queue and executes
    missions via an autonomous controller.

    Constructor Contract:
    - Directly instantiable with dependency-injected queue and controller.
    - Parameters once, worker_id, poll_interval, and max_idle_cycles appear only once.
    - Accept keyword overrides without duplicating arguments.
    """

    def __init__(
        self,
        queue: MissionQueueProtocol,
        controller: AutonomousControllerProtocol,
        *,
        once: bool = False,
        worker_id: Optional[str] = None,
        poll_interval: float = 5.0,
        max_idle_cycles: Optional[int] = None,
    ) -> None:
        if poll_interval <= 0:
            raise ValueError("poll_interval must be > 0")
        if max_idle_cycles is not None and max_idle_cycles < 0:
            raise ValueError("max_idle_cycles must be >= 0 or None")

        self._queue: MissionQueueProtocol = queue
        self._controller: AutonomousControllerProtocol = controller
        self.once: bool = bool(once)
        self.worker_id: str = worker_id if worker_id is not None else "worker"
        self.poll_interval: float = float(poll_interval)
        self.max_idle_cycles: Optional[int] = max_idle_cycles

        self._shutdown_requested: bool = False
        self._shutdown_event_emitted: bool = False
        self._recovered: bool = False
        self._idle_cycles: int = 0
        self._lock = threading.Lock()

        # Deterministic structured events retained in memory
        self.events: List[Dict[str, Any]] = []

        # Install signal handlers for graceful shutdown
        self._install_signal_handlers()

    # Signal handling
    def _install_signal_handlers(self) -> None:
        # Register signal handlers in main thread only; ignore failures in non-main threads
        try:
            if threading.current_thread() is threading.main_thread():
                signal.signal(signal.SIGINT, self._handle_signal)
                try:
                    signal.signal(signal.SIGTERM, self._handle_signal)
                except Exception:
                    # Some platforms may not support SIGTERM in the same way
                    pass
        except Exception:
            # Best-effort; do not crash if signals cannot be set
            pass

    def _handle_signal(self, signum: int, frame: Optional[Any]) -> None:  # pragma: no cover (indirectly tested)
        self.request_shutdown()

    def request_shutdown(self) -> None:
        with self._lock:
            self._shutdown_requested = True

    # Event emission
    def _emit(self, event: str, mission_id: Optional[str] = None, **extra: Any) -> None:
        record: Dict[str, Any] = {
            "event": event,
            "timestamp": _utc_timestamp(),
        }
        if mission_id is not None:
            record["mission_id"] = mission_id
        # Attach any non-sensitive extra fields (do not include payloads or secrets)
        for k, v in extra.items():
            # Only simple JSON-serializable values should be added; avoid logging payloads
            if k not in ("payload", "secret", "token", "password"):
                record[k] = v
        self.events.append(record)

    # Recovery on startup
    def _recover_once(self) -> None:
        if self._recovered:
            return
        self._recovered = True
        try:
            recovered: Iterable[str] = self._queue.recover_stale(self.worker_id)
        except AttributeError:
            recovered = []
        for mission_id in recovered:
            self._emit("recovered", mission_id=mission_id)

    def _should_stop(self) -> bool:
        with self._lock:
            return self._shutdown_requested

    def run(self) -> None:
        """
        Run the worker loop. In once mode, perform a single polling/processing cycle.
        """
        self._recover_once()

        while True:
            # Exclusive claim is the only acquisition boundary
            mission: Optional[Dict[str, Any]] = self._queue.claim(self.worker_id)

            if mission is None:
                # Empty poll cycle
                self._emit("idle")
                self._idle_cycles += 1

                # If graceful shutdown has been requested, emit shutdown exactly once then exit
                if self._should_stop():
                    if not self._shutdown_event_emitted:
                        self._emit("shutdown")
                        self._shutdown_event_emitted = True
                    break

                # In single-run mode, exit after the first idle cycle
                if self.once:
                    break

                # Terminate after hitting max idle cycles (emit idle before evaluating)
                if self.max_idle_cycles is not None and self._idle_cycles >= self.max_idle_cycles:
                    break

                time.sleep(self.poll_interval)
                continue

            # We claimed a mission; reset idle counter
            self._idle_cycles = 0
            mission_id = str(mission.get("id"))
            # Emit claimed event upon successful exclusive claim
            self._emit("claimed", mission_id=mission_id)

            # Execute via controller
            result = self._controller.execute(mission)
            status: str
            if isinstance(result, dict):
                status = str(result.get("status"))
            else:
                status = str(result)

            # Map controller status to queue state transitions
            if status == "success":
                self._queue.complete(mission_id)
                self._emit("completed", mission_id=mission_id)
            elif status == "retry":
                # MissionQueue.fail() is the single retry-budget authority:
                # it atomically moves running -> retrying while budget remains,
                # otherwise running -> failed.
                self._queue.fail(mission_id)
                self._emit("retrying", mission_id=mission_id)
            elif status == "exhausted":
                # Controller-level retries are exhausted. Queue transition still
                # goes through fail() so attempt accounting remains centralized.
                self._queue.fail(mission_id)
                self._emit("failed", mission_id=mission_id)
            elif status == "blocked":
                # Policy/security failure path
                self._queue.block(mission_id)
                # Use failed event with reason to adhere to the logging contract while signaling blockage
                self._emit("failed", mission_id=mission_id, reason="blocked")
            else:
                # Unknown controller output fails closed. Do not create an
                # implicit retry path outside the established retry authority.
                self._queue.block(mission_id)
                self._emit(
                    "failed",
                    mission_id=mission_id,
                    reason="unknown_status",
                )

            # In once mode, exit after processing a single claimed mission
            if self.once:
                break

            # If shutdown was requested during processing, we exit cleanly at next idle cycle.

    # CLI helpers
    @staticmethod
    def build_arg_parser() -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog="background_worker",
            description=(
                "Autonomous Background Worker: consumes missions from a queue and executes them via controller."
            ),
        )
        parser.add_argument(
            "--queue-path",
            dest="queue_path",
            required=True,
            help="Path to the mission queue or queue directory",
        )
        parser.add_argument(
            "--once",
            dest="once",
            action="store_true",
            help="Process at most one mission or idle cycle, then exit",
        )
        parser.add_argument(
            "--poll-interval",
            dest="poll_interval",
            type=float,
            default=5.0,
            help="Polling interval in seconds (default: 5.0)",
        )
        parser.add_argument(
            "--worker-id",
            dest="worker_id",
            default="worker",
            help="Identifier for this worker instance",
        )
        parser.add_argument(
            "--max-idle-cycles",
            dest="max_idle_cycles",
            type=int,
            default=None,
            help="Maximum consecutive idle polling cycles before exit (default: unlimited)",
        )
        return parser


def _construct_queue_and_controller(queue_path: str) -> tuple[MissionQueueProtocol, AutonomousControllerProtocol]:
    """
    Best-effort construction of queue and controller for CLI context.
    Falls back to internal minimal implementations to avoid side effects.
    """
    # Attempt to discover external implementations, but do not require them
    queue: MissionQueueProtocol = _DirectoryIdleQueue(queue_path)
    controller: AutonomousControllerProtocol = _NoOpController()

    try:
        # Prefer package-relative imports if available
        try:
            from agent.runtime import mission_queue as mq  # type: ignore
        except Exception:  # pragma: no cover - fallback path only when executed in agent/ working dir
            from runtime import mission_queue as mq  # type: ignore
        # Heuristic construction: try common factory names
        if hasattr(mq, "open_queue"):
            queue = mq.open_queue(queue_path)  # type: ignore[attr-defined]
        elif hasattr(mq, "MissionQueue"):
            queue = mq.MissionQueue(queue_path)  # type: ignore[attr-defined]
        elif hasattr(mq, "FileMissionQueue"):
            queue = mq.FileMissionQueue(queue_path)  # type: ignore[attr-defined]
    except Exception:
        # Fallback to idle queue
        queue = _DirectoryIdleQueue(queue_path)

    try:
        try:
            from agent.ai import autonomous_controller as ac  # type: ignore
        except Exception:  # pragma: no cover - fallback path only when executed in agent/ working dir
            from runtime.ai import autonomous_controller as ac  # type: ignore
        if hasattr(ac, "AutonomousController"):
            controller = ac.AutonomousController()  # type: ignore[attr-defined]
    except Exception:
        controller = _NoOpController()

    return queue, controller


def cli_main(argv: Optional[List[str]] = None) -> int:
    parser = BackgroundWorker.build_arg_parser()
    args = parser.parse_args(argv)

    # Validate arguments deterministically via argparse semantics
    if args.poll_interval <= 0:
        raise SystemExit("poll-interval must be > 0")
    if args.max_idle_cycles is not None and args.max_idle_cycles < 0:
        raise SystemExit("max-idle-cycles must be >= 0 or omitted")

    queue, controller = _construct_queue_and_controller(args.queue_path)

    worker = BackgroundWorker(
        queue=queue,
        controller=controller,
        once=bool(args.once),
        worker_id=str(args.worker_id),
        poll_interval=float(args.poll_interval),
        max_idle_cycles=args.max_idle_cycles,
    )

    worker.run()
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(cli_main())
