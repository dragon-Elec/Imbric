"""Desktop integration helpers and Sidebar data providers."""

import gi
gi.require_version('Gio', '2.0')
from gi.repository import Gio, GLib
from pathlib import Path
from urllib.parse import unquote
from PySide6.QtCore import QObject, Signal, Slot, Property
from core.utils.gio_qtoast import GioWorkerPool

def open_with_default_app(path: str) -> bool:
    """Launch the default application for the given file path/URI."""
    try:
        gfile = Gio.File.new_for_commandline_arg(path)
        Gio.AppInfo.launch_default_for_uri(gfile.get_uri(), None)
        return True
    except GLib.Error:
        return False

class BookmarksBridge(QObject):
    """Reads GTK 3.0 bookmarks and monitors changes."""
    bookmarksChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.bookmarks_path = Path.home() / ".config" / "gtk-3.0" / "bookmarks"
        self._monitor = None
        self._setup_monitor()

    def _setup_monitor(self):
        """Watch the bookmarks file for changes."""
        if not self.bookmarks_path.parent.exists():
            return

        gfile = Gio.File.new_for_path(str(self.bookmarks_path))
        try:
            self._monitor = gfile.monitor_file(Gio.FileMonitorFlags.NONE, None)
            self._monitor.connect("changed", self._on_file_changed)
        except Exception as e:
            print(f"Failed to monitor bookmarks: {e}")

    def _on_file_changed(self, monitor, file, other_file, event_type):
        if event_type in (Gio.FileMonitorEvent.CHANGES_DONE_HINT, 
                          Gio.FileMonitorEvent.CREATED, 
                          Gio.FileMonitorEvent.DELETED):
            self.bookmarksChanged.emit()

    @Slot(result=list)
    def get_bookmarks(self):
        items = []
        if not self.bookmarks_path.exists():
            return items

        try:
            with open(self.bookmarks_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line: continue
                    parts = line.split(" ", 1)
                    uri = parts[0]
                    if not uri.startswith("file://"): continue
                    path = unquote(uri[7:])
                    name = parts[1] if len(parts) > 1 else Path(path).name
                    items.append({"name": name, "path": path, "icon": "folder"})
        except Exception as e:
            print(f"Error reading bookmarks: {e}")
        return items

def _check_trash_empty_task() -> bool:
    """Check if trash is empty using GIO query_info in background thread."""
    try:
        gfile = Gio.File.new_for_uri("trash:///")
        info = gfile.query_info("trash::item-count", Gio.FileQueryInfoFlags.NONE, None)
        count = info.get_attribute_uint32("trash::item-count")
        return count > 0
    except Exception:
        return False

class QuickAccessBridge(QObject):
    """Aggregates Standard XDG Directories and User Bookmarks."""
    itemsChanged = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._bookmarks_bridge = BookmarksBridge(self)
        self._bookmarks_bridge.bookmarksChanged.connect(self.itemsChanged.emit)
        
        self._trash_icon = "delete"
        self._pool = GioWorkerPool(max_concurrent=1, parent=self)
        self._pool.resultReady.connect(self._on_trash_status_ready)
        self._setup_trash_monitor()

    @Property(str, constant=True)
    def title(self): return "Quick Access"

    @Property(str, constant=True)
    def icon(self): return "star"

    def _setup_trash_monitor(self):
        try:
            trash_file = Gio.File.new_for_uri("trash:///")
            self._monitor = trash_file.monitor_directory(Gio.FileMonitorFlags.NONE, None)
            self._monitor.connect("changed", lambda *a: self._check_trash())
            self._check_trash() 
        except Exception: pass

    def _check_trash(self):
        self._pool.enqueue("trash_check", _check_trash_empty_task, priority=100)

    def _on_trash_status_ready(self, task_id, is_full):
        new_icon = "delete_full" if is_full else "delete"
        if self._trash_icon != new_icon:
            self._trash_icon = new_icon
            self.itemsChanged.emit()

    @Slot(result=list)
    def get_items(self):
        items = []
        home_path = Path.home()
        items.append({"name": "Home", "path": str(home_path), "icon": "home", "type": "standard"})
        items.append({"name": "Recent", "path": "recent:///", "icon": "history", "type": "standard"})
        
        xdg_dirs = [
            (GLib.UserDirectory.DIRECTORY_DESKTOP, "Desktop", "desktop_windows"), 
            (GLib.UserDirectory.DIRECTORY_DOCUMENTS, "Documents", "description"),
            (GLib.UserDirectory.DIRECTORY_DOWNLOAD, "Downloads", "file_download"),
            (GLib.UserDirectory.DIRECTORY_PICTURES, "Pictures", "image"),
            (GLib.UserDirectory.DIRECTORY_MUSIC, "Music", "music_note"),
            (GLib.UserDirectory.DIRECTORY_VIDEOS, "Videos", "movie"),
        ]
        
        for xdg_enum, name, icon in xdg_dirs:
            path_str = GLib.get_user_special_dir(xdg_enum)
            if path_str:
                gfile = Gio.File.new_for_path(path_str)
                if gfile.query_exists() and Path(path_str) != home_path:
                    items.append({"name": name, "path": path_str, "icon": icon, "type": "standard"})
        
        items.append({"name": "Trash", "path": "trash:///", "icon": self._trash_icon, "type": "standard"})
        
        existing = {i['path'] for i in items}
        for b in self._bookmarks_bridge.get_bookmarks():
            if b['path'] not in existing:
                b['type'] = "bookmark"
                items.append(b)
        return items
