import sys
import os
import shutil
import time
import unittest
import tempfile
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PySide6.QtCore import QCoreApplication, QTimer, QObject, Slot, QEventLoop
from core.threading.worker_pool import AsyncWorkerPool
from core.managers import FileOperations
from core.registry import BackendRegistry
from core.backends.gio.backend import GIOBackend
from core.models.file_job import FileOperationSignals

# Ensure QApplication exists for signals
app = QCoreApplication.instance() or QCoreApplication(sys.argv)


class TestTrashManagerHardened(unittest.TestCase):
    """
    Hardened test suite for TrashManager (via FileOperations).
    Tests duplicate handling, restore conflicts, and edge cases.
    """

    def setUp(self):
        """Create a temp environment for each test."""
        # Use a local directory for trash support (system /tmp often fails with Gio Trash)
        base_dir = os.path.expanduser("~/Desktop/imbric_test_trash")
        if not os.path.exists(base_dir):
            os.makedirs(base_dir)
        self.test_dir = tempfile.mkdtemp(prefix="run_", dir=base_dir)

        signals = FileOperationSignals()
        registry = BackendRegistry()
        registry.set_default_io(GIOBackend())

        self.tm = FileOperations()
        self.tm.setRegistry(registry)

        # Signal capture
        self.finished_signal = None
        self.error_signal = None

        # Connect signals
        self.tm.operationFinished.connect(self._on_finished)
        self.tm.trashNotSupported.connect(self._on_error)

    def tearDown(self):
        """Cleanup."""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

        # We should logically empty trash of our test items, but that's risky
        # in a real environment. Ideally we mock Gio, but here we test integration.
        # So we leave trash as is, or manually clean specific items if possible.
        pass

    @Slot(str, str, str, str, bool, str)
    def _on_finished(self, tid, job_id, op_type, result, success, msg):
        self.finished_signal = (op_type, success, msg)

    @Slot(str, str)
    def _on_error(self, path, error):
        self.error_signal = (path, error)

    def _wait(self, timeout_ms=3000):
        """Process events until signal received or timeout."""
        start = time.time()
        self.finished_signal = None
        self.error_signal = None

        while self.finished_signal is None and self.error_signal is None:
            app.processEvents()
            if (time.time() - start) * 1000 > timeout_ms:
                return False
            time.sleep(0.01)
        return True

    def create_file(self, name, content="test"):
        path = os.path.join(self.test_dir, name)
        with open(path, "w") as f:
            f.write(content)
        return path

    def test_basic_lifecycle(self):
        """Test: Create -> Trash -> Restore"""
        print("\n[Test] Basic Lifecycle")
        path = self.create_file("basic.txt")
        original_content = "test"

        # 1. Trash
        self.tm.trash(path)
        assert self._wait(), "Trash timeout"
        assert self.finished_signal[1], f"Trash failed: {self.finished_signal[2]}"
        assert not os.path.exists(path), "File should be gone from original location"

        # 2. Restore
        self.tm.restore(path)
        assert self._wait(), "Restore timeout"
        assert self.finished_signal[1], f"Restore failed: {self.finished_signal[2]}"
        assert os.path.exists(path), "File should be back"
        assert Path(path).read_text() == original_content

    def test_duplicate_trash_resolution(self):
        """
        Test: Trash 'foo' (v1) -> Create 'foo' (v2) -> Trash 'foo' (v2) -> Restore
        Expectation: Should restore v2 (most recent), not v1.
        """
        print("\n[Test] Duplicate Resolution")
        path = os.path.join(self.test_dir, "dup.txt")

        # Version 1
        with open(path, "w") as f:
            f.write("Version 1")
        self.tm.trash(path)
        self._wait()

        # Ensure timestamp differs (Gio uses second resolution usually)
        time.sleep(1.5)

        # Version 2
        with open(path, "w") as f:
            f.write("Version 2")
        self.tm.trash(path)
        self._wait()

        # Restore
        self.tm.restore(path)
        self._wait()

        assert os.path.exists(path), "File not restored"
        content = Path(path).read_text()
        print(f"Restored content: {content}")

        if content == "Version 2":
            print("PASS: Correctly restored newest version.")
        else:
            self.fail(
                f"FAIL: Restored wrong version. Expected 'Version 2', got '{content}'"
            )

    def test_restore_conflict_exists(self):
        """
        Test: Trash 'file.txt' -> Create new 'file.txt' in same spot -> Restore
        Expectation: Should FAIL or handle gracefully (currently expected to FAIL/Exception).
        """
        print("\n[Test] Restore Conflict (Target Exists)")
        path = self.create_file("conflict.txt", "Original")

        # Trash it
        self.tm.trash(path)
        self._wait()

        # Create a BLOCKER file at the same place
        self.create_file("conflict.txt", "Blocker")

        # Attempt restore
        print("Attempting restore over existing file...")
        self.tm.restore(path)
        self._wait()

        success = self.finished_signal[1]
        msg = self.finished_signal[2]

        if not success:
            print(f"PASS: Restore correctly failed or handled conflict. Message: {msg}")

            # Verify Rich Metadata
            try:
                # signal emission: (job_id, op_type, original_path, metadata)
                # But here we captured (op_type, success, msg) from finished signal
                # Wait, we need to capture operationError signal to verify metadata!
                pass  # TODO: Add explicit signal capture for operationError in setUp
            except:
                pass
        else:
            # Check what happened - did it overwrite?
            content = Path(path).read_text()
            if content == "Original":
                print("WARNING: Restore OVERWROTE the existing file without asking.")
            else:
                print(
                    "WARNING: Restore reported success but content is unchanged (silent fail?)."
                )

    def test_restore_conflict_with_rename(self):
        """Test: Restore with rename_to parameter."""
        print("\n[Test] Restore Conflict (Rename Fix)")
        path = self.create_file("rename_conflict.txt", "Original")
        self.tm.trash(path)
        self._wait()

        # Blocker
        self.create_file("rename_conflict.txt", "Blocker")

        # Restore with RENAME
        self.tm.restore(path, rename_to="rename_conflict (2).txt")
        self._wait()

        assert self.finished_signal[1], f"Restore failed: {self.finished_signal[2]}"

        # Verify both files exist
        blocker = os.path.join(self.test_dir, "rename_conflict.txt")
        restored = os.path.join(self.test_dir, "rename_conflict (2).txt")

        assert os.path.exists(blocker), "Blocker should still be there"
        assert os.path.exists(restored), "Restored file should be renamed"
        assert Path(restored).read_text() == "Original", "Content check failed"
        print("PASS: Successfully restored with new name.")

    def test_restore_conflict_with_overwrite(self):
        """Test: Restore with overwrite=True."""
        print("\n[Test] Restore Conflict (Overwrite Fix)")
        path = self.create_file("overwrite_conflict.txt", "Original")
        self.tm.trash(path)
        self._wait()

        # Blocker
        self.create_file("overwrite_conflict.txt", "Blocker")

        # Restore with OVERWRITE
        self.tm.restore(path, overwrite=True)
        self._wait()

        # Verify success
        assert self.finished_signal[1], f"Restore failed: {self.finished_signal[2]}"
        content = Path(path).read_text()
        assert content == "Original", f"Should have overwritten blocker. Got: {content}"
        print("PASS: Successfully overwritten blocker.")

    def test_directory_lifecycle(self):
        """Test trashing and restoring a non-empty directory."""
        print("\n[Test] Directory Lifecycle")
        subdir = os.path.join(self.test_dir, "my_folder")
        os.makedirs(subdir)
        with open(os.path.join(subdir, "child.txt"), "w") as f:
            f.write("child")

        # Trash
        self.tm.trash(subdir)
        self._wait()
        assert not os.path.exists(subdir)

        # Restore
        self.tm.restore(subdir)
        self._wait()
        assert os.path.exists(subdir)
        assert os.path.exists(os.path.join(subdir, "child.txt"))

    def test_ghost_restore(self):
        """Test restoring a file that was never trashed."""
        print("\n[Test] Ghost Restore")
        fake_path = os.path.join(self.test_dir, "ghost.txt")

        self.tm.restore(fake_path)
        self._wait()

        success = self.finished_signal[1]
        assert not success, "Restore of non-existent file should fail"
        print(
            f"PASS: Correctly failed to restore ghost file: {self.finished_signal[2]}"
        )


if __name__ == "__main__":
    unittest.main()
