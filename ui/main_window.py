from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QToolBar, QHBoxLayout, QToolButton,
                               QTreeView, QSplitter, QFileSystemModel, QLineEdit, QSizePolicy)
from PySide6.QtCore import QUrl, Slot, Qt, QDir
from PySide6.QtGui import QAction, QIcon, QKeySequence



from pathlib import Path
import os

# Import our core logic
from core.gio_bridge.scanner import FileScanner
from ui.models.column_splitter import ColumnSplitter
from core.image_providers.thumbnail_provider import ThumbnailProvider
from core.selection_helper import SelectionHelper
from core.file_operations import FileOperations
from core.clipboard_manager import ClipboardManager
from core.file_monitor import FileMonitor
from ui.widgets.progress_overlay import ProgressOverlay
from ui.widgets.status_bar import StatusBar

class MainWindow(QMainWindow):
    def __init__(self, start_path=None):
        super().__init__()
        self.setWindowTitle("Imbric")
        self.resize(1200, 800)
        
        # 1. Init Core Logic
        self.scanner = FileScanner()
        self.splitter = ColumnSplitter()
        self.thumbnail_provider = ThumbnailProvider()
        self.selection_helper = SelectionHelper()
        self.file_ops = FileOperations()
        self.clipboard = ClipboardManager()
        self.file_monitor = FileMonitor()
        
        # Connect logic
        self.scanner.filesFound.connect(self.splitter.appendFiles)
        self.splitter.columnsChanged.connect(self._on_columns_changed)
        
        # Auto-refresh: When files change in the watched directory, rescan
        self.file_monitor.directoryChanged.connect(self._on_directory_changed)

        # 2. UI Setup
        self.setup_ui()
        
        # 3. Start
        initial_path = start_path if start_path else QDir.homePath()
        self.navigate_to(initial_path)

    def setup_ui(self):
        # --- Status Bar ---
        self.status_bar = StatusBar()
        self.setStatusBar(self.status_bar)
        
        # Connect scanner to update status when files are loaded
        self.scanner.filesFound.connect(self.status_bar.updateItemCount)
        
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
        self.path_edit.returnPressed.connect(lambda: self.navigate_to(self.path_edit.text()))
        self.toolbar.addWidget(self.path_edit)
        
        # --- Standard Actions (Global Shortcuts) ---
        # Copy (Ctrl+C)
        self.act_copy = QAction("Copy", self)
        self.act_copy.setShortcut(QKeySequence.Copy)
        self.act_copy.triggered.connect(self._on_copy_triggered)
        self.addAction(self.act_copy)
        
        # Cut (Ctrl+X)
        self.act_cut = QAction("Cut", self)
        self.act_cut.setShortcut(QKeySequence.Cut)
        self.act_cut.triggered.connect(self._on_cut_triggered)
        self.addAction(self.act_cut)
        
        # Paste (Ctrl+V)
        self.act_paste = QAction("Paste", self)
        self.act_paste.setShortcut(QKeySequence.Paste)
        self.act_paste.triggered.connect(self._on_paste_triggered)
        self.addAction(self.act_paste)
        
        # Trash (Delete)
        self.act_trash = QAction("Move to Trash", self)
        self.act_trash.setShortcut(QKeySequence.Delete)
        self.act_trash.triggered.connect(self._on_trash_triggered)
        self.addAction(self.act_trash)

        # Spacer to push Zoom buttons to the right (Optional, but looks better)
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
        # Add Shortcut via QAction (since button doesn't own shortcuts globally like QAction)
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
        # Add Shortcut
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
        
        self.setCentralWidget(central_widget)
        
        # Sidebar (Native QTreeView with QFileSystemModel)
        # We use QFileSystemModel for standard "native" file browsing behavior in sidebar
        self.fs_model = QFileSystemModel()
        self.fs_model.setRootPath(QDir.rootPath())
        # Filter to show only dirs in the tree if desired, or all files. 
        # Standard file managers usually show dirs in tree.
        self.fs_model.setFilter(QDir.NoDotAndDotDot | QDir.AllDirs)
        
        self.sidebar_tree = QTreeView()
        self.sidebar_tree.setObjectName("SidebarTree")
        self.sidebar_tree.setModel(self.fs_model)
        self.sidebar_tree.setRootIndex(self.fs_model.index(QDir.homePath())) # Start at home
        self.sidebar_tree.clicked.connect(self._on_sidebar_clicked)
        self.sidebar_tree.setHeaderHidden(True)
        # Hide extra columns (Size, Type, Date) - keep only Name
        for i in range(1, 4):
            self.sidebar_tree.hideColumn(i)
            
        self.main_splitter.addWidget(self.sidebar_tree)
        self.main_splitter.setStretchFactor(0, 0) # Sidebar doesn't stretch much
        
        # --- Central Content (Optimized Embedding) ---
        # We use QQuickView + createWindowContainer for native GPU performance.
        # This avoids the "jitter" of QQuickWidget (which uses software copying).
        from PySide6.QtQuick import QQuickView
        
        self.qml_view = QQuickView()
        self.qml_view.setResizeMode(QQuickView.SizeRootObjectToView)
        
        # Transparent background to blend with theme (optional, can be removed if performance hints strict opacity)
        self.qml_view.setColor(Qt.transparent)
        
        # Expose Python objects to QML
        root_ctx = self.qml_view.engine().rootContext()
        root_ctx.setContextProperty("fileScanner", self.scanner)
        root_ctx.setContextProperty("columnSplitter", self.splitter)
        
        # Bridge
        from ui.models.app_bridge import AppBridge
        
        self.bridge = AppBridge(self)
        root_ctx.setContextProperty("appBridge", self.bridge)
        root_ctx.setContextProperty("selectionHelper", self.selection_helper)
        
        # Image Provider
        self.qml_view.engine().addImageProvider("thumbnail", self.thumbnail_provider)
        
        # Add import path for shared QML components
        qml_dir = Path(__file__).parent / "qml"
        self.qml_view.engine().addImportPath(str(qml_dir))
        
        # Load QML
        qml_path = Path(__file__).parent / "qml" / "views" / "MasonryView.qml"
        self.qml_view.setSource(QUrl.fromLocalFile(str(qml_path)))
        
        # Wrap as a Widget
        container = QWidget.createWindowContainer(self.qml_view, self)
        # Important: set Focus Policy so QML can receive keys if needed
        container.setFocusPolicy(Qt.TabFocus)
        container.setMinimumSize(100, 100)
        
        self.main_splitter.addWidget(container)
        self.main_splitter.setStretchFactor(1, 1) # Content takes rest of space
        
        # Keep reference for resize logic
        self.qml_container = container
        
        # Responsive Grid Logic
        self.target_column_width = 75 # Initial "Zoom Level" (px) - User Default
        self.bridge.targetCellWidth = self.target_column_width # Sync initial
        
        # Install Event Filter to track resize of the view container
        self.qml_container.installEventFilter(self)

        # Initial splitter sizes
        self.main_splitter.setSizes([250, 950])

    def navigate_to(self, path):
        path = str(path) # Ensure string
        if not os.path.exists(path):
            return
            
        print(f"Navigating to: {path}")
        self.current_path = path
        self.path_edit.setText(path)
        self.bridge.pathChanged.emit(path)
        
        # 1. Update Scanner (Content)
        self.status_bar.resetCounts()  # Reset before new scan
        self.splitter.setFiles([]) # Clear old
        self.scanner.scan_directory(path)
        
        # 2. Start watching this directory for changes
        self.file_monitor.watch(path)
        
        # 2. Update Sidebar Selection (Sync)
        index = self.fs_model.index(path)
        if index.isValid():
            self.sidebar_tree.setCurrentIndex(index)
            self.sidebar_tree.scrollTo(index)

    def go_up(self):
        parent = os.path.dirname(self.current_path)
        if parent and os.path.exists(parent):
            self.navigate_to(parent)

    def _on_sidebar_clicked(self, index):
        path = self.fs_model.filePath(index)
        self.navigate_to(path)

    @Slot()
    def _on_copy_triggered(self):
        root = self.qml_view.rootObject()
        if not root: return
        selection = root.property("currentSelection")
        
        # Convert QJSValue to Python list if needed
        if hasattr(selection, "toVariant"):
            selection = selection.toVariant()
            
        if selection:
            self.clipboard.copy(selection)
            
    @Slot()
    def _on_cut_triggered(self):
        root = self.qml_view.rootObject()
        if not root: return
        selection = root.property("currentSelection")
        
        if hasattr(selection, "toVariant"):
            selection = selection.toVariant()
            
        if selection:
            self.clipboard.cut(selection)
            
    @Slot()
    def _on_paste_triggered(self):
        # Delegate to bridge to ensure consistent behavior with context menu
        if self.bridge:
            self.bridge.paste()

    @Slot()
    def _on_trash_triggered(self):
        root = self.qml_view.rootObject()
        if not root: return
        selection = root.property("currentSelection")
        
        if hasattr(selection, "toVariant"):
            selection = selection.toVariant()
            
        if selection:
            self.file_ops.trashMultiple(selection)

    def _on_path_entered(self):
        pass
        
    def _on_columns_changed(self):
        pass
    
    @Slot()
    def _on_directory_changed(self):
        """
        Called by FileMonitor when the watched directory changes.
        Triggers a rescan of the current directory.
        """
        if hasattr(self, 'current_path') and self.current_path:
            print(f"Directory changed, rescanning: {self.current_path}")
            self.splitter.setFiles([])
            self.scanner.scan_directory(self.current_path)
        
    def eventFilter(self, obj, event):
        """
        Detect resize of the QML container to adjust column count dynamically.
        """
        if obj == self.qml_container and event.type() == event.Type.Resize:
            self._recalc_columns()
            
        return super().eventFilter(obj, event)
        
    def _recalc_columns(self):
        """
        Calculates optimal column count based on available width and target column width.
        Effect: Rigid Grid (Nemo-style). Columns are fixed width.
        Formula: (N * Width) + ((N-1) * Spacing) <= AvailableWidth
        """
        available_width = self.qml_container.width()
        if available_width <= 0: return
        
        spacing = 10 # Must match QML spacing
        
        # Solve for N:
        # N * W + N * S - S <= Available
        # N (W + S) <= Available + S
        # N <= (Available + S) / (W + S)
        
        numerator = available_width + spacing
        denominator = self.target_column_width + spacing
        
        if denominator == 0: return # Avoid div zero
        
        count = int(numerator / denominator)
        
        # Ensure at least 1 column, max 24 (increased from 12)
        count = max(1, min(24, count))
        
        self.splitter.setColumnCount(count)

    def change_zoom(self, delta):
        """
        Adjusts target column size (Zoom Level).
        delta: +1 (Zoom Out / Smaller items via smaller target), -1 (Zoom In / Larger items via larger target)
        """
        # Logic: 
        # Zoom In (-1) -> We want LARGER items -> INCREASE target_column_width
        # Zoom Out (+1) -> We want SMALLER items -> DECREASE target_column_width
        
        step = 25 # Smaller step for smoother control
        
        if delta < 0: # Zoom In
            self.target_column_width += step
        else: # Zoom Out
            self.target_column_width -= step
            
        # Clamp
        # Lowered min to 50 (extra zoom out) and default is 75
        self.target_column_width = max(50, min(800, self.target_column_width))
        
        # Update Bridge so QML updates width
        self.bridge.targetCellWidth = self.target_column_width
        
        # Trigger update of column count
        self._recalc_columns()
    
    def closeEvent(self, event):
        """Clean shutdown of worker threads."""
        self.file_ops.shutdown()
        super().closeEvent(event)

