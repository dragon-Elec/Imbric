from PySide6.QtCore import Qt, QUrl, QMimeData
from PySide6.QtGui import QDrag, QIcon

def start_drag_session(parent, paths):
    """
    Initiates a system drag-and-drop operation for the given paths.
    This is a blocking call (exec) until drag ends.
    """
    if not paths: return

    drag = QDrag(parent)
    mime_data = QMimeData()
    
    # Format as text/uri-list
    urls = [QUrl.fromLocalFile(p) for p in paths]
    mime_data.setUrls(urls)
    
    drag.setMimeData(mime_data)
    
    # VISUAL FEEDBACK: Create a pixmap that looks like a file/stack of files
    icon = QIcon.fromTheme("text-x-generic")
    pixmap = icon.pixmap(64, 64)
    drag.setPixmap(pixmap)
    drag.setHotSpot(pixmap.rect().center())
    
    # Execute Drag: Allow Copy and Move, default to Move
    drag.exec(Qt.CopyAction | Qt.MoveAction, Qt.MoveAction)
