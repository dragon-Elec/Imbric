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
# IMAGE_EXTENSIONS removed in favor of MIME fallback


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
    
    # Shared cache for generic MIME icons to prevent RAM explosion
    # Key: mime_type (str), Value: QImage
    _mime_icon_cache = {}

    def run(self):
        """Generate or load thumbnail in background thread."""
        file_path = self._response._path
        requested_size = self._response._requested_size
        factory = self._response._factory
        
        target_size = requested_size if requested_size.isValid() else QSize(256, 256)

        # [NEW] Check if this is a generic MIME request
        if file_path.startswith("mime/"):
            mime_type = file_path.replace("mime/", "")
            
            # 1. Check Cache First
            if mime_type in self._mime_icon_cache:
                self._response.set_image(self._mime_icon_cache[mime_type])
                return

            # 2. Generate and Cache
            img = self._get_mime_icon_from_type(mime_type, target_size)
            self._mime_icon_cache[mime_type] = img
            
            self._response.set_image(img)
            return
        
        # --- Symlink Resolution ---
        is_symlink = os.path.islink(file_path)
        resolved_path = os.path.realpath(file_path) if is_symlink else file_path
        
        # --- 1. HANDLE BROKEN SYMLINKS ---
        if not os.path.exists(resolved_path):
            # Broken Symlink: Base=Link Arrow, Emblem=Unavailable/X
            # User wants to see it looks like a LINK first, then broken.
            img = self._get_emblemed_icon(
                "emblem-symbolic-link",  # Base: Symlink Arrow
                "emblem-unreadable",     # Overlay: X (Error)
                target_size
            )
            self._response.set_image(img)
            return

        # --- 2. HANDLE DIRECTORIES ---
        if os.path.isdir(resolved_path):
            base_icon = "folder"
            # Check permissions (Locked Folder)
            if not os.access(resolved_path, os.W_OK):
                img = self._get_emblemed_icon(base_icon, "emblem-readonly", target_size)
            else:
                img = self._get_themed_icon(base_icon, target_size)
            self._response.set_image(img)
            return
        
        # --- 3. HANDLE FILES (Images & Others) ---
        ext = os.path.splitext(resolved_path)[1].lower()
        
        # Special Case: Locked File (Non-Image)
        # Verify read/write access. If read-only, we might want a lock emblem.
        is_locked = not os.access(resolved_path, os.W_OK)
        
        # Non-image files: Get MIME-based icon [+ Lock if needed]
        # Non-image files: Get MIME-based icon [+ Lock if needed]
        # [FIX] Trust the MIME type. If it's a known image type or video, we try to thumb it.
        # Use Gio to detect if we should fallback.
        
        # If we have no extension, we rely purely on MIME type (which factory handles).
        # We only fallback if it's NOT an image/video MIME type.
        
        try:
             # Re-query MIME if not passed (though ideally we should pass it)
             # For now, let's treat "application/octet-stream" as a potential fallback
             pass
        except:
             pass

        # We allow the factory to attempt ANY file. 
        # Only if it fails will we show the generic icon later.
        
        # --- 4. HANDLE IMAGES ---
        # Try GNOME thumbnail cache
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
                # Use Gio to detect the actual content type content_type
                try:
                    # We create a new file object for the path to query its content type
                    # This is fast and local
                    gfile = Gio.File.new_for_path(resolved_path) 
                    info = gfile.query_info("standard::content-type", Gio.FileQueryInfoFlags.NONE, None)
                    mime_type = info.get_content_type()
                except Exception:
                    # Fallback if Gio fails
                    mime_map = {
                        '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                        '.png': 'image/png', '.gif': 'image/gif',
                        '.bmp': 'image/bmp', '.webp': 'image/webp',
                        '.svg': 'image/svg+xml', '.tiff': 'image/tiff',
                        '.tif': 'image/tiff', '.ico': 'image/x-icon',
                    }
                    mime_type = mime_map.get(ext, 'image/png')
                
                if mime_type:
                    pixbuf = factory.generate_thumbnail(uri, mime_type)
                    if pixbuf:
                        factory.save_thumbnail(pixbuf, uri, mtime)
                        thumb_path = factory.lookup(uri, mtime) 
            except Exception:
                pass 
        
        # Load from thumbnail or original
        is_from_cache = False
        if thumb_path and os.path.exists(thumb_path):
            img = QImage(thumb_path)
            is_from_cache = True
        else:
            # FIX: Memory-efficient loading via QImageReader
            from PySide6.QtGui import QImageReader
            reader = QImageReader(resolved_path)
            
            # [SAFETY] Always limit decode size for raw files to prevent RAM explosion
            # If requested_size is invalid (removed from QML for quality), use target_size (256)
            decode_size = requested_size if requested_size.isValid() else target_size
            reader.setScaledSize(decode_size)
            
            img = reader.read()
        
        if img.isNull():
             # [FIX] If thumbnailing failed completely, fallback to MIME icon
            img = self._get_mime_icon(resolved_path, target_size)
            
        elif requested_size.isValid() and not is_from_cache:
            # Only scale if we loaded a raw original image.
            # If it's a cached thumbnail (256px), return as-is for HiDPI sharpness.
            from PySide6.QtCore import Qt
            img = img.scaled(requested_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            
        # Add Lock Emblem if needed (even on thumbnails!)
        if is_locked:
            img = self._overlay_emblem(img, "emblem-readonly", target_size)
            
        self._response.set_image(img)
    
    def _get_mime_icon_from_type(self, mime_type: str, target_size: QSize) -> QImage:
        """
        Get the desktop theme icon directly from a MIME type string.
        """
        from gi.repository import Gio
        
        try:
            # Get GIcon for the MIME type
            gicon = Gio.content_type_get_icon(mime_type)
            
            if gicon:
                if hasattr(gicon, 'get_names'):
                    for name in gicon.get_names():
                        icon = QIcon.fromTheme(name)
                        if not icon.isNull():
                            return icon.pixmap(target_size).toImage()
        except Exception:
            pass
            
        return self._get_themed_icon("application-x-generic", target_size)

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
    def _get_emblemed_icon(self, base_icon_name: str, emblem_icon_name: str, target_size: QSize) -> QImage:
        """
        Get an icon with an emblem overlay.
        Wrapper helper that loads base icon and calls _overlay_emblem.
        """
        base_img = self._get_themed_icon(base_icon_name, target_size)
        return self._overlay_emblem(base_img, emblem_icon_name, target_size)
    
    def _overlay_emblem(self, base_image: QImage, emblem_name: str, target_size: QSize) -> QImage:
        """
        Overlay an emblem onto an existing QImage.
        """
        from PySide6.QtGui import QPainter, QIcon
        from PySide6.QtCore import Qt
        
        # Create a copy to draw on
        result = base_image.copy()
        if result.isNull():
             return result

        # Get emblem icon
        emblem_size = QSize(target_size.width() // 2, target_size.height() // 2)
        emblem_icon = QIcon.fromTheme(emblem_name)
        
        if not emblem_icon.isNull():
            emblem_pixmap = emblem_icon.pixmap(emblem_size)
            
            # Composite (Bottom-Right)
            painter = QPainter(result)
            emblem_x = target_size.width() - emblem_size.width()
            emblem_y = target_size.height() - emblem_size.height()
            painter.drawPixmap(emblem_x, emblem_y, emblem_pixmap)
            painter.end()
            
        return result


class ThumbnailProvider(QQuickAsyncImageProvider):
    """
    Async thumbnail provider using GNOME Desktop Thumbnail Factory.
    
    Inherits from QQuickAsyncImageProvider for non-blocking operation.
    """
    
    # Shared factory instance (Singleton) to avoid per-tab memory overhead
    _shared_factory = None

    def __init__(self):
        super().__init__()
        
        # Initialize singleton if not exists
        if ThumbnailProvider._shared_factory is None:
            ThumbnailProvider._shared_factory = GnomeDesktop.DesktopThumbnailFactory.new(GnomeDesktop.DesktopThumbnailSize.LARGE)
            
        self._factory = ThumbnailProvider._shared_factory
    
    def requestImageResponse(self, id_path: str, requested_size: QSize) -> QQuickImageResponse:
        """
        Called by Qt when an image is requested.
        
        Returns a response object that will be populated asynchronously.
        """
        return ThumbnailResponse(id_path, requested_size, self._factory)
