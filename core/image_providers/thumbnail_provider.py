"""
[DONE] ThumbnailProvider — Async Thumbnail Loading

Provides thumbnails using GnomeDesktop.DesktopThumbnailFactory.
Uses QQuickAsyncImageProvider for non-blocking thumbnail generation.

Usage in QML: source: "image://thumbnail/" + "/path/to/file.jpg"
"""

import gi
gi.require_version('GnomeDesktop', '3.0')
from gi.repository import GnomeDesktop, GLib, Gio

from PySide6.QtQuick import QQuickAsyncImageProvider, QQuickImageResponse
from PySide6.QtGui import QImage, QIcon
from PySide6.QtCore import QSize, QRunnable, QThreadPool, Signal, QObject, QMutex, QMutexLocker

import os
import urllib.parse
from core.metadata_utils import get_file_info # Used for URI resolution

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
        
        # --- GIO / METADATA SYNC ---
        target_size = requested_size if requested_size.isValid() else QSize(256, 256)
        
        # 1. Resolve Path via MetadataUtils (handles recent:// targets)
        info = get_file_info(file_path)
        if not info:
             # File missing/broken
            img = self._get_emblemed_icon("emblem-unreadable", "emblem-unreadable", target_size)
            self._response.set_image(img)
            return

        # Use target_uri if it's a virtual shortcut (recent, search, etc)
        effective_path = info.target_uri if info.target_uri else file_path
        gfile = Gio.File.new_for_commandline_arg(effective_path)
        uri = gfile.get_uri()
        mtime = info.modified_ts
        mime_type = info.mime_type
        locked = not info.can_write

        # --- 2. HANDLE DIRECTORIES ---
        if info.is_dir:
            base_icon = "folder"
            if locked:
                img = self._get_emblemed_icon(base_icon, "emblem-readonly", target_size)
            else:
                img = self._get_themed_icon(base_icon, target_size)
            self._response.set_image(img)
            return

        # --- 3. GATHER METADATA ---
        # (Using 'info' gathered above)
        
        # --- 4. HANDLE THUMBNAILS (Images, Audio, Video) ---
        thumb_path = ""
        
        # [CRITICAL] DesktopThumbnailFactory is NOT thread-safe for generation.
        # We must wrap the singleton lookup and generation in a mutex.
        with QMutexLocker(ThumbnailProvider._lock):
            thumb_path = factory.lookup(uri, mtime)
            
            if not thumb_path:
                try:
                    # GNOME external thumbnailers can crash or hang, giving us the Segfault
                    # if accessed concurrently from multiple threads.
                    pixbuf = factory.generate_thumbnail(uri, mime_type)
                    if pixbuf:
                        factory.save_thumbnail(pixbuf, uri, mtime)
                        thumb_path = factory.lookup(uri, mtime)
                except Exception as e:
                    print(f"[ThumbnailProvider] GNOME Factory failed to generate thumbnail for {uri}: {e}")
        
        # Load from thumbnail or original
        is_from_cache = False
        img = QImage()
        
        if thumb_path and os.path.exists(thumb_path):
            img = QImage(thumb_path)
            is_from_cache = True
        else:
            # Fallback: Try decoding locally if we have a FUSE path
            # This allows us to read from MTP/SMB mounts without GIO stream complexity
            local_path = gfile.get_path()
            if local_path and os.path.exists(local_path):
                from PySide6.QtGui import QImageReader
                reader = QImageReader(local_path)
                
                # [SAFETY] Always limit decode size for raw files to prevent RAM explosion
                decode_size = requested_size if requested_size.isValid() else target_size
                reader.setScaledSize(decode_size)
                
                read_img = reader.read()
                if not read_img.isNull():
                    img = read_img
        
        if img.isNull():
             # If thumbnailing failed completely, fallback to MIME icon
            img = self._get_mime_icon_from_type(mime_type, target_size)
            
        elif requested_size.isValid() and not is_from_cache:
            from PySide6.QtCore import Qt
            img = img.scaled(requested_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            
        # Add Lock Emblem if needed
        if locked:
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
            gicon = info.get_attribute_object("standard::icon") if info.has_attribute("standard::icon") else None
            
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
    _lock = QMutex() # Thread-safety for the shared factory

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
