from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Set, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone


# Exceptions
class PlanValidationError(Exception):
    """Base class for structured validation and safety errors."""

    code: str

    def __init__(self, message: str = "", *, code: str = "invalid_plan") -> None:
        super().__init__(message)
        self.code = code


class InvalidApprovedRequestError(PlanValidationError):
    def __init__(self, message: str = "Invalid approved request") -> None:
        super().__init__(message, code="invalid_approved_request")


class InvalidPlanError(PlanValidationError):
    def __init__(self, message: str = "Invalid plan") -> None:
        super().__init__(message, code="invalid_plan")


class DuplicateStepError(PlanValidationError):
    def __init__(self, message: str = "Duplicate step identifier") -> None:
        super().__init__(message, code="duplicate_step")


class UnknownDependencyError(PlanValidationError):
    def __init__(self, message: str = "Unknown dependency") -> None:
        super().__init__(message, code="unknown_dependency")


class SelfDependencyError(PlanValidationError):
    def __init__(self, message: str = "Self dependency is not allowed") -> None:
        super().__init__(message, code="self_dependency")


class CircularDependencyError(PlanValidationError):
    def __init__(self, message: str = "Circular dependency detected") -> None:
        super().__init__(message, code="circular_dependency")


class UnsafePayloadError(PlanValidationError):
    def __init__(self, message: str = "Unsafe payload") -> None:
        super().__init__(message, code="unsafe_payload")


# Typing aliases
JSONScalar = Optional[object]
JSONValue = object


@dataclass(frozen=True)
class _MissionMeta:
    mission_id: str
    step_id: str
    priority: int
    original_index: int


