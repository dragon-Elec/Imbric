"""
GIO helper functions - path/URI utilities using GIO.
"""

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio


def _make_gfile(path_or_uri: str) -> Gio.File:
    """Create Gio.File from local path or URI. Handles both transparently."""
    if "://" in path_or_uri:
        return Gio.File.new_for_uri(path_or_uri)
    return Gio.File.new_for_path(path_or_uri)


def _gfile_path(gfile: Gio.File) -> str:
    """Get usable path string. Returns local path if available, URI otherwise."""
    return gfile.get_path() or gfile.get_uri()


def ensure_uri(path_or_uri: str) -> str:
    """
    Robustly converts a string to a GIO URI.
    Uses Gio.File.new_for_commandline_arg for canonical parsing.
    """
    if not path_or_uri:
        return ""
    return Gio.File.new_for_commandline_arg(path_or_uri).get_uri()


def to_unix_timestamp(dt) -> int:
    """
    Safe convert GLib.DateTime to Unix timestamp (int).
    Returns 0 if None.
    """
    if dt is None:
        return 0
    try:
        return int(dt.to_unix())
    except Exception:
        return 0
