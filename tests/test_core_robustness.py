#!/usr/bin/env python3
"""
Verification Script for Structural Fixes
Focus: Race Conditions, Path Traversal, Transaction Integrity

Usage: python3 tests/verify_fixes.py
"""

import sys
import os
import shutil
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock

# Add project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PySide6.QtCore import QCoreApplication, QTimer, QObject, Slot, Signal
from core.managers import FileOperations
from core.managers import TransactionManager
from core.registry import BackendRegistry
from core.backends.gio.backend import GIOBackend
from core.models.file_job import FileOperationSignals


class VerificationSuite(QObject):
    def __init__(self):
        super().__init__()
        self.file_ops = None
        self.tm = None
        self.test_dir = None
        self.results = {}
        self.registry = None

    def setup(self):
        # Use local directory to ensure filesystem consistency
        base_dir = Path(os.getcwd()) / "tests" / "temp_artifacts"
        base_dir.mkdir(parents=True, exist_ok=True)
        self.test_dir = tempfile.mkdtemp(prefix="imbric_verify_", dir=str(base_dir))
        print(f"📁 Test Dir: {self.test_dir}")
        signals = FileOperationSignals()
        self.registry = BackendRegistry()
        self.registry.set_default_io(GIOBackend())
        self.file_ops = FileOperations()
        self.file_ops.setRegistry(self.registry)
        self.tm = TransactionManager()
        self.tm.setFileOperations(self.file_ops)
        self.file_ops.operationFinished.connect(self.tm.onOperationFinished)

    def teardown(self):
        self.file_ops.shutdown()
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    # -------------------------------------------------------------------------
    # TEST 1: New Folder Race Condition (Atomic Check)
    # -------------------------------------------------------------------------
    def test_race_condition(self):
        print("\n[TEST 1] Race Condition (New Folder)...")

        # Fire 20 concurrent requests for "Untitled Folder"
        # Since we use auto_rename=True now, all 20 should succeed with unique names

        base_path = os.path.join(self.test_dir, "Untitled Folder")
        job_ids = []

        for i in range(20):
            # Simulate what FileManager now does: call with auto_rename=True
            jid = self.file_ops.createFolder(base_path, auto_rename=True)
            job_ids.append(jid)

        # Wait for all
        running = True
        start = time.time()
        while running and (time.time() - start < 5):
            QCoreApplication.processEvents()
            active = self.file_ops.activeJobCount()
            if active == 0:
                running = False
            time.sleep(0.01)

        # Verify
        folders = [f for f in os.listdir(self.test_dir) if "Untitled Folder" in f]
        count = len(folders)
        print(f"  -> Created {count}/20 folders")

        if count == 20:
            print("  ✅ SUCCESS: All 20 folders created with unique names.")
            return True
        else:
            print(f"  ❌ FAILURE: Expected 20, got {count}. Some failed?")
            return False

    # -------------------------------------------------------------------------
    # TEST 2: Path Traversal Security Check
    # -------------------------------------------------------------------------
    def test_path_traversal(self):
        print("\n[TEST 2] Path Traversal Security...")

        # Mock a conflict
        dummy_job = "job_pwnd"
        self.tm._pending_conflicts[dummy_job] = {
            "src_path": "/tmp/safe.txt",
            "dest_path": os.path.join(self.test_dir, "target.txt"),
            "_context": {
                "op_type": "rename",
                "tid": "tid_1",
                "src": "/tmp/safe.txt",
                "dest": os.path.join(self.test_dir, "target.txt"),
            },
        }

        # Mock FileOps.rename to capture call
        self.file_ops.rename = MagicMock()

        # Attempt traversal
        bad_name = "../../etc/passwd"
        self.tm.setFileOperations(self.file_ops)  # Ensure connected

        print(f"  -> Attempting resolveConflict with new_name='{bad_name}'")
        self.tm.resolveConflict(dummy_job, "rename", new_name=bad_name)

        # Check what was called
        # We expect sanitizer to convert "../../etc/passwd" -> "passwd"
        # So destination should be {test_dir}/passwd

        # Wait for any signals
        QCoreApplication.processEvents()

        # file_ops.rename(src, dest)
        if self.file_ops.rename.called:
            args = self.file_ops.rename.call_args[0]
            dest_called = args[1]  # 2nd arg
            print(f"  -> Backend called with dest: {dest_called}")

            if ".." in dest_called:
                print("  ❌ FAILURE: Path traversal succeeded!")
                return False
            elif dest_called.endswith(f"{self.test_dir}/passwd"):
                print("  ✅ SUCCESS: Input sanitized to basename.")
                return True
            else:
                # Did it reject entirely?
                pass
        else:
            print("  -> No call made (likely rejected entirely). Safe.")
            return True

        return False

    # -------------------------------------------------------------------------
    # TEST 3: Hanging Transaction (Memory Leak)
    # -------------------------------------------------------------------------
    def test_hanging_transaction(self):
        print("\n[TEST 3] Transaction Cleanup (Partial Failures)...")

        # Start a transaction with 2 ops
        tid = self.tm.startTransaction("Batch Test")
        self.tm.addOperation(tid, "copy", "src1", "dest1")
        self.tm.addOperation(tid, "copy", "src2", "dest2")

        # Op 1 Succeeds
        self.tm.onOperationFinished(tid, "job1", "copy", "dest1", True, "OK")

        # Op 2 Fails
        self.tm.onOperationFinished(tid, "job2", "copy", "dest2", False, "Error")

        # Check if transaction is gone from active list
        is_active = tid in self.tm._active_transactions

        if not is_active:
            print("  ✅ SUCCESS: Transaction removed from active list despite failure.")
            return True
        else:
            print("  ❌ FAILURE: Transaction still active (Hanging).")
            return False

    def run_all(self):
        self.setup()

        r1 = self.test_race_condition()
        r2 = self.test_path_traversal()
        r3 = self.test_hanging_transaction()

        self.teardown()

        if r1 and r2 and r3:
            print("\n🌟 ALL CHECKS PASSED")
            sys.exit(0)
        else:
            print("\n💀 SOME CHECKS FAILED")
            sys.exit(1)


if __name__ == "__main__":
    app = QCoreApplication(sys.argv)

    suite = VerificationSuite()
    QTimer.singleShot(100, suite.run_all)

    sys.exit(app.exec())
