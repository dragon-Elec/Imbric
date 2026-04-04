"""
GIO File Operations - Runnable implementations.
Extracted from core/file_workers.py - GIO-specific operations.
"""

import time
from PySide6.QtCore import QRunnable
import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

from core.models.file_job import FileJob, FileOperationSignals, InversePayload
from core.backends.gio.helpers import _make_gfile, _gfile_path
from core.backends.gio.metadata import get_file_info
from core.utils.path_ops import generate_candidate_path, build_conflict_payload


# =============================================================================
# BASE RUNNABLE
# =============================================================================


class GIOOperationRunnable(QRunnable):
    """Base class for GIO file operation runnables."""

    def __init__(self, job: FileJob, signals: FileOperationSignals):
        super().__init__()
        self.job = job
        self.signals = signals
        self._last_progress_time = 0
        self.setAutoDelete(True)

    def emit_started(self):
        self.job.status = "running"
        self.signals.started.emit(self.job.id, self.job.op_type, self.job.source)

    def emit_progress(self, current: int, total: int):
        now = time.time()
        if now - self._last_progress_time > 0.1 or current == total:
            self._last_progress_time = now
            self.signals.progress.emit(self.job.id, current, total)

    def emit_finished(self, success: bool, message: str, result_override: str = None):
        print(
            f"[Worker] emit_finished: tid={self.job.transaction_id[:8]}, jid={self.job.id[:8]}, success={success}"
        )
        self.job.status = "done" if success else "error"
        result_path = (
            result_override
            if result_override is not None
            else (self.job.dest if self.job.dest else self.job.source)
        )

        inv_payload = getattr(self.job, "inverse_payload", None)
        self.signals.finished.emit(
            self.job.transaction_id,
            self.job.id,
            self.job.op_type,
            result_path,
            success,
            message,
            inv_payload,
        )

    def _progress_callback(self, current_bytes, total_bytes, user_data):
        self.emit_progress(current_bytes, total_bytes)

    def _handle_gio_error(
        self, e: GLib.Error, op_type: str, path: str, conflict_data=None
    ):
        if e.code == Gio.IOErrorEnum.EXISTS:
            if conflict_data is None:
                conflict_data = build_conflict_payload(path, path)
            self.signals.operationError.emit(
                self.job.transaction_id,
                self.job.id,
                op_type,
                path,
                str(e),
                conflict_data,
            )
        elif e.code != Gio.IOErrorEnum.CANCELLED:
            self.signals.operationError.emit(
                self.job.transaction_id, self.job.id, op_type, path, str(e), None
            )
        self.emit_finished(False, str(e))

    def _run_create_operation(self, op_type: str, target_path: str):
        self.emit_started()

        if self.job.auto_rename:
            counter = 0
            while counter < 10000:
                candidate = generate_candidate_path(
                    target_path, counter, style="number"
                )
                gfile = _make_gfile(candidate)
                try:
                    self._do_create(gfile)
                    self.job.inverse_payload = InversePayload(
                        action="trash", target=candidate, backend_id=self.job.backend_id
                    )
                    self.emit_finished(True, candidate, result_override=candidate)
                    return
                except GLib.Error as e:
                    if e.code == Gio.IOErrorEnum.EXISTS:
                        counter += 1
                        continue
                    self._handle_gio_error(e, op_type, candidate)
                    return
            self.emit_finished(False, "Auto-rename limit reached")
            return

        gfile = _make_gfile(target_path)
        try:
            self._do_create(gfile)
            self.job.inverse_payload = InversePayload(
                action="trash", target=target_path, backend_id=self.job.backend_id
            )
            self.emit_finished(True, target_path)
        except GLib.Error as e:
            self._handle_gio_error(e, op_type, target_path)

    def _do_create(self, gfile):
        raise NotImplementedError


# =============================================================================
# TRANSFER OPERATIONS
# =============================================================================


