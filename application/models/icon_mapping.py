"""
Icon Mapping — Maps internal action names to Material Symbols ligatures.
"""

ICON_MAP = {
    # File Operations
    "COPY": "content_copy",
    "CUT": "content_cut",
    "PASTE": "content_paste",
    "TRASH": "delete",
    "RENAME": "edit",
    "DUPLICATE": "content_copy",
    "NEW_FOLDER": "create_new_folder",
    "DELETE_PERMANENT": "delete_forever",
    # History
    "UNDO": "undo",
    "REDO": "redo",
    # Navigation
    "GO_UP": "arrow_upward",
    "GO_BACK": "arrow_back",
    "GO_FORWARD": "arrow_forward",
    "GO_HOME": "home",
    "REFRESH": "refresh",
    "FIND": "search",
    # View Controls
    "TOGGLE_HIDDEN": "visibility_off",
    "ZOOM_IN": "zoom_in",
    "ZOOM_OUT": "zoom_out",
    "ZOOM_RESET": "zoom_in",  # or "image"
    "SELECT_ALL": "select_all",
    # Tab Management
    "NEW_TAB": "add",
    "CLOSE_TAB": "close",
    "EDIT": "edit",
    # Sidebar Categories
    "FAVORITES": "star",
    "DRIVES": "storage",
    "NETWORK": "cloud",
    "TRASH_BIN": "delete",
    "RECENT": "schedule",
    "DOCUMENTS": "description",
    "PICTURES": "image",
    "VIDEOS": "movie",
    "MUSIC": "music_note",
    "DOWNLOADS": "download",
}


def get_ligature(action_name: str) -> str:
    """Returns the MD3 ligature for a given internal action name."""
    return ICON_MAP.get(action_name, "help_outline")
