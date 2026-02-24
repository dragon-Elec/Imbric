"""
FileManager — High-Level File Operations & Clipboard

Consolidates:
- ClipboardManager (Cut/Copy/Paste state)
- AppBridge File Logic (Drag & Drop, Paste Conflict handling)
- Context Menu Action implementation
"""

from PySide6.QtCore import QObject, Signal, Slot, QMimeData, QUrl
from PySide6.QtGui import QClipboard, QGuiApplication
from ui.services.conflict_resolver import ConflictResolver
from ui.dialogs.conflicts import ConflictAction

from typing import List, Optional

class FileManager(QObject):
    clipboardChanged = Signal()
    cutPathsChanged = Signal()
    
    # MIME types
    GNOME_COPIED_FILES = "x-special/gnome-copied-files"
    URI_LIST = "text/uri-list"

    def __init__(self, main_window):
        super().__init__(main_window)
        self.mw = main_window
        self._clipboard = QGuiApplication.clipboard()
        self._clipboard.dataChanged.connect(self._on_clipboard_and_emit)
        
        # State
        self._is_cut = False

    # --- Context Helper ---
    
    def _current_tab(self):
        return self.mw.tab_manager.current_tab
        
    def _get_selection(self) -> List[str]:
        if tab := self._current_tab():
            return tab.selection
        return []

    # --- Actions (Slots) ---

    @Slot()
    def copy_selection(self):
        paths = self._get_selection()
        if paths:
            self._set_clipboard(paths, is_cut=False)

    @Slot()
    def cut_selection(self):
        paths = self._get_selection()
        if paths:
            self._set_clipboard(paths, is_cut=True)

    @Slot()
    def paste_to_current(self):
        """Pastes clipboard contents to current tab's folder."""
        tab = self._current_tab()
        if not tab: return
        
        target_dir = tab.current_path
        self._execute_paste(target_dir)

    @Slot()
    def trash_selection(self):
        paths = self._get_selection()
        if not paths: return
        
        tid = self.mw.transaction_manager.startTransaction(f"Trash {len(paths)} items")
        for p in paths:
            self.mw.file_ops.trash(p, transaction_id=tid)
            
        self.mw.transaction_manager.commitTransaction(tid)

    @Slot()
    def rename_selection(self):
        # Rename is typically single-item. 
        # If Action is single-item specific, we check selection len
        paths = self._get_selection()
        if len(paths) == 1:
            # Tell the Tab/Bridge to enter rename mode?
            # Or emit a signal? 
            # AppBridge currently has 'renameRequested' signal which QML listens to.
            # We can route this via AppBridge for now.
            if tab := self._current_tab():
                tab.bridge.renameRequested.emit(paths[0])

    @Slot()
    def create_new_folder(self):
        if tab := self._current_tab():
            # Delegate to existing logic in AppBridge or move it here?
            # Let's use the logic we moved from AppBridge (see below methods)
            self._create_folder_internal(tab.current_path)

    @Slot()
    def duplicate_selection(self):
        paths = self._get_selection()
        if not paths: return
        
        tab = self._current_tab()
        if not tab: return
        
        tid = self.mw.transaction_manager.startTransaction(f"Duplicate {len(paths)} items")
        
        for p in paths:
            if not self.mw.file_ops.check_exists(p): continue
            
            # Target is same folder, so we just use the original path as dest key
            # and let auto_rename handle the (Copy) suffix generation
            self.mw.file_ops.copy(p, p, transaction_id=tid, auto_rename=True)
            
        self.mw.transaction_manager.commitTransaction(tid)

    # --- Clipboard Logic (Ex-ClipboardManager) ---

    def _on_clipboard_and_emit(self):
        self.clipboardChanged.emit()
        self.cutPathsChanged.emit()

    def _set_clipboard(self, paths: list, is_cut: bool):
        self._is_cut = is_cut
        mime_data = QMimeData()
        
        urls = [QUrl.fromLocalFile(p) for p in paths]
        mime_data.setUrls(urls)
        
        action = "cut" if is_cut else "copy"
        uri_list = "\n".join(["file://" + p for p in paths])
        gnome_data = f"{action}\n{uri_list}"
        mime_data.setData(self.GNOME_COPIED_FILES, gnome_data.encode('utf-8'))
        mime_data.setData(self.URI_LIST, uri_list.encode('utf-8'))
        
        self._clipboard.setMimeData(mime_data)

    def get_clipboard_files(self) -> List[str]:
        mime = self._clipboard.mimeData()
        if not mime or not mime.hasUrls(): return []
        return [u.toLocalFile() for u in mime.urls() if u.isLocalFile()]

    def is_cut_mode(self) -> bool:
        mime = self._clipboard.mimeData()
        if not mime: return False
        if mime.hasFormat(self.GNOME_COPIED_FILES):
            data = bytes(mime.data(self.GNOME_COPIED_FILES)).decode('utf-8')
            return data.startswith("cut")
        return False
        
    def get_cut_paths(self) -> List[str]:
        if self.is_cut_mode():
            return self.get_clipboard_files()
        return []

    # --- Operation Logic (Ex-AppBridge) ---

    def _execute_paste(self, target_dir: str):
        files = self.get_clipboard_files()
        if not files: return
        
        is_cut = self.is_cut_mode()
        self._run_transfer(files, target_dir, is_move=is_cut)
        
        if is_cut:
            self._clipboard.clear()

    def _create_folder_internal(self, current_path):
        # Atomic creation via Core.
        # UI only guesses a name for better UX, but Core ensures uniqueness.
        base_name = "Untitled Folder"
        folder_path = self.mw.file_ops.build_dest_path(base_name, current_path)
        self.mw.file_ops.createFolder(folder_path, auto_rename=True)

    def _run_transfer(self, sources: List[str], dest_dir: str, is_move: bool):
        """Delegate transfer to Core's TransactionManager."""
        resolver = ConflictResolver(self.mw)
        mode = "move" if is_move else "copy"

        # Map ConflictAction enum → plain string for Core contract
        _ACTION_MAP = {
            ConflictAction.CANCEL: "cancel",
            ConflictAction.SKIP: "skip",
            ConflictAction.OVERWRITE: "overwrite",
            ConflictAction.RENAME: "rename",
        }

        def _resolver_callback(src, dest):
            action, final_dest = resolver.resolve(src, dest)
            return (_ACTION_MAP.get(action, "cancel"), final_dest)

        self.mw.transaction_manager.batchTransfer(
            sources, dest_dir, mode=mode, conflict_resolver=_resolver_callback
        )

    # --- Drag & Drop ---
    
    def handle_drop(self, urls: List[str], dest_dir: Optional[str] = None):
        """Called by AppBridge when QML drops files."""
        if not dest_dir:
            if tab := self._current_tab():
                dest_dir = tab.current_path
            else:
                return

        # Convert URLs to usable paths (Qt clipboard work — stays in UI)
        real_paths = []
        for u in urls:
            qurl = QUrl(u)
            if qurl.isLocalFile():
                real_paths.append(qurl.toLocalFile())
            elif self.mw.file_ops.check_exists(u):
                real_paths.append(u)

        if real_paths:
            # Delegate to Core — "auto" mode lets FileOperations decide move vs copy
            self.mw.transaction_manager.batchTransfer(
                real_paths, dest_dir, mode="auto"
            )
