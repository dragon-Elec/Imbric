from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ViewState:
    """
    Pure data model representing the saved UI presentation state for a specific directory.
    This structure is independent of any backend or Qt implementation.
    """

    # Using strings for enums to keep the model completely decoupled from UI types (like SortKey)
    sort_key: Optional[str] = None  # e.g. "NAME", "DATE_MODIFIED", "SIZE", "TYPE"
    sort_ascending: Optional[bool] = None  # True/False
    folders_first: Optional[bool] = None  # True/False
    view_type: Optional[str] = None  # "grid", "list", "compact"
    # zoom_level: Optional[int] = None      # 60, 100, 140
