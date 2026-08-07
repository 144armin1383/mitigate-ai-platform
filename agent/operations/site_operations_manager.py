from __future__ import annotations

import enum
import hashlib
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Deque, Dict, Iterable, List, Mapping, MutableMapping, Optional, Protocol, Sequence, Tuple
from collections import deque
from urllib.parse import urlparse


# ==========================
# Protocols for Dependencies
# ==========================

class Clock(Protocol):
    def now(self) -> datetime: ...


class IDGenerator(Protocol):
    def new(self, namespace: str, name: str) -> str: ...


class EventSink(Protocol):
    def emit(self, event_type: str, payload: Mapping[str, Any]) -> None: ...


class ProjectMemoryManager(Protocol):
    def add_record(self, project_id: str, record: Mapping[str, Any]) -> None: ...


class AutonomousDevelopmentSupervisor(Protocol):
    def submit_development_request(self, request: Mapping[str, Any]) -> Mapping[str, Any]: ...


class BudgetEvaluator(Protocol):
    def can_spend(self, project_id: str, amount: float, cycle_id: str) -> bool: ...
    def record_spend(self, project_id: str, amount: float, cycle_id: str) -> None: ...


class ApprovalStore(Protocol):
    def is_approved(self, project_id: str, task_id: str) -> bool: ...
    def record_approval(self, project_id: str, task_id: str, approval: Mapping[str, Any]) -> None: ...
    def record_rejection(self, project_id: str, task_id: str, reason_code: str) -> None: ...


# ==========================
# Utility Implementations
# ==========================

class DefaultClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class DeterministicIDGenerator:
    """Generates deterministic IDs using sha256 over a namespace and name."""

    def new(self, namespace: str, name: str) -> str:
        h = hashlib.sha256()
        h.update(namespace.encode("utf-8"))
        h.update(b"::")
        h.update(name.encode("utf-8"))
        return h.hexdigest()[:32]


# ==========================
# Enumerations and Constants
# ==========================

class SiteFindingSeverity(enum.Enum):
    info = 0
    low = 1
    medium = 2
    high = 3
    critical = 4

    @classmethod
    def from_str(cls, value: str) -> "SiteFindingSeverity":
        v = value.strip().lower()
        return cls[v]


class SiteFindingType(enum.Enum):
    site_unavailable = "site_unavailable"
    slow_response = "slow_response"
    broken_internal_link = "broken_internal_link"
    broken_external_link = "broken_external_link"
    redirect_chain = "redirect_chain"
    redirect_loop = "redirect_loop"
    missing_title = "missing_title"
    duplicate_title = "duplicate_title"
    weak_title = "weak_title"
    missing_meta_description = "missing_meta_description"
    duplicate_meta_description = "duplicate_meta_description"
    missing_h1 = "missing_h1"
    multiple_h1 = "multiple_h1"
    heading_hierarchy_issue = "heading_hierarchy_issue"
    missing_canonical = "missing_canonical"
    conflicting_canonical = "conflicting_canonical"
    noindex_unexpected = "noindex_unexpected"
    robots_blocking = "robots_blocking"
    sitemap_missing = "sitemap_missing"
    sitemap_invalid = "sitemap_invalid"
    sitemap_stale = "sitemap_stale"
    sitemap_url_error = "sitemap_url_error"
    structured_data_missing = "structured_data_missing"
    structured_data_invalid = "structured_data_invalid"
    image_missing_alt = "image_missing_alt"
    image_oversized = "image_oversized"
    image_unoptimized = "image_unoptimized"
    image_broken = "image_broken"
    page_too_large = "page_too_large"
    render_blocking_resource = "render_blocking_resource"
    poor_lcp = "poor_lcp"
    poor_inp = "poor_inp"
    poor_cls = "poor_cls"
    accessibility_issue = "accessibility_issue"
    security_header_issue = "security_header_issue"
    mixed_content = "mixed_content"
    certificate_warning = "certificate_warning"
    stale_content = "stale_content"
    orphan_page = "orphan_page"
    duplicate_content = "duplicate_content"
    thin_content = "thin_content"
    pagination_issue = "pagination_issue"
    ecommerce_product_issue = "ecommerce_product_issue"
    ecommerce_price_issue = "ecommerce_price_issue"
    ecommerce_stock_issue = "ecommerce_stock_issue"
    checkout_warning = "checkout_warning"
    repository_health_issue = "repository_health_issue"
    deployment_health_issue = "deployment_health_issue"
    regression_detected = "regression_detected"
    seo_visibility_drop = "seo_visibility_drop"
    indexing_warning = "indexing_warning"
    monitoring_gap = "monitoring_gap"
    technical_debt = "technical_debt"
    maintenance_required = "maintenance_required"

    @classmethod
    def from_str(cls, value: str) -> "SiteFindingType":
        v = value.strip().lower()
        for item in cls:
            if item.value == v:
                return item
        raise ValueError(f"Unknown SiteFindingType: {value}")


class RiskLevel(enum.Enum):
    low = 1
    medium = 2
    high = 3
    critical = 4


class DevTaskStatus(enum.Enum):
    candidate = "candidate"
    awaiting_approval = "awaiting_approval"
    submitted = "submitted"
    planning = "planning"
    executing = "executing"
    validating = "validating"
    ready_for_merge = "ready_for_merge"
    merged = "merged"
    deployment_pending = "deployment_pending"
    deployed = "deployed"
    completed = "completed"
    blocked = "blocked"
    failed = "failed"
    cancelled = "cancelled"


class SiteOperationsStatus(enum.Enum):
    completed = "completed"
    completed_with_warnings = "completed_with_warnings"
    blocked = "blocked"
    failed = "failed"
    cancelled = "cancelled"


# ==========================
# Data Classes
# ==========================


def _safe_http_url(url: str) -> bool:
    try:
        p = urlparse(url)
        if p.scheme not in ("http", "https"):
            return False
        if not p.netloc:
            return False
        if "@" in p.netloc:
            return False
        # Disallow credentials in URL path/query/fragment implicitly by not logging/storing
        return True
    except Exception:
        return False


def _validate_rel_path(path: str) -> bool:
    if "\x00" in path:
        return False
    if path.startswith("/"):
        return False
    # Normalize simple traversal checks
    parts = path.replace("\\", "/").split("/")
    for part in parts:
        if part in ("..", "."):
            return False
    return True


def _stable_id(namespace: str, components: Sequence[str]) -> str:
    h = hashlib.sha256()
    h.update(namespace.encode("utf-8"))
    for c in components:
        h.update(b"::")
        h.update((c or "").encode("utf-8"))
    return h.hexdigest()[:32]


