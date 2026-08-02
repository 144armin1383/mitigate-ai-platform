from __future__ import annotations

import io
import json
import os
import threading
import time
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Callable

from agent.projects.project_registry import (
    ProjectRegistry,
    ProjectValidationError,
    DuplicateProjectError,
    UnknownProjectError,
    ProtectedDeletionError,
    CrossProjectViolation,
    RegistryStorageCorrupted,
)


def make_git_repo(root: Path) -> Path:
    # Create a minimal filesystem structure that looks like a git repo without any operations
    root.mkdir(parents=True, exist_ok=True)
    (root / ".git").mkdir(parents=True, exist_ok=True)
    # simulate HEAD file inside .git for realistic shape
    with open(root / ".git" / "HEAD", "w", encoding="utf-8") as f:
        f.write("ref: refs/heads/main\n")
    return root


def example_profile(project_id: str, repo: Path) -> dict:
    return {
        "project_id": project_id,
        "display_name": f"Project {project_id}",
        "repository_root": str(repo),
        "default_branch": "main",
        "project_type": "wordpress",
        "mission_queue_path": "queue",
        "conversations_path": "conversations",
        "uploads_metadata_path": "uploads/metadata.json",
        "uploads_directory": "uploads/files",
        "events_path": "events",
        "reports_path": "reports",
        "worker_heartbeat_path": "worker/heartbeat",
        "deployment_target": "staging",
        "allowed_domains": ["example.com"],
        "enabled_providers": ["openai:chat"],
        "policy_profile": "default",
        "created_at": "2024-01-01T00:00:00.000000Z",
        "updated_at": "2024-01-01T00:00:00.000000Z",
        "status": "active",
    }


