"""
GNOME Thumbnailer Backend - Thumbnail and theme icon providers.
"""

from core.backends.gnome_thumbnailer.provider import ThumbnailProvider
from core.backends.gnome_thumbnailer.theme_icons import ThemeImageProvider

__all__ = [
    "ThumbnailProvider",
    "ThemeImageProvider",
]
