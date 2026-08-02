from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Mapping, Optional, Protocol, TypedDict, runtime_checkable


class RequestEstimate(TypedDict, total=True):
    project_id: str
    request_id: str
    task_type: str
    provider_id: str
    model_id: str
    estimated_input_tokens: int
    requested_output_tokens: int
    estimated_cost: Optional[float]
    cost_currency: str
    request_timestamp: datetime


class DecisionResult(TypedDict, total=True):
    allowed: bool
    warning: bool
    blocked_reason: Optional[str]
    pricing_known: bool
    remaining_daily_budget: Optional[float]
    remaining_monthly_budget: Optional[float]
    remaining_daily_tokens: Optional[int]
    remaining_monthly_tokens: Optional[int]
    evaluated_at: str
    project_id: str
    request_id: str


@runtime_checkable
class BudgetStore(Protocol):
    def get_project_budget(self, project_id: str) -> Optional[Mapping[str, Any]]:
        """Return a mapping with project's budget configuration or None if not configured."""
        ...


@runtime_checkable
class UsageLedger(Protocol):
    def usage_summary(self, project_id: str, start: datetime, end: datetime) -> Mapping[str, Optional[float | int]]:
        """Return a usage summary mapping with keys: 'tokens' (int or None) and 'cost' (float or None)."""
        ...


@runtime_checkable
class ProjectResolver(Protocol):
    def is_known_project(self, project_id: str) -> bool:
        ...

    # Optional, if provided will be used for additional cross-project validation
    def is_valid_reference(self, project_id: str, request: Mapping[str, Any]) -> bool:  # pragma: no cover - optional
        ...


@runtime_checkable
class ModelResolver(Protocol):
    def is_valid_provider(self, provider_id: str) -> bool:
        ...

    def is_valid_model(self, provider_id: str, model_id: str) -> bool:
        ...


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime:
        ...


@dataclass(frozen=True)
class _Limits:
    per_request_max_input_tokens: Optional[int]
    per_request_max_output_tokens: Optional[int]
    per_request_max_cost: Optional[float]
    daily_token_limit: Optional[int]
    monthly_token_limit: Optional[int]
    daily_budget_limit: Optional[float]
    monthly_budget_limit: Optional[float]
    soft_warning_percent: Optional[float]
    unknown_pricing_policy: str


def _iso_now(clock: Optional[Clock]) -> str:
    now = clock.now() if clock else datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc).isoformat()


def _start_of_day_utc(dt: datetime) -> datetime:
    dtu = dt.astimezone(timezone.utc)
    return dtu.replace(hour=0, minute=0, second=0, microsecond=0)


def _start_of_next_day_utc(dt: datetime) -> datetime:
    return _start_of_day_utc(dt) + timedelta(days=1)


def _start_of_month_utc(dt: datetime) -> datetime:
    dtu = dt.astimezone(timezone.utc)
    return dtu.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _start_of_next_month_utc(dt: datetime) -> datetime:
    dtu = dt.astimezone(timezone.utc)
    year = dtu.year + (1 if dtu.month == 12 else 0)
    month = 1 if dtu.month == 12 else dtu.month + 1
    return dtu.replace(year=year, month=month, day=1, hour=0, minute=0, second=0, microsecond=0)


