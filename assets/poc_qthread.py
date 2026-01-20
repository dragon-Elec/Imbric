"""
POC: QThread + Gio.Cancellable

The "proper" approach for non-blocking file operations in Qt + GIO.

Features:
- Non-blocking UI
- Progress signals
- Cancellation support via Gio.Cancellable
- Clean separation (Worker + Controller pattern)

Run: python3 poc_qthread.py
"""

import sys
import os
import tempfile

# Qt imports
from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QVBoxLayout, 
    QWidget, QLabel, QProgressBar, QHBoxLayout
)

# GIO imports
import gi
gi.require_version('Gio', '2.0')
from gi.repository import Gio, GLib


# =============================================================================
# WORKER CLASS (Runs in separate thread)
# =============================================================================
class FileOperationWorker(QObject):
    """
    Worker that executes file operations in a separate thread.
    Uses Gio for actual file I/O.
    """
    
    # Signals (emitted from worker thread, received in main thread)
    started = Signal(str)           # operation_type
    progress = Signal(int, int)     # current_bytes, total_bytes
    finished = Signal(bool, str)    # success, message
    
    def __init__(self):
        super().__init__()
        self._cancellable = None
    
    @Slot(str, str)
    def copy_file(self, source_path: str, dest_path: str):
        """Copy a file with progress reporting."""
        self._cancellable = Gio.Cancellable()
        self.started.emit("copy")
        
        source = Gio.File.new_for_path(source_path)
        dest = Gio.File.new_for_path(dest_path)
        
        try:
            # Gio's copy with progress callback
            source.copy(
                dest,
                Gio.FileCopyFlags.OVERWRITE,
                self._cancellable,
                self._progress_callback,
                None
            )
            self.finished.emit(True, f"Copied to {os.path.basename(dest_path)}")
        except GLib.Error as e:
            if e.code == Gio.IOErrorEnum.CANCELLED:
                self.finished.emit(False, "Operation cancelled")
            else:
                self.finished.emit(False, str(e))
    
    @Slot(str, str)
    def move_file(self, source_path: str, dest_path: str):
        """Move a file with progress reporting."""
        self._cancellable = Gio.Cancellable()
        self.started.emit("move")
        
        source = Gio.File.new_for_path(source_path)
        dest = Gio.File.new_for_path(dest_path)
        
        try:
            source.move(
                dest,
                Gio.FileCopyFlags.OVERWRITE,
                self._cancellable,
                self._progress_callback,
                None
            )
            self.finished.emit(True, f"Moved to {os.path.basename(dest_path)}")
        except GLib.Error as e:
            if e.code == Gio.IOErrorEnum.CANCELLED:
                self.finished.emit(False, "Operation cancelled")
            else:
                self.finished.emit(False, str(e))
    
    @Slot(str)
    def trash_file(self, path: str):
        """Trash a file."""
        self._cancellable = Gio.Cancellable()
        self.started.emit("trash")
        
        gfile = Gio.File.new_for_path(path)
        
        try:
            gfile.trash(self._cancellable)
            self.finished.emit(True, f"Trashed {os.path.basename(path)}")
        except GLib.Error as e:
            if e.code == Gio.IOErrorEnum.CANCELLED:
                self.finished.emit(False, "Operation cancelled")
            else:
                self.finished.emit(False, str(e))
    
    @Slot()
    def cancel(self):
        """Cancel the current operation."""
        if self._cancellable:
            self._cancellable.cancel()
    
    def _progress_callback(self, current_bytes, total_bytes, user_data):
        """Called by Gio during copy/move."""
        self.progress.emit(current_bytes, total_bytes)


