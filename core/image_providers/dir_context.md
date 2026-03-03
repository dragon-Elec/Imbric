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
Role: High-performance GNOME-native thumbnail extraction with virtual-URI resolution.

/DNA/: [requestImage(path) -> metadata_utils.get_file_info(path) -> resolve(target_uri)]
/DNA/: [factory.lookup/generate(synchronized via QMutex) -> read() => QImage]
/DNA/: [Fallback: if(thumbnail_fail) -> resolve_mime_icon() => QImage]

- SrcDeps: core.metadata_utils
- SysDeps: gi.repository (Gio, GLib, GnomeDesktop), PySide6.QtQuick, PySide6.QtGui

API:
  - [ThumbnailProvider](./thumbnail_provider.py#L25)(QQuickAsyncImageProvider): Thread-safe integration with `GnomeDesktop.DesktopThumbnailFactory`.
!Caveat: `DesktopThumbnailFactory` is NOT thread-safe for concurrent generation; the provider uses a static `QMutex` to serialize calls across all worker threads.
!Feature: Transparently resolves `recent:///` and `trash:///` virtual URIs to their physical targets via GIO's `standard::target-uri`.
