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
gi.require_version('GnomeDesktop', '3.0')
from gi.repository import Gio, GLib, GnomeDesktop
import urllib.parse
from uuid import uuid4

from PySide6.QtCore import QObject, Signal, Slot, QTimer
# from PySide6.QtGui import QImageReader # REMOVED: No longer used in main thread
from core.gio_bridge.count_worker import ItemCountWorker
from core.gio_bridge.dimension_worker import DimensionWorker


class FileScanner(QObject):
    """
    Async directory scanner using Gio.
    
    Signals:
        filesFound(str, list) - Emitted with (session_id, batch) for cross-talk filtering
        scanFinished(str) - Emitted with session_id when scan completes successfully
        scanError(str) - Emitted on fatal error (e.g., directory not found)
    """
    
    # [FIX] Session-tagged signals to prevent cross-talk
    filesFound = Signal(str, list)  # (session_id, batch)
    scanFinished = Signal(str)       # (session_id)
    scanError = Signal(str)
    fileAttributeUpdated = Signal(str, str, object)  # path, attribute_name, value

    # Valid visual extensions (thumbnails needed)
    # VISUAL_EXTENSIONS removed in favor of MIME type detection

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
        
        # Thumbnail info (Active: Native detection)
        "standard::thumbnail-path"
    ])

    # Batch size for efficient layout updates
    BATCH_SIZE = 200

    # [FIX] Timer interval for coalesced emission (reduces layout thrashing)
    EMIT_DEBOUNCE_MS = 100

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cancellable: Gio.Cancellable | None = None
        self._current_path: str | None = None
        self._show_hidden: bool = False
        
        # [FIX] Session ID for cross-talk prevention
        self._session_id: str = ""
        
        # [FIX] Buffer and timer for coalesced emission
        self._batch_buffer: list[dict] = []
        self._emit_timer = QTimer(self)
        self._emit_timer.setInterval(self.EMIT_DEBOUNCE_MS)
        self._emit_timer.setSingleShot(True)
        self._emit_timer.timeout.connect(self._flush_buffer)
        
        # Background item counter
        self._count_worker = ItemCountWorker(self)
        self._count_worker.countReady.connect(self._on_count_ready)

        # [NEW] Background dimension reader (Async)
        self._dimension_worker = DimensionWorker(self)
        self._dimension_worker.dimensionsReady.connect(self._on_dimensions_ready)
        
        # [NEW] Shared Thumbnail Factory (Lazy load to avoid overhead if not needed immediately)
        self._factory = None

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
        # [FIX] Generate unique session ID for cross-talk prevention
        self._session_id = str(uuid4())
        
        # Capture the specific token for this scan
        cancellable = self._cancellable
        
        gfile = Gio.File.new_for_path(path)
        
        gfile.enumerate_children_async(
            self.QUERY_ATTRIBUTES,
            Gio.FileQueryInfoFlags.NONE,
            GLib.PRIORITY_DEFAULT,
            cancellable,
            self._on_enumerate_ready,
            cancellable # Pass token as user_data
        )

    @Slot()
    def cancel(self) -> None:
        """Cancel any in-progress scan."""
        # [FIX] Stop timer and clear buffer to prevent stale emissions
        self._emit_timer.stop()
        self._batch_buffer.clear()
        
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
        cancellable = user_data
        if cancellable.is_cancelled():
            return

        try:
            enumerator = source.enumerate_children_finish(result)
        except GLib.Error as e:
            if cancellable.is_cancelled(): return
            error_msg = f"Cannot open directory: {e.message}"
            print(f"[FileScanner] Error: {error_msg}")
            self.scanError.emit(error_msg)
            return
        
        parent_path = source.get_path()
        if parent_path is None:
            self.scanError.emit("Invalid directory path")
            return
        
        self._fetch_next_batch(enumerator, parent_path, cancellable)

    def _fetch_next_batch(self, enumerator: Gio.FileEnumerator, parent_path: str, cancellable: Gio.Cancellable) -> None:
        """Request the next batch of files from the enumerator."""
        enumerator.next_files_async(
            self.BATCH_SIZE,
            GLib.PRIORITY_DEFAULT,
            cancellable,
            self._on_batch_ready,
            (enumerator, parent_path, cancellable)
        )

    def _on_batch_ready(
        self,
        source_obj,
        result: Gio.AsyncResult,
        context: tuple
    ) -> None:
        """Callback when a batch of files is ready."""
        stored_enumerator, parent_path, cancellable = context
        
        if cancellable.is_cancelled():
            self._close_enumerator(stored_enumerator)
            return
        
        try:
            file_infos = stored_enumerator.next_files_finish(result)
        except GLib.Error as e:
            if cancellable.is_cancelled():
                self._close_enumerator(stored_enumerator)
                return
                
            error_msg = f"Error reading directory contents: {e.message}"
            print(f"[FileScanner] {error_msg}")
            self.scanError.emit(error_msg)
            self._close_enumerator(stored_enumerator)
            return
        
        if not file_infos:
            # [FIX] Flush remaining buffer before signaling completion
            self._flush_buffer()
            self.scanFinished.emit(self._session_id)
            self._close_enumerator(stored_enumerator)
            return
        
        batch = self._process_batch(file_infos, parent_path)
        
        # [FIX] Buffer batch instead of immediate emit (reduces layout thrashing)
        if batch:
            self._batch_buffer.extend(batch)
            if not self._emit_timer.isActive():
                self._emit_timer.start()
        
        self._fetch_next_batch(stored_enumerator, parent_path, cancellable)

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
            
            # Extension & Visual Check -> NATIVE THUMBNAIL LOGIC
            # Full path (MOVED UP: Required for Native Thumbnail Logic)
            if parent_path == '/':
                full_path = '/' + name
            else:
                full_path = parent_path + '/' + name

            # Type detection (MOVED UP: Required for can_thumbnail logic)
            file_type = info.get_file_type()
            is_dir = file_type == Gio.FileType.DIRECTORY
            
            # 1. Initialize factory if needed
            if self._factory is None:
                self._factory = GnomeDesktop.DesktopThumbnailFactory.new(GnomeDesktop.DesktopThumbnailSize.LARGE)

            mime_type = info.get_content_type() or ""
            
            # 2. Check for existing thumbnail (Fastest path)
            thumb_path = info.get_attribute_byte_string("standard::thumbnail-path")
            
            is_visual = False
            if thumb_path:
                is_visual = True
            else:
                # 3. Ask the Oracle (Can we thumbnail this?)
                # We need a URI for this check
                uri = "file://" + urllib.parse.quote(full_path)
                mtime = info.get_modification_date_time().to_unix() if info.get_modification_date_time() else 0
                
                # Only check if it's a file (directories don't get thumbnails via this factory usually)
                if not is_dir:
                    try:
                        is_visual = self._factory.can_thumbnail(uri, mime_type, mtime)
                    except Exception:
                        pass
            
            # is_visual tells the UI to request a thumbnail.
            # should_read_dimensions tells the backend to read the header for Aspect Ratio.
            # We ONLY read dims for actual images. Videos/PDFs get thumbnails but stay square.
            should_read_dimensions = mime_type.startswith("image/")
            
            # Full path (ALREADY CALCULATED ABOVE)
            # if parent_path == '/':
            #     full_path = '/' + name
            # else:
            #     full_path = parent_path + '/' + name
            
            # Type detection (ALREADY CALCULATED ABOVE)
            # file_type = info.get_file_type()
            # is_dir = file_type == Gio.FileType.DIRECTORY
            is_symlink = info.get_is_symlink()
            
            # Symlink target (empty string if not a symlink)
            symlink_target = ""
            if is_symlink:
                target = info.get_symlink_target()
                symlink_target = target if target else ""
            
            # Size
            size = info.get_size()
            
            # MIME type (e.g., "image/jpeg", "inode/directory")
            # Already fetched above for is_visual check
            
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

            
            # Determine icon name for non-visual files (used by QML image://theme/)
            icon_name = ""
            if not is_visual:
                # Convert MIME type to icon name (e.g., "inode/directory" -> "inode-directory")
                icon_name = mime_type.replace("/", "-") if mime_type else "application-x-generic"

            batch.append({
                # Core
                "name": name,
                "path": full_path,
                "iconName": icon_name,  # For QML image://theme/ (non-visual only)
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
                
                # Thumbnail dimensions (populated by header read)
                "width": 0,
                "height": 0,
            })
            
            # [NEW] Queue dimension reading (Async)
            # Only for supported image types (videos/PDFs stay square)
            if should_read_dimensions:
                self._dimension_worker.enqueue(full_path)
            
            # width/height default to 0 initially (see lines 341-342)
        
        return batch

    def _get_timestamp(self, dt: GLib.DateTime | None) -> int:
        """Convert GLib.DateTime to Unix timestamp, or 0 if unavailable."""
        if dt is None:
            return 0
        try:
            return dt.to_unix()
        except Exception:
            return 0

    def _flush_buffer(self) -> None:
        """
        [FIX] Timer callback: Emit all buffered files at once.
        Reduces layout updates from 50+ to ~10 per second.
        """
        if self._batch_buffer and self._session_id:
            self.filesFound.emit(self._session_id, self._batch_buffer)
            self._batch_buffer = []



    def _on_count_ready(self, path: str, count: int) -> None:
        """Called when ItemCountWorker finishes counting a directory."""
        self.fileAttributeUpdated.emit(path, "childCount", count)

    def _on_dimensions_ready(self, path: str, width: int, height: int) -> None:
        """Called when DimensionWorker finishes reading header."""
        # Update width and height
        # [FIX] optimized: emit single signal to prevent double layout invalidation
        self.fileAttributeUpdated.emit(path, "dimensions", {"width": width, "height": height})

    def _close_enumerator(self, enumerator: Gio.FileEnumerator) -> None:
        """Safely close the enumerator to release resources."""
        try:
            enumerator.close(None)
        except Exception:
            pass

