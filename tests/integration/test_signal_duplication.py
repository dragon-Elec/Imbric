"""
Integration test: Signal Duplication Verification

Verifies that the signal architecture fix is effective:
- TransactionManager.jobCompleted is the ONLY source for granular job events
- FileOperations.operationCompleted signal has been removed
- For a single operation, UI receives exactly 1 event (not 2)

MARKER: @pytest.mark.private_api
JUSTIFICATION: Directly emits on private _signals object to test the fix.
                This is the most direct way to verify the signal was removed.
"""

import pytest
from unittest.mock import MagicMock


class TestSignalArchitecture:
    """Test signal deduplication architecture."""

    def test_legacy_signal_removed(self, file_ops):
        """
        Verify that FileOperations no longer has operationCompleted signal.

        This test directly checks the existence of the legacy signal.
        """
        has_legacy = hasattr(file_ops, "operationCompleted")
        assert not has_legacy, (
            "Legacy operationCompleted signal should be removed from FileOperations"
        )

    def test_job_completed_signal_exists(self, transaction_manager):
        """Verify that TransactionManager has the new jobCompleted signal."""
        has_new = hasattr(transaction_manager, "jobCompleted")
        assert has_new, "TransactionManager should have jobCompleted signal"

    def test_single_signal_for_orphan_operation(self, file_ops_system, qapp):
        """
        Verify that orphan operations (no transaction) emit jobCompleted.
        """
        tm = file_ops_system["tm"]
        file_ops = file_ops_system["file_ops"]

        job_completed_mock = MagicMock()
        tm.jobCompleted.connect(job_completed_mock)

        # Simulate orphan finished signal (no tid)
        file_ops._signals.finished.emit(
            "", "job_123", "rename", "/path/to/newname", True, "Success", None
        )
        qapp.processEvents()

        assert job_completed_mock.call_count == 1, (
            "Orphan operation should emit exactly 1 jobCompleted"
        )

    def test_transaction_operation_no_double_count(self, transaction_manager, qapp):
        """
        Verify no double counting for operations inside a transaction.

        Both jobCompleted and transactionProgress fire, but they serve
        DIFFERENT purposes:
        - jobCompleted => For "select this file" UI logic
        - transactionProgress => For "update progress bar" UI logic
        """
        job_completed_mock = MagicMock()
        progress_mock = MagicMock()

        transaction_manager.jobCompleted.connect(job_completed_mock)
        transaction_manager.transactionProgress.connect(progress_mock)

        # Start a real transaction
        tid = transaction_manager.startTransaction("Test Batch")
        transaction_manager.addOperation(tid, "copy", "/src", "/dest", "job_456")

        # Get file_ops from transaction manager
        file_ops = transaction_manager._file_ops

        # Simulate worker finishing
        file_ops._signals.finished.emit(
            tid, "job_456", "copy", "/dest/file", True, "Success", None
        )
        qapp.processEvents()

        # Both signals fire but for different purposes
        assert job_completed_mock.call_count == 1, "Should have exactly 1 jobCompleted"
        assert progress_mock.call_count >= 1, (
            "Should have at least 1 transactionProgress"
        )

    def test_error_does_not_emit_job_completed(self, file_ops_system, qapp):
        """
        Verify that failed operations do NOT emit jobCompleted.
        jobCompleted should only fire on success.
        """
        tm = file_ops_system["tm"]
        file_ops = file_ops_system["file_ops"]

        job_completed_mock = MagicMock()
        tm.jobCompleted.connect(job_completed_mock)

        # Simulate failed operation
        file_ops._signals.finished.emit(
            "", "job_fail", "copy", "/path", False, "Permission denied", None
        )
        qapp.processEvents()

        assert job_completed_mock.call_count == 0, (
            "Failed operation should NOT emit jobCompleted"
        )