@dataclass(frozen=True)
class SiteOperationsProjectConfig:
    project_id: str
    site_name: str
    canonical_base_url: str
    repository_id: str
    default_branch: str
    allowed_paths: Tuple[str, ...] = field(default_factory=tuple)
    denied_paths: Tuple[str, ...] = field(default_factory=tuple)
    environment_name: str = "production"
    site_type: str = "website"
    cms_type: str = "wordpress"
    ecommerce_enabled: bool = False
    seo_enabled: bool = True
    performance_monitoring_enabled: bool = True
    availability_monitoring_enabled: bool = True
    accessibility_monitoring_enabled: bool = False
    security_monitoring_enabled: bool = True
    content_quality_monitoring_enabled: bool = True
    image_optimization_enabled: bool = True
    broken_link_monitoring_enabled: bool = True
    sitemap_monitoring_enabled: bool = True
    robots_monitoring_enabled: bool = True
    schema_monitoring_enabled: bool = True
    automatic_low_risk_fixes_enabled: bool = True
    automatic_medium_risk_fixes_enabled: bool = False
    maximum_tasks_per_cycle: int = 10
    maximum_estimated_cost_per_cycle: float = 1000.0
    minimum_severity_for_task_creation: SiteFindingSeverity = SiteFindingSeverity.low
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_dict(data: Mapping[str, Any]) -> "SiteOperationsProjectConfig":
        allowed_fields = {
            "project_id",
            "site_name",
            "canonical_base_url",
            "repository_id",
            "default_branch",
            "allowed_paths",
            "denied_paths",
            "environment_name",
            "site_type",
            "cms_type",
            "ecommerce_enabled",
            "seo_enabled",
            "performance_monitoring_enabled",
            "availability_monitoring_enabled",
            "accessibility_monitoring_enabled",
            "security_monitoring_enabled",
            "content_quality_monitoring_enabled",
            "image_optimization_enabled",
            "broken_link_monitoring_enabled",
            "sitemap_monitoring_enabled",
            "robots_monitoring_enabled",
            "schema_monitoring_enabled",
            "automatic_low_risk_fixes_enabled",
            "automatic_medium_risk_fixes_enabled",
            "maximum_tasks_per_cycle",
            "maximum_estimated_cost_per_cycle",
            "minimum_severity_for_task_creation",
            "metadata",
        }
        unknown = set(data.keys()) - allowed_fields
        if unknown:
            raise ValueError(f"Unknown project config fields: {sorted(unknown)}")

        project_id = str(data.get("project_id", "")).strip()
        if not project_id:
            raise ValueError("Project ID must be non-empty")

        canonical_base_url = str(data.get("canonical_base_url", "")).strip()
        if not _safe_http_url(canonical_base_url):
            raise ValueError("Canonical base URL is unsafe or invalid")

        # Validate repository paths in allowed/denied
        allowed_paths_in = tuple(map(str, data.get("allowed_paths", ()) or ()))
        denied_paths_in = tuple(map(str, data.get("denied_paths", ()) or ()))
        for p in allowed_paths_in + denied_paths_in:
            if not _validate_rel_path(p):
                raise ValueError(f"Unsafe repository path: {p}")

        # Ensure no secrets in metadata by key heuristic
        metadata = dict(data.get("metadata", {}) or {})
        for k in metadata.keys():
            lk = str(k).lower()
            if any(s in lk for s in ("secret", "token", "api_key", "apikey", "password", "credential")):
                raise ValueError("Secrets must not be included in project metadata")

        min_sev_raw = data.get("minimum_severity_for_task_creation", SiteFindingSeverity.low)
        if isinstance(min_sev_raw, SiteFindingSeverity):
            min_sev = min_sev_raw
        else:
            min_sev = SiteFindingSeverity.from_str(str(min_sev_raw))

        return SiteOperationsProjectConfig(
            project_id=project_id,
            site_name=str(data.get("site_name", project_id)),
            canonical_base_url=canonical_base_url,
            repository_id=str(data.get("repository_id", project_id)),
            default_branch=str(data.get("default_branch", "main")),
            allowed_paths=allowed_paths_in,
            denied_paths=denied_paths_in,
            environment_name=str(data.get("environment_name", "production")),
            site_type=str(data.get("site_type", "website")),
            cms_type=str(data.get("cms_type", "wordpress")),
            ecommerce_enabled=bool(data.get("ecommerce_enabled", False)),
            seo_enabled=bool(data.get("seo_enabled", True)),
            performance_monitoring_enabled=bool(data.get("performance_monitoring_enabled", True)),
            availability_monitoring_enabled=bool(data.get("availability_monitoring_enabled", True)),
            accessibility_monitoring_enabled=bool(data.get("accessibility_monitoring_enabled", False)),
            security_monitoring_enabled=bool(data.get("security_monitoring_enabled", True)),
            content_quality_monitoring_enabled=bool(data.get("content_quality_monitoring_enabled", True)),
            image_optimization_enabled=bool(data.get("image_optimization_enabled", True)),
            broken_link_monitoring_enabled=bool(data.get("broken_link_monitoring_enabled", True)),
            sitemap_monitoring_enabled=bool(data.get("sitemap_monitoring_enabled", True)),
            robots_monitoring_enabled=bool(data.get("robots_monitoring_enabled", True)),
            schema_monitoring_enabled=bool(data.get("schema_monitoring_enabled", True)),
            automatic_low_risk_fixes_enabled=bool(data.get("automatic_low_risk_fixes_enabled", True)),
            automatic_medium_risk_fixes_enabled=bool(data.get("automatic_medium_risk_fixes_enabled", False)),
            maximum_tasks_per_cycle=int(data.get("maximum_tasks_per_cycle", 10)),
            maximum_estimated_cost_per_cycle=float(data.get("maximum_estimated_cost_per_cycle", 1000.0)),
            minimum_severity_for_task_creation=min_sev,
            metadata=metadata,
        )


@dataclass(frozen=True)
class SiteOperationsConfig:
    max_findings_per_cycle: int = 1000
    max_task_candidates_per_cycle: int = 50
    max_auto_dispatch_per_cycle: int = 5
    max_cycle_seconds: int = 300
    events_buffer_limit: int = 1000


@dataclass
class SiteObservation:
    project_id: str
    source: str
    observation_type: str
    severity: Optional[SiteFindingSeverity] = None
    finding_type: Optional[SiteFindingType] = None
    url: Optional[str] = None
    component: Optional[str] = None
    summary: Optional[str] = None
    details: Mapping[str, Any] = field(default_factory=dict)
    observed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def key(self) -> str:
        parts = [
            self.project_id,
            self.source,
            self.observation_type,
            self.finding_type.value if self.finding_type else "",
            self.url or "",
            self.component or "",
        ]
        return _stable_id("mitigate.siteops.observation", parts)


