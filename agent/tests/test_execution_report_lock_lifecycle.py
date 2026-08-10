import tempfile
import unittest
from pathlib import Path

from agent.execution.execution_report_writer import _InterProcessFileLock


class ExecutionReportLockLifecycleTests(unittest.TestCase):
    def test_context_manager_closes_handle_after_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock = _InterProcessFileLock(str(Path(tmp) / "reports.lock"))

            with lock:
                self.assertIsNotNone(lock._fh)
                self.assertFalse(lock._fh.closed)

            self.assertIsNone(lock._fh)
            self.assertIsNone(lock._owner)

    def test_lock_can_be_reacquired_after_handle_close(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock = _InterProcessFileLock(str(Path(tmp) / "reports.lock"))

            with lock:
                first_handle = lock._fh
                self.assertIsNotNone(first_handle)

            self.assertTrue(first_handle.closed)
            self.assertIsNone(lock._fh)

            with lock:
                second_handle = lock._fh
                self.assertIsNotNone(second_handle)
                self.assertIsNot(first_handle, second_handle)
                self.assertFalse(second_handle.closed)

            self.assertTrue(second_handle.closed)
            self.assertIsNone(lock._fh)


if __name__ == "__main__":
    unittest.main()
