from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QMessageBox
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
from ui.components.status_bar import StatusBar
from ui.components.progress_overlay import ProgressOverlay

class MainWindow(QMainWindow):
    """
    Main application window using Unified QML Shell.
    """
    def __init__(self, start_path=None):
        super().__init__()
        self.setWindowTitle("Imbric")
        self.resize(1200, 800)
        
        # Experimental CSD Flag
        self.use_csd = os.environ.get("IMBRIC_CSD") == "1"
        
        if self.use_csd:
            self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        else:
            self.setWindowFlags(Qt.Window)
        
        # 1. Init Core Logic
        self.file_ops = FileOperations()
        self.file_monitor = FileMonitor()
        self.transaction_manager = TransactionManager()
        self.undo_manager = UndoManager(self.transaction_manager)
        
        # Wire Core Logic
        self.transaction_manager.setFileOperations(self.file_ops)
        self.file_ops.setTransactionManager(self.transaction_manager)
        self.file_ops.setUndoManager(self.undo_manager)
        # [FIX] Disconnected global reload on directory change to allow surgical updates
        
        # 2. Setup Unified Shell Manager
        # This replaces both Sidebar and TabManager
        from ui.managers.shell_manager import ShellManager
        self.shell_manager = ShellManager(self)
        
        # 3. Setup UI Layout
        # Import CustomHeader only if needed (or generally)
        if self.use_csd:
            from ui.components.custom_header import CustomHeader
            
        self._setup_ui()
        
        # 4. Init Managers (Now that UI exists)
        self.shortcuts = Shortcuts(self)
        self.view_manager = ViewManager(self)
        self.file_manager = FileManager(self)
        self.action_manager = ActionManager(self)
        
        # Setup Actions
        # Note: action_manager expects 'tab_manager', we pass 'shell_manager' as it mimics the API
        self.action_manager.setup_actions(
            window=self,
            shortcuts=self.shortcuts,
            file_manager=self.file_manager,
            view_manager=self.view_manager,
            nav_bar=self.nav_bar,
            tab_manager=self.shell_manager,
            undo_manager=self.undo_manager
        )
        
        # Connect Components to Managers
        self.nav_bar.zoomChanged.connect(self.change_zoom)
        
        # 5. Start
        initial_path = start_path if start_path else QDir.homePath()
        self.shell_manager.add_tab(initial_path)

    def _setup_ui(self):
        # Navigation Bar (Top)
        self.nav_bar = NavigationBar()
        # self.addToolBar(self.nav_bar) # REMOVED: We are now CSD
        
        # Status Bar (Bottom)
        self.status_bar = StatusBar()
        self.setStatusBar(self.status_bar)
        
        # Central Layout
        central_widget = QWidget()
        central_layout = QVBoxLayout(central_widget)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        
        if self.use_csd:
            # CSD Header (Top)
            from ui.components.custom_header import CustomHeader
            self.header = CustomHeader(self.nav_bar, self)
            central_layout.addWidget(self.header)
        else:
            # Standard Toolbar
            # NavigationBar is a QWidget not QToolBar now, so we must wrap it
            from PySide6.QtWidgets import QToolBar
            toolbar = QToolBar(self)
            toolbar.setMovable(False)
            toolbar.addWidget(self.nav_bar)
            self.addToolBar(toolbar)

        # UNIFIED SHELL (Replaces Splitter/Sidebar/Tabs)
        central_layout.addWidget(self.shell_manager.container, 1)
        
        # Progress Overlay
        self.progress_overlay = ProgressOverlay()
        
        # PRIMARY: Connect to TransactionManager for batch operations
        self.transaction_manager.transactionStarted.connect(self.progress_overlay.onBatchStarted)
        self.transaction_manager.transactionProgress.connect(self.progress_overlay.onBatchProgress)
        self.transaction_manager.transactionUpdate.connect(self.progress_overlay.onBatchUpdate)
        self.transaction_manager.transactionFinished.connect(self.progress_overlay.onBatchFinished)
        
        # Cancel support
        self.progress_overlay.cancelRequested.connect(self._on_cancel_requested)
        central_layout.addWidget(self.progress_overlay)
        
        # Granular job completion for Smart UI (select after rename, enter edit mode, etc.)
        self.transaction_manager.jobCompleted.connect(self._on_op_completed)
        self.transaction_manager.operationFailed.connect(self._show_error_dialog)
        
        self.setCentralWidget(central_widget)
        
        # Connect Components
        self.nav_bar.navigateRequested.connect(self.navigate_to)
        
        # Connect Shell Signals
        self.shell_manager.currentPathChanged.connect(self._on_tab_path_changed)

        # [DIAGNOSTICS] F12 to trigger Memory Dump
        from PySide6.QtGui import QShortcut, QKeySequence
        self.diag_shortcut = QShortcut(QKeySequence("F12"), self)
        self.diag_shortcut.activated.connect(self._run_diagnostics)

    def _run_diagnostics(self):
        """Trigger internal memory profiling."""
        from scripts.diagnostics import MemoryProfiler
        MemoryProfiler.print_report()

    # --- NAVIGATION ---

    def navigate_to(self, path):
        path = str(path)
        if not os.path.exists(path): return
        
        self.shell_manager.navigate_to(path)
        self.file_monitor.watch(path)
        
        # Syncing sidebar to path is now handled internally by Shell or via signals if needed
        # self.sidebar.sync_to_path(path) 

    def go_up(self):
        tab = self.shell_manager.current_tab
        if tab:
            parent = os.path.dirname(tab.current_path)
            if parent and os.path.exists(parent):
                self.navigate_to(parent)

    def _on_tab_path_changed(self, path):
        """Sync UI components when tab path changes."""
        print(f"[DEBUG-SURGICAL] MainWindow._on_tab_path_changed: {path}")
        self.nav_bar.set_path(path)
        self.status_bar.resetCounts()
        
        # Ensure the FileMonitor is actually watching the current path
        self.file_monitor.watch(path)
        
        # Re-connect status bar
        tab = self.shell_manager.current_tab
        if tab:
            # Disconnect previous scanner if it exists
            if hasattr(self, '_active_scanner') and self._active_scanner:
                try:
                    self._active_scanner.filesFound.disconnect(self.status_bar.updateItemCount)
                    # Also disconnect attribute updates
                    self._active_scanner.fileAttributeUpdated.disconnect(self.status_bar.updateAttribute)
                except Exception:
                    pass
            
            # Connect new scanner and store reference
            self._active_scanner = tab.scanner
            self._active_scanner.filesFound.connect(self.status_bar.updateItemCount)
            self._active_scanner.fileAttributeUpdated.connect(self.status_bar.updateAttribute)

    def _on_directory_changed(self):
        # [FIX] Intentional no-op. Full reloads disabled in favor of surgical row_builder updates.
        pass

    # --- ACTIONS ---

    def change_zoom(self, delta):
        # Legacy hook, forward to ViewManager
        if delta < 0:
            self.view_manager.zoom_in()
        else:
            self.view_manager.zoom_out()

    @property
    def tab_manager(self):
        """Backward compatibility alias for Managers that expect 'tab_manager'."""
        return self.shell_manager

    @Slot(str, str, str)
    def _on_op_completed(self, op_type, path, result_data):
        tab = self.shell_manager.current_tab
        if not tab or not tab.bridge: return
            
        if op_type == "rename":
            tab.bridge.selectPath(result_data)
        elif op_type == "createFolder":
            if tab.bridge._pending_rename_path == path:
                tab.bridge._pending_rename_path = None
                QTimer.singleShot(100, lambda: tab.bridge.renameRequested.emit(path))
    
    @Slot(str, str, str)
    def _show_error_dialog(self, op_type: str, path: str, message: str):
        """Displays a modal dialog for generic file operation errors."""
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Critical)
        dialog.setWindowTitle(f"{op_type.capitalize()} Error")
        dialog.setText(f"<b>Failed to {op_type} file:</b>")
        dialog.setInformativeText(f"{message}\n\nPath: {path}")
        dialog.setStandardButtons(QMessageBox.Ok)
        dialog.exec()

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
        return self.shell_manager.current_tab.current_path if self.shell_manager.current_tab else QDir.homePath()

    @property
    def bridge(self):
        return self.shell_manager.current_tab.bridge if self.shell_manager.current_tab else None
    
    @property
    def qml_view(self):
        # New Architecture: ShellManager owns the single QML view
        return self.shell_manager.qml_view

    def closeEvent(self, event):
        self.file_ops.shutdown()
        super().closeEvent(event)
