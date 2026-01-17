from PySide6.QtCore import QObject, Signal, Property, Slot, QUrl, QMimeData, Qt
from PySide6.QtWidgets import QMenu
from PySide6.QtGui import QCursor, QIcon, QDrag
import os

class AppBridge(QObject):
    pathChanged = Signal(str)
    targetCellWidthChanged = Signal(int)
    
    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        self._target_cell_width = 75

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
        
        # Perform Copy (default for drag and drop)
        for src in paths:
            # Generate unique destination
            dest = self._get_unique_destination(target_dir, src)
            
            # Simple check: If dropping file onto itself in the same dir and no rename needed
            # (although _get_unique_destination handles rename, we assume Drag = Copy)
            
            self.mw.file_ops.copy(src, dest)

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
            act_open.triggered.connect(lambda: self.mw.file_ops.openWithDefaultApp(path))
            menu.addSeparator()
        
        # Copy / Cut / Paste
        act_copy = menu.addAction(QIcon.fromTheme("edit-copy"), "Copy")
        act_copy.triggered.connect(lambda: self.mw.clipboard.copy(paths))
        
        act_cut = menu.addAction(QIcon.fromTheme("edit-cut"), "Cut")
        act_cut.triggered.connect(lambda: self.mw.clipboard.cut(paths))
        
        act_paste = menu.addAction(QIcon.fromTheme("edit-paste"), "Paste")
        act_paste.setEnabled(self.mw.clipboard.hasFiles())
        act_paste.triggered.connect(lambda: self.paste())
        
        menu.addSeparator()
        
        # Rename (single only)
        if is_single:
            act_rename = menu.addAction(QIcon.fromTheme("edit-rename"), "Rename")
            # TODO: Inline rename
            
        # Trash
        act_trash = menu.addAction(QIcon.fromTheme("user-trash"), "Move to Trash")
        act_trash.triggered.connect(lambda: self.mw.file_ops.trashMultiple(paths))
        
        # Show at cursor position
        menu.exec(QCursor.pos())
    
    @Slot()
    def showBackgroundContextMenu(self):
        """
        Shows a context menu for empty space (no file selected).
        Options: Paste, New Folder, Select All, Properties
        """
        menu = QMenu(self.mw)
        
        # Paste
        act_paste = menu.addAction(QIcon.fromTheme("edit-paste"), "Paste")
        act_paste.setEnabled(self.mw.clipboard.hasFiles())
        act_paste.triggered.connect(lambda: self.paste())
        
        menu.addSeparator()
        
        # New Folder
        act_new_folder = menu.addAction(QIcon.fromTheme("folder-new"), "New Folder")
        act_new_folder.triggered.connect(lambda: self._create_new_folder())
        
        menu.addSeparator()
        
        # Select All
        act_select_all = menu.addAction(QIcon.fromTheme("edit-select-all"), "Select All")
        act_select_all.triggered.connect(lambda: self._select_all())
        
        # Show at cursor position
        menu.exec(QCursor.pos())
    
    def _create_new_folder(self):
        """Creates a new folder in the current directory with a dialog."""
        from PySide6.QtWidgets import QInputDialog
        
        name, ok = QInputDialog.getText(
            self.mw, "New Folder", "Enter folder name:", text="New Folder"
        )
        
        if ok and name:
            new_path = os.path.join(self.mw.current_path, name)
            self.mw.file_ops.createFolder(new_path)
    
    def _select_all(self):
        """Selects all items in the current view."""
        # Get all paths from the column splitter
        all_paths = []
        for column in self.mw.splitter.getColumns():
            for item in column:
                all_paths.append(item.get('path', ''))
        
        # Signal QML to select all (via root object)
        root = self.mw.qml_view.rootObject()
        if root:
            selection_model = root.property("selectionModel")
            if selection_model:
                selection_model.setProperty("selection", all_paths)
    
    def _get_unique_destination(self, dest_folder, source_path):
        """Generates unique path e.g. 'file (Copy).txt'."""
        import os
        filename = os.path.basename(source_path)
        dest_path = os.path.join(dest_folder, filename)
        
        if not os.path.exists(dest_path):
            return dest_path
            
        base, ext = os.path.splitext(filename)
        counter = 1
        new_name = f"{base} (Copy){ext}"
        dest_path = os.path.join(dest_folder, new_name)
        
        while os.path.exists(dest_path):
            counter += 1
            new_name = f"{base} (Copy {counter}){ext}"
            dest_path = os.path.join(dest_folder, new_name)
            
        return dest_path

    @Slot()
    def paste(self):
        """Pastes files from clipboard to current directory."""
        files = self.mw.clipboard.getFiles()
        is_cut = self.mw.clipboard.isCut()
        
        if not files: return
            
        print(f"Pasting {len(files)} files (Cut: {is_cut})")
        
        for src in files:
            dest = self._get_unique_destination(self.mw.current_path, src)
            
            if is_cut:
                self.mw.file_ops.move(src, dest)
            else:
                self.mw.file_ops.copy(src, dest)
        
        if is_cut:
            self.mw.clipboard.clear()
        
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

