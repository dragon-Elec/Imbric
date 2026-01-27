from PySide6.QtCore import QObject, Slot, QRectF

class SelectionHelper(QObject):
    """
    Helper class to perform geometry intersection checks for rubberband selection.
    Offloads the O(N) geometry check from QML JS to Python for slight perf gain 
    and cleaner code.
    """
    def __init__(self):
        super().__init__()

    @Slot(QObject, int, float, float, float, float, float, float, result=list)
    def getMasonrySelection(self, splitter, col_count, col_width, spacing, x, y, w, h):
        """
        Calculates selection based on theoretical Masonry layout.
        Since QML ListViews are virtualized, we can't query item geometry from QML
        for off-screen items. We must replicate the layout logic here.
        """
        if not splitter: return []
        
        # Access the master list from the splitter (we need to add a getter to splitter or access protected)
        # Assuming splitter has 'all_items' property exposed or we access _all_items
        items = splitter.getAllItems() 
        if not items: return []
        
        selection_rect = QRectF(x, y, w, h).normalized()
        selected_paths = []
        
        # Track Y position for each column
        col_y = [0.0] * col_count
        
        # Footer height constraint (Must match QML)
        footer_height = 36
        
        for i, item in enumerate(items):
            # 1. Determine Column
            col_idx = i % col_count
            
            # 2. Determine X
            # Margin? Padding? Assuming 0 padding for now or passed in 'x' includes it relative to flow.
            # QML Row spacing is 10.
            # Row is centered? 
            # Actually, the QML structure is: Row { spacing: 10 ... }
            # So X = col_idx * (col_width + spacing)
            item_x = col_idx * (col_width + spacing)
            
            # 3. Determine Height
            width = item.get('width', 0)
            height = item.get('height', 0)
            is_dir = item.get('isDir', False)
            
            display_height = col_width # Fallback
            if is_dir:
                display_height = col_width * 0.8
            elif width > 0 and height > 0:
                display_height = (height / width) * col_width
            
            total_item_height = display_height + footer_height
            
            # 4. Determine Y
            item_y = col_y[col_idx]
            
            # 5. Check Intersection
            item_rect = QRectF(item_x, item_y, col_width, total_item_height)
            
            if selection_rect.intersects(item_rect):
                selected_paths.append(item.get('path'))
                
            # 6. Update Column Y (Add spacing? ListView spacing?)
            # QML ListView default spacing is 0 unless set. "MasonryView" delegate has margins?
            # Delegate has: anchors.margins: 4 inside a container. But Delegate height is exact.
            # Let's assume 0 spacing between delegates in the ListView for now unless we see spacing.
            col_y[col_idx] += total_item_height
            
        return selected_paths
