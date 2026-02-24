"""ConflictResolver — Stateful helper for resolving file conflicts during batch ops."""

from ui.dialogs.conflicts import ConflictDialog, ConflictAction


class ConflictResolver:
    """
    Stateful helper for resolving file conflicts during a batch operation.
    """
    
    def __init__(self, parent_widget):
        self.parent = parent_widget
        self._file_ops = parent_widget.file_ops
        self._apply_all_action = None
    
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
        
        # Show Dialog
        dialog = ConflictDialog(self.parent, src, dest)
        dialog.exec()
        action = dialog.action
        
        if dialog.apply_to_all:
            self._apply_all_action = action
            
        return self._process_action(action, dest, naming_style)
    
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
