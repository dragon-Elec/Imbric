from PySide6.QtCore import QObject, Slot, Signal, Property


class ContextMenuViewModel(QObject):
    """
    ViewModel handling state and data formatting for the GTK Mimic Context Menu.
    This decouples UI presentation data from the core bridge layer.
    """

    def __init__(self, main_window):
        super().__init__(main_window)
        self.mw = main_window

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

        try:
            enum_id = ShortcutAction[action_id]
            act = self.mw.action_manager.get_action(enum_id)
            if act:
                act.trigger()
        except KeyError:
            print(f"[ContextMenuViewModel] Unknown action ID: {action_id}")
