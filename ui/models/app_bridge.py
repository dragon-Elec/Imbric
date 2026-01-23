from PySide6.QtCore import QObject, Signal, Property, Slot, QUrl, QMimeData, Qt
from PySide6.QtWidgets import QMenu
from PySide6.QtGui import QCursor, QIcon, QDrag
from ui.dialogs.conflict_dialog import ConflictResolver, ConflictAction
from core.search_worker import SearchWorker
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
        return self.mw.clipboard.getCutPaths()

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
        """
        if not urls:
            return
            
        # Convert QUrl strings to local paths
        paths = []
        for u in urls:
            qurl = QUrl(u)
            if qurl.isLocalFile():
                paths.append(qurl.toLocalFile())
        
        if not paths:
            return

        target_dir = dest_dir if dest_dir else self.mw.current_path
        
        # Determine device of target directory
        try:
            target_dev = os.stat(target_dir).st_dev
        except OSError:
            target_dev = None

        # Create conflict resolver for this drop operation
        resolver = ConflictResolver(self.mw)
        
        for src in paths:
            # Calculate destination path
            dest = os.path.join(target_dir, os.path.basename(src))
            
            # Skip if dropping file onto itself
            if os.path.abspath(src) == os.path.abspath(dest):
                print(f"[DROP] Skipped: Same file {os.path.basename(src)}")
                continue
            
            # Resolve conflict (shows dialog if dest exists)
            action, final_dest = resolver.resolve(src, dest)
            
            if action == ConflictAction.CANCEL:
                print("[DROP] Cancelled by user")
                break
            elif action == ConflictAction.SKIP:
                print(f"[DROP] Skipped: {os.path.basename(src)}")
                continue
            
            # Check if source is on same device
            is_same_device = False
            if target_dev is not None:
                try:
                    src_dev = os.stat(src).st_dev
                    is_same_device = (src_dev == target_dev)
                except OSError:
                    pass
            
            src_dir = os.path.dirname(os.path.abspath(src))
            same_dir = src_dir == os.path.abspath(target_dir)

            if same_dir:
                # Dragging to same folder -> Copy/Clone
                self.mw.file_ops.copy(src, final_dest)
            elif is_same_device:
                self.mw.file_ops.move(src, final_dest)
            else:
                self.mw.file_ops.copy(src, final_dest)

    @Slot(str)
    def openPath(self, path):
        self.mw.navigate_to(path)
    
    @Slot(list)
    def showContextMenu(self, paths):
        """
        Shows a native QMenu for the selected file(s).
        Called from QML on right-click.
        """
        if not paths:
            return
            
        menu = QMenu(self.mw)
        
        # Single vs Multi selection
        is_single = len(paths) == 1
        path = paths[0] if is_single else None
        
        # Open (single only)
        if is_single:
            act_open = menu.addAction(QIcon.fromTheme("document-open"), "Open")
            act_open.triggered.connect(lambda checked=False, p=path: self.mw.file_ops.openWithDefaultApp(p))
            menu.addSeparator()
        
        # Copy / Cut / Paste
        act_copy = menu.addAction(QIcon.fromTheme("edit-copy"), "Copy")
        act_copy.triggered.connect(lambda checked=False, p=paths: self.mw.clipboard.copy(p))
        
        act_cut = menu.addAction(QIcon.fromTheme("edit-cut"), "Cut")
        act_cut.triggered.connect(lambda checked=False, p=paths: self.mw.clipboard.cut(p))
        
        act_paste = menu.addAction(QIcon.fromTheme("edit-paste"), "Paste")
        act_paste.setEnabled(self.mw.clipboard.hasFiles())
        act_paste.triggered.connect(lambda: self.paste())
        
        menu.addSeparator()
        
        # Rename (single only)
        if is_single:
            act_rename = menu.addAction(QIcon.fromTheme("edit-rename"), "Rename")
            act_rename.triggered.connect(lambda checked=False, p=path: self.renameRequested.emit(p))
            
        # Move to Trash (All)
        menu.addSeparator()
        act_trash = menu.addAction(QIcon.fromTheme("user-trash"), "Move to Trash")
        act_trash.triggered.connect(lambda checked=False, p=paths: self.mw.file_ops.trashMultiple(p))
            
        menu.exec_(QCursor.pos())

    @Slot()
    def showBackgroundContextMenu(self):
        """
        Shows a context menu for empty space.
        """
        menu = QMenu(self.mw)
        
        act_paste = menu.addAction(QIcon.fromTheme("edit-paste"), "Paste")
        act_paste.setEnabled(self.mw.clipboard.hasFiles())
        act_paste.triggered.connect(lambda: self.paste())
        
        menu.addSeparator()
        
        act_new_folder = menu.addAction(QIcon.fromTheme("folder-new"), "New Folder")
        act_new_folder.triggered.connect(lambda: self._create_new_folder())
        
        menu.exec_(QCursor.pos())
    
    def _create_new_folder(self):
        """Create a new folder with unique name (Untitled Folder, Untitled Folder (2), etc.)"""
        base_name = "Untitled Folder"
        folder_path = os.path.join(self.mw.current_path, base_name)
        
        # Auto-number if exists
        counter = 2
        while os.path.exists(folder_path):
            folder_path = os.path.join(self.mw.current_path, f"{base_name} ({counter})")
            counter += 1
        
        self.queueSelectionAfterRefresh([folder_path])
        self._pending_rename_path = folder_path  # Trigger rename after folder is created
        self.mw.file_ops.createFolder(folder_path)
    
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
        """Pastes files from clipboard to current directory."""
        files = self.mw.clipboard.getFiles()
        is_cut = self.mw.clipboard.isCut()
        
        if not files:
            print("[PASTE] No files in clipboard")
            return
            
        print(f"[PASTE] {len(files)} files (Cut: {is_cut})")
        
        # Create conflict resolver for this paste operation
        resolver = ConflictResolver(self.mw)
        
        # Track results
        successful_count = 0
        skipped_count = 0
        failed_files = []
        cancelled = False
        pasted_paths = []  # Track destination paths for post-paste selection
        
        for src in files:
            # Check if source file still exists
            if not os.path.exists(src):
                print(f"[PASTE] SKIP: Source no longer exists: {src}")
                failed_files.append(src)
                continue
            
            # Calculate initial destination
            dest = os.path.join(self.mw.current_path, os.path.basename(src))
            
            # Resolve conflict (shows dialog if dest exists)
            action, final_dest = resolver.resolve(src, dest)
            
            if action == ConflictAction.CANCEL:
                print("[PASTE] Cancelled by user")
                cancelled = True
                break
            elif action == ConflictAction.SKIP:
                print(f"[PASTE] Skipped: {os.path.basename(src)}")
                skipped_count += 1
                continue
            
            # OVERWRITE or RENAME — proceed with operation
            if is_cut:
                self.mw.file_ops.move(src, final_dest)
            else:
                self.mw.file_ops.copy(src, final_dest)
            
            pasted_paths.append(final_dest)  # Track for selection
            successful_count += 1
        
        # Queue paths for selection after directory refreshes
        if pasted_paths:
            self.queueSelectionAfterRefresh(pasted_paths)
        
        # Clear clipboard only if cut mode, not cancelled, and no failures
        if is_cut and not cancelled and len(failed_files) == 0:
            self.mw.clipboard.clear()
            print(f"[PASTE] Complete: {successful_count} moved, {skipped_count} skipped, clipboard cleared")
        elif is_cut:
            print(f"[PASTE] Partial: {successful_count} moved, {skipped_count} skipped, {len(failed_files)} failed")
        else:
            print(f"[PASTE] Complete: {successful_count} copied, {skipped_count} skipped")
    
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
        """
        Zoom in or out. Called from QML on Ctrl+Scroll.
        delta: positive = zoom out (more columns), negative = zoom in (fewer columns)
        """
        self.mw.change_zoom(delta)
    
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

