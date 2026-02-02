from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QSplitter
from PySide6.QtCore import QDir, Slot, Qt, QTimer

from pathlib import Path
import os

# Core Logic
from core.file_operations import FileOperations
from core.file_monitor import FileMonitor
from core.transaction_manager import TransactionManager
from core.undo_manager import UndoManager

# UI Managers
from ui.managers.action_manager import ActionManager
from ui.managers.file_manager import FileManager
from ui.managers.view_manager import ViewManager
from ui.models.shortcuts import Shortcuts

# UI Components
from ui.components.navigation_bar import NavigationBar
from ui.components.sidebar import Sidebar
from ui.components.status_bar import StatusBar
from ui.components.tab_manager import TabManager
from ui.components.progress_overlay import ProgressOverlay

class MainWindow(QMainWindow):
    """
    Main application window.
    """
    def __init__(self, start_path=None):
        super().__init__()
        self.setWindowTitle("Imbric")
        self.resize(1200, 800)
        
        # 1. Init Core Logic
        self.file_ops = FileOperations()
        self.file_monitor = FileMonitor()
        self.transaction_manager = TransactionManager()
        self.undo_manager = UndoManager(self.transaction_manager)
        
        # Wire Core Logic
        self.transaction_manager.setFileOperations(self.file_ops)
        self.file_ops.setTransactionManager(self.transaction_manager)
        self.file_ops.setUndoManager(self.undo_manager)
        self.file_monitor.directoryChanged.connect(self._on_directory_changed)
        
        # 2. Setup UI Components
        self._setup_ui()
        
        # 3. Init Managers (Now that UI exists)
        self.shortcuts = Shortcuts(self)
        self.view_manager = ViewManager(self)
        self.file_manager = FileManager(self)
        self.action_manager = ActionManager(self)
        
        # Setup Actions
        self.action_manager.setup_actions(
            window=self,
            shortcuts=self.shortcuts,
            file_manager=self.file_manager,
            view_manager=self.view_manager,
            nav_bar=self.nav_bar,
            tab_manager=self.tab_manager,
            undo_manager=self.undo_manager
        )
        
        # Connect Components to Managers
        self.nav_bar.zoomChanged.connect(self.change_zoom)
        
        # 4. Start
        initial_path = start_path if start_path else QDir.homePath()
        self.tab_manager.add_tab(initial_path)

    def _setup_ui(self):
        # Navigation Bar (Top)
        self.nav_bar = NavigationBar()
        self.addToolBar(self.nav_bar)
        
        # Status Bar (Bottom)
        self.status_bar = StatusBar()
        self.setStatusBar(self.status_bar)
        
        # Central Layout
        central_widget = QWidget()
        central_layout = QVBoxLayout(central_widget)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        
        # Splitter (Sidebar | Tabs)
        self.splitter_widget = QSplitter(Qt.Horizontal)
        
        self.sidebar = Sidebar()
        self.tab_manager = TabManager(self)
        
        self.splitter_widget.addWidget(self.sidebar)
        self.splitter_widget.addWidget(self.tab_manager)
        self.splitter_widget.setStretchFactor(1, 1)
        self.splitter_widget.setSizes([250, 950])
        
        central_layout.addWidget(self.splitter_widget, 1)
        
        # Progress Overlay
        self.progress_overlay = ProgressOverlay()
        
        # PRIMARY: Connect to TransactionManager for batch operations
        self.transaction_manager.transactionStarted.connect(self.progress_overlay.onBatchStarted)
        self.transaction_manager.transactionProgress.connect(self.progress_overlay.onBatchProgress)
        self.transaction_manager.transactionUpdate.connect(self.progress_overlay.onBatchUpdate)
        self.transaction_manager.transactionFinished.connect(self.progress_overlay.onBatchFinished)
        
        # FALLBACK connections removed: All operations now go through TransactionManager.
        # The legacy operationCompleted signal has been deprecated.
        
        # Cancel support
        self.progress_overlay.cancelRequested.connect(self._on_cancel_requested)
        central_layout.addWidget(self.progress_overlay)
        
        # Granular job completion for Smart UI (select after rename, enter edit mode, etc.)
        self.transaction_manager.jobCompleted.connect(self._on_op_completed)
        
        self.setCentralWidget(central_widget)
        
        # Connect Components
        self.nav_bar.navigateRequested.connect(self.navigate_to)
        self.sidebar.navigationRequested.connect(self.navigate_to)
        self.tab_manager.currentPathChanged.connect(self._on_tab_path_changed)

        # [DIAGNOSTICS] F12 to trigger Memory Dump
        from PySide6.QtGui import QShortcut, QKeySequence
        self.diag_shortcut = QShortcut(QKeySequence("F12"), self)
        self.diag_shortcut.activated.connect(self._run_diagnostics)

    def _run_diagnostics(self):
        """Trigger internal memory profiling."""
        from core.diagnostics import MemoryProfiler
        MemoryProfiler.print_report()

    # --- NAVIGATION ---

    def navigate_to(self, path):
        path = str(path)
        if not os.path.exists(path): return
        
        self.tab_manager.navigate_to(path)
        self.file_monitor.watch(path)
        self.sidebar.sync_to_path(path)

    def go_up(self):
        tab = self.tab_manager.current_tab
        if tab:
            parent = os.path.dirname(tab.current_path)
            if parent and os.path.exists(parent):
                self.navigate_to(parent)

    def _on_tab_path_changed(self, path):
        """Sync UI components when tab path changes."""
        self.nav_bar.set_path(path)
        self.status_bar.resetCounts()
        
        # Re-connect status bar
        tab = self.tab_manager.current_tab
        if tab:
            # Disconnect previous scanner if it exists
            if hasattr(self, '_active_scanner') and self._active_scanner:
                try:
                    self._active_scanner.filesFound.disconnect(self.status_bar.updateItemCount)
                except Exception:
                    pass
            
            # Connect new scanner and store reference
            self._active_scanner = tab.scanner
            self._active_scanner.filesFound.connect(self.status_bar.updateItemCount)
            self._active_scanner.fileAttributeUpdated.connect(self.status_bar.updateAttribute)

    def _on_directory_changed(self):
        tab = self.tab_manager.current_tab
        if tab: start_path = tab.current_path; tab.navigate_to(start_path)

    # --- ACTIONS ---

    def change_zoom(self, delta):
        # Legacy hook, forward to ViewManager
        if delta < 0:
            self.view_manager.zoom_in()
        else:
            self.view_manager.zoom_out()

    @Slot(str, str, str)
    def _on_op_completed(self, op_type, path, result_data):
        tab = self.tab_manager.current_tab
        if not tab or not tab.bridge: return
            
        if op_type == "rename":
            tab.bridge.selectPath(result_data)
        elif op_type == "createFolder":
            if tab.bridge._pending_rename_path == path:
                tab.bridge._pending_rename_path = None
                QTimer.singleShot(100, lambda: tab.bridge.renameRequested.emit(path))
    
    @Slot(str)
    def _on_cancel_requested(self, identifier: str):
        """
        Handle cancel request from ProgressOverlay.
        identifier can be a transaction_id or a job_id.
        """
        # Try to cancel all jobs in a transaction
        tx = self.transaction_manager._active_transactions.get(identifier)
        if tx:
            for op in tx.ops:
                if op.job_id:
                    self.file_ops.cancel(op.job_id)
        else:
            # Fallback: treat as single job_id
            self.file_ops.cancel(identifier)
    
    # --- PROPERTIES (For Bridge Access to Managers) ---
    
    @property
    def clipboard(self):
        # Legacy accessor for AppBridge to use FileManager as clipboard logic source
        return self.file_manager 

    @property
    def current_path(self):
        return self.tab_manager.current_tab.current_path if self.tab_manager.current_tab else QDir.homePath()

    @property
    def bridge(self):
        return self.tab_manager.current_tab.bridge if self.tab_manager.current_tab else None
    
    @property
    def qml_view(self):
        return self.tab_manager.current_tab.qml_view if self.tab_manager.current_tab else None

    def closeEvent(self, event):
        self.file_ops.shutdown()
        super().closeEvent(event)
