import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

from core.interfaces.view_state_provider import ViewStateProvider
from core.models.view_state import ViewState
from core.utils.path_classifier import classify
from core.backends.gio.helpers import _make_gfile


class GIOViewStateProvider(ViewStateProvider):
    """
    Implements ViewState persistence using GNOME's GVfs metadata daemon.
    This saves UI preferences per-directory (including USB, MTP, Network)
    without polluting the target filesystem with hidden files.
    """

    # GVfs metadata keys
    KEY_SORT_KEY = "metadata::imbric-sort-key"
    KEY_SORT_ASC = "metadata::imbric-sort-asc"
    KEY_FOLDERS_FIRST = "metadata::imbric-folders-first"
    KEY_VIEW_TYPE = "metadata::imbric-view-type"

    # We query all our keys at once
    QUERY_ATTRS = f"{KEY_SORT_KEY},{KEY_SORT_ASC},{KEY_FOLDERS_FIRST},{KEY_VIEW_TYPE}"

    def get_view_state(self, path_or_uri: str) -> ViewState | None:
        """Read state from GVfs metadata."""
        caps = classify(path_or_uri)
        if caps.is_virtual or not caps.is_writable:
            # We don't save state for synthetic paths like recent://
            return None

        try:
            gfile = _make_gfile(path_or_uri)
            info = gfile.query_info(self.QUERY_ATTRS, Gio.FileQueryInfoFlags.NONE, None)

            if not info:
                return None

            # Extract keys
            sort_key = info.get_attribute_string(self.KEY_SORT_KEY)
            view_type = info.get_attribute_string(self.KEY_VIEW_TYPE)

            # For booleans, GVfs metadata often uses strings.
            sort_asc_str = info.get_attribute_string(self.KEY_SORT_ASC)
            sort_asc = (sort_asc_str == "true") if sort_asc_str else None

            folders_first_str = info.get_attribute_string(self.KEY_FOLDERS_FIRST)
            folders_first = (folders_first_str == "true") if folders_first_str else None

            # Only return ViewState if at least one setting was found
            if (
                sort_key
                or sort_asc is not None
                or folders_first is not None
                or view_type is not None
            ):
                return ViewState(
                    sort_key=sort_key,
                    sort_ascending=sort_asc,
                    folders_first=folders_first,
                    view_type=view_type,
                )

            return None

        except GLib.Error as e:
            # Metadata might not be supported on this mount, or file doesn't exist
            print(f"[GIOViewState] Failed to read metadata for {path_or_uri}: {e}")
            return None

    def set_view_state(self, path_or_uri: str, state: ViewState) -> None:
        """Write non-None fields to GVfs metadata."""
        caps = classify(path_or_uri)
        if caps.is_virtual or not caps.is_writable:
            return

        try:
            gfile = _make_gfile(path_or_uri)

            # GIO set_attribute functions are synchronous but fast for metadata
            # We use strings for all values to avoid type mismatch issues across GVfs backends
            if state.sort_key is not None:
                gfile.set_attribute_string(
                    self.KEY_SORT_KEY, state.sort_key, Gio.FileQueryInfoFlags.NONE, None
                )

            if state.sort_ascending is not None:
                val = "true" if state.sort_ascending else "false"
                gfile.set_attribute_string(
                    self.KEY_SORT_ASC, val, Gio.FileQueryInfoFlags.NONE, None
                )

            if state.folders_first is not None:
                val = "true" if state.folders_first else "false"
                gfile.set_attribute_string(
                    self.KEY_FOLDERS_FIRST, val, Gio.FileQueryInfoFlags.NONE, None
                )

            if state.view_type is not None:
                gfile.set_attribute_string(
                    self.KEY_VIEW_TYPE,
                    state.view_type,
                    Gio.FileQueryInfoFlags.NONE,
                    None,
                )

        except GLib.Error as e:
            print(f"[GIOViewState] Failed to write metadata for {path_or_uri}: {e}")