class BatchTransferRunnable(GIOOperationRunnable):
    """
    True batch worker for Copy and Move.
    Processes a list of items sequentially in a single thread to avoid
    thread pool exhaustion, GIL fighting, and signal storms.
    """

    def run(self):
        self.job.status = "running"

        throttle_sec = self.job.ui_refresh_rate_ms / 1000.0
        last_emit = 0

        success_list = []
        failed_list = []

        total = len(self.job.items)

        for index, item in enumerate(self.job.items):
            if self.job.cancellable and self.job.cancellable.is_cancelled():
                break

            job_id = item.get("job_id", "")
            src = item.get("src", "")
            dest = item.get("dest", "")
            op_type = item.get("op_type", "copy")
            overwrite = item.get("overwrite", False)
            auto_rename = item.get("auto_rename", False)

            # Throttled UI Progress Emission
            if time.time() - last_emit > throttle_sec:
                current_filename = _make_gfile(src).get_basename()
                self.signals.batchProgress.emit(
                    self.job.transaction_id, index, total, current_filename
                )
                last_emit = time.time()

            try:
                final_dest = self._perform_single_transfer(
                    src, dest, op_type, overwrite, auto_rename
                )
                success_list.append(
                    {
                        "job_id": job_id,
                        "result_path": final_dest,
                        "op_type": op_type,
                        "src": src,
                    }
                )
            except Exception as e:
                failed_list.append(
                    {"job_id": job_id, "error": str(e), "op_type": op_type, "src": src}
                )
                if self.job.halt_on_error:
                    break

        self.job.status = "done"
        self.signals.batchFinished.emit(
            self.job.transaction_id, success_list, failed_list
        )

    def _perform_single_transfer(
        self,
        source: str,
        base_dest: str,
        op_type: str,
        overwrite: bool,
        auto_rename: bool,
    ) -> str:
        counter = 0
        if _make_gfile(source).equal(_make_gfile(base_dest)):
            counter = 1

        max_retries = 10000 if auto_rename else 1

        while counter < max_retries:
            final_dest = generate_candidate_path(base_dest, counter, style="copy")
            src_file = _make_gfile(source)
            dst_file = _make_gfile(final_dest)

            try:
                skipped_files = []

                match op_type:
                    case "move":
                        try:
                            flags = (
                                (
                                    Gio.FileCopyFlags.OVERWRITE
                                    if overwrite
                                    else Gio.FileCopyFlags.NONE
                                )
                                | Gio.FileCopyFlags.ALL_METADATA
                                | Gio.FileCopyFlags.NOFOLLOW_SYMLINKS
                            )

                            src_file.move(
                                dst_file,
                                flags | Gio.FileCopyFlags.NO_FALLBACK_FOR_MOVE,
                                self.job.cancellable,
                                None,  # No progress callback to avoid signal storms
                                None,
                            )
                            return final_dest
                        except GLib.Error as e:
                            match e.code:
                                case (
                                    Gio.IOErrorEnum.NOT_SUPPORTED
                                    | Gio.IOErrorEnum.WOULD_MERGE
                                    | 29
                                ):
                                    self._recursive_transfer(
                                        src_file,
                                        dst_file,
                                        is_move=True,
                                        overwrite=overwrite,
                                        skipped_files=skipped_files,
                                    )
                                    if skipped_files:
                                        raise Exception(
                                            f"Partial Success: {len(skipped_files)} skipped"
                                        )
                                    return final_dest
                                case _:
                                    raise e
                    case _:
                        self._recursive_transfer(
                            src_file,
                            dst_file,
                            is_move=False,
                            overwrite=overwrite,
                            skipped_files=skipped_files,
                        )
                        if skipped_files:
                            raise Exception(
                                f"Partial Success: {len(skipped_files)} skipped"
                            )
                        return final_dest

            except GLib.Error as e:
                if e.code == Gio.IOErrorEnum.EXISTS:
                    if auto_rename:
                        counter += 1
                        continue
                    else:
                        raise e
                else:
                    raise e

        raise Exception("Auto-rename limit reached")

    def _recursive_transfer(self, source, dest, is_move, overwrite, skipped_files):
        info = source.query_info(
            "standard::type,standard::name",
            Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS,
            self.job.cancellable,
        )
        file_type = info.get_file_type()

        if file_type == Gio.FileType.DIRECTORY:
            try:
                dest.make_directory_with_parents(self.job.cancellable)
            except GLib.Error as e:
                if e.code != Gio.IOErrorEnum.EXISTS:
                    raise e

            local_error = False
            enumerator = None
            try:
                enumerator = source.enumerate_children(
                    "standard::name,standard::type",
                    Gio.FileQueryInfoFlags.NONE,
                    self.job.cancellable,
                )
                for child_info in enumerator:
                    child_name = child_info.get_name()
                    c_src = source.get_child(child_name)
                    c_dst = dest.get_child(child_name)

                    try:
                        self._recursive_transfer(
                            c_src, c_dst, is_move, overwrite, skipped_files
                        )
                    except GLib.Error as e:
                        if e.code in [
                            Gio.IOErrorEnum.CANCELLED,
                            Gio.IOErrorEnum.EXISTS,
                        ]:
                            raise
                        skipped_files.append(c_src.get_path())
                        local_error = True
            finally:
                if enumerator:
                    enumerator.close(None)

            if is_move and not local_error:
                try:
                    source.delete(self.job.cancellable)
                except Exception:
                    pass
        else:
            flags = (
                (Gio.FileCopyFlags.OVERWRITE if overwrite else Gio.FileCopyFlags.NONE)
                | Gio.FileCopyFlags.ALL_METADATA
                | Gio.FileCopyFlags.NOFOLLOW_SYMLINKS
            )

            if is_move:
                source.move(dest, flags, self.job.cancellable, None, None)
            else:
                source.copy(dest, flags, self.job.cancellable, None, None)


