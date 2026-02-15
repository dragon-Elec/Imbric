import gi
gi.require_version('Gio', '2.0')
from gi.repository import GLib, Gio
from PySide6.QtCore import QObject, Signal, Slot
from pathlib import Path

# Import the reactive bookmarks bridge
from core.gio_bridge.bookmarks import BookmarksBridge

class QuickAccessBridge(QObject):
    """
    Aggregates Standard XDG Directories and User Bookmarks for the Quick Access Grid.
    """
    itemsChanged = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._bookmarks_bridge = BookmarksBridge(self)
        self._bookmarks_bridge.bookmarksChanged.connect(self.itemsChanged.emit)
        
        # [NEW] Async Trash Monitoring
        self._trash_icon = "delete"
        self._trash_monitor = None
        self._setup_trash_monitor()

    def _setup_trash_monitor(self):
        try:
            self._trash_file = Gio.File.new_for_uri("trash:///")
            self._trash_monitor = self._trash_file.monitor_directory(Gio.FileMonitorFlags.NONE, None)
            self._trash_monitor.connect("changed", self._on_trash_changed)
            
            # Initial check
            self._check_trash_status()
        except Exception:
            pass

    def _on_trash_changed(self, monitor, file, other_file, event_type):
        self._check_trash_status()

    def _check_trash_status(self):
        self._trash_file.enumerate_children_async(
            "standard::name",
            Gio.FileQueryInfoFlags.NONE,
            GLib.PRIORITY_DEFAULT,
            None,
            self._on_trash_enumerated,
            None
        )

    def _on_trash_enumerated(self, source, result, user_data):
        try:
            enumerator = source.enumerate_children_finish(result)
            enumerator.next_files_async(
                1, 
                GLib.PRIORITY_DEFAULT, 
                None, 
                self._on_trash_peek, 
                enumerator
            )
        except GLib.Error:
            pass

    def _on_trash_peek(self, source, result, enumerator):
        try:
            files = source.next_files_finish(result)
            new_icon = "delete_full" if files else "delete"
            
            if self._trash_icon != new_icon:
                self._trash_icon = new_icon
                self.itemsChanged.emit()
            
            enumerator.close_async(GLib.PRIORITY_LOW, None, None, None)
        except GLib.Error:
            pass
        
    @Slot(result=list)
    def get_items(self):
        """
        Returns a list of items for the grid:
        [Home, Desktop, Docs, Downloads, Music, Pics, Videos, ...Bookmarks]
        """
        items = []
        
        # 1. Home Directory (Always first)
        home_path = Path.home()
        items.append({
            "name": "Home",
            "path": str(home_path),
            "icon": "home",
            "type": "standard"
        })

        # 1.5 Recent (Standard)
        items.append({
            "name": "Recent",
            "path": "recent:///",
            "icon": "history",
            "type": "standard"
        })
        
        # 2. Standard XDG Directories
        # Map GLib UserDirectory constants to (Name, IconName)
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
                p = Path(path_str)
                # Only add if it exists and is NOT the home directory itself 
                # (sometimes Desktop is Home on weird configs, but usually distinct)
                if p.exists() and p != home_path:
                    items.append({
                        "name": name,
                        "path": path_str,
                        "icon": icon,
                        "type": "standard"
                    })
        
        # 2.5 Trash (Standard) - [Async]
        items.append({
            "name": "Trash",
            "path": "trash:///",
            # Use cached icon updated by async monitor
            "icon": self._trash_icon,
            "type": "standard"
        })
                
        # 3. User Bookmarks
        # We append these after the standard directories
        user_bookmarks = self._bookmarks_bridge.get_bookmarks()
        
        # Filter duplicates: Don't show "Downloads" again if it's already in standard dirs
        existing_paths = {item['path'] for item in items}
        
        for b in user_bookmarks:
            if b['path'] not in existing_paths:
                b['type'] = "bookmark"
                # Keep 'folder' icon for generic bookmarks, or map specific names if we want
                items.append(b)
                
        return items
