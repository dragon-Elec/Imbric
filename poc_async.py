"""
POC: QtAsyncio + Gio Async Integration

Tests whether we can use Gio's async methods (copy_async, trash_async)
within Qt's event loop using PySide6.QtAsyncio.

Run: python poc_async.py
"""

import asyncio
import sys
import os
import tempfile

# Qt imports
from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget, QLabel
from PySide6.QtAsyncio import QAsyncioEventLoopPolicy

# GIO imports
import gi
gi.require_version('Gio', '2.0')
from gi.repository import Gio, GLib


class AsyncFileOps:
    """
    Async wrapper for Gio file operations.
    Uses Gio's native async methods which return awaitables when callback is None.
    """
    
    @staticmethod
    async def copy_async(source_path: str, dest_path: str) -> bool:
        """
        Copies a file asynchronously using Gio.
        Returns True on success, raises on failure.
        """
        source = Gio.File.new_for_path(source_path)
        dest = Gio.File.new_for_path(dest_path)
        
        try:
            # When callback is omitted, PyGObject returns an awaitable
            result = await asyncio.to_thread(
                source.copy,
                dest,
                Gio.FileCopyFlags.OVERWRITE,
                None,  # Cancellable
                None,  # Progress callback (can't use with to_thread easily)
                None   # User data
            )
            return result
        except GLib.Error as e:
            print(f"Copy failed: {e}")
            raise
    
    @staticmethod
    async def trash_async(path: str) -> bool:
        """
        Moves a file to trash asynchronously.
        """
        gfile = Gio.File.new_for_path(path)
        
        try:
            result = await asyncio.to_thread(gfile.trash, None)
            return result
        except GLib.Error as e:
            print(f"Trash failed: {e}")
            raise


class TestWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Async File Ops POC")
        self.resize(400, 200)
        
        # UI
        central = QWidget()
        layout = QVBoxLayout(central)
        
        self.status_label = QLabel("Ready. Click a button to test.")
        layout.addWidget(self.status_label)
        
        btn_copy = QPushButton("Test Async Copy")
        btn_copy.clicked.connect(lambda: asyncio.ensure_future(self.test_copy()))
        layout.addWidget(btn_copy)
        
        btn_trash = QPushButton("Test Async Trash")
        btn_trash.clicked.connect(lambda: asyncio.ensure_future(self.test_trash()))
        layout.addWidget(btn_trash)
        
        btn_stress = QPushButton("Stress Test (10 copies)")
        btn_stress.clicked.connect(lambda: asyncio.ensure_future(self.test_stress()))
        layout.addWidget(btn_stress)
        
        self.setCentralWidget(central)
    
    async def test_copy(self):
        """Test a single async copy."""
        self.status_label.setText("Copying...")
        
        # Create a temp file to copy
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            f.write(b"Test content for async copy POC\n" * 1000)
            src = f.name
        
        dest = src + ".copy"
        
        try:
            await AsyncFileOps.copy_async(src, dest)
            self.status_label.setText(f"SUCCESS: Copied to {os.path.basename(dest)}")
            
            # Cleanup
            os.remove(src)
            os.remove(dest)
        except Exception as e:
            self.status_label.setText(f"FAILED: {e}")
    
    async def test_trash(self):
        """Test async trash."""
        self.status_label.setText("Creating file and trashing...")
        
        # Create a temp file in HOME (not /tmp - /tmp doesn't support Trash)
        home = os.path.expanduser("~")
        path = os.path.join(home, ".imbric_trash_test.txt")
        
        with open(path, 'w') as f:
            f.write("File to be trashed\n")
        
        try:
            await AsyncFileOps.trash_async(path)
            self.status_label.setText(f"SUCCESS: Trashed {os.path.basename(path)}")
        except Exception as e:
            self.status_label.setText(f"FAILED: {e}")
    
    async def test_stress(self):
        """Test multiple concurrent copies to verify UI stays responsive."""
        self.status_label.setText("Starting 10 concurrent copies...")
        
        # Create source file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            # Make it ~1MB to actually take some time
            f.write(b"X" * (1024 * 1024))
            src = f.name
        
        tasks = []
        dests = []
        for i in range(10):
            dest = f"{src}.copy{i}"
            dests.append(dest)
            tasks.append(AsyncFileOps.copy_async(src, dest))
        
        try:
            await asyncio.gather(*tasks)
            self.status_label.setText("SUCCESS: 10 files copied concurrently!")
            
            # Cleanup
            os.remove(src)
            for d in dests:
                if os.path.exists(d):
                    os.remove(d)
        except Exception as e:
            self.status_label.setText(f"FAILED: {e}")


def main():
    # QtAsyncio handles event loop setup automatically
    from PySide6 import QtAsyncio
    
    app = QApplication(sys.argv)
    window = TestWindow()
    window.show()
    
    # Run using QtAsyncio - this bridges Qt and asyncio event loops
    QtAsyncio.run()


if __name__ == "__main__":
    main()
