"""
BackendRegistry - Maps mount types / path patterns to backend instances.
Enables backend-agnostic dispatch for future extensibility (liburing, MTP, etc).
"""

from core.interfaces.io_backend import IOBackend
from core.interfaces.scanner_backend import ScannerBackend
from core.interfaces.thumbnail_provider import ThumbnailProviderBackend
from core.interfaces.metadata_provider import MetadataProvider
from core.interfaces.monitor_backend import MonitorBackend
from core.interfaces.device_provider import DeviceProvider
from core.interfaces.metadata_workers import (
    ItemCountWorkerBackend,
    DimensionWorkerBackend,
)
from core.interfaces.search_backend import SearchBackend
from core.models.file_job import FileOperationSignals


class BackendRegistry:
    """Maps mount types / path patterns to backend instances."""

    def __init__(self):
        self._io_signals = FileOperationSignals()
        self._io_backends: dict[str, IOBackend] = {}
        self._scanner_backends: dict[str, ScannerBackend] = {}
        self._thumbnail_backends: list[ThumbnailProviderBackend] = []
        self._metadata_provider: MetadataProvider | None = None
        self._monitor_backend: MonitorBackend | None = None
        self._device_provider: DeviceProvider | None = None
        self._count_worker_cls: type[ItemCountWorkerBackend] | None = None
        self._dimension_worker_cls: type[DimensionWorkerBackend] | None = None
        self._search_backend: SearchBackend | None = None

        self._default_io: IOBackend | None = None
        self._default_scanner: ScannerBackend | None = None

    # -------------------------------------------------------------------------
    # IO Backend Registration
    # -------------------------------------------------------------------------
    def register_io(self, scheme: str, backend: IOBackend) -> None:
        """Register backend for a URI scheme (e.g., 'mtp', 'sftp', 'file')."""
        backend.set_signals(self._io_signals)
        self._io_backends[scheme] = backend

    def set_default_io(self, backend: IOBackend) -> None:
        """Set the default IO backend (typically GIO for local files)."""
        backend.set_signals(self._io_signals)
        self._default_io = backend

    def get_io(self, path_or_uri: str) -> IOBackend | None:
        """Route to the correct IO backend based on path/URI scheme."""
        if "://" in path_or_uri:
            scheme = path_or_uri.split("://")[0]
            if scheme in self._io_backends:
                return self._io_backends[scheme]
        return self._default_io

    def get_io_id(self, path_or_uri: str) -> str:
        """Return the scheme/backend key for a given path. 'default' for the fallback."""
        if "://" in path_or_uri:
            scheme = path_or_uri.split("://")[0]
            if scheme in self._io_backends:
                return scheme
        return "default"

    # -------------------------------------------------------------------------
    # Scanner Backend Registration
    # -------------------------------------------------------------------------
    def register_scanner(self, scheme: str, backend: ScannerBackend) -> None:
        """Register scanner for a URI scheme."""
        self._scanner_backends[scheme] = backend

    def set_default_scanner(self, backend: ScannerBackend) -> None:
        """Set the default scanner backend."""
        self._default_scanner = backend

    def get_scanner(self, path_or_uri: str) -> ScannerBackend | None:
        """Route to the correct scanner backend."""
        if "://" in path_or_uri:
            scheme = path_or_uri.split("://")[0]
            if scheme in self._scanner_backends:
                return self._scanner_backends[scheme]
        return self._default_scanner

    # -------------------------------------------------------------------------
    # Thumbnail Provider Registration
    # -------------------------------------------------------------------------
    def register_thumbnail(self, backend: ThumbnailProviderBackend) -> None:
        """Register a thumbnail provider. Multiple can be registered (tried in order)."""
        self._thumbnail_backends.append(backend)

    def get_thumbnail(self, mime_type: str) -> ThumbnailProviderBackend | None:
        """Get first thumbnail provider that supports the given MIME type."""
        for backend in self._thumbnail_backends:
            if backend.supports(mime_type):
                return backend
        return None

    # -------------------------------------------------------------------------
    # Metadata Provider (single)
    # -------------------------------------------------------------------------
    def set_metadata_provider(self, provider: MetadataProvider) -> None:
        """Set the metadata provider."""
        self._metadata_provider = provider

    def get_metadata(self) -> MetadataProvider | None:
        """Get the metadata provider."""
        return self._metadata_provider

    # -------------------------------------------------------------------------
    # Monitor & Devices
    # -------------------------------------------------------------------------
    def set_monitor_backend(self, backend: MonitorBackend) -> None:
        self._monitor_backend = backend

    def get_monitor(self) -> MonitorBackend | None:
        return self._monitor_backend

    def set_device_provider(self, provider: DeviceProvider) -> None:
        self._device_provider = provider

    def get_devices(self) -> DeviceProvider | None:
        return self._device_provider

    # -------------------------------------------------------------------------
    # Metadata Workers
    # -------------------------------------------------------------------------
    def set_worker_classes(
        self,
        count_cls: type[ItemCountWorkerBackend],
        dim_cls: type[DimensionWorkerBackend],
    ) -> None:
        self._count_worker_cls = count_cls
        self._dimension_worker_cls = dim_cls

    def create_count_worker(self) -> ItemCountWorkerBackend | None:
        return self._count_worker_cls() if self._count_worker_cls else None

    def create_dimension_worker(self) -> DimensionWorkerBackend | None:
        return self._dimension_worker_cls() if self._dimension_worker_cls else None

    def get_io_signals(self):
        """Get the FileOperationSignals hub shared across all backends."""
        return self._io_signals

    # -------------------------------------------------------------------------
    # Search Backend
    # -------------------------------------------------------------------------
    def set_search_backend(self, backend: SearchBackend) -> None:
        self._search_backend = backend

    def get_search(self) -> SearchBackend | None:
        return self._search_backend
