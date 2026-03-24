"""
GNOME Thumbnail Provider - Uses GnomeDesktop.DesktopThumbnailFactory.
Moved from core/image_providers/thumbnail_provider.py
"""

import gi

gi.require_version("GnomeDesktop", "3.0")
from gi.repository import GnomeDesktop, GLib, Gio

from PySide6.QtQuick import QQuickAsyncImageProvider, QQuickImageResponse
from PySide6.QtGui import QImage, QIcon
from PySide6.QtCore import QSize, QRunnable, QThreadPool, QMutex, QMutexLocker

import os
from core.backends.gio.metadata import get_file_info


class ThumbnailResponse(QQuickImageResponse):
    def __init__(self, path: str, requested_size: QSize, factory):
        super().__init__()
        self._image = QImage()
        self._path = path
        self._requested_size = requested_size
        self._factory = factory

        runnable = ThumbnailRunnable(self)
        QThreadPool.globalInstance().start(runnable)

    def textureFactory(self):
        from PySide6.QtQuick import QQuickTextureFactory

        return QQuickTextureFactory.textureFactoryForImage(self._image)

    def set_image(self, image: QImage):
        self._image = image
        self.finished.emit()

    def errorString(self):
        return ""


class ThumbnailRunnable(QRunnable):
    _mime_icon_cache = {}

    def __init__(self, response: ThumbnailResponse):
        super().__init__()
        self._response = response
        self.setAutoDelete(True)

    def run(self):
        file_path = self._response._path
        requested_size = self._response._requested_size
        factory = self._response._factory

        target_size = requested_size if requested_size.isValid() else QSize(256, 256)

        info = get_file_info(file_path)
        if not info:
            img = self._get_emblemed_icon(
                "emblem-unreadable", "emblem-unreadable", target_size
            )
            self._response.set_image(img)
            return

        effective_path = info.target_uri if info.target_uri else file_path
        gfile = Gio.File.new_for_commandline_arg(effective_path)
        uri = gfile.get_uri()
        mtime = info.modified_ts
        mime_type = info.mime_type
        locked = not info.can_write

        if info.is_dir:
            base_icon = "folder"
            if locked:
                img = self._get_emblemed_icon(base_icon, "emblem-readonly", target_size)
            else:
                img = self._get_themed_icon(base_icon, target_size)
            self._response.set_image(img)
            return

        thumb_path = ""

        with QMutexLocker(ThumbnailProvider._lock):
            thumb_path = factory.lookup(uri, mtime)

            if not thumb_path:
                try:
                    pixbuf = factory.generate_thumbnail(uri, mime_type)
                    if pixbuf:
                        factory.save_thumbnail(pixbuf, uri, mtime)
                        thumb_path = factory.lookup(uri, mtime)
                except Exception as e:
                    pass

        is_from_cache = False
        img = QImage()

        if thumb_path and os.path.exists(thumb_path):
            img = QImage(thumb_path)
            is_from_cache = True
        else:
            local_path = gfile.get_path()
            if local_path and os.path.exists(local_path):
                from PySide6.QtGui import QImageReader

                reader = QImageReader(local_path)
                decode_size = (
                    requested_size if requested_size.isValid() else target_size
                )
                reader.setScaledSize(decode_size)
                read_img = reader.read()
                if not read_img.isNull():
                    img = read_img

        if img.isNull():
            img = self._get_mime_icon_from_type(mime_type, target_size)

        elif requested_size.isValid() and not is_from_cache:
            from PySide6.QtCore import Qt

            img = img.scaled(
                requested_size, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )

        if locked:
            img = self._overlay_emblem(img, "emblem-readonly", target_size)

        self._response.set_image(img)

    def _get_mime_icon_from_type(self, mime_type: str, target_size: QSize) -> QImage:
        try:
            gicon = Gio.content_type_get_icon(mime_type)

            if gicon:
                if hasattr(gicon, "get_names"):
                    for name in gicon.get_names():
                        icon = QIcon.fromTheme(name)
                        if not icon.isNull():
                            return icon.pixmap(target_size).toImage()
        except Exception:
            pass

        return self._get_themed_icon("application-x-generic", target_size)

    def _get_themed_icon(self, icon_name: str, target_size: QSize) -> QImage:
        icon = QIcon.fromTheme(icon_name)
        if icon.isNull():
            icon = QIcon.fromTheme("application-x-generic")

        if not icon.isNull():
            return icon.pixmap(target_size).toImage()

        return QImage()

    def _get_mime_icon(self, file_path: str, target_size: QSize) -> QImage:
        try:
            gfile = Gio.File.new_for_path(file_path)
            info = gfile.query_info("standard::icon", Gio.FileQueryInfoFlags.NONE, None)
            gicon = (
                info.get_attribute_object("standard::icon")
                if info.has_attribute("standard::icon")
                else None
            )

            if gicon:
                if hasattr(gicon, "get_names"):
                    icon_names = gicon.get_names()
                    for name in icon_names:
                        icon = QIcon.fromTheme(name)
                        if not icon.isNull():
                            return icon.pixmap(target_size).toImage()
        except Exception:
            pass

        return self._get_themed_icon("application-x-generic", target_size)

    def _get_emblemed_icon(
        self, base_icon_name: str, emblem_icon_name: str, target_size: QSize
    ) -> QImage:
        base_img = self._get_themed_icon(base_icon_name, target_size)
        return self._overlay_emblem(base_img, emblem_icon_name, target_size)

    def _overlay_emblem(
        self, base_image: QImage, emblem_name: str, target_size: QSize
    ) -> QImage:
        from PySide6.QtGui import QPainter, QIcon
        from PySide6.QtCore import Qt

        result = base_image.copy()
        if result.isNull():
            return result

        emblem_size = QSize(target_size.width() // 2, target_size.height() // 2)
        emblem_icon = QIcon.fromTheme(emblem_name)

        if not emblem_icon.isNull():
            emblem_pixmap = emblem_icon.pixmap(emblem_size)

            painter = QPainter(result)
            emblem_x = target_size.width() - emblem_size.width()
            emblem_y = target_size.height() - emblem_size.height()
            painter.drawPixmap(emblem_x, emblem_y, emblem_pixmap)
            painter.end()

        return result


class ThumbnailProvider(QQuickAsyncImageProvider):
    _shared_factory = None
    _lock = QMutex()

    def __init__(self):
        super().__init__()

        if ThumbnailProvider._shared_factory is None:
            ThumbnailProvider._shared_factory = (
                GnomeDesktop.DesktopThumbnailFactory.new(
                    GnomeDesktop.DesktopThumbnailSize.LARGE
                )
            )

        self._factory = ThumbnailProvider._shared_factory

    def requestImageResponse(
        self, id_path: str, requested_size: QSize
    ) -> QQuickImageResponse:
        return ThumbnailResponse(id_path, requested_size, self._factory)
