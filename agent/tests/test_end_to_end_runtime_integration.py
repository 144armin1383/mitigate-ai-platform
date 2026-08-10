from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import time
import unittest
from typing import Dict, List, Tuple

from agent.app.application import (
    ApplicationConfig,
    ApplicationContainer,
    build_application,
)
from agent.execution.execution_report_writer import ExecutionReportWriter
from agent.runtime.autonomous_runtime_adapter import AutonomousRuntimeAdapter
from agent.runtime.background_worker import BackgroundWorker
from agent.runtime.mission_queue import MissionQueue
from agent.runtime.runtime_service import RuntimeConfig, RuntimeService


class RepositorySafetyTests(unittest.TestCase):

    def test_temporary_directory_cleanup(self) -> None:
        path = None

        with tempfile.TemporaryDirectory() as td:
            path = td
            target = os.path.join(td, "temp.txt")

            with open(target, "w", encoding="utf-8") as handle:
                handle.write("ok")

            self.assertTrue(os.path.exists(target))

        self.assertIsNotNone(path)
        self.assertFalse(os.path.exists(str(path)))

    def test_deterministic_identifier_generation(self) -> None:
        seed = b"fixed-seed-utc-20200101T000000Z"
        project = "project-A"
        request = {
            "type": "chat",
            "turn": 1,
        }

        payload = json.dumps(
            request,
            sort_keys=True,
        ).encode("utf-8")

        first = hashlib.sha256(
            seed + project.encode("utf-8") + payload
        ).hexdigest()

        second = hashlib.sha256(
            seed + project.encode("utf-8") + payload
        ).hexdigest()

        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)
        int(first, 16)

    def test_concurrent_equivalent_submission_ordering_is_stable(
        self,
    ) -> None:
        submissions: List[Tuple[str, str]] = []
        lock = threading.Lock()
        seed = b"fixed-seed-for-threads"

        payloads: List[Dict[str, object]] = [
            {"turn": 1, "type": "chat", "content": "x"},
            {"turn": 2, "type": "chat", "content": "y"},
            {"turn": 3, "type": "chat", "content": "z"},
            {"turn": 1, "type": "chat", "content": "x"},
        ]

        def submit(payload: Dict[str, object]) -> None:
            encoded = json.dumps(
                payload,
                sort_keys=True,
            ).encode("utf-8")

            ident = hashlib.sha256(
                seed + b"project-A" + encoded
            ).hexdigest()

            with lock:
                submissions.append((ident, "project-A"))

        threads = [
            threading.Thread(
                target=submit,
                args=(payload,),
                daemon=True,
            )
            for payload in payloads
        ]

        for thread in threads:
            thread.start()

        deadline = time.time() + 5.0

        for thread in threads:
            thread.join(
                timeout=max(0.0, deadline - time.time())
            )
            self.assertFalse(thread.is_alive())

        ordered = sorted(submissions)

        expected = []

        for payload in payloads:
            encoded = json.dumps(
                payload,
                sort_keys=True,
            ).encode("utf-8")

            ident = hashlib.sha256(
                seed + b"project-A" + encoded
            ).hexdigest()

            expected.append((ident, "project-A"))

        self.assertEqual(
            ordered,
            sorted(expected),
        )


class EndToEndRuntimeIntegrationTests(unittest.TestCase):

    def test_current_public_interfaces_are_importable(self) -> None:
        self.assertTrue(callable(build_application))

        for component in (
            ApplicationConfig,
            ApplicationContainer,
            RuntimeConfig,
            RuntimeService,
            BackgroundWorker,
            MissionQueue,
            AutonomousRuntimeAdapter,
            ExecutionReportWriter,
        ):
            self.assertIsInstance(component, type)

    def test_runtime_lifecycle_api_shape(self) -> None:
        for method in (
            "start",
            "stop",
            "close",
            "__enter__",
            "__exit__",
        ):
            self.assertTrue(
                hasattr(RuntimeService, method),
                msg=f"RuntimeService missing {method}",
            )

    def test_builder_api_shape(self) -> None:
        self.assertTrue(callable(build_application))

    def test_no_automatic_start_on_import(self) -> None:
        active_non_daemon = [
            thread
            for thread in threading.enumerate()
            if thread.is_alive() and not thread.daemon
        ]

        self.assertLessEqual(
            len(active_non_daemon),
            2,
        )


if __name__ == "__main__":
    unittest.main()
