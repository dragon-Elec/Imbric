"""
Theme Icon Provider - System icon theme integration via QML image://theme/.
Moved from core/image_providers/theme_provider.py
"""

from PySide6.QtQuick import QQuickImageProvider
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtCore import QSize


class ThemeImageProvider(QQuickImageProvider):
    """
    Image provider that resolves freedesktop icon names to themed pixmaps.
    Uses QQuickPixmapCache for efficient RAM sharing across delegates.
    """

    def __init__(self):
        super().__init__(QQuickImageProvider.Pixmap)

    def requestPixmap(self, id: str, size: QSize, requestedSize: QSize):
        target_size = requestedSize if requestedSize.isValid() else QSize(128, 128)

        icon = QIcon()

        if "/" in id:
            from gi.repository import Gio

            gicon = Gio.content_type_get_icon(id)
            if gicon and hasattr(gicon, "get_names"):
                for name in gicon.get_names():
                    if QIcon.hasThemeIcon(name):
                        icon = QIcon.fromTheme(name)
                        break
        else:
            if QIcon.hasThemeIcon(id):
                icon = QIcon.fromTheme(id)

        if icon.isNull():
            icon = QIcon.fromTheme("application-x-generic")

        return icon.pixmap(target_size)
