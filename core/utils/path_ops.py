"""
Pure path operations - no GIO, no Qt.
These helpers work with strings and don't need backend knowledge.
"""

import re


def _split_name_ext(filename: str) -> tuple[str, str]:
    """Split filename into (base, ext). Handles .tar.gz and dotfiles."""
    if filename.endswith(".tar.gz"):
        return filename[:-7], ".tar.gz"
    dot = filename.rfind(".")
    if dot <= 0:
        return filename, ""
    return filename[:dot], filename[dot:]


def generate_candidate_path(base_path: str, counter: int, style: str = "copy") -> str:
    """
    Generate a candidate path for auto-renaming.
    Note: This is a pure string manipulation version. Backend-specific
    versions will need to handle actual Gio.File operations.
    """
    if counter == 0:
        return base_path

    # Extract directory and filename
    # Handle both local paths and URIs
    if "://" in base_path:
        # URI handling - split at last /
        last_slash = base_path.rfind("/")
        if last_slash <= 0:
            return base_path
        dir_path = base_path[: last_slash + 1]
        filename = base_path[last_slash + 1 :]
    else:
        # Local path handling
        last_slash = base_path.rfind("/")
        if last_slash < 0:
            return base_path
        dir_path = base_path[: last_slash + 1]
        filename = base_path[last_slash + 1 :]

    name, ext = _split_name_ext(filename)

    if style == "copy":
        suffix = " (Copy)" if counter == 1 else f" (Copy {counter})"
    else:
        suffix = f" ({counter})"

    return f"{dir_path}{name}{suffix}{ext}"


import os

def build_dest_path(src: str, dest_dir: str) -> str:
    """Build full dest path: dest_dir/basename(src)."""
    return os.path.join(dest_dir, os.path.basename(src))


def build_renamed_dest(dest: str, new_name: str) -> str:
    """Replace filename in dest with new_name."""
    if not new_name:
        return dest
    parent = os.path.dirname(dest)
    return os.path.join(parent, new_name)


def build_conflict_payload(
    src_path, dest_path, src_info=None, dest_info=None, extra_src_data=None
):
    """
    Standardized conflict payload generator.
    Ensures TransactionManager always gets consistent data structure.
    """
    payload = {
        "error": "exists",
        "src_path": src_path,
        "dest_path": dest_path,
        "dest": {"size": dest_info.size, "mtime": dest_info.modified_ts}
        if dest_info
        else {},
        "src": {},
    }

    if src_info and hasattr(src_info, "size"):
        payload["src"] = {"size": src_info.size, "mtime": src_info.modified_ts}

    if extra_src_data:
        payload["src"].update(extra_src_data)

    return payload
