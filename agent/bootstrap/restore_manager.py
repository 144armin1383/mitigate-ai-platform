from __future__ import annotations

# Restore Manager for MITIGATE AI
# - Restores only safe, non-secret assets
# - Provider- and platform-neutral
# - No subprocess, no external network

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import json
import sys
from datetime import datetime, timezone
import re


MEMORY_SCHEMA_VERSION = "1.0"
RESTORE_SCHEMA_VERSION = "1.0"
PROJECT_CONFIG_VERSION = "1.0"


class RestoreStatus(str, Enum):
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
class RestoreConfig:
    repository_root: Path
    agent_root: Path
    data_root: Path
    runtime_data_root: Path
    memory_root: Path
    config_root: Path
    environment_name: str
    expected_project_id: str
    restore_source: Path
    validate_only: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "RestoreConfig":
        allowed = {
            "repository_root",
            "agent_root",
            "data_root",
            "runtime_data_root",
            "memory_root",
            "config_root",
            "environment_name",
            "expected_project_id",
            "restore_source",
            "validate_only",
            "metadata",
        }
        unknown = set(data.keys()) - allowed
        if unknown:
            raise ValueError(f"Unknown restore config fields: {sorted(unknown)}")

        def _as_path(name: str, v: Any) -> Path:
            if isinstance(v, Path):
                p = v
            elif isinstance(v, str):
                if "\x00" in v:
                    raise ValueError(f"Null byte in path field {name}")
                p = Path(v)
            else:
                raise ValueError(f"Path field {name} must be a string or Path")
            return p.resolve()

        def _as_str(name: str, v: Any) -> str:
            if not isinstance(v, str):
                raise ValueError(f"Field {name} must be a string")
            if "\x00" in v:
                raise ValueError(f"Null byte in field {name}")
            return v

        def _as_bool(name: str, v: Any) -> bool:
            if isinstance(v, bool):
                return v
            raise ValueError(f"Field {name} must be a boolean")

        repo = _as_path("repository_root", data.get("repository_root", "."))
        agent = _as_path("agent_root", data.get("agent_root", repo / "agent"))
        data_root = _as_path("data_root", data.get("data_root", agent / ".data"))
        runtime_data_root = _as_path("runtime_data_root", data.get("runtime_data_root", data_root / "runtime"))
        memory_root = _as_path("memory_root", data.get("memory_root", data_root / "memory"))
        config_root = _as_path("config_root", data.get("config_root", agent / "config"))
        restore_source = _as_path("restore_source", data.get("restore_source", data_root / "restore_source"))

        # Safety: all paths must be inside repository root
        for name, p in (
            ("agent_root", agent),
            ("data_root", data_root),
            ("runtime_data_root", runtime_data_root),
            ("memory_root", memory_root),
            ("config_root", config_root),
            ("restore_source", restore_source),
        ):
            _ensure_safe_path(repo, p, name)

        env_name = _as_str("environment_name", data.get("environment_name", "dev"))
        expected_project_id = _as_str("expected_project_id", data.get("expected_project_id", "default"))
        validate_only = _as_bool("validate_only", data.get("validate_only", False))
        metadata_val = data.get("metadata", {})
        if not isinstance(metadata_val, dict):
            raise ValueError("metadata must be a dictionary")
        for k, v in metadata_val.items():
            if _RE_SECRETS.search(str(k)):
                raise ValueError("Secret-like key names are not allowed in metadata")
            if isinstance(v, str) and _RE_SECRETS.search(v):
                raise ValueError("Secret-like values are not allowed in metadata")

        return RestoreConfig(
            repository_root=repo,
            agent_root=agent,
            data_root=data_root,
            runtime_data_root=runtime_data_root,
            memory_root=memory_root,
            config_root=config_root,
            environment_name=env_name,
            expected_project_id=expected_project_id,
            restore_source=restore_source,
            validate_only=validate_only,
            metadata=metadata_val,
        )


