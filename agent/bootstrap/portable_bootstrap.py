from __future__ import annotations

# Portable Bootstrap Core for MITIGATE AI
# - Python 3.12 compatible
# - Standard library only
# - No dynamic code execution, no subprocess
# - Provider-neutral, platform-neutral

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import json
import sys
import os
import re
from datetime import datetime, timezone


BOOTSTRAP_SCHEMA_VERSION = "1.0"
MEMORY_SCHEMA_VERSION = "1.0"
PROJECT_CONFIG_VERSION = "1.0"


class BootstrapStatus(str, Enum):
    VALIDATED = "validated"
    COMPLETED = "completed"
    FAILED = "failed"


class FailureCode(str, Enum):
    INVALID_BOOTSTRAP_CONFIG = "invalid_bootstrap_config"
    UNSAFE_PATH = "unsafe_path"
    REPOSITORY_INVALID = "repository_invalid"
    PYTHON_INCOMPATIBLE = "python_incompatible"
    VIRTUALENV_INVALID = "virtualenv_invalid"
    CONFIGURATION_INVALID = "configuration_invalid"
    MEMORY_RESTORE_FAILED = "memory_restore_failed"
    SCHEMA_INCOMPATIBLE = "schema_incompatible"
    PROJECT_MISMATCH = "project_mismatch"
    ADAPTER_CONFIGURATION_INVALID = "adapter_configuration_invalid"
    INSTALLATION_VALIDATION_FAILED = "installation_validation_failed"
    DEPENDENCY_FAILED = "dependency_failed"
    TIMEOUT = "timeout"


SAFE_EVENT_TYPES = {
    "bootstrap_started",
    "repository_validated",
    "configuration_prepared",
    "memory_restore_started",
    "memory_restore_completed",
    "memory_restore_failed",
    "installation_validated",
    "bootstrap_completed",
    "bootstrap_failed",
    "recovery_completed",
    "recovery_failed",
}


_RE_SECRETS = re.compile(r"(api[_-]?key|access[_-]?token|authorization|cookie|refresh[_-]?token|private[_-]?key|secret|bearer|password)", re.IGNORECASE)


