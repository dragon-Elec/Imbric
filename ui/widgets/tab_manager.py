"""
TabManager — Multi-Tab Support for Imbric

Provides a QTabWidget with per-tab browsing state (path, selection, scanner).
Each tab has its own QML MasonryView and ColumnSplitter.

Design:
- TabManager wraps QTabWidget
- Each tab = BrowserTab (QWidget container with QQuickView)
- MainWindow owns one TabManager instead of a single QQuickView
- Tabs can be opened via Ctrl+T, middle-click on folder, or "Open in New Tab"
"""

from PySide6.QtWidgets import QTabWidget, QWidget, QVBoxLayout, QTabBar, QPushButton, QHBoxLayout
from PySide6.QtCore import Qt, QUrl, Signal, Slot, QTimer
from PySide6.QtQuick import QQuickView
from pathlib import Path
import os


class BrowserTab(QWidget):
    """
    A single browser tab containing its own QML view and state.
    """
    
    # Signal when this tab's path changes (for path bar sync)
    pathChanged = Signal(str)
    
    def __init__(self, main_window, initial_path: str = None):
        super().__init__()
        self.mw = main_window
        self.current_path = initial_path or str(Path.home())
        
        # Per-tab components
        from core.gio_bridge.scanner import FileScanner
        from ui.models.column_splitter import ColumnSplitter
        from core.selection_helper import SelectionHelper
        from ui.models.app_bridge import AppBridge
        
        self.scanner = FileScanner()
        self.splitter = ColumnSplitter()
        self.selection_helper = SelectionHelper()
        
        # Connect scanner to splitter
        self.scanner.filesFound.connect(self.splitter.appendFiles)
        self.scanner.scanFinished.connect(self._on_scan_finished)
        
        # Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # QML View
        self.qml_view = QQuickView()
        self.qml_view.setResizeMode(QQuickView.SizeRootObjectToView)
        self.qml_view.setColor(Qt.transparent)
        
        # Expose objects to QML
        ctx = self.qml_view.engine().rootContext()
        ctx.setContextProperty("fileScanner", self.scanner)
        ctx.setContextProperty("columnSplitter", self.splitter)
        ctx.setContextProperty("selectionHelper", self.selection_helper)
        
        # Bridge (tab-specific)
        self.bridge = AppBridge(main_window)
        self.bridge._tab = self  # Reference back to this tab for path operations
        ctx.setContextProperty("appBridge", self.bridge)
        
        # Image Provider (per-tab instance — Qt takes ownership and deletes on engine destroy)
        # We create a new instance for each tab to avoid the shared provider being deleted
        from core.image_providers.thumbnail_provider import ThumbnailProvider
        self._thumbnail_provider = ThumbnailProvider()
        self.qml_view.engine().addImageProvider("thumbnail", self._thumbnail_provider)
        
        # QML import path
        qml_dir = Path(__file__).parent.parent / "qml"
        self.qml_view.engine().addImportPath(str(qml_dir))
        
        # Load QML
        qml_path = Path(__file__).parent.parent / "qml" / "views" / "MasonryView.qml"
        self.qml_view.setSource(QUrl.fromLocalFile(str(qml_path)))
        
        # Wrap as widget
        container = QWidget.createWindowContainer(self.qml_view, self)
        container.setFocusPolicy(Qt.TabFocus)
        container.setMinimumSize(100, 100)
        layout.addWidget(container)
        
        self.qml_container = container
        
        # Initial column setup
        self._target_column_width = 75
        self.bridge.targetCellWidth = self._target_column_width
        
        # Install resize filter
        container.installEventFilter(self)
        
        # Defer initial column calculation (widget needs to be sized first)
        self._needs_initial_recalc = True
    
    def showEvent(self, event):
        """Called when tab becomes visible. Trigger initial column calculation."""
        super().showEvent(event)
        if self._needs_initial_recalc:
            self._needs_initial_recalc = False
            # Use timer to let the layout settle
            QTimer.singleShot(50, self._recalc_columns)
    
    def navigate_to(self, path: str):
        """Navigate this tab to a new path."""
        if not os.path.isdir(path):
            return
        
        self.current_path = path
        self.splitter.setFiles([])  # Clear
        self.scanner.scan_directory(path)
        self.pathChanged.emit(path)
    
    def _on_scan_finished(self):
        """Called when directory scan completes."""
        # Check if there are pending paths to select (e.g., from paste)
        pending = self.bridge.selectPendingPaths()
        if pending:
            # Access QML root and call selectPaths function
            root = self.qml_view.rootObject()
            if root:
                # Use QMetaObject to invoke the QML function
                from PySide6.QtCore import QMetaObject, Q_ARG
                QMetaObject.invokeMethod(root, "selectPaths", Q_ARG("QVariant", pending))
    
    def eventFilter(self, obj, event):
        """Track resize for column recalculation."""
        from PySide6.QtCore import QEvent
        if obj == self.qml_container and event.type() == QEvent.Resize:
            self._recalc_columns()
        return super().eventFilter(obj, event)
    
    def _recalc_columns(self):
        """Calculate optimal column count based on width."""
        available_width = self.qml_container.width()
        spacing = 10
        target = self._target_column_width
        
        # Formula: (N * W) + ((N-1) * S) <= Available
        n = 1
        while True:
            needed = (n * target) + ((n - 1) * spacing)
            if needed > available_width:
                break
            n += 1
        
        optimal = max(1, n - 1)
        if self.splitter:
            self.splitter.setColumnCount(optimal)
    
    def change_zoom(self, delta: int):
        """Adjust zoom level."""
        step = 25
        new_width = self._target_column_width + (delta * step)
        new_width = max(50, min(500, new_width))
        
        self._target_column_width = new_width
        self.bridge.targetCellWidth = new_width
        self._recalc_columns()
    
    @property
    def selection(self):
        """Get current selection from QML."""
        root = self.qml_view.rootObject()
        if root:
            sel = root.property("currentSelection")
            if hasattr(sel, "toVariant"):
                return sel.toVariant()
            return sel
        return []


