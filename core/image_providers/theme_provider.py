"""
[NEW] ThemeImageProvider — System Icon Theme Integration

Provides freedesktop theme icons via the 'image://theme/' QML URL scheme.
Leverages Qt's QQuickPixmapCache for efficient RAM sharing across delegates.

Usage in QML: source: "image://theme/folder"
"""

from PySide6.QtQuick import QQuickImageProvider
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtCore import QSize


class ThemeImageProvider(QQuickImageProvider):
    """
    Image provider that resolves freedesktop icon names to themed pixmaps.
    
    Automatically selects the best icon variant (SVG, PNG) based on system theme
    and requested size. QML's internal cache ensures each unique (name, size) pair
    is rendered only once, even if 1000 delegates request "folder" at 128px.
    """
    
    def __init__(self):
        # Use Pixmap type for efficient caching
        super().__init__(QQuickImageProvider.Pixmap)
    
    def requestPixmap(self, id: str, size: QSize, requestedSize: QSize):
        """
        Called by Qt when QML requests an icon.
        
        Args:
            id: Icon name (e.g., "folder", "application-pdf", "inode-directory")
            size: Output parameter (Qt modifies this automatically)
            requestedSize: Size requested by QML (from sourceSize property)
        
        Returns:
            QPixmap (size is set via output parameter automatically by Qt)
        """
        target_size = requestedSize if requestedSize.isValid() else QSize(128, 128)
        
        icon = QIcon()
        
        # If the requested ID is a MIME type (contains '/'), use Gio to get proper fallback names
        if "/" in id:
            from gi.repository import Gio
            gicon = Gio.content_type_get_icon(id)
            if gicon and hasattr(gicon, 'get_names'):
                for name in gicon.get_names():
                    if QIcon.hasThemeIcon(name):
                        icon = QIcon.fromTheme(name)
                        break
        else:
            # Standard single icon name request
            if QIcon.hasThemeIcon(id):
                icon = QIcon.fromTheme(id)
        
        # Fallback to generic icon if theme icon not found or generation failed
        if icon.isNull():
            icon = QIcon.fromTheme("application-x-generic")
        
        # Render at requested size and return
        return icon.pixmap(target_size)