class MonotonicTestClock:
    def __init__(self, start: datetime | None = None) -> None:
        self._now = start or datetime(2024, 1, 1, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        # Return the same timestamp on first two calls, then advance; to test monotonic updated_at
        current = self._now
        # Do not advance here to simulate equal timestamps; callers will ensure monotonicity
        return current

    def advance(self, us: int = 1) -> None:
        self._now = self._now + timedelta(microseconds=us)


class TestProjectRegistry(unittest.TestCase):
    def setUp(self) -> None:
        self.td = TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        self.root = Path(self.td.name)
        self.repo = make_git_repo(self.root / "repo")
        self.clock = MonotonicTestClock()
        self.registry = ProjectRegistry(self.root / "storage", clock=self.clock)

    def test_project_creation(self) -> None:
        p = example_profile("site_2", self.repo)
        created = self.registry.create_project(p)
        self.assertEqual(created["project_id"], "site_2")
        self.assertIn("created_at", created)
        self.assertIn("updated_at", created)

    def test_deterministic_project_listing(self) -> None:
        p1 = example_profile("b", self.repo)
        p2 = example_profile("r1", self.repo)
        self.registry.create_project(p2)
        self.registry.create_project(p1)
        lst = self.registry.list_projects()
        self.assertEqual([p["project_id"] for p in lst], ["b", "r1"])  # sorted by project_id

    def test_duplicate_project_rejection(self) -> None:
        p = example_profile("timefx-web", self.repo)
        self.registry.create_project(p)
        with self.assertRaises(DuplicateProjectError):
            self.registry.create_project(p)

    def test_invalid_project_identifiers(self) -> None:
        bad_ids = [
            "A",
            "site..",
            "-bad",
            "bad-",
            "bad/ok",
            "bad\\ok",
            "a b",
        ]
        for bid in bad_ids:
            p = example_profile(bid, self.repo)
            with self.assertRaises(ProjectValidationError):
                self.registry.create_project(p)

    def test_path_traversal_rejection(self) -> None:
        p = example_profile("safe1", self.repo)
        p["mission_queue_path"] = "../escape"
        self.registry.create_project(p)
        with self.assertRaises(ProjectValidationError):
            self.registry.resolve_project_paths("safe1")

    def test_project_update(self) -> None:
        p = example_profile("upd1", self.repo)
        created = self.registry.create_project(p)
        created_at = created["created_at"]
        updated_at1 = created["updated_at"]
        # Clock returns the same time; registry must advance deterministically
        updated = self.registry.update_project("upd1", {"display_name": "Updated"})
        self.assertEqual(updated["created_at"], created_at)
        updated_at2 = updated["updated_at"]
        self.assertNotEqual(updated_at1, updated_at2)
        # Ensure updated_at moves forward lexicographically
        self.assertGreater(updated_at2, updated_at1)

    def test_suspend_and_activate(self) -> None:
        p = example_profile("s1", self.repo)
        self.registry.create_project(p)
        s = self.registry.suspend_project("s1")
        self.assertEqual(s["status"], "suspended")
        a = self.registry.activate_project("s1")
        self.assertEqual(a["status"], "active")

    def test_archive(self) -> None:
        p = example_profile("arch1", self.repo)
        self.registry.create_project(p)
        ar = self.registry.archive_project("arch1")
        self.assertEqual(ar["status"], "archived")

    def test_protected_active_deletion(self) -> None:
        p = example_profile("del1", self.repo)
        self.registry.create_project(p)
        with self.assertRaises(ProtectedDeletionError):
            self.registry.delete_project("del1")

    def test_forced_deletion(self) -> None:
        p = example_profile("del2", self.repo)
        self.registry.create_project(p)
        self.registry.delete_project("del2", force=True)
        with self.assertRaises(UnknownProjectError):
            self.registry.get_project("del2")

    def test_atomic_persistence_and_restart_recovery(self) -> None:
        p1 = example_profile("b", self.repo)
        p2 = example_profile("r1", self.repo)
        self.registry.create_project(p1)
        self.registry.create_project(p2)
        # Restart: new instance should load previous projects
        reg2 = ProjectRegistry(self.root / "storage", clock=self.clock)
        lst = reg2.list_projects()
        self.assertEqual([p["project_id"] for p in lst], ["b", "r1"])  # deterministic

    def test_corrupted_storage_rejection(self) -> None:
        # Corrupt the registry file
        reg_file = self.root / "storage" / "project_registry.json"
        reg_file.write_text("{not-json}", encoding="utf-8")
        with self.assertRaises(RegistryStorageCorrupted):
            ProjectRegistry(self.root / "storage")

    def test_deterministic_serialization(self) -> None:
        p1 = example_profile("a1", self.repo)
        p2 = example_profile("a2", self.repo)
        self.registry.create_project(p1)
        self.registry.create_project(p2)
        reg_file = self.root / "storage" / "project_registry.json"
        content1 = reg_file.read_text(encoding="utf-8")
        # Touch persistence by updating a non-material field to same value (no-op state change)
        _ = self.registry.suspend_project("a1")
        _ = self.registry.activate_project("a1")
        content2 = reg_file.read_text(encoding="utf-8")
        self.assertIsInstance(content1, str)
        self.assertIsInstance(content2, str)
        # The JSON object keys order and determinism must be stable for same state count of projects
        self.assertEqual(json.loads(content1).keys(), json.loads(content2).keys())

    def test_immutable_project_context(self) -> None:
        p = example_profile("imm1", self.repo)
        self.registry.create_project(p)
        ctx = self.registry.get_context("imm1")
        with self.assertRaises(Exception):
            # type: ignore[attr-defined]
            ctx.project_id = "new"
        self.assertEqual(ctx.project_id, "imm1")

    def test_two_independent_project_profiles_and_isolation(self) -> None:
        p1 = example_profile("p1", self.repo)
        p2 = example_profile("p2", self.repo)
        self.registry.create_project(p1)
        self.registry.create_project(p2)
        c1 = self.registry.get_context("p1")
        c2 = self.registry.get_context("p2")
        # All critical paths differ and are under isolated base dirs
        self.assertNotEqual(c1.queue_path, c2.queue_path)
        self.assertNotEqual(c1.conversations_path, c2.conversations_path)
        self.assertNotEqual(c1.uploads_directory, c2.uploads_directory)
        self.assertNotEqual(c1.events_path, c2.events_path)
        self.assertNotEqual(c1.reports_path, c2.reports_path)
        self.assertNotEqual(c1.worker_heartbeat_path, c2.worker_heartbeat_path)
        base = self.registry.projects_base_dir().resolve()
        self.assertTrue(str(c1.queue_path.resolve()).startswith(str((base / "p1").resolve())))
        self.assertTrue(str(c2.queue_path.resolve()).startswith(str((base / "p2").resolve())))
        # Cross-project rejections
        with self.assertRaises(CrossProjectViolation):
            self.registry.ensure_same_project("p1", "p2", what="mission")

    def test_queue_conversation_upload_event_report_worker_isolation(self) -> None:
        p1 = example_profile("iso1", self.repo)
        p2 = example_profile("iso2", self.repo)
        self.registry.create_project(p1)
        self.registry.create_project(p2)
        c1 = self.registry.get_context("iso1")
        c2 = self.registry.get_context("iso2")
        self.assertNotEqual(c1.queue_path, c2.queue_path)
        self.assertNotEqual(c1.conversations_path, c2.conversations_path)
        self.assertNotEqual(c1.uploads_metadata_path, c2.uploads_metadata_path)
        self.assertNotEqual(c1.uploads_directory, c2.uploads_directory)
        self.assertNotEqual(c1.events_path, c2.events_path)
        self.assertNotEqual(c1.reports_path, c2.reports_path)
        self.assertNotEqual(c1.worker_heartbeat_path, c2.worker_heartbeat_path)

    def test_repository_root_and_branch_selection(self) -> None:
        p = example_profile("repo1", self.repo)
        p["default_branch"] = "develop"
        self.registry.create_project(p)
        ctx = self.registry.get_context("repo1")
        self.assertEqual(ctx.repository_root, self.repo.resolve())
        self.assertEqual(ctx.default_branch, "develop")

    def test_mitigate_profile_is_data_driven(self) -> None:
        example_path = Path("agent/projects/mitigate.project.example.json")
        self.assertTrue(example_path.exists(), "Mitigate example profile must exist")
        raw = json.loads(example_path.read_text(encoding="utf-8"))
        # It must not contain secrets and must be valid JSON structure
        self.assertIn("project_id", raw)
        self.assertIn("enabled_providers", raw)
        self.assertNotIn("api_key", raw)
        self.assertNotIn("token", raw)
        # Use it as a template (override repository_root to a real test repo path)
        raw["project_id"] = "mit1"
        raw["repository_root"] = str(self.repo)
        reg2 = ProjectRegistry(self.root / "storage2")
        reg2.create_project(raw)
        self.assertIn("mit1", [p["project_id"] for p in reg2.list_projects()])

    def test_add_second_project_without_core_changes(self) -> None:
        p1 = example_profile("snp1", self.repo)
        p2 = example_profile("snp2", self.repo)
        self.registry.create_project(p1)
        # Add second in a separate thread with bounded timeout to ensure no deadlock
        result: dict[str, str] = {}

        def worker() -> None:
            try:
                self.registry.create_project(p2)
                result["ok"] = "1"
            except Exception as e:  # pragma: no cover - ensure test captures result
                result["err"] = str(e)

        t = threading.Thread(target=worker)
        t.daemon = True
        t.start()
        t.join(timeout=2.0)
        self.assertFalse(t.is_alive(), "operation should complete promptly without blocking")
        self.assertIn("ok", result)

    def test_secret_values_are_never_serialized(self) -> None:
        p = example_profile("nosecret", self.repo)
        self.registry.create_project(p)
        reg_file = self.root / "storage" / "project_registry.json"
        content = reg_file.read_text(encoding="utf-8")
        self.assertNotIn("api_key", content)
        self.assertNotIn("token", content)
        self.assertNotIn("sk-", content)

    def test_unrestricted_paths_absent_from_safe_public_responses(self) -> None:
        p = example_profile("pub1", self.repo)
        self.registry.create_project(p)
        events = self.registry.latest_events()
        root_str = str(self.root)
        for evt in events:
            s = json.dumps(evt)
            self.assertNotIn(root_str, s)

    def test_unrelated_files_remain_unchanged(self) -> None:
        other = self.root / "storage" / "unrelated.txt"
        other.parent.mkdir(parents=True, exist_ok=True)
        other.write_text("keep", encoding="utf-8")
        p = example_profile("keep1", self.repo)
        self.registry.create_project(p)
        # Update and delete unrelated to ensure file persists unchanged
        self.registry.update_project("keep1", {"display_name": "K"})
        self.assertEqual(other.read_text(encoding="utf-8"), "keep")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
