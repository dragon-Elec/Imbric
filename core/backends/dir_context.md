Identity: core/backends — Concrete backend implementations. Each sub-directory is a self-contained provider for one technology.

!Decision: [Backend-per-subdirectory] - Reason: Isolates GIO, gnome-thumbnailer, and any future backends (MTP, SFTP, liburing) into their own dependency boundaries.

Index:
- gio/ — GIO-based IOBackend, ScannerBackend, MetadataProvider, FileMonitor, VolumesBridge, and all I/O runnables. The default backend for all local and GVfs mounts.
- gnome_thumbnailer/ — QML async image provider using GnomeDesktop.DesktopThumbnailFactory. Implements ThumbnailProviderBackend.
