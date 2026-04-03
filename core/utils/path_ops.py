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
    Uses vfs_path helpers for URI-safe splitting.
    """
    if counter == 0:
        return base_path

    from core.utils.vfs_path import vfs_basename, vfs_dirname, vfs_join

    filename = vfs_basename(base_path)
    dir_path = vfs_dirname(base_path)
    if not filename:
        return base_path

    name, ext = _split_name_ext(filename)

    if style == "copy":
        suffix = " (Copy)" if counter == 1 else f" (Copy {counter})"
    else:
        suffix = f" ({counter})"

    return vfs_join(dir_path, f"{name}{suffix}{ext}")


from core.utils.vfs_path import vfs_basename, vfs_dirname, vfs_join

def build_dest_path(src: str, dest_dir: str) -> str:
    """Build full dest path: dest_dir/basename(src)."""
    return vfs_join(dest_dir, vfs_basename(src))


def build_renamed_dest(dest: str, new_name: str) -> str:
    """Replace filename in dest with new_name."""
    if not new_name:
        return dest
    parent = vfs_dirname(dest)
    return vfs_join(parent, new_name)


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
