Identity: core/backends/gnome_thumbnailer — QML async image provider using GnomeDesktop.DesktopThumbnailFactory. Moved from core/image_providers/.

!Pattern: [shared factory + class-level lock] - Reason: `DesktopThumbnailFactory` is not thread-safe; single shared instance guarded by `ThumbnailProvider._lock` (QMutex) serializes `lookup` and `generate_thumbnail` calls.
!Decision: [QQuickAsyncImageProvider > sync] - Reason: Thumbnail generation is blocking I/O; async provider keeps QML render thread unblocked.

---

### [FILE: provider.py] [DONE]
Role: QML async thumbnail provider. Falls back from GNOME cache -> GnomeDesktop.generate -> QImageReader -> MIME icon, in that order.

/DNA/: `ThumbnailProvider.requestImageResponse(path, size)` -> `ThumbnailResponse(path, size, factory)` -> QThreadPool.start(`ThumbnailRunnable`); `ThumbnailRunnable.run()`:
  - get_file_info(path) -> FileInfo
  - if is_dir: get_themed_icon("folder") -> emit finished
  - else: [lock] factory.lookup(uri, mtime) || factory.generate_thumbnail -> save -> lookup [unlock]
  - if thumb_path + exists: QImage(thumb_path)
  - elif local_path: QImageReader.read(scaled)
  - if still null: _get_mime_icon_from_type(mime_type)
  - if locked(can_write=False): _overlay_emblem("emblem-readonly")
  - response.set_image(img) -> em:finished

- SrcDeps: core.backends.gio.metadata
- SysDeps: PySide6{QtQuick, QtGui, QtCore}, gi.repository{GnomeDesktop, GLib, Gio}, os

API:
  - ThumbnailProvider(QQuickAsyncImageProvider):
    - requestImageResponse(id_path: str, requested_size: QSize) -> QQuickImageResponse

  - ThumbnailResponse(QQuickImageResponse):
    - set_image(image: QImage) -> None: sets _image + em:finished
    - textureFactory() -> QQuickTextureFactory
    - errorString() -> str: always ""

  - ThumbnailRunnable(QRunnable):
    Class attr: _mime_icon_cache (dict) — module-level MIME icon caching (no invalidation).

!Caveat: `ThumbnailRunnable._mime_icon_cache` is a class-level dict with no eviction; stays in memory for application lifetime.
!Caveat: `ThumbnailRunnable.run()` references `ThumbnailProvider._lock` directly by class name — coupling between Runnable and Provider for lock access.

---

### [FILE: theme_icons.py] [DONE]
Role: Provides synchronous themed icon rendering for QML (non-async path, for UI chrome icons).

/DNA/: Inspect as needed — small helper module relocated from core/image_providers/theme_provider.py.

- SysDeps: PySide6{QtGui, QtCore}, gi.repository{Gio}
