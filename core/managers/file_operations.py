"""FileOperations — Unified controller for all file I/O (Standard + Trash)."""

import os
from uuid import uuid4

from PySide6.QtCore import (
    QObject,
    Signal,
    Slot,
    QThreadPool,
    QMutex,
    QMutexLocker,
    Qt,
    QRunnable,
)

from core.models import FileJob, FileOperationSignals, TrashItem
from core.registry import BackendRegistry
from core.backends.gio.metadata_workers import UniqueNameWorker, ExistenceWorker
from core.logic.transfer_policy import TransferPolicy, SyncPolicy, ConflictResolution

_MAX_RENAME_ATTEMPTS = 1000


class FileOperations(QObject):
    """Central controller for non-blocking file I/O via QThreadPool."""

    # Unified Signals
    operationStarted = Signal(str, str, str)  # (job_id, op_type, path)
    operationProgress = Signal(str, int, int)  # (job_id, current, total)
    operationFinished = Signal(
        str, str, str, str, bool, str, object
    )  # (tid, job_id, op_type, result_path, success, message, inverse_payload)
    operationError = Signal(
        str, str, str, str, str, object
    )  # (tid, job_id, op_type, path, message, conflict_data)

    # Trash Specific Signals
    itemListed = Signal(object)  # TrashItem
    trashNotSupported = Signal(str, str)  # (path, error)

    # Pre-Flight
    batchAssessmentReady = Signal(str, list, list)  # (tid, valid_items, conflicts)

    # True Batching
    batchProgress = Signal(str, int, int, str)
    batchFinished = Signal(str, list, list)

    uniqueNameReady = Signal(str, str)  # (task_id, unique_path)
    existenceReady = Signal(str, bool)  # (task_id, exists)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent=parent)

        self._undo_manager = None
        self._transaction_manager = None
        self._pool = QThreadPool.globalInstance()
        self._jobs: dict[str, FileJob] = {}
        self._mutex = QMutex()
        self._registry: BackendRegistry | None = None

        self._signals: FileOperationSignals | None = None

        self._unique_name_worker = UniqueNameWorker(self)
        self._unique_name_worker.uniqueNameReady.connect(self.uniqueNameReady)

        self._existence_worker = ExistenceWorker(self)
        self._existence_worker.existenceReady.connect(self.existenceReady)

    def _setup_signals(self):
        """Connect internal signals to public signals. Called after _signals is set."""
        print(f"[FO] _setup_signals: signals={self._signals}")
        if self._signals is None:
            return
        self._signals.started.connect(self.operationStarted)
        self._signals.progress.connect(self.operationProgress)
        self._signals.finished.connect(self._on_finished)
        self._signals.operationError.connect(self._on_error)
        self._signals.itemListed.connect(self.itemListed)
        self._signals.trashNotSupported.connect(self.trashNotSupported)
        self._signals.batchAssessmentReady.connect(self.batchAssessmentReady)

        # True Batching Signals
        self._signals.batchProgress.connect(self.batchProgress)
        self._signals.batchFinished.connect(self._on_batch_finished)
        self._signals.batchConflictEncountered.connect(self.operationError)

    # -------------------------------------------------------------------------
    # SIGNAL HANDLERS
    # -------------------------------------------------------------------------
    def _on_batch_finished(self, tid: str, success_list: list, failed_list: list):
        # Process results on main thread to avoid signal storms
        for item in success_list:
            self._on_finished(
                tid,
                item["job_id"],
                item["op_type"],
                item["result_path"],
                True,
                "Success",
            )

        for item in failed_list:
            # Re-emit errors and mark as finished
            self._on_error(
                tid, item["job_id"], item["op_type"], item["src"], item["error"], None
            )
            self._on_finished(
                tid, item["job_id"], item["op_type"], item["src"], False, item["error"]
            )

        self.batchFinished.emit(tid, success_list, failed_list)

    @Slot(str, str, str, str, bool, str, object)
    def _on_finished(
        self,
        tid: str,
        job_id: str,
        op_type: str,
        result_path: str,
        success: bool,
        message: str,
        inv_payload=None,
    ):
        print(f"[FO] _on_finished: tid={tid[:8]}, jid={job_id[:8]}")
        with QMutexLocker(self._mutex):
            if job_id in self._jobs:
                del self._jobs[job_id]

        self.operationFinished.emit(
            tid, job_id, op_type, result_path, success, message, inv_payload
        )

    @Slot(str, str, str, str, str, object)
    def _on_error(
        self,
        tid: str,
        job_id: str,
        op_type: str,
        path: str,
        message: str,
        conflict_data: object,
    ):
        self.operationError.emit(tid, job_id, op_type, path, message, conflict_data)

    # -------------------------------------------------------------------------
    # PUBLIC API
    # -------------------------------------------------------------------------

    def setTransactionManager(self, tm):
        self._transaction_manager = tm

    def setUndoManager(self, undo_manager):
        self._undo_manager = undo_manager

    def setRegistry(self, registry: BackendRegistry):
        self._registry = registry
        signals = registry.get_io_signals()
        if signals:
            self._signals = signals
            self._setup_signals()

    def _create_job(
        self,
        op_type: str,
        source: str,
        dest: str = "",
        tid: str = "",
        overwrite: bool = False,
        rename_to: str = "",
        policy: SyncPolicy | None = None,
    ) -> FileJob:
        # [FIX] Generate ID first, then register with TransactionManager
        job_id = str(uuid4())

        if tid and self._transaction_manager:
            self._transaction_manager.addOperation(tid, op_type, source, dest, job_id)

        return FileJob(
            id=job_id,
            op_type=op_type,
            source=source,
            dest=dest,
            transaction_id=tid,
            overwrite=overwrite,
            rename_to=rename_to,
            policy=policy,
        )

    def _submit(self, job: FileJob, backend_method) -> str:
        with QMutexLocker(self._mutex):
            self._jobs[job.id] = job
        if self._registry:
            job.backend_id = self._registry.get_io_id(job.source)
        return backend_method(job)

    @Slot(str, str, str, bool, bool, object, result=str)
    def copy(
        self,
        source_path: str,
        dest_path: str,
        transaction_id: str = "",
        overwrite: bool = False,
        auto_rename: bool = False,
        policy: SyncPolicy | None = None,
    ) -> str:
        assert self._registry
        job = self._create_job(
            "copy", source_path, dest_path, transaction_id, overwrite, policy=policy
        )
        job.auto_rename = auto_rename
        backend = self._registry.get_io(source_path)
        return self._submit(job, backend.copy)

    @Slot(str, str, str, bool, object, result=str)
    def move(
        self,
        source_path: str,
        dest_path: str,
        transaction_id: str = "",
        overwrite: bool = False,
        policy: SyncPolicy | None = None,
    ) -> str:
        assert self._registry
        job = self._create_job(
            "move", source_path, dest_path, transaction_id, overwrite, policy=policy
        )
        backend = self._registry.get_io(source_path)
        return self._submit(job, backend.move)

    @Slot(str, str, str, str, bool, bool, object, result=str)
    def transfer(
        self,
        source_path: str,
        dest_path: str,
        mode: str = "auto",
        transaction_id: str = "",
        overwrite: bool = False,
        auto_rename: bool = False,
        policy: SyncPolicy | None = None,
    ) -> str:
        """
        Generic transfer method.
        Mode: "copy", "move", or "auto" (guesses based on filesystem).
        """
        assert self._registry, "Registry must be set before use"
        op_type = mode
        if mode == "auto":
            op_type = "move"

        job = self._create_job(
            op_type, source_path, dest_path, transaction_id, overwrite, policy=policy
        )
        job.auto_rename = auto_rename
        backend = self._registry.get_io(source_path)
        if op_type == "copy":
            return self._submit(job, backend.copy)
        return self._submit(job, backend.move)

    def transfer_batch(
        self,
        transaction_id: str,
        items: list,
        ui_refresh_rate_ms: int = 100,
        halt_on_error: bool = False,
        policy: SyncPolicy | None = None,
    ) -> str:
        """
        True batching: dispatch multiple files in a single background thread.
        """
        if not items:
            return ""

        assert self._registry, "Registry must be set before use"
        job_id = str(uuid4())

        # Route to the backend based on the first item
        first_source = items[0]["src"]

        job = FileJob(
            id=job_id,
            op_type="batch_transfer",
            source=first_source,
            transaction_id=transaction_id,
            items=items,
            ui_refresh_rate_ms=ui_refresh_rate_ms,
            halt_on_error=halt_on_error,
            policy=policy,
        )

        backend = self._registry.get_io(first_source)
        return self._submit(job, backend.batch_transfer)

    def assessBatch(
        self,
        tid: str,
        sources: list,
        dest_dir: str,
        mode: str,
        resolver=None,
        policy: SyncPolicy | None = None,
    ):
        runnable = BatchAssessmentRunnable(
            tid,
            sources,
            dest_dir,
            mode,
            self,
            self._signals,
            resolver=resolver,
            policy=policy,
        )
        self._pool.start(runnable)

    @Slot(str, str, str, result=str)
    def rename(self, path: str, new_name: str, transaction_id: str = "") -> str:
        if not new_name or "/" in new_name or "\\" in new_name or ".." in new_name:
            raise ValueError(
                f"Invalid filename for rename: '{new_name}'. "
                "Must be a valid filename without path separators or '..'."
            )
        if new_name.startswith("."):
            raise ValueError(
                f"Invalid filename for rename: '{new_name}'. Hidden files not allowed via rename."
            )
        job = self._create_job("rename", path, new_name, transaction_id)
        backend = self._registry.get_io(path)
        return self._submit(job, backend.rename)

    @Slot(str, str, bool, result=str)
    def createFolder(
        self, path: str, transaction_id: str = "", auto_rename: bool = False
    ) -> str:
        job = self._create_job("createFolder", path, "", transaction_id)
        job.auto_rename = auto_rename
        backend = self._registry.get_io(path)
        return self._submit(job, backend.create_folder)

    @Slot(str, str, bool, result=str)
    def createFile(
        self, path: str, transaction_id: str = "", auto_rename: bool = False
    ) -> str:
        """Create an empty file at the given path."""
        job = self._create_job("createFile", path, "", transaction_id)
        job.auto_rename = auto_rename
        backend = self._registry.get_io(path)
        return self._submit(job, backend.create_file)

    @Slot(str, str, str, bool, result=str)
    def createSymlink(
        self,
        target: str,
        link_path: str,
        transaction_id: str = "",
        auto_rename: bool = False,
    ) -> str:
        """Create a symbolic link at link_path pointing to target."""
        job = self._create_job("createSymlink", target, link_path, transaction_id)
        job.auto_rename = auto_rename
        backend = self._registry.get_io(link_path)
        return self._submit(job, backend.create_symlink)

    # --- TRASH API ---

    @Slot(str, str, result=str)
    def trash(self, path: str, transaction_id: str = "") -> str:
        job = self._create_job("trash", path, "", transaction_id)
        backend = self._registry.get_io(path)
        return self._submit(job, backend.trash)

    @Slot(list)
    def trashMultiple(self, paths: list):
        """Trash multiple files as a single batch transaction."""
        if not paths:
            return

        # Create a transaction for batch progress aggregation
        tid = ""
        if self._transaction_manager:
            tid = self._transaction_manager.startTransaction(
                f"Trashing {len(paths)} items"
            )

        for path in paths:
            self.trash(path, transaction_id=tid)

        if tid and self._transaction_manager:
            self._transaction_manager.commitTransaction(tid)

    # Updated signature to match what TransactionManager needs
    @Slot(str, str, bool, str, result=str)
    def restore(
        self,
        original_path: str,
        transaction_id: str = "",
        overwrite: bool = False,
        rename_to: str = "",
    ) -> str:
        """Restores file from trash. Source is original path string."""
        job = self._create_job(
            "restore", original_path, "", transaction_id, overwrite, rename_to
        )
        backend = self._registry.get_io(
            original_path
        )  # Restore usually works through destination or default IO
        return self._submit(job, backend.restore)

    @Slot(str, result=str)
    def restore_from_trash(self, original_path_to_restore: str) -> str:
        """Alias for restore() for legacy compatibility."""
        return self.restore(original_path_to_restore)

    @Slot(str, str, str, bool, result=bool)
    def resolve_conflict(
        self, job_id: str, action: str, new_dest: str = "", apply_to_all: bool = False
    ) -> bool:
        """Resolve a conflict encountered during JIT execution."""
        found = False
        if self._registry:
            # We iterate through backends and tell them to resolve the job
            for backend in self._registry._io_backends.values():
                if backend.resolve_conflict(job_id, action, new_dest, apply_to_all):
                    found = True
        return found

    @Slot(result=str)
    def listTrash(self) -> str:
        assert self._registry
        job = self._create_job("list", "")
        backend = self._registry.get_io("trash:///")
        return self._submit(job, backend.list_trash)

    @Slot(result=str)
    def emptyTrash(self) -> str:
        assert self._registry
        job = self._create_job("empty", "")
        backend = self._registry.get_io("trash:///")
        return self._submit(job, backend.empty_trash)

    @Slot(dict, result=str)
    def execute_inverse_payload(self, payload: dict) -> str:
        """Executes an opaque inverse payload bypassing manual transaction math."""
        action = payload.get("action")
        tid = payload.get("tid", "")
        if action == "trash":
            return self.trash(payload["target"], transaction_id=tid)
        elif action == "restore":
            return self.restore(
                payload["target"],
                transaction_id=tid,
                rename_to=payload.get("rename_to", ""),
            )
        elif action == "rename":
            return self.rename(
                payload["target"], payload["new_name"], transaction_id=tid
            )
        elif action == "move":
            from core.utils.vfs_path import vfs_dirname

            dest_dir = vfs_dirname(payload["dest"])
            return self.move(payload["target"], dest_dir, transaction_id=tid)
        return ""

    # -------------------------------------------------------------------------
    # VFS HELPERS (delegates to Gio workers)
    # -------------------------------------------------------------------------

    def check_exists(self, path: str) -> bool:
        assert self._registry
        backend = self._registry.get_io(path)
        return backend.query_exists(path)

    def is_same_file(self, path_a: str, path_b: str) -> bool:
        assert self._registry
        backend = self._registry.get_io(path_a)
        return backend.is_same_file(path_a, path_b)

    def generate_unique_name(self, dest_path: str, style: str = "copy") -> str:
        """
        Find a conflict-free path by appending suffixes.
        WARNING: Synchronous. Use get_unique_name_async from UI.
        """
        from core.utils.path_ops import generate_candidate_path

        for counter in range(1, _MAX_RENAME_ATTEMPTS + 1):
            candidate = generate_candidate_path(dest_path, counter, style=style)
            if not self.check_exists(candidate):
                return candidate
        raise RuntimeError(
            f"Auto-rename limit ({_MAX_RENAME_ATTEMPTS}) for: {dest_path}"
        )

    @Slot(str, str, str)
    def get_unique_name_async(self, task_id: str, dest_path: str, style: str = "copy"):
        """Asynchronously find a unique name."""
        self._unique_name_worker.enqueue(task_id, dest_path, style)

    @Slot(str, str)
    def check_exists_async(self, task_id: str, path: str):
        """Asynchronously check if a file exists."""
        self._existence_worker.enqueue(task_id, path)

    # -------------------------------------------------------------------------
    # UTILS
    # -------------------------------------------------------------------------

    @Slot(str)
    @Slot()
    def cancel(self, job_id: str = None):
        with QMutexLocker(self._mutex):
            if job_id:
                job = self._jobs.get(job_id)
                if job and job.cancellable:
                    job.cancellable.cancel()
                    job.status = "cancelled"
            else:
                for job in self._jobs.values():
                    if job.cancellable:
                        job.cancellable.cancel()
                    job.status = "cancelled"

    def cancelAll(self):
        self.cancel(None)

    @Slot(result=int)
    def activeJobCount(self) -> int:
        with QMutexLocker(self._mutex):
            return len(self._jobs)

    @Slot(str, result=str)
    def jobStatus(self, job_id: str) -> str:
        with QMutexLocker(self._mutex):
            job = self._jobs.get(job_id)
            return job.status if job else "unknown"

    def shutdown(self):
        self.cancelAll()
        self._pool.waitForDone(3000)


