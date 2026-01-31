from PySide6.QtCore import QObject, Signal, Property, Slot, QUrl, QMimeData, Qt
from PySide6.QtWidgets import QMenu
from PySide6.QtGui import QCursor, QIcon, QDrag
from ui.dialogs.conflicts import ConflictResolver, ConflictAction
from core.search_worker import SearchWorker
from ui.models.shortcuts import ShortcutAction
import os

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
            act_open.triggered.connect(lambda checked=False, p=paths[0]: self.mw.file_ops.openWithDefaultApp(p))
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
    
    @Slot(str, str)
    def renameFile(self, old_path, new_name):
        """
        Renames a file. Called from QML after user finishes editing.
        """
        if not old_path or not new_name:
            return
            
        new_path = os.path.join(os.path.dirname(old_path), new_name)
        
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
        final_name = os.path.basename(final_dest)
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
        self.mw.view_manager.zoom_in() if delta < 0 else self.mw.view_manager.zoom_out()
    
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

