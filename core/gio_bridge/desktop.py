"""Desktop integration helpers and Sidebar data providers."""

import gi
gi.require_version('Gio', '2.0')
from gi.repository import Gio, GLib
from pathlib import Path
from urllib.parse import unquote
from PySide6.QtCore import QObject, Signal, Slot, Property
from core.utils.gio_qtoast import GioWorkerPool
from core.metadata_utils import ensure_uri

def open_with_default_app(path: str) -> bool:
    """Launch the default application for the given file path/URI."""
    try:
        gfile = Gio.File.new_for_commandline_arg(path)
        Gio.AppInfo.launch_default_for_uri(gfile.get_uri(), None)
        return True
    except GLib.Error:
        return False

_SPECIAL_DIR_CACHE = None

def get_special_dirs() -> dict:
    """Returns a dictionary mapping absolute paths to (LocalizedName, IconName) using XDG settings."""
    global _SPECIAL_DIR_CACHE
    if _SPECIAL_DIR_CACHE is not None:
        return _SPECIAL_DIR_CACHE
        
    _SPECIAL_DIR_CACHE = {
        str(Path.home()): ("Home", "user-home-symbolic")
    }
    
    xdg_dirs = [
        (GLib.UserDirectory.DIRECTORY_DESKTOP, "Desktop", "user-desktop-symbolic"), 
        (GLib.UserDirectory.DIRECTORY_DOCUMENTS, "Documents", "folder-documents-symbolic"),
        (GLib.UserDirectory.DIRECTORY_DOWNLOAD, "Downloads", "folder-download-symbolic"),
        (GLib.UserDirectory.DIRECTORY_PICTURES, "Pictures", "folder-pictures-symbolic"),
        (GLib.UserDirectory.DIRECTORY_MUSIC, "Music", "folder-music-symbolic"),
        (GLib.UserDirectory.DIRECTORY_VIDEOS, "Videos", "folder-videos-symbolic"),
    ]
    
    for xdg_enum, default_name, icon in xdg_dirs:
        path_str = GLib.get_user_special_dir(xdg_enum)
        if path_str:
            _SPECIAL_DIR_CACHE[path_str] = (default_name, icon)
            
    return _SPECIAL_DIR_CACHE

def resolve_identity(raw_path: str) -> str:
    """
    Background Worker Function: Resolves a raw path to its canonical GIO parsed name 
    """
    if not raw_path: return ""
    
    if raw_path.startswith("file://") or "://" not in raw_path:
        gfile = Gio.File.new_for_commandline_arg(raw_path)
    else:
        gfile = Gio.File.parse_name(raw_path)
        
    return gfile.get_parse_name()