@dataclass
class RestoreResult:
    status: RestoreStatus
    message: str
    failure_code: Optional[FailureCode] = None
    events: List[Dict[str, Any]] = field(default_factory=list)
    restored_files: List[str] = field(default_factory=list)
    skipped_files: List[Dict[str, str]] = field(default_factory=list)
    schema_versions: Dict[str, str] = field(default_factory=lambda: {
        "restore": RESTORE_SCHEMA_VERSION,
        "memory": MEMORY_SCHEMA_VERSION,
        "project_config": PROJECT_CONFIG_VERSION,
    })


class RestoreManager:
    def __init__(self, config: RestoreConfig) -> None:
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

    def _load_manifest(self, src: Path) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        manifest = src / "manifest.json"
        if manifest.exists():
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
                return data, None
            except Exception:
                return None, "Manifest unreadable"
        return None, None

    def _validate_manifest(self, manifest: Optional[Dict[str, Any]]) -> Optional[str]:
        if not manifest:
            return None
        # schema version
        schema_ver = str(manifest.get("schema_version", MEMORY_SCHEMA_VERSION))
        if schema_ver != MEMORY_SCHEMA_VERSION:
            return "schema_incompatible"
        # project identity
        proj = str(manifest.get("project_id", ""))
        if proj and proj != self._config.expected_project_id:
            return "project_mismatch"
        return None

    def _is_safe_file(self, p: Path) -> Tuple[bool, Optional[str]]:
        if not p.is_file():
            return False, "not_a_file"
        # Only restore safe types
        allowed_ext = {".json", ".ndjson", ".txt", ".md", ".yaml", ".yml"}
        if p.suffix.lower() not in allowed_ext:
            return False, "unsupported_file_type"
        # inspect content for secret-like markers (text files only)
        try:
            txt = p.read_text(encoding="utf-8", errors="strict")
            if _RE_SECRETS.search(txt):
                return False, "secret_like_content"
        except Exception:
            return False, "unreadable"
        return True, None

    def _safe_write_text(self, dst: Path, content: str) -> None:
        # Ensure destination stays within memory_root or config_root
        base_allowed = [self._config.memory_root.resolve(), self._config.config_root.resolve()]
        dr = dst.resolve()
        if not any(dr.is_relative_to(b) for b in base_allowed):
            raise ValueError("unsafe_path")
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(content, encoding="utf-8")

    def perform_restore(self) -> RestoreResult:
        self.emit_event("memory_restore_started", status="starting", project_id=self._config.expected_project_id)
        src = self._config.restore_source
        if not src.exists() or not src.is_dir():
            self.emit_event("memory_restore_failed", status="failed")
            return RestoreResult(
                status=RestoreStatus.FAILED,
                message="Restore source does not exist or is not a directory",
                failure_code=FailureCode.MEMORY_RESTORE_FAILED,
                events=self._events,
            )

        manifest, err = self._load_manifest(src)
        if err:
            self.emit_event("memory_restore_failed", status="failed")
            return RestoreResult(
                status=RestoreStatus.FAILED,
                message="Manifest unreadable",
                failure_code=FailureCode.SCHEMA_INCOMPATIBLE,
                events=self._events,
            )
        mval = self._validate_manifest(manifest)
        if mval == "schema_incompatible":
            self.emit_event("memory_restore_failed", status="failed")
            return RestoreResult(
                status=RestoreStatus.FAILED,
                message="Memory schema incompatible",
                failure_code=FailureCode.SCHEMA_INCOMPATIBLE,
                events=self._events,
            )
        if mval == "project_mismatch":
            self.emit_event("memory_restore_failed", status="failed")
            return RestoreResult(
                status=RestoreStatus.FAILED,
                message="Project identity mismatch",
                failure_code=FailureCode.PROJECT_MISMATCH,
                events=self._events,
            )

        restored: List[str] = []
        skipped: List[Dict[str, str]] = []

        # Allowed categories and destinations (relative to memory_root/config_root)
        categories = {
            "memory": (self._config.memory_root, "memory"),
            "handoff": (self._config.memory_root / "handoff", "handoff"),
            "snapshots": (self._config.memory_root / "snapshots", "snapshots"),
            "decisions": (self._config.memory_root / "decisions", "decisions"),
            "work": (self._config.memory_root / "work", "work"),
            "issues": (self._config.memory_root / "issues", "issues"),
            "config": (self._config.config_root / "projects", "config"),
        }

        for cat, (dst_base, folder) in categories.items():
            cat_src = src / folder
            if not cat_src.exists() or not cat_src.is_dir():
                continue
            for fp in cat_src.rglob("*"):
                if not fp.is_file():
                    continue
                safe, reason = self._is_safe_file(fp)
                rel = fp.relative_to(cat_src)
                if not safe:
                    skipped.append({"path": str((folder / rel).as_posix() if isinstance(folder, Path) else f"{folder}/{rel}"), "reason": reason or "unsafe"})
                    continue
                if self._config.validate_only:
                    restored.append(str((folder / rel).as_posix() if isinstance(folder, Path) else f"{folder}/{rel}"))
                    continue
                try:
                    content = fp.read_text(encoding="utf-8")
                    dst = (dst_base / self._config.expected_project_id / rel).resolve() if cat != "config" else (dst_base / f"{self._config.expected_project_id}.json").resolve() if fp.suffix == ".json" and rel.name == "project.json" else (dst_base / rel).resolve()
                    self._safe_write_text(dst, content)
                    restored.append(str(dst))
                except Exception:
                    skipped.append({"path": str((folder / rel).as_posix() if isinstance(folder, Path) else f"{folder}/{rel}"), "reason": "write_failed"})

        status = RestoreStatus.VALIDATED if self._config.validate_only else RestoreStatus.COMPLETED
        if status == RestoreStatus.COMPLETED and not restored and not skipped:
            # Nothing to restore is considered completed with message
            msg = "No restorable files found"
        else:
            msg = "Restore validation completed" if self._config.validate_only else "Restore completed"

        self.emit_event("memory_restore_completed", status="ok", count=len(restored))
        self.emit_event("recovery_completed", status=status.value)

        return RestoreResult(
            status=status,
            message=msg,
            restored_files=restored,
            skipped_files=skipped,
            events=self._events,
        )


