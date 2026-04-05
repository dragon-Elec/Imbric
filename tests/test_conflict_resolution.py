import unittest
import os
import sys
import time
import shutil

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtCore import QCoreApplication
from core.managers import FileOperations
from core.managers import TransactionManager
from core.registry import BackendRegistry
from core.backends.gio.backend import GIOBackend
from core.models.file_job import FileOperationSignals

# Create QApplication instance if needed
app = QCoreApplication.instance()
if not app:
    app = QCoreApplication([])

TEST_DIR = "/tmp/imbric_test_conflict"


class TestTransactionConflict(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.path.exists(TEST_DIR):
            shutil.rmtree(TEST_DIR)
        os.makedirs(TEST_DIR)

    def setUp(self):
        signals = FileOperationSignals()
        self.registry = BackendRegistry()
        self.registry.set_default_io(GIOBackend())
        self.file_ops = FileOperations()
        self.file_ops.setRegistry(self.registry)
        self.tm = TransactionManager()
        self.tm.setFileOperations(self.file_ops)

        # Test files
        self.src = os.path.join(TEST_DIR, "src.txt")
        self.dest = os.path.join(TEST_DIR, "dest.txt")

        with open(self.src, "w") as f:
            f.write("SOURCE_CONTENT")

        with open(self.dest, "w") as f:
            f.write("DEST_CONTENT")

        self.conflict_job_id = None
        self.conflict_data = None
        self.op_finished = False

    def tearDown(self):
        # Clean up files for next test
        if os.path.exists(self.src):
            os.remove(self.src)
        if os.path.exists(self.dest):
            os.remove(self.dest)

        self.file_ops.shutdown()

    def on_conflict(self, job_id, data):
        print(f"[TEST] Conflict detected for job {job_id}")
        self.conflict_job_id = job_id
        self.conflict_data = data

    def on_finished(self, tid, job_id, op_type, path, success, msg):
        if success:
            print(f"[TEST] Op finished successfully: {path}")
            self.op_finished = True

    def test_overwrite_conflict(self):
        # Connect signals
        self.tm.conflictDetected.connect(self.on_conflict)
        self.tm.onOperationFinished = (
            self.on_finished
        )  # Mock connection for direct verification
        # Ideally we check TM signals, but checking raw callback is easier for unit test
        # Actually, let's connect to FileOps finished too
        self.file_ops.operationFinished.connect(self.on_finished)

        # Start Transaction
        tid = self.tm.startTransaction("Test Conflict")

        # Add Op (conceptual)
        self.tm.addOperation(tid, "copy", self.src, self.dest)

        # Execute Op (via FileOps directly, mimicking AppBridge)
        # Note: Default overwrite=False
        print("[TEST] Starting copy (expecting conflict)...")
        self.file_ops.copy(self.src, self.dest, tid)

        # Wait for conflict
        timeout = 0
        while self.conflict_job_id is None and timeout < 20:
            app.processEvents()
            time.sleep(0.1)
            timeout += 1

        self.assertIsNotNone(self.conflict_job_id, "Conflict should be detected")
        self.assertEqual(
            self.conflict_data["error"], "exists", "Error should be 'exists'"
        )

        # Check file content (should still be DEST_CONTENT)
        with open(self.dest, "r") as f:
            content = f.read()
        self.assertEqual(content, "DEST_CONTENT", "File should NOT be overwritten yet")

        # Resolve with Overwrite
        print("[TEST] Resolving with 'overwrite'...")
        self.tm.resolveConflict(self.conflict_job_id, "overwrite")

        # Wait for finish
        timeout = 0
        self.op_finished = False  # Reset
        while not self.op_finished and timeout < 20:
            app.processEvents()
            time.sleep(0.1)
            timeout += 1

        self.assertTrue(self.op_finished, "Operation should complete after resolution")

        # Check file content (should now be SOURCE_CONTENT)
        with open(self.dest, "r") as f:
            content = f.read()
        self.assertEqual(
            content, "SOURCE_CONTENT", "File SHOULD be overwritten after resolution"
        )


if __name__ == "__main__":
    unittest.main()