class BatchAssessmentRunnable(QRunnable):
    """
    Runs asynchronous pre-flight checks for batch operations.
    Validates exists, computes destinations, checks for same-folder and existence conflicts.
    Runs in background thread to avoid freezing UI (especially on MTP).
    """

    def __init__(
        self,
        tid,
        sources,
        dest_dir,
        mode,
        file_ops,
        signals,
        resolver=None,
        policy: SyncPolicy | None = None,
    ):
        super().__init__()
        self.tid = tid
        self.sources = sources
        self.dest_dir = dest_dir
        self.mode = mode
        self.file_ops = file_ops
        self.signals = signals
        self.resolver = resolver
        self.policy = policy or TransferPolicy.DEFAULT_POLICY
        self.setAutoDelete(True)

    def run(self):
        valid_items = []
        conflicts = []

        # NOTE: Pre-flight assessment is performed in background.
        # If a resolver is provided, it is called from this thread (blocking it, but not UI).

        for src in self.sources:
            backend = self.file_ops._registry.get_io(src)
            src_meta = backend.get_metadata(src)
            if not src_meta:
                continue

            from core.utils.path_ops import build_dest_path

            dest = build_dest_path(src, self.dest_dir)

            if backend.is_same_file(src, dest):
                if self.mode == "copy":
                    valid_items.append(
                        {
                            "src": src,
                            "dest": dest,
                            "mode": "copy",
                            "overwrite": False,
                            "auto_rename": True,
                        }
                    )
                continue

            dest_meta = backend.get_metadata(dest)

            decision = TransferPolicy.decide(src_meta, dest_meta, self.policy)

            if decision == ConflictResolution.SKIP:
                continue

            if decision == ConflictResolution.OVERWRITE:
                valid_items.append(
                    {
                        "src": src,
                        "dest": dest,
                        "mode": self.mode,
                        "overwrite": True,
                        "auto_rename": False,
                    }
                )
                continue

            if decision == ConflictResolution.RENAME:
                valid_items.append(
                    {
                        "src": src,
                        "dest": dest,
                        "mode": self.mode,
                        "overwrite": False,
                        "auto_rename": True,
                    }
                )
                continue

            if decision == ConflictResolution.PROMPT:
                if self.resolver:
                    # RESOLVE IN BACKGROUND
                    # This calls ConflictResolver which handles thread-safe dialog execution.
                    action, final_dest = self.resolver(src, dest)

                    # Convert Enum to string if necessary (resolver might return ConflictAction enum)
                    action_val = action.value if hasattr(action, "value") else action

                    if action_val == "cancel":
                        break
                    if action_val == "skip":
                        continue

                    valid_items.append(
                        {
                            "src": src,
                            "dest": final_dest or dest,
                            "mode": self.mode,
                            "overwrite": (action_val == "overwrite"),
                            "auto_rename": (action_val == "rename" and not final_dest),
                        }
                    )
                else:
                    from core.utils.path_ops import build_conflict_payload

                    # Fallback to emitting conflict for UI handling if no resolver
                    conflict_data = build_conflict_payload(src_path=src, dest_path=dest)
                    conflicts.append(
                        {
                            "src": src,
                            "dest": dest,
                            "mode": self.mode,
                            "auto_rename": False,
                            "conflict_data": conflict_data,
                        }
                    )

        self.signals.batchAssessmentReady.emit(self.tid, valid_items, conflicts)