class TabManager(QTabWidget):
    """
    Manages multiple browser tabs.
    """
    
    # Signal when active tab's path changes
    currentPathChanged = Signal(str)
    
    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        self._tabs = []
        
        # Tab bar styling
        self.setTabsClosable(True)
        self.setMovable(True)
        self.setDocumentMode(True)  # Cleaner look
        
        # Signals
        self.tabCloseRequested.connect(self._close_tab)
        self.currentChanged.connect(self._on_tab_changed)
        
        # Add "New Tab" button
        self._add_new_tab_button()
    
    def _add_new_tab_button(self):
        """Add a + button to create new tabs."""
        btn = QPushButton("+")
        btn.setFixedSize(24, 24)
        btn.setFlat(True)
        btn.setToolTip("New Tab (Ctrl+T)")
        btn.clicked.connect(self.add_tab)
        self.setCornerWidget(btn, Qt.TopRightCorner)
    
    @Slot()
    def add_tab(self, path: str = None) -> BrowserTab:
        """Create a new tab, optionally at a specific path."""
        tab = BrowserTab(self.mw, path)
        tab.pathChanged.connect(self._on_tab_path_changed)
        
        # Tab title from path
        title = os.path.basename(tab.current_path) or "Home"
        
        index = self.addTab(tab, title)
        self._tabs.append(tab)
        self.setCurrentIndex(index)
        
        # Navigate to path
        tab.navigate_to(tab.current_path)
        
        return tab
    
    def _close_tab(self, index: int):
        """Close a tab safely."""
        if self.count() <= 1:
            return  # Keep at least one tab
        
        tab = self.widget(index)
        if tab in self._tabs:
            self._tabs.remove(tab)
        
        # Remove from tab widget first
        self.removeTab(index)
        
        # Clean up QML view before deletion to prevent segfault
        if hasattr(tab, 'qml_view') and tab.qml_view:
            tab.qml_view.setSource(QUrl())  # Unload QML
            tab.qml_view.engine().clearComponentCache()
        
        # Schedule for deletion (safer than immediate delete)
        tab.deleteLater()
    
    def _on_tab_changed(self, index: int):
        """Called when active tab changes."""
        tab = self.widget(index)
        if tab:
            self.currentPathChanged.emit(tab.current_path)
    
    def _on_tab_path_changed(self, path: str):
        """Update tab title when path changes."""
        tab = self.sender()
        if tab:
            index = self.indexOf(tab)
            if index >= 0:
                title = os.path.basename(path) or "Home"
                self.setTabText(index, title)
        
        # If it's the current tab, emit signal
        if tab == self.currentWidget():
            self.currentPathChanged.emit(path)
    
    @property
    def current_tab(self) -> BrowserTab:
        """Get the currently active tab."""
        return self.currentWidget()
    
    def navigate_to(self, path: str):
        """Navigate the current tab to a path."""
        tab = self.current_tab
        if tab:
            tab.navigate_to(path)
