import json
import tempfile
import unittest
from pathlib import Path

from agent.runtime.mission_queue import MissionQueue


class TestRuntimeQueueBootstrap(unittest.TestCase):

    def test_missing_queue_file_is_valid_empty_queue(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "missions.json"

            self.assertFalse(path.exists())

            queue = MissionQueue(str(path))

            self.assertEqual(queue.list(), [])

    def test_persisted_empty_queue_uses_mapping(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "missions.json"

            queue = MissionQueue(str(path))

            # Force a canonical persistence cycle through the queue itself.
            queue.enqueue_from_planner([])

            if path.exists():
                payload = json.loads(path.read_text(encoding="utf-8"))

                self.assertIsInstance(payload, dict)
                self.assertIn("missions", payload)
                self.assertIsInstance(payload["missions"], dict)

                reloaded = MissionQueue(str(path))
                self.assertEqual(reloaded.list(), [])

    def test_legacy_list_shaped_missions_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "missions.json"

            path.write_text(
                json.dumps({"missions": []}),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ValueError,
                "Persisted missions must be a mapping",
            ):
                MissionQueue(str(path))


if __name__ == "__main__":
    unittest.main()
