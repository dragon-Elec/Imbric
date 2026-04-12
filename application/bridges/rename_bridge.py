from PySide6.QtCore import QObject, Signal, Slot
from application.services.conflict_resolver import ConflictResolver
from application.dialogs.conflicts import ConflictAction
from core.threading.worker_pool import AsyncWorkerPool


class RenameBridge(QObject):
    renameCompleted = Signal(str, str)

    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window

        self._rename_pool = AsyncWorkerPool(max_concurrent=1, parent=self)
        self._rename_pool.resultReady.connect(self._on_rename_assessed)

    @Slot(str, str)
    def renameFile(self, old_path: str, new_name: str):
        if not old_path or not new_name:
            return

        print(
            f"[RenameBridge] Enqueueing rename assessment for '{old_path}' -> '{new_name}'"
        )
        self._rename_pool.enqueue(
            f"rename_{old_path}",
            self._assess_rename_task,
            priority=10,
            old_path=old_path,
            new_name=new_name,
        )

    @staticmethod
    def _assess_rename_task(old_path: str, new_name: str):
        from gi.repository import Gio

        try:
            gfile = Gio.File.parse_name(old_path)
            parent = gfile.get_parent()
            if not parent:
                return None

            new_gfile = parent.get_child(new_name)
            new_path = new_gfile.get_path() or new_gfile.get_uri()

            if old_path == new_path:
                return {"skip": True}

            return {
                "skip": False,
                "old_path": old_path,
                "new_path": new_path,
                "new_name": new_name,
            }
        except Exception as e:
            print(f"[RenameBridge] Background rename assessment failed: {e}")
            return None

    def _on_rename_assessed(self, task_id: str, result):
        if not task_id.startswith("rename_") or not result:
            return

        if result.get("skip"):
            return

        old_path = result["old_path"]
        new_path = result["new_path"]
        new_name = result["new_name"]

        resolver = ConflictResolver(self.mw)
        action, final_dest = resolver.resolve_rename(old_path, new_path)

        if action == ConflictAction.CANCEL or action == ConflictAction.SKIP:
            return

        from gi.repository import Gio

        final_gfile = Gio.File.parse_name(final_dest)
        final_name = final_gfile.get_basename()
        self.mw.file_ops.rename(old_path, final_name)
        self.renameCompleted.emit(old_path, final_dest)
