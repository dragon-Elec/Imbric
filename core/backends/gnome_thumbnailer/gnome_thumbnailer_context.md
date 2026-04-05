Identity: /Imbric/core/backends/gnome_thumbnailer - QML async thumbnail and themed icon providers leveraging GnomeDesktop.

Rules:
- [Factory Synchronization] DesktopThumbnailFactory is NOT thread-safe; all access MUST be serialized via `ThumbnailProvider._lock` (QMutex).

Atomic Notes:
- !Decision: [QQuickAsyncImageProvider > Sync] - Reason: Generation is blocking; async provider keeps QML render thread responsive.
- !Pattern: [Tiered Fallback] - Reason: GNOME cache -> GnomeDesktop loop -> QImageReader (local only) -> MIME icon providing best-effort visual parity.

Index:
- None

Audits:

### [FILE: provider.py] [USABLE]
Role: QML async image provider using `GnomeDesktop` for standard thumbnails and local reader fallbacks.

/DNA/: [ThumbnailProvider.requestImageResponse -> ThumbnailResponse -> ThumbnailRunnable (QThreadPool) -> Metadata lookup -> {lock}factory.lookup/generate{unlock} -> QImageReader (local) -> MIME icon => set_image]

- SrcDeps: core.registry.BackendRegistry
- SysDeps: gi.repository{GnomeDesktop, GLib, Gio}, PySide6.QtQuick{QQuickAsyncImageProvider, QQuickImageResponse}, PySide6.QtGui{QImage, QIcon}, PySide6.QtCore{QSize, QRunnable, QThreadPool, QMutex, QMutexLocker}, os

API:
  - ThumbnailProvider(QQuickAsyncImageProvider):
    - requestImageResponse(id_path: str, requested_size: QSize) -> QQuickImageResponse
  - ThumbnailResponse(QQuickImageResponse):
    - set_image(image: QImage) -> None: sets private image and emits finished.
    - textureFactory() -> QQuickTextureFactory: wraps QImage for QML rendering.
    - errorString() -> str: returns empty string.
  - ThumbnailRunnable(QRunnable):
    - run(): executes the tiered lookup and generation fallbacks.
!Caveat: `ThumbnailRunnable._mime_icon_cache` is a class-level stub, currently unused.
!Caveat: `ThumbnailProvider._lock` must be used for both `lookup` and `generate_thumbnail` calls.

### [FILE: theme_icons.py] [USABLE]
Role: Synchronous QML image provider (`image://theme/`) for system icon lookup.

/DNA/: [requestPixmap(id, size) -> if(MIME in id): Gio.content_type_get_icon -> QIcon.fromTheme | else: QIcon.fromTheme(id) => QPixmap]

- SrcDeps: None
- SysDeps: PySide6.QtQuick.QQuickImageProvider, PySide6.QtGui{QIcon, QPixmap}, PySide6.QtCore.QSize, gi.repository.Gio

API:
  - ThemeImageProvider(QQuickImageProvider):
    - requestPixmap(id: str, size: QSize, requestedSize: QSize) -> QPixmap: resolves icon name or MIME type to themed pixmap.
