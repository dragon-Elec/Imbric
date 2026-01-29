"""
[DONE] FileScanner — Async Directory Enumeration

Scans a directory using Gio.enumerate_children_async for true non-blocking I/O.
Emits file metadata in batches for efficient list model updates.

Features:
- Batched async enumeration (50 files per batch)
- Cancellation support via Gio.Cancellable
- Robust error handling (per-batch and per-file)
- Rich metadata: size, dates, MIME, symlinks, permissions
- Hidden files toggle
"""

import gi
gi.require_version('Gio', '2.0')
from gi.repository import Gio, GLib

from PySide6.QtCore import QObject, Signal, Slot
from core.gio_bridge.count_worker import ItemCountWorker


class FileScanner(QObject):
    """
    Async directory scanner using Gio.
    
    Signals:
        filesFound(list[dict]) - Emitted with each batch of files
        scanFinished() - Emitted when scan completes successfully
        scanError(str) - Emitted on fatal error (e.g., directory not found)
    """
    
    filesFound = Signal(list)
    scanFinished = Signal()
    scanError = Signal(str)
    fileAttributeUpdated = Signal(str, str, object)  # path, attribute_name, value

    # Valid visual extensions (thumbnails needed)
    VISUAL_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg', '.tiff', '.tif', '.ico', '.mp4', '.mkv', '.webm', '.mov', '.avi'}

    # Gio attributes to request
    # Active: Used in UI immediately
    # Passive: Fetched but not yet used (for future features)
    QUERY_ATTRIBUTES = ",".join([
        # Core (always needed)
        "standard::name",
        "standard::type",
        "standard::is-hidden",
        "standard::size",
        
        # MIME type (Active: for icons and "Open With")
        "standard::content-type",
        
        # Symlinks (Active: for UI indicator)
        "standard::is-symlink",
        "standard::symlink-target",
        
        # Timestamps (Active: for sorting, display)
        "time::modified",
        "time::access",
        
        # Permissions (Passive: for future properties dialog)
        "unix::mode",
        "unix::uid",
        "unix::gid",
    ])

    # Batch size increased to 200 to reduce Masonry layout thrashing (O(N^2) sorts)
    BATCH_SIZE = 200

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cancellable: Gio.Cancellable | None = None
        self._current_path: str | None = None
        self._show_hidden: bool = False
        
        # Background item counter
        self._count_worker = ItemCountWorker(self)
        self._count_worker.countReady.connect(self._on_count_ready)

    @property
    def current_path(self) -> str | None:
        """The path currently being scanned (or last scanned)."""
        return self._current_path

    @Slot(bool)
    def setShowHidden(self, show: bool) -> None:
        """Set whether to include hidden files in scan results."""
        self._show_hidden = show

    @Slot(result=bool)
    def showHidden(self) -> bool:
        """Get current hidden files visibility setting."""
        return self._show_hidden

    @Slot(str)
    def scan_directory(self, path: str) -> None:
        """
        Start an async scan of the given directory.
        
        Any previous scan is cancelled before starting. Results are emitted
        via the `filesFound` signal in batches.
        
        Args:
            path: Absolute path to the directory to scan.
        """
        self.cancel()
        
        self._current_path = path
        self._cancellable = Gio.Cancellable()
        
        gfile = Gio.File.new_for_path(path)
        
        gfile.enumerate_children_async(
            self.QUERY_ATTRIBUTES,
            Gio.FileQueryInfoFlags.NONE,
            GLib.PRIORITY_DEFAULT,
            self._cancellable,
            self._on_enumerate_ready,
            None
        )

    @Slot()
    def cancel(self) -> None:
        """Cancel any in-progress scan."""
        if self._cancellable is not None:
            self._cancellable.cancel()
            self._cancellable = None
        
        # Clear pending count requests
        self._count_worker.clear()

    # -------------------------------------------------------------------------
    # INTERNAL CALLBACKS
    # -------------------------------------------------------------------------

    def _on_enumerate_ready(self, source: Gio.File, result: Gio.AsyncResult, user_data) -> None:
        """Callback when enumerate_children_async completes."""
        try:
            enumerator = source.enumerate_children_finish(result)
        except GLib.Error as e:
            error_msg = f"Cannot open directory: {e.message}"
            print(f"[FileScanner] Error: {error_msg}")
            self.scanError.emit(error_msg)
            return
        
        parent_path = source.get_path()
        if parent_path is None:
            self.scanError.emit("Invalid directory path")
            return
        
        self._fetch_next_batch(enumerator, parent_path)

    def _fetch_next_batch(self, enumerator: Gio.FileEnumerator, parent_path: str) -> None:
        """Request the next batch of files from the enumerator."""
        enumerator.next_files_async(
            self.BATCH_SIZE,
            GLib.PRIORITY_DEFAULT,
            self._cancellable,
            self._on_batch_ready,
            (enumerator, parent_path)
        )

    def _on_batch_ready(
        self,
        enumerator: Gio.FileEnumerator,
        result: Gio.AsyncResult,
        context: tuple
    ) -> None:
        """Callback when a batch of files is ready."""
        stored_enumerator, parent_path = context
        
        try:
            file_infos = enumerator.next_files_finish(result)
        except GLib.Error as e:
            error_msg = f"Error reading directory contents: {e.message}"
            print(f"[FileScanner] {error_msg}")
            self.scanError.emit(error_msg)
            self._close_enumerator(stored_enumerator)
            return
        
        if not file_infos:
            self.scanFinished.emit()
            self._close_enumerator(stored_enumerator)
            return
        
        batch = self._process_batch(file_infos, parent_path)
        
        if batch:
            self.filesFound.emit(batch)
        
        self._fetch_next_batch(stored_enumerator, parent_path)

    def _process_batch(self, file_infos: list[Gio.FileInfo], parent_path: str) -> list[dict]:
        """
        Convert Gio.FileInfo objects to dictionaries with rich metadata.
        """
        batch = []
        
        # Normalize parent path
        if parent_path.endswith('/') and parent_path != '/':
            parent_path = parent_path.rstrip('/')
        
        for info in file_infos:
            # Hidden filter
            if not self._show_hidden and info.get_is_hidden():
                continue
            
            name = info.get_name()
            if name is None:
                continue
            
            # Extension & Visual Check
            lower_name = name.lower()
            is_visual = False
            for ext in self.VISUAL_EXTENSIONS:
                if lower_name.endswith(ext):
                    is_visual = True
                    break
            
            # Full path
            if parent_path == '/':
                full_path = '/' + name
            else:
                full_path = parent_path + '/' + name
            
            # Type detection
            file_type = info.get_file_type()
            is_dir = file_type == Gio.FileType.DIRECTORY
            is_symlink = info.get_is_symlink()
            
            # Symlink target (empty string if not a symlink)
            symlink_target = ""
            if is_symlink:
                target = info.get_symlink_target()
                symlink_target = target if target else ""
            
            # Size
            size = info.get_size()
            
            # MIME type (e.g., "image/jpeg", "inode/directory")
            mime_type = info.get_content_type() or ""
            
            # Timestamps
            date_modified = self._get_timestamp(info.get_modification_date_time())
            date_accessed = self._get_timestamp(info.get_access_date_time())
            
            # Permissions (Passive - stored for future use)
            # unix::mode returns octal like 0o755
            mode = info.get_attribute_uint32("unix::mode") if info.has_attribute("unix::mode") else 0
            uid = info.get_attribute_uint32("unix::uid") if info.has_attribute("unix::uid") else 0
            gid = info.get_attribute_uint32("unix::gid") if info.has_attribute("unix::gid") else 0
            
            # File count for directories
            # Start at -1 (loading), will be updated async
            child_count = -1 if (is_dir and not is_symlink) else 0
            
            # Queue directory for async counting
            if is_dir and not is_symlink:
                self._count_worker.enqueue(full_path)

            
            # Wrapper for QML caching
            if is_visual:
                # Images/Videos get unique thumbnails
                icon_source = f"image://thumbnail/{full_path}"
            else:
                # Non-visual files get a SHARED icon based on MIME type
                # QML will now see the SAME URL for all .txt files and reuse the RAM cache
                icon_source = f"image://thumbnail/mime/{mime_type}"

            batch.append({
                # Core
                "name": name,
                "path": full_path,
                "iconSource": icon_source,
                "isDir": is_dir,
                "size": size,
                
                # MIME (Active)
                "mimeType": mime_type,
                "isVisual": is_visual,
                
                # Symlink (Active)
                "isSymlink": is_symlink,
                "symlinkTarget": symlink_target,
                
                # Timestamps (Active)
                "dateModified": date_modified,
                "dateAccessed": date_accessed,
                
                # Permissions (Passive - for future properties dialog)
                "mode": mode,
                "uid": uid,
                "gid": gid,
                
                # Directory info (Active)
                "childCount": child_count,
                
                # Thumbnail dimensions (populated by UI after load)
                "width": 0,
                "height": 0,
            })
        
        return batch

    def _get_timestamp(self, dt: GLib.DateTime | None) -> int:
        """Convert GLib.DateTime to Unix timestamp, or 0 if unavailable."""
        if dt is None:
            return 0
        try:
            return dt.to_unix()
        except Exception:
            return 0



    def _on_count_ready(self, path: str, count: int) -> None:
        """Called when ItemCountWorker finishes counting a directory."""
        self.fileAttributeUpdated.emit(path, "childCount", count)

    def _close_enumerator(self, enumerator: Gio.FileEnumerator) -> None:
        """Safely close the enumerator to release resources."""
        try:
            enumerator.close(None)
        except Exception:
            pass

