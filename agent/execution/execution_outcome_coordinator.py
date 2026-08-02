from __future__ import annotations

import json
import threading
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Set, Tuple
import re


AllowedStatus = {"completed", "failed", "blocked", "cancelled", "retrying"}


class ExecutionOutcomeValidationError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class CoordinatorConfig:
    # Reserved for future configurability (e.g., max metadata size)
    max_changed_files: int = 1024


class ExecutionOutcomeCoordinator:
    """
    Coordinates processing of a single mission execution outcome.

    This class is dependency-injected and uses only provided public interfaces:
      - project_resolver: resolve(project_id) -> object or raises/returns None on unknown
      - mission_status_writer: update_status(project_id, mission_id, status, *, completed_at: datetime,
         blocked_reason: Optional[str] = None) -> dict with keys: {accepted: bool, failure_code?: str,
         mission_not_found?: bool, invalid_status_transition?: bool}
      - usage_ledger: record_usage(usage: Mapping[str, Any]) -> dict with keys {ok: bool, failure_code?: str}
      - report_writer: store_report(outcome: Mapping[str, Any]) -> dict with keys {ok: bool, failure_code?: str}
      - clock: provides utcnow() -> datetime (tz-aware UTC) [optional]
      - id_generator: next_id() -> str deterministic unique ID
      - event_sink: emit(event_name: str, payload: Mapping[str, Any]) -> None

    Public methods:
      - process(outcome)
      - validate_outcome(outcome)
      - get_result(execution_id)
      - status(project_id=None)
      - latest_events(limit, project_id=None)
    """

    def __init__(
        self,
        *,
        project_resolver: Any,
        mission_status_writer: Any,
        usage_ledger: Any,
        report_writer: Any,
        clock: Any,
        id_generator: Any,
        event_sink: Any,
        config: Optional[CoordinatorConfig] = None,
    ) -> None:
        self._project_resolver = project_resolver
        self._mission_status_writer = mission_status_writer
        self._usage_ledger = usage_ledger
        self._report_writer = report_writer
        self._clock = clock
        self._id_generator = id_generator
        self._event_sink = event_sink
        self._config = config or CoordinatorConfig()

        self._lock = threading.Lock()
        self._inflight: Set[str] = set()
        self._results: Dict[str, Dict[str, Any]] = {}
        self._events: List[Dict[str, Any]] = []
        self._usage_recorded_exec_ids: Set[str] = set()

    # ---------------------- Public Interface ----------------------

    def validate_outcome(self, outcome: Mapping[str, Any]) -> Mapping[str, Any]:
        """
        Validate the execution outcome according to constraints.
        Returns a deep-copied validated mapping. Does not mutate input.

        Raises ExecutionOutcomeValidationError with .code set to a failure code on invalid input.
        """
        if not isinstance(outcome, Mapping):
            raise ExecutionOutcomeValidationError("invalid_execution_outcome", "Outcome must be a mapping.")

        # Strict field whitelist
        allowed_fields = {
            "execution_id",
            "project_id",
            "request_id",
            "conversation_id",
            "plan_id",
            "mission_id",
            "step_id",
            "task_type",
            "provider_id",
            "model_id",
            "worker_id",
            "started_at",
            "completed_at",
            "status",
            "success",
            "retryable",
            "fallback_used",
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "estimated_cost",
            "cost_currency",
            "safe_error_code",
            "summary",
            "changed_files",
            "git_branch",
            "git_commit",
            "validation_status",
            "metadata",
        }

        unknown = [k for k in outcome.keys() if k not in allowed_fields]
        if unknown:
            raise ExecutionOutcomeValidationError(
                "invalid_execution_outcome", f"Unknown fields: {', '.join(sorted(str(x) for x in unknown))}"
            )

        # Deep copy to avoid mutating original input
        data = deepcopy(dict(outcome))

        # Required identifiers (non-empty strings)
        required_str_fields = [
            "execution_id",
            "project_id",
            "request_id",
            "mission_id",
            "status",
        ]
        for f in required_str_fields:
            v = data.get(f)
            if not isinstance(v, str) or not v.strip():
                raise ExecutionOutcomeValidationError(
                    "invalid_execution_outcome", f"Field '{f}' must be a non-empty string."
                )

        # Optional identifier string fields
        optional_str_fields = [
            "conversation_id",
            "plan_id",
            "step_id",
            "task_type",
            "provider_id",
            "model_id",
            "worker_id",
            "git_branch",
            "git_commit",
            "safe_error_code",
            "validation_status",
        ]
        for f in optional_str_fields:
            if f in data and data[f] is not None and not (isinstance(data[f], str) and data[f].strip() != ""):
                raise ExecutionOutcomeValidationError(
                    "invalid_execution_outcome", f"Field '{f}' must be a non-empty string if provided."
                )

        # status constraints
        status = data.get("status")
        if status not in AllowedStatus:
            raise ExecutionOutcomeValidationError("invalid_execution_outcome", f"Unsupported status: {status}")

        # success, retryable, fallback_used booleans
        for f in ("success", "retryable", "fallback_used"):
            if f not in data:
                raise ExecutionOutcomeValidationError("invalid_execution_outcome", f"Missing field '{f}'.")
            if not isinstance(data[f], bool):
                raise ExecutionOutcomeValidationError(
                    "invalid_execution_outcome", f"Field '{f}' must be a boolean."
                )

        # status/success logical consistency
        success = bool(data["success"])
        retryable = bool(data["retryable"])
        if status == "completed" and not success:
            raise ExecutionOutcomeValidationError(
                "invalid_execution_outcome", "Status 'completed' requires success=True."
            )
        if status in {"failed", "blocked", "cancelled"} and success:
            raise ExecutionOutcomeValidationError(
                "invalid_execution_outcome", f"Status '{status}' requires success=False."
            )
        if status == "retrying" and not retryable:
            raise ExecutionOutcomeValidationError(
                "invalid_execution_outcome", "Status 'retrying' requires retryable=True."
            )

        # timestamps: tz-aware UTC and ordering
        for f in ("started_at", "completed_at"):
            if f not in data or not isinstance(data[f], datetime):
                raise ExecutionOutcomeValidationError(
                    "invalid_execution_outcome", f"Field '{f}' must be a datetime."
                )
            if data[f].tzinfo is None or data[f].utcoffset() != timezone.utc.utcoffset(data[f]):
                # Compare with UTC offset zero
                if data[f].tzinfo is None or data[f].utcoffset() is None or data[f].utcoffset().total_seconds() != 0:
                    raise ExecutionOutcomeValidationError(
                        "invalid_execution_outcome", f"Field '{f}' must be timezone-aware UTC."
                    )
        if data["completed_at"] < data["started_at"]:
            raise ExecutionOutcomeValidationError(
                "invalid_execution_outcome", "completed_at must not be earlier than started_at."
            )

        # tokens: non-negative integers and total equals sum
        for f in ("input_tokens", "output_tokens", "total_tokens"):
            if f not in data:
                raise ExecutionOutcomeValidationError(
                    "invalid_execution_outcome", f"Missing field '{f}'."
                )
            if not isinstance(data[f], int) or data[f] < 0:
                raise ExecutionOutcomeValidationError(
                    "invalid_execution_outcome", f"Field '{f}' must be a non-negative integer."
                )
        if data["total_tokens"] != data["input_tokens"] + data["output_tokens"]:
            raise ExecutionOutcomeValidationError(
                "invalid_execution_outcome", "total_tokens must equal input_tokens + output_tokens."
            )

        # estimated_cost: non-negative or None
        if "estimated_cost" in data and data["estimated_cost"] is not None:
            if not isinstance(data["estimated_cost"], (int, float)) or data["estimated_cost"] < 0:
                raise ExecutionOutcomeValidationError(
                    "invalid_execution_outcome", "estimated_cost must be non-negative or null."
                )
            # if cost present, currency must be non-empty string
            if "cost_currency" not in data or not isinstance(data["cost_currency"], str) or not data["cost_currency"].strip():
                raise ExecutionOutcomeValidationError(
                    "invalid_execution_outcome", "cost_currency must be provided when estimated_cost is set."
                )
        else:
            # Unknown cost must remain null, ensure we don't fabricate
            data["estimated_cost"] = None

        if "cost_currency" in data and data["estimated_cost"] is None:
            # If no cost, normalize currency to None to avoid implying a known cost
            if data["cost_currency"] is not None:
                # Allow currency to be present but do not reject; we can pass-through but ensure JSON-safe
                if not isinstance(data["cost_currency"], str) and data["cost_currency"] is not None:
                    raise ExecutionOutcomeValidationError(
                        "invalid_execution_outcome", "cost_currency must be a string or null."
                    )

        # changed_files validation
        if "changed_files" in data and data["changed_files"] is not None:
            if not isinstance(data["changed_files"], list):
                raise ExecutionOutcomeValidationError(
                    "invalid_execution_outcome", "changed_files must be a list of safe relative paths."
                )
            if len(data["changed_files"]) > self._config.max_changed_files:
                raise ExecutionOutcomeValidationError(
                    "invalid_execution_outcome", "Too many changed_files entries."
                )
            for p in data["changed_files"]:
                if not isinstance(p, str) or not p:
                    raise ExecutionOutcomeValidationError(
                        "invalid_execution_outcome", "changed_files must contain non-empty strings."
                    )
                if not self._is_safe_rel_path(p):
                    raise ExecutionOutcomeValidationError(
                        "invalid_execution_outcome", f"Unsafe path in changed_files: {p}"
                    )

        # metadata must be JSON-safe
        if "metadata" in data and data["metadata"] is not None:
            try:
                json.dumps(data["metadata"], allow_nan=False)
            except Exception as exc:  # noqa: BLE001
                raise ExecutionOutcomeValidationError(
                    "invalid_execution_outcome", f"metadata must be JSON-serializable: {exc}"
                )

        # summary can be any string; we do not persist raw summary here, only pass-through. Validate type only.
        if "summary" in data and data["summary"] is not None and not isinstance(data["summary"], str):
            raise ExecutionOutcomeValidationError(
                "invalid_execution_outcome", "summary must be a string if provided."
            )

        return data

    def process(self, outcome: Mapping[str, Any]) -> Dict[str, Any]:
        """
        Process one execution outcome according to the defined rules.
        Returns a deterministic result mapping. Never mutates the input.
        """
        # Emit received event early (sanitized)
        self._emit_event(
            "execution_outcome_received",
            self._safe_event_payload({
                "execution_id": outcome.get("execution_id"),
                "project_id": outcome.get("project_id"),
                "mission_id": outcome.get("mission_id"),
                "status": outcome.get("status"),
            }),
        )

        try:
            data = self.validate_outcome(outcome)
        except ExecutionOutcomeValidationError as ve:
            result = self._reject_result(outcome, failure_code=ve.code)
            self._emit_event(
                "execution_outcome_rejected",
                self._safe_event_payload({
                    "execution_id": outcome.get("execution_id"),
                    "project_id": outcome.get("project_id"),
                    "mission_id": outcome.get("mission_id"),
                    "failure_code": ve.code,
                }),
            )
            return result
        except Exception:
            result = self._reject_result(outcome, failure_code="invalid_execution_outcome")
            self._emit_event(
                "execution_outcome_rejected",
                self._safe_event_payload({
                    "execution_id": outcome.get("execution_id"),
                    "project_id": outcome.get("project_id"),
                    "mission_id": outcome.get("mission_id"),
                    "failure_code": "invalid_execution_outcome",
                }),
            )
            return result

        execution_id = data["execution_id"]

        # Duplicate detection must be atomic, but events must be emitted
        # only after releasing the non-reentrant coordinator lock.
        duplicate_result = None
        with self._lock:
            if execution_id in self._results:
                duplicate_result = deepcopy(self._results[execution_id])
            elif execution_id in self._inflight:
                duplicate_result = self._reject_result(
                    data,
                    failure_code="duplicate_execution",
                )
            else:
                self._inflight.add(execution_id)

        if duplicate_result is not None:
            self._emit_event(
                "duplicate_execution_detected",
                self._safe_event_payload({
                    "execution_id": execution_id,
                    "project_id": data["project_id"],
                    "mission_id": data["mission_id"],
                }),
            )
            return duplicate_result

        # Resolve project
        try:
            project_obj = self._project_resolver.resolve(data["project_id"])  # type: ignore[attr-defined]
        except Exception:
            project_obj = None
        if not project_obj:
            result = self._failure_result(data, failure_code="cross_project_reference")
            self._finalize_result(execution_id, result)
            self._emit_event(
                "execution_outcome_failed",
                self._safe_event_payload({
                    "execution_id": execution_id,
                    "project_id": data["project_id"],
                    "mission_id": data["mission_id"],
                    "failure_code": "cross_project_reference",
                }),
            )
            return result

        # 3. Update mission status via injected interface
        blocked_reason: Optional[str] = None
        if data["status"] == "blocked":
            blocked_reason = data.get("validation_status") or data.get("safe_error_code")
        try:
            msr = self._mission_status_writer.update_status(
                data["project_id"],
                data["mission_id"],
                data["status"],
                completed_at=data["completed_at"],
                blocked_reason=blocked_reason,
            )
        except Exception:
            msr = {"accepted": False, "failure_code": "mission_status_update_failed"}

        if not isinstance(msr, Mapping) or not msr.get("accepted"):
            failure_code = (
                "mission_not_found"
                if bool(msr.get("mission_not_found"))
                else "invalid_status_transition"
                if bool(msr.get("invalid_status_transition"))
                else str(msr.get("failure_code") or "mission_status_update_failed")
            )
            # Stop further processing per rules
            result = self._failure_result(data, failure_code=failure_code)
            self._finalize_result(execution_id, result)
            self._emit_event(
                "mission_status_update_failed",
                self._safe_event_payload({
                    "execution_id": execution_id,
                    "project_id": data["project_id"],
                    "mission_id": data["mission_id"],
                    "failure_code": failure_code,
                }),
            )
            return result

        self._emit_event(
            "mission_status_updated",
            self._safe_event_payload({
                "execution_id": execution_id,
                "project_id": data["project_id"],
                "mission_id": data["mission_id"],
                "status": data["status"],
            }),
        )

        # 4. Record provider usage exactly once per execution_id
        usage_recorded = False
        try:
            with self._lock:
                already_recorded = execution_id in self._usage_recorded_exec_ids
            if not already_recorded:
                usage_id = self._id_generator.next_id()
                usage = self._build_usage_record(usage_id, data)
                try:
                    ur = self._usage_ledger.record_usage(usage)
                except Exception:
                    ur = {"ok": False, "failure_code": "usage_recording_failed"}
                if not isinstance(ur, Mapping) or not ur.get("ok"):
                    failure_code = str(ur.get("failure_code") or "usage_recording_failed")
                    result = self._failure_result(data, failure_code=failure_code)
                    self._finalize_result(execution_id, result)
                    self._emit_event(
                        "usage_recording_failed",
                        self._safe_event_payload({
                            "execution_id": execution_id,
                            "project_id": data["project_id"],
                            "mission_id": data["mission_id"],
                            "failure_code": failure_code,
                        }),
                    )
                    return result
                usage_recorded = True
                with self._lock:
                    self._usage_recorded_exec_ids.add(execution_id)
                self._emit_event(
                    "usage_recorded",
                    self._safe_event_payload({
                        "execution_id": execution_id,
                        "project_id": data["project_id"],
                        "mission_id": data["mission_id"],
                        "usage_id": usage_id,
                    }),
                )
            else:
                usage_recorded = True
        except Exception:
            # Safety fallback
            result = self._failure_result(data, failure_code="usage_recording_failed")
            self._finalize_result(execution_id, result)
            self._emit_event(
                "usage_recording_failed",
                self._safe_event_payload({
                    "execution_id": execution_id,
                    "project_id": data["project_id"],
                    "mission_id": data["mission_id"],
                    "failure_code": "usage_recording_failed",
                }),
            )
            return result

        # 5. Persist the execution report via ExecutionReportWriter
        report_persisted = False
        try:
            rr = self._report_writer.store_report(deepcopy(outcome))
        except Exception:
            rr = {"ok": False, "failure_code": "report_persistence_failed"}
        if not isinstance(rr, Mapping) or not rr.get("ok"):
            failure_code = str(rr.get("failure_code") or "report_persistence_failed")
            result = self._partial_result(
                data,
                accepted=False,
                usage_recorded=usage_recorded,
                report_persisted=False,
                failure_code=failure_code,
            )
            self._finalize_result(execution_id, result)
            self._emit_event(
                "execution_report_persistence_failed",
                self._safe_event_payload({
                    "execution_id": execution_id,
                    "project_id": data["project_id"],
                    "mission_id": data["mission_id"],
                    "failure_code": failure_code,
                }),
            )
            return result

        report_persisted = True
        self._emit_event(
            "execution_report_persisted",
            self._safe_event_payload({
                "execution_id": execution_id,
                "project_id": data["project_id"],
                "mission_id": data["mission_id"],
            }),
        )

        # 6. Emit completion events and return success
        result = self._partial_result(
            data,
            accepted=True,
            usage_recorded=usage_recorded,
            report_persisted=report_persisted,
            failure_code=None,
        )
        self._finalize_result(execution_id, result)
        self._emit_event(
            "execution_outcome_completed",
            self._safe_event_payload({
                "execution_id": execution_id,
                "project_id": data["project_id"],
                "mission_id": data["mission_id"],
                "status": data["status"],
            }),
        )
        return result

    def get_result(self, execution_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            r = self._results.get(execution_id)
            return deepcopy(r) if r is not None else None

    def status(self, project_id: Optional[str] = None) -> Dict[str, Any]:
        with self._lock:
            results = list(self._results.values())
            if project_id is not None:
                results = [r for r in results if r.get("project_id") == project_id]
            total = len(results)
            accepted = sum(1 for r in results if r.get("accepted"))
            failed = sum(1 for r in results if not r.get("accepted"))
            duplicates = 0  # duplicates are not stored as separate results
            return {
                "total": total,
                "accepted": accepted,
                "failed": failed,
                "duplicates": duplicates,
            }

    def latest_events(self, limit: int, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if not isinstance(limit, int) or limit <= 0:
            limit = 10
        with self._lock:
            evs = list(self._events)
        if project_id is not None:
            evs = [e for e in evs if e.get("project_id") == project_id]
        return evs[-limit:]

    # ---------------------- Internal Helpers ----------------------

    def _reject_result(self, outcome: Mapping[str, Any], *, failure_code: str) -> Dict[str, Any]:
        execution_id = outcome.get("execution_id") if isinstance(outcome, Mapping) else None
        project_id = outcome.get("project_id") if isinstance(outcome, Mapping) else None
        mission_id = outcome.get("mission_id") if isinstance(outcome, Mapping) else None
        status_value = outcome.get("status") if isinstance(outcome, Mapping) else None
        completed_at = outcome.get("completed_at") if isinstance(outcome, Mapping) else None
        return {
            "accepted": False,
            "execution_id": execution_id,
            "project_id": project_id,
            "request_id": outcome.get("request_id") if isinstance(outcome, Mapping) else None,
            "mission_id": mission_id,
            "status": status_value,
            "usage_recorded": False,
            "report_persisted": False,
            "duplicate": False,
            "blocked_reason": None,
            "completed_at": completed_at,
            "failure_code": failure_code,
        }

    def _failure_result(self, data: Mapping[str, Any], *, failure_code: str) -> Dict[str, Any]:
        return {
            "accepted": False,
            "execution_id": data["execution_id"],
            "project_id": data["project_id"],
            "request_id": data.get("request_id"),
            "mission_id": data.get("mission_id"),
            "status": data.get("status"),
            "usage_recorded": False,
            "report_persisted": False,
            "duplicate": False,
            "blocked_reason": data.get("validation_status") if data.get("status") == "blocked" else None,
            "completed_at": data.get("completed_at"),
            "failure_code": failure_code,
        }

    def _partial_result(
        self,
        data: Mapping[str, Any],
        *,
        accepted: bool,
        usage_recorded: bool,
        report_persisted: bool,
        failure_code: Optional[str],
    ) -> Dict[str, Any]:
        return {
            "accepted": bool(accepted),
            "execution_id": data["execution_id"],
            "project_id": data["project_id"],
            "request_id": data.get("request_id"),
            "mission_id": data.get("mission_id"),
            "status": data.get("status"),
            "usage_recorded": bool(usage_recorded),
            "report_persisted": bool(report_persisted),
            "duplicate": False,
            "blocked_reason": data.get("validation_status") if data.get("status") == "blocked" else None,
            "completed_at": data.get("completed_at"),
            **({"failure_code": failure_code} if failure_code else {}),
        }

    def _store_result_once(self, result: Mapping[str, Any]) -> None:
        execution_id = result.get("execution_id")
        if not isinstance(execution_id, str) or not execution_id:
            return
        with self._lock:
            if execution_id not in self._results:
                self._results[execution_id] = deepcopy(dict(result))

    def _finalize_result(self, execution_id: str, result: Mapping[str, Any]) -> None:
        with self._lock:
            self._results[execution_id] = deepcopy(dict(result))
            self._inflight.discard(execution_id)

    def _build_usage_record(self, usage_id: str, data: Mapping[str, Any]) -> Dict[str, Any]:
        return {
            "usage_id": usage_id,
            "project_id": data.get("project_id"),
            "request_id": data.get("request_id"),
            "mission_id": data.get("mission_id"),
            "conversation_id": data.get("conversation_id"),
            "task_type": data.get("task_type"),
            "provider_id": data.get("provider_id"),
            "model_id": data.get("model_id"),
            "started_at": data.get("started_at"),
            "completed_at": data.get("completed_at"),
            "input_tokens": data.get("input_tokens"),
            "output_tokens": data.get("output_tokens"),
            "total_tokens": data.get("total_tokens"),
            "estimated_cost": data.get("estimated_cost"),
            "cost_currency": data.get("cost_currency"),
            "fallback_used": data.get("fallback_used"),
            "success": data.get("success"),
            "safe_error_code": data.get("safe_error_code"),
        }

    def _emit_event(self, name: str, payload: Mapping[str, Any]) -> None:
        event = {"event": name, **dict(payload)}
        try:
            self._event_sink.emit(name, dict(payload))
        except Exception:
            # Swallow event sink failures for safety; still record locally
            pass
        with self._lock:
            self._events.append(event)

    @staticmethod
    def _is_safe_rel_path(p: str) -> bool:
        # Reject absolute paths, drive letters, UNC paths, parent traversal, and control chars
        if not p or not isinstance(p, str):
            return False
        if any(ord(ch) < 32 for ch in p):
            return False
        if p.startswith("/") or p.startswith("\\"):
            return False
        if re.match(r"^[A-Za-z]:\\", p) or re.match(r"^[A-Za-z]:/", p):
            return False
        # Normalize and inspect components for traversal
        parts = [seg for seg in re.split(r"[\\/]+", p) if seg not in ("", ".")]
        if any(seg == ".." for seg in parts):
            return False
        return True

    @staticmethod
    def _safe_event_payload(payload: Mapping[str, Any]) -> Dict[str, Any]:
        # Redact potential sensitive or large fields; allow only known safe keys
        allowed = {
            "execution_id",
            "project_id",
            "mission_id",
            "status",
            "failure_code",
            "usage_id",
        }
        return {k: v for k, v in payload.items() if k in allowed}


__all__ = ["ExecutionOutcomeCoordinator", "CoordinatorConfig", "ExecutionOutcomeValidationError"]
