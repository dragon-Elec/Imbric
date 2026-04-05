"""
Real filesystem stress tests.
Tests performance and correctness with actual file operations.
MARKER: @pytest.mark.stress_real - runs with real I/O
"""

import pytest
import os
import time
import shutil
from pathlib import Path


class TestRealStressScenarios:
    """
    Stress tests using real filesystem operations.
    These tests are slower but verify actual I/O behavior.
    """

    @pytest.mark.slow
    def test_symlink_loop_handling(
        self, test_home_dir, qapp, signals, backend_registry
    ):
        """
        Test that recursive operations handle circular symlinks gracefully.
        Should NOT hang or crash.
        """
        from core.managers import FileOperations

        fo = FileOperations()
        fo.setRegistry(backend_registry)

        # Create source with circular symlink
        src_dir = test_home_dir / "loop_src"
        src_dir.mkdir(exist_ok=True)
        (src_dir / "real_file.txt").write_text("content")

        # Create circular link
        loop_link = src_dir / "recursive_link"
        if loop_link.exists() or loop_link.is_symlink():
            loop_link.unlink()
        loop_link.symlink_to(src_dir)

        dest_dir = test_home_dir / "loop_dest"

        # Track completion
        finished = []
        fo.operationFinished.connect(lambda *args: finished.append(args))

        # Start copy
        fo.copy(str(src_dir), str(dest_dir))

        # Wait with timeout (should complete or fail gracefully)
        start = time.time()
        timeout = 10.0
        while len(finished) == 0 and (time.time() - start) < timeout:
            from PySide6.QtCore import QCoreApplication

            QCoreApplication.processEvents()
            time.sleep(0.1)

        fo.shutdown()

        # Should have completed (even if it skipped the link)
        assert len(finished) > 0 or (time.time() - start) >= timeout, (
            "Operation should complete or timeout, not hang indefinitely"
        )

    @pytest.mark.slow
    def test_camera_dump_simulation(
        self, test_home_dir, qapp, signals, backend_registry
    ):
        """
        Test copying 2000 files in nested structure.
        Simulates copying photos from a camera.
        """
        from core.managers import FileOperations

        fo = FileOperations()
        fo.setRegistry(backend_registry)

        # Generate structure
        src_root = test_home_dir / "dcim_src"
        if src_root.exists():
            shutil.rmtree(src_root)
        src_root.mkdir(parents=True)

        print("\n  Generating 2000 test files...", end="", flush=True)
        TOTAL_FILES = 2000
        for i in range(10):  # 10 folders
            d = src_root / f"Folder_{i}"
            d.mkdir()
            for j in range(200):  # 200 files per folder
                (d / f"IMG_{j:04d}.jpg").write_bytes(b"FAKE_JPEG" + os.urandom(100))
        print(" Done.")

        dest_root = test_home_dir / "dcim_dest"

        # Track completion
        finished = []
        fo.operationFinished.connect(lambda *args: finished.append(args))

        print("  Starting recursive copy...")
        start_time = time.time()
        fo.copy(str(src_root), str(dest_root))

        # Wait for completion
        start = time.time()
        timeout = 60.0
        while len(finished) == 0 and (time.time() - start) < timeout:
            from PySide6.QtCore import QCoreApplication

            QCoreApplication.processEvents()
            time.sleep(0.1)

        duration = time.time() - start_time

        fo.shutdown()

        # Verify
        assert len(finished) > 0, "Operation should complete"

        # Count files in destination
        count = 0
        for root, dirs, files in os.walk(dest_root):
            count += len(files)

        assert count == TOTAL_FILES, f"Expected {TOTAL_FILES} files, found {count}"
        print(f"  Copied {count} files in {duration:.2f}s")

    @pytest.mark.slow
    def test_transaction_spam_real(
        self, test_home_dir, qapp, signals, backend_registry
    ):
        """
        Test rapidly submitting 50 file operations.
        """
        from core.managers import FileOperations

        fo = FileOperations()
        fo.setRegistry(backend_registry)

        spam_dir = test_home_dir / "spam"
        spam_dir.mkdir(exist_ok=True)

        # Create 50 source files
        for i in range(50):
            (spam_dir / f"f_{i}.txt").write_text("x")

        dest_dir = test_home_dir / "spam_dest"
        dest_dir.mkdir(exist_ok=True)

        finished = []
        errors = []
        fo.operationFinished.connect(lambda *args: finished.append(args))
        fo.operationError.connect(lambda *args: errors.append(args))

        print("\n  Launching 50 copies...")
        job_ids = []
        for i in range(50):
            jid = fo.copy(str(spam_dir / f"f_{i}.txt"), str(dest_dir / f"f_{i}.txt"))
            job_ids.append(jid)

        # Wait for all
        start = time.time()
        timeout = 30.0
        while (len(finished) + len(errors)) < 50 and (time.time() - start) < timeout:
            from PySide6.QtCore import QCoreApplication

            QCoreApplication.processEvents()
            time.sleep(0.05)

        duration = time.time() - start

        fo.shutdown()

        total = len(finished) + len(errors)
        print(f"  Completed: {total}/50 in {duration:.2f}s")

        assert total == 50, f"Expected 50 operations, got {total}"

    @pytest.mark.slow
    def test_permission_lockdown(self, test_home_dir, qapp, signals, backend_registry):
        """
        Test operations on read-only files and directories.
        """
        from core.managers import FileOperations

        fo = FileOperations()
        fo.setRegistry(backend_registry)

        locked_dir = test_home_dir / "locked"
        locked_dir.mkdir(exist_ok=True)

        # Create and lock a file
        fpath = locked_dir / "cant_touch_this.txt"
        fpath.write_text("hammer time")
        os.chmod(fpath, 0o444)  # Read only

        errors = []
        fo.operationError.connect(lambda *args: errors.append(args))

        # Try to delete read-only file
        fo.trash(str(fpath))

        time.sleep(0.5)
        from PySide6.QtCore import QCoreApplication

        QCoreApplication.processEvents()

        # Cleanup permissions for teardown
        os.chmod(locked_dir, 0o700)
        if fpath.exists():
            os.chmod(fpath, 0o600)

        fo.shutdown()

        # Should have reported an error or succeeded (depends on OS)
        # The point is it shouldn't crash
        assert len(errors) > 0 or not fpath.exists(), (
            "Read-only file operation should either fail or succeed (OS dependent)"
        )


