from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any


_PROVIDER_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_MODEL_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,199}$")


def data_root() -> Path:
    return Path(os.environ.get("MITIGATE_AI_DATA_ROOT", "/srv/mitigate/data")).expanduser().resolve()


def provider_secret_path(provider: str) -> Path:
    name = str(provider or "").strip().lower()
    if not _PROVIDER_ID.fullmatch(name):
        raise ValueError("invalid_provider_id")
    return data_root() / "runtime" / "provider-secrets" / f"{name}.json"


def save_provider_secret(*, provider: str, api_key: str, model: str) -> Path:
    key = str(api_key or "").strip()
    model_ref = str(model or "").strip()
    if not key or len(key) > 4096:
        raise ValueError("invalid_provider_api_key")
    if not _MODEL_REF.fullmatch(model_ref):
        raise ValueError("invalid_provider_model")

    path = provider_secret_path(provider)
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    payload = {
        "provider": str(provider).strip().lower(),
        "model": model_ref,
        "api_key": key,
        "schema_version": 1,
    }

    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, separators=(",", ":"), ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, path)
        os.chmod(path, 0o600)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
    return path


def load_provider_secret(provider: str) -> dict[str, Any]:
    path = provider_secret_path(provider)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    model = str(payload.get("model") or "").strip()
    api_key = str(payload.get("api_key") or "").strip()
    if not model or not api_key:
        return {}
    return {"provider": str(provider).strip().lower(), "model": model, "api_key": api_key}


__all__ = [
    "data_root",
    "provider_secret_path",
    "save_provider_secret",
    "load_provider_secret",
]
