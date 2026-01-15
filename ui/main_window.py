from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QToolBar, 
                               QTreeView, QSplitter, QFileSystemModel, QLineEdit)
from PySide6.QtCore import QUrl, Slot, Qt, QDir
from PySide6.QtGui import QAction, QIcon

from pathlib import Path
import os

# Import our core logic
from core.gio_bridge.scanner import FileScanner
from ui.models.column_splitter import ColumnSplitter
from core.image_providers.thumbnail_provider import ThumbnailProvider

class MainWindow(QMainWindow):
    def __init__(self, start_path=None):
        super().__init__()
        self.setWindowTitle("Imbric")
        self.resize(1200, 800)
        
        # 1. Init Core Logic
        self.scanner = FileScanner()
        self.splitter = ColumnSplitter()
        self.thumbnail_provider = ThumbnailProvider()
        
        # Connect logic
        self.scanner.filesFound.connect(self.splitter.appendFiles)
        self.splitter.columnsChanged.connect(self._on_columns_changed) # Debug hook if needed

        # 2. UI Setup
        self.setup_ui()
        
        # 3. Start
        initial_path = start_path if start_path else QDir.homePath()
        self.navigate_to(initial_path)

    def setup_ui(self):
        # --- Toolbar ---
        self.toolbar = QToolBar("Navigation")
        self.addToolBar(self.toolbar)
        
        # Up Button
        self.up_action = QAction(QIcon.fromTheme("go-up"), "Up", self)
        self.up_action.triggered.connect(self.go_up)
        self.toolbar.addAction(self.up_action)
        
        # Path Bar
        self.path_edit = QLineEdit()
        self.path_edit.returnPressed.connect(lambda: self.navigate_to(self.path_edit.text()))
        self.toolbar.addWidget(self.path_edit)

        # --- Main Layout (Splitter) ---
        self.main_splitter = QSplitter(Qt.Horizontal)
        self.setCentralWidget(self.main_splitter)
        
        # Sidebar (Native QTreeView with QFileSystemModel)
        # We use QFileSystemModel for standard "native" file browsing behavior in sidebar
        self.fs_model = QFileSystemModel()
        self.fs_model.setRootPath(QDir.rootPath())
        # Filter to show only dirs in the tree if desired, or all files. 
        # Standard file managers usually show dirs in tree.
        self.fs_model.setFilter(QDir.NoDotAndDotDot | QDir.AllDirs)
        
        self.sidebar_tree = QTreeView()
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
        from PySide6.QtCore import QObject, Signal
        class AppBridge(QObject):
            pathChanged = Signal(str)
            def __init__(self, main_window):
                super().__init__()
                self.mw = main_window

            @Slot(str)
            def openPath(self, path):
                self.mw.navigate_to(path)
        
        self.bridge = AppBridge(self)
        root_ctx.setContextProperty("appBridge", self.bridge)
        
        # Image Provider
        self.qml_view.engine().addImageProvider("thumbnail", self.thumbnail_provider)
        
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
        self.splitter.setFiles([]) # Clear old
        self.scanner.scan_directory(path)
        
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

    def _on_columns_changed(self):
        pass