def get_breadcrumb_segments(path: str, active_path: str, fast_mode: bool = False) -> list:
    """
    Universally shared logic for building breadcrumb segments.
    Works for both Instant (fast_mode) and Background (enriched) phases.
    Uses strict GIO tree-walking to preserve trailing spaces and avoid string mangling.
    """
    if not path: return []
    
    if path.startswith("file://") or "://" not in path:
        curr = Gio.File.new_for_commandline_arg(path)
    else:
        curr = Gio.File.parse_name(path)
        
    if not active_path:
        active_path = path

    if active_path.startswith("file://") or "://" not in active_path:
        active_gfile = Gio.File.new_for_commandline_arg(active_path)
    else:
        active_gfile = Gio.File.parse_name(active_path)

    home_path = str(Path.home())
    home_gfile = Gio.File.new_for_commandline_arg(home_path)
    special_dirs = get_special_dirs()
    
    segments = []
    is_future = False
    
    while curr:
        # get_parse_name() is only used as a lookup key for local special directories
        # Navigation uses get_uri() or get_path() to be safe.
        lookup_key = curr.get_parse_name()
        if lookup_key == "file:///":
            lookup_key = "/"
            
        name, icon = "", ""
        if fast_mode:
            name, icon = special_dirs.get(lookup_key, ("", ""))
        else:
            name, icon = special_dirs.get(lookup_key, ("", ""))
            if not name:
                try:
                    m = curr.find_enclosing_mount(None)
                    if m and curr.equal(m.get_root()):
                        name = m.get_name()
                        gicon = m.get_symbolic_icon() or m.get_icon()
                        if gicon and hasattr(gicon, "get_names"):
                            names = gicon.get_names()
                            if names:
                                icon = names[0]
                        # Cache the resolved Mount/Virtual Root so Fast Mode instantly uses it
                        if name:
                            special_dirs[lookup_key] = (name, icon)
                except Exception:
                    pass

        curr_basename = curr.get_basename()
        display_name = name or curr_basename
        if not display_name or display_name == "/":
            display_name = lookup_key if "://" in lookup_key else "/"

        # Use the canonical GIO Parse Name for the segment's logical identity.
        # This ensures Fast Mode and Enriched Mode always agree on 'which folder this is'
        # even if one thinks in URIs and the other in Mount Paths.
        target_path = lookup_key

        segments.insert(0, {
            "name": display_name,
            "target_path": target_path,
            "icon": icon,
            "is_first": False,
            "is_active": curr.equal(active_gfile),
            "is_future": is_future
        })
        
        if curr.equal(active_gfile):
            is_future = True
            
        parent = curr.get_parent()
        
        if curr.equal(home_gfile) and "://" not in path:
            break
            
        curr = parent

    if segments:
        segments[0]["is_first"] = True
        if not segments[0]["icon"]:
            is_home_strict = False
            first_target = segments[0]["target_path"]
            if first_target.startswith("file://") or "://" not in first_target:
                first_gfile = Gio.File.new_for_commandline_arg(first_target)
            else:
                first_gfile = Gio.File.parse_name(first_target)
            is_home_strict = first_gfile.equal(home_gfile)
            segments[0]["icon"] = "user-home-symbolic" if is_home_strict else "drive-harddisk-symbolic"
            
    return segments

def enrich_breadcrumbs(virtual_path: str, active_path: str) -> list:
    """Background Worker Entry Point."""
    return get_breadcrumb_segments(virtual_path, active_path, fast_mode=False)

