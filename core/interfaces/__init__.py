"""
Core interfaces - Abstract Base Classes defining backend contracts.
"""

from core.interfaces.io_backend import IOBackend
from core.interfaces.scanner_backend import ScannerBackend
from core.interfaces.thumbnail_provider import ThumbnailProviderBackend
from core.interfaces.metadata_provider import MetadataProvider
from core.interfaces.cache_provider import CacheProvider

__all__ = [
    "IOBackend",
    "ScannerBackend",
    "ThumbnailProviderBackend",
    "MetadataProvider",
    "CacheProvider",
]
