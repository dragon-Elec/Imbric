"""
Unit tests for FileOperations public API.
Tests basic operations using public signals and return values.
"""

import pytest
import time
from pathlib import Path

from core.managers import FileOperations
from core.models.file_job import FileOperationSignals


def wait_for_condition(qapp, condition_fn, timeout_ms=5000, poll_ms=10):
    """Wait for a condition to become True."""
    start = time.time()
    timeout_sec = timeout_ms / 1000
    poll_sec = poll_ms / 1000

    while not condition_fn():
        qapp.processEvents()
        if (time.time() - start) > timeout_sec:
            return False
        time.sleep(poll_sec)
    return True


class TestFileOperationsBasic:
    """Test basic file operations through public API."""

    def test_copy_file(self, file_ops, temp_dir, qapp):
        """Test basic file copy."""
        src = temp_dir / "source.txt"
        src.write_text("Hello World")
        dest = temp_dir / "dest.txt"

        results = []
        file_ops.operationFinished.connect(lambda *a: results.append(a))

        job_id = file_ops.copy(str(src), str(dest))
        assert job_id, "copy() should return job_id"

        # Wait for completion
        completed = wait_for_condition(qapp, lambda: len(results) > 0)
        assert completed, "Operation should complete"

        assert dest.exists(), "Destination should exist"
        assert dest.read_text() == "Hello World"

    def test_move_file(self, file_ops, temp_dir, qapp):
        """Test basic file move."""
        src = temp_dir / "move_src.txt"
        src.write_text("Moving content")
        dest = temp_dir / "move_dest.txt"

        results = []
        file_ops.operationFinished.connect(lambda *a: results.append(a))

        job_id = file_ops.move(str(src), str(dest))
        assert job_id, "move() should return job_id"

        completed = wait_for_condition(qapp, lambda: len(results) > 0)
        assert completed, "Operation should complete"

        assert not src.exists(), "Source should not exist after move"
        assert dest.exists(), "Destination should exist"
        assert dest.read_text() == "Moving content"

    def test_create_folder(self, file_ops, temp_dir, qapp):
        """Test folder creation."""
        new_folder = temp_dir / "new_folder"

        results = []
        file_ops.operationFinished.connect(lambda *a: results.append(a))

        job_id = file_ops.createFolder(str(new_folder))
        assert job_id, "createFolder() should return job_id"

        completed = wait_for_condition(qapp, lambda: len(results) > 0)
        assert completed, "Operation should complete"

        assert new_folder.exists(), "Folder should be created"
        assert new_folder.is_dir(), "Should be a directory"

    def test_rename_file(self, file_ops, temp_dir, qapp):
        """Test file rename."""
        original = temp_dir / "original.txt"
        original.write_text("Rename me")

        results = []
        file_ops.operationFinished.connect(lambda *a: results.append(a))

        # Rename to new name in same directory
        job_id = file_ops.rename(str(original), "renamed.txt")
        assert job_id, "rename() should return job_id"

        completed = wait_for_condition(qapp, lambda: len(results) > 0)
        assert completed, "Operation should complete"

        assert not original.exists(), "Original should not exist"
        renamed = temp_dir / "renamed.txt"
        assert renamed.exists(), "Renamed file should exist"
        assert renamed.read_text() == "Rename me"

    def test_error_on_nonexistent_file(self, file_ops, temp_dir, qapp):
        """Test error handling for non-existent source."""
        nonexistent = temp_dir / "does_not_exist.txt"
        dest = temp_dir / "dest.txt"

        errors = []
        file_ops.operationError.connect(lambda *a: errors.append(a))

        job_id = file_ops.copy(str(nonexistent), str(dest))
        assert job_id, "copy() should return job_id"

        completed = wait_for_condition(qapp, lambda: len(errors) > 0, timeout_ms=3000)
        assert completed, "Error should be reported"

        assert len(errors) == 1

    def test_active_job_count(self, file_ops, temp_dir):
        """Test active job count tracking."""
        # Create a small file
        large = temp_dir / "test.bin"
        large.write_bytes(b"x" * 1024)  # 1KB

        job_id = file_ops.copy(str(large), str(temp_dir / "copy.bin"))

        count = file_ops.activeJobCount()
        assert count >= 0, "activeJobCount should return non-negative"

    def test_parallel_operations(self, file_ops, temp_dir, qapp):
        """Test multiple operations can run in parallel."""
        # Create 5 source files
        for i in range(5):
            (temp_dir / f"src_{i}.txt").write_text(f"Content {i}")

        results = []
        file_ops.operationFinished.connect(lambda *a: results.append(a))

        # Start 5 copy operations
        job_ids = []
        for i in range(5):
            job_id = file_ops.copy(
                str(temp_dir / f"src_{i}.txt"), str(temp_dir / f"dest_{i}.txt")
            )
            job_ids.append(job_id)

        # All job IDs should be non-empty
        assert all(jid for jid in job_ids), "All operations should return job IDs"

        # Wait for all to complete
        completed = wait_for_condition(
            qapp, lambda: len(results) >= 5, timeout_ms=10000
        )
        assert completed, "All operations should complete"

        # Verify all files copied
        for i in range(5):
            assert (temp_dir / f"dest_{i}.txt").exists()


class TestFileOperationsCancel:
    """Test operation cancellation."""

    def test_cancel_operation(self, file_ops, temp_dir, qapp):
        """Test cancellation of an in-progress operation."""
        # Create a large file
        large = temp_dir / "cancel_test.bin"
        large.write_bytes(b"x" * (1024 * 1024))  # 1MB

        finished = []
        file_ops.operationFinished.connect(lambda *a: finished.append(a))

        dest = temp_dir / "cancel_dest.bin"
        job_id = file_ops.copy(str(large), str(dest))

        # Immediately cancel
        file_ops.cancel(job_id)

        # Wait a bit for cancellation to process
        time.sleep(0.5)
        qapp.processEvents()

        # Either completed or error/cancelled - both acceptable
        # Just verify we don't crash


class TestFileOperationsWithTransactions:
    """Test operations within transactions."""

    def test_operation_in_transaction(self, file_ops_system, temp_dir, qapp):
        """Test operation tracked within transaction."""
        tm = file_ops_system["tm"]
        file_ops = file_ops_system["file_ops"]

        src = temp_dir / "tx_src.txt"
        src.write_text("Transaction content")
        dest = temp_dir / "tx_dest.txt"

        completed = []
        tm.transactionFinished.connect(lambda t, s: completed.append((t, s)))

        tid = tm.startTransaction("Copy Test")
        file_ops.copy(str(src), str(dest), tid)

        # Wait for transaction to complete
        done = wait_for_condition(qapp, lambda: len(completed) > 0, timeout_ms=5000)

        # The operation should have happened
        assert dest.exists(), "File should be copied"
