"""
ViewConfig — Resolves path capabilities into presentation defaults.

Takes PathCapabilities from core and decides:
- Default sort key
- Default sort direction
- Whether folders-first applies
- Thumbnail strategy
- Whether to use streaming layout builds

This is a pure UI concern. Core classifies; UI decides presentation.
"""

from dataclasses import dataclass
from application.services.sorter import SortKey


@dataclass(frozen=True)
class ViewConfig:
    """Presentation defaults for a given path type."""

    default_sort_key: SortKey
    default_ascending: bool
    folders_first: bool
    default_view_type: str  # "grid", "list", "compact"
    skip_thumbnail_precompute: bool
    use_streaming_layout: bool


# Presets by path type
_CONFIGS = {
    "recent": ViewConfig(
        default_sort_key=SortKey.DATE_MODIFIED,
        default_ascending=False,  # most recent first
        folders_first=False,  # Recent mixes files from everywhere; folders-first is meaningless
        default_view_type="list",  # Dense metadata view benefits from list layout
        skip_thumbnail_precompute=True,  # thumbnails are often stale for scattered files
        use_streaming_layout=False,  # Recent is one-shot; no streaming needed
    ),
    "trash": ViewConfig(
        default_sort_key=SortKey.DATE_MODIFIED,
        default_ascending=False,  # most recently trashed first
        folders_first=False,
        default_view_type="list",  # Trash benefits from seeing details
        skip_thumbnail_precompute=False,
        use_streaming_layout=False,
    ),
    "file": ViewConfig(
        default_sort_key=SortKey.NAME,
        default_ascending=True,
        folders_first=True,
        default_view_type="grid",  # Standard file browsing = justified grid
        skip_thumbnail_precompute=False,
        use_streaming_layout=True,
    ),
}


def resolve(path_caps) -> ViewConfig:
    """
    Resolve PathCapabilities into a ViewConfig.

    Falls back to the "file" preset for any unrecognized scheme.
    """
    return _CONFIGS.get(path_caps.scheme, _CONFIGS["file"])