class PlanValidatorMissionBuilder:
    """
    Validates approved requests and plans and builds deterministic, project-scoped mission objects.

    Priority ordering direction: lower integer means higher priority (i.e., 0 > 1 > 2).
    Among dependency-ready missions, ordering is deterministic using:
      1) Priority ascending (lower first)
      2) Step ID lexicographic ascending
      3) Original validated step order (stable tie-breaker)

    All mission identifiers are generated once, before dependency conversion.
    Dependencies in each mission are converted to mission_ids and sorted lexicographically.
    Sensitive payload fields are redacted by replacing values with "[redacted]".
    """

    _APPROVED_REQUEST_FIELDS: Set[str] = {
        "request_id",
        "project_id",
        "conversation_id",
        "provider_id",
        "model_id",
        "task_type",
        "created_at",
    }

    _PLAN_FIELDS: Set[str] = {
        "plan_id",
        "request_id",
        "project_id",
        "summary",
        "steps",
    }

    _STEP_FIELDS: Set[str] = {
        "step_id",
        "title",
        "description",
        "dependencies",
        "priority",
        "task_type",
        "payload",
    }

    _FORBIDDEN_PAYLOAD_KEYS: Set[str] = {
        "shell",
        "command",
        "cmd",
        "bash",
        "powershell",
        "subprocess",
        "executable",
        "script",
    }

    _SENSITIVE_KEYS: Set[str] = {
        "password",
        "passwd",
        "secret",
        "token",
        "api_key",
        "api-key",
        "authorization",
        "bearer",
        "credential",
        "private_key",
    }

    def __init__(
        self,
        *,
        supported_task_types: Optional[Set[str]] = None,
        id_generator: Optional[Callable[[], str]] = None,
        clock: Optional[Callable[[], str]] = None,
    ) -> None:
        # If supported_task_types is None or empty, accept any non-empty string as supported.
        self._supported_task_types: Optional[Set[str]] = (
            set(supported_task_types) if supported_task_types else None
        )
        self._id_generator: Callable[[], str] = id_generator or self._default_id_generator
        self._clock: Callable[[], str] = clock or self._default_clock

    # Public API
    def validate_approved_request(self, approved_request: Mapping[str, Any]) -> Dict[str, Any]:
        if not isinstance(approved_request, Mapping):
            raise InvalidApprovedRequestError("Approved request must be a mapping")
        unknown = set(approved_request.keys()) - self._APPROVED_REQUEST_FIELDS
        if unknown:
            raise InvalidApprovedRequestError(
                f"Unknown approved request fields: {sorted(unknown)}"
            )
        required = self._APPROVED_REQUEST_FIELDS
        for field in required:
            if field not in approved_request:
                raise InvalidApprovedRequestError(f"Missing field: {field}")
        # Validate identifiers
        for field in ("request_id", "project_id", "conversation_id", "provider_id", "model_id"):
            self._ensure_non_empty_identifier(approved_request.get(field), error_cls=InvalidApprovedRequestError, field_name=field)
        # Validate task_type supported
        task_type = approved_request.get("task_type")
        if not isinstance(task_type, str) or not task_type.strip():
            raise InvalidApprovedRequestError("task_type must be a non-empty string")
        if self._supported_task_types is not None and task_type not in self._supported_task_types:
            raise InvalidApprovedRequestError(f"Unsupported task_type: {task_type}")
        # created_at must be present; accept any string
        if not isinstance(approved_request.get("created_at"), str):
            raise InvalidApprovedRequestError("created_at must be a string timestamp")
        return dict(approved_request)

    def validate_plan(self, plan: Mapping[str, Any], approved_request: Mapping[str, Any]) -> Dict[str, Any]:
        if not isinstance(plan, Mapping):
            raise InvalidPlanError("Plan must be a mapping")
        unknown = set(plan.keys()) - self._PLAN_FIELDS
        if unknown:
            raise InvalidPlanError(f"Unknown plan fields: {sorted(unknown)}")
        for field in self._PLAN_FIELDS:
            if field not in plan:
                raise InvalidPlanError(f"Missing plan field: {field}")
        # Basic fields
        plan_id = plan.get("plan_id")
        self._ensure_non_empty_identifier(plan_id, error_cls=InvalidPlanError, field_name="plan_id")
        request_id = plan.get("request_id")
        project_id = plan.get("project_id")
        summary = plan.get("summary")
        if request_id != approved_request.get("request_id"):
            raise InvalidPlanError("Plan request_id does not match approved request")
        if project_id != approved_request.get("project_id"):
            raise InvalidPlanError("Plan project_id does not match approved request")
        if not isinstance(summary, str):
            raise InvalidPlanError("Plan summary must be a string")
        steps = plan.get("steps")
        if not isinstance(steps, list):
            raise InvalidPlanError("Plan steps must be a list")
        if len(steps) == 0:
            raise InvalidPlanError("Plan must contain at least one step")

        # Validate steps and collect step_ids
        step_ids: List[str] = []
        step_index_by_id: Dict[str, int] = {}
        for i, step in enumerate(steps):
            if not isinstance(step, Mapping):
                raise InvalidPlanError("Each step must be a mapping")
            unknown_step_fields = set(step.keys()) - self._STEP_FIELDS
            if unknown_step_fields:
                raise InvalidPlanError(f"Unknown step fields: {sorted(unknown_step_fields)}")
            for field in self._STEP_FIELDS:
                if field not in step:
                    raise InvalidPlanError(f"Missing step field: {field}")
            step_id = step.get("step_id")
            self._ensure_non_empty_identifier(step_id, error_cls=InvalidPlanError, field_name="step.step_id")
            if step_id in step_index_by_id:
                raise DuplicateStepError(f"Duplicate step_id: {step_id}")
            step_ids.append(step_id)  # type: ignore[arg-type]
            step_index_by_id[step_id] = i

            # Title/description
            if not isinstance(step.get("title"), str) or not isinstance(step.get("description"), str):
                raise InvalidPlanError("Step title and description must be strings")

            # Priority
            if not isinstance(step.get("priority"), int):
                raise InvalidPlanError("Step priority must be an integer")

            # task_type
            stype = step.get("task_type")
            if not isinstance(stype, str) or not stype.strip():
                raise InvalidPlanError("Step task_type must be a non-empty string")
            if self._supported_task_types is not None and stype not in self._supported_task_types:
                raise InvalidPlanError(f"Unsupported step task_type: {stype}")

            # Dependencies must be list[str]
            deps = step.get("dependencies")
            if not isinstance(deps, list):
                raise InvalidPlanError("Step dependencies must be a list of step identifiers")
            for d in deps:
                if not isinstance(d, str) or not d.strip():
                    raise InvalidPlanError("Dependency identifiers must be non-empty strings")

            # Payload must be a JSON-safe dict and safe
            payload = step.get("payload")
            if not isinstance(payload, Mapping):
                raise UnsafePayloadError("Step payload must be a dictionary")
            # Reject forbidden keys anywhere in the payload (case-insensitive)
            if self._contains_forbidden_keys(payload, self._FORBIDDEN_PAYLOAD_KEYS):
                raise UnsafePayloadError("Payload contains forbidden command-related keys")
            # Ensure JSON-safe
            if not self._is_json_safe(payload):
                raise UnsafePayloadError("Payload must be JSON-safe")

        # Validate dependencies exist and are safe (self, unknown)
        step_id_set = set(step_ids)
        for step in steps:
            cur_id = step["step_id"]
            for dep in step["dependencies"]:  # type: ignore[index]
                if dep == cur_id:
                    raise SelfDependencyError(f"Step {cur_id} may not depend on itself")
                if dep not in step_id_set:
                    raise UnknownDependencyError(f"Step {cur_id} has unknown dependency: {dep}")

        # Detect cycles using DFS
        adjacency: Dict[str, List[str]] = {sid: list() for sid in step_ids}
        for step in steps:
            cur = step["step_id"]
            # Edge cur -> dep (for cycle detection on dependencies graph)
            for dep in step["dependencies"]:  # type: ignore[index]
                adjacency[cur].append(dep)
        if self._has_cycle(adjacency):
            raise CircularDependencyError("Plan contains circular dependencies")

        return dict(plan)

    def validate_and_build(
        self,
        plan: Mapping[str, Any],
        approved_request: Mapping[str, Any],
    ) -> Dict[str, Any]:
        """
        Coordinator-facing compatibility contract.

        Accepts the richer approved request produced by the
        PlannerQueueFlowCoordinator, extracts only the canonical
        fields owned by this builder, validates the plan, and
        returns the structured result expected by the coordinator.
        """

        if not isinstance(approved_request, Mapping):
            return {
                "ok": False,
                "plan_id": "",
                "plan_summary": "",
                "missions": [],
            }

        builder_request = {
            key: approved_request.get(key)
            for key in self._APPROVED_REQUEST_FIELDS
        }

        try:
            missions = self.build_missions(
                plan,
                builder_request,
            )
        except PlanValidationError:
            return {
                "ok": False,
                "plan_id": "",
                "plan_summary": "",
                "missions": [],
            }

        plan_id = (
            str(plan.get("plan_id") or "")
            if isinstance(plan, Mapping)
            else ""
        )

        plan_summary = (
            str(plan.get("summary") or "")
            if isinstance(plan, Mapping)
            else ""
        )

        return {
            "ok": True,
            "plan_id": plan_id,
            "plan_summary": plan_summary,
            "missions": missions,
        }

    def build_missions(self, plan: Mapping[str, Any], approved_request: Mapping[str, Any]) -> List[Dict[str, Any]]:
        # Validate inputs
        approved_request_v = self.validate_approved_request(approved_request)
        plan_v = self.validate_plan(plan, approved_request_v)

        steps: List[Mapping[str, Any]] = plan_v["steps"]  # type: ignore[assignment]

        # Generate mission IDs deterministically in validated step order
        step_to_mission: Dict[str, str] = {}
        generated_ids: List[str] = []
        for step in steps:
            sid = step["step_id"]  # type: ignore[index]
            mid = self._id_generator()
            if not isinstance(mid, str) or not mid:
                # Defensive check to keep determinism and safety
                raise InvalidPlanError("Identifier generator returned an invalid mission_id")
            if mid in generated_ids:
                # Enforce uniqueness for generated identifiers
                raise InvalidPlanError("Identifier generator produced duplicate mission_id")
            generated_ids.append(mid)
            step_to_mission[sid] = mid

        now = self._clock()
        missions: List[Dict[str, Any]] = []
        # Build mission objects in validated order (ordering is applied later)
        for idx, step in enumerate(steps):
            sid: str = step["step_id"]  # type: ignore[index]
            deps: List[str] = list(step["dependencies"])  # type: ignore[assignment]
            # Convert dependencies to mission IDs deterministically
            dep_missions = [step_to_mission[d] for d in deps]
            dep_missions.sort()  # Lexicographic order per contract

            payload_sanitized = self._sanitize_and_redact(step["payload"])  # type: ignore[index]

            mission: Dict[str, Any] = {
                "mission_id": step_to_mission[sid],
                "project_id": approved_request_v["project_id"],
                "request_id": approved_request_v["request_id"],
                "conversation_id": approved_request_v["conversation_id"],
                "plan_id": plan_v["plan_id"],
                "step_id": sid,
                "title": step["title"],
                "description": step["description"],
                "task_type": step["task_type"],
                "provider_id": approved_request_v["provider_id"],
                "model_id": approved_request_v["model_id"],
                "dependencies": dep_missions,
                "priority": step["priority"],
                "payload": payload_sanitized,
                "status": "pending",
                "created_at": now,
            }
            missions.append(mission)

        # Final deterministic topological ordering
        ordered = self.order_missions(missions)
        return ordered

    def order_missions(self, missions: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        # Build lookup and indegrees from mission dependencies (already mission_ids)
        id_to_mission: Dict[str, Dict[str, Any]] = {}
        indegree: Dict[str, int] = {}
        dependants: Dict[str, List[str]] = {}
        meta: Dict[str, _MissionMeta] = {}
        for idx, m in enumerate(missions):
            mid = m["mission_id"]  # type: ignore[index]
            id_to_mission[mid] = dict(m)  # Copy to ensure output is detached
            indegree[mid] = len(m.get("dependencies", []))  # type: ignore[arg-type]
            for d in m.get("dependencies", []):  # type: ignore[assignment]
                dependants.setdefault(d, []).append(mid)
            meta[mid] = _MissionMeta(
                mission_id=mid,
                step_id=m["step_id"],  # type: ignore[index]
                priority=m["priority"],  # type: ignore[index]
                original_index=idx,
            )

        # Initialize ready set
        ready: List[str] = [mid for mid, deg in indegree.items() if deg == 0]
        # Deterministic ordering function for ready set: (priority asc, step_id asc, original_index asc)
        def sort_ready(ids: List[str]) -> None:
            ids.sort(key=lambda x: (meta[x].priority, meta[x].step_id, meta[x].original_index))

        sort_ready(ready)

        ordered_ids: List[str] = []
        while ready:
            current = ready.pop(0)  # pop smallest by ordering
            ordered_ids.append(current)
            for dep in dependants.get(current, []):
                indegree[dep] -= 1
                if indegree[dep] == 0:
                    ready.append(dep)
            # Re-sort after potential new additions
            sort_ready(ready)

        if len(ordered_ids) != len(missions):
            # This should not occur after validation, but keep a guard
            raise CircularDependencyError("Cycle detected during ordering")

        # Return missions in final order, preserving converted dependencies
        return [id_to_mission[mid] for mid in ordered_ids]

    def status(self) -> Dict[str, Any]:
        return {
            "component": "PlanValidatorMissionBuilder",
            "version": 1,
            "priority_direction": "lower_integers_higher_priority",
            "supported_task_types": sorted(self._supported_task_types) if self._supported_task_types else "any_non_empty",
        }

    # Internal helpers
    @staticmethod
    def _default_id_generator() -> str:
        # Default non-deterministic; tests should inject a deterministic generator.
        # Uses UTC timestamp with microseconds to reduce collision risk.
        now = datetime.now(timezone.utc)
        return f"m{int(now.timestamp() * 1_000_000)}"

    @staticmethod
    def _default_clock() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _ensure_non_empty_identifier(value: Any, *, error_cls: type[Exception], field_name: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise error_cls(f"{field_name} must be a non-empty string")

    @classmethod
    def _contains_forbidden_keys(cls, payload: Mapping[str, Any], forbidden: Set[str]) -> bool:
        forbidden_lower = {k.lower() for k in forbidden}
        stack: List[Any] = [payload]
        while stack:
            cur = stack.pop()
            if isinstance(cur, Mapping):
                for k, v in cur.items():
                    if isinstance(k, str) and k.lower() in forbidden_lower:
                        return True
                    if isinstance(v, (Mapping, list)):
                        stack.append(v)
            elif isinstance(cur, list):
                for v in cur:
                    if isinstance(v, (Mapping, list)):
                        stack.append(v)
        return False

    @classmethod
    def _is_json_safe(cls, value: Any) -> bool:
        # JSON-safe types: dict(str->json), list, str, int, float, bool, None
        def _safe(v: Any) -> bool:
            if v is None:
                return True
            if isinstance(v, (str, int, float, bool)):
                return True
            if isinstance(v, list):
                return all(_safe(x) for x in v)
            if isinstance(v, Mapping):
                # Keys must be strings
                for k, item in v.items():
                    if not isinstance(k, str):
                        return False
                    if not _safe(item):
                        return False
                return True
            return False
        return _safe(value)

    @classmethod
    def _sanitize_and_redact(cls, payload: Mapping[str, Any]) -> Dict[str, Any]:
        # Do not mutate input. Recursively redact sensitive keys case-insensitively.
        sensitive_lower = {k.lower() for k in cls._SENSITIVE_KEYS}

        def _redact(obj: Any) -> Any:
            if isinstance(obj, Mapping):
                new_dict: Dict[str, Any] = {}
                for k, v in obj.items():
                    if isinstance(k, str) and k.lower() in sensitive_lower:
                        new_dict[k] = "[redacted]"
                    else:
                        new_dict[k] = _redact(v)
                return new_dict
            if isinstance(obj, list):
                return [_redact(x) for x in obj]
            # Scalars unchanged
            return obj

        return _redact(payload)

    @staticmethod
    def _has_cycle(graph: Mapping[str, List[str]]) -> bool:
        # DFS cycle detection on directed graph where edges are node -> dependencies
        visited: Set[str] = set()
        in_stack: Set[str] = set()

        def dfs(node: str) -> bool:
            if node in in_stack:
                return True
            if node in visited:
                return False
            visited.add(node)
            in_stack.add(node)
            for nb in graph.get(node, []):
                if dfs(nb):
                    return True
            in_stack.remove(node)
            return False

        for n in graph.keys():
            if n not in visited:
                if dfs(n):
                    return True
        return False