# =============================================================================
# CONTROLLER (Manages worker thread)
# =============================================================================
class FileOperationController(QObject):
    """
    Controller that manages the worker thread.
    Call methods on this from the main thread.
    """
    
    # Re-expose worker signals for convenience
    started = Signal(str)
    progress = Signal(int, int)
    finished = Signal(bool, str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Create thread and worker
        self._thread = QThread()
        self._worker = FileOperationWorker()
        
        # Move worker to thread
        self._worker.moveToThread(self._thread)
        
        # Connect worker signals to controller signals
        self._worker.started.connect(self.started)
        self._worker.progress.connect(self.progress)
        self._worker.finished.connect(self.finished)
        
        # Start thread
        self._thread.start()
    
    def copy(self, source: str, dest: str):
        """Queue a copy operation."""
        # Use QMetaObject.invokeMethod for thread-safe call
        self._worker.copy_file(source, dest)
    
    def move(self, source: str, dest: str):
        """Queue a move operation."""
        self._worker.move_file(source, dest)
    
    def trash(self, path: str):
        """Queue a trash operation."""
        self._worker.trash_file(path)
    
    def cancel(self):
        """Cancel current operation."""
        self._worker.cancel()
    
    def shutdown(self):
        """Clean shutdown of worker thread."""
        self._thread.quit()
        self._thread.wait()


# =============================================================================
# TEST WINDOW
# =============================================================================
class TestWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("QThread + Gio POC")
        self.resize(500, 250)
        
        # File operation controller
        self.file_ops = FileOperationController(self)
        self.file_ops.started.connect(self.on_started)
        self.file_ops.progress.connect(self.on_progress)
        self.file_ops.finished.connect(self.on_finished)
        
        # UI
        central = QWidget()
        layout = QVBoxLayout(central)
        
        self.status_label = QLabel("Ready. Click a button to test.")
        layout.addWidget(self.status_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Buttons row
        btn_row = QHBoxLayout()
        
        btn_copy = QPushButton("Test Copy (50MB)")
        btn_copy.clicked.connect(self.test_copy)
        btn_row.addWidget(btn_copy)
        
        btn_trash = QPushButton("Test Trash")
        btn_trash.clicked.connect(self.test_trash)
        btn_row.addWidget(btn_trash)
        
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.file_ops.cancel)
        self.btn_cancel.setEnabled(False)
        btn_row.addWidget(self.btn_cancel)
        
        layout.addLayout(btn_row)
        
        # Stress test
        btn_stress = QPushButton("Stress: Copy 50MB while clicking buttons")
        btn_stress.clicked.connect(self.test_stress)
        layout.addWidget(btn_stress)
        
        # Counter to prove UI is responsive
        self.click_count = 0
        self.click_label = QLabel("Click counter: 0")
        layout.addWidget(self.click_label)
        
        btn_click = QPushButton("Click me during copy!")
        btn_click.clicked.connect(self.increment_counter)
        layout.addWidget(btn_click)
        
        self.setCentralWidget(central)
    
    def increment_counter(self):
        self.click_count += 1
        self.click_label.setText(f"Click counter: {self.click_count}")
    
    def test_copy(self):
        """Test copying a large file."""
        # Create a 50MB test file
        self.status_label.setText("Creating 50MB test file...")
        QApplication.processEvents()
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as f:
            f.write(b"X" * (50 * 1024 * 1024))  # 50MB
            self.test_src = f.name
        
        self.test_dest = self.test_src + ".copy"
        self.file_ops.copy(self.test_src, self.test_dest)
    
    def test_trash(self):
        """Test trashing a file."""
        # Create file in home (not /tmp)
        home = os.path.expanduser("~")
        path = os.path.join(home, ".imbric_trash_test.txt")
        
        with open(path, 'w') as f:
            f.write("Test file for trash\n")
        
        self.file_ops.trash(path)
    
    def test_stress(self):
        """Same as test_copy but reminds user to click."""
        self.status_label.setText("Starting 50MB copy. Click the button below to prove UI is responsive!")
        self.test_copy()
    
    @Slot(str)
    def on_started(self, op_type):
        self.status_label.setText(f"Operation: {op_type} started...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.btn_cancel.setEnabled(True)
    
    @Slot(int, int)
    def on_progress(self, current, total):
        if total > 0:
            percent = int((current / total) * 100)
            self.progress_bar.setValue(percent)
            mb_done = current / (1024 * 1024)
            mb_total = total / (1024 * 1024)
            self.status_label.setText(f"Progress: {mb_done:.1f} / {mb_total:.1f} MB")
    
    @Slot(bool, str)
    def on_finished(self, success, message):
        self.progress_bar.setVisible(False)
        self.btn_cancel.setEnabled(False)
        
        if success:
            self.status_label.setText(f"✓ SUCCESS: {message}")
            # Cleanup test files
            if hasattr(self, 'test_src') and os.path.exists(self.test_src):
                os.remove(self.test_src)
            if hasattr(self, 'test_dest') and os.path.exists(self.test_dest):
                os.remove(self.test_dest)
        else:
            self.status_label.setText(f"✗ FAILED: {message}")
    
    def closeEvent(self, event):
        self.file_ops.shutdown()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    window = TestWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
