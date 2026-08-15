from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping

from agent.projects.project_adapter import (
    ProjectDeploymentRequest,
    ProjectDeploymentResult,
)


class WordPressProjectAdapter:
    """Deploy repository-managed WordPress packages with bounded WP-CLI actions.

    The adapter accepts no mission-provided shell or SQL. Optional live actions
    are declared in ``wordpress/mitigate-deploy.json`` and validated against a
    small schema. Plugin-owned database migrations stay inside plugin activation
    hooks, where WordPress owns prefixing and lifecycle behavior.
    """

    MANIFEST = "wordpress/mitigate-deploy.json"
    _ROUTINE_REQUIRED = "project.deploy"
    _ALLOWED_ACTIONS = {"activate_plugin", "ensure_page", "health_path"}

    def __init__(
        self,
        *,
        wordpress_root: str | Path | None = None,
        wp_binary: str | None = None,
        health_base_url: str | None = None,
        runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
        urlopen: Callable[..., Any] | None = None,
    ) -> None:
        self.wordpress_root = Path(
            wordpress_root
            or os.environ.get("MITIGATE_WORDPRESS_ROOT")
            or "/srv/mitigate/wordpress/current"
        ).expanduser()
        self.wp_binary = str(
            wp_binary or os.environ.get("MITIGATE_WP_CLI_BINARY") or "wp"
        ).strip()
        self.health_base_url = str(
            health_base_url or os.environ.get("MITIGATE_WORDPRESS_HEALTH_URL") or ""
        ).rstrip("/")
        self._runner = runner or subprocess.run
        self._urlopen = urlopen or urllib.request.urlopen

    @property
    def name(self) -> str:
        return "wordpress"

    def supports(self, project_type: str) -> bool:
        return str(project_type or "").strip().lower() in {
            "wordpress", "woocommerce", "wp"
        }

    @staticmethod
    def _safe_slug(value: str) -> str:
        text = str(value or "").strip().lower()
        if not text or any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for ch in text):
            raise ValueError("unsafe_wordpress_slug")
        return text

    def _run_wp(self, *args: str) -> subprocess.CompletedProcess[str]:
        proc = self._runner(
            [self.wp_binary, f"--path={self.wordpress_root}", *args],
            text=True,
            capture_output=True,
            check=False,
            timeout=90,
            env={**os.environ, "HOME": os.environ.get("MITIGATE_WP_CLI_HOME", "/tmp")},
        )
        if proc.returncode != 0:
            raise RuntimeError("wordpress_wp_cli_failed")
        return proc

    def _manifest(self, repository_root: Path) -> dict[str, Any]:
        path = repository_root / self.MANIFEST
        if not path.is_file():
            return {"version": 1, "actions": []}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError) as exc:
            raise RuntimeError("wordpress_deploy_manifest_invalid") from exc
        if not isinstance(payload, dict) or payload.get("version") != 1:
            raise RuntimeError("wordpress_deploy_manifest_invalid")
        actions = payload.get("actions", [])
        if not isinstance(actions, list) or len(actions) > 30:
            raise RuntimeError("wordpress_deploy_manifest_invalid")
        for action in actions:
            if not isinstance(action, dict):
                raise RuntimeError("wordpress_deploy_manifest_invalid")
            if set(action) - {"type", "plugin", "slug", "title", "content", "path"}:
                raise RuntimeError("wordpress_deploy_manifest_invalid")
            if action.get("type") not in self._ALLOWED_ACTIONS:
                raise RuntimeError("wordpress_deploy_manifest_action_denied")
        return payload

    @staticmethod
    def _packages(changed_files: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
        packages: list[tuple[str, str]] = []
        for raw in changed_files:
            path = PurePosixPath(str(raw).replace("\\", "/"))
            if len(path.parts) < 2 or path.parts[0] != "wordpress":
                continue
            package = path.parts[1]
            if package == "mitigate-deploy.json":
                continue
            kind = "theme" if package.endswith("-child") else "plugin"
            item = (kind, package)
            if item not in packages:
                packages.append(item)
        return tuple(packages)

    def _atomic_copy_package(
        self,
        *,
        repository_root: Path,
        kind: str,
        package: str,
    ) -> str:
        package = self._safe_slug(package)
        source = repository_root / "wordpress" / package
        if not source.is_dir():
            raise RuntimeError("wordpress_package_source_missing")
        live_parent = self.wordpress_root / "wp-content" / ("themes" if kind == "theme" else "plugins")
        if not live_parent.is_dir():
            raise RuntimeError("wordpress_live_package_root_missing")
        target = live_parent / package
        with tempfile.TemporaryDirectory(prefix=f".{package}.", dir=live_parent) as td:
            staged = Path(td) / package
            shutil.copytree(source, staged, symlinks=False)
            backup = live_parent / f".{package}.mitigate-backup"
            if backup.exists():
                shutil.rmtree(backup)
            if target.exists():
                target.rename(backup)
            try:
                staged.rename(target)
            except Exception:
                if backup.exists() and not target.exists():
                    backup.rename(target)
                raise
            if backup.exists():
                shutil.rmtree(backup)
        return f"deploy_{kind}:{package}"

    def _apply_manifest(self, manifest: Mapping[str, Any]) -> tuple[list[str], str | None]:
        actions_done: list[str] = []
        health_path: str | None = None
        for action in manifest.get("actions", []):
            action_type = str(action.get("type") or "")
            if action_type == "activate_plugin":
                plugin = self._safe_slug(str(action.get("plugin") or ""))
                self._run_wp("plugin", "activate", plugin)
                actions_done.append(f"activate_plugin:{plugin}")
            elif action_type == "ensure_page":
                slug = self._safe_slug(str(action.get("slug") or ""))
                title = str(action.get("title") or "").strip()[:200]
                content = str(action.get("content") or "")[:50000]
                if not title:
                    raise RuntimeError("wordpress_deploy_manifest_invalid")
                found = self._run_wp(
                    "post", "list", "--post_type=page", f"--name={slug}",
                    "--field=ID", "--format=csv",
                ).stdout.strip().splitlines()
                page_id = next((line.strip() for line in found if line.strip().isdigit()), "")
                if page_id:
                    self._run_wp(
                        "post", "update", page_id, f"--post_title={title}",
                        f"--post_content={content}", "--post_status=publish",
                    )
                    actions_done.append(f"update_page:{slug}")
                else:
                    self._run_wp(
                        "post", "create", "--post_type=page", f"--post_name={slug}",
                        f"--post_title={title}", f"--post_content={content}",
                        "--post_status=publish",
                    )
                    actions_done.append(f"create_page:{slug}")
            elif action_type == "health_path":
                value = str(action.get("path") or "").strip()
                if not value.startswith("/") or "//" in value or ".." in value:
                    raise RuntimeError("wordpress_deploy_manifest_invalid")
                health_path = value
                actions_done.append(f"health_path:{value}")
        return actions_done, health_path

    def _health_url(self, request: ProjectDeploymentRequest, health_path: str | None) -> str | None:
        base = self.health_base_url
        if not base:
            target = str(request.deployment_target or "").strip()
            if target.startswith("http://") or target.startswith("https://"):
                base = target.rstrip("/")
        if not base:
            return None
        return base + (health_path or "/")

    def _check_health(self, url: str) -> bool:
        try:
            response = self._urlopen(url, timeout=15)
            status = int(getattr(response, "status", 200))
            return 200 <= status < 400
        except Exception:
            return False

    def deploy(self, request: ProjectDeploymentRequest) -> ProjectDeploymentResult:
        if self._ROUTINE_REQUIRED not in request.routine_operations:
            return ProjectDeploymentResult(
                success=False,
                adapter=self.name,
                deployed_revision=request.revision,
                diagnostics=("project_deploy_not_authorized",),
            )
        repository_root = Path(request.repository_root).expanduser().resolve()
        actions: list[str] = []
        try:
            manifest = self._manifest(repository_root)
            for kind, package in self._packages(request.changed_files):
                actions.append(self._atomic_copy_package(
                    repository_root=repository_root,
                    kind=kind,
                    package=package,
                ))
            manifest_actions, health_path = self._apply_manifest(manifest)
            actions.extend(manifest_actions)
        except Exception as exc:
            return ProjectDeploymentResult(
                success=False,
                adapter=self.name,
                deployed_revision=request.revision,
                changed_files=request.changed_files,
                actions=tuple(actions),
                diagnostics=(f"deployment_failed:{type(exc).__name__}",),
            )

        url = self._health_url(request, health_path)
        health_ok = self._check_health(url) if url else None
        if health_ok is False:
            return ProjectDeploymentResult(
                success=False,
                adapter=self.name,
                deployed_revision=request.revision,
                changed_files=request.changed_files,
                actions=tuple(actions),
                health_ok=False,
                health_url=url,
                diagnostics=("wordpress_healthcheck_failed",),
            )
        return ProjectDeploymentResult(
            success=True,
            adapter=self.name,
            deployed_revision=request.revision,
            changed_files=request.changed_files,
            actions=tuple(actions),
            health_ok=health_ok,
            health_url=url,
        )

    def verify_health(self, request: ProjectDeploymentRequest) -> ProjectDeploymentResult:
        url = self._health_url(request, None)
        ok = self._check_health(url) if url else None
        return ProjectDeploymentResult(
            success=ok is not False,
            adapter=self.name,
            deployed_revision=request.revision,
            health_ok=ok,
            health_url=url,
        )

    def rollback(self, request: ProjectDeploymentRequest, revision: str) -> ProjectDeploymentResult:
        return ProjectDeploymentResult(
            success=False,
            adapter=self.name,
            deployed_revision=request.revision,
            rollback_revision=revision,
            diagnostics=("wordpress_revision_rollback_requires_orchestrator",),
        )


__all__ = ["WordPressProjectAdapter"]