class BookmarksBridge(QObject):
    """Reads GTK 3.0 bookmarks and monitors changes with background resolution."""
    bookmarksChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.bookmarks_path = Path.home() / ".config" / "gtk-3.0" / "bookmarks"
        self._cached_bookmarks = []
        self._is_resolving = False
        self._monitor = None
        
        self._pool = GioWorkerPool(max_concurrent=1, parent=self)
        self._pool.resultReady.connect(self._on_resolve_ready)
        
        self._setup_monitor()
        self._resolve_bookmarks_async()

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
            self._resolve_bookmarks_async()

    def _resolve_bookmarks_async(self):
        """Enqueue background task to parse and resolve bookmark URIs."""
        if self._is_resolving: return
        self._is_resolving = True
        self._pool.enqueue("resolve_bookmarks", self._resolve_task, priority=30)

    @staticmethod
    def _resolve_task():
        """Background Worker: Reads and resolves canonical URIs for bookmarks."""
        items = []
        path = Path.home() / ".config" / "gtk-3.0" / "bookmarks"
        if not path.exists(): return items
        
        try:
            with open(path, "r") as f:
                for line in f:
                    if not (line := line.strip()): continue
                    parts = line.split(" ", 1)
                    uri = parts[0]
                    
                    try:
                        # Resolve URI to parseable name in background
                        gfile = Gio.File.new_for_uri(uri)
                        parsed_path = gfile.get_parse_name()
                        name = parts[1] if len(parts) > 1 else gfile.get_basename()
                        
                        items.append({"name": name, "path": parsed_path, "icon": "folder"})
                    except Exception as e:
                        print(f"[g.bridge.desktop] Failed to resolve bookmark URI {uri}: {e}")
        except Exception as e:
            print(f"Error resolving bookmarks: {e}")
        return items

    def _on_resolve_ready(self, task_id, result):
        if task_id == "resolve_bookmarks":
            self._cached_bookmarks = result
            self._is_resolving = False
            self.bookmarksChanged.emit()

    @Slot(result=list)
    def get_bookmarks(self):
        """Instant result from cache."""
        return self._cached_bookmarks

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
    """Aggregates Standard XDG Directories and User Bookmarks with Async Caching."""
    itemsChanged = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._bookmarks_bridge = BookmarksBridge(self)
        self._bookmarks_bridge.bookmarksChanged.connect(self._rebuild_items_async)
        
        self._cached_items = []
        self._trash_icon = "delete"
        self._pool = GioWorkerPool(max_concurrent=1, parent=self)
        self._pool.resultReady.connect(self._on_worker_result)
        
        self._setup_trash_monitor()
        self._rebuild_items_async()

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
        except Exception as e:
            print(f"[g.bridge.desktop] Failed to monitor trash: {e}")

    def _check_trash(self):
        self._pool.enqueue("trash_check", _check_trash_empty_task, priority=100)

    def _rebuild_items_async(self):
        """Enqueue background check for standard XDG directories."""
        self._pool.enqueue("rebuild_items", self._rebuild_items_task, priority=40)

    @staticmethod
    def _rebuild_items_task():
        """Background task: Checks existence of XDG dirs and returns the core list."""
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
                # query_exists is now safe here in background
                if gfile.query_exists() and Path(path_str) != home_path:
                    items.append({"name": name, "path": path_str, "icon": icon, "type": "standard"})
                else:
                    # Log if it doesn't exist (excluding Home since we added it manually)
                    if Path(path_str) != home_path:
                        print(f"[g.bridge.desktop] Filtered out missing XDG dir: {name} ({path_str})")
        
        items.append({"name": "Trash", "path": "trash:///", "type": "standard"})
        return items

    def _on_worker_result(self, task_id, result):
        match task_id:
            case "trash_check":
                new_icon = "delete_full" if result else "delete"
                if self._trash_icon != new_icon:
                    self._trash_icon = new_icon
                    # Trigger items rebuild to refresh the trash icon in the list
                    self._rebuild_items_async()
            case "rebuild_items":
                # Merge with bookmarks from bridge
                # Trash icon needs to be dynamic based on current status
                for item in result:
                    if item.get("name") == "Trash":
                        item["icon"] = self._trash_icon
                
                # Append bookmarks
                existing_paths = {i['path'] for i in result}
                for b in self._bookmarks_bridge.get_bookmarks():
                    if b['path'] not in existing_paths:
                        b['type'] = "bookmark"
                        result.append(b)
                
                self._cached_items = result
                self.itemsChanged.emit()

    @Slot(result=list)
    def get_items(self):
        """Instant result from cache."""
        return self._cached_items

def create_desktop_mime_data(paths: list, is_cut: bool) -> 'QMimeData':
    """
    Universally robust QMimeData factory for GNOME/GTK desktop operations.
    Returns a QMimeData object containing:
    1. Standard URI List (QUrl)
    2. GNOME-specific Metadata (x-special/gnome-copied-files)
    3. Plain Text fallback
    """
    from PySide6.QtCore import QMimeData, QUrl
    from core.metadata_utils import ensure_uri
    
    mime_data = QMimeData()
    
    # 1. Standard URI List (Cross-platform/Standard DND)
    urls = [QUrl(ensure_uri(p)) for p in paths]
    mime_data.setUrls(urls)
    
    # 2. GNOME Metadata (Nautilus/Files compatibility)
    action = "cut" if is_cut else "copy"
    uris = [ensure_uri(p) for p in paths]
    gnome_data = f"{action}\n" + "\n".join(uris)
    mime_data.setData("x-special/gnome-copied-files", gnome_data.encode('utf-8'))
    
    # 3. Plain Text Fallback (Terminals/Editors)
    mime_data.setText("\n".join([u.toString() for u in urls]))
    
    return mime_data
