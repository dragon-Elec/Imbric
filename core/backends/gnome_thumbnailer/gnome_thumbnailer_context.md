Identity: /home/ray/Desktop/files/wrk/Imbric/Imbric/core/backends/gnome_thumbnailer — QML async image provider using GnomeDesktop.DesktopThumbnailFactory.

!Pattern: [shared factory + class-level lock] - Reason: `DesktopThumbnailFactory` is not thread-safe; single shared instance guarded by `ThumbnailProvider._lock` (QMutex) serializes `lookup` and `generate_thumbnail` calls.
!Decision: [QQuickAsyncImageProvider > sync] - Reason: Thumbnail generation is blocking I/O; async provider keeps QML render thread unblocked.

Index:
- provider.py — QML async thumbnail provider. Falls back from GNOME cache -> GnomeDesktop.generate -> QImageReader -> MIME icon.
- theme_icons.py — System icon theme integration via QML image://theme/.

---

### [FILE: provider.py] [USABLE]
Role: QML async thumbnail provider via `GnomeDesktop.DesktopThumbnailFactory`. Falls back from GNOME cache -> GnomeDesktop.generate -> QImageReader -> MIME icon.

/DNA/: `ThumbnailProvider.requestImageResponse` -> `ThumbnailResponse` -> `ThumbnailRunnable` [QThreadPool] -> `get_file_info` -> if dir: themed icon | else: `[lock] factory.lookup || factory.generate_thumbnail [unlock]` -> if null: `QImageReader` -> if still null: `_get_mime_icon_from_type` -> `set_image`.

- SrcDeps: core.backends.gio.metadata
- SysDeps: gi.repository{GnomeDesktop, GLib, Gio}, PySide6{QtQuick, QtGui, QtCore}, os

API:
  - ThumbnailProvider(QQuickAsyncImageProvider):
    - requestImageResponse(id_path: str, requested_size: QSize) -> QQuickImageResponse

  - ThumbnailResponse(QQuickImageResponse):
    - set_image(image: QImage) -> None: sets _image + em:finished
    - textureFactory() -> QQuickTextureFactory
    - errorString() -> str: always ""

  - ThumbnailRunnable(QRunnable):
    Class attr: _mime_icon_cache (dict) — module-level MIME icon caching (no invalidation).
    - run() -> None

!Caveat: `ThumbnailRunnable._mime_icon_cache` is a class-level dict with no eviction.
!Caveat: `ThumbnailRunnable.run()` references `ThumbnailProvider._lock` directly by class name.

---

### [FILE: theme_icons.py] [USABLE]
Role: Themed icon provider for QML `image://theme/`. Provides synchronous themed icon rendering for QML.

/DNA/: `requestPixmap(id, size, requestedSize)` -> if "/" in id: `Gio.content_type_get_icon` -> `QIcon.fromTheme` | else: `QIcon.fromTheme(id)` -> `icon.pixmap`.

- SysDeps: PySide6{QtQuick, QtGui, QtCore}, gi.repository{Gio}

API:
  - ThemeImageProvider(QQuickImageProvider):
    - requestPixmap(id: str, size: QSize, requestedSize: QSize) -> QPixmap
