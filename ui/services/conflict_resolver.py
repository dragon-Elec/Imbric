"""ConflictResolver — Stateful helper for resolving file conflicts during batch ops."""

from PySide6.QtCore import QObject, QMetaObject, Qt, Q_ARG, Q_RETURN_ARG
from ui.dialogs.conflicts import ConflictDialog, ConflictAction


class ConflictResolver(QObject):
    """
    Stateful helper for resolving file conflicts during a batch operation.
    """
    
    def __init__(self, parent_widget):
        super().__init__(parent_widget)
        self.parent = parent_widget
        self._file_ops = parent_widget.file_ops
        self._apply_all_action = None
        self._last_result = None

    def __call__(self, src_path: str, dest_path: str) -> tuple[ConflictAction, str]:
        """Enable direct instance calling: resolver(src, dest)."""
        return self.resolve(src_path, dest_path)
    
    def resolve(self, src_path: str, dest_path: str) -> tuple[ConflictAction, str]:
        """
        Resolve a potential file conflict (Standard Mode: Copy/Paste).
        Naming Style: "file (Copy).txt"
        """
        return self._resolve_internal(src_path, dest_path, naming_style="copy")

    def resolve_rename(self, old_path: str, new_path: str) -> tuple[ConflictAction, str]:
        """
        Resolve a potential file conflict (Rename Mode).
        Naming Style: "file (2).txt"
        """
        return self._resolve_internal(old_path, new_path, naming_style="number")

    def _resolve_internal(self, src, dest, naming_style="copy") -> tuple[ConflictAction, str]:
        if not self._file_ops.check_exists(dest):
            return (ConflictAction.OVERWRITE, dest)
        
        # Check cache
        if self._apply_all_action is not None:
            return self._process_action(self._apply_all_action, dest, naming_style)
        
        # Determine if we are on the main thread
        import threading
        if threading.current_thread() is threading.main_thread():
            action, apply_to_all = self._show_dialog_main_thread(src, dest)
        else:
            # Safely invoke on main thread and wait for result
            # We use _resolve_internal_threaded to handle the result capture correctly in PySide6
            return self._resolve_internal_threaded(src, dest, naming_style)

        if apply_to_all:
            self._apply_all_action = action
            
        return self._process_action(action, dest, naming_style)

    def _resolve_internal_threaded(self, src, dest, naming_style):
        # Helper to handle the result from main thread
        self._last_result = None
        QMetaObject.invokeMethod(
            self, 
            "_show_dialog_and_store", 
            Qt.BlockingQueuedConnection,
            Q_ARG(str, src),
            Q_ARG(str, dest)
        )
        action, apply_to_all = self._last_result
        if apply_to_all:
            self._apply_all_action = action
        return self._process_action(action, dest, naming_style)

    def _show_dialog_and_store(self, src, dest):
        self._last_result = self._show_dialog_main_thread(src, dest)

    def _show_dialog_main_thread(self, src, dest):
        """Must be called on Main Thread."""
        dialog = ConflictDialog(self.parent, src, dest)
        dialog.exec()
        return (dialog.action, dialog.apply_to_all)
    
    def _process_action(self, action, dest_path, style):
        if action == ConflictAction.SKIP:
            return (ConflictAction.SKIP, "")
        elif action == ConflictAction.CANCEL:
            return (ConflictAction.CANCEL, "")
        elif action == ConflictAction.OVERWRITE:
            return (ConflictAction.OVERWRITE, dest_path)
        elif action == ConflictAction.RENAME:
            unique = self._file_ops.generate_unique_name(dest_path, style)
            return (ConflictAction.RENAME, unique)
        
        return (ConflictAction.CANCEL, "")
