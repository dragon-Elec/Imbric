"""
RowBuilder — Justified Grid Layout Engine (Phase 1)

Replaces ColumnSplitter with a simple row-based layout.
Input: List of file items.
Output: List of rows (where each row is a list of items).

Algorithm:
1. Sort items (using Sorter).
2. Scale items to fixed ROW_HEIGHT.
3. Pack left-to-right until width limit is reached.
4. Wrap to new row.
"""

from PySide6.QtCore import QObject, Slot, Signal, Property, QTimer
from core.sorter import Sorter
import hashlib
import urllib.parse
import os

class RowBuilder(QObject):
    rowsChanged = Signal()
    sortChanged = Signal()
    rowHeightChanged = Signal(int)
    selectAllRequested = Signal()
    
    # Constants for Phase 1
    FOOTER_HEIGHT = 36
    SPACING = 10
    
    # Layout Constants
    DEFAULT_ROW_HEIGHT = 120
    MIN_ROW_HEIGHT = 80
    MAX_ROW_HEIGHT = 400
    ZOOM_STEP = 20
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._image_height = self.DEFAULT_ROW_HEIGHT # Default
        self._items = []        # All items (raw)
        self._sorted_items = [] # All items (sorted)
        self._rows = []         # List of rows (list of list of dicts)
        self._available_width = 1000 # Default fallback
        
        # [FIX] Streaming mode flag
        self._is_loading = False
        
        # [FIX] Pending dimensions cache (race condition fix)
        # Dimensions may arrive before filesFound due to debouncing
        self._pending_dimensions: dict[str, tuple[int, int]] = {}  # path -> (width, height)
        
        self._sorter = Sorter(self)
        self._sorter.sortChanged.connect(self._on_sort_changed)
        
        # [FIX] Layout Debouncer
        self._layout_timer = QTimer(self)
        self._layout_timer.setSingleShot(True)
        self._layout_timer.setInterval(50) # 50ms debounce
        self._layout_timer.timeout.connect(self._perform_layout_update)

    def _trigger_layout_update(self):
        """Schedule a layout update."""
        self._layout_timer.start()

    def _perform_layout_update(self):
        """Actually execute the build."""
        self._build_rows()
        self.rowsChanged.emit()

    @property
    def sorter(self) -> Sorter:
        return self._sorter

    @Slot(int)
    def setRowHeight(self, height: int) -> None:
        """Set the target image height for rows."""
        # Clamp to reasonable values
        height = max(self.MIN_ROW_HEIGHT, min(self.MAX_ROW_HEIGHT, height))
        
        if height != self._image_height:
            self._image_height = height
            self._trigger_layout_update()
            # self.rowsChanged.emit() # Handled by timer
            self.rowHeightChanged.emit(height)

    @Slot(result=int)
    def getRowHeight(self) -> int:
        return self._image_height

    @Slot(int, result=int)
    def calculate_next_zoom_height(self, direction: int) -> int:
        """
        Calculates next height to snap to a perfect grid column count.
        direction: +1 (Zoom In), -1 (Zoom Out)
        Force a min step of 15px to ensure zoom feels responsive.
        """
        if self._available_width <= 0:
            return self._image_height + (direction * self.ZOOM_STEP)
            
        width = self._available_width
        spacing = self.SPACING
        h = self._image_height
        
        # Current capacity (N items of size h)
        # W = N*H + (N-1)*S  =>  N = (W + S) / (H + S)
        current_cols = int((width + spacing) / (h + spacing))
        if current_cols < 1: current_cols = 1
        
        target_cols = current_cols
        new_h = h
        
        # Loop until we find a height change >= 15px (or hit limits)
        while True:
            target_cols = target_cols - direction # In (+1) -> Fewer Cols, Out (-1) -> More Cols
            
            if target_cols < 1: 
                # Can't have 0 cols, cap at Max Height
                return self.MAX_ROW_HEIGHT
            
            # Calc Height for this count: H = (W - (N-1)*S) / N
            calculated_h = (width - (target_cols - 1) * spacing) / target_cols
            
            # Check difference
            if abs(calculated_h - h) >= 15:
                # Found a good step
                new_h = int(calculated_h)
                break
                
            # Safety break to prevent infinite loops at extremes
            if calculated_h < self.MIN_ROW_HEIGHT and direction == -1: 
                new_h = self.MIN_ROW_HEIGHT
                break
            if calculated_h > self.MAX_ROW_HEIGHT and direction == 1:
                new_h = self.MAX_ROW_HEIGHT
                break
                
        # Final Clamp
        return max(self.MIN_ROW_HEIGHT, min(self.MAX_ROW_HEIGHT, new_h))


    @Slot(int)
    def setAvailableWidth(self, width: int) -> None:
        """Update available width and re-layout if changed."""
        if width != self._available_width and width > 0:
            self._available_width = width
            self._trigger_layout_update()
            # self.rowsChanged.emit()

    @Slot(list)
    def setFiles(self, files: list) -> None:
        """Called on navigation to reset the view."""
        self._items = files
        self._sorted_items = []
        self._rows = []
        self._is_loading = True
        self._pending_dimensions.clear()  # [FIX] Clear stale dimensions from previous folder
        # Don't emit yet, waiting for finishLoading
        
    # GNOME Thumbnail Cache Size (LARGE = 256px longest edge)
    THUMBNAIL_CACHE_SIZE = 256
    
    # GNOME thumbnail cache directory (resolved once)
    _THUMB_CACHE_DIR = os.path.expanduser("~/.cache/thumbnails/large")

    @staticmethod
    def _resolve_thumbnail_url(path: str) -> str:
        """
        Pre-compute the thumbnail URL for a visual item.
        
        Checks the GNOME thumbnail cache (MD5 of URI -> ~/.cache/thumbnails/large/).
        Returns a direct file:// URL if cached, else falls back to the async
        image://thumbnail/ provider.
        
        This runs once per item at load time, removing all blocking I/O
        from the QML render path.
        """
        try:
            uri = "file://" + urllib.parse.quote(path)
            md5_hash = hashlib.md5(uri.encode('utf-8')).hexdigest()
            thumb_path = os.path.join(RowBuilder._THUMB_CACHE_DIR, f"{md5_hash}.png")
            # [DEBUG] Force disable direct file access to test if it causes lag
            # if os.path.exists(thumb_path):
            #    return f"file://{thumb_path}"
        except Exception:
            pass
        return f"image://thumbnail/{path}"

    @Slot(list)
    def appendFiles(self, new_files: list) -> None:
        """Append files (streaming mode)."""
        if not new_files:
            return
        
        # [FIX] Apply any pending dimensions that arrived before this batch
        dimensions_applied = False
        for item in new_files:
            path = item.get("path")
            if path and path in self._pending_dimensions:
                w, h = self._pending_dimensions.pop(path)
                item["width"] = w
                item["height"] = h
                dimensions_applied = True
            
            # Calculate thumbnail cap dimensions
            self._calculate_thumbnail_cap(item)
            
            # [PERF] Pre-compute thumbnail URL (removes blocking I/O from QML render path)
            if item.get("isVisual") and path:
                item["thumbnailUrl"] = self._resolve_thumbnail_url(path)
            else:
                item["thumbnailUrl"] = ""
        
        self._items.extend(new_files)
        self._sorted_items.extend(new_files)
        self._build_rows()
        self.rowsChanged.emit()
    
    def _calculate_thumbnail_cap(self, item: dict) -> None:
        """
        Calculate the maximum display size for a thumbnail.
        
        For visuals (photos), this is the GNOME LARGE cache size (256px longest edge).
        For non-visuals (icons/vectors), this is 0 (no cap - can scale infinitely).
        """
        if not item.get("isVisual"):
            # Icons/folders: no cap (vectors scale infinitely)
            item["thumbnailWidth"] = 0
            item["thumbnailHeight"] = 0
            return
        
        # Visuals: cap at cache size, preserving aspect ratio
        w = item.get("width", 0)
        h = item.get("height", 0)
        
        if w > 0 and h > 0:
            # Scale to fit within cache size, longest edge = THUMBNAIL_CACHE_SIZE
            if w >= h:
                item["thumbnailWidth"] = self.THUMBNAIL_CACHE_SIZE
                item["thumbnailHeight"] = int(self.THUMBNAIL_CACHE_SIZE * h / w)
            else:
                item["thumbnailHeight"] = self.THUMBNAIL_CACHE_SIZE
                item["thumbnailWidth"] = int(self.THUMBNAIL_CACHE_SIZE * w / h)
        else:
            # Fallback: assume square thumbnail
            item["thumbnailWidth"] = self.THUMBNAIL_CACHE_SIZE
            item["thumbnailHeight"] = self.THUMBNAIL_CACHE_SIZE

    @Slot()
    def finishLoading(self) -> None:
        """Called when scan completes. Applies sorting."""
        self._is_loading = False
        self._reapply_sort_and_layout()

    @Slot()
    def clear(self) -> None:
        self._items = []
        self._sorted_items = []
        self._rows = []
        self._is_loading = False
        self.rowsChanged.emit()

    @Slot(dict)
    def addSingleItem(self, item: dict) -> None:
        """Surgically insert a single file without forcing a full scan reload."""
        path = item.get("path")
        print(f"[DEBUG-SURGICAL] RowBuilder: addSingleItem called for {path}")
        if not path: return
        
        # Check if already exists (debounce protection)
        for existing in self._items:
            if existing.get("path") == path:
                print(f"[DEBUG-SURGICAL] RowBuilder: Item already exists, ignoring {path}")
                return
                
        # Apply pending dimensions
        if path in self._pending_dimensions:
            w, h = self._pending_dimensions.pop(path)
            item["width"] = w
            item["height"] = h
            
        self._calculate_thumbnail_cap(item)
        if item.get("isVisual"):
            item["thumbnailUrl"] = self._resolve_thumbnail_url(path)
        else:
            item["thumbnailUrl"] = ""
            
        self._items.append(item)
        self._reapply_sort_and_layout()
        print(f"[DEBUG-SURGICAL] RowBuilder: Item added. Total items: {len(self._items)}")
        
    @Slot(str)
    def removeSingleItem(self, path: str) -> None:
        """Surgically remove a single file."""
        print(f"[DEBUG-SURGICAL] RowBuilder: removeSingleItem called for {path}")
        if not path: return
        for i, item in enumerate(self._items):
            if item.get("path") == path:
                self._items.pop(i)
                self._reapply_sort_and_layout()
                print(f"[DEBUG-SURGICAL] RowBuilder: Item {path} removed. Total items: {len(self._items)}")
                break

    @Slot(result="QVariant") # type: ignore # Returns list of lists
    def getRows(self):
        return self._rows
        
    @Slot(result="QObject*") # type: ignore
    def getSorter(self) -> Sorter:
        return self._sorter

    # --- Layout Logic ---

    def _on_sort_changed(self) -> None:
        self._reapply_sort_and_layout()

    def _reapply_sort_and_layout(self):
        self._sorted_items = self._sorter.sort(self._items)
        self._build_rows()
        self.rowsChanged.emit()

    def _build_rows(self):
        """
        The core "Simple Justified" algorithm.
        """
        if not self._sorted_items:
            self._rows = []
            return

        rows = []
        current_row = []
        current_width = 0
        
        # Max width for content (subtract padding if needed)
        max_width = self._available_width
        
        for item in self._sorted_items:
            # Calculate width when scaled to target height
            w = item.get('width', 0)
            h = item.get('height', 0)
            
            # Default aspect ratio 1.0 if missing dimensions
            if w > 0 and h > 0:
                aspect = w / h
            else:
                aspect = 1.0
                
            item_width = aspect * self._image_height
            
            # [FIX] Cap item_width at thumbnail's capability for row packing
            # This ensures more items fit per row at high zoom levels
            thumb_cap = max(item.get('thumbnailWidth', 0), item.get('thumbnailHeight', 0))
            if thumb_cap > 0:
                item_width = min(item_width, thumb_cap)
            
            # Does it fit?
            # If current_row is empty, we must add it (even if it's wider than screen)
            if current_width + item_width > max_width and current_row:
                # Row is full, finalize it
                rows.append(current_row)
                current_row = []
                current_width = 0
            
            current_row.append(item)
            current_width += item_width + self.SPACING
        
        # Don't forget the last row
        if current_row:
            rows.append(current_row)
            
        self._rows = rows

    # --- Selection Logic ---

    @Slot(int, int, result=list)
    def getItemsInRange(self, start_row_idx: int, end_row_idx: int) -> list:
        """
        Returns a list of item PATHS for the rows in the given range (inclusive).
        Used by RubberBand selection.
        """
        selected_paths = []
        
        if not self._rows:
            return []

        # Clamp indices
        if start_row_idx < 0: start_row_idx = 0
        if end_row_idx >= len(self._rows): end_row_idx = len(self._rows) - 1
        
        if start_row_idx > end_row_idx:
            return []
            
        for i in range(start_row_idx, end_row_idx + 1):
            row = self._rows[i]
            for item in row:
                selected_paths.append(item.get('path'))
                
        return selected_paths

    @Slot(int, int, int, int, result=list)
    def getItemsInRect(self, rect_x: int, rect_y: int, rect_w: int, rect_h: int) -> list:
        """
        Returns a list of item PATHS that intersect with the given rectangle.
        
        Coordinate System:
        - rect_x, rect_y: Content Coordinates (Already mapped from QML Viewport)
        - Helper: Checks if item box (x, y, w, h) overlaps rect (x, y, w, h)
        """
        selected_paths = []
        
        if not self._rows:
            return []

        # Optimization: Row-based filtering
        # Rows are stacked vertically. We know exactly where they are.
        # Height of one row block = image_height + footer + spacing (approx/exact?)
        # Justified Layout is constant height per row? Yes: _image_height.
        # But wait, RowDelegate has height = imageHeight + footerHeight.
        # Let's verify constant. 
        # RowDelegate.qml: height: imageHeight + footerHeight
        # AND spacing: 10 (in ListView)
        
        # NOTE: ListView spacing is handled by the ListView, not the RowBuilder's data structure.
        # But logically, the Y position of row N is:
        # Y = N * (ROW_HEIGHT + FOOTER_HEIGHT + LISTVIEW_SPACING)
        
        row_content_height = self._image_height + self.FOOTER_HEIGHT
        row_stride = row_content_height + self.SPACING
        
        # Calculate row index range
        start_row_idx = max(0, int(rect_y // row_stride))
        end_row_idx =  int((rect_y + rect_h) // row_stride)
        
        # Clamp
        end_row_idx = min(len(self._rows) - 1, end_row_idx)
        
        if start_row_idx > end_row_idx:
            return []
            
        # Iterate relevant rows
        for i in range(start_row_idx, end_row_idx + 1):
            row = self._rows[i]
            
            # Row Y start
            row_y = i * row_stride
            
            # Horizontal Scan
            current_x = 0
            for item in row:
                # Calculate Item Width (Visual)
                w = item.get('width', 0)
                h = item.get('height', 0)
                
                # Aspect
                aspect = (w / h) if (w > 0 and h > 0) else 1.0
                item_width = aspect * self._image_height

                # Thumbnail Cap check
                thumb_cap = max(item.get('thumbnailWidth', 0), item.get('thumbnailHeight', 0))
                if thumb_cap > 0:
                    item_width = min(item_width, thumb_cap)
                    
                # Calculate Item Height (Visual Image Only, excluding footer)
                # If we want to strictly select only when touching the image:
                item_height = self._image_height
                
                # FULL BOX INTERSECTION CHECK
                # Item Box: [current_x, row_y, item_width, item_height]
                
                # X Overlap: (ItemLeft < RectRight) AND (ItemRight > RectLeft)
                x_overlap = (current_x < rect_x + rect_w) and (current_x + item_width > rect_x)
                
                # Y Overlap: (ItemTop < RectBottom) AND (ItemBottom > RectTop)
                y_overlap = (row_y < rect_y + rect_h) and (row_y + item_height > rect_y)
                
                if x_overlap and y_overlap:
                    selected_paths.append(item.get('path'))
                
                # Advance X
                current_x += item_width + self.SPACING

        return selected_paths

    @Slot(result=list)
    def getAllItems(self) -> list:
        return self._sorted_items
        
    @Slot(str, str, object)
    def updateItem(self, path: str, attr: str, value) -> None:
        """Update a single item's attribute (e.g. childCount, width, height, dimensions)."""
        
        # [FIX] Consolidated dimensions update
        if attr == "dimensions":
            w = value.get("width", 0)
            h = value.get("height", 0)
            
            # 1. Update active item
            found = False
            for item in self._items:
                if item.get("path") == path:
                    item["width"] = w
                    item["height"] = h
                    # [CRITICAL] Re-calculate cap now that we have dimensions
                    self._calculate_thumbnail_cap(item)
                    found = True
                    self._trigger_layout_update()
                    break
            
            # 2. Cache pending (if item hasn't arrived from scanner yet)
            if not found:
                self._pending_dimensions[path] = (w, h)
            return

        # Standard attribute update (childCount, etc)
        for item in self._items:
            if item.get("path") == path:
                item[attr] = value
                break

