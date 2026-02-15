"""
[NEW] DimensionWorker — Async Image Dimension Reader

Offloads QImageReader header parsing to a background thread to prevent
UI freezes during folder scanning.
"""

from PySide6.QtCore import QObject, Signal, QRunnable, QThreadPool
from PySide6.QtGui import QImageReader

class DimensionRunnable(QRunnable):
    """
    Background task to read image headers.
    """
    def __init__(self, path, emitter_wrapper):
        super().__init__()
        self.path = path
        self.emitter_wrapper = emitter_wrapper
        self.setAutoDelete(True)

    def run(self):
        try:
            reader = QImageReader(self.path)
            # Only read the header, not the full image
            if reader.canRead():
                size = reader.size()
                # Call the wrapper to emit the signal
                self.emitter_wrapper(self.path, size.width(), size.height())
        except Exception:
            pass

class DimensionWorker(QObject):
    """
    Manages background dimension reading.
    """
    # Signal: path, width, height
    dimensionsReady = Signal(str, int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        # Use global pool to avoid thread overhead
        self._pool = QThreadPool.globalInstance()

    def enqueue(self, path: str):
        # Create runnable and start
        # We pass a lambda/method that emits the signal
        # Note: Qt signals are thread-safe when emitted from workers
        task = DimensionRunnable(path, self.dimensionsReady.emit)
        self._pool.start(task)

    def clear(self):
        # QThreadPool.globalInstance() cannot be cleared safely of just our tasks
        # Reliance on session management in the consumer (Scanner/RowBuilder) is preferred
        pass
