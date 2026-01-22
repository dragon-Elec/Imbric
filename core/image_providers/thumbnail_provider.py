"""
[DONE] ThumbnailProvider — Async Thumbnail Loading

Provides thumbnails using GnomeDesktop.DesktopThumbnailFactory.
Uses QQuickAsyncImageProvider for non-blocking thumbnail generation.

Usage in QML: source: "image://thumbnail/" + "/path/to/file.jpg"
"""

import gi
gi.require_version('GnomeDesktop', '3.0')
from gi.repository import GnomeDesktop, GLib

from PySide6.QtQuick import QQuickAsyncImageProvider, QQuickImageResponse
from PySide6.QtGui import QImage, QIcon
from PySide6.QtCore import QSize, QRunnable, QThreadPool, Signal, QObject

import os
import urllib.parse

# Supported image extensions that Qt can load directly
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg', '.tiff', '.tif', '.ico'}


class ThumbnailResponse(QQuickImageResponse):
    """
    Response object for async thumbnail loading.
    
    Qt polls this object to check if the image is ready.
    """
    
    def __init__(self, path: str, requested_size: QSize, factory):
        super().__init__()
        self._image = QImage()
        self._path = path
        self._requested_size = requested_size
        self._factory = factory
        
        # Start background loading
        runnable = ThumbnailRunnable(self)
        QThreadPool.globalInstance().start(runnable)
    
    def textureFactory(self):
        """Called by Qt when response is ready. Return the image as texture."""
        from PySide6.QtQuick import QQuickTextureFactory
        return QQuickTextureFactory.textureFactoryForImage(self._image)
    
    def set_image(self, image: QImage):
        """Called by worker when image is ready."""
        self._image = image
        self.finished.emit()
    
    def errorString(self):
        return ""


class ThumbnailRunnable(QRunnable):
    """
    Background worker that generates thumbnails.
    """
    
    def __init__(self, response: ThumbnailResponse):
        super().__init__()
        self._response = response
        self.setAutoDelete(True)
    
    def run(self):
        """Generate or load thumbnail in background thread."""
        file_path = self._response._path
        requested_size = self._response._requested_size
        factory = self._response._factory
        
        target_size = requested_size if requested_size.isValid() else QSize(128, 128)
        
        # --- Symlink Resolution ---
        # Resolve symlinks to get the actual target path
        is_symlink = os.path.islink(file_path)
        resolved_path = os.path.realpath(file_path) if is_symlink else file_path
        
        # Check if target exists (handles broken symlinks)
        if not os.path.exists(resolved_path):
            # Broken symlink or missing file
            img = self._get_themed_icon("emblem-symbolic-link" if is_symlink else "dialog-error", target_size)
            self._response.set_image(img)
            return
        
        # Directories: Return folder icon
        if os.path.isdir(resolved_path):
            img = self._get_themed_icon("folder", target_size)
            self._response.set_image(img)
            return
        
        # Check file extension (use RESOLVED path for correct extension)
        ext = os.path.splitext(resolved_path)[1].lower()
        
        # Non-image files: Get MIME-based icon from desktop theme
        if ext not in IMAGE_EXTENSIONS:
            img = self._get_mime_icon(resolved_path, target_size)
            self._response.set_image(img)
            return
        
        # Try GNOME thumbnail cache (use RESOLVED path for URI)
        uri = "file://" + urllib.parse.quote(resolved_path)
        try:
            mtime = int(os.path.getmtime(resolved_path))
        except OSError:
            self._response.set_image(self._get_themed_icon("image-x-generic", target_size))
            return
        
        # Check cache
        thumb_path = factory.lookup(uri, mtime)
        
        if not thumb_path:
            # Generate thumbnail
            try:
                mime_map = {
                    '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                    '.png': 'image/png', '.gif': 'image/gif',
                    '.bmp': 'image/bmp', '.webp': 'image/webp',
                    '.svg': 'image/svg+xml', '.tiff': 'image/tiff',
                    '.tif': 'image/tiff', '.ico': 'image/x-icon',
                }
                mime_type = mime_map.get(ext, 'image/png')
                
                pixbuf = factory.generate_thumbnail(uri, mime_type)
                if pixbuf:
                    factory.save_thumbnail(pixbuf, uri, mtime)
                    thumb_path = factory.lookup(uri, mtime)
            except Exception:
                pass  # Silent fail, fallback to original
        
        # Load from thumbnail or original
        if thumb_path and os.path.exists(thumb_path):
            img = QImage(thumb_path)
        else:
            # Fallback: Load original image
            img = QImage(file_path)
        
        if img.isNull():
            img = self._get_themed_icon("image-x-generic", target_size)
        elif requested_size.isValid():
            from PySide6.QtCore import Qt
            img = img.scaled(requested_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        
        self._response.set_image(img)
    
    def _get_themed_icon(self, icon_name: str, target_size: QSize) -> QImage:
        """Load a themed icon as QImage."""
        icon = QIcon.fromTheme(icon_name)
        if icon.isNull():
            icon = QIcon.fromTheme("application-x-generic")
        
        if not icon.isNull():
            return icon.pixmap(target_size).toImage()
        
        return QImage()
    
    def _get_mime_icon(self, file_path: str, target_size: QSize) -> QImage:
        """
        Get the desktop theme icon for a file's MIME type.
        
        Uses Gio to detect content type and retrieve the appropriate icon.
        """
        from gi.repository import Gio
        
        try:
            gfile = Gio.File.new_for_path(file_path)
            info = gfile.query_info("standard::icon", Gio.FileQueryInfoFlags.NONE, None)
            gicon = info.get_icon()
            
            if gicon:
                # Get icon names from GIcon (ThemedIcon has get_names())
                if hasattr(gicon, 'get_names'):
                    icon_names = gicon.get_names()
                    for name in icon_names:
                        icon = QIcon.fromTheme(name)
                        if not icon.isNull():
                            return icon.pixmap(target_size).toImage()
        except Exception:
            pass  # Fall through to generic icon
        
        # Fallback to generic file icon
        return self._get_themed_icon("application-x-generic", target_size)


class ThumbnailProvider(QQuickAsyncImageProvider):
    """
    Async thumbnail provider using GNOME Desktop Thumbnail Factory.
    
    Inherits from QQuickAsyncImageProvider for non-blocking operation.
    """
    
    def __init__(self):
        super().__init__()
        self._factory = GnomeDesktop.DesktopThumbnailFactory.new(GnomeDesktop.DesktopThumbnailSize.LARGE)
    
    def requestImageResponse(self, id_path: str, requested_size: QSize) -> QQuickImageResponse:
        """
        Called by Qt when an image is requested.
        
        Returns a response object that will be populated asynchronously.
        """
        return ThumbnailResponse(id_path, requested_size, self._factory)
