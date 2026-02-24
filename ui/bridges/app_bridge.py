from PySide6.QtCore import QObject, Signal, Property, Slot, QUrl, QMimeData, Qt
from PySide6.QtWidgets import QMenu
from PySide6.QtGui import QCursor, QIcon, QDrag
from ui.services.conflict_resolver import ConflictResolver
from ui.dialogs.conflicts import ConflictAction
from core.search_worker import SearchWorker
from ui.models.shortcuts import ShortcutAction
from core.gio_bridge.desktop import open_with_default_app as _open_file


class AppBridge(QObject):
    pathChanged = Signal(str)
    targetCellWidthChanged = Signal(int)
    renameRequested = Signal(str)
    cutPathsChanged = Signal()  # Emitted when clipboard cut state changes
    
    # Search signals
    searchResultsFound = Signal(list)   # Batch of paths
    searchFinished = Signal(int)         # Total count
    searchError = Signal(str)            # Error message
    
    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        self._target_cell_width = 75
        self._pending_select_paths = []  # Paths to select after next directory refresh
        self._pending_rename_path = None  # Path to trigger rename after createFolder completes
        
        # Initialize search worker
        self._search_worker = SearchWorker(self)
        self._search_worker.resultsFound.connect(self.searchResultsFound)
        self._search_worker.searchFinished.connect(self.searchFinished)
        self._search_worker.searchError.connect(self.searchError)
        
        # Connect to clipboard changes
        self.mw.clipboard.clipboardChanged.connect(self._on_clipboard_changed)
    
    def _on_clipboard_changed(self):
        self.cutPathsChanged.emit()
    
    @Property(list, notify=cutPathsChanged)
    def cutPaths(self):
        """Returns list of paths currently in cut state."""
        # Delegated to FileManager
        return self.mw.file_manager.get_cut_paths()

    @Slot(list)
    def startDrag(self, paths):
        """
        Initiates a system drag-and-drop operation for the given paths.
        This is a blocking call (exec) until drag ends.
        """
        if not paths:
            return

        drag = QDrag(self.mw)
        mime_data = QMimeData()
        
        # Format as text/uri-list
        urls = [QUrl.fromLocalFile(p) for p in paths]
        mime_data.setUrls(urls)
        
        drag.setMimeData(mime_data)
        
        # VISUAL FEEDBACK: Create a pixmap that looks like a file/stack of files
        # We grab a standard icon from the theme
        icon = QIcon.fromTheme("text-x-generic")
        pixmap = icon.pixmap(64, 64)
        drag.setPixmap(pixmap)
        drag.setHotSpot(pixmap.rect().center())
        
        # Execute Drag
        # Qt.MoveAction | Qt.CopyAction allows both. default to Copy.
        drag.exec(Qt.CopyAction | Qt.MoveAction, Qt.CopyAction)

    @Slot(list, str)
    def handleDrop(self, urls, dest_dir=None):
        """
        Handles files dropped onto the view or a folder.
        Delegated to FileManager.
        """
        self.mw.file_manager.handle_drop(urls, dest_dir)

    @Slot(str)
    def openPath(self, path):
        self.mw.navigate_to(path)
    
    @Slot(list)
    def showContextMenu(self, paths):
        """
        Shows a native QMenu using ActionManager actions.
        """
        if not paths: return
            
        menu = QMenu(self.mw)
        am = self.mw.action_manager
        
        is_single = len(paths) == 1
        
        # Open (single only) - we don't have an action for "Open" in AM yet (it's logic here)
        # But we can keep specific logic or move it. 
        # For now, let's keep Open logic or create a one-off action.
        if is_single:
            act_open = menu.addAction(QIcon.fromTheme("document-open"), "Open")
            act_open.triggered.connect(lambda checked=False, p=paths[0]: _open_file(p))
            menu.addSeparator()
        
        menu.addAction(am.get_action(ShortcutAction.COPY))
        menu.addAction(am.get_action(ShortcutAction.CUT))
        
        # Paste needs enabled check
        act_paste = am.get_action(ShortcutAction.PASTE)
        act_paste.setEnabled(self.mw.file_manager.get_clipboard_files() != [])
        menu.addAction(act_paste)
        
        menu.addSeparator()
        
        if is_single:
            menu.addAction(am.get_action(ShortcutAction.RENAME))
            
        menu.addSeparator()
        menu.addAction(am.get_action(ShortcutAction.TRASH))
            
        menu.exec(QCursor.pos())

    @Slot()
    def showBackgroundContextMenu(self):
        """Shows a context menu for empty space."""
        menu = QMenu(self.mw)
        am = self.mw.action_manager
        
        act_paste = am.get_action(ShortcutAction.PASTE)
        act_paste.setEnabled(self.mw.file_manager.get_clipboard_files() != [])
        menu.addAction(act_paste)
        
        menu.addSeparator()
        menu.addAction(am.get_action(ShortcutAction.NEW_FOLDER))
        
        menu.exec(QCursor.pos())
    
    # _create_new_folder moved to FileManager
    
    @Slot(str, result=str)
    def getThumbnailPath(self, path: str) -> str:
        """
        [DEPRECATED] Check if a native GNOME thumbnail exists for the file.
        Returns direct file:// URL if cached, else fallback to image:// provider.
        
        NOTE: This method is no longer called from QML during scroll.
        Thumbnail URL resolution has been moved to RowBuilder._resolve_thumbnail_url()
        which pre-computes the URL at load time, eliminating blocking I/O from
        the render path. Kept for backward compatibility.
        """
        import hashlib
        import urllib.parse
        from pathlib import Path
        
        try:
            # 1. Construct canonical URI (file:///path/to/file)
            # Must be quote-encoded (e.g. " " -> "%20")
            uri = "file://" + urllib.parse.quote(path)
            
            # 2. GNOME Thumbnail Spec: MD5 of URI
            md5_hash = hashlib.md5(uri.encode('utf-8')).hexdigest()
            
            # 3. Check Large Cache (256px)
            # The standard location is ~/.cache/thumbnails/large/
            cache_dir = Path.home() / ".cache" / "thumbnails" / "large"
            thumb_path = cache_dir / f"{md5_hash}.png"
            
            if thumb_path.exists():
                # SUCCESS: Return direct path to bypass Python loader
                return f"file://{thumb_path}"
                
        except Exception as e:
            print(f"[AppBridge] Thumbnail lookup failed: {e}")
            
        # FALLBACK: Ask the generator to make one
        return f"image://thumbnail/{path}"

    @Slot(str, str)
    def renameFile(self, old_path, new_name):
        """
        Renames a file. Called from QML after user finishes editing.
        """
        if not old_path or not new_name:
            return
            
        from gi.repository import Gio
        gfile = Gio.File.parse_name(old_path)
        parent = gfile.get_parent()
        if not parent:
            return
            
        new_gfile = parent.get_child(new_name)
        new_path = new_gfile.get_path() or new_gfile.get_uri()
        
        # Check if name actually changed
        if old_path == new_path:
            return
            
        print(f"[AppBridge] Renaming '{old_path}' -> '{new_name}'")
        
        # Creates a single-use resolver for this rename op
        resolver = ConflictResolver(self.mw)
        action, final_dest = resolver.resolve_rename(old_path, new_path)
        
        if action == ConflictAction.CANCEL or action == ConflictAction.SKIP:
            return
            
        # Overwrite or Rename logic
        final_gfile = Gio.File.parse_name(final_dest)
        final_name = final_gfile.get_basename()
        self.mw.file_ops.rename(old_path, final_name)

    @Slot()
    def paste(self):
        self.mw.file_manager.paste_to_current()
    
    def queueSelectionAfterRefresh(self, paths):
        """Queue paths to be selected after the next directory refresh."""
        self._pending_select_paths = paths
    
    def selectPendingPaths(self):
        """Called after directory refresh to select queued files. Returns and clears the queue."""
        paths = self._pending_select_paths
        self._pending_select_paths = []
        return paths
        
    @Property(int, notify=targetCellWidthChanged)
    def targetCellWidth(self):
        return self._target_cell_width
        
    @targetCellWidth.setter
    def targetCellWidth(self, val):
        if self._target_cell_width != val:
            self._target_cell_width = val
            self.targetCellWidthChanged.emit(val)
    
    @Slot(int)
    def zoom(self, delta):
        # FIX: Wheel Up (Positive) should Zoom In
        self.mw.view_manager.zoom_in() if delta > 0 else self.mw.view_manager.zoom_out()
    
    # -------------------------------------------------------------------------
    # SEARCH API
    # -------------------------------------------------------------------------
    
    @Slot(str, str, bool)
    def startSearch(self, directory: str, pattern: str, recursive: bool = True):
        """
        Start a file search in the background.
        
        Results are emitted via searchResultsFound signal in batches.
        """
        self._search_worker.start_search(directory, pattern, recursive)
    
    @Slot()
    def cancelSearch(self):
        """Cancel the current search."""
        self._search_worker.cancel()
    
    @Property(str, constant=True)
    def searchEngineName(self) -> str:
        """Returns the name of the current search engine (fd or scandir)."""
        return self._search_worker.engine_name