@dataclass(frozen=True)
class BootstrapConfig:
    repository_root: Path
    agent_root: Path
    data_root: Path
    runtime_data_root: Path
    memory_root: Path
    config_root: Path
    environment_name: str = "dev"
    default_project_id: str = "default"
    python_executable: str = sys.executable
    virtualenv_path: Path = Path("agent/.venv")
    provider_name: str = "local"
    provider_adapter_name: str = "local"
    site_adapter_name: str = "generic"
    restore_memory: bool = False
    validate_only: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "BootstrapConfig":
        allowed = {
            "repository_root",
            "agent_root",
            "data_root",
            "runtime_data_root",
            "memory_root",
            "config_root",
            "environment_name",
            "default_project_id",
            "python_executable",
            "virtualenv_path",
            "provider_name",
            "provider_adapter_name",
            "site_adapter_name",
            "restore_memory",
            "validate_only",
            "metadata",
        }
        unknown = set(data.keys()) - allowed
        if unknown:
            raise ValueError(f"Unknown bootstrap config fields: {sorted(unknown)}")

        def _as_path(v: Any) -> Path:
            if isinstance(v, Path):
                return v
            if not isinstance(v, str):
                raise ValueError("Path fields must be strings or Path")
            if "\x00" in v:
                raise ValueError("Null byte in path is not allowed")
            return Path(v)

        def _as_str(v: Any, name: str) -> str:
            if not isinstance(v, str):
                raise ValueError(f"Field {name} must be a string")
            if "\x00" in v:
                raise ValueError(f"Null byte in field {name} not allowed")
            return v

        def _as_bool(v: Any, name: str) -> bool:
            if isinstance(v, bool):
                return v
            raise ValueError(f"Field {name} must be a boolean")

        repo_root = _as_path(data.get("repository_root", ".")).resolve()
        agent_root = _as_path(data.get("agent_root", repo_root / "agent")).resolve()
        data_root = _as_path(data.get("data_root", agent_root / ".data")).resolve()
        runtime_data_root = _as_path(data.get("runtime_data_root", data_root / "runtime")).resolve()
        memory_root = _as_path(data.get("memory_root", data_root / "memory")).resolve()
        config_root = _as_path(data.get("config_root", agent_root / "config")).resolve()
        virtualenv_path = _as_path(data.get("virtualenv_path", agent_root / ".venv")).resolve()

        environment_name = _as_str(data.get("environment_name", "dev"), "environment_name")
        default_project_id = _as_str(data.get("default_project_id", "default"), "default_project_id")
        python_executable = _as_str(data.get("python_executable", sys.executable), "python_executable")
        provider_name = _as_str(data.get("provider_name", "local"), "provider_name")
        provider_adapter_name = _as_str(data.get("provider_adapter_name", "local"), "provider_adapter_name")
        site_adapter_name = _as_str(data.get("site_adapter_name", "generic"), "site_adapter_name")

        restore_memory = _as_bool(data.get("restore_memory", False), "restore_memory")
        validate_only = _as_bool(data.get("validate_only", False), "validate_only")

        metadata_val = data.get("metadata", {})
        if not isinstance(metadata_val, dict):
            raise ValueError("metadata must be a dictionary")
        # Ensure no secrets are embedded in metadata keys/values
        for k, v in metadata_val.items():
            if _RE_SECRETS.search(str(k)):
                raise ValueError("Secret-like key names are not allowed in metadata")
            if isinstance(v, str) and _RE_SECRETS.search(v):
                raise ValueError("Secret-like values are not allowed in metadata")

        # Path safety checks: must be within repository_root
        for name, p in (
            ("agent_root", agent_root),
            ("data_root", data_root),
            ("runtime_data_root", runtime_data_root),
            ("memory_root", memory_root),
            ("config_root", config_root),
            ("virtualenv_path", virtualenv_path),
        ):
            _ensure_safe_path(repo_root, p, name)

        return BootstrapConfig(
            repository_root=repo_root,
            agent_root=agent_root,
            data_root=data_root,
            runtime_data_root=runtime_data_root,
            memory_root=memory_root,
            config_root=config_root,
            environment_name=environment_name,
            default_project_id=default_project_id,
            python_executable=python_executable,
            virtualenv_path=virtualenv_path,
            provider_name=provider_name,
            provider_adapter_name=provider_adapter_name,
            site_adapter_name=site_adapter_name,
            restore_memory=restore_memory,
            validate_only=validate_only,
            metadata=metadata_val,
        )


@dataclass
class BootstrapResult:
    status: BootstrapStatus
    message: str
    failure_code: Optional[FailureCode] = None
    events: List[Dict[str, Any]] = field(default_factory=list)
    validated_components: Dict[str, Any] = field(default_factory=dict)
    created_paths: List[str] = field(default_factory=list)
    schema_versions: Dict[str, str] = field(default_factory=lambda: {
        "bootstrap": BOOTSTRAP_SCHEMA_VERSION,
        "memory": MEMORY_SCHEMA_VERSION,
        "project_config": PROJECT_CONFIG_VERSION,
    })


