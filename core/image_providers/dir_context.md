# Imbric Core: Image Providers
Role: QML-integrated image providers for dynamic icon and thumbnail resolution.

## Maintenance Rules
- Non-Blocking: QML requests are synchronous on the UI thread unless handled carefully. Ensure quick returns or caching.
- GIO Buffers: Use GIO to read thumbnail files to support network and MTP mounts.

## Atomic Notes (Architectural Truths)
- !Decision: [Request Size > Default Size] - Reason: Requesting exact sizes from GThumbnail reduces downsampling overhead in QML.
- !Rule: [Native Fallback] - Reason: If GnomeDesktop thumbnailing fails, fallback to standard theme icons to avoid empty cells.

## Sub-Directory Index
- None

## Module Audits

### [FILE: [theme_provider.py](./theme_provider.py)] [DONE]
Role: Resolution of system theme icons for non-visual MIME types.

/DNA/: [requestImage(id) -> QIcon.fromTheme(id) -> pixmap() => QImage]

- SrcDeps: None
- SysDeps: PySide6.QtQuick (QQuickImageProvider), PySide6.QtGui (QIcon, QImage)

API:
  - [ThemeImageProvider](./theme_provider.py#L8)(QQuickImageProvider): Maps MIME names to system theme icons.

### [FILE: [thumbnail_provider.py](./thumbnail_provider.py)] [DONE]
Role: High-performance GNOME-native thumbnail extraction.

/DNA/: [requestImage(path) -> gfile.query_info(thumbnail-path) -> if(cached) -> read() => QImage]
/DNA/: [if(!cached) -> factory.generate_thumbnail() -> read() => QImage]

- SrcDeps: core.metadata_utils
- SysDeps: gi.repository (Gio, GLib, GnomeDesktop), PySide6.QtQuick (QQuickImageProvider), PySide6.QtGui (QImage, QPixmap)

API:
  - [ThumbnailProvider](./thumbnail_provider.py#L25)(QQuickImageProvider): Direct integration with `GnomeDesktop.DesktopThumbnailFactory`.
!Caveat: Thumbnail generation is blocking; for large batches, the `FileScanner` pre-queues metadata to trigger the system's background thumbnailer (bubblewrap) first.
