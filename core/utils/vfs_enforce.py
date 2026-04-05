"""
VFS enforcement helpers.

These utilities force the UI layer to go through the BackendRegistry
instead of using direct os/pathlib access for file operations.

Usage:
    from core.utils.vfs_enforce import require_vfs_path

    # Raises RuntimeError if path bypasses VFS routing
    require_vfs_path(user_path, registry)
"""


def normalize_to_uri(path: str) -> str:
    """
    Convert a plain POSIX path to a file:// URI if it doesn't already have a scheme.
    This ensures consistent scheme detection in the Registry.
    """
    if "://" in path:
        return path
    return f"file://{path}"


def require_vfs_path(path: str, registry, operation: str = "file operation") -> None:
    """
    Assert that a valid backend exists for the given path.
    Raises RuntimeError if no backend is registered for the path's scheme.

    Use this in UI code to catch VFS bypasses early.
    """
    uri = normalize_to_uri(path)
    backend = registry.get_io(uri)
    if backend is None:
        schemes = registry.get_registered_schemes()
        raise RuntimeError(
            f"VFS violation: {operation} on '{path}' has no registered backend. "
            f"Registered schemes: {schemes}. "
            f"All file operations must route through BackendRegistry."
        )


def is_vfs_routable(path: str, registry) -> bool:
    """
    Check if a path can be routed through the VFS without raising.
    Returns True if a backend exists for the path's scheme.
    """
    uri = normalize_to_uri(path)
    return registry.get_io(uri) is not None
