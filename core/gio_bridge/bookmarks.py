from pathlib import Path
from urllib.parse import unquote
import gi
gi.require_version('Gio', '2.0')
from gi.repository import Gio, GLib
from PySide6.QtCore import QObject, Signal, Slot

class BookmarksBridge(QObject):
    """
    Reads GTK 3.0 bookmarks and monitors changes.
    """
    bookmarksChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.bookmarks_path = Path.home() / ".config" / "gtk-3.0" / "bookmarks"
        self._monitor = None
        self._setup_monitor()

    def _setup_monitor(self):
        """Watch the bookmarks file for changes."""
        # Ensure directory exists before monitoring, though usually it does on GNOME-like systems
        if not self.bookmarks_path.parent.exists():
            return

        gfile = Gio.File.new_for_path(str(self.bookmarks_path))
        try:
            self._monitor = gfile.monitor_file(Gio.FileMonitorFlags.NONE, None)
            self._monitor.connect("changed", self._on_file_changed)
        except Exception as e:
            print(f"Failed to monitor bookmarks: {e}")

    def _on_file_changed(self, monitor, file, other_file, event_type):
        """Emit signal when file changes."""
        # We listen for CHANGES_DONE_HINT (write finished) or CREATED/DELETED
        if event_type in (Gio.FileMonitorEvent.CHANGES_DONE_HINT, 
                          Gio.FileMonitorEvent.CREATED, 
                          Gio.FileMonitorEvent.DELETED):
            self.bookmarksChanged.emit()

    @Slot(result=list)
    def get_bookmarks(self):
        """
        Returns a list of dicts: [{'name': 'Pictures', 'path': '/home/user/Pictures'}, ...]
        """
        items = []
        
        if not self.bookmarks_path.exists():
            return items

        try:
            with open(self.bookmarks_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                        
                    # Format: file:///home/user/Folder Name
                    # OR: file:///home/user/Folder CustomName
                    parts = line.split(" ", 1)
                    uri = parts[0]
                    
                    if not uri.startswith("file://"):
                        continue
                        
                    path = unquote(uri[7:]) # Strip file://
                    
                    if len(parts) > 1:
                        name = parts[1]
                    else:
                        # Use directory name as label
                        name = Path(path).name
                        
                    items.append({"name": name, "path": path, "icon": "folder"})
                    
        except Exception as e:
            print(f"Error reading bookmarks: {e}")
            
        return items

