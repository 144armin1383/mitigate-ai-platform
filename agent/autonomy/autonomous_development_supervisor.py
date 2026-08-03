from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from threading import RLock
from time import monotonic
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Protocol, Sequence, Tuple, Union, runtime_checkable
import json
import re
import uuid
from datetime import datetime, timezone, timedelta

# ===========================
# Public Types and Interfaces
# ===========================


class DevelopmentRunStatus(str, Enum):
    CREATED = "created"
    VALIDATING = "validating"
    PLANNING = "planning"
    AWAITING_APPROVAL = "awaiting_approval"
    PREPARING_BRANCH = "preparing_branch"
    GENERATING_MISSIONS = "generating_missions"
    EXECUTING = "executing"
    VALIDATING_RESULTS = "validating_results"
    RETRYING = "retrying"
    READY_FOR_MERGE = "ready_for_merge"
    MERGING = "merging"
    READY_FOR_DEPLOYMENT = "ready_for_deployment"
    DEPLOYING = "deploying"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ApprovalDecisionType(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    APPROVED_WITH_CONSTRAINTS = "approved_with_constraints"


SafeFailureCode = str  # Enumerated codes enforced by usage locations


@dataclass(frozen=True, slots=True)
class ApprovalDecision:
    decision_id: str
    run_id: str
    approver_id: str
    decision: ApprovalDecisionType
    constraints: Mapping[str, Any]
    timestamp: datetime
    reason_code: Optional[str] = None


@dataclass(frozen=True, slots=True)
class DevelopmentRequest:
    request_id: str
    project_id: str
    user_id: str
    title: str
    objective: str
    requirements: Sequence[str] = field(default_factory=tuple)
    constraints: Sequence[str] = field(default_factory=tuple)
    allowed_paths: Sequence[str] = field(default_factory=tuple)
    denied_paths: Sequence[str] = field(default_factory=tuple)
    requested_branch_name: Optional[str] = None
    requested_base_branch: Optional[str] = None
    requested_risk_level: Optional[RiskLevel] = None
    auto_merge_requested: bool = False
    auto_deploy_requested: bool = False
    max_cost: Optional[float] = None
    deadline: Optional[datetime] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_dict(data: Mapping[str, Any]) -> "DevelopmentRequest":
        # Strict field validation: reject unknown fields
        valid_fields = {
            "request_id",
            "project_id",
            "user_id",
            "title",
            "objective",
            "requirements",
            "constraints",
            "allowed_paths",
            "denied_paths",
            "requested_branch_name",
            "requested_base_branch",
            "requested_risk_level",
            "auto_merge_requested",
            "auto_deploy_requested",
            "max_cost",
            "deadline",
            "metadata",
        }
        unknown = set(data.keys()) - valid_fields
        if unknown:
            raise ValueError(f"invalid_development_request: unknown_fields={sorted(unknown)}")
        # Coerce requested_risk_level if provided
        rrl = data.get("requested_risk_level")
        if isinstance(rrl, str):
            try:
                data = dict(data)
                data["requested_risk_level"] = RiskLevel(rrl)
            except Exception as exc:  # noqa: BLE001 - precise error text is not emitted
                raise ValueError("invalid_development_request: invalid requested_risk_level") from exc
        # Coerce sequences
        def _seq(name: str) -> Sequence[str]:
            v = data.get(name)
            if v is None:
                return tuple()
            if isinstance(v, (list, tuple)):
                return tuple(str(x) for x in v)
            raise ValueError(f"invalid_development_request: field {name} must be a sequence")

        requirements = _seq("requirements")
        constraints = _seq("constraints")
        allowed_paths = _seq("allowed_paths")
        denied_paths = _seq("denied_paths")

        deadline = data.get("deadline")
        if isinstance(deadline, str):
            try:
                deadline = datetime.fromisoformat(deadline)
            except Exception as exc:  # noqa: BLE001
                raise ValueError("invalid_development_request: invalid deadline") from exc

        metadata = data.get("metadata") or {}
        if not isinstance(metadata, Mapping):
            raise ValueError("invalid_development_request: metadata must be a mapping")

        return DevelopmentRequest(
            request_id=str(data.get("request_id", "")),
            project_id=str(data.get("project_id", "")),
            user_id=str(data.get("user_id", "")),
            title=str(data.get("title", "")),
            objective=str(data.get("objective", "")),
            requirements=requirements,
            constraints=constraints,
            allowed_paths=allowed_paths,
            denied_paths=denied_paths,
            requested_branch_name=(str(data["requested_branch_name"]) if data.get("requested_branch_name") is not None else None),
            requested_base_branch=(str(data["requested_base_branch"]) if data.get("requested_base_branch") is not None else None),
            requested_risk_level=data.get("requested_risk_level"),
            auto_merge_requested=bool(data.get("auto_merge_requested", False)),
            auto_deploy_requested=bool(data.get("auto_deploy_requested", False)),
            max_cost=(float(data["max_cost"]) if data.get("max_cost") is not None else None),
            deadline=deadline,
            metadata=dict(metadata),
        )


@dataclass(frozen=True, slots=True)
class AutonomousDevelopmentConfig:
    default_base_branch: str = "main"
    maximum_plan_steps: int = 50
    maximum_missions: int = 50
    maximum_retry_attempts_per_mission: int = 3
    maximum_total_retry_attempts: int = 10
    maximum_parallel_missions: int = 1
    maximum_run_seconds: int = 7200
    maximum_cost: Optional[float] = None
    auto_merge_low_risk: bool = False
    auto_merge_medium_risk: bool = False
    auto_deploy_enabled: bool = False

    require_approval_for_database_changes: bool = True
    require_approval_for_secret_changes: bool = True
    require_approval_for_dependency_changes: bool = True
    require_approval_for_dns_changes: bool = True
    require_approval_for_security_policy_changes: bool = True
    require_approval_for_destructive_changes: bool = True
    require_approval_for_production_deployment: bool = True

    stop_on_security_failure: bool = True
    stop_on_compliance_failure: bool = True
    stop_on_budget_failure: bool = True

    final_report_required: bool = True


@dataclass(slots=True)
class DevelopmentRunResult:
    run_id: str
    request_id: str
    project_id: str
    title: str
    objective: str
    status: DevelopmentRunStatus
    risk_level: RiskLevel
    approvals: List[ApprovalDecision] = field(default_factory=list)
    plan_summary: Mapping[str, Any] = field(default_factory=dict)
    mission_summary: Mapping[str, Any] = field(default_factory=dict)
    completed_missions: Sequence[str] = field(default_factory=tuple)
    failed_missions: Sequence[str] = field(default_factory=tuple)
    blocked_missions: Sequence[str] = field(default_factory=tuple)
    changed_files: Sequence[str] = field(default_factory=tuple)
    tests_executed: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    tests_skipped: int = 0
    retries: int = 0
    provider_usage: Mapping[str, Any] = field(default_factory=dict)
    estimated_cost: float = 0.0
    branch: Optional[str] = None
    commits: Sequence[str] = field(default_factory=tuple)
    merge_status: Optional[str] = None
    deployment_status: Optional[str] = None
    warnings: Sequence[str] = field(default_factory=tuple)
    safe_failure_codes: Sequence[SafeFailureCode] = field(default_factory=tuple)
    next_required_action: Optional[str] = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None


# ======================
# Dependency Protocols
# ======================


@runtime_checkable
class Clock(Protocol):
    def utcnow(self) -> datetime: ...  # noqa: E701


@runtime_checkable
class IdentifierGenerator(Protocol):
    def new_run_id(self, project_id: str, request_id: str) -> str: ...  # noqa: E701


@runtime_checkable
class EventSink(Protocol):
    def publish(self, event: Mapping[str, Any]) -> None: ...  # noqa: E701


@runtime_checkable
class ProjectRegistry(Protocol):
    def resolve(self, project_id: str) -> Mapping[str, Any]: ...  # noqa: E701


@runtime_checkable
class Planner(Protocol):
    def plan(self, planner_input: Mapping[str, Any]) -> Mapping[str, Any]: ...  # returns a plan mapping


@runtime_checkable
class PlanValidator(Protocol):
    def validate(self, plan: Mapping[str, Any]) -> Mapping[str, Any]: ...  # returns validation result


@runtime_checkable
class MissionBuilder(Protocol):
    def build(self, plan: Mapping[str, Any]) -> Mapping[str, Any]: ...  # returns {missions: [...], dependencies: {}}


@runtime_checkable
class MissionExecutor(Protocol):
    def execute(self, mission: Mapping[str, Any], context: Mapping[str, Any]) -> Mapping[str, Any]: ...


@runtime_checkable
class ValidationEngine(Protocol):
    def validate_generated_files(self, run_context: Mapping[str, Any]) -> Mapping[str, Any]: ...

    def run_selected_tests(self, run_context: Mapping[str, Any]) -> Mapping[str, Any]: ...

    def run_full_repository_tests(self, run_context: Mapping[str, Any]) -> Mapping[str, Any]: ...


@runtime_checkable
class RetryClassifier(Protocol):
    def classify(self, failure: Mapping[str, Any]) -> Mapping[str, Any]: ...  # returns {retryable: bool}


@runtime_checkable
class GitWorkflow(Protocol):
    def verify_clean_repository(self, project_id: str) -> Mapping[str, Any]: ...

    def verify_base_branch(self, project_id: str, branch: str) -> Mapping[str, Any]: ...

    def fetch_status(self, project_id: str) -> Mapping[str, Any]: ...

    def create_development_branch(self, project_id: str, base_branch: str, new_branch: str) -> Mapping[str, Any]: ...

    def inspect_changed_files(self, project_id: str, branch: str) -> Mapping[str, Any]: ...

    def inspect_diff_summary(self, project_id: str, branch: str) -> Mapping[str, Any]: ...

    def commit_changes(self, project_id: str, branch: str, message: str) -> Mapping[str, Any]: ...

    def push_branch(self, project_id: str, branch: str) -> Mapping[str, Any]: ...

    def merge_branch(self, project_id: str, from_branch: str, to_branch: str) -> Mapping[str, Any]: ...

    def rollback_branch(self, project_id: str, branch: str) -> Mapping[str, Any]: ...


@runtime_checkable
class ApprovalStore(Protocol):
    def record(self, decision: ApprovalDecision) -> None: ...

    def list(self, run_id: str) -> Sequence[ApprovalDecision]: ...


@runtime_checkable
class RunStateStore(Protocol):
    def create_run(self, run_state: Mapping[str, Any]) -> bool: ...  # returns False if duplicate

    def get_run(self, run_id: str) -> Optional[Mapping[str, Any]]: ...

    def get_by_project_request(self, project_id: str, request_id: str) -> Optional[Mapping[str, Any]]: ...

    def update_run(self, run_id: str, updates: Mapping[str, Any]) -> None: ...

    def list_runs(self, project_id: Optional[str] = None) -> Sequence[Mapping[str, Any]]: ...


@runtime_checkable
class ProviderUsageLedger(Protocol):
    def record_usage(self, run_id: str, usage: Mapping[str, Any]) -> None: ...

    def summarize(self, run_id: str) -> Mapping[str, Any]: ...


@runtime_checkable
class ProviderRateLimiter(Protocol):
    def allow(self, run_id: str, category: str) -> bool: ...


@runtime_checkable
class ProviderBudgetLimitEvaluator(Protocol):
    def allow(self, run_id: str, proposed_cost: float, max_cost: Optional[float]) -> bool: ...


@runtime_checkable
class ReportWriter(Protocol):
    def write(self, report: Mapping[str, Any]) -> None: ...


@runtime_checkable
class RiskEvaluator(Protocol):
    def assess(self, request: Mapping[str, Any], plan: Optional[Mapping[str, Any]]) -> Mapping[str, Any]: ...  # returns {level: str, reasons: [...]}


@runtime_checkable
class CostEvaluator(Protocol):
    def estimate_plan_cost(self, plan: Mapping[str, Any]) -> float: ...


# ==============================
# Internal Helper Data and Types
# ==============================


@dataclass(slots=True)
class _RunInternalState:
    run_id: str
    project_id: str
    request_id: str
    status: DevelopmentRunStatus
    risk_level: RiskLevel = RiskLevel.LOW
    approvals: List[ApprovalDecision] = field(default_factory=list)
    plan: Optional[Mapping[str, Any]] = None
    missions: Sequence[Mapping[str, Any]] = field(default_factory=tuple)
    mission_dependencies: Mapping[str, Sequence[str]] = field(default_factory=dict)
    completed_missions: List[str] = field(default_factory=list)
    failed_missions: List[str] = field(default_factory=list)
    blocked_missions: List[str] = field(default_factory=list)
    changed_files: List[str] = field(default_factory=list)
    tests_executed: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    tests_skipped: int = 0
    retries: int = 0
    provider_usage: Dict[str, Any] = field(default_factory=dict)
    estimated_cost: float = 0.0
    branch: Optional[str] = None
    commits: List[str] = field(default_factory=list)
    merge_status: Optional[str] = None
    deployment_status: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    safe_failure_codes: List[SafeFailureCode] = field(default_factory=list)
    next_required_action: Optional[str] = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    cancelled: bool = False


@dataclass(slots=True)
class _SupervisorDependencies:
    clock: Clock
    id_gen: IdentifierGenerator
    event_sink: EventSink
    project_registry: ProjectRegistry
    planner: Planner
    plan_validator: PlanValidator
    mission_builder: MissionBuilder
    mission_executor: MissionExecutor
    validation_engine: ValidationEngine
    retry_classifier: RetryClassifier
    git_workflow: GitWorkflow
    approval_store: ApprovalStore
    run_state_store: RunStateStore
    usage_ledger: ProviderUsageLedger
    rate_limiter: ProviderRateLimiter
    budget_evaluator: ProviderBudgetLimitEvaluator
    report_writer: ReportWriter
    risk_evaluator: Optional[RiskEvaluator] = None
    cost_evaluator: Optional[CostEvaluator] = None


# ==============================
# Utility Functions
# ==============================


_SENSITIVE_KEY_RE = re.compile(
    r"(secret|token|password|credential|authorization|cookie|session|api[_-]?key)",
    re.IGNORECASE,
)


def _redact_metadata(meta: Mapping[str, Any]) -> Mapping[str, Any]:
    redacted: Dict[str, Any] = {}
    for k, v in meta.items():
        if _SENSITIVE_KEY_RE.search(str(k)):
            redacted[k] = "[REDACTED]"
        else:
            if isinstance(v, (dict, Mapping)):
                redacted[k] = _redact_metadata(v)  # type: ignore[arg-type]
            elif isinstance(v, (list, tuple)):
                redacted[k] = ["[REDACTED]" if _SENSITIVE_KEY_RE.search(str(x)) else x for x in v]
            else:
                sval = str(v)
                if _SENSITIVE_KEY_RE.search(sval):
                    redacted[k] = "[REDACTED]"
                else:
                    redacted[k] = v
    return redacted


def _normalize_branch_name(project_id: str, request_id: str, requested: Optional[str]) -> str:
    base = requested or f"dev-{project_id}-{request_id}"
    base = base.lower()
    base = re.sub(r"[^a-z0-9._/-]+", "-", base)
    base = base.replace("..", ".")
    base = base.strip("-/.")
    if not base:
        base = f"dev-{project_id}-{request_id}"
    # Ensure deterministic short length
    if len(base) > 120:
        h = uuid.uuid5(uuid.NAMESPACE_URL, base).hex[:8]
        base = base[:100].rstrip("-/.") + f"-{h}"
    return base


def _validate_paths(paths: Sequence[str]) -> Tuple[bool, Optional[str]]:
    for p in paths:
        if not isinstance(p, str) or not p:
            return False, "unsafe_path"
        if "\x00" in p:
            return False, "unsafe_path"
        if p.startswith("/"):
            return False, "unsafe_path"
        if "://" in p:
            return False, "unsafe_path"
        parts = p.split("/")
        if any(part == ".." for part in parts):
            return False, "unsafe_path"
    return True, None


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ==============================
# AutonomousDevelopmentSupervisor
# ==============================


class AutonomousDevelopmentSupervisor:
    def __init__(self, config: AutonomousDevelopmentConfig, dependencies: _SupervisorDependencies) -> None:
        self._config = config
        self._dep = dependencies
        self._global_lock = RLock()
        self._run_locks: Dict[str, RLock] = {}
        self._events_buffer: List[Mapping[str, Any]] = []
        self._events_buffer_limit = 1000

    # ------------- Public API -------------

    def submit(self, request: Union[DevelopmentRequest, Mapping[str, Any]]) -> str:
        req = self._coerce_request(request)
        self._validate_request_basic(req)
        run_id = self._ensure_run_created(req)
        self._emit_event(
            "development_run_created",
            run_id=run_id,
            project_id=req.project_id,
            request_id=req.request_id,
            state=DevelopmentRunStatus.CREATED.value,
        )
        return run_id

    def run(self, request: Union[DevelopmentRequest, Mapping[str, Any]]) -> DevelopmentRunResult:
        req = self._coerce_request(request)
        self._validate_request_basic(req)
        run_id = self._ensure_run_created(req)

        start_monotonic = monotonic()

        # Execute synchronously through stages
        self._transition(run_id, DevelopmentRunStatus.CREATED, DevelopmentRunStatus.VALIDATING)
        self._emit_event("request_validating", run_id=run_id, project_id=req.project_id, request_id=req.request_id)
        self._validate_request_paths(req)
        project_cfg = self._resolve_project(req.project_id)
        self._emit_event("request_validated", run_id=run_id)

        self._transition(run_id, DevelopmentRunStatus.VALIDATING, DevelopmentRunStatus.PLANNING)
        self._emit_event("planning_started", run_id=run_id)

        planner_input = self._build_planner_input(req, project_cfg)
        plan = self._call_planner(planner_input, run_id)
        self._ensure_within_time(start_monotonic, run_id)

        validation_result = self._validate_plan(plan, run_id)
        self._ensure_within_time(start_monotonic, run_id)

        missions, deps = self._generate_missions(plan, run_id)
        self._ensure_within_time(start_monotonic, run_id)

        # Risk assessment
        assessed_risk, reasons = self._assess_risk(req, plan)
        self._set_risk(run_id, assessed_risk)
        self._emit_event("risk_assessed", run_id=run_id, risk_level=assessed_risk.value)

        # Determine required approvals
        required_categories = self._determine_required_approvals(req, plan, assessed_risk, reasons)
        if required_categories:
            self._transition(run_id, DevelopmentRunStatus.PLANNING, DevelopmentRunStatus.AWAITING_APPROVAL)
            self._emit_event(
                "approval_required",
                run_id=run_id,
                risk_level=assessed_risk.value,
                categories=sorted(required_categories),
            )
            return self._result_for(run_id, req, plan, missions, deps, status=DevelopmentRunStatus.AWAITING_APPROVAL)

        # Prepare branch
        self._transition(run_id, DevelopmentRunStatus.PLANNING, DevelopmentRunStatus.PREPARING_BRANCH)
        branch = self._prepare_branch(req)
        self._set_branch(run_id, branch)
        self._emit_event("branch_prepared", run_id=run_id, branch=branch)

        # Generate missions recorded
        self._transition(run_id, DevelopmentRunStatus.PREPARING_BRANCH, DevelopmentRunStatus.GENERATING_MISSIONS)
        self._record_missions(run_id, missions, deps)
        self._emit_event("mission_generated", run_id=run_id, mission_count=len(missions))

        # Execute missions
        self._transition(run_id, DevelopmentRunStatus.GENERATING_MISSIONS, DevelopmentRunStatus.EXECUTING)
        self._execute_missions(run_id, req, branch, missions, deps, start_monotonic)

        # Validate results
        self._transition(run_id, DevelopmentRunStatus.EXECUTING, DevelopmentRunStatus.VALIDATING_RESULTS)
        validation_passed = self._final_validation(run_id, req, branch)
        if not validation_passed:
            self._transition(run_id, DevelopmentRunStatus.VALIDATING_RESULTS, DevelopmentRunStatus.FAILED)
            self._emit_event("validation_completed", run_id=run_id, success=False)
            return self._result_for(run_id, req, plan, missions, deps, status=DevelopmentRunStatus.FAILED)
        self._emit_event("validation_completed", run_id=run_id, success=True)

        # Merge policy
        merge_ready = self._determine_merge_readiness(run_id, req, assessed_risk)
        if not merge_ready:
            self._transition(run_id, DevelopmentRunStatus.VALIDATING_RESULTS, DevelopmentRunStatus.READY_FOR_MERGE)
            self._emit_event("merge_ready", run_id=run_id)
            # Deployment eligibility marking only
            if self._deployment_allowed(assessed_risk):
                self._transition(run_id, DevelopmentRunStatus.READY_FOR_MERGE, DevelopmentRunStatus.READY_FOR_DEPLOYMENT)
                self._emit_event("deployment_ready", run_id=run_id)
                final_status = DevelopmentRunStatus.READY_FOR_DEPLOYMENT
            else:
                final_status = DevelopmentRunStatus.READY_FOR_MERGE
            return self._result_for(run_id, req, plan, missions, deps, status=final_status)

        # Attempt auto-merge when explicitly allowed by config and policy
        self._transition(run_id, DevelopmentRunStatus.VALIDATING_RESULTS, DevelopmentRunStatus.MERGING)
        merged = self._attempt_merge(run_id, req, branch, assessed_risk)
        if not merged:
            self._transition(run_id, DevelopmentRunStatus.MERGING, DevelopmentRunStatus.READY_FOR_MERGE)
            self._emit_event("merge_ready", run_id=run_id)
            final_status = DevelopmentRunStatus.READY_FOR_MERGE
        else:
            self._emit_event("merge_completed", run_id=run_id)
            # Mark deployment readiness only; no deployment in this mission
            if self._deployment_allowed(assessed_risk):
                self._transition(run_id, DevelopmentRunStatus.MERGING, DevelopmentRunStatus.READY_FOR_DEPLOYMENT)
                self._emit_event("deployment_ready", run_id=run_id)
                final_status = DevelopmentRunStatus.READY_FOR_DEPLOYMENT
            else:
                self._transition(run_id, DevelopmentRunStatus.MERGING, DevelopmentRunStatus.COMPLETED)
                self._emit_event("development_run_completed", run_id=run_id)
                final_status = DevelopmentRunStatus.COMPLETED

        return self._result_for(run_id, req, plan, missions, deps, status=final_status)

    def resume(self, run_id: str) -> DevelopmentRunResult:
        run_state = self._get_run_state(run_id)
        req = self._get_request_from_state(run_state)
        status = DevelopmentRunStatus(run_state["status"])  # type: ignore[arg-type]
        if status not in {DevelopmentRunStatus.AWAITING_APPROVAL, DevelopmentRunStatus.BLOCKED, DevelopmentRunStatus.RETRYING, DevelopmentRunStatus.READY_FOR_MERGE, DevelopmentRunStatus.READY_FOR_DEPLOYMENT}:
            # Idempotent no-op
            return self._result_for(run_id, req, None, tuple(), {}, status=status)
        # Continue execution consistent with run()
        # Here we only transition from approval-waiting if approvals exist
        approvals = self._dep.approval_store.list(run_id)
        if status == DevelopmentRunStatus.AWAITING_APPROVAL:
            if not approvals or all(a.decision == ApprovalDecisionType.REJECTED for a in approvals):
                return self._result_for(run_id, req, None, tuple(), {}, status=status)
            # Proceed to branch prep and beyond
            branch = self._prepare_branch(req)
            self._set_branch(run_id, branch)
            self._emit_event("branch_prepared", run_id=run_id, branch=branch)
            # Missions and plan might be persisted; we attempt to reconstruct minimal state
            plan = run_state.get("plan")  # type: ignore[assignment]
            missions = tuple(run_state.get("missions") or tuple())  # type: ignore[assignment]
            deps = dict(run_state.get("mission_dependencies") or {})  # type: ignore[assignment]
            self._transition(run_id, DevelopmentRunStatus.AWAITING_APPROVAL, DevelopmentRunStatus.GENERATING_MISSIONS)
            self._record_missions(run_id, missions, deps)
            self._transition(run_id, DevelopmentRunStatus.GENERATING_MISSIONS, DevelopmentRunStatus.EXECUTING)
            self._execute_missions(run_id, req, branch, missions, deps, monotonic())
            self._transition(run_id, DevelopmentRunStatus.EXECUTING, DevelopmentRunStatus.VALIDATING_RESULTS)
            passed = self._final_validation(run_id, req, branch)
            if not passed:
                self._transition(run_id, DevelopmentRunStatus.VALIDATING_RESULTS, DevelopmentRunStatus.FAILED)
                return self._result_for(run_id, req, plan, missions, deps, status=DevelopmentRunStatus.FAILED)
            assessed_risk = RiskLevel(run_state.get("risk_level", RiskLevel.LOW.value))  # type: ignore[arg-type]
            if not self._determine_merge_readiness(run_id, req, assessed_risk):
                self._transition(run_id, DevelopmentRunStatus.VALIDATING_RESULTS, DevelopmentRunStatus.READY_FOR_MERGE)
                return self._result_for(run_id, req, plan, missions, deps, status=DevelopmentRunStatus.READY_FOR_MERGE)
            self._transition(run_id, DevelopmentRunStatus.VALIDATING_RESULTS, DevelopmentRunStatus.MERGING)
            merged = self._attempt_merge(run_id, req, branch, assessed_risk)
            if merged:
                if self._deployment_allowed(assessed_risk):
                    self._transition(run_id, DevelopmentRunStatus.MERGING, DevelopmentRunStatus.READY_FOR_DEPLOYMENT)
                    return self._result_for(run_id, req, plan, missions, deps, status=DevelopmentRunStatus.READY_FOR_DEPLOYMENT)
                self._transition(run_id, DevelopmentRunStatus.MERGING, DevelopmentRunStatus.COMPLETED)
                return self._result_for(run_id, req, plan, missions, deps, status=DevelopmentRunStatus.COMPLETED)
            self._transition(run_id, DevelopmentRunStatus.MERGING, DevelopmentRunStatus.READY_FOR_MERGE)
            return self._result_for(run_id, req, plan, missions, deps, status=DevelopmentRunStatus.READY_FOR_MERGE)
        # For other resumable states, return current snapshot
        return self._result_for(run_id, req, run_state.get("plan"), tuple(run_state.get("missions") or tuple()), dict(run_state.get("mission_dependencies") or {}), status=status)

    def cancel(self, run_id: str) -> None:
        with self._lock_for(run_id):
            rs = self._get_run_state(run_id)
            if rs.get("status") in {DevelopmentRunStatus.COMPLETED.value, DevelopmentRunStatus.CANCELLED.value, DevelopmentRunStatus.FAILED.value}:  # type: ignore[index]
                return
            updates = {"cancelled": True, "status": DevelopmentRunStatus.CANCELLED.value, "completed_at": self._dep.clock.utcnow().isoformat()}
            self._dep.run_state_store.update_run(run_id, updates)
        self._emit_event("development_run_cancelled", run_id=run_id)

    def approve(self, run_id: str, decision: ApprovalDecision) -> None:
        # Record approval without bypassing validation
        if decision.run_id != run_id:
            raise ValueError("invalid_approval: mismatched run_id")
        if decision.decision == ApprovalDecisionType.REJECTED and not decision.reason_code:
            raise ValueError("invalid_approval: rejection must include reason_code")
        self._dep.approval_store.record(decision)
        self._emit_event("approval_received" if decision.decision != ApprovalDecisionType.REJECTED else "approval_rejected", run_id=run_id, decision=decision.decision.value)

    def reject(self, run_id: str, reason_code: str) -> None:
        # Convenience rejection
        dec = ApprovalDecision(
            decision_id=str(uuid.uuid4()),
            run_id=run_id,
            approver_id="system",
            decision=ApprovalDecisionType.REJECTED,
            constraints={},
            timestamp=self._dep.clock.utcnow(),
            reason_code=reason_code,
        )
        self.approve(run_id, dec)
        with self._lock_for(run_id):
            self._dep.run_state_store.update_run(run_id, {"status": DevelopmentRunStatus.BLOCKED.value, "next_required_action": "approval_rejected"})
        self._emit_event("development_run_blocked", run_id=run_id, reason_code=reason_code)

    def status(self, run_id: Optional[str] = None) -> Mapping[str, Any]:
        if run_id:
            rs = self._get_run_state(run_id)
            return self._public_run_snapshot(rs)
        # Aggregate
        runs = self._dep.run_state_store.list_runs()
        counts: Dict[str, int] = {}
        for r in runs:
            s = str(r.get("status", DevelopmentRunStatus.CREATED.value))
            counts[s] = counts.get(s, 0) + 1
        return {"counts": counts, "total": len(runs)}

    def latest_events(self, limit: int = 100) -> Sequence[Mapping[str, Any]]:
        if limit <= 0:
            return tuple()
        with self._global_lock:
            return tuple(self._events_buffer[-min(limit, len(self._events_buffer)):])

    def final_report(self, run_id: str) -> Mapping[str, Any]:
        rs = self._get_run_state(run_id)
        report = self._build_final_report(rs)
        # Persist via report writer if required
        if self._config.final_report_required:
            self._dep.report_writer.write(report)
        return report

    def close(self) -> None:
        # Idempotent; no external resources to release beyond what DI provides
        return None

    # Context manager support
    def __enter__(self) -> "AutonomousDevelopmentSupervisor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        self.close()

    # ------------- Internal Helpers -------------

    def _coerce_request(self, request: Union[DevelopmentRequest, Mapping[str, Any]]) -> DevelopmentRequest:
        if isinstance(request, DevelopmentRequest):
            return request
        return DevelopmentRequest.from_dict(request)

    def _validate_request_basic(self, req: DevelopmentRequest) -> None:
        if not req.project_id or not req.request_id:
            raise ValueError("invalid_development_request: missing project_id or request_id")
        if not req.objective or not req.title:
            raise ValueError("invalid_development_request: objective/title required")
        # Deadline in the past check
        if req.deadline and req.deadline.tzinfo is None:
            raise ValueError("invalid_development_request: deadline must be timezone-aware")

    def _validate_request_paths(self, req: DevelopmentRequest) -> None:
        ok, code = _validate_paths(req.allowed_paths)
        if not ok:
            self._safe_fail(req.project_id, req.request_id, "unsafe_path", DevelopmentRunStatus.FAILED)
            raise ValueError(code or "unsafe_path")
        ok, code = _validate_paths(req.denied_paths)
        if not ok:
            self._safe_fail(req.project_id, req.request_id, "unsafe_path", DevelopmentRunStatus.FAILED)
            raise ValueError(code or "unsafe_path")

    def _ensure_run_created(self, req: DevelopmentRequest) -> str:
        # Enforce single active run per project/request
        existing = self._dep.run_state_store.get_by_project_request(req.project_id, req.request_id)
        if existing is not None:
            return str(existing.get("run_id"))
        run_id = self._dep.id_gen.new_run_id(req.project_id, req.request_id)
        state: Dict[str, Any] = {
            "run_id": run_id,
            "project_id": req.project_id,
            "request_id": req.request_id,
            "status": DevelopmentRunStatus.CREATED.value,
            "risk_level": RiskLevel.LOW.value,
            "approvals": [],
            "plan": None,
            "missions": [],
            "mission_dependencies": {},
            "completed_missions": [],
            "failed_missions": [],
            "blocked_missions": [],
            "changed_files": [],
            "tests_executed": 0,
            "tests_passed": 0,
            "tests_failed": 0,
            "tests_skipped": 0,
            "retries": 0,
            "provider_usage": {},
            "estimated_cost": 0.0,
            "branch": None,
            "commits": [],
            "merge_status": None,
            "deployment_status": None,
            "warnings": [],
            "safe_failure_codes": [],
            "next_required_action": None,
            "started_at": self._dep.clock.utcnow().isoformat(),
            "completed_at": None,
            "cancelled": False,
            # Persist only redacted metadata
            "request_snapshot": {
                "title": req.title,
                "objective": req.objective,
                "requirements": list(req.requirements),
                "constraints": list(req.constraints),
                "allowed_paths": list(req.allowed_paths),
                "denied_paths": list(req.denied_paths),
                "requested_branch_name": req.requested_branch_name,
                "requested_base_branch": req.requested_base_branch,
                "requested_risk_level": req.requested_risk_level.value if req.requested_risk_level else None,
                "auto_merge_requested": req.auto_merge_requested,
                "auto_deploy_requested": req.auto_deploy_requested,
                "max_cost": req.max_cost,
                "deadline": req.deadline.isoformat() if req.deadline else None,
                "metadata": _redact_metadata(req.metadata),
            },
        }
        created = self._dep.run_state_store.create_run(state)
        if not created:
            # Another concurrent submit created it.
            existing2 = self._dep.run_state_store.get_by_project_request(req.project_id, req.request_id)
            if existing2 is None:
                raise RuntimeError("invalid_run_state_store: duplicate create denied without existing run")
            return str(existing2.get("run_id"))
        # Initialize per-run lock after create
        with self._global_lock:
            if run_id not in self._run_locks:
                self._run_locks[run_id] = RLock()
        return run_id

    def _resolve_project(self, project_id: str) -> Mapping[str, Any]:
        cfg = self._dep.project_registry.resolve(project_id)
        if not isinstance(cfg, Mapping):
            raise RuntimeError("unknown_project")
        return cfg

    def _build_planner_input(self, req: DevelopmentRequest, project_cfg: Mapping[str, Any]) -> Mapping[str, Any]:
        # Deterministic planner input; exclude secrets and private values
        base_branch = req.requested_base_branch or self._config.default_base_branch
        return {
            "request_id": req.request_id,
            "project_id": req.project_id,
            "user_id": req.user_id,
            "title": req.title,
            "objective": req.objective,
            "requirements": list(req.requirements),
            "constraints": list(req.constraints),
            "allowed_paths": list(req.allowed_paths),
            "denied_paths": list(req.denied_paths),
            "base_branch": base_branch,
            "requested_branch": _normalize_branch_name(req.project_id, req.request_id, req.requested_branch_name),
            "metadata": _redact_metadata(req.metadata),
            "config": {"maximum_plan_steps": self._config.maximum_plan_steps},
            "project": {k: v for k, v in project_cfg.items() if k not in ("secrets", "credentials", "tokens")},
        }

    def _call_planner(self, planner_input: Mapping[str, Any], run_id: str) -> Mapping[str, Any]:
        try:
            plan = self._dep.planner.plan(planner_input)
        except Exception:
            self._record_failure(run_id, "planning_failed")
            raise
        if not isinstance(plan, Mapping):
            self._record_failure(run_id, "planning_failed")
            raise RuntimeError("planning_failed")
        # Enforce maximum plan size
        steps = plan.get("steps")
        if not isinstance(steps, list) or len(steps) == 0:
            self._record_failure(run_id, "planning_failed")
            raise RuntimeError("planning_failed")
        if len(steps) > self._config.maximum_plan_steps:
            self._record_failure(run_id, "invalid_plan")
            raise RuntimeError("invalid_plan")
        self._emit_event("planning_completed", run_id=run_id, step_count=len(steps))
        return plan

    def _validate_plan(self, plan: Mapping[str, Any], run_id: str) -> Mapping[str, Any]:
        try:
            result = self._dep.plan_validator.validate(plan)
        except Exception:
            self._record_failure(run_id, "invalid_plan")
            raise
        if not isinstance(result, Mapping) or not result.get("valid", False):
            self._record_failure(run_id, "invalid_plan")
            raise RuntimeError("invalid_plan")
        # Additional safety: reject circular dependencies if provided
        deps = result.get("dependencies") or {}
        if isinstance(deps, Mapping):
            if self._has_cycle(deps):
                self._record_failure(run_id, "invalid_plan")
                raise RuntimeError("invalid_plan")
        return result

    @staticmethod
    def _has_cycle(graph: Mapping[str, Sequence[str]]) -> bool:
        temp: set[str] = set()
        perm: set[str] = set()

        def visit(n: str) -> bool:
            if n in perm:
                return False
            if n in temp:
                return True
            temp.add(n)
            for m in graph.get(n, ()):  # type: ignore[arg-type]
                if visit(m):
                    return True
            temp.remove(n)
            perm.add(n)
            return False

        return any(visit(node) for node in graph.keys())

    def _generate_missions(self, plan: Mapping[str, Any], run_id: str) -> Tuple[Sequence[Mapping[str, Any]], Mapping[str, Sequence[str]]]:
        try:
            built = self._dep.mission_builder.build(plan)
        except Exception:
            self._record_failure(run_id, "mission_generation_failed")
            raise
        if not isinstance(built, Mapping):
            self._record_failure(run_id, "mission_generation_failed")
            raise RuntimeError("mission_generation_failed")
        missions = built.get("missions")
        deps = built.get("dependencies") or {}
        if not isinstance(missions, list):
            self._record_failure(run_id, "mission_generation_failed")
            raise RuntimeError("mission_generation_failed")
        if len(missions) > self._config.maximum_missions:
            self._record_failure(run_id, "mission_generation_failed")
            raise RuntimeError("mission_generation_failed")
        # Check unique identifiers and deterministic ordering
        ids = [str(m.get("id")) for m in missions]
        if len(ids) != len(set(ids)):
            self._record_failure(run_id, "mission_generation_failed")
            raise RuntimeError("mission_generation_failed")
        if self._has_cycle(deps if isinstance(deps, Mapping) else {}):
            self._record_failure(run_id, "mission_generation_failed")
            raise RuntimeError("mission_generation_failed")
        self._emit_event("mission_generation_started", run_id=run_id, mission_count=len(missions))
        return missions, {str(k): tuple(v) for k, v in (deps.items() if isinstance(deps, Mapping) else {})}

    def _assess_risk(self, req: DevelopmentRequest, plan: Optional[Mapping[str, Any]]) -> Tuple[RiskLevel, Sequence[str]]:
        # Use injected evaluator if present
        if self._dep.risk_evaluator is not None:
            try:
                res = self._dep.risk_evaluator.assess(asdict(req), plan)
                level = RiskLevel(str(res.get("level", RiskLevel.LOW.value)))
                reasons = list(res.get("reasons") or [])
                # If user requested higher risk, raise
                if req.requested_risk_level and level.value < req.requested_risk_level.value:
                    level = req.requested_risk_level
                return level, reasons
            except Exception:
                # Fall back to heuristic
                pass
        # Deterministic heuristic based on content keywords
        text = " ".join([
            req.title,
            req.objective,
            " ".join(req.requirements),
            " ".join(req.constraints),
            json.dumps(_redact_metadata(req.metadata), sort_keys=True),
        ]).lower()
        keywords_critical = [
            "dns", "cloudflare", "secret rotation", "drop table", "production deletion", "force-push",
        ]
        keywords_high = [
            "database migration", "auth", "authentication", "authorization", "dependency", "infrastructure", "payment", "compliance", "deployment",
        ]
        keywords_medium = ["refactor", "api", "configuration", "config"]
        level = RiskLevel.LOW
        reasons: List[str] = []
        if any(k in text for k in keywords_critical):
            level = RiskLevel.CRITICAL
            reasons.append("critical_keywords")
        elif any(k in text for k in keywords_high):
            level = RiskLevel.HIGH
            reasons.append("high_keywords")
        elif any(k in text for k in keywords_medium):
            level = RiskLevel.MEDIUM
            reasons.append("medium_keywords")
        # User requested risk can increase but never reduce
        if req.requested_risk_level and req.requested_risk_level.value > level.value:
            level = req.requested_risk_level
            reasons.append("user_requested_increase")
        return level, reasons

    def _determine_required_approvals(
        self,
        req: DevelopmentRequest,
        plan: Mapping[str, Any],
        risk: RiskLevel,
        reasons: Sequence[str],
    ) -> Sequence[str]:
        required: List[str] = []
        # Determine categories from plan summary if available
        categories = set()
        if isinstance(plan, Mapping):
            cats = plan.get("categories")
            if isinstance(cats, list):
                categories.update(str(c) for c in cats)
        text = " ".join([
            req.title,
            req.objective,
            " ".join(req.requirements),
            " ".join(req.constraints),
        ]).lower()
        def need(flag: bool, cat: str, matchers: Iterable[str]) -> None:
            if not flag:
                return
            if cat in categories or any(m in text for m in matchers):
                required.append(cat)

        need(self._config.require_approval_for_database_changes, "database_changes", ["database", "migration", "sql", "schema"])
        need(self._config.require_approval_for_secret_changes, "secret_changes", ["secret", "credential", "password", "token"])
        need(self._config.require_approval_for_dependency_changes, "dependency_changes", ["dependency", "requirements.txt", "pip", "poetry"])  # no actual file IO
        need(self._config.require_approval_for_dns_changes, "dns_changes", ["dns", "cloudflare"])
        need(self._config.require_approval_for_security_policy_changes, "security_policy_changes", ["security", "policy", "firewall", "nginx", "systemd"])
        need(self._config.require_approval_for_destructive_changes, "destructive_changes", ["delete", "destructive", "drop table", "remove data"])
        if req.auto_deploy_requested or "deployment" in categories:
            if self._config.require_approval_for_production_deployment:
                required.append("production_deployment")
        if risk in {RiskLevel.HIGH, RiskLevel.CRITICAL}:
            required.append("high_or_critical_risk")
        if req.max_cost is not None and self._config.maximum_cost is not None and req.max_cost > self._config.maximum_cost:
            required.append("cost_threshold_exceeded")
        # Ensure determinism and uniqueness
        return tuple(dict.fromkeys(sorted(required)))

    def _prepare_branch(self, req: DevelopmentRequest) -> str:
        # Verify clean repository and base branch via injected git workflow
        base_branch = req.requested_base_branch or self._config.default_base_branch
        gr = self._dep.git_workflow.verify_clean_repository(req.project_id)
        if not bool(gr.get("clean", False)):
            raise RuntimeError("dirty_repository")
        br = self._dep.git_workflow.verify_base_branch(req.project_id, base_branch)
        if not bool(br.get("exists", False)):
            raise RuntimeError("branch_preparation_failed")
        new_branch = _normalize_branch_name(req.project_id, req.request_id, req.requested_branch_name)
        cr = self._dep.git_workflow.create_development_branch(req.project_id, base_branch, new_branch)
        if not bool(cr.get("created", False)):
            raise RuntimeError("branch_preparation_failed")
        self._emit_event("branch_preparation_started", run_id=self._find_run_id(req.project_id, req.request_id), base_branch=base_branch, new_branch=new_branch)
        return new_branch

    def _record_missions(self, run_id: str, missions: Sequence[Mapping[str, Any]], deps: Mapping[str, Sequence[str]]) -> None:
        updates = {"missions": list(missions), "mission_dependencies": {k: list(v) for k, v in deps.items()}}
        self._dep.run_state_store.update_run(run_id, updates)

    def _execute_missions(
        self,
        run_id: str,
        req: DevelopmentRequest,
        branch: str,
        missions: Sequence[Mapping[str, Any]],
        deps: Mapping[str, Sequence[str]],
        start_monotonic: float,
    ) -> None:
        total_retries = 0
        completed: List[str] = []
        failed: List[str] = []
        blocked: List[str] = []
        budget_limit = req.max_cost if req.max_cost is not None else self._config.maximum_cost

        mission_index: Dict[str, Mapping[str, Any]] = {str(m["id"]): m for m in missions}

        def dependencies_done(mid: str) -> bool:
            return all(d in completed for d in deps.get(mid, ()))

        for mission in missions:
            if self._timeout_exceeded(start_monotonic):
                self._record_failure(run_id, "timeout")
                raise RuntimeError("timeout")
            mid = str(mission.get("id"))
            if not dependencies_done(mid):
                blocked.append(mid)
                continue
            self._emit_event("mission_execution_started", run_id=run_id, mission_id=mid)

            # Rate limit and budget checks
            if not self._dep.rate_limiter.allow(run_id, "mission"):
                blocked.append(mid)
                self._record_failure(run_id, "rate_limit_blocked")
                continue
            # Prepare execution context
            context = {
                "run_id": run_id,
                "project_id": req.project_id,
                "branch": branch,
                "allowed_paths": list(req.allowed_paths),
                "denied_paths": list(req.denied_paths),
            }
            attempt = 0
            while True:
                if budget_limit is not None and not self._dep.budget_evaluator.allow(run_id, 0.0, budget_limit):
                    self._record_failure(run_id, "budget_blocked")
                    blocked.append(mid)
                    break
                try:
                    result = self._dep.mission_executor.execute(mission, context)
                except Exception:
                    # Classify retry
                    retry_info = {"reason": "exception"}
                    if total_retries >= self._config.maximum_total_retry_attempts or attempt >= self._config.maximum_retry_attempts_per_mission:
                        failed.append(mid)
                        self._record_failure(run_id, "retry_exhausted")
                        break
                    cl = self._dep.retry_classifier.classify(retry_info)
                    if not bool(cl.get("retryable", False)):
                        failed.append(mid)
                        self._record_failure(run_id, "mission_execution_failed")
                        break
                    attempt += 1
                    total_retries += 1
                    self._emit_event("mission_retry_scheduled", run_id=run_id, mission_id=mid, attempt=attempt)
                    continue

                # Interpret result safely
                success = bool(result.get("success", False))
                retryable = bool(result.get("retryable", False))
                estimated_cost_delta = float(result.get("cost", 0.0))
                # Budget check after estimate
                if budget_limit is not None and not self._dep.budget_evaluator.allow(run_id, estimated_cost_delta, budget_limit):
                    self._record_failure(run_id, "budget_blocked")
                    blocked.append(mid)
                    break
                # Record provider usage if any
                usage = result.get("usage")
                if isinstance(usage, Mapping):
                    self._dep.usage_ledger.record_usage(run_id, dict(usage))

                if success:
                    completed.append(mid)
                    self._emit_event("mission_completed", run_id=run_id, mission_id=mid)
                    break
                # Security/compliance/billing/auth failures must not be retried
                failure_category = str(result.get("failure_category", ""))
                if failure_category in {"security", "compliance", "auth", "billing", "permission"}:
                    failed.append(mid)
                    code_map = {
                        "security": "security_failure",
                        "compliance": "compliance_failure",
                        "auth": "mission_execution_failed",
                        "billing": "mission_execution_failed",
                        "permission": "mission_execution_failed",
                    }
                    self._record_failure(run_id, code_map.get(failure_category, "mission_execution_failed"))
                    self._emit_event("mission_failed", run_id=run_id, mission_id=mid, safe_failure_code=code_map.get(failure_category, "mission_execution_failed"))
                    break

                if retryable and attempt < self._config.maximum_retry_attempts_per_mission and total_retries < self._config.maximum_total_retry_attempts:
                    attempt += 1
                    total_retries += 1
                    self._emit_event("mission_retry_scheduled", run_id=run_id, mission_id=mid, attempt=attempt)
                    continue

                failed.append(mid)
                self._record_failure(run_id, "mission_execution_failed")
                self._emit_event("mission_failed", run_id=run_id, mission_id=mid, safe_failure_code="mission_execution_failed")
                break

        updates = {
            "completed_missions": completed,
            "failed_missions": failed,
            "blocked_missions": blocked,
            "retries": total_retries,
        }
        self._dep.run_state_store.update_run(run_id, updates)

    def _final_validation(self, run_id: str, req: DevelopmentRequest, branch: str) -> bool:
        self._emit_event("validation_started", run_id=run_id)
        ctx = {
            "run_id": run_id,
            "project_id": req.project_id,
            "branch": branch,
            "allowed_paths": list(req.allowed_paths),
            "denied_paths": list(req.denied_paths),
        }
        try:
            gen = self._dep.validation_engine.validate_generated_files(ctx)
            if not bool(gen.get("success", False)):
                self._record_failure(run_id, "validation_failed")
                return False
            sel = self._dep.validation_engine.run_selected_tests(ctx)
            if not bool(sel.get("success", False)):
                self._record_failure(run_id, "validation_failed")
                return False
            full = self._dep.validation_engine.run_full_repository_tests(ctx)
            if not bool(full.get("success", False)):
                self._record_failure(run_id, "validation_failed")
                return False
            tests_executed = int(full.get("tests_executed", 0))
            tests_failed = int(full.get("tests_failed", 0))
            tests_passed = int(full.get("tests_passed", 0))
            tests_skipped = int(full.get("tests_skipped", 0))
            self._dep.run_state_store.update_run(
                run_id,
                {
                    "tests_executed": tests_executed,
                    "tests_failed": tests_failed,
                    "tests_passed": tests_passed,
                    "tests_skipped": tests_skipped,
                },
            )
            return tests_failed == 0 and tests_executed >= tests_passed
        except Exception:
            self._record_failure(run_id, "validation_failed")
            return False

    def _determine_merge_readiness(self, run_id: str, req: DevelopmentRequest, risk: RiskLevel) -> bool:
        # Auto-merge policy
        if risk in {RiskLevel.HIGH, RiskLevel.CRITICAL}:
            return False
        if risk == RiskLevel.MEDIUM and not self._config.auto_merge_medium_risk:
            return False
        if risk == RiskLevel.LOW and not self._config.auto_merge_low_risk:
            return False
        # Ensure approvals do not include any unresolved categories
        approvals = self._dep.approval_store.list(run_id)
        if any(a.decision == ApprovalDecisionType.REJECTED for a in approvals):
            return False
        return True

    def _attempt_merge(self, run_id: str, req: DevelopmentRequest, branch: str, risk: RiskLevel) -> bool:
        # Never merge when tests fail; this is ensured earlier. Also obey risk policy.
        if risk in {RiskLevel.HIGH, RiskLevel.CRITICAL}:
            self._record_failure(run_id, "merge_not_allowed")
            return False
        try:
            res = self._dep.git_workflow.merge_branch(req.project_id, branch, req.requested_base_branch or self._config.default_base_branch)
            if bool(res.get("merged", False)):
                self._dep.run_state_store.update_run(run_id, {"merge_status": "merged"})
                return True
            self._record_failure(run_id, "merge_failed")
            return False
        except Exception:
            self._record_failure(run_id, "merge_failed")
            return False

    def _deployment_allowed(self, risk: RiskLevel) -> bool:
        if not self._config.auto_deploy_enabled:
            return False
        # Production deployment always requires explicit approval; this supervisor only marks readiness
        return risk in {RiskLevel.LOW, RiskLevel.MEDIUM}

    def _result_for(
        self,
        run_id: str,
        req: DevelopmentRequest,
        plan: Optional[Mapping[str, Any]],
        missions: Sequence[Mapping[str, Any]],
        deps: Mapping[str, Sequence[str]],
        status: DevelopmentRunStatus,
    ) -> DevelopmentRunResult:
        rs = self._get_run_state(run_id)
        approvals = list(self._dep.approval_store.list(run_id))
        risk = RiskLevel(rs.get("risk_level", RiskLevel.LOW.value))  # type: ignore[arg-type]
        return DevelopmentRunResult(
            run_id=run_id,
            request_id=req.request_id,
            project_id=req.project_id,
            title=req.title,
            objective=req.objective,
            status=status,
            risk_level=risk,
            approvals=approvals,
            plan_summary=self._safe_plan_summary(plan),
            mission_summary={
                "mission_count": len(missions),
                "dependencies": {k: list(v) for k, v in deps.items()},
            },
            completed_missions=tuple(rs.get("completed_missions", [])),
            failed_missions=tuple(rs.get("failed_missions", [])),
            blocked_missions=tuple(rs.get("blocked_missions", [])),
            changed_files=tuple(rs.get("changed_files", [])),
            tests_executed=int(rs.get("tests_executed", 0)),
            tests_passed=int(rs.get("tests_passed", 0)),
            tests_failed=int(rs.get("tests_failed", 0)),
            tests_skipped=int(rs.get("tests_skipped", 0)),
            retries=int(rs.get("retries", 0)),
            provider_usage=dict(self._dep.usage_ledger.summarize(run_id)),
            estimated_cost=float(rs.get("estimated_cost", 0.0)),
            branch=rs.get("branch"),  # type: ignore[arg-type]
            commits=tuple(rs.get("commits", [])),
            merge_status=rs.get("merge_status"),  # type: ignore[arg-type]
            deployment_status=rs.get("deployment_status"),  # type: ignore[arg-type]
            warnings=tuple(rs.get("warnings", [])),
            safe_failure_codes=tuple(rs.get("safe_failure_codes", [])),
            next_required_action=rs.get("next_required_action"),  # type: ignore[arg-type]
            started_at=datetime.fromisoformat(rs.get("started_at")),  # type: ignore[arg-type]
            completed_at=(datetime.fromisoformat(rs["completed_at"]) if rs.get("completed_at") else None),  # type: ignore[arg-type]
        )

    def _safe_plan_summary(self, plan: Optional[Mapping[str, Any]]) -> Mapping[str, Any]:
        if not plan:
            return {}
        steps = plan.get("steps") if isinstance(plan, Mapping) else None
        return {
            "step_count": len(steps) if isinstance(steps, list) else 0,
            "categories": list(plan.get("categories", [])) if isinstance(plan, Mapping) else [],
        }

    def _transition(self, run_id: str, expected: DevelopmentRunStatus, new: DevelopmentRunStatus) -> None:
        with self._lock_for(run_id):
            rs = self._get_run_state(run_id)
            current = DevelopmentRunStatus(str(rs.get("status", DevelopmentRunStatus.CREATED.value)))
            if current != expected:
                # Allow idempotent transitions if already moved ahead
                if current == new:
                    return
                # Invalid transition
                self._record_failure(run_id, "invalid_transition")
                raise RuntimeError("invalid_state_transition")
            self._dep.run_state_store.update_run(run_id, {"status": new.value, "updated_at": self._dep.clock.utcnow().isoformat()})

    def _set_risk(self, run_id: str, risk: RiskLevel) -> None:
        with self._lock_for(run_id):
            self._dep.run_state_store.update_run(run_id, {"risk_level": risk.value})

    def _set_branch(self, run_id: str, branch: str) -> None:
        with self._lock_for(run_id):
            self._dep.run_state_store.update_run(run_id, {"branch": branch})

    def _ensure_within_time(self, start_monotonic: float, run_id: str) -> None:
        if self._timeout_exceeded(start_monotonic):
            self._record_failure(run_id, "timeout")
            raise RuntimeError("timeout")

    def _timeout_exceeded(self, start_monotonic: float) -> bool:
        return (monotonic() - start_monotonic) > float(self._config.maximum_run_seconds)

    def _record_failure(self, run_id: str, code: SafeFailureCode) -> None:
        with self._lock_for(run_id):
            rs = self._get_run_state(run_id)
            failures = list(rs.get("safe_failure_codes", []))
            failures.append(code)
            self._dep.run_state_store.update_run(run_id, {"safe_failure_codes": failures})

    def _find_run_id(self, project_id: str, request_id: str) -> str:
        rs = self._dep.run_state_store.get_by_project_request(project_id, request_id)
        if not rs:
            raise RuntimeError("unknown_run")
        return str(rs.get("run_id"))

    def _get_run_state(self, run_id: str) -> Mapping[str, Any]:
        rs = self._dep.run_state_store.get_run(run_id)
        if rs is None:
            raise RuntimeError("unknown_run")
        return rs

    def _get_request_from_state(self, rs: Mapping[str, Any]) -> DevelopmentRequest:
        snap = rs.get("request_snapshot")
        if not isinstance(snap, Mapping):
            raise RuntimeError("invalid_run_state")
        # Coerce DevelopmentRequest from snapshot and IDs
        return DevelopmentRequest(
            request_id=str(rs.get("request_id")),
            project_id=str(rs.get("project_id")),
            user_id="",  # Not persisted for privacy
            title=str(snap.get("title", "")),
            objective=str(snap.get("objective", "")),
            requirements=tuple(snap.get("requirements", [])),
            constraints=tuple(snap.get("constraints", [])),
            allowed_paths=tuple(snap.get("allowed_paths", [])),
            denied_paths=tuple(snap.get("denied_paths", [])),
            requested_branch_name=(snap.get("requested_branch_name") or None),
            requested_base_branch=(snap.get("requested_base_branch") or None),
            requested_risk_level=(RiskLevel(snap["requested_risk_level"]) if snap.get("requested_risk_level") else None),
            auto_merge_requested=bool(snap.get("auto_merge_requested", False)),
            auto_deploy_requested=bool(snap.get("auto_deploy_requested", False)),
            max_cost=(float(snap.get("max_cost")) if snap.get("max_cost") is not None else None),
            deadline=(datetime.fromisoformat(snap["deadline"]) if snap.get("deadline") else None),
            metadata=dict(snap.get("metadata", {})),
        )

    def _public_run_snapshot(self, rs: Mapping[str, Any]) -> Mapping[str, Any]:
        return {
            "run_id": rs.get("run_id"),
            "project_id": rs.get("project_id"),
            "request_id": rs.get("request_id"),
            "status": rs.get("status"),
            "risk_level": rs.get("risk_level"),
            "branch": rs.get("branch"),
            "tests_executed": rs.get("tests_executed"),
            "tests_failed": rs.get("tests_failed"),
            "tests_passed": rs.get("tests_passed"),
            "retries": rs.get("retries"),
            "started_at": rs.get("started_at"),
            "completed_at": rs.get("completed_at"),
        }

    def _build_final_report(self, rs: Mapping[str, Any]) -> Mapping[str, Any]:
        run_id = str(rs.get("run_id"))
        approvals = [asdict(a) for a in self._dep.approval_store.list(run_id)]
        # strip private notes if any field exists; here ApprovalDecision has no private notes
        return {
            "run_id": run_id,
            "request_id": rs.get("request_id"),
            "project_id": rs.get("project_id"),
            "title": (rs.get("request_snapshot", {}).get("title") if isinstance(rs.get("request_snapshot"), Mapping) else None),
            "objective_summary": (rs.get("request_snapshot", {}).get("objective") if isinstance(rs.get("request_snapshot"), Mapping) else None),
            "status": rs.get("status"),
            "risk_level": rs.get("risk_level"),
            "approvals": approvals,
            "plan_summary": self._safe_plan_summary(rs.get("plan") if isinstance(rs.get("plan"), Mapping) else None),
            "mission_summary": {
                "mission_count": len(rs.get("missions", [])),
                "completed": list(rs.get("completed_missions", [])),
                "failed": list(rs.get("failed_missions", [])),
                "blocked": list(rs.get("blocked_missions", [])),
            },
            "completed_missions": list(rs.get("completed_missions", [])),
            "failed_missions": list(rs.get("failed_missions", [])),
            "blocked_missions": list(rs.get("blocked_missions", [])),
            "changed_files": list(rs.get("changed_files", [])),
            "tests_executed": rs.get("tests_executed", 0),
            "tests_passed": rs.get("tests_passed", 0),
            "tests_failed": rs.get("tests_failed", 0),
            "tests_skipped": rs.get("tests_skipped", 0),
            "retries": rs.get("retries", 0),
            "provider_usage": self._dep.usage_ledger.summarize(run_id),
            "estimated_cost": rs.get("estimated_cost", 0.0),
            "branch": rs.get("branch"),
            "commits": list(rs.get("commits", [])),
            "merge_status": rs.get("merge_status"),
            "deployment_status": rs.get("deployment_status"),
            "warnings": list(rs.get("warnings", [])),
            "safe_failure_codes": list(rs.get("safe_failure_codes", [])),
            "next_required_action": rs.get("next_required_action"),
            "started_at": rs.get("started_at"),
            "completed_at": rs.get("completed_at"),
        }

    def _safe_fail(self, project_id: str, request_id: str, code: SafeFailureCode, final_state: DevelopmentRunStatus) -> None:
        # Attempt to mark existing run as failed safely if exists
        existing = self._dep.run_state_store.get_by_project_request(project_id, request_id)
        if existing is not None:
            run_id = str(existing.get("run_id"))
            self._record_failure(run_id, code)
            with self._lock_for(run_id):
                self._dep.run_state_store.update_run(run_id, {"status": final_state.value, "completed_at": self._dep.clock.utcnow().isoformat()})

    def _lock_for(self, run_id: str) -> RLock:
        with self._global_lock:
            lock = self._run_locks.get(run_id)
            if lock is None:
                lock = RLock()
                self._run_locks[run_id] = lock
            return lock

    def _emit_event(self, event_type: str, **data: Any) -> None:
        event = {
            "type": event_type,
            "timestamp": self._dep.clock.utcnow().isoformat(),
        }
        # Safe fields only
        for k, v in data.items():
            if k in {"metadata", "secrets", "headers", "env"}:
                continue
            if isinstance(v, Mapping) and k == "approval":
                # remove private notes if present
                event[k] = {kk: vv for kk, vv in v.items() if kk != "private_notes"}
            else:
                event[k] = v
        # Buffer in-memory and publish externally
        with self._global_lock:
            self._events_buffer.append(event)
            if len(self._events_buffer) > self._events_buffer_limit:
                self._events_buffer = self._events_buffer[-self._events_buffer_limit :]
        try:
            self._dep.event_sink.publish(event)
        except Exception:
            # Swallow to avoid breaking control flow; events are best-effort
            pass


# ==============================
# Builder and Status Functions
# ==============================


def build_autonomous_development_supervisor(
    config: AutonomousDevelopmentConfig,
    dependencies: Optional[Mapping[str, Any]] = None,
) -> AutonomousDevelopmentSupervisor:
    if dependencies is None:
        raise ValueError("invalid_supervisor_config: dependencies required")

    def _require(name: str) -> Any:
        if name not in dependencies or dependencies[name] is None:
            raise ValueError(f"invalid_supervisor_config: missing dependency {name}")
        return dependencies[name]

    dep = _SupervisorDependencies(
        clock=_require("clock"),
        id_gen=_require("id_gen"),
        event_sink=_require("event_sink"),
        project_registry=_require("project_registry"),
        planner=_require("planner"),
        plan_validator=_require("plan_validator"),
        mission_builder=_require("mission_builder"),
        mission_executor=_require("mission_executor"),
        validation_engine=_require("validation_engine"),
        retry_classifier=_require("retry_classifier"),
        git_workflow=_require("git_workflow"),
        approval_store=_require("approval_store"),
        run_state_store=_require("run_state_store"),
        usage_ledger=_require("usage_ledger"),
        rate_limiter=_require("rate_limiter"),
        budget_evaluator=_require("budget_evaluator"),
        report_writer=_require("report_writer"),
        risk_evaluator=dependencies.get("risk_evaluator"),
        cost_evaluator=dependencies.get("cost_evaluator"),
    )
    return AutonomousDevelopmentSupervisor(config=config, dependencies=dep)


def supervisor_status(supervisor: AutonomousDevelopmentSupervisor) -> Mapping[str, Any]:
    return supervisor.status()
