from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

__all__ = [
    "PortableBootstrapValidator",
    "validate_portable_bootstrap",
    "validate",
    "validate_repository",
    "run_validation",
]


@dataclass(frozen=True)
class ValidationResult:
    """
    Structured result for portable bootstrap validation.

    This result is designed to be safe to compute from a clean repository checkout
    without requiring any machine-specific hidden files, runtime state, provider
    configuration, or network connectivity.

    Interpretation:
    - status:
        - "validated": structure present and non-placeholder configuration detected
        - "configuration_required": structure present but placeholders indicate external configuration still required
        - "validation_ready": alias for configuration-required when explicitly requested by callers
        - "invalid": repository/bootstrap structure invalid or missing required assets
    - ok: True for status in {validated, configuration_required, validation_ready}; False for invalid
    - No external side effects are performed.
    """

    ok: bool
    status: str
    validated: bool
    validation_ready: bool
    ready_for_configuration: bool
    configuration_required: bool
    details: Dict[str, Any]


class PortableBootstrapValidator:
    """
    Clean-checkout-safe portable bootstrap validator.

    This validator performs only local repository structure checks and placeholder
    detection. It does not contact providers, access system configuration, execute
    Git, or depend on pre-existing runtime state. It distinguishes between:
      A) valid repository/bootstrap structure that still requires external configuration
      B) invalid repository/bootstrap structure

    For (A) it returns a safe structured result with status "configuration_required"
    (or "validation_ready"), not an exception.
    For (B) it returns a structured result with status "invalid" and ok=False.
    """

    # Filenames considered part of the managed bootstrap assets
    PROJECT_TEMPLATE = Path("agent/bootstrap/project.example.json")
    ENV_TEMPLATE = Path("agent/bootstrap/env.example")

    # Minimal canonical required fields for project template structural validity
    REQUIRED_PROJECT_FIELDS: Tuple[str, ...] = (
        "project_id",
        "project_name",
        "repository",
        "default_branch",
        "site_type",
        "cms_type",
        "adapter",
        "canonical_url",
        "allowed_paths",
        "denied_paths",
        "environment",
        "seo_enabled",
        "performance_monitoring_enabled",
        "availability_monitoring_enabled",
        "security_monitoring_enabled",
        "accessibility_monitoring_enabled",
        "ecommerce_enabled",
        "autonomous_low_risk_fixes",
        "autonomous_medium_risk_fixes",
        "memory_enabled",
        "metadata",
    )

    # Keys in env.example that must exist with placeholder-only values
    REQUIRED_ENV_KEYS: Tuple[str, ...] = (
        "ENVIRONMENT",
        "MITIGATE_AI_ENVIRONMENT_NAME",
        "PROJECT_ID",
        "MITIGATE_AI_PROJECT_ID",
        "REPOSITORY_ROOT",
        "MITIGATE_AI_REPOSITORY_ROOT",
        "DATA_ROOT",
        "MITIGATE_AI_DATA_ROOT",
        "MEMORY_ROOT",
        "MITIGATE_AI_MEMORY_ROOT",
        "PROVIDER",
        "MITIGATE_AI_PROVIDER",
        "PROVIDER_API_KEY",
        "MITIGATE_AI_PROVIDER_API_KEY",
        "PROVIDER_BASE_URL",
        "MITIGATE_AI_PROVIDER_BASE_URL",
        "PROVIDER_MODEL",
        "MITIGATE_AI_PROVIDER_MODEL",
        "SITE_ADAPTER",
        "MITIGATE_AI_SITE_ADAPTER",
        "RUNTIME_HOST",
        "MITIGATE_AI_RUNTIME_HOST",
        "RUNTIME_PORT",
        "MITIGATE_AI_RUNTIME_PORT",
        "API_TOKEN",
        "MITIGATE_AI_API_TOKEN",
    )

    PLACEHOLDER_TOKENS: Tuple[str, ...] = (
        "<PLACEHOLDER>",
        "<ENVIRONMENT>",
        "<PROJECT_ID>",
        "<REPOSITORY_ROOT>",
        "<DATA_ROOT>",
        "<MEMORY_ROOT>",
        "<PROVIDER>",
        "<PROVIDER_BASE_URL>",
        "<PROVIDER_MODEL>",
        "<SITE_ADAPTER>",
        "<RUNTIME_HOST>",
        "<RUNTIME_PORT>",
    )

    def __init__(self, repository_root: Optional[os.PathLike[str] | str] = None) -> None:
        if repository_root is None:
            root = Path.cwd()
        else:
            root = Path(repository_root)
        # Path validation without weakening isolation guarantees
        root = root.resolve()
        object.__setattr__(self, "_root", root)

    @property
    def repository_root(self) -> Path:
        return self._root  # type: ignore[attr-defined]

    # Public API
    def validate(self, *, validation_only: bool = True) -> ValidationResult:
        root = self.repository_root
        details: Dict[str, Any] = {
            "paths": {
                "repository_root": str(root),
                "project_template": str(root / self.PROJECT_TEMPLATE),
                "env_template": str(root / self.ENV_TEMPLATE),
            },
            "missing": [],
            "placeholders": [],
            "project_fields_missing": [],
        }

        # Ensure repository root exists and is a directory
        if not root.exists() or not root.is_dir():
            details["missing"].append("repository_root")
            return ValidationResult(
                ok=False,
                status="invalid",
                validated=False,
                validation_ready=False,
                ready_for_configuration=False,
                configuration_required=False,
                details=details,
            )

        # Validate presence of bootstrap assets
        project_path = root / self.PROJECT_TEMPLATE
        env_path = root / self.ENV_TEMPLATE
        missing_assets: List[str] = []
        if not project_path.is_file():
            missing_assets.append(str(self.PROJECT_TEMPLATE))
        if not env_path.is_file():
            missing_assets.append(str(self.ENV_TEMPLATE))
        if missing_assets:
            details["missing"].extend(missing_assets)
            return ValidationResult(
                ok=False,
                status="invalid",
                validated=False,
                validation_ready=False,
                ready_for_configuration=False,
                configuration_required=False,
                details=details,
            )

        # Parse and validate project template structure
        project_ok, project_details = self._validate_project_template(project_path)
        details.update(project_details)
        if not project_ok:
            return ValidationResult(
                ok=False,
                status="invalid",
                validated=False,
                validation_ready=False,
                ready_for_configuration=False,
                configuration_required=False,
                details=details,
            )

        # Parse env example and check placeholders (clean checkout expected)
        env_ok, env_details = self._validate_env_template(env_path)
        details.update(env_details)
        if not env_ok:
            # Structural problem with env template represents invalid repository
            return ValidationResult(
                ok=False,
                status="invalid",
                validated=False,
                validation_ready=False,
                ready_for_configuration=False,
                configuration_required=False,
                details=details,
            )

        # Determine configuration state based on placeholder presence
        placeholders: List[str] = details.get("placeholders", [])
        if placeholders:
            status = "validation_ready" if validation_only else "configuration_required"
            return ValidationResult(
                ok=True,
                status=status,
                validated=False,
                validation_ready=True,
                ready_for_configuration=True,
                configuration_required=True,
                details=details,
            )

        # No placeholders detected; treat as ready
        return ValidationResult(
            ok=True,
            status="validated",
            validated=True,
            validation_ready=True,
            ready_for_configuration=False,
            configuration_required=False,
            details=details,
        )

    # Internal helpers
    def _validate_project_template(self, project_path: Path) -> Tuple[bool, Dict[str, Any]]:
        out: Dict[str, Any] = {"project_fields_missing": [], "project_template_loaded": False}
        try:
            with project_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            out["project_template_loaded"] = True
        except Exception as exc:  # Parsing failure => invalid structure
            out["error"] = f"project_template_parse_error: {type(exc).__name__}"
            return False, out

        missing: List[str] = []
        for field in self.REQUIRED_PROJECT_FIELDS:
            if field not in data:
                missing.append(field)
        out["project_fields_missing"] = missing
        # project_id must exist at top level (clean checkout project identity)
        if "project_id" not in data:
            missing.append("project_id")
        out["project_id_present"] = "project_id" in data

        # environment should be an object with a name key, but name may be placeholder
        env_obj = data.get("environment")
        out["environment_object_present"] = isinstance(env_obj, dict)
        if not isinstance(env_obj, dict):
            return False, out
        out["environment_name_present"] = "name" in env_obj

        if missing:
            return False, out
        return True, out

    def _validate_env_template(self, env_path: Path) -> Tuple[bool, Dict[str, Any]]:
        out: Dict[str, Any] = {"env_template_loaded": False, "placeholders": []}
        try:
            raw = env_path.read_text(encoding="utf-8")
            out["env_template_loaded"] = True
        except Exception as exc:
            out["error"] = f"env_template_read_error: {type(exc).__name__}"
            return False, out

        parsed = self._parse_env_lines(raw.splitlines())
        out["env_keys_present"] = sorted(parsed.keys())
        missing_keys = [k for k in self.REQUIRED_ENV_KEYS if k not in parsed]
        out["env_keys_missing"] = missing_keys
        if missing_keys:
            return False, out

        placeholders: List[str] = []
        for key, value in parsed.items():
            if self._is_placeholder(value):
                placeholders.append(key)
        out["placeholders"] = sorted(set(placeholders))
        return True, out

    @staticmethod
    def _parse_env_lines(lines: Iterable[str]) -> Dict[str, str]:
        result: Dict[str, str] = {}
        for line in lines:
            s = line.strip()
            if not s:
                continue
            if s.startswith("#"):
                # comments allowed in file, ignored for parsing
                continue
            if "=" not in s:
                # skip invalid lines rather than failing clean checkout validation
                continue
            key, val = s.split("=", 1)
            key = key.strip()
            val = val.strip()
            # Strip surrounding quotes if present (KEY="VALUE")
            if len(val) >= 2 and ((val[0] == '"' and val[-1] == '"') or (val[0] == "'" and val[-1] == "'")):
                val = val[1:-1]
            result[key] = val
        return result

    def _is_placeholder(self, value: str) -> bool:
        if not value:
            return True
        # Angle-bracket placeholders
        if value.startswith("<") and value.endswith(">"):
            return True
        for token in self.PLACEHOLDER_TOKENS:
            if value == token:
                return True
        # Special-case generic placeholder marker embedded in compound values
        if "<PLACEHOLDER>" in value:
            return True
        return False


# Backwards/forwards compatibility helpers to preserve public API symbols

def validate_portable_bootstrap(repository_root: Optional[os.PathLike[str] | str] = None, *, validation_only: bool = True) -> Dict[str, Any]:
    validator = PortableBootstrapValidator(repository_root)
    res = validator.validate(validation_only=validation_only)
    return _result_to_mapping(res)


def validate(repository_root: Optional[os.PathLike[str] | str] = None, *, validation_only: bool = True) -> Dict[str, Any]:
    return validate_portable_bootstrap(repository_root, validation_only=validation_only)


def validate_repository(repository_root: Optional[os.PathLike[str] | str] = None) -> Dict[str, Any]:
    return validate_portable_bootstrap(repository_root, validation_only=True)


def run_validation(repository_root: Optional[os.PathLike[str] | str] = None) -> Dict[str, Any]:
    return validate_portable_bootstrap(repository_root, validation_only=True)


def _result_to_mapping(result: ValidationResult) -> Dict[str, Any]:
    return {
        "ok": result.ok,
        "status": result.status,
        "validated": result.validated,
        "validation_ready": result.validation_ready,
        "ready_for_configuration": result.ready_for_configuration,
        "configuration_required": result.configuration_required,
        "details": result.details,
    }