class TransferRunnable(GIOOperationRunnable):
    """
    Unified worker for Copy and Move.
    Implements Smart Transfer: atomic rename, recursive copy+delete, etc.
    """

    def run(self):
        try:
            self.emit_started()

            base_dest = self.job.dest
            counter = 0

            if _make_gfile(self.job.source).equal(_make_gfile(base_dest)):
                counter = 1

            max_retries = 10000 if self.job.auto_rename else 1

            while counter < max_retries:
                final_dest = generate_candidate_path(base_dest, counter, style="copy")

                src_file = _make_gfile(self.job.source)
                dst_file = _make_gfile(final_dest)

                try:
                    self.job.skipped_files = []

                    match self.job.op_type:
                        case "move":
                            try:
                                flags = (
                                    (
                                        Gio.FileCopyFlags.OVERWRITE
                                        if self.job.overwrite
                                        else Gio.FileCopyFlags.NONE
                                    )
                                    | Gio.FileCopyFlags.ALL_METADATA
                                    | Gio.FileCopyFlags.NOFOLLOW_SYMLINKS
                                )
                                src_file.move(
                                    dst_file,
                                    flags | Gio.FileCopyFlags.NO_FALLBACK_FOR_MOVE,
                                    self.job.cancellable,
                                    self._progress_callback,
                                    None,
                                )
                                self.job.inverse_payload = InversePayload(
                                    action="move",
                                    target=final_dest,
                                    dest=self.job.source,
                                    backend_id=self.job.backend_id,
                                )
                                self.emit_finished(
                                    True, "Success", result_override=final_dest
                                )
                                return
                            except GLib.Error as e:
                                match e.code:
                                    case (
                                        Gio.IOErrorEnum.NOT_SUPPORTED
                                        | Gio.IOErrorEnum.WOULD_MERGE
                                        | 29
                                    ):
                                        self._recursive_transfer(
                                            src_file, dst_file, is_move=True
                                        )
                                        msg = (
                                            f"Partial Success: {len(self.job.skipped_files)} skipped"
                                            if self.job.skipped_files
                                            else "Success"
                                        )
                                        self.job.inverse_payload = InversePayload(
                                            action="move",
                                            target=final_dest,
                                            dest=self.job.source,
                                            backend_id=self.job.backend_id,
                                        )
                                        self.emit_finished(
                                            True, msg, result_override=final_dest
                                        )
                                        return
                                    case Gio.IOErrorEnum.EXISTS | _:
                                        raise e
                        case _:
                            self._recursive_transfer(src_file, dst_file, is_move=False)
                            msg = (
                                f"Partial Success: {len(self.job.skipped_files)} skipped"
                                if self.job.skipped_files
                                else "Success"
                            )
                            self.job.inverse_payload = InversePayload(
                                action="trash",
                                target=final_dest,
                                backend_id=self.job.backend_id,
                            )
                            self.emit_finished(True, msg, result_override=final_dest)
                            return

                except GLib.Error as e:
                    if e.code == Gio.IOErrorEnum.EXISTS:
                        if self.job.auto_rename:
                            counter += 1
                            continue
                        else:
                            conflict_data = build_conflict_payload(
                                self.job.source, final_dest
                            )
                            self._handle_gio_error(
                                e, self.job.op_type, final_dest, conflict_data
                            )
                            return
                    else:
                        self._handle_gio_error(e, self.job.op_type, final_dest)
                        return

            self.emit_finished(False, "Auto-rename limit reached")
        except Exception as e:
            self.emit_finished(False, f"Internal Error: {str(e)}")

    def _recursive_transfer(self, source, dest, is_move=False):
        # Progress for UI on large folder copies
        self.emit_progress(0, 1)

        info = source.query_info(
            "standard::type,standard::name",
            Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS,
            self.job.cancellable,
        )
        file_type = info.get_file_type()

        if file_type == Gio.FileType.DIRECTORY:
            try:
                dest.make_directory_with_parents(self.job.cancellable)
            except GLib.Error as e:
                if e.code != Gio.IOErrorEnum.EXISTS:
                    raise e

            local_error = False
            enumerator = None
            try:
                enumerator = source.enumerate_children(
                    "standard::name,standard::type",
                    Gio.FileQueryInfoFlags.NONE,
                    self.job.cancellable,
                )
                for child_info in enumerator:
                    child_name = child_info.get_name()
                    c_src = source.get_child(child_name)
                    c_dst = dest.get_child(child_name)

                    try:
                        self._recursive_transfer(c_src, c_dst, is_move=is_move)
                    except GLib.Error as e:
                        if e.code in [
                            Gio.IOErrorEnum.CANCELLED,
                            Gio.IOErrorEnum.EXISTS,
                        ]:
                            raise
                        self.job.skipped_files.append(c_src.get_path())
                        local_error = True
            finally:
                if enumerator:
                    enumerator.close(None)

            if is_move and not local_error:
                try:
                    source.delete(self.job.cancellable)
                except Exception:
                    pass
        else:
            flags = (
                (
                    Gio.FileCopyFlags.OVERWRITE
                    if self.job.overwrite
                    else Gio.FileCopyFlags.NONE
                )
                | Gio.FileCopyFlags.ALL_METADATA
                | Gio.FileCopyFlags.NOFOLLOW_SYMLINKS
            )
            match is_move:
                case True:
                    source.move(
                        dest, flags, self.job.cancellable, self._progress_callback, None
                    )
                case False:
                    source.copy(
                        dest, flags, self.job.cancellable, self._progress_callback, None
                    )


