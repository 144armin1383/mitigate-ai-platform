from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set, Tuple


@dataclass(frozen=True)
class MissionSpec:
    """Immutable specification for a mission before IDs are assigned.

    The key is a stable identifier for the mission category (e.g., "database", "api").
    Dependencies are expressed using these keys and later translated to mission IDs
    after a stable topological ordering is computed.
    """

    key: str
    title: str
    category: str
    priority: str
    depends_on_keys: Tuple[str, ...] = field(default_factory=tuple)


class AIPlanner:
    """Deterministic AI Planner that converts a high-level request into
    an ordered execution plan composed of autonomous missions.

    - Deterministic planning and JSON output
    - Stable mission ordering
    - Dependency preservation and validation
    - Duplicate mission elimination
    - No execution of missions; only plan generation
    """

    # Stable, total ordering over mission categories to tie-break topological sort
    _TYPE_ORDER: Tuple[str, ...] = (
        "database",
        "backend",
        "api",
        "security",
        "frontend",
        "testing",
        "deployment",
        "documentation",
    )

    # Priority mapping for deterministic assignment
    _PRIORITY_BY_TYPE: Dict[str, str] = {
        "database": "high",
        "backend": "high",
        "api": "high",
        "security": "high",
        "frontend": "normal",
        "testing": "high",
        "deployment": "normal",
        "documentation": "low",
    }

    def plan(self, request: str) -> Dict[str, List[Dict[str, object]]]:
        """Create a deterministic execution plan for the given request.

        Returns a dictionary with a single key "missions" mapping to a list of mission
        objects. Each mission contains: id, title, category, priority, depends_on.
        """
        text = self._normalize(request)
        components = self._detect_components(text)
        mission_specs = self._build_mission_specs(components)

        ordered_specs = self._toposort_specs(mission_specs)

        # Assign sequential mission IDs in the sorted order to ensure dependencies
        # always refer to earlier missions.
        id_by_key: Dict[str, str] = {}
        missions: List[Dict[str, object]] = []

        for idx, spec in enumerate(ordered_specs, start=1):
            mission_id = f"M{idx}"
            id_by_key[spec.key] = mission_id

        for spec in ordered_specs:
            depends_ids = [id_by_key[d] for d in self._sorted_by_type(spec.depends_on_keys)]
            missions.append(
                {
                    "id": id_by_key[spec.key],
                    "title": spec.title,
                    "category": spec.category,
                    "priority": spec.priority,
                    "depends_on": depends_ids,
                }
            )

        # Validate that all dependencies point to earlier missions
        self._validate_dependencies(missions)

        return {"missions": missions}

    def to_json(self, plan: Dict[str, object]) -> str:
        """Return deterministic JSON string for a plan."""
        return json.dumps(plan, sort_keys=True, separators=(",", ":"))

    # ----------------------- Internal helpers ----------------------- #

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r"\s+", " ", text or "").strip().lower()

    def _detect_components(self, text: str) -> Dict[str, bool]:
        """Detect implied components from the high-level request.

        Detection rules are keyword-based and deterministic. At most one of
        backend/api is selected; API takes precedence when both are implied.
        Testing, deployment, and documentation are always included to ensure
        comprehensive planning and compliance with dependency rules.
        """
        def has_any(patterns: Iterable[str]) -> bool:
            return any(p in text for p in patterns)

        frontend_terms = (
            "ui",
            "user interface",
            "page",
            "form",
            "dashboard",
            "frontend",
            "client",
            "react",
            "view",
            "layout",
            "button",
            "component",
            "admin panel",
            "screen",
            "modal",
        )
        api_terms = ("api", "endpoint", "endpoints", "webhook", "rest", "graphql")
        backend_terms = (
            "backend",
            "server",
            "service",
            "job",
            "worker",
            "cron",
            "business logic",
            "server-side",
        )
        db_terms = (
            "save",
            "persist",
            "persistence",
            "database",
            "db ",
            " schema",
            "migration",
            "table",
            "model",
            "record",
            "storage",
        )
        security_terms = (
            "auth",
            "authentication",
            "authorize",
            "authorization",
            "oauth",
            "jwt",
            "encrypt",
            "encryption",
            "security",
            "csrf",
            "xss",
            "acl",
            "mfa",
            "2fa",
        )
        deploy_terms = (
            "deploy",
            "deployment",
            "container",
            "docker",
            "kubernetes",
            "helm",
            "cloud",
            "production",
            "ci/cd",
            "pipeline",
            "release",
        )
        docs_terms = (
            "doc",
            "docs",
            "documentation",
            "readme",
            "guide",
            "manual",
            "spec",
            "specification",
            "changelog",
        )

        has_frontend = has_any(frontend_terms)
        has_api = has_any(api_terms)
        has_backend = has_any(backend_terms)
        has_db = has_any(db_terms)
        has_security = has_any(security_terms)
        has_deploy = has_any(deploy_terms)
        has_docs = has_any(docs_terms)

        # If either API or backend is implied, prefer API when both are present.
        selected_backend_kind: Optional[str] = None
        if has_api:
            selected_backend_kind = "api"
        elif has_backend:
            selected_backend_kind = "backend"

        # Always include testing; include deployment and docs to maintain
        # consistent comprehensive planning. This ensures dependency-related
        # acceptance criteria are met regardless of wording.
        include_testing = True
        include_deployment = True or has_deploy  # Always include deterministically
        include_docs = True  # Always include deterministically

        return {
            "frontend": bool(has_frontend),
            "database": bool(has_db),
            "security": bool(has_security),
            "backend_kind": selected_backend_kind,  # "api" | "backend" | None
            "testing": include_testing,
            "deployment": include_deployment,
            "documentation": include_docs,
        }

    def _build_mission_specs(self, components: Dict[str, object]) -> List[MissionSpec]:
        present: Set[str] = set()
        backend_kind = components.get("backend_kind")  # type: ignore[assignment]

        if components.get("database"):
            present.add("database")
        if backend_kind in ("api", "backend"):
            present.add(backend_kind)  # type: ignore[arg-type]
        if components.get("frontend"):
            present.add("frontend")
        if components.get("security"):
            present.add("security")
        if components.get("testing"):
            present.add("testing")
        if components.get("deployment"):
            present.add("deployment")
        if components.get("documentation"):
            present.add("documentation")

        # Deduplicate implicitly by using a set. Build deterministic dependencies by keys.
        deps_by_key: Dict[str, Set[str]] = {k: set() for k in present}

        # database -> backend/api
        if "database" in present and "api" in present:
            deps_by_key["api"].add("database")
        if "database" in present and "backend" in present:
            deps_by_key["backend"].add("database")

        # backend/api -> frontend
        if "frontend" in present and "api" in present:
            deps_by_key["frontend"].add("api")
        if "frontend" in present and "backend" in present and "api" not in present:
            deps_by_key["frontend"].add("backend")

        # security depends on backend/api and database when present
        if "security" in present and "api" in present:
            deps_by_key["security"].add("api")
        if "security" in present and "backend" in present and "api" not in present:
            deps_by_key["security"].add("backend")
        if "security" in present and "database" in present:
            deps_by_key["security"].add("database")

        # testing depends on all implementation missions that exist
        for impl in ("database", "api", "backend", "frontend", "security"):
            if impl in present and "testing" in present:
                deps_by_key["testing"].add(impl)

        # deployment depends on testing
        if "deployment" in present and "testing" in present:
            deps_by_key["deployment"].add("testing")

        # documentation depends on testing
        if "documentation" in present and "testing" in present:
            deps_by_key["documentation"].add("testing")

        specs: List[MissionSpec] = []
        for key in self._sorted_by_type(present):
            specs.append(
                MissionSpec(
                    key=key,
                    title=self._title_for(key),
                    category=key,
                    priority=self._PRIORITY_BY_TYPE.get(key, "normal"),
                    depends_on_keys=tuple(self._sorted_by_type(deps_by_key.get(key, set()))),
                )
            )
        return specs

    def _toposort_specs(self, specs: List[MissionSpec]) -> List[MissionSpec]:
        """Stable topological sort with deterministic tie-breaking using _TYPE_ORDER.

        Edges are derived from depends_on_keys as (dep -> node).
        """
        key_to_spec: Dict[str, MissionSpec] = {s.key: s for s in specs}
        present_keys: Set[str] = set(key_to_spec)

        # Build adjacency and indegree
        adj: Dict[str, Set[str]] = {k: set() for k in present_keys}
        indeg: Dict[str, int] = {k: 0 for k in present_keys}

        for s in specs:
            for dep in s.depends_on_keys:
                if dep not in present_keys:
                    raise ValueError(f"Invalid dependency '{dep}' for mission '{s.key}'")
                if s.key not in adj[dep]:
                    adj[dep].add(s.key)
                    indeg[s.key] += 1

        # Initialize queue with zero-indegree nodes in deterministic order
        zero: List[str] = [k for k, d in indeg.items() if d == 0]
        zero.sort(key=self._type_index)  # deterministic

        order: List[str] = []
        while zero:
            k = zero.pop(0)  # pop front deterministically
            order.append(k)
            for nxt in sorted(adj[k], key=self._type_index):
                indeg[nxt] -= 1
                if indeg[nxt] == 0:
                    # Insert maintaining order by type index
                    zero.append(nxt)
                    zero.sort(key=self._type_index)

        if len(order) != len(present_keys):
            # Cycle detected or unresolved dependencies
            missing = present_keys - set(order)
            raise ValueError(f"Cyclic or unresolved dependencies among: {sorted(missing)}")

        return [key_to_spec[k] for k in order]

    def _validate_dependencies(self, missions: List[Dict[str, object]]) -> None:
        """Ensure each dependency references an existing earlier mission."""
        id_to_index: Dict[str, int] = {m["id"]: i for i, m in enumerate(missions)}
        for i, m in enumerate(missions):
            deps = m.get("depends_on", [])
            if not isinstance(deps, list):
                raise ValueError("depends_on must be a list")
            for dep_id in deps:
                if dep_id not in id_to_index:
                    raise ValueError(f"Unknown dependency id: {dep_id}")
                if id_to_index[dep_id] >= i:
                    raise ValueError(
                        f"Dependency {dep_id} for mission {m['id']} does not precede it in order"
                    )

    def _title_for(self, key: str) -> str:
        titles = {
            "database": "Design and implement database schema and migrations",
            "backend": "Implement backend services and business logic",
            "api": "Design and implement API endpoints",
            "security": "Implement authentication, authorization, and security controls",
            "frontend": "Build user interface components and pages",
            "testing": "Create and run automated tests (unit, integration, e2e)",
            "deployment": "Prepare CI/CD and deployment configuration",
            "documentation": "Write and update project documentation",
        }
        return titles.get(key, key.capitalize())

    def _type_index(self, key: str) -> int:
        try:
            return self._TYPE_ORDER.index(key)
        except ValueError:
            # Unknown types are ordered after known ones but deterministically by name
            return len(self._TYPE_ORDER) + hash(key) % 1000

    def _sorted_by_type(self, items: Iterable[str]) -> List[str]:
        return sorted(items, key=self._type_index)


__all__ = ["AIPlanner", "MissionSpec"]
