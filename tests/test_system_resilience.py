#!/usr/bin/env python3
"""
Stress Test Suite for Imbric Core.
Tests edge cases, resource contention, and high volume operations.

Usage:
    python3 tests/test_stress_scenarios.py
"""

import sys
import os
import shutil
import time
import random
import unittest
import tempfile
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PySide6.QtCore import QCoreApplication, QTimer, QObject, Slot
from core.managers import FileOperations
from core.managers import TransactionManager
from core.registry import BackendRegistry
from core.backends.gio.backend import GIOBackend
from core.models.file_job import FileOperationSignals

# Create App
app = QCoreApplication.instance() or QCoreApplication(sys.argv)


class StressTest(unittest.TestCase):
    def setUp(self):
        # Use a real directory (not /tmp) to ensure xattrs/trash usually work better
        base = os.path.expanduser("~/Desktop/imbric_stress_test")
        if os.path.exists(base):
            shutil.rmtree(base)
        os.makedirs(base)
        self.test_dir = base

        signals = FileOperationSignals()
        self.registry = BackendRegistry()
        self.registry.set_default_io(GIOBackend())

        self.tm = TransactionManager()
        self.file_ops = FileOperations()
        self.file_ops.setRegistry(self.registry)
        self.tm.setFileOperations(self.file_ops)

        # Tracking
        self.finished_ops = 0
        self.errors = []

        # Connect signals
        self.tm.transactionFinished.connect(self._on_tx_finished)
        self.file_ops.operationError.connect(self._on_op_error)
        self.file_ops.operationFinished.connect(self._on_op_finished)

    def tearDown(self):
        self.file_ops.shutdown()
        # Cleanup (optional - maybe leave for inspection if failed)
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def _on_tx_finished(self, tid, status):
        pass

    def _on_op_finished(self, tid, job_id, op_type, result, success, msg):
        self.finished_ops += 1
        if not success:
            pass  # tracked in error signal usually, but sometimes here

    def _on_op_error(self, tid, job_id, op_type, path, msg, data):
        self.errors.append((op_type, msg))

    def _wait_for_ops(self, count, timeout_sec=10):
        start = time.time()
        while self.finished_ops < count:
            app.processEvents()
            if time.time() - start > timeout_sec:
                return False
            time.sleep(0.05)
        return True

    def test_01_symlink_loop_of_death(self):
        """
        Test: Recursive copy of a directory containing a circular symlink.
        Expectation: Should fail gracefully or skip the link, NOT hang forever.
        """
        print("\n[STRESS] Symlink Loop Test")
        src_dir = os.path.join(self.test_dir, "loop_src")
        os.makedirs(src_dir)

        # Create Loop: src/link -> src
        link_path = os.path.join(src_dir, "recursive_link")
        os.symlink(src_dir, link_path)

        dest_dir = os.path.join(self.test_dir, "loop_dest")

        print("  Copying folder with recursive symlink...")
        self.file_ops.copy(src_dir, dest_dir)

        # Wait
        success = self._wait_for_ops(1, timeout_sec=5)

        if not success:
            self.fail("FAIL: Operation timed out (Potential Infinite Loop!)")

        print("  PASS: Operation finished without hanging.")
        # Optional: check if dest size is reasonable (not infinite)

    def test_02_permission_lockdown(self):
        """
        Test: Operations on strictly locked files.
        """
        print("\n[STRESS] Permission Lockdown")
        locked_dir = os.path.join(self.test_dir, "locked")
        os.makedirs(locked_dir)

        # Create file and remove write permissions
        fpath = os.path.join(locked_dir, "cant_touch_this.txt")
        with open(fpath, "w") as f:
            f.write("hammer time")
        os.chmod(fpath, 0o444)  # Read only

        # Try to delete (Trash)
        print("  Trashing read-only file...")
        self.file_ops.trash(fpath)
        self._wait_for_ops(1)

        # Should succeed (you can delete read-only files if you own the dir)
        if os.path.exists(fpath):
            print("  Note: Read-only file not deleted (OS dependent).")
        else:
            print("  PASS: Read-only file deleted (standard behavior).")

        # Now lock the DIRECTORY
        self.finished_ops = 0
        os.chmod(locked_dir, 0o500)  # Read/Exec, NO WRITE

        # Try to create file inside
        print("  Creating file in read-only directory...")
        self.file_ops.createFolder(os.path.join(locked_dir, "fail_folder"))
        self._wait_for_ops(1)

        # Should fail
        assert len(self.errors) > 0, "Should have reported an error"
        print(f"  PASS: Error reported correctly: {self.errors[-1][1]}")

        # Cleanup permission to allow teardown
        os.chmod(locked_dir, 0o700)

    def test_03_transaction_spam(self):
        """
        Test: Rapidly submitting and cancelling transactions.
        """
        print("\n[STRESS] Transaction Spam (50 ops)")
        spam_dir = os.path.join(self.test_dir, "spam")
        os.makedirs(spam_dir)

        # Create source files
        for i in range(50):
            with open(os.path.join(spam_dir, f"f_{i}.txt"), "w") as f:
                f.write("x")

        self.finished_ops = 0
        dest_dir = os.path.join(self.test_dir, "spam_dest")
        os.makedirs(dest_dir)

        print("  Launching 50 copies...")
        # Fire 50 ops
        job_ids = []
        for i in range(50):
            jid = self.file_ops.copy(
                os.path.join(spam_dir, f"f_{i}.txt"),
                os.path.join(dest_dir, f"f_{i}.txt"),
            )
            job_ids.append(jid)

        print("  Cancelling odd numbered jobs...")
        # Cancel half
        for i, jid in enumerate(job_ids):
            if i % 2 != 0:
                self.file_ops.cancel(jid)

        # Wait for all to settle
        # Note: Cancellation might result in "finished" (with success=False) OR just stop?
        # Our FileWorkers emit finished(False, "Cancelled") usually.
        self._wait_for_ops(50, timeout_sec=2)

        print(f"  Finished: {self.finished_ops}/50")
        print("  PASS: Engine survived spam.")

    def test_04_camera_dump_simulation(self):
        """
        Test: Volume test. 2,000 files in nested structure.
        """
        print("\n[STRESS] Camera Dump (2,000 files)")

        # Generate Structure
        src_root = os.path.join(self.test_dir, "dcim_src")
        os.makedirs(src_root)

        print("  Generating files...", end="", flush=True)
        total_files = 2000
        for i in range(10):  # 10 Folders
            d = os.path.join(src_root, f"Folder_{i}")
            os.makedirs(d)
            for j in range(200):  # 200 Files per folder
                with open(os.path.join(d, f"IMG_{j}.jpg"), "w") as f:
                    f.write("fake_image_data")
        print(" Done.")

        dest_root = os.path.join(self.test_dir, "dcim_dest")

        self.finished_ops = 0
        start_time = time.time()

        # Copy the ROOT folder (recursive single job)
        print("  Starting Recursive Copy...")
        self.file_ops.copy(src_root, dest_root)

        success = self._wait_for_ops(1, timeout_sec=30)
        duration = time.time() - start_time

        if not success:
            self.fail("FAIL: Timeout during mass copy")

        print(f"  PASS: Copied {total_files} files in {duration:.2f}s")

        # Verify count
        count = 0
        for root, dirs, files in os.walk(dest_root):
            count += len(files)

        assert count == total_files, f"Expected {total_files}, found {count}"
        print("  PASS: File count verified.")


if __name__ == "__main__":
    unittest.main()