class PortableBootstrap:
    def __init__(self, config: BootstrapConfig) -> None:
        self._config = config
        self._events: List[Dict[str, Any]] = []

    def emit_event(self, event_type: str, **payload: Any) -> None:
        if event_type not in SAFE_EVENT_TYPES:
            return
        safe_payload = {k: v for k, v in payload.items() if k in {
            "status", "count", "project_id", "version", "component", "result", "missing", "validated", "timestamp", "failure_code"
        }}
        evt = {
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **safe_payload,
        }
        self._events.append(evt)

    def _validate_python(self) -> Tuple[bool, Optional[str]]:
        ver = sys.version_info
        if ver.major == 3 and ver.minor >= 12:
            return True, None
        return False, f"Python {ver.major}.{ver.minor} detected; Python 3.12+ required"

    def _validate_repository(self) -> Dict[str, Any]:
        root = self._config.repository_root
        required_dirs = [
            root / "agent/ai",
            root / "agent/runtime",
            root / "agent/api",
            root / "agent/orchestrator",
            root / "agent/autonomy",
            root / "agent/memory",
            root / "agent/operations",
            root / "agent/missions",
            root / "agent/tests",
            root / "agent/deploy",
        ]
        missing = [str(p.relative_to(root)) for p in required_dirs if not p.exists() or not p.is_dir()]

        # Heuristic checks for production modules where present
        module_hints = {
            "runtime_service": (root / "agent/runtime", ("service", "server", "app")),
            "private_runtime_api": (root / "agent/api", ("private", "internal")),
            "autonomous_dev_supervisor": (root / "agent/autonomy", ("supervisor", "controller")),
            "project_memory_manager": (root / "agent/memory", ("manager", "store")),
            "site_operations_manager": (root / "agent/operations", ("manager", "ops")),
        }
        module_presence: Dict[str, bool] = {}
        for key, (base, tokens) in module_hints.items():
            present = False
            if base.exists() and base.is_dir():
                for child in base.glob("**/*.py"):
                    name = child.stem.lower()
                    if any(tok in name for tok in tokens):
                        present = True
                        break
            module_presence[key] = present

        result = {
            "missing_components": missing,
            "module_presence": module_presence,
            "repository_root": str(root),
        }
        return result

    def _prepare_directories(self) -> List[str]:
        created: List[str] = []
        for path in [
            self._config.data_root,
            self._config.runtime_data_root,
            self._config.memory_root,
            self._config.config_root,
        ]:
            if not path.exists():
                # Create only within repository, validated already
                path.mkdir(parents=True, exist_ok=True)
                created.append(str(path))
        return created

    def run(self) -> BootstrapResult:
        self.emit_event("bootstrap_started", status="starting")

        py_ok, py_msg = self._validate_python()
        if not py_ok:
            self.emit_event("bootstrap_failed", status="failed", failure_code=FailureCode.PYTHON_INCOMPATIBLE.value)
            return BootstrapResult(
                status=BootstrapStatus.FAILED,
                message=py_msg or "Python incompatible",
                failure_code=FailureCode.PYTHON_INCOMPATIBLE,
                events=self._events,
            )

        repo_validation = self._validate_repository()
        self.emit_event(
            "repository_validated",
            status="ok" if not repo_validation["missing_components"] else "missing",
            validated=len(repo_validation["module_presence"]),
            missing=len(repo_validation["missing_components"]),
        )

        if repo_validation["missing_components"]:
            self.emit_event("bootstrap_failed", status="failed", failure_code=FailureCode.REPOSITORY_INVALID.value)
            return BootstrapResult(
                status=BootstrapStatus.FAILED,
                message="Repository layout missing required components",
                failure_code=FailureCode.REPOSITORY_INVALID,
                events=self._events,
                validated_components=repo_validation,
            )

        created_paths: List[str] = []
        if not self._config.validate_only:
            created_paths = self._prepare_directories()
            self.emit_event("configuration_prepared", status="ok", count=len(created_paths))
        else:
            self.emit_event("configuration_prepared", status="skipped", count=0)

        status = BootstrapStatus.VALIDATED if self._config.validate_only else BootstrapStatus.COMPLETED
        final_event = "bootstrap_completed" if status != BootstrapStatus.FAILED else "bootstrap_failed"
        self.emit_event(final_event, status=status.value)

        return BootstrapResult(
            status=status,
            message="Bootstrap validation completed" if self._config.validate_only else "Bootstrap completed",
            events=self._events,
            created_paths=created_paths,
            validated_components=repo_validation,
        )


def _ensure_safe_path(repo_root: Path, target: Path, field_name: str) -> None:
    if not isinstance(target, Path):
        raise ValueError(f"{field_name} must be a Path")
    if "\x00" in str(target):
        raise ValueError(f"Null byte in {field_name} not allowed")
    repo_resolved = repo_root.resolve()
    tgt_resolved = target.resolve()
    try:
        if not tgt_resolved.is_relative_to(repo_resolved):  # Python 3.9+ API present in 3.12
            raise ValueError
    except Exception:
        raise ValueError(f"{field_name} must be within repository_root: {repo_resolved}")


# Public builders

def build_portable_bootstrap(config: BootstrapConfig) -> PortableBootstrap:
    return PortableBootstrap(config)


# CLI interface

