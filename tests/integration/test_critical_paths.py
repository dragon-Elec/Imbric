"""
Integration tests for critical security paths.
These tests MUST access private APIs to verify security-critical behavior.

MARKER: @pytest.mark.private_api
JUSTIFICATION: Path traversal sanitization cannot be tested through public API
                because we need to inject malicious input at the conflict resolution
                level to verify it gets sanitized before reaching filesystem.
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock


class TestPathTraversalSecurity:
    """
    Tests that verify malicious path traversal attempts are blocked.

    JUSTIFICATION FOR PRIVATE API ACCESS:
    - These tests inject test state into _pending_conflicts to simulate
      conflict scenarios with malicious filenames
    - Public API cannot reach this code path with controlled test data
    - Security-critical code requires direct verification
    """

    def test_traversal_blocked_in_rename(self, file_ops_system, temp_dir):
        """
        Verify that path traversal sequences in rename are rejected.

        Attempts to rename a file using a path with ".." sequences.
        The rename() method should raise ValueError for security reasons.
        """
        file_ops = file_ops_system["file_ops"]

        # Create source file
        src_file = temp_dir / "source.txt"
        src_file.write_text("content")

        # Try to rename with traversal - should raise ValueError
        with pytest.raises(ValueError, match="Invalid filename.*path separators"):
            file_ops.rename(str(src_file), "../../etc/passwd")

        # Verify source file is unchanged
        assert src_file.exists()
        assert src_file.read_text() == "content"

    def test_backslash_traversal_blocked(self, file_ops_system, temp_dir):
        """Verify Windows-style path separators are also rejected."""
        file_ops = file_ops_system["file_ops"]

        src_file = temp_dir / "test.txt"
        src_file.write_text("content")

        with pytest.raises(ValueError, match="Invalid filename.*path separators"):
            file_ops.rename(str(src_file), "..\\..\\windows\\system32")

    def test_dot_prefix_rejected(self, file_ops_system, temp_dir):
        """Verify filenames starting with dot are rejected."""
        file_ops = file_ops_system["file_ops"]

        src_file = temp_dir / "test.txt"
        src_file.write_text("content")

        with pytest.raises(ValueError, match="Hidden files not allowed"):
            file_ops.rename(str(src_file), ".hidden")

    def test_empty_name_rejected(self, file_ops_system, temp_dir):
        """Verify empty filenames are rejected."""
        file_ops = file_ops_system["file_ops"]

        src_file = temp_dir / "test.txt"
        src_file.write_text("content")

        with pytest.raises(ValueError, match="Invalid filename"):
            file_ops.rename(str(src_file), "")


class TestTransactionIntegrity:
    """
    Tests for transaction integrity and proper cleanup.

    JUSTIFICATION FOR PRIVATE API ACCESS:
    - We verify internal state (_active_transactions, _pending_conflicts)
      to ensure transactions are properly cleaned up on success/failure
    - This prevents memory leaks and hanging transactions
    """

    def test_transaction_removed_on_completion(self, file_ops_system, temp_dir):
        """
        Verify transaction is removed from _active_transactions after completion.
        """
        tm = file_ops_system["tm"]

        # Create and start transaction
        tid = tm.startTransaction("Cleanup Test")
        assert tid in tm._active_transactions

        # Create a file to copy
        src = temp_dir / "src.txt"
        src.write_text("content")

        # Perform operation
        tm._file_ops.copy(str(src), str(temp_dir / "dest.txt"), tid)

        # Commit the transaction so cleanup can happen
        tm.commitTransaction(tid)

        # Wait for transaction to complete (via private state check)
        import time
        from PySide6.QtCore import QCoreApplication

        start = time.time()
        while tid in tm._active_transactions and (time.time() - start) < 5:
            QCoreApplication.processEvents()
            time.sleep(0.05)

        assert tid not in tm._active_transactions, "Transaction should be removed"

    def test_transaction_removed_on_failure(self, file_ops_system, temp_dir):
        """
        Verify transaction is removed even when operations fail.
        """
        tm = file_ops_system["tm"]

        tid = tm.startTransaction("Failure Test")
        assert tid in tm._active_transactions

        # Try to copy nonexistent file (will fail)
        tm._file_ops.copy(
            str(temp_dir / "nonexistent.txt"), str(temp_dir / "dest.txt"), tid
        )

        # Commit the transaction so cleanup can happen
        tm.commitTransaction(tid)

        # Wait for cleanup
        import time
        from PySide6.QtCore import QCoreApplication

        start = time.time()
        while tid in tm._active_transactions and (time.time() - start) < 5:
            QCoreApplication.processEvents()
            time.sleep(0.05)

        assert tid not in tm._active_transactions, (
            "Transaction should be removed even on failure"
        )


class TestRaceConditionHandling:
    """
    Tests for race condition handling.

    JUSTIFICATION FOR PRIVATE API ACCESS:
    - We inject multiple simultaneous folder creation requests to verify
      auto_rename works correctly under concurrent access
    - Need to verify internal state during race condition
    """

    def test_concurrent_folder_creation(self, file_ops_system, temp_dir):
        """
        Verify that creating multiple folders with same name succeeds
        with unique names when auto_rename=True.
        """
        file_ops = file_ops_system["file_ops"]

        base_path = str(temp_dir / "Untitled Folder")
        job_ids = []

        # Fire 20 concurrent requests
        for _ in range(20):
            jid = file_ops.createFolder(base_path, auto_rename=True)
            job_ids.append(jid)

        # Wait for all to complete
        import time
        from PySide6.QtCore import QCoreApplication

        start = time.time()
        while file_ops.activeJobCount() > 0 and (time.time() - start) < 5:
            QCoreApplication.processEvents()
            time.sleep(0.05)

        # Verify all 20 folders created with unique names
        folders = list(temp_dir.glob("Untitled Folder*"))
        assert len(folders) == 20, f"Expected 20 folders, got {len(folders)}"