# Safety helpers

def _ensure_safe_path(repo_root: Path, target: Path, field_name: str) -> None:
    repo_resolved = repo_root.resolve()
    tgt_resolved = target.resolve()
    try:
        if not tgt_resolved.is_relative_to(repo_resolved):
            raise ValueError
    except Exception:
        raise ValueError(f"{field_name} must be within repository_root: {repo_resolved}")


# Public builders

def build_restore_manager(config: RestoreConfig) -> RestoreManager:
    return RestoreManager(config)


def _parse_args(argv: List[str]) -> Dict[str, Any]:
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
        elif arg == "--expected-project-id":
            out["expected_project_id"] = next(it, "default")
        elif arg == "--restore-source":
            out["restore_source"] = next(it, "agent/.data/restore_source")
        elif arg == "--validate-only":
            out["validate_only"] = True
        else:
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
        FailureCode.INSTALLATION_VALIDATION_FAILED: 20,
        FailureCode.DEPENDENCY_FAILED: 21,
        FailureCode.TIMEOUT: 22,
    }
    return mapping.get(code, 1) if code else 0


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    try:
        cfg = RestoreConfig.from_dict(args)
    except ValueError as e:
        res = RestoreResult(status=RestoreStatus.FAILED, message=str(e), failure_code=FailureCode.INVALID_BOOTSTRAP_CONFIG)
        print(json.dumps(res.__dict__, default=str))
        return _exit_code_from_failure(res.failure_code)
    try:
        mgr = build_restore_manager(cfg)
        result = mgr.perform_restore()
        print(json.dumps({
            "status": result.status.value,
            "message": result.message,
            "failure_code": result.failure_code.value if result.failure_code else None,
            "events": result.events,
            "restored_files": result.restored_files,
            "skipped_files": result.skipped_files,
            "schema_versions": result.schema_versions,
        }))
        return _exit_code_from_failure(result.failure_code)
    except Exception:
        safe = RestoreResult(
            status=RestoreStatus.FAILED,
            message="Restore failed due to an unexpected error",
            failure_code=FailureCode.DEPENDENCY_FAILED,
        )
        print(json.dumps(safe.__dict__, default=str))
        return _exit_code_from_failure(safe.failure_code)


if __name__ == "__main__":
    raise SystemExit(main())
