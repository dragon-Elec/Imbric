"""
GIO-specific metadata extraction.
Extracted from core/metadata_utils.py - GIO-dependent functions only.
"""

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

from core.models.file_info import FileInfo
from core.utils.formatting import format_size, unix_mode_to_str
from core.backends.gio.helpers import ensure_uri, to_unix_timestamp


# =============================================================================
# CONSTANTS & GIO ATTRIBUTES
# =============================================================================

GIO_STANDARD_ATTRS = (
    "standard::name,standard::display-name,standard::type,standard::size,"
    "standard::is-hidden,standard::is-symlink,standard::symlink-target,"
    "standard::target-uri,trash::orig-path,trash::deletion-date"
)

GIO_MIME_ATTRS = "standard::content-type,standard::fast-content-type"

GIO_TIME_ATTRS = "time::modified,time::access,time::created"

GIO_ICON_ATTRS = "standard::icon,standard::symbolic-icon"

GIO_ACCESS_ATTRS = (
    "unix::mode,unix::uid,unix::gid,owner::user,owner::group,access::can-write"
)

ATTRS_BASIC = f"{GIO_STANDARD_ATTRS},{GIO_MIME_ATTRS}"
ATTRS_FULL = f"{GIO_STANDARD_ATTRS},{GIO_MIME_ATTRS},{GIO_TIME_ATTRS},{GIO_ACCESS_ATTRS},{GIO_ICON_ATTRS}"


# =============================================================================
# GIO LOGIC
# =============================================================================


def resolve_mime_icon(gfile: Gio.File, cancellable: Gio.Cancellable = None) -> str:
    """
    Resolve the desktop theme icon name for a file using GIO.
    """
    try:
        info = gfile.query_info(
            "standard::icon", Gio.FileQueryInfoFlags.NONE, cancellable
        )

        if info.has_attribute("standard::icon"):
            gicon = info.get_attribute_object("standard::icon")
        else:
            gicon = None
        if gicon:
            if hasattr(gicon, "get_names"):
                names = gicon.get_names()
                if names:
                    return names[0]

    except GLib.Error:
        pass

    return "application-x-generic"


def get_file_info(path_or_uri: str, attributes: str = ATTRS_FULL) -> FileInfo | None:
    """
    Synchronously fetch and populate FileInfo for a path or URI.
    """
    gfile = Gio.File.new_for_commandline_arg(path_or_uri)

    try:
        info = gfile.query_info(
            attributes, Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS, None
        )

        uri = gfile.get_uri()
        path = gfile.get_path() or uri

        _raw = info.get_attribute_byte_string("standard::name")
        name = (
            (_raw.decode("utf-8", "replace") if isinstance(_raw, bytes) else _raw)
            if _raw
            else ""
        )
        display_name = info.get_attribute_string("standard::display-name") or name
        size = info.get_attribute_uint64("standard::size")

        type_val = info.get_attribute_uint32("standard::type")
        file_type = type_val if type_val else Gio.FileType.REGULAR
        is_dir = file_type == Gio.FileType.DIRECTORY
        is_symlink = info.get_attribute_boolean("standard::is-symlink")
        is_hidden = info.get_attribute_boolean("standard::is-hidden")

        symlink_target = (
            (info.get_attribute_string("standard::symlink-target") or "")
            if is_symlink
            else ""
        )

        mime_type = (
            info.get_attribute_string("standard::content-type")
            or "application/octet-stream"
        )

        icon_name = "application-x-generic"
        if info.has_attribute("standard::icon"):
            gicon = info.get_attribute_object("standard::icon")
            if gicon and hasattr(gicon, "get_names"):
                names = gicon.get_names()
                if names:
                    icon_name = names[0]

        m_time = (
            to_unix_timestamp(info.get_modification_date_time())
            if info.has_attribute("time::modified")
            else 0
        )
        a_time = (
            to_unix_timestamp(info.get_access_date_time())
            if info.has_attribute("time::access")
            else 0
        )
        c_time = (
            to_unix_timestamp(info.get_creation_date_time())
            if info.has_attribute("time::created")
            else 0
        )

        mode = info.get_attribute_uint32("unix::mode")
        perm_str = unix_mode_to_str(mode)

        owner = info.get_attribute_string("owner::user") or str(
            info.get_attribute_uint32("unix::uid")
        )
        group = info.get_attribute_string("owner::group") or str(
            info.get_attribute_uint32("unix::gid")
        )

        can_write = (
            info.get_attribute_boolean("access::can-write")
            if info.has_attribute("access::can-write")
            else True
        )
        target_uri = info.get_attribute_string("standard::target-uri") or ""
        trash_orig = info.get_attribute_byte_string("trash::orig-path") or ""
        trash_date = info.get_attribute_string("trash::deletion-date") or ""

        return FileInfo(
            path=path,
            uri=uri,
            name=name,
            display_name=display_name,
            size=size,
            size_human=format_size(size),
            is_dir=is_dir,
            is_symlink=is_symlink,
            symlink_target=symlink_target,
            is_hidden=is_hidden,
            mime_type=mime_type,
            icon_name=icon_name,
            modified_ts=m_time,
            accessed_ts=a_time,
            created_ts=c_time,
            mode=mode,
            permissions_str=perm_str,
            owner=owner,
            group=group,
            can_write=can_write,
            target_uri=target_uri,
            trash_orig_path=trash_orig,
            trash_deletion_date=trash_date,
        )

    except GLib.Error:
        return None