class RenameRunnable(GIOOperationRunnable):
    def run(self):
        self.emit_started()
        gfile = _make_gfile(self.job.source)
        try:
            result = gfile.set_display_name(self.job.dest, self.job.cancellable)
            if result:
                abs_path = _gfile_path(result)
                from core.utils.vfs_path import vfs_basename

                self.job.inverse_payload = InversePayload(
                    action="rename",
                    target=abs_path,
                    new_name=vfs_basename(self.job.source),
                    backend_id=self.job.backend_id,
                )
                self.emit_finished(True, "Success", result_override=abs_path)
            else:
                self.emit_finished(False, "Rename returned no result")
        except GLib.Error as e:
            if e.code == Gio.IOErrorEnum.EXISTS:
                dest_path = _gfile_path(gfile.get_parent().get_child(self.job.dest))
                conflict_data = build_conflict_payload(self.job.source, dest_path)
                self._handle_gio_error(e, "rename", dest_path, conflict_data)
            else:
                self._handle_gio_error(e, "rename", self.job.source)


class CreateFolderRunnable(GIOOperationRunnable):
    def run(self):
        self._run_create_operation("createFolder", self.job.source)

    def _do_create(self, gfile):
        gfile.make_directory(self.job.cancellable)


class CreateFileRunnable(GIOOperationRunnable):
    def run(self):
        self._run_create_operation("createFile", self.job.source)

    def _do_create(self, gfile):
        stream = gfile.create(Gio.FileCreateFlags.NONE, self.job.cancellable)
        stream.close(None)


class CreateSymlinkRunnable(GIOOperationRunnable):
    def run(self):
        self._run_create_operation("createSymlink", self.job.dest)

    def _do_create(self, gfile):
        gfile.make_symbolic_link(self.job.source, self.job.cancellable)
