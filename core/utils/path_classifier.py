"""
PathClassifier — Pure utility that categorizes paths by their VFS capabilities.

Replaces scattered startswith() checks across scanner, monitor, and UI layer.
All functions are stateless, thread-safe, and have zero I/O.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PathCapabilities:
    """Immutable capability set for a given path."""

    scheme: str
    is_native: bool
    is_monitorable: bool
    is_writable: bool
    is_virtual: bool

    @property
    def is_local_file(self) -> bool:
        return self.scheme == "file"

    @property
    def is_recent(self) -> bool:
        return self.scheme == "recent"

    @property
    def is_trash(self) -> bool:
        return self.scheme == "trash"


# Schemes that are synthetic and cannot be monitored with Gio.File.monitor_directory().
# trash:// IS monitorable via gvfsd-trash; only recent:// is truly unmonitorable.
_UNMONITORABLE_SCHEMES = frozenset({"recent"})

# Schemes that are read-only from the file manager's perspective.
_READONLY_SCHEMES = frozenset({"recent"})

# Schemes that GIO considers "native" (local filesystem or GVfs-backed).
# Everything else is remote (sftp, dav, mtp, etc.).
_NATIVE_SCHEMES = frozenset({"file", "trash", "recent"})


def classify(path: str) -> PathCapabilities:
    """
    Classify a path string into its VFS capabilities.

    Zero I/O. Pure string analysis. Safe to call from any thread.

    Args:
        path: A POSIX path or URI (e.g. "/home/user", "recent:///", "sftp://host")

    Returns:
        PathCapabilities with scheme, native, monitorable, writable, virtual flags.
    """
    if "://" in path:
        scheme = path.split("://", 1)[0]
    else:
        scheme = "file"

    is_virtual = scheme in _UNMONITORABLE_SCHEMES
    is_native = scheme in _NATIVE_SCHEMES
    is_monitorable = not is_virtual  # GIO can't monitor recent:// or trash://
    is_writable = scheme not in _READONLY_SCHEMES

    return PathCapabilities(
        scheme=scheme,
        is_native=is_native,
        is_monitorable=is_monitorable,
        is_writable=is_writable,
        is_virtual=is_virtual,
    )
