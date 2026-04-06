from PySide6.QtCore import QObject, Slot, Signal, Property
from ui.services.sorter import SortKey
from core.models.view_state import ViewState


class ContextMenuViewModel(QObject):
    """
    ViewModel handling state and data formatting for the GTK Mimic Context Menu.
    This decouples UI presentation data from the core bridge layer.
    """

    def __init__(self, main_window):
        super().__init__(main_window)
        self.mw = main_window

    def _get_current_sorter(self):
        """Get the Sorter from the currently active pane."""
        shell = self.mw.shell_manager
        pane = shell.current_pane
        if pane:
            sorter = pane.row_builder.getSorter()
            print(f"[ContextMenuViewModel] Got sorter from active pane: {sorter}")
            return sorter
        print(f"[ContextMenuViewModel] No active pane found")
        return None

    def _build_sort_submenu(self):
        """Build the Sort By submenu model."""
        sorter = self._get_current_sorter()
        if not sorter:
            print(f"[ContextMenuViewModel] No sorter, skipping sort submenu")
            return []

        current_key = sorter.currentKey()
        is_ascending = sorter.isAscending()
        is_folders_first = sorter.isFoldersFirst()

        print(
            f"[ContextMenuViewModel] Sort state: key={current_key}, asc={is_ascending}, folders_first={is_folders_first}"
        )

        submenu = []

        # Sort by options (mutually exclusive - only one checked at a time)
        for key in SortKey:
            is_checked = key.value == current_key
            print(
                f"[ContextMenuViewModel] Sort option: {key.name} checked={is_checked}"
            )
            submenu.append(
                {
                    "id": f"SORT_KEY_{key.name}",
                    "text": key.name.replace("_", " ").title(),
                    "icon": "view-sort-ascending-symbolic" if is_checked else "",
                    "checkable": True,
                    "checked": is_checked,
                    "is_radio": True,
                }
            )

        submenu.append({"type": "separator"})

        # Ascending/Descending toggle
        submenu.append(
            {
                "id": "SORT_ASCENDING",
                "text": "Ascending",
                "icon": "view-sort-ascending-symbolic" if is_ascending else "",
                "checkable": True,
                "checked": is_ascending,
            }
        )

        # Folders First toggle
        submenu.append(
            {
                "id": "SORT_FOLDERS_FIRST",
                "text": "Folders First",
                "icon": "folder-symbolic" if is_folders_first else "",
                "checkable": True,
                "checked": is_folders_first,
            }
        )

        return submenu

    def _build_view_submenu(self):
        """Build the View As submenu model."""
        shell = self.mw.shell_manager
        pane = shell.current_pane
        if not pane:
            return []

        row_builder = pane.row_builder
        if not row_builder:
            return []

        current_view = row_builder.getCurrentViewType()

        submenu = []
        for view_type in ("grid", "list", "compact"):
            is_checked = view_type == current_view
            is_enabled = view_type == "grid"
            submenu.append(
                {
                    "id": f"VIEW_TYPE_{view_type.upper()}",
                    "text": view_type.capitalize(),
                    "icon": "view-grid-symbolic" if is_checked else "",
                    "checkable": True,
                    "checked": is_checked,
                    "enabled": is_enabled,
                    "is_radio": True,
                }
            )

        return submenu

    @Slot(list, result=list)
    def getModelForPaths(self, paths):
        """
        Generates a model (list of dicts) for GtkActionMenu.
        If paths is empty, returns background context menu.
        """
        from ui.models.shortcuts import ShortcutAction

        am = self.mw.action_manager
        fm = self.mw.file_manager
        is_single = len(paths) == 1
        model = []

        if not paths:
            # --- Background Context Menu ---
            paste_act = am.get_action(ShortcutAction.PASTE)
            icon_name = paste_act.icon().name()
            if icon_name and not icon_name.endswith("-symbolic"):
                icon_name += "-symbolic"
            model.append(
                {
                    "id": ShortcutAction.PASTE.name,
                    "text": paste_act.text(),
                    "icon": icon_name,
                    "shortcut": paste_act.shortcut().toString(),
                    "enabled": fm.get_clipboard_files() != [],
                }
            )
            model.append({"type": "separator"})

            new_folder_act = am.get_action(ShortcutAction.NEW_FOLDER)
            icon_name = new_folder_act.icon().name()
            if icon_name and not icon_name.endswith("-symbolic"):
                icon_name += "-symbolic"
            model.append(
                {
                    "id": ShortcutAction.NEW_FOLDER.name,
                    "text": new_folder_act.text(),
                    "icon": icon_name,
                    "shortcut": new_folder_act.shortcut().toString(),
                    "enabled": True,
                }
            )

            model.append({"type": "separator"})

            # Sort By submenu
            sort_submenu = self._build_sort_submenu()
            if sort_submenu:
                model.append(
                    {
                        "text": "Sort By",
                        "icon": "view-sort-ascending-symbolic",
                        "submenu": sort_submenu,
                    }
                )

            # View As submenu
            view_submenu = self._build_view_submenu()
            if view_submenu:
                model.append(
                    {
                        "text": "View As",
                        "icon": "view-grid-symbolic",
                        "submenu": view_submenu,
                    }
                )
        else:
            # --- File/Folder Context Menu ---
            if is_single:
                model.append(
                    {
                        "id": "OPEN_NATIVE",
                        "text": "Open",
                        "icon": "document-open-symbolic",
                        "enabled": True,
                    }
                )
                model.append({"type": "separator"})

            # Standard Actions
            for action_enum in [
                ShortcutAction.COPY,
                ShortcutAction.CUT,
                ShortcutAction.PASTE,
            ]:
                act = am.get_action(action_enum)
                enabled = True
                if action_enum == ShortcutAction.PASTE:
                    enabled = fm.get_clipboard_files() != []
                icon_name = act.icon().name()
                if icon_name and not icon_name.endswith("-symbolic"):
                    icon_name += "-symbolic"

                model.append(
                    {
                        "id": action_enum.name,
                        "text": act.text(),
                        "icon": icon_name,
                        "shortcut": act.shortcut().toString(),
                        "enabled": enabled,
                    }
                )

            model.append({"type": "separator"})

            if is_single:
                rename_act = am.get_action(ShortcutAction.RENAME)
                icon_name = rename_act.icon().name()
                if icon_name and not icon_name.endswith("-symbolic"):
                    icon_name += "-symbolic"
                model.append(
                    {
                        "id": ShortcutAction.RENAME.name,
                        "text": rename_act.text(),
                        "icon": icon_name,
                        "shortcut": rename_act.shortcut().toString(),
                        "enabled": True,
                    }
                )
                model.append({"type": "separator"})

            trash_act = am.get_action(ShortcutAction.TRASH)
            icon_name = trash_act.icon().name()
            if icon_name and not icon_name.endswith("-symbolic"):
                icon_name += "-symbolic"
            model.append(
                {
                    "id": ShortcutAction.TRASH.name,
                    "text": trash_act.text(),
                    "icon": icon_name,
                    "shortcut": trash_act.shortcut().toString(),
                    "enabled": True,
                }
            )

        return model

    @Slot(str, list)
    def executeAction(self, action_id, paths):
        """
        Executes an action from GtkActionMenu.
        """
        from ui.models.shortcuts import ShortcutAction
        from core.backends.gio.desktop import open_with_default_app as _open_file

        if action_id == "OPEN_NATIVE" and paths:
            _open_file(paths[0])
            return

        # Sort actions
        if action_id.startswith("SORT_KEY_"):
            key_name = action_id[len("SORT_KEY_") :]
            try:
                sort_key = SortKey[key_name]
                sorter = self._get_current_sorter()
                if sorter:
                    sorter.setKey(int(sort_key))
                    path = self.mw.shell_manager.current_pane.current_path
                    state = ViewState(sort_key=sort_key.name)
                    self.mw.registry.get_view_state().set_view_state(path, state)
            except KeyError:
                print(f"[ContextMenuViewModel] Unknown sort key: {key_name}")
            return

        if action_id == "SORT_ASCENDING":
            sorter = self._get_current_sorter()
            if sorter:
                new_val = not sorter.isAscending()
                sorter.setAscending(new_val)
                path = self.mw.shell_manager.current_pane.current_path
                state = ViewState(sort_ascending=new_val)
                self.mw.registry.get_view_state().set_view_state(path, state)
            return

        if action_id == "SORT_FOLDERS_FIRST":
            sorter = self._get_current_sorter()
            if sorter:
                new_val = not sorter.isFoldersFirst()
                sorter.setFoldersFirst(new_val)
                path = self.mw.shell_manager.current_pane.current_path
                state = ViewState(folders_first=new_val)
                self.mw.registry.get_view_state().set_view_state(path, state)
            return

        # View type actions
        if action_id.startswith("VIEW_TYPE_"):
            view_type = action_id[len("VIEW_TYPE_") :].lower()
            shell = self.mw.shell_manager
            pane = shell.current_pane
            if pane and pane.row_builder:
                pane.row_builder.setViewType(view_type)
            return

        try:
            enum_id = ShortcutAction[action_id]
            act = self.mw.action_manager.get_action(enum_id)
            if act:
                act.trigger()
        except KeyError:
            print(f"[ContextMenuViewModel] Unknown action ID: {action_id}")