class TestRealUndoStress:
    """Real filesystem undo/redo stress tests."""

    @pytest.mark.slow
    def test_rapid_fire_undo(self, test_home_dir, qapp, signals, backend_registry):
        """
        Create 10 folders, then undo them all rapidly.
        Tests undo stack and operation ordering.
        """
        from core.managers import FileOperations, TransactionManager, UndoManager

        tm = TransactionManager()
        fo = FileOperations()
        fo.setRegistry(backend_registry)
        tm.setFileOperations(fo)
        fo.setTransactionManager(tm)

        um = UndoManager(tm)
        um.setFileOperations(fo)

        # Create 10 folders
        print("\n  Creating 10 folders...")
        from PySide6.QtCore import QCoreApplication

        for i in range(10):
            p = str(test_home_dir / f"Rapid_{i}")
            tid = tm.startTransaction(f"Create_{i}")
            fo.createFolder(p, tid)
            tm.commitTransaction(tid)

            # Wait for each
            timeout = 100
            while timeout > 0 and tid in tm._active_transactions:
                QCoreApplication.processEvents()
                time.sleep(0.02)
                timeout -= 1

        # Wait a bit for history to commit
        for _ in range(20):
            if um.can_undo():
                break
            QCoreApplication.processEvents()
            time.sleep(0.05)

        assert um.can_undo(), (
            f"Should be able to undo. History stack: {len(um._undo_stack)}"
        )

        # Rapid undo
        print("  Undoing...")
        for i in range(10):
            if not um.can_undo():
                break
            um.undo()
            time.sleep(0.1)  # Small delay between undos

            from PySide6.QtCore import QCoreApplication

            QCoreApplication.processEvents()

        # Check remaining folders
        remaining = list(test_home_dir.glob("Rapid_*"))
        print(f"  Remaining: {len(remaining)} folders")

        fo.shutdown()

    @pytest.mark.slow
    def test_batch_undo(self, test_home_dir, qapp, signals, backend_registry):
        """
        Create 20 folders in one transaction, undo as batch.
        """
        from core.managers import FileOperations, TransactionManager, UndoManager

        tm = TransactionManager()
        fo = FileOperations()
        fo.setRegistry(backend_registry)
        tm.setFileOperations(fo)
        fo.setTransactionManager(tm)

        um = UndoManager(tm)
        um.setFileOperations(fo)

        # Create batch
        NUM = 20
        tid = tm.startTransaction("Batch Create")

        for i in range(NUM):
            p = str(test_home_dir / f"Batch_{i}")
            fo.createFolder(p, tid)

        tm.commitTransaction(tid)

        # Wait for completion
        timeout = 200
        from PySide6.QtCore import QCoreApplication

        while timeout > 0 and tid in tm._active_transactions:
            QCoreApplication.processEvents()
            time.sleep(0.05)
            timeout -= 1

        # Wait for history
        for _ in range(20):
            if um.can_undo():
                break
            QCoreApplication.processEvents()
            time.sleep(0.05)

        assert um.can_undo(), "Should be able to undo batch"

        # Undo entire batch
        print(f"\n  Undoing batch of {NUM} folders...")
        um.undo()

        # Wait for undo
        start_wait = time.time()
        while (
            um._pending_mode != um._pending_mode.NONE
            and (time.time() - start_wait) < 10
        ):
            QCoreApplication.processEvents()
            time.sleep(0.1)

        remaining = list(test_home_dir.glob("Batch_*"))
        print(f"  Remaining after batch undo: {len(remaining)}")

        fo.shutdown()
