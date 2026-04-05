"""
Test: Signal Duplication Verification

Verifies that the signal architecture fix is effective.
After the fix:
- TransactionManager.jobCompleted should be the ONLY source for granular job events.
- FileOperations should NOT have operationCompleted signal.
- For a single operation, UI should receive exactly 1 event (not 2).
"""

import sys
import os
import unittest
from unittest.mock import MagicMock
from PySide6.QtCore import QCoreApplication

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.managers import FileOperations
from core.managers import TransactionManager
from core.registry import BackendRegistry
from core.backends.gio.backend import GIOBackend
from core.models.file_job import FileOperationSignals


class TestSignalDuplicationFixed(unittest.TestCase):
    def setUp(self):
        self.app = QCoreApplication.instance() or QCoreApplication(sys.argv)
        signals = FileOperationSignals()
        self.registry = BackendRegistry()
        self.registry.set_default_io(GIOBackend())
        self.file_ops = FileOperations()
        self.file_ops.setRegistry(self.registry)
        self.tm = TransactionManager()
        self.tm.setFileOperations(self.file_ops)

    def tearDown(self):
        self.file_ops.shutdown()

    def test_legacy_signal_removed(self):
        """Verify that FileOperations no longer has operationCompleted signal."""
        print("\n[TEST] Checking for Legacy Signal Removal...")

        has_legacy = hasattr(self.file_ops, "operationCompleted")

        if has_legacy:
            print(
                "  ❌ FAIL: operationCompleted signal still exists on FileOperations!"
            )
        else:
            print("  ✅ PASS: operationCompleted signal has been removed.")

        self.assertFalse(
            has_legacy, "Legacy operationCompleted signal should be removed"
        )

    def test_job_completed_signal_exists(self):
        """Verify that TransactionManager has the new jobCompleted signal."""
        print("\n[TEST] Checking for New jobCompleted Signal...")

        has_new = hasattr(self.tm, "jobCompleted")

        if has_new:
            print("  ✅ PASS: jobCompleted signal exists on TransactionManager.")
        else:
            print("  ❌ FAIL: jobCompleted signal missing from TransactionManager!")

        self.assertTrue(has_new, "TransactionManager should have jobCompleted signal")

    def test_single_signal_for_orphan_operation(self):
        """Verify that orphan operations (no transaction) emit jobCompleted."""
        print("\n[TEST] Checking Orphan Operation Signal...")

        job_completed_mock = MagicMock()
        self.tm.jobCompleted.connect(job_completed_mock)

        # Simulate an orphan finished signal (no tid)
        self.file_ops._signals.finished.emit(
            "", "job_123", "rename", "/path/to/newname", True, "Success", None
        )
        self.app.processEvents()

        calls = job_completed_mock.call_count
        print(f"  -> jobCompleted signals received: {calls}")

        if calls == 1:
            print("  ✅ PASS: Exactly 1 jobCompleted signal for orphan operation.")
        else:
            print(f"  ❌ FAIL: Expected 1 signal, got {calls}.")

        self.assertEqual(
            calls, 1, "Orphan operation should emit exactly 1 jobCompleted"
        )

    def test_no_double_counting_in_transaction(self):
        """Verify no double counting for operations inside a transaction."""
        print("\n[TEST] Checking Transaction Operation (No Double Count)...")

        job_completed_mock = MagicMock()
        transaction_progress_mock = MagicMock()

        self.tm.jobCompleted.connect(job_completed_mock)
        self.tm.transactionProgress.connect(transaction_progress_mock)

        # Start a real transaction
        tid = self.tm.startTransaction("Test Batch")
        job_id = "job_456"
        self.tm.addOperation(tid, "copy", "/src", "/dest", job_id)

        # Simulate worker finishing
        self.file_ops._signals.finished.emit(
            tid, job_id, "copy", "/dest/file", True, "Success", None
        )
        self.app.processEvents()

        job_calls = job_completed_mock.call_count
        progress_calls = transaction_progress_mock.call_count

        print(f"  -> jobCompleted signals: {job_calls}")
        print(f"  -> transactionProgress signals: {progress_calls}")

        # Both signals fire, but they serve DIFFERENT purposes:
        # - jobCompleted => For "select this file" UI logic
        # - transactionProgress => For "update progress bar" logic
        # This is NOT double counting because they convey different information.

        self.assertEqual(job_calls, 1, "Should have exactly 1 jobCompleted")
        self.assertGreaterEqual(
            progress_calls, 1, "Should have at least 1 transactionProgress"
        )

        print("  ✅ PASS: Signals are distinct and serve different purposes.")


if __name__ == "__main__":
    unittest.main()
