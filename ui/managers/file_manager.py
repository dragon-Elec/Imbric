"""
FileManager — High-Level File Operations & Clipboard

Consolidates:
- ClipboardManager (Cut/Copy/Paste state)
- AppBridge File Logic (Drag & Drop, Paste Conflict handling)
- Context Menu Action implementation
"""

from PySide6.QtCore import QObject, Signal, Slot, QMimeData, QUrl
from PySide6.QtGui import QClipboard, QGuiApplication
from ui.dialogs.conflicts import ConflictResolver, ConflictAction
from typing import List, Optional
import os

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
        
        # Borrow resolver logic for name generation, or implement simple version
        # We'll do a simple loop here to avoid instantiating UI dialog classes for logic
        tid = self.mw.transaction_manager.startTransaction(f"Duplicate {len(paths)} items")
        
        for p in paths:
            if not os.path.exists(p): continue
            
            dirname = os.path.dirname(p)
            filename = os.path.basename(p)
            
            # Split ext
            if filename.endswith(".tar.gz"):
                base = filename[:-7]
                ext = ".tar.gz"
            else:
                base, ext = os.path.splitext(filename)
            
            # Find unique name: "Foo (Copy).txt", "Foo (Copy 2).txt"
            counter = 1
            while True:
                suffix = " (Copy)" if counter == 1 else f" (Copy {counter})"
                candidate_name = f"{base}{suffix}{ext}"
                candidate_path = os.path.join(dirname, candidate_name)
                
                if not os.path.exists(candidate_path):
                    # Found it
                    self.mw.file_ops.copy(p, candidate_path, transaction_id=tid)
                    break 
                    
                counter += 1

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
        base_name = "Untitled Folder"
        folder_path = os.path.join(current_path, base_name)
        counter = 2
        while os.path.exists(folder_path):
            folder_path = os.path.join(current_path, f"{base_name} ({counter})")
            counter += 1
            
        # We need to tell the bridge to select this later
        # Logic for "pending select" acts on Bridges.
        if tab := self._current_tab():
            tab.bridge.queueSelectionAfterRefresh([folder_path])
            # tab.bridge._pending_rename_path = folder_path # If we want auto-rename
            
        self.mw.file_ops.createFolder(folder_path)

    def _run_transfer(self, sources: List[str], dest_dir: str, is_move: bool):
        """
        Generic transfer logic (Paste / DragDrop) with Conflict Resolution.
        """
        resolver = ConflictResolver(self.mw)
        op_name = "Move" if is_move else "Copy"
        tid = self.mw.transaction_manager.startTransaction(f"{op_name} {len(sources)} items")
        
        # Check cross-device for moves
        try:
            dest_dev = os.stat(dest_dir).st_dev
        except OSError:
            dest_dev = None

        for src in sources:
            if not os.path.exists(src): continue
            
            dest = os.path.join(dest_dir, os.path.basename(src))
            if os.path.abspath(src) == os.path.abspath(dest): continue

            action, final_dest = resolver.resolve(src, dest)
            
            if action == ConflictAction.CANCEL: break
            if action == ConflictAction.SKIP: continue
            
            if is_move:
                # If move across devices, falls back to copy-del in fileOPS usually, 
                # but let's check optimization
                self.mw.file_ops.move(src, final_dest, transaction_id=tid)
            else:
                self.mw.file_ops.copy(src, final_dest, transaction_id=tid)

    # --- Drag & Drop ---
    
    def handle_drop(self, urls: List[str], dest_dir: Optional[str] = None):
        """Called by AppBridge when QML drops files."""
        if not dest_dir:
            if tab := self._current_tab():
                dest_dir = tab.current_path
            else:
                return

        # Convert URLs to local paths
        real_paths = []
        for u in urls:
            qurl = QUrl(u)
            if qurl.isLocalFile():
                real_paths.append(qurl.toLocalFile())
            elif os.path.exists(u):
                real_paths.append(u)

        if real_paths:
            # For this refactor, we default to Copy/Move logic via run_transfer.
            # Ideally we check device to decide Move vs Copy default.
            # Existing AppBridge logic did complex checks. 
            # We will default to 'move' if on same device, else 'copy', inside run_transfer?
            # actually run_transfer takes explicit is_move.
            # Let's do a simple check here:
            is_move = False
            try:
                # Simple heuristic: if same device, move.
                if dest_dir and os.path.exists(dest_dir):
                    dest_dev = os.stat(dest_dir).st_dev
                    src_dev = os.stat(real_paths[0]).st_dev
                    if dest_dev == src_dev:
                        is_move = True
            except:
                pass
                
            self._run_transfer(real_paths, dest_dir, is_move=is_move)
