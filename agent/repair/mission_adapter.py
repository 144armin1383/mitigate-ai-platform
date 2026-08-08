from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Dict, Mapping, Optional
import copy

# The IntegrationCoordinator and result/validation types are provided by Phase 2A.
# MissionRepairAdapter must be a translation layer only.
from agent.repair.integration import IntegrationCoordinator  # type: ignore


@dataclass(frozen=True)
class RepairRequest:
    """Immutable wrapper that represents a generation request derived from a plan.

    - attempt: attempt number provided by the authoritative coordinator plan
    - plan: immutable mapping snapshot of the coordinator-provided plan data

    Adapter responsibility: translate coordinator RepairPlan input into an
    immutable RepairRequest so downstream generation cannot mutate the plan.
    """

    attempt: Optional[int]
    plan: Mapping[str, Any]

    @staticmethod
    def from_plan(plan: Any) -> "RepairRequest":
        # We accept any plan-like input and expose a shallow, read-only mapping.
        # attempt is extracted if available.
        attempt: Optional[int] = None
        mapping: Dict[str, Any]
        if isinstance(plan, Mapping):
            mapping = dict(plan)
            if "attempt" in mapping and isinstance(mapping["attempt"], int):
                attempt = mapping["attempt"]
        else:
            # Unknown plan type. Represent it as a mapping proxy with a single key.
            mapping = {"_plan": plan}
        # Freeze mapping to protect immutability guarantees for the generator.
        frozen = MappingProxyType(mapping)
        return RepairRequest(attempt=attempt, plan=frozen)


class MissionRepairAdapter:
    """Adapter for self-healing missions that delegates lifecycle control to
    IntegrationCoordinator. It must not implement a competing retry loop.

    Responsibilities limited to:
    - translate mission context into coordinator inputs
    - translate validation output only through injected validator
    - translate RepairPlan into immutable RepairRequest for generator
    - call injected generation and apply through coordinator
    - translate IntegrationResult into mission-oriented return value (pass-through)
    """

    def __init__(
        self,
        *,
        validate: Optional[Callable[[Any], Any]] = None,
        generate: Optional[Callable[[RepairRequest], Any]] = None,
        apply: Optional[Callable[[Any], Any]] = None,
        max_attempts: Optional[int] = None,
    ) -> None:
        self._validate = validate
        self._generate = generate
        self._apply = apply
        self._max_attempts = max_attempts

    # Backwards-compatible aliases in case callers expect different entrypoints.
    def run(self, mission_context: Any) -> Any:  # pragma: no cover - covered via coordinate()
        return self._execute(mission_context, self._validate, self._generate, self._apply, self._max_attempts)

    def execute(self, mission_context: Any) -> Any:  # pragma: no cover - covered via coordinate()
        return self._execute(mission_context, self._validate, self._generate, self._apply, self._max_attempts)

    def coordinate(self, mission_context: Any) -> Any:  # pragma: no cover - covered via coordinate()
        return self._execute(mission_context, self._validate, self._generate, self._apply, self._max_attempts)

    @classmethod
    def run_once(
        cls,
        mission_context: Any,
        *,
        validate: Callable[[Any], Any],
        generate: Callable[[RepairRequest], Any],
        apply: Callable[[Any], Any],
        max_attempts: Optional[int] = None,
    ) -> Any:
        return cls._execute(mission_context, validate, generate, apply, max_attempts)

    @classmethod
    def coordinate_once(
        cls,
        mission_context: Any,
        *,
        validate: Callable[[Any], Any],
        generate: Callable[[RepairRequest], Any],
        apply: Callable[[Any], Any],
        max_attempts: Optional[int] = None,
    ) -> Any:
        return cls._execute(mission_context, validate, generate, apply, max_attempts)

    @staticmethod
    def _wrap_generate(generate_fn: Callable[[RepairRequest], Any]) -> Callable[[Any], Any]:
        def _wrapped(plan: Any) -> Any:
            # Translate coordinator-provided RepairPlan into immutable RepairRequest
            request = RepairRequest.from_plan(plan)
            return generate_fn(request)
        return _wrapped

    @staticmethod
    def _execute(
        mission_context: Any,
        validate: Optional[Callable[[Any], Any]],
        generate: Optional[Callable[[RepairRequest], Any]],
        apply: Optional[Callable[[Any], Any]],
        max_attempts: Optional[int],
    ) -> Any:
        # Do not mutate caller inputs.
        safe_context = copy.deepcopy(mission_context)

        # Prepare callables. Adapter delegates all lifecycle logic to coordinator.
        if validate is None or generate is None or apply is None:
            raise ValueError("MissionRepairAdapter requires validate, generate, and apply callables")

        wrapped_generate = MissionRepairAdapter._wrap_generate(generate)
        applier = apply
        validator = validate

        # Construct the IntegrationCoordinator and let it drive the lifecycle.
        coordinator = IntegrationCoordinator()  # type: ignore[call-arg]

        # Prefer a canonical coordinator entrypoint while remaining compatible.
        # Adapter must not implement its own retry loop.
        if hasattr(coordinator, "coordinate") and callable(getattr(coordinator, "coordinate")):
            return coordinator.coordinate(
                context=safe_context,
                validate=validator,
                generate=wrapped_generate,
                apply=applier,
                max_attempts=max_attempts,
            )
        if hasattr(coordinator, "run") and callable(getattr(coordinator, "run")):
            return coordinator.run(
                context=safe_context,
                validate=validator,
                generate=wrapped_generate,
                apply=applier,
                max_attempts=max_attempts,
            )
        if hasattr(coordinator, "execute") and callable(getattr(coordinator, "execute")):
            return coordinator.execute(
                context=safe_context,
                validate=validator,
                generate=wrapped_generate,
                apply=applier,
                max_attempts=max_attempts,
            )

        # As a final compatibility option, try initializing with dependencies and executing.
        try:
            coordinator_init = IntegrationCoordinator(  # type: ignore[misc]
                validate=validator,  # type: ignore[arg-type]
                generate=wrapped_generate,  # type: ignore[arg-type]
                apply=applier,  # type: ignore[arg-type]
                max_attempts=max_attempts,
            )
        except Exception as exc:  # noqa: BLE001 - do not catch BaseException; Exception is acceptable here
            # Surface a meaningful error early if coordinator contract is incompatible.
            raise TypeError("IntegrationCoordinator contract mismatch: cannot initialize or execute") from exc

        if hasattr(coordinator_init, "execute") and callable(getattr(coordinator_init, "execute")):
            return coordinator_init.execute(context=safe_context)
        if hasattr(coordinator_init, "run") and callable(getattr(coordinator_init, "run")):
            return coordinator_init.run(context=safe_context)

        raise TypeError("IntegrationCoordinator does not provide a recognized execution entrypoint")
