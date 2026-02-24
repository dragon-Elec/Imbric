"""Desktop integration helpers — open files, launch apps, etc."""

import gi
gi.require_version('Gio', '2.0')
from gi.repository import Gio, GLib


def open_with_default_app(path: str) -> bool:
    """Launch the default application for the given file path/URI."""
    try:
        gfile = Gio.File.new_for_path(path)
        Gio.AppInfo.launch_default_for_uri(gfile.get_uri(), None)
        return True
    except GLib.Error:
        return False
