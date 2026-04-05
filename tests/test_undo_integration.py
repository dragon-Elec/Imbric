#!/usr/bin/env python3
"""
Test Suite for UndoManager Execution
Verifies that Undo/Redo operations actually modify the filesystem correctly.
"""

import sys
import os
import shutil
import time
import unittest
import tempfile
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PySide6.QtCore import QCoreApplication, QTimer, QObject, Slot
from core.backends.gio.scanner import FileScanner
from core.managers import FileOperations, TransactionManager, UndoManager
from core.registry import BackendRegistry
from core.backends.gio.backend import GIOBackend
from core.models.file_job import FileOperationSignals

# Create App
app = QCoreApplication.instance() or QCoreApplication(sys.argv)


class TestUndoLogic(unittest.TestCase):
    def setUp(self):
        base = os.path.expanduser("~/Desktop/imbric_undo_test")
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
        self.undo_mgr = UndoManager(self.tm)
        self.undo_mgr.setFileOperations(self.file_ops)

        # Inject FileOps into TM
        self.tm.setFileOperations(self.file_ops)

        self.undo_finished = False
        self.undo_success = False

        # Connect to undo signals
        self.undo_mgr.operationFinished.connect(self._on_undo_finished)

    def tearDown(self):
        self.file_ops.shutdown()
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def _on_undo_finished(self, success, msg):
        print(f"  [SIGNAL] Finished: success={success} msg={msg}")
        self.undo_finished = True
        self.undo_success = success

    def _wait_for_undo(self, timeout=5):
        self.undo_finished = False
        start = time.time()
        while not self.undo_finished:
            app.processEvents()
            time.sleep(0.05)
            if time.time() - start > timeout:
                return False
        return True

    def _wait_for_op(self, count=1):
        # Rough wait for FileOps
        for _ in range(count * 20):
            app.processEvents()
            time.sleep(0.05)
            # Check idle? activeJobCount?
            if self.file_ops.activeJobCount() == 0:
                break

    def test_01_undo_rename(self):
        print("\n[TEST] Undo Rename")
        f = os.path.join(self.test_dir, "original.txt")
        with open(f, "w") as fp:
            fp.write("content")

        # 1. Perform Rename A -> B
        tid = self.tm.startTransaction("Rename Job")
        self.tm.addOperation(tid, "rename", f, "renamed.txt")
        self.file_ops.rename(f, "renamed.txt", tid)
        self.tm.commitTransaction(tid)

        self._wait_for_op()

        # Verify Rename Happened
        renamed = os.path.join(self.test_dir, "renamed.txt")
        assert os.path.exists(renamed)

        # 2. Undo
        print("  Triggering Undo...")
        assert self.undo_mgr.can_undo()
        self.undo_mgr.undo()

        # 3. Wait for Signal
        result = self._wait_for_undo()
        if not result:
            assert False, "Undo timed out"

        assert self.undo_success
        assert os.path.exists(f)
        assert not os.path.exists(renamed)
        print("  ✅ Undo Rename passed")

    def test_02_undo_trash(self):
        print("\n[TEST] Undo Trash")
        f = os.path.join(self.test_dir, "trash_me.txt")
        with open(f, "w") as fp:
            fp.write("trash data")

        # 1. Trash it
        tid = self.tm.startTransaction("Trash Job")
        self.tm.addOperation(tid, "trash", f, "")
        self.file_ops.trash(f, transaction_id=tid)
        self.tm.commitTransaction(tid)

        self._wait_for_op()

        # Verify Trashed
        assert not os.path.exists(f)

        # 2. Undo
        print("  Triggering Undo...")
        self.undo_mgr.undo()

        result = self._wait_for_undo()
        assert result
        assert self.undo_success
        assert os.path.exists(f)
        print("  ✅ Undo Trash passed")

    def test_03_redo_flow(self):
        print("\n[TEST] Redo Flow (Create -> Undo -> Redo)")
        folder = os.path.join(self.test_dir, "RedoFolder")

        # 1. Create
        tid = self.tm.startTransaction("Create Job")
        self.tm.addOperation(tid, "createFolder", folder, "")
        self.file_ops.createFolder(folder, transaction_id=tid)
        self.tm.commitTransaction(tid)

        self._wait_for_op()
        assert os.path.exists(folder)

        # 2. Undo (Should Trash it)
        print("  Undo...")
        self.undo_mgr.undo()
        self._wait_for_undo()
        assert not os.path.exists(folder)

        # 3. Redo (Should Restore/Recreate it)
        print("  Redo...")
        assert self.undo_mgr.can_redo()
        self.undo_mgr.redo()
        self._wait_for_undo()
        assert self.undo_success
        assert os.path.exists(folder)
        print("  ✅ Redo passed")


if __name__ == "__main__":
    unittest.main()
