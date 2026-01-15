import gi
gi.require_version('GnomeDesktop', '3.0')
from gi.repository import GnomeDesktop, GLib

from PySide6.QtQuick import QQuickImageProvider
from PySide6.QtGui import QImage, QIcon
from PySide6.QtCore import QSize, QUrl, Qt

import os
import urllib.parse

# Supported image extensions that Qt can load directly
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg', '.tiff', '.tif', '.ico'}

class ThumbnailProvider(QQuickImageProvider):
    """
    Provides thumbnails using GnomeDesktop.DesktopThumbnailFactory.
    Usage in QML: source: "image://thumbnail/" + "/path/to/file.jpg"
    """
    def __init__(self):
        super().__init__(QQuickImageProvider.Image)
        self._factory = GnomeDesktop.DesktopThumbnailFactory.new(GnomeDesktop.DesktopThumbnailSize.LARGE)

    def requestImage(self, id_path, size, requestedSize):
        """
        id_path: The distinct path requested after image://thumbnail/
        size: QSize to be SET to the original image dimensions (passed by reference)
        requestedSize: Requested size from QML (optional hint)
        Returns: QImage
        """
        file_path = id_path
        
        if not os.path.exists(file_path):
            return QImage()
        
        target_size = requestedSize if requestedSize.isValid() else QSize(128, 128)
            
        if os.path.isdir(file_path):
            # Directories: Return system folder icon
            return self._get_themed_icon("folder", size, target_size)

        # Check file extension
        ext = os.path.splitext(file_path)[1].lower()
        
        # For non-image files, return a file icon
        if ext not in IMAGE_EXTENSIONS:
            return self._get_themed_icon("text-x-generic", size, target_size)

        # Get Thumbnail Path for images
        uri = "file://" + urllib.parse.quote(file_path)
        mtime = int(os.path.getmtime(file_path))
        
        # Try to find existing cached thumbnail
        thumb_path = self._factory.lookup(uri, mtime)

        if not thumb_path:
            # Thumbnail doesn't exist. Try to generate.
            try:
                mime_map = {
                    '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                    '.png': 'image/png', '.gif': 'image/gif',
                    '.bmp': 'image/bmp', '.webp': 'image/webp',
                    '.svg': 'image/svg+xml', '.tiff': 'image/tiff',
                    '.tif': 'image/tiff', '.ico': 'image/x-icon',
                }
                mime_type = mime_map.get(ext, 'image/png')
                
                pixbuf = self._factory.generate_thumbnail(uri, mime_type)
                if pixbuf:
                    self._factory.save_thumbnail(pixbuf, uri, mtime)
                    thumb_path = self._factory.lookup(uri, mtime)
            except Exception:
                pass  # Silent fail, will use fallback
        
        # Load from cached thumbnail path
        if thumb_path and os.path.exists(thumb_path):
            img = QImage(thumb_path)
        else:
            # Fallback: Load original image directly
            img = QImage(file_path)

        if img.isNull():
            # Image failed to load - return file icon
            return self._get_themed_icon("image-x-generic", size, target_size)

        # Set size to original image dimensions (REQUIRED by Qt)
        size.setWidth(img.width())
        size.setHeight(img.height())

        # Resize if requested (QML sourceSize)
        if requestedSize.isValid():
            img = img.scaled(requestedSize, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        return img
    
    def _get_themed_icon(self, icon_name, size, target_size):
        """Helper to get a themed icon as QImage and set size parameter."""
        icon = QIcon.fromTheme(icon_name)
        if icon.isNull():
            icon = QIcon.fromTheme("application-x-generic")
        
        if not icon.isNull():
            img = icon.pixmap(target_size).toImage()
            size.setWidth(img.width())
            size.setHeight(img.height())
            return img
        
        return QImage()
