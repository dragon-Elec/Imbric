"""
Pure utility functions - no GIO, no Qt, no state.
"""

from core.utils.formatting import format_size, unix_mode_to_str
from core.utils.path_ops import (
    _split_name_ext,
    generate_candidate_path,
    build_conflict_payload,
)

__all__ = [
    "format_size",
    "unix_mode_to_str",
    "_split_name_ext",
    "generate_candidate_path",
    "build_conflict_payload",
]
