from PySide6.QtCore import Qt, QMimeData
from PySide6.QtGui import QDrag, QIcon, QImage, QPixmap
from core.backends.gio.helpers import ensure_uri
from core.backends.gio.desktop import create_desktop_mime_data


def start_drag_session(mainwindow, paths):
    """
    Initiates a system drag-and-drop operation.
    mainwindow: The QMainWindow instance.
    paths: List of absolute paths or URIs.
    """
    print(f"[DragHelper] Initiating drag for {len(paths)} paths: {paths}")
    if not paths:
        print("[DragHelper] Skip: No paths provided.")
        return

    # STRATEGY: Find the most appropriate 'source' widget.
    # If ShellManager is decoupled, we should use the 'container' widget
    # that actually holds the QML content.
    source_widget = mainwindow
    if hasattr(mainwindow, "shell_manager"):
        source_widget = mainwindow.shell_manager.container
        print(f"[DragHelper] Using ShellManager container as source: {source_widget}")
    else:
        print(
            f"[DragHelper] Warning: No ShellManager found, using MainWindow: {source_widget}"
        )

    drag = QDrag(source_widget)
    mime_data = create_desktop_mime_data(paths, is_cut=False)
    drag.setMimeData(mime_data)

    # Visual Feedback
    # Use standard theme icon for simplicity or first item's icon
    icon = QIcon.fromTheme("text-x-generic")
    pixmap = icon.pixmap(64, 64)
    drag.setPixmap(pixmap)
    drag.setHotSpot(pixmap.rect().center())

    # Execute Drag: Allow Copy and Move
    # This is blocking.
    drag.exec(Qt.CopyAction | Qt.MoveAction, Qt.MoveAction)
