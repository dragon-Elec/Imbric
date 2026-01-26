from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QToolBar, QHBoxLayout, QToolButton,
                               QTreeView, QSplitter, QFileSystemModel, QLineEdit, QSizePolicy)
from PySide6.QtCore import QUrl, Slot, Qt, QDir
from PySide6.QtGui import QAction, QIcon, QKeySequence

from pathlib import Path
import os

# Import core logic (shared across tabs)
from core.file_operations import FileOperations
from core.clipboard_manager import ClipboardManager
from core.file_monitor import FileMonitor
from core.transaction_manager import TransactionManager
from core.undo_manager import UndoManager
from core.trash_manager import TrashManager
from ui.widgets.progress_overlay import ProgressOverlay
from ui.widgets.status_bar import StatusBar
from ui.widgets.tab_manager import TabManager


class MainWindow(QMainWindow):
    def __init__(self, start_path=None):
        super().__init__()
        self.setWindowTitle("Imbric")
        self.resize(1200, 800)
        
        # 1. Init SHARED Core Logic (used by all tabs)
        # Note: ThumbnailProvider is now per-tab (Qt takes ownership on addImageProvider)
        self.file_ops = FileOperations()
        self.clipboard = ClipboardManager()
        self.file_monitor = FileMonitor()
        
        # Transaction Manager (Batch orchestration + Progress aggregation)
        self.transaction_manager = TransactionManager()
        
        # Undo Manager (History stack)
        self.undo_manager = UndoManager(file_operations=self.file_ops)
        
        # Trash Manager (Native Freedesktop trash)
        self.trash_manager = TrashManager()
        
        # Wire them together:
        # 1. FileOperations -> TransactionManager (operation completion tracking)
        self.file_ops.operationFinished.connect(self.transaction_manager.onOperationFinished)
        
        # 2. TrashManager -> TransactionManager (trash operations use same tracking)
        self.trash_manager.operationFinished.connect(self.transaction_manager.onOperationFinished)
        
        # 3. TransactionManager -> UndoManager (batch history)
        self.transaction_manager.historyCommitted.connect(self.undo_manager.push)
        
        # 4. Inject managers into FileOperations
        self.file_ops.setUndoManager(self.undo_manager)
        self.file_ops.setTrashManager(self.trash_manager)
        
        # Auto-refresh: When files change in the watched directory, rescan
        self.file_monitor.directoryChanged.connect(self._on_directory_changed)

        # 2. UI Setup
        self.setup_ui()
        
        # 3. Start with first tab
        initial_path = start_path if start_path else QDir.homePath()
        self.tab_manager.add_tab(initial_path)

    def setup_ui(self):
        # --- Status Bar ---
        self.status_bar = StatusBar()
        self.setStatusBar(self.status_bar)
        
        # --- Toolbar ---
        self.toolbar = QToolBar("Navigation")
        self.addToolBar(self.toolbar)
        
        # Up Button
        self.up_action = QAction(QIcon.fromTheme("go-up"), "Up", self)
        self.up_action.triggered.connect(self.go_up)
        self.toolbar.addAction(self.up_action)
        
        # Path Bar
        self.path_edit = QLineEdit()
        self.path_edit.setObjectName("PathBar")
        self.path_edit.returnPressed.connect(self._on_path_bar_submit)
        self.toolbar.addWidget(self.path_edit)
        
        # --- Standard Actions (Global Shortcuts) ---
        # Copy (Ctrl+C)
        self.act_copy = QAction("Copy", self)
        self.act_copy.setShortcut(QKeySequence.Copy)
        self.act_copy.setShortcutContext(Qt.ApplicationShortcut)
        self.act_copy.triggered.connect(self._on_copy_triggered)
        self.addAction(self.act_copy)
        
        # Cut (Ctrl+X)
        self.act_cut = QAction("Cut", self)
        self.act_cut.setShortcut(QKeySequence.Cut)
        self.act_cut.setShortcutContext(Qt.ApplicationShortcut)
        self.act_cut.triggered.connect(self._on_cut_triggered)
        self.addAction(self.act_cut)
        
        # Paste (Ctrl+V)
        self.act_paste = QAction("Paste", self)
        self.act_paste.setShortcut(QKeySequence.Paste)
        self.act_paste.setShortcutContext(Qt.ApplicationShortcut)
        self.act_paste.triggered.connect(self._on_paste_triggered)
        self.addAction(self.act_paste)
        
        # Trash (Delete)
        self.act_trash = QAction("Move to Trash", self)
        self.act_trash.setShortcut(QKeySequence.Delete)
        self.act_trash.setShortcutContext(Qt.ApplicationShortcut)
        self.act_trash.triggered.connect(self._on_trash_triggered)
        self.addAction(self.act_trash)
        
        # New Tab (Ctrl+T)
        act_new_tab = QAction("New Tab", self)
        act_new_tab.setShortcut("Ctrl+T")
        act_new_tab.setShortcutContext(Qt.ApplicationShortcut)
        act_new_tab.triggered.connect(lambda: self.tab_manager.add_tab())
        self.addAction(act_new_tab)
        
        # Close Tab (Ctrl+W)
        act_close_tab = QAction("Close Tab", self)
        act_close_tab.setShortcut("Ctrl+W")
        act_close_tab.setShortcutContext(Qt.ApplicationShortcut)
        act_close_tab.triggered.connect(lambda: self.tab_manager._close_tab(self.tab_manager.currentIndex()))
        self.addAction(act_close_tab)

        # Spacer to push Zoom buttons to the right
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.toolbar.addWidget(spacer)
        
        # Zoom Group (Compact)
        zoom_widget = QWidget()
        zoom_layout = QHBoxLayout(zoom_widget)
        zoom_layout.setSpacing(0)
        zoom_layout.setContentsMargins(0, 0, 0, 0)
        
        # Zoom Out
        self.btn_zoom_out = QToolButton()
        self.btn_zoom_out.setIcon(QIcon.fromTheme("zoom-out"))
        self.btn_zoom_out.setToolTip("Zoom Out (Ctrl+-)")
        self.btn_zoom_out.setAutoRaise(True)
        self.btn_zoom_out.clicked.connect(lambda: self.change_zoom(1))
        zoom_out_act = QAction(self)
        zoom_out_act.setShortcut("Ctrl+-")
        zoom_out_act.triggered.connect(lambda: self.change_zoom(1))
        self.addAction(zoom_out_act)
        
        # Zoom In
        self.btn_zoom_in = QToolButton()
        self.btn_zoom_in.setIcon(QIcon.fromTheme("zoom-in"))
        self.btn_zoom_in.setToolTip("Zoom In (Ctrl+=)")
        self.btn_zoom_in.setAutoRaise(True)
        self.btn_zoom_in.clicked.connect(lambda: self.change_zoom(-1))
        zoom_in_act = QAction(self)
        zoom_in_act.setShortcut("Ctrl+=")
        zoom_in_act.triggered.connect(lambda: self.change_zoom(-1))
        self.addAction(zoom_in_act)
        
        zoom_layout.addWidget(self.btn_zoom_out)
        zoom_layout.addWidget(self.btn_zoom_in)
        
        self.toolbar.addWidget(zoom_widget)

        # --- Main Layout (Central Widget with Overlay) ---
        central_widget = QWidget()
        central_layout = QVBoxLayout(central_widget)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        
        # Main content splitter
        self.main_splitter = QSplitter(Qt.Horizontal)
        central_layout.addWidget(self.main_splitter, 1)
        
        # Progress overlay (bottom)
        self.progress_overlay = ProgressOverlay()
        self.file_ops.operationStarted.connect(self.progress_overlay.onOperationStarted)
        self.file_ops.operationProgress.connect(self.progress_overlay.onOperationProgress)
        self.file_ops.operationCompleted.connect(self.progress_overlay.onOperationCompleted)
        self.file_ops.operationError.connect(self.progress_overlay.onOperationError)
        self.progress_overlay.cancelRequested.connect(self.file_ops.cancel)
        central_layout.addWidget(self.progress_overlay)
        
        # Connect operation completion to logic (e.g. selection persistence)
        self.file_ops.operationCompleted.connect(self._on_op_completed)
        
        self.setCentralWidget(central_widget)
        
        # Sidebar (Native QTreeView with QFileSystemModel)
        self.fs_model = QFileSystemModel()
        self.fs_model.setRootPath(QDir.rootPath())
        self.fs_model.setFilter(QDir.NoDotAndDotDot | QDir.AllDirs)
        
        self.sidebar_tree = QTreeView()
        self.sidebar_tree.setObjectName("SidebarTree")
        self.sidebar_tree.setModel(self.fs_model)
        self.sidebar_tree.setRootIndex(self.fs_model.index(QDir.homePath()))
        self.sidebar_tree.clicked.connect(self._on_sidebar_clicked)
        self.sidebar_tree.setHeaderHidden(True)
        for i in range(1, 4):
            self.sidebar_tree.hideColumn(i)
            
        self.main_splitter.addWidget(self.sidebar_tree)
        self.main_splitter.setStretchFactor(0, 0)
        
        # --- TAB MANAGER (replaces single QQuickView) ---
        self.tab_manager = TabManager(self)
        self.tab_manager.currentPathChanged.connect(self._on_tab_path_changed)
        
        self.main_splitter.addWidget(self.tab_manager)
        self.main_splitter.setStretchFactor(1, 1)
        
        # Initial splitter sizes
        self.main_splitter.setSizes([250, 950])

    # --- NAVIGATION (delegates to current tab) ---
    
    def navigate_to(self, path):
        """Navigate the current tab to a path."""
        path = str(path)
        if not os.path.exists(path):
            return
            
        print(f"Navigating to: {path}")
        self.tab_manager.navigate_to(path)
        
        # Update file monitor
        self.file_monitor.watch(path)
        
        # Sync sidebar
        index = self.fs_model.index(path)
        if index.isValid():
            self.sidebar_tree.setCurrentIndex(index)
            self.sidebar_tree.scrollTo(index)

    def go_up(self):
        """Navigate current tab to parent directory."""
        tab = self.tab_manager.current_tab
        if tab:
            parent = os.path.dirname(tab.current_path)
            if parent and os.path.exists(parent):
                self.navigate_to(parent)

    def _on_path_bar_submit(self):
        """Handle Enter press in path bar with error feedback."""
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QToolTip
        from PySide6.QtGui import QCursor
        
        path = self.path_edit.text().strip()
        previous_path = self.current_path
        
        if not path:
            return
            
        if os.path.exists(path) and os.path.isdir(path):
            # Valid directory - navigate
            self.navigate_to(path)
        else:
            # Invalid path - show error feedback
            error_msg = "Path does not exist" if not os.path.exists(path) else "Not a directory"
            
            # Show tooltip near path bar
            QToolTip.showText(
                self.path_edit.mapToGlobal(self.path_edit.rect().bottomLeft()),
                f"⚠ {error_msg}: {path}",
                self.path_edit,
                self.path_edit.rect(),
                2000  # 2 second timeout
            )
            
            # Visual feedback - red border
            self.path_edit.setStyleSheet("QLineEdit { border: 2px solid #d32f2f; }")
            
            # Reset after delay
            def reset_style():
                self.path_edit.setStyleSheet("")
                self.path_edit.setText(previous_path)
            
            QTimer.singleShot(1500, reset_style)

    def _on_sidebar_clicked(self, index):
        path = self.fs_model.filePath(index)
        self.navigate_to(path)
    
    def _on_tab_path_changed(self, path):
        """Sync path bar with current tab's path."""
        self.path_edit.setText(path)
        self.status_bar.resetCounts()
        
        # Update status bar with current tab's scanner
        tab = self.tab_manager.current_tab
        if tab:
            tab.scanner.filesFound.connect(self.status_bar.updateItemCount)
    
    def _on_directory_changed(self):
        """Called by FileMonitor when the watched directory changes."""
        tab = self.tab_manager.current_tab
        if tab:
            tab.navigate_to(tab.current_path)

    # --- PROPERTY ACCESSORS (for AppBridge compatibility) ---
    
    @property
    def current_path(self):
        """Current path of active tab."""
        tab = self.tab_manager.current_tab
        return tab.current_path if tab else str(Path.home())
    
    @property
    def bridge(self):
        """Bridge of active tab."""
        tab = self.tab_manager.current_tab
        return tab.bridge if tab else None
    
    @property
    def qml_view(self):
        """QML view of active tab."""
        tab = self.tab_manager.current_tab
        return tab.qml_view if tab else None
    
    @property
    def splitter(self):
        """Column splitter of active tab."""
        tab = self.tab_manager.current_tab
        return tab.splitter if tab else None

    # --- COPY / CUT / PASTE / TRASH ---

    @Slot()
    def _on_copy_triggered(self):
        tab = self.tab_manager.current_tab
        if not tab:
            print("[SHORTCUT] Copy: No active tab")
            return
        
        selection = tab.selection
        if not selection:
            print("[SHORTCUT] Copy: No items selected")
            return
            
        print(f"[SHORTCUT] Copy: {len(selection)} items")
        self.clipboard.copy(selection)
            
    @Slot()
    def _on_cut_triggered(self):
        tab = self.tab_manager.current_tab
        if not tab:
            print("[SHORTCUT] Cut: No active tab")
            return
        
        selection = tab.selection
        if not selection:
            print("[SHORTCUT] Cut: No items selected")
            return
            
        print(f"[SHORTCUT] Cut: {len(selection)} items")
        self.clipboard.cut(selection)
            
    @Slot(str, str, str)
    def _on_op_completed(self, op_type, path, result_data):
        """
        Called when a file operation completes.
        Used for logic that depends on the result (e.g. re-selecting renamed files, triggering rename on new folder).
        """
        tab = self.tab_manager.current_tab
        if not tab or not tab.bridge:
            return
            
        if op_type == "rename":
            new_path = result_data
            # Re-select renamed file
            print(f"[MainWindow] Re-selecting renamed file: {new_path}")
            tab.bridge.selectPath(new_path)
        
        elif op_type == "createFolder":
            # Check if we should trigger inline rename for this new folder
            pending_path = tab.bridge._pending_rename_path
            if pending_path and pending_path == path:
                tab.bridge._pending_rename_path = None  # Clear flag
                # Trigger rename after a short delay to allow FileMonitor to refresh
                from PySide6.QtCore import QTimer
                QTimer.singleShot(100, lambda: tab.bridge.renameRequested.emit(path))

    @Slot()
    def _on_paste_triggered(self):
        tab = self.tab_manager.current_tab
        if tab and tab.bridge:
            print("[SHORTCUT] Paste triggered")
            tab.bridge.paste()
        else:
            print("[SHORTCUT] Paste: No active tab/bridge")

    @Slot()
    def _on_trash_triggered(self):
        tab = self.tab_manager.current_tab
        if not tab:
            print("[SHORTCUT] Trash: No active tab")
            return
        
        selection = tab.selection
        if not selection:
            print("[SHORTCUT] Trash: No items selected")
            return
            
        print(f"[SHORTCUT] Trash: {len(selection)} items")
        self.file_ops.trashMultiple(selection)

    # --- ZOOM ---

    def change_zoom(self, delta):
        """Adjust zoom for the current tab."""
        tab = self.tab_manager.current_tab
        if tab:
            tab.change_zoom(delta)

    # --- SHUTDOWN ---

    def closeEvent(self, event):
        """Clean shutdown of worker threads."""
        self.file_ops.shutdown()
        super().closeEvent(event)