def _parse_args(argv: List[str]) -> Dict[str, Any]:
    # Minimal, dependency-free argument parsing
    # Supported flags:
    #   --repository-root PATH
    #   --agent-root PATH
    #   --data-root PATH
    #   --runtime-data-root PATH
    #   --memory-root PATH
    #   --config-root PATH
    #   --environment-name NAME
    #   --default-project-id ID
    #   --python-executable PATH
    #   --virtualenv-path PATH
    #   --provider-name NAME
    #   --provider-adapter NAME
    #   --site-adapter NAME
    #   --restore-memory (flag)
    #   --validate-only (flag)
    #   --bootstrap (flag)  # synonym for not validate-only
    out: Dict[str, Any] = {}
    it = iter(argv)
    for arg in it:
        if arg == "--repository-root":
            out["repository_root"] = next(it, ".")
        elif arg == "--agent-root":
            out["agent_root"] = next(it, "agent")
        elif arg == "--data-root":
            out["data_root"] = next(it, "agent/.data")
        elif arg == "--runtime-data-root":
            out["runtime_data_root"] = next(it, "agent/.data/runtime")
        elif arg == "--memory-root":
            out["memory_root"] = next(it, "agent/.data/memory")
        elif arg == "--config-root":
            out["config_root"] = next(it, "agent/config")
        elif arg == "--environment-name":
            out["environment_name"] = next(it, "dev")
        elif arg == "--default-project-id":
            out["default_project_id"] = next(it, "default")
        elif arg == "--python-executable":
            out["python_executable"] = next(it, sys.executable)
        elif arg == "--virtualenv-path":
            out["virtualenv_path"] = next(it, "agent/.venv")
        elif arg == "--provider-name":
            out["provider_name"] = next(it, "local")
        elif arg == "--provider-adapter":
            out["provider_adapter_name"] = next(it, "local")
        elif arg == "--site-adapter":
            out["site_adapter_name"] = next(it, "generic")
        elif arg == "--restore-memory":
            out["restore_memory"] = True
        elif arg == "--validate-only":
            out["validate_only"] = True
        elif arg == "--bootstrap":
            out["validate_only"] = False
        else:
            # ignore unknown CLI tokens to maintain robustness; config builder rejects unknown fields
            continue
    return out


def _exit_code_from_failure(code: Optional[FailureCode]) -> int:
    mapping = {
        FailureCode.INVALID_BOOTSTRAP_CONFIG: 10,
        FailureCode.UNSAFE_PATH: 11,
        FailureCode.REPOSITORY_INVALID: 12,
        FailureCode.PYTHON_INCOMPATIBLE: 13,
        FailureCode.VIRTUALENV_INVALID: 14,
        FailureCode.CONFIGURATION_INVALID: 15,
        FailureCode.MEMORY_RESTORE_FAILED: 16,
        FailureCode.SCHEMA_INCOMPATIBLE: 17,
        FailureCode.PROJECT_MISMATCH: 18,
        FailureCode.ADAPTER_CONFIGURATION_INVALID: 19,
        FailureCode.INSTALLATION_VALIDATED: 20 if hasattr(FailureCode, 'INSTALLATION_VALIDATED') else 20,  # compatibility
        FailureCode.DEPENDENCY_FAILED: 21,
        FailureCode.TIMEOUT: 22,
    }
    return mapping.get(code, 1) if code else 0


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    try:
        cfg = BootstrapConfig.from_dict(args)
    except ValueError as e:
        result = BootstrapResult(
            status=BootstrapStatus.FAILED,
            message=str(e),
            failure_code=FailureCode.INVALID_BOOTSTRAP_CONFIG,
        )
        print(json.dumps(result.__dict__, default=str))
        return _exit_code_from_failure(result.failure_code)
    try:
        bootstrap = build_portable_bootstrap(cfg)
        res = bootstrap.run()
        print(json.dumps({
            "status": res.status.value,
            "message": res.message,
            "failure_code": res.failure_code.value if res.failure_code else None,
            "events": res.events,
            "validated_components": res.validated_components,
            "created_paths": res.created_paths,
            "schema_versions": res.schema_versions,
        }))
        return _exit_code_from_failure(res.failure_code)
    except Exception:
        # Avoid raw exception exposure
        safe = BootstrapResult(
            status=BootstrapStatus.FAILED,
            message="Bootstrap failed due to an unexpected error",
            failure_code=FailureCode.DEPENDENCY_FAILED,
        )
        print(json.dumps(safe.__dict__, default=str))
        return _exit_code_from_failure(safe.failure_code)


if __name__ == "__main__":
    raise SystemExit(main())