@dataclass
class SiteFinding:
    finding_id: str
    project_id: str
    finding_type: SiteFindingType
    severity: SiteFindingSeverity
    title: str
    safe_summary: str
    affected_url: Optional[str]
    affected_component: Optional[str]
    first_seen_at: datetime
    last_seen_at: datetime
    occurrence_count: int
    evidence_summary: Optional[str]
    recommended_action: Optional[str]
    estimated_risk: RiskLevel
    estimated_effort: float
    auto_fix_eligible: bool
    approval_required: bool
    related_memory_records: Tuple[str, ...] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class SiteTaskCandidate:
    task_id: str
    project_id: str
    title: str
    objective: str
    finding_ids: Tuple[str, ...]
    recommended_changes: Mapping[str, Any]
    allowed_paths: Tuple[str, ...]
    denied_paths: Tuple[str, ...]
    risk_level: RiskLevel
    approval_required: bool
    auto_dispatch_eligible: bool
    priority: float
    estimated_effort: float
    estimated_cost: float
    acceptance_criteria: Tuple[str, ...]
    validation_requirements: Tuple[str, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class SiteOperationsCycleResult:
    cycle_id: str
    project_id: str
    started_at: datetime
    completed_at: datetime
    status: SiteOperationsStatus
    observations_processed: int
    findings_created: int
    findings_updated: int
    findings_resolved: int
    task_candidates_created: int
    tasks_auto_dispatched: int
    tasks_awaiting_approval: int
    tasks_deferred: int
    critical_findings: int
    estimated_cost: float
    development_run_ids: Tuple[str, ...]
    warnings: Tuple[str, ...]
    safe_failure_codes: Tuple[str, ...]
    next_recommended_actions: Tuple[str, ...]


# ==========================
# Internal Structures
# ==========================

@dataclass
class _TaskState:
    candidate: SiteTaskCandidate
    status: DevTaskStatus = DevTaskStatus.candidate
    development_run_id: Optional[str] = None


@dataclass
class _ProjectState:
    config: SiteOperationsProjectConfig
    observations: Dict[str, SiteObservation] = field(default_factory=dict)  # keyed by observation key
    findings: Dict[str, SiteFinding] = field(default_factory=dict)  # keyed by finding_id
    tasks: Dict[str, _TaskState] = field(default_factory=dict)  # keyed by task_id
    active_equivalent_dispatch_keys: Dict[str, str] = field(default_factory=dict)  # equivalent_key -> run_id
    events: Deque[Mapping[str, Any]] = field(default_factory=deque)
    lock: threading.RLock = field(default_factory=threading.RLock)


@dataclass
class _Dependencies:
    clock: Clock = field(default_factory=DefaultClock)
    id_gen: IDGenerator = field(default_factory=DeterministicIDGenerator)
    event_sink: Optional[EventSink] = None
    memory_manager: Optional[ProjectMemoryManager] = None
    dev_supervisor: Optional[AutonomousDevelopmentSupervisor] = None
    budget_evaluator: Optional[BudgetEvaluator] = None
    approval_store: Optional[ApprovalStore] = None


# ==========================
# Manager Implementation
# ==========================

class SiteOperationsManager:
    def __init__(self, config: SiteOperationsConfig, dependencies: Optional[_Dependencies] = None) -> None:
        if not isinstance(config, SiteOperationsConfig):
            raise ValueError("invalid_site_operations_config")
        self._config = config
        self._deps = dependencies or _Dependencies()
        self._projects: Dict[str, _ProjectState] = {}
        self._events: Deque[Mapping[str, Any]] = deque(maxlen=self._config.events_buffer_limit)
        self._lock = threading.RLock()

    # ---------------
    # Project Methods
    # ---------------
    def register_project(self, project_config: SiteOperationsProjectConfig | Mapping[str, Any]) -> None:
        cfg = project_config if isinstance(project_config, SiteOperationsProjectConfig) else SiteOperationsProjectConfig.from_dict(project_config)
        with self._lock:
            if cfg.project_id in self._projects:
                # Replace only if config differs
                self._projects[cfg.project_id].config = cfg
                return
            state = _ProjectState(config=cfg)
            state.events = deque(maxlen=self._config.events_buffer_limit)
            self._projects[cfg.project_id] = state

    def unregister_project(self, project_id: str) -> None:
        with self._lock:
            self._projects.pop(project_id, None)

    # -----------------
    # Observation Input
    # -----------------
    def ingest_observations(self, project_id: str, observations: Iterable[SiteObservation]) -> None:
        state = self._require_project(project_id)
        now = self._deps.clock.now()
        added = 0
        with state.lock:
            for obs in observations:
                # Ensure project isolation
                if obs.project_id != project_id:
                    continue
                key = obs.key()
                if key not in state.observations:
                    state.observations[key] = obs
                    added += 1
        if added:
            self._emit_event(project_id, "observations_ingested", {
                "project_id": project_id,
                "count": added,
                "timestamp": now.isoformat(),
            })

    # ------------------
    # Findings Assessment
    # ------------------
    def assess_findings(self, project_id: str) -> Tuple[int, int]:
        """Returns (created, updated). Deterministic per input observations."""
        state = self._require_project(project_id)
        created = 0
        updated = 0
        now = self._deps.clock.now()

        with state.lock:
            # Process existing observations deterministically by sorted key
            for key in sorted(state.observations.keys()):
                obs = state.observations[key]
                # Only convert observations that already propose a finding_type
                if not obs.finding_type or not obs.severity:
                    continue
                finding = self._finding_from_observation(state.config, obs)
                existing = state.findings.get(finding.finding_id)
                if existing is None:
                    state.findings[finding.finding_id] = finding
                    created += 1
                    self._emit_event(project_id, "finding_created", {
                        "project_id": project_id,
                        "finding_id": finding.finding_id,
                        "finding_type": finding.finding_type.value,
                        "severity": finding.severity.name,
                        "timestamp": now.isoformat(),
                    })
                    if finding.severity in (SiteFindingSeverity.high, SiteFindingSeverity.critical):
                        self._emit_event(project_id, "critical_finding_detected", {
                            "project_id": project_id,
                            "finding_id": finding.finding_id,
                            "finding_type": finding.finding_type.value,
                            "severity": finding.severity.name,
                            "timestamp": now.isoformat(),
                        })
                else:
                    # Update deterministically: occurrence count and last_seen; severity escalation only
                    esc = finding.severity.value > existing.severity.value
                    existing.last_seen_at = finding.last_seen_at
                    existing.occurrence_count += 1
                    if esc:
                        existing.severity = finding.severity
                    updated += 1
                    self._emit_event(project_id, "finding_updated", {
                        "project_id": project_id,
                        "finding_id": existing.finding_id,
                        "finding_type": existing.finding_type.value,
                        "severity": existing.severity.name,
                        "timestamp": now.isoformat(),
                    })
        return created, updated

    def _finding_from_observation(self, cfg: SiteOperationsProjectConfig, obs: SiteObservation) -> SiteFinding:
        assert obs.finding_type is not None and obs.severity is not None
        # Title and summary synthesis deterministically
        url_note = f" for {obs.url}" if obs.url else ""
        title = f"{obs.finding_type.value.replace('_', ' ').title()}{url_note}"
        safe_summary = obs.summary or f"Detected {obs.finding_type.value} from {obs.source}"
        risk = self._estimated_risk_for_finding(obs.finding_type, obs.severity)
        effort = self._estimated_effort_for_finding(obs.finding_type, obs.severity)
        auto_fix_eligible = self._auto_fix_eligible(obs.finding_type)
        approval_required = self._approval_required_for_finding(obs.finding_type)
        fid = _stable_id(
            "mitigate.siteops.finding",
            [cfg.project_id, obs.finding_type.value, obs.url or "", obs.component or "", title],
        )
        now = self._deps.clock.now()
        return SiteFinding(
            finding_id=fid,
            project_id=cfg.project_id,
            finding_type=obs.finding_type,
            severity=obs.severity,
            title=title,
            safe_summary=safe_summary,
            affected_url=obs.url,
            affected_component=obs.component,
            first_seen_at=now,
            last_seen_at=now,
            occurrence_count=1,
            evidence_summary=None,
            recommended_action=self._recommended_action_for_finding(obs.finding_type),
            estimated_risk=risk,
            estimated_effort=effort,
            auto_fix_eligible=auto_fix_eligible,
            approval_required=approval_required,
            related_memory_records=tuple(),
            metadata={"source": obs.source, "observation_type": obs.observation_type},
        )

    # --------------------
    # Task Candidate Logic
    # --------------------
    def generate_task_candidates(self, project_id: str) -> List[SiteTaskCandidate]:
        state = self._require_project(project_id)
        cfg = state.config
        min_sev = cfg.minimum_severity_for_task_creation.value

        # Sort findings deterministically
        with state.lock:
            findings = list(state.findings.values())
        findings.sort(key=lambda f: (f.severity.value * -1, f.finding_type.value, f.affected_url or "", f.finding_id))

        candidates: List[SiteTaskCandidate] = []
        seen_equiv: set[str] = set()
        for f in findings:
            if f.severity.value < min_sev:
                continue
            if f.finding_type in (SiteFindingType.site_unavailable,):
                # Always create urgent task
                pass
            # Skip if already has an open task
            if self._finding_has_open_task(state, f.finding_id):
                continue
            cand = self._task_for_finding(cfg, f)
            if cand is None:
                continue
            # Deduplicate equivalent tasks
            equiv_key = self._equivalent_task_key(cand)
            if equiv_key in seen_equiv:
                continue
            seen_equiv.add(equiv_key)
            candidates.append(cand)
            if len(candidates) >= min(self._config.max_task_candidates_per_cycle, cfg.maximum_tasks_per_cycle):
                break

        # Register candidates into state
        now = self._deps.clock.now()
        created: List[SiteTaskCandidate] = []
        with state.lock:
            for cand in candidates:
                if cand.task_id not in state.tasks:
                    state.tasks[cand.task_id] = _TaskState(candidate=cand)
                    created.append(cand)
        for cand in created:
            self._emit_event(project_id, "task_candidate_created", {
                "project_id": project_id,
                "task_id": cand.task_id,
                "timestamp": now.isoformat(),
            })

        return created

    def _finding_has_open_task(self, state: _ProjectState, finding_id: str) -> bool:
        for ts in state.tasks.values():
            if finding_id in ts.candidate.finding_ids and ts.status not in (DevTaskStatus.completed, DevTaskStatus.cancelled, DevTaskStatus.failed):
                return True
        return False

    def _equivalent_task_key(self, cand: SiteTaskCandidate) -> str:
        return _stable_id(
            "mitigate.siteops.task_equiv",
            [
                cand.project_id,
                cand.title,
                cand.objective,
                ",".join(sorted(cand.finding_ids)),
                ",".join(cand.allowed_paths),
                ",".join(cand.denied_paths),
            ],
        )

    def _task_for_finding(self, cfg: SiteOperationsProjectConfig, f: SiteFinding) -> Optional[SiteTaskCandidate]:
        # Map finding to task
        title, objective, changes, acceptance, validation, risk = self._task_blueprint_for_finding(f)
        if title is None:
            return None
        approval_required = self._approval_required_for_task_blueprint(f, risk)
        auto_eligible = self._auto_dispatch_eligible(cfg, risk, approval_required)
        # Deterministic priority calculation
        priority = self._priority_for_finding(f)
        est_cost = self._estimated_cost_for_effort(f.estimated_effort)
        task_id = _stable_id("mitigate.siteops.task", [
            cfg.project_id,
            f.finding_type.value,
            f.affected_url or "",
            title,
            ",".join(sorted([f.finding_id])),
        ])
        return SiteTaskCandidate(
            task_id=task_id,
            project_id=cfg.project_id,
            title=title,
            objective=objective,
            finding_ids=(f.finding_id,),
            recommended_changes=changes,
            allowed_paths=cfg.allowed_paths,
            denied_paths=cfg.denied_paths,
            risk_level=risk,
            approval_required=approval_required,
            auto_dispatch_eligible=auto_eligible,
            priority=priority,
            estimated_effort=f.estimated_effort,
            estimated_cost=est_cost,
            acceptance_criteria=acceptance,
            validation_requirements=validation,
            metadata={"finding_type": f.finding_type.value},
        )

    # --------------------
    # Dispatching
    # --------------------
    def dispatch_safe_tasks(self, project_id: str) -> Tuple[int, List[str], List[str]]:
        state = self._require_project(project_id)
        cfg = state.config
        dev = self._deps.dev_supervisor
        now = self._deps.clock.now()
        if dev is None:
            return 0, [], ["dependency_failed"]
        dispatched = 0
        run_ids: List[str] = []
        failures: List[str] = []
        total_cost = 0.0
        with state.lock:
            # Order candidates deterministically by priority high-to-low and task_id
            candidates = [ts for ts in state.tasks.values() if ts.status in (DevTaskStatus.candidate, DevTaskStatus.awaiting_approval)]
            # Filter by approval
            filtered: List[_TaskState] = []
            for ts in candidates:
                cand = ts.candidate
                approved = True
                if cand.approval_required:
                    approved = self._is_task_approved(state, cand.task_id)
                    if ts.status == DevTaskStatus.candidate and cand.approval_required and not approved:
                        ts.status = DevTaskStatus.awaiting_approval
                        self._emit_event(project_id, "task_approval_required", {
                            "project_id": project_id,
                            "task_id": cand.task_id,
                            "timestamp": now.isoformat(),
                        })
                if cand.auto_dispatch_eligible and approved:
                    filtered.append(ts)
            filtered.sort(key=lambda t: (-t.candidate.priority, t.candidate.task_id))

            for ts in filtered:
                if dispatched >= min(self._config.max_auto_dispatch_per_cycle, cfg.maximum_tasks_per_cycle):
                    failures.append("task_limit_reached")
                    self._emit_event(project_id, "task_deferred", {
                        "project_id": project_id,
                        "task_id": ts.candidate.task_id,
                        "timestamp": now.isoformat(),
                    })
                    continue
                cand = ts.candidate
                # Budget check
                candidate_cost = cand.estimated_cost
                if total_cost + candidate_cost > cfg.maximum_estimated_cost_per_cycle:
                    failures.append("budget_blocked")
                    self._emit_event(project_id, "task_deferred", {
                        "project_id": project_id,
                        "task_id": cand.task_id,
                        "timestamp": now.isoformat(),
                    })
                    continue
                if self._deps.budget_evaluator and not self._deps.budget_evaluator.can_spend(project_id, candidate_cost, self._deterministic_cycle_id(project_id, now)):
                    failures.append("budget_blocked")
                    self._emit_event(project_id, "task_deferred", {
                        "project_id": project_id,
                        "task_id": cand.task_id,
                        "timestamp": now.isoformat(),
                    })
                    continue
                # Prevent duplicate equivalent dispatch
                equiv_key = self._equivalent_task_key(cand)
                if equiv_key in state.active_equivalent_dispatch_keys:
                    failures.append("duplicate_dispatch_prevented")
                    continue
                # Build development request safely
                request = {
                    "project_id": project_id,
                    "objective": cand.objective,
                    "allowed_paths": list(cand.allowed_paths),
                    "denied_paths": list(cand.denied_paths),
                    "risk_level": cand.risk_level.name,
                    "acceptance_criteria": list(cand.acceptance_criteria),
                    "validation_requirements": list(cand.validation_requirements),
                    "metadata": {
                        "task_id": cand.task_id,
                        "finding_ids": list(cand.finding_ids),
                        "site_name": cfg.site_name,
                        "environment_name": cfg.environment_name,
                        "repository_id": cfg.repository_id,
                        "default_branch": cfg.default_branch,
                    },
                }
                try:
                    resp = dev.submit_development_request(request)
                    run_id = str(resp.get("run_id") or resp.get("id") or _stable_id("mitigate.siteops.run", [project_id, cand.task_id]))
                    state.active_equivalent_dispatch_keys[equiv_key] = run_id
                    ts.status = DevTaskStatus.submitted
                    ts.development_run_id = run_id
                    dispatched += 1
                    total_cost += candidate_cost
                    if self._deps.budget_evaluator:
                        self._deps.budget_evaluator.record_spend(project_id, candidate_cost, self._deterministic_cycle_id(project_id, now))
                    run_ids.append(run_id)
                    self._emit_event(project_id, "task_dispatched", {
                        "project_id": project_id,
                        "task_id": cand.task_id,
                        "development_run_id": run_id,
                        "timestamp": now.isoformat(),
                    })
                    self._write_memory_safe(project_id, {
                        "type": "task_dispatched",
                        "task_id": cand.task_id,
                        "objective": cand.objective,
                        "finding_ids": list(cand.finding_ids),
                        "development_run_id": run_id,
                        "dispatched_at": now.isoformat(),
                    })
                except Exception:
                    ts.status = DevTaskStatus.blocked
                    failures.append("dispatch_failed")
        return dispatched, run_ids, failures

    # ---------------------------
    # Approvals
    # ---------------------------
    def approve_task(self, task_id: str, approval: Mapping[str, Any]) -> bool:
        state = self._find_project_by_task(task_id)
        if state is None:
            return False
        with state.lock:
            ts = state.tasks.get(task_id)
            if not ts:
                return False
            if self._deps.approval_store:
                try:
                    self._deps.approval_store.record_approval(state.config.project_id, task_id, approval)
                except Exception:
                    pass
            # Set status for potential dispatch in next call
            if ts.status == DevTaskStatus.awaiting_approval:
                ts.status = DevTaskStatus.candidate
            return True

    def reject_task(self, task_id: str, reason_code: str) -> bool:
        state = self._find_project_by_task(task_id)
        if state is None:
            return False
        with state.lock:
            ts = state.tasks.get(task_id)
            if not ts:
                return False
            if self._deps.approval_store:
                try:
                    self._deps.approval_store.record_rejection(state.config.project_id, task_id, reason_code)
                except Exception:
                    pass
            ts.status = DevTaskStatus.cancelled
            return True

    # ---------------------------
    # Cycle Orchestration
    # ---------------------------
    def run_cycle(self, project_id: str) -> SiteOperationsCycleResult:
        state = self._require_project(project_id)
        started_at = self._deps.clock.now()
        cycle_id = self._deterministic_cycle_id(project_id, started_at)
        self._emit_event(project_id, "operations_cycle_started", {
            "project_id": project_id,
            "cycle_id": cycle_id,
            "timestamp": started_at.isoformat(),
        })
        warnings: List[str] = []
        failures: List[str] = []
        created = updated = resolved = 0
        candidates_created = 0
        auto_dispatched = 0
        awaiting_approval = 0
        deferred = 0
        critical_count = 0
        est_cost = 0.0
        dev_runs: List[str] = []
        status = SiteOperationsStatus.completed

        try:
            created, updated = self.assess_findings(project_id)
            # Count criticals
            with state.lock:
                critical_count = sum(1 for f in state.findings.values() if f.severity in (SiteFindingSeverity.high, SiteFindingSeverity.critical))
            cands = self.generate_task_candidates(project_id)
            candidates_created = len(cands)
            # Count awaiting approval after generation
            with state.lock:
                awaiting_approval = sum(1 for t in state.tasks.values() if t.status == DevTaskStatus.awaiting_approval)
            dcount, runs, dfailures = self.dispatch_safe_tasks(project_id)
            auto_dispatched = dcount
            dev_runs = runs
            deferred = sum(1 for code in dfailures if code in ("task_limit_reached", "budget_blocked"))
            failures.extend(code for code in dfailures if code not in ("task_limit_reached", "budget_blocked"))
            with state.lock:
                est_cost = sum(t.candidate.estimated_cost for t in state.tasks.values() if t.status in (DevTaskStatus.submitted, DevTaskStatus.executing, DevTaskStatus.planning))
        except Exception:
            status = SiteOperationsStatus.failed
            failures.append("dependency_failed")
        completed_at = self._deps.clock.now()

        # Memory capture
        mem_ok = self._write_memory_safe(project_id, {
            "type": "operations_cycle_summary",
            "cycle_id": cycle_id,
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "findings_created": created,
            "findings_updated": updated,
            "task_candidates_created": candidates_created,
            "tasks_auto_dispatched": auto_dispatched,
            "awaiting_approval": awaiting_approval,
            "critical_findings": critical_count,
            "development_run_ids": dev_runs,
        })
        if not mem_ok:
            warnings.append("memory_capture_failed")
            if status == SiteOperationsStatus.completed:
                status = SiteOperationsStatus.completed_with_warnings

        result = SiteOperationsCycleResult(
            cycle_id=cycle_id,
            project_id=project_id,
            started_at=started_at,
            completed_at=completed_at,
            status=status,
            observations_processed=self._count_observations(project_id),
            findings_created=created,
            findings_updated=updated,
            findings_resolved=resolved,
            task_candidates_created=candidates_created,
            tasks_auto_dispatched=auto_dispatched,
            tasks_awaiting_approval=awaiting_approval,
            tasks_deferred=deferred,
            critical_findings=critical_count,
            estimated_cost=est_cost,
            development_run_ids=tuple(dev_runs),
            warnings=tuple(warnings),
            safe_failure_codes=tuple(failures),
            next_recommended_actions=self._next_actions_hint(project_id),
        )
        self._emit_event(project_id, "operations_cycle_completed", {
            "project_id": project_id,
            "cycle_id": cycle_id,
            "status": result.status.value,
            "timestamp": completed_at.isoformat(),
        })
        return result

    def run_all_projects_cycle(self) -> List[SiteOperationsCycleResult]:
        with self._lock:
            pids = list(self._projects.keys())
        results: List[SiteOperationsCycleResult] = []
        for pid in sorted(pids):
            results.append(self.run_cycle(pid))
        return results

    # ---------------------------
    # Status and Reporting
    # ---------------------------
    def status(self, project_id: Optional[str] = None) -> Mapping[str, Any]:
        if project_id is not None:
            state = self._require_project(project_id)
            with state.lock:
                return {
                    "project_id": project_id,
                    "site_name": state.config.site_name,
                    "findings": len(state.findings),
                    "open_tasks": sum(1 for t in state.tasks.values() if t.status not in (DevTaskStatus.completed, DevTaskStatus.cancelled, DevTaskStatus.failed)),
                    "awaiting_approval": sum(1 for t in state.tasks.values() if t.status == DevTaskStatus.awaiting_approval),
                    "recent_events": list(state.events)[-10:],
                }
        with self._lock:
            return {
                "projects": {
                    pid: {
                        "site_name": st.config.site_name,
                        "findings": len(st.findings),
                        "open_tasks": sum(1 for t in st.tasks.values() if t.status not in (DevTaskStatus.completed, DevTaskStatus.cancelled, DevTaskStatus.failed)),
                        "awaiting_approval": sum(1 for t in st.tasks.values() if t.status == DevTaskStatus.awaiting_approval),
                    }
                    for pid, st in self._projects.items()
                }
            }

    def latest_findings(self, project_id: str, limit: int = 20) -> List[SiteFinding]:
        state = self._require_project(project_id)
        with state.lock:
            items = list(state.findings.values())
        items.sort(key=lambda f: (f.last_seen_at, f.finding_id), reverse=True)
        return items[: max(0, limit)]

    def latest_events(self, limit: int = 50) -> List[Mapping[str, Any]]:
        with self._lock:
            items = list(self._events)
        return items[-max(0, limit):]

    def final_cycle_report(self, project_id: str) -> Mapping[str, Any]:
        state = self._require_project(project_id)
        with state.lock:
            findings = list(state.findings.values())
            tasks = list(state.tasks.values())
        critical_alerts = [f for f in findings if f.severity in (SiteFindingSeverity.high, SiteFindingSeverity.critical)]
        new_findings = sorted(findings, key=lambda f: f.first_seen_at, reverse=True)[:20]
        recurring_findings = [f for f in findings if f.occurrence_count > 1]
        resolved_findings: List[SiteFinding] = []  # resolution lifecycle external
        work_started = [t.candidate for t in tasks if t.status in (DevTaskStatus.submitted, DevTaskStatus.planning, DevTaskStatus.executing, DevTaskStatus.validating)]
        awaiting = [t.candidate for t in tasks if t.status == DevTaskStatus.awaiting_approval]
        completed = [t.candidate for t in tasks if t.status == DevTaskStatus.completed]
        deferred = [t.candidate for t in tasks if t.status == DevTaskStatus.blocked]

        return {
            "project": {
                "project_id": project_id,
                "site_name": state.config.site_name,
                "canonical_base_url": state.config.canonical_base_url,
                "environment": state.config.environment_name,
            },
            "site_health_summary": {
                "total_findings": len(findings),
                "critical": len(critical_alerts),
            },
            "seo_summary": self._summary_for_category(findings, {
                SiteFindingType.missing_title,
                SiteFindingType.duplicate_title,
                SiteFindingType.missing_meta_description,
                SiteFindingType.duplicate_meta_description,
                SiteFindingType.missing_canonical,
                SiteFindingType.conflicting_canonical,
                SiteFindingType.noindex_unexpected,
                SiteFindingType.sitemap_missing,
                SiteFindingType.sitemap_invalid,
                SiteFindingType.sitemap_stale,
                SiteFindingType.structured_data_missing,
                SiteFindingType.structured_data_invalid,
                SiteFindingType.broken_internal_link,
                SiteFindingType.broken_external_link,
                SiteFindingType.redirect_chain,
                SiteFindingType.redirect_loop,
                SiteFindingType.seo_visibility_drop,
                SiteFindingType.indexing_warning,
                SiteFindingType.orphan_page,
                SiteFindingType.thin_content,
                SiteFindingType.duplicate_content,
            }),
            "performance_summary": self._summary_for_category(findings, {
                SiteFindingType.slow_response,
                SiteFindingType.page_too_large,
                SiteFindingType.render_blocking_resource,
                SiteFindingType.poor_lcp,
                SiteFindingType.poor_inp,
                SiteFindingType.poor_cls,
                SiteFindingType.image_unoptimized,
                SiteFindingType.image_oversized,
            }),
            "availability_summary": self._summary_for_category(findings, {SiteFindingType.site_unavailable, SiteFindingType.deployment_health_issue}),
            "security_summary": self._summary_for_category(findings, {SiteFindingType.security_header_issue, SiteFindingType.mixed_content, SiteFindingType.certificate_warning}),
            "accessibility_summary": self._summary_for_category(findings, {SiteFindingType.accessibility_issue}),
            "ecommerce_summary": self._summary_for_category(findings, {
                SiteFindingType.ecommerce_product_issue,
                SiteFindingType.ecommerce_price_issue,
                SiteFindingType.ecommerce_stock_issue,
                SiteFindingType.checkout_warning,
            }) if state.config.ecommerce_enabled else {"enabled": False},
            "new_findings": [self._safe_finding_view(f) for f in new_findings],
            "recurring_findings": [self._safe_finding_view(f) for f in recurring_findings[:20]],
            "resolved_findings": [self._safe_finding_view(f) for f in resolved_findings],
            "work_started_automatically": [self._safe_task_view(t) for t in work_started],
            "work_awaiting_approval": [self._safe_task_view(t) for t in awaiting],
            "completed_development_work": [self._safe_task_view(t) for t in completed],
            "deferred_work": [self._safe_task_view(t) for t in deferred],
            "critical_alerts": [self._safe_finding_view(f) for f in critical_alerts],
            "cost_summary": {
                "estimated_cost_in_progress": sum(t.estimated_cost for t in work_started),
            },
            "next_recommended_actions": list(self._next_actions_hint(project_id)),
        }

    def close(self) -> None:
        # No background threads created; nothing to clean beyond in-memory state
        pass

    # ---------------------------
    # Helper methods
    # ---------------------------
    def _require_project(self, project_id: str) -> _ProjectState:
        with self._lock:
            if project_id not in self._projects:
                raise KeyError("unknown_project")
            return self._projects[project_id]

    def _emit_event(self, project_id: str, event_type: str, payload: Mapping[str, Any]) -> None:
        event = {
            **payload,
            "event_type": event_type,
            "project_id": project_id,
        }
        with self._lock:
            self._events.append(event)
        state = self._projects.get(project_id)
        if state is not None:
            with state.lock:
                state.events.append(event)
        if self._deps.event_sink:
            try:
                self._deps.event_sink.emit(event_type, event)
            except Exception:
                # Never raise on event sink failure
                pass

    def _write_memory_safe(self, project_id: str, record: Mapping[str, Any]) -> bool:
        if not self._deps.memory_manager:
            return True
        try:
            self._deps.memory_manager.add_record(project_id, record)
            return True
        except Exception:
            return False

    def _deterministic_cycle_id(self, project_id: str, started_at: datetime) -> str:
        # Deterministic per project and start minute
        minute_bucket = started_at.replace(second=0, microsecond=0).isoformat()
        return _stable_id("mitigate.siteops.cycle", [project_id, minute_bucket])

    def _count_observations(self, project_id: str) -> int:
        state = self._require_project(project_id)
        with state.lock:
            return len(state.observations)

    def _is_task_approved(self, state: _ProjectState, task_id: str) -> bool:
        if self._deps.approval_store:
            try:
                return self._deps.approval_store.is_approved(state.config.project_id, task_id)
            except Exception:
                return False
        # Local fallback: not approved unless explicitly approved via approve_task
        ts = state.tasks.get(task_id)
        return bool(ts and ts.status != DevTaskStatus.awaiting_approval)

    def _priority_for_finding(self, f: SiteFinding) -> float:
        # Deterministic weighted priority
        base = 10.0 * (f.severity.value + 1)
        impact_bonus = 0.0
        if f.finding_type in (SiteFindingType.site_unavailable, SiteFindingType.checkout_warning):
            impact_bonus += 50.0
        elif f.finding_type in (SiteFindingType.seo_visibility_drop, SiteFindingType.indexing_warning):
            impact_bonus += 20.0
        recurrence_bonus = min(f.occurrence_count, 10) * 1.5
        risk_penalty = {RiskLevel.low: 0.0, RiskLevel.medium: 2.0, RiskLevel.high: 5.0, RiskLevel.critical: 8.0}[f.estimated_risk]
        effort_penalty = min(f.estimated_effort, 40.0) * 0.2
        return base + impact_bonus + recurrence_bonus - risk_penalty - effort_penalty

    def _estimated_risk_for_finding(self, ft: SiteFindingType, sev: SiteFindingSeverity) -> RiskLevel:
        if ft in (SiteFindingType.site_unavailable, SiteFindingType.checkout_warning, SiteFindingType.mixed_content, SiteFindingType.certificate_warning):
            return RiskLevel.high if sev.value <= SiteFindingSeverity.high.value else RiskLevel.critical
        if ft in (SiteFindingType.security_header_issue,):
            return RiskLevel.high if sev.value >= SiteFindingSeverity.medium.value else RiskLevel.medium
        if ft in (SiteFindingType.image_unoptimized, SiteFindingType.image_oversized, SiteFindingType.missing_title, SiteFindingType.missing_meta_description):
            return RiskLevel.low
        if ft in (SiteFindingType.redirect_chain, SiteFindingType.redirect_loop, SiteFindingType.broken_internal_link, SiteFindingType.broken_external_link):
            return RiskLevel.medium
        if ft in (SiteFindingType.seo_visibility_drop, SiteFindingType.indexing_warning):
            return RiskLevel.high
        return RiskLevel.medium if sev.value >= SiteFindingSeverity.medium.value else RiskLevel.low

    def _estimated_effort_for_finding(self, ft: SiteFindingType, sev: SiteFindingSeverity) -> float:
        # Simple deterministic effort model (hours)
        table: Dict[SiteFindingType, float] = {
            SiteFindingType.image_unoptimized: 2.0,
            SiteFindingType.image_oversized: 1.5,
            SiteFindingType.missing_title: 1.0,
            SiteFindingType.missing_meta_description: 1.0,
            SiteFindingType.broken_internal_link: 2.0,
            SiteFindingType.redirect_chain: 3.0,
            SiteFindingType.redirect_loop: 4.0,
            SiteFindingType.site_unavailable: 6.0,
            SiteFindingType.security_header_issue: 3.0,
            SiteFindingType.poor_lcp: 5.0,
            SiteFindingType.poor_inp: 5.0,
            SiteFindingType.poor_cls: 4.0,
            SiteFindingType.page_too_large: 3.0,
        }
        base = table.get(ft, 2.0)
        sev_mult = {SiteFindingSeverity.info: 0.8, SiteFindingSeverity.low: 1.0, SiteFindingSeverity.medium: 1.2, SiteFindingSeverity.high: 1.5, SiteFindingSeverity.critical: 1.8}[sev]
        return round(base * sev_mult, 2)

    def _estimated_cost_for_effort(self, effort_hours: float) -> float:
        # Deterministic flat rate model
        return round(effort_hours * 120.0, 2)

    def _auto_fix_eligible(self, ft: SiteFindingType) -> bool:
        return ft in (
            SiteFindingType.image_unoptimized,
            SiteFindingType.image_oversized,
            SiteFindingType.missing_title,
            SiteFindingType.missing_meta_description,
            SiteFindingType.broken_internal_link,
            SiteFindingType.page_too_large,
            SiteFindingType.render_blocking_resource,
        )

    def _approval_required_for_finding(self, ft: SiteFindingType) -> bool:
        # Conservative: robots/canonical broad changes require approval, but we do not create sitewide tasks here.
        if ft in (SiteFindingType.noindex_unexpected, SiteFindingType.robots_blocking, SiteFindingType.conflicting_canonical):
            return True
        if ft in (SiteFindingType.security_header_issue, SiteFindingType.mixed_content, SiteFindingType.certificate_warning):
            return True
        return False

    def _task_blueprint_for_finding(self, f: SiteFinding) -> Tuple[Optional[str], Optional[str], Mapping[str, Any], Tuple[str, ...], Tuple[str, ...], RiskLevel]:
        # Returns: (title, objective, changes, acceptance, validation, risk)
        ft = f.finding_type
        risk = f.estimated_risk
        if ft in (SiteFindingType.image_unoptimized, SiteFindingType.image_oversized):
            title = "Optimize images for performance"
            objective = "Compress and resize images, enable lazy loading, and ensure WebP/AVIF where supported without degrading quality."
            changes = {"actions": ["compress_images", "resize_large_images", "enable_lazy_load"], "scope_url": f.affected_url}
            acceptance = (
                "All affected images are served in optimized formats with appropriate dimensions.",
                "Largest Contentful Paint improves or remains stable on affected pages.",
            )
            validation = (
                "Run performance audit to verify LCP/CLS/INP are not degraded.",
                "Verify visual parity on affected pages.",
            )
            return title, objective, changes, acceptance, validation, risk
        if ft == SiteFindingType.missing_title:
            title = "Add concise, descriptive page title"
            objective = "Introduce a clear, unique <title> element for the affected page."
            changes = {"actions": ["update_html_head"], "scope_url": f.affected_url}
            acceptance = (
                "Page renders a unique, descriptive title tag.",
                "No duplicate titles on key pages.",
            )
            validation = (
                "Crawl affected URL to confirm presence of title.",
                "Check that title length is within recommended range.",
            )
            return title, objective, changes, acceptance, validation, risk
        if ft == SiteFindingType.missing_meta_description:
            title = "Add informative meta description"
            objective = "Add a concise, accurate meta description tag reflecting page content without keyword stuffing."
            changes = {"actions": ["update_html_head"], "scope_url": f.affected_url}
            acceptance = (
                "Meta description exists and summarizes content truthfully.",
                "No duplication across similar pages where avoidable.",
            )
            validation = (
                "Fetch head and confirm description tag presence.",
                "Ensure no regressions to robots/indexability.",
            )
            return title, objective, changes, acceptance, validation, risk
        if ft == SiteFindingType.broken_internal_link:
            title = "Fix broken internal link"
            objective = "Update or remove broken internal links to valid targets; add redirects where appropriate."
            changes = {"actions": ["fix_internal_link", "add_redirect_if_needed"], "scope_url": f.affected_url}
            acceptance = (
                "No 4xx/5xx for updated links.",
                "No redirect loops introduced.",
            )
            validation = (
                "Re-crawl updated links.",
                "Check redirect response chain depth <= 1.",
            )
            return title, objective, changes, acceptance, validation, risk
        if ft == SiteFindingType.redirect_chain:
            title = "Resolve redirect chain"
            objective = "Simplify redirect paths to at most one hop; update source links to final destinations."
            changes = {"actions": ["update_links", "adjust_redirects"], "scope_url": f.affected_url}
            acceptance = (
                "No chain over a single redirect.",
                "Final URL returns 200 where expected.",
            )
            validation = (
                "Check redirect depth is <= 1.",
                "Verify canonical and hreflang unaffected.",
            )
            return title, objective, changes, acceptance, validation, risk
        if ft == SiteFindingType.site_unavailable:
            title = "Restore site availability"
            objective = "Investigate outage, roll back or fix configuration, and restore HTTP 200 for key pages."
            changes = {"actions": ["triage_outage", "restore_availability"], "scope": "site"}
            acceptance = (
                "Health checks pass with HTTP 200.",
                "Error rate below threshold.",
            )
            validation = (
                "Run availability checks post-fix.",
                "Verify no new critical errors introduced.",
            )
            return title, objective, changes, acceptance, validation, risk
        if ft in (SiteFindingType.security_header_issue, SiteFindingType.mixed_content, SiteFindingType.certificate_warning):
            title = "Address security header / mixed content issue"
            objective = "Enable required security headers and eliminate mixed content without weakening security posture."
            changes = {"actions": ["configure_security_headers", "fix_mixed_content"], "scope_url": f.affected_url}
            acceptance = (
                "Security headers present (CSP, HSTS, X-Frame-Options, X-Content-Type-Options).",
                "No mixed content warnings on target pages.",
            )
            validation = (
                "Security scan summaries show compliance.",
                "Manual check for warnings in console.",
            )
            return title, objective, changes, acceptance, validation, risk
        if ft in (SiteFindingType.poor_lcp, SiteFindingType.page_too_large, SiteFindingType.render_blocking_resource):
            title = "Improve page performance and render path"
            objective = "Reduce LCP and remove render-blocking resources by optimizing critical CSS/JS and caching."
            changes = {"actions": ["inline_critical_css", "defer_noncritical_js", "enable_caching"], "scope_url": f.affected_url}
            acceptance = (
                "LCP improves on affected pages.",
                "No layout shifts introduced.",
            )
            validation = (
                "Collect CWV summary post-change.",
                "Audit with performance tool and verify budgets.",
            )
            return title, objective, changes, acceptance, validation, risk
        # Default: no task blueprint
        return None, None, {}, tuple(), tuple(), risk

    def _recommended_action_for_finding(self, ft: SiteFindingType) -> str:
        mapping = {
            SiteFindingType.image_unoptimized: "Optimize images and enable lazy loading.",
            SiteFindingType.image_oversized: "Resize and compress large images.",
            SiteFindingType.missing_title: "Add a unique, descriptive title tag.",
            SiteFindingType.missing_meta_description: "Add an accurate meta description.",
            SiteFindingType.broken_internal_link: "Update or remove broken links; add redirects if appropriate.",
            SiteFindingType.redirect_chain: "Simplify redirects and update source links.",
            SiteFindingType.site_unavailable: "Restore service and investigate root cause.",
            SiteFindingType.security_header_issue: "Enable required security headers.",
            SiteFindingType.poor_lcp: "Optimize critical rendering path and assets.",
        }
        return mapping.get(ft, "Investigate and remediate per best practices.")

    def _approval_required_for_task_blueprint(self, f: SiteFinding, risk: RiskLevel) -> bool:
        if risk in (RiskLevel.high, RiskLevel.critical):
            return True
        if f.finding_type in (SiteFindingType.security_header_issue, SiteFindingType.mixed_content, SiteFindingType.certificate_warning):
            return True
        # Robots or canonical strategy changes would need approval, but not created here.
        return False

    def _auto_dispatch_eligible(self, cfg: SiteOperationsProjectConfig, risk: RiskLevel, approval_required: bool) -> bool:
        if approval_required:
            return False
        if risk == RiskLevel.low:
            return cfg.automatic_low_risk_fixes_enabled
        if risk == RiskLevel.medium:
            return cfg.automatic_medium_risk_fixes_enabled
        return False

    # ---------------------------
    # Safe Views
    # ---------------------------
    def _safe_finding_view(self, f: SiteFinding) -> Mapping[str, Any]:
        return {
            "finding_id": f.finding_id,
            "type": f.finding_type.value,
            "severity": f.severity.name,
            "title": f.title,
            "summary": f.safe_summary,
            "affected_url": f.affected_url,
            "first_seen_at": f.first_seen_at.isoformat(),
            "last_seen_at": f.last_seen_at.isoformat(),
            "occurrence_count": f.occurrence_count,
            "recommended_action": f.recommended_action,
            "auto_fix_eligible": f.auto_fix_eligible,
        }

    def _safe_task_view(self, t: SiteTaskCandidate) -> Mapping[str, Any]:
        return {
            "task_id": t.task_id,
            "title": t.title,
            "objective": t.objective,
            "risk_level": t.risk_level.name,
            "approval_required": t.approval_required,
            "auto_dispatch_eligible": t.auto_dispatch_eligible,
            "estimated_effort": t.estimated_effort,
            "estimated_cost": t.estimated_cost,
            "acceptance_criteria": list(t.acceptance_criteria),
            "validation_requirements": list(t.validation_requirements),
        }

    def _summary_for_category(self, findings: Sequence[SiteFinding], types: Sequence[SiteFindingType]) -> Mapping[str, Any]:
        subset = [f for f in findings if f.finding_type in types]
        return {
            "enabled": True,
            "total": len(subset),
            "by_severity": {
                s.name: sum(1 for f in subset if f.severity == s)
                for s in SiteFindingSeverity
            },
        }

    def _next_actions_hint(self, project_id: str) -> Tuple[str, ...]:
        state = self._require_project(project_id)
        hints: List[str] = []
        with state.lock:
            if any(f.finding_type == SiteFindingType.site_unavailable for f in state.findings.values()):
                hints.append("Escalate incident for site availability and pause non-urgent changes.")
            if any(f.finding_type in (SiteFindingType.image_unoptimized, SiteFindingType.image_oversized) for f in state.findings.values()):
                hints.append("Batch image optimization across high-traffic pages.")
            if any(t.status == DevTaskStatus.awaiting_approval for t in state.tasks.values()):
                hints.append("Review and approve pending safe technical tasks.")
        if not hints:
            hints.append("Continue regular health, performance, and SEO monitoring.")
        return tuple(hints)

    def _find_project_by_task(self, task_id: str) -> Optional[_ProjectState]:
        with self._lock:
            for st in self._projects.values():
                with st.lock:
                    if task_id in st.tasks:
                        return st
        return None


# ==========================
# Public helper functions
# ==========================

def build_site_operations_manager(config: SiteOperationsConfig, dependencies: Optional[Mapping[str, Any]] = None) -> SiteOperationsManager:
    deps_obj: Optional[_Dependencies] = None
    if dependencies is not None:
        # Map provided dependencies to _Dependencies safely
        deps_obj = _Dependencies(
            clock=dependencies.get("clock", DefaultClock()),
            id_gen=dependencies.get("id_gen", DeterministicIDGenerator()),
            event_sink=dependencies.get("event_sink"),
            memory_manager=dependencies.get("memory_manager"),
            dev_supervisor=dependencies.get("dev_supervisor"),
            budget_evaluator=dependencies.get("budget_evaluator"),
            approval_store=dependencies.get("approval_store"),
        )
    return SiteOperationsManager(config=config, dependencies=deps_obj)


def site_operations_status(manager: SiteOperationsManager) -> Mapping[str, Any]:
    return manager.status()
