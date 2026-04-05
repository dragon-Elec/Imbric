Identity: /home/ray/Desktop/files/wrk/Imbric/Imbric/core/backends — Concrete backend implementations. Each sub-directory is a self-contained provider for one technology.

!Decision: [Backend-per-subdirectory] - Reason: Isolates GIO, gnome-thumbnailer, and any future backends (MTP, SFTP, liburing) into their own dependency boundaries.

Index:
- gio/ — GIO-based IOBackend, ScannerBackend, MetadataProvider, FileMonitor (dedicated GLib thread), VolumesBridge, and all I/O runnables. The default backend for all local and GVfs mounts.
- gnome_thumbnailer/ — QML async image provider using GnomeDesktop.DesktopThumbnailFactory. Implements ThumbnailProviderBackend.

Architecture Notes:
- FileMonitor uses a singleton `_GLibThread` (QThread running GLib.MainLoop) for async callback dispatch. This keeps GIO I/O off the Qt main thread while ensuring signals reach the UI.
- DimensionWorker supports virtual paths (MTP, SFTP, GDrive) by streaming the first 64KB via `Gio.File.read()` into `QImageReader` — no full file download needed.
- BackendRegistry supports strict VFS mode (`set_strict_vfs(True)`) which raises RuntimeError on unknown schemes, forcing UI migration away from direct os/pathlib access.