class ProviderBudgetLimitEvaluator:
    def __init__(
        self,
        budget_store: BudgetStore,
        usage_ledger: UsageLedger,
        project_resolver: Optional[ProjectResolver] = None,
        model_resolver: Optional[ModelResolver] = None,
        clock: Optional[Clock] = None,
    ) -> None:
        self._budget_store = budget_store
        self._ledger = usage_ledger
        self._project_resolver = project_resolver
        self._model_resolver = model_resolver
        self._clock = clock

    def remaining_limits(self, project_id: str, timestamp: Optional[datetime] = None) -> Dict[str, Optional[float | int]]:
        ts = timestamp or (self._clock.now() if self._clock else datetime.now(timezone.utc))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        ts = ts.astimezone(timezone.utc)

        cfg_raw = self._budget_store.get_project_budget(project_id) or {}
        limits = self._parse_limits(cfg_raw)

        day_start = _start_of_day_utc(ts)
        day_end = _start_of_next_day_utc(ts)
        mon_start = _start_of_month_utc(ts)
        mon_end = _start_of_next_month_utc(ts)

        daily_summary = self._safe_summary(project_id, day_start, day_end)
        monthly_summary = self._safe_summary(project_id, mon_start, mon_end)

        remaining_daily_tokens: Optional[int] = None
        remaining_monthly_tokens: Optional[int] = None
        remaining_daily_budget: Optional[float] = None
        remaining_monthly_budget: Optional[float] = None

        if limits.daily_token_limit is not None and isinstance(daily_summary.get("tokens"), int):
            used = int(daily_summary["tokens"])  # type: ignore[index]
            remaining_daily_tokens = max(limits.daily_token_limit - used, 0)
        if limits.monthly_token_limit is not None and isinstance(monthly_summary.get("tokens"), int):
            used_m = int(monthly_summary["tokens"])  # type: ignore[index]
            remaining_monthly_tokens = max(limits.monthly_token_limit - used_m, 0)

        if limits.daily_budget_limit is not None and isinstance(daily_summary.get("cost"), (int, float)):
            used_c = float(daily_summary["cost"])  # type: ignore[index]
            remaining_daily_budget = max(limits.daily_budget_limit - used_c, 0.0)
        if limits.monthly_budget_limit is not None and isinstance(monthly_summary.get("cost"), (int, float)):
            used_cm = float(monthly_summary["cost"])  # type: ignore[index]
            remaining_monthly_budget = max(limits.monthly_budget_limit - used_cm, 0.0)

        return {
            "remaining_daily_tokens": remaining_daily_tokens,
            "remaining_monthly_tokens": remaining_monthly_tokens,
            "remaining_daily_budget": remaining_daily_budget,
            "remaining_monthly_budget": remaining_monthly_budget,
        }

    def check_request(self, project_id: str, request_estimate: Mapping[str, Any]) -> DecisionResult:
        # Validate request structure and basic semantics
        validation_error = self._validate_request_shape_and_values(project_id, request_estimate)
        if validation_error is not None:
            return self._blocked_result(project_id, request_estimate.get("request_id", ""), validation_error, pricing_known=self._is_pricing_known(request_estimate))

        # Validate project existence if resolver provided
        if self._project_resolver is not None:
            if not self._project_resolver.is_known_project(project_id):
                return self._blocked_result(project_id, request_estimate["request_id"], "unknown_project", pricing_known=self._is_pricing_known(request_estimate))
            if hasattr(self._project_resolver, "is_valid_reference"):
                try:
                    ref_ok = self._project_resolver.is_valid_reference(project_id, request_estimate)  # type: ignore[attr-defined]
                except Exception:
                    ref_ok = False
                if not ref_ok:
                    return self._blocked_result(project_id, request_estimate["request_id"], "cross_project_reference", pricing_known=self._is_pricing_known(request_estimate))

        # Validate provider and model when resolver configured
        if self._model_resolver is not None:
            provider_id = str(request_estimate["provider_id"])  # already validated exists
            model_id = str(request_estimate["model_id"])  # already validated exists
            try:
                if hasattr(self._model_resolver, "is_valid_provider"):
                    if not self._model_resolver.is_valid_provider(provider_id):
                        return self._blocked_result(project_id, request_estimate["request_id"], "invalid_provider_or_model", pricing_known=self._is_pricing_known(request_estimate))
                if not self._model_resolver.is_valid_model(provider_id, model_id):
                    return self._blocked_result(project_id, request_estimate["request_id"], "invalid_provider_or_model", pricing_known=self._is_pricing_known(request_estimate))
            except Exception:
                return self._blocked_result(project_id, request_estimate["request_id"], "invalid_provider_or_model", pricing_known=self._is_pricing_known(request_estimate))

        # Load configuration
        cfg_raw = self._budget_store.get_project_budget(project_id) or {}
        limits = self._parse_limits(cfg_raw)

        # If there is no configuration at all (missing budgets), allow request per policy
        if not cfg_raw:
            return self._allowed_result(project_id, request_estimate, pricing_known=self._is_pricing_known(request_estimate), warning=False)

        # Extract estimates
        est_in = int(request_estimate["estimated_input_tokens"])  # validated non-negative int
        est_out = int(request_estimate["requested_output_tokens"])  # validated non-negative int
        est_cost_opt = request_estimate["estimated_cost"]  # Optional[float]
        ts: datetime = request_estimate["request_timestamp"]

        # Evaluation order of hard limits
        # 1. Per-request input token limit
        if limits.per_request_max_input_tokens is not None and est_in > limits.per_request_max_input_tokens:
            return self._blocked_result(project_id, request_estimate["request_id"], "per_request_input_token_limit_exceeded", pricing_known=self._is_pricing_known(request_estimate))

        # 2. Per-request output token limit
        if limits.per_request_max_output_tokens is not None and est_out > limits.per_request_max_output_tokens:
            return self._blocked_result(project_id, request_estimate["request_id"], "per_request_output_token_limit_exceeded", pricing_known=self._is_pricing_known(request_estimate))

        # 3. Per-request budget
        if est_cost_opt is not None and limits.per_request_max_cost is not None and float(est_cost_opt) > limits.per_request_max_cost:
            return self._blocked_result(project_id, request_estimate["request_id"], "per_request_budget_exceeded", pricing_known=True)

        # Prepare periods and usage summaries for subsequent checks
        day_start = _start_of_day_utc(ts)
        day_end = _start_of_next_day_utc(ts)
        mon_start = _start_of_month_utc(ts)
        mon_end = _start_of_next_month_utc(ts)

        daily_summary = self._safe_summary(project_id, day_start, day_end)
        monthly_summary = self._safe_summary(project_id, mon_start, mon_end)

        add_tokens = est_in + est_out

        # 4. Daily token limit
        if limits.daily_token_limit is not None and isinstance(daily_summary.get("tokens"), int):
            used_tokens = int(daily_summary["tokens"])  # type: ignore[index]
            if used_tokens + add_tokens > limits.daily_token_limit:
                return self._blocked_result(project_id, request_estimate["request_id"], "daily_token_limit_exceeded", pricing_known=self._is_pricing_known(request_estimate))

        # 5. Monthly token limit
        if limits.monthly_token_limit is not None and isinstance(monthly_summary.get("tokens"), int):
            used_tokens_m = int(monthly_summary["tokens"])  # type: ignore[index]
            if used_tokens_m + add_tokens > limits.monthly_token_limit:
                return self._blocked_result(project_id, request_estimate["request_id"], "monthly_token_limit_exceeded", pricing_known=self._is_pricing_known(request_estimate))

        # 6. Daily budget
        if est_cost_opt is not None and limits.daily_budget_limit is not None and isinstance(daily_summary.get("cost"), (int, float)):
            used_cost = float(daily_summary["cost"])  # type: ignore[index]
            if used_cost + float(est_cost_opt) > limits.daily_budget_limit:
                return self._blocked_result(project_id, request_estimate["request_id"], "daily_budget_limit_exceeded", pricing_known=True)

        # 7. Monthly budget
        if est_cost_opt is not None and limits.monthly_budget_limit is not None and isinstance(monthly_summary.get("cost"), (int, float)):
            used_cost_m = float(monthly_summary["cost"])  # type: ignore[index]
            if used_cost_m + float(est_cost_opt) > limits.monthly_budget_limit:
                return self._blocked_result(project_id, request_estimate["request_id"], "monthly_budget_limit_exceeded", pricing_known=True)

        # 8. Unknown pricing policy
        pricing_known = est_cost_opt is not None
        unknown_policy_warning = False
        if not pricing_known:
            policy = limits.unknown_pricing_policy
            if policy == "block":
                return self._blocked_result(project_id, request_estimate["request_id"], "unknown_pricing_blocked", pricing_known=False)
            elif policy == "warn":
                unknown_policy_warning = True
            # 'allow' or missing: permit

        # 9. Soft warning threshold (non-blocking)
        warning = bool(unknown_policy_warning)
        if limits.soft_warning_percent is not None:
            pct = limits.soft_warning_percent
            if pct is not None and pct >= 0:
                # tokens daily
                if limits.daily_token_limit is not None and isinstance(daily_summary.get("tokens"), int):
                    used = int(daily_summary["tokens"])  # type: ignore[index]
                    projected = used + add_tokens
                    threshold = (limits.daily_token_limit * pct) / 100.0
                    if projected >= threshold and projected <= limits.daily_token_limit:
                        warning = True
                # tokens monthly
                if limits.monthly_token_limit is not None and isinstance(monthly_summary.get("tokens"), int):
                    usedm = int(monthly_summary["tokens"])  # type: ignore[index]
                    projectedm = usedm + add_tokens
                    thresholdm = (limits.monthly_token_limit * pct) / 100.0
                    if projectedm >= thresholdm and projectedm <= limits.monthly_token_limit:
                        warning = True
                # budget daily
                if pricing_known and limits.daily_budget_limit is not None and isinstance(daily_summary.get("cost"), (int, float)):
                    usedc = float(daily_summary["cost"])  # type: ignore[index]
                    projectedc = usedc + float(est_cost_opt)  # type: ignore[arg-type]
                    thresholdc = (limits.daily_budget_limit * pct) / 100.0
                    if projectedc >= thresholdc and projectedc <= limits.daily_budget_limit:
                        warning = True
                # budget monthly
                if pricing_known and limits.monthly_budget_limit is not None and isinstance(monthly_summary.get("cost"), (int, float)):
                    usedcm = float(monthly_summary["cost"])  # type: ignore[index]
                    projectedcm = usedcm + float(est_cost_opt)  # type: ignore[arg-type]
                    thresholdcm = (limits.monthly_budget_limit * pct) / 100.0
                    if projectedcm >= thresholdcm and projectedcm <= limits.monthly_budget_limit:
                        warning = True

        # Prepare remaining fields (do not deduct current request to avoid fabricating usage)
        remain = self.remaining_limits(project_id, timestamp=ts)

        result: DecisionResult = {
            "allowed": True,
            "warning": warning,
            "blocked_reason": None,
            "pricing_known": pricing_known,
            "remaining_daily_budget": remain.get("remaining_daily_budget"),
            "remaining_monthly_budget": remain.get("remaining_monthly_budget"),
            "remaining_daily_tokens": remain.get("remaining_daily_tokens"),
            "remaining_monthly_tokens": remain.get("remaining_monthly_tokens"),
            "evaluated_at": _iso_now(self._clock),
            "project_id": project_id,
            "request_id": str(request_estimate["request_id"]),
        }
        return result

    # Internal helpers
    def _safe_summary(self, project_id: str, start: datetime, end: datetime) -> Mapping[str, Optional[float | int]]:
        try:
            summary = self._ledger.usage_summary(project_id, start, end)
        except Exception:
            return {"tokens": None, "cost": None}
        # Ensure keys exist
        tokens_val: Optional[int]
        cost_val: Optional[float]
        tv = summary.get("tokens")
        cv = summary.get("cost")
        tokens_val = int(tv) if isinstance(tv, int) else None
        cost_val = float(cv) if isinstance(cv, (int, float)) else None
        return {"tokens": tokens_val, "cost": cost_val}

    def _parse_limits(self, cfg_raw: Mapping[str, Any]) -> _Limits:
        per_req = cfg_raw.get("per_request") or {}
        daily = cfg_raw.get("daily") or {}
        monthly = cfg_raw.get("monthly") or {}
        soft_pct = cfg_raw.get("soft_warning_percent")
        unknown_policy = cfg_raw.get("unknown_pricing_policy", "allow")
        return _Limits(
            per_request_max_input_tokens=self._as_opt_int(per_req.get("max_input_tokens")),
            per_request_max_output_tokens=self._as_opt_int(per_req.get("max_output_tokens")),
            per_request_max_cost=self._as_opt_float(per_req.get("max_cost")),
            daily_token_limit=self._as_opt_int(daily.get("token_limit")),
            monthly_token_limit=self._as_opt_int(monthly.get("token_limit")),
            daily_budget_limit=self._as_opt_float(daily.get("budget_limit")),
            monthly_budget_limit=self._as_opt_float(monthly.get("budget_limit")),
            soft_warning_percent=self._as_opt_float(soft_pct),
            unknown_pricing_policy=str(unknown_policy if isinstance(unknown_policy, str) else "allow").lower(),
        )

    @staticmethod
    def _as_opt_int(v: Any) -> Optional[int]:
        if v is None:
            return None
        if isinstance(v, bool):  # exclude bools
            return None
        try:
            iv = int(v)
            if iv < 0:
                return None
            return iv
        except Exception:
            return None

    @staticmethod
    def _as_opt_float(v: Any) -> Optional[float]:
        if v is None:
            return None
        if isinstance(v, bool):
            return None
        try:
            fv = float(v)
            if fv < 0:
                return None
            return fv
        except Exception:
            return None

    def _is_pricing_known(self, request_estimate: Mapping[str, Any]) -> bool:
        return request_estimate.get("estimated_cost") is not None

    def _blocked_result(self, project_id: str, request_id: Any, reason: str, pricing_known: bool) -> DecisionResult:
        remain = self.remaining_limits(project_id)
        return {
            "allowed": False,
            "warning": False,
            "blocked_reason": reason,
            "pricing_known": pricing_known,
            "remaining_daily_budget": remain.get("remaining_daily_budget"),
            "remaining_monthly_budget": remain.get("remaining_monthly_budget"),
            "remaining_daily_tokens": remain.get("remaining_daily_tokens"),
            "remaining_monthly_tokens": remain.get("remaining_monthly_tokens"),
            "evaluated_at": _iso_now(self._clock),
            "project_id": project_id,
            "request_id": str(request_id),
        }

    def _allowed_result(self, project_id: str, request_estimate: Mapping[str, Any], pricing_known: bool, warning: bool) -> DecisionResult:
        remain = self.remaining_limits(project_id, timestamp=request_estimate["request_timestamp"]) if "request_timestamp" in request_estimate else self.remaining_limits(project_id)
        return {
            "allowed": True,
            "warning": warning,
            "blocked_reason": None,
            "pricing_known": pricing_known,
            "remaining_daily_budget": remain.get("remaining_daily_budget"),
            "remaining_monthly_budget": remain.get("remaining_monthly_budget"),
            "remaining_daily_tokens": remain.get("remaining_daily_tokens"),
            "remaining_monthly_tokens": remain.get("remaining_monthly_tokens"),
            "evaluated_at": _iso_now(self._clock),
            "project_id": project_id,
            "request_id": str(request_estimate.get("request_id", "")),
        }

    def _validate_request_shape_and_values(self, project_id: str, req: Mapping[str, Any]) -> Optional[str]:
        # Unknown field rejection
        required_fields = {
            "project_id",
            "request_id",
            "task_type",
            "provider_id",
            "model_id",
            "estimated_input_tokens",
            "requested_output_tokens",
            "estimated_cost",
            "cost_currency",
            "request_timestamp",
        }
        unknown_keys = set(req.keys()) - required_fields
        if unknown_keys:
            return "unknown_fields"

        # Presence and basic type checks
        try:
            if str(req["project_id"]) != project_id:
                return "cross_project_reference"
            _ = str(req["request_id"])  # noqa: F841
            _ = str(req["task_type"])  # noqa: F841
            _ = str(req["provider_id"])  # noqa: F841
            _ = str(req["model_id"])  # noqa: F841
        except Exception:
            return "invalid_request"

        # Token estimates must be non-negative integers
        try:
            est_in = int(req["estimated_input_tokens"])  # type: ignore[arg-type]
            est_out = int(req["requested_output_tokens"])  # type: ignore[arg-type]
        except Exception:
            return "invalid_token_estimate"
        if est_in < 0 or est_out < 0:
            return "invalid_token_estimate"

        # estimated_cost must be non-negative or null
        est_cost = req.get("estimated_cost")
        if est_cost is not None:
            try:
                if float(est_cost) < 0:
                    return "invalid_estimated_cost"
            except Exception:
                return "invalid_estimated_cost"

        # request_timestamp must be timezone-aware UTC
        ts = req.get("request_timestamp")
        if not isinstance(ts, datetime):
            return "invalid_timestamp"
        if ts.tzinfo is None or ts.astimezone(timezone.utc).utcoffset() != timedelta(0):
            return "invalid_timestamp"

        return None
