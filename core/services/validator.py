"""
Post-operation filesystem verification.
Moved from core/operation_validator.py
"""

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio

from PySide6.QtCore import QObject, Signal, QRunnable, QThreadPool

from core.backends.gio.helpers import _make_gfile


class OperationValidator(QObject):
    """Post-operation validator. Verifies filesystem state matches reported outcomes."""

    validationPassed = Signal(str, str)
    validationFailed = Signal(str, str, str, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pool = QThreadPool.globalInstance()
        self._enabled = True

    def setEnabled(self, enabled: bool):
        self._enabled = enabled

    def validate(
        self, job_id: str, op_type: str, source: str, result_path: str, success: bool
    ):
        if not self._enabled or not success:
            return

        if not source or not result_path:
            return

        runnable = ValidationRunnable(job_id, op_type, source, result_path, self)
        self._pool.start(runnable)


class ValidationRunnable(QRunnable):
    def __init__(
        self,
        job_id: str,
        op_type: str,
        source: str,
        result_path: str,
        validator: OperationValidator,
    ):
        super().__init__()
        self.job_id = job_id
        self.op_type = op_type
        self.source = source
        self.result_path = result_path
        self.validator = validator
        self.setAutoDelete(True)

    def run(self):
        try:
            checker = _VALIDATORS.get(self.op_type)
            if not checker:
                return

            passed, expected, actual = checker(self.source, self.result_path)

            if passed:
                self.validator.validationPassed.emit(self.job_id, self.op_type)
            else:
                print(
                    f"[VALIDATOR] ✗ {self.op_type.upper()} FAILED: "
                    f"src={self.source} result={self.result_path} "
                    f"expected=({expected}) actual=({actual})"
                )
                self.validator.validationFailed.emit(
                    self.job_id, self.op_type, self.source, expected, actual
                )
        except Exception as e:
            print(f"[VALIDATOR] Error during validation: {e}")


def _check_copy(source: str, result_path: str) -> tuple:
    src_exists = _make_gfile(source).query_exists(None)
    dest_exists = _make_gfile(result_path).query_exists(None)

    if dest_exists and src_exists:
        return (True, "", "")

    issues = []
    if not dest_exists:
        issues.append("dest missing")
    if not src_exists:
        issues.append("source deleted (should still exist after copy)")

    return (False, "dest exists + source exists", ", ".join(issues))


def _check_move(source: str, result_path: str) -> tuple:
    src_exists = _make_gfile(source).query_exists(None)
    dest_exists = _make_gfile(result_path).query_exists(None)

    if dest_exists and not src_exists:
        return (True, "", "")

    issues = []
    if not dest_exists:
        issues.append("dest missing")
    if src_exists:
        issues.append("source still exists (should be gone after move)")

    return (False, "dest exists + source gone", ", ".join(issues))


def _check_rename(source: str, result_path: str) -> tuple:
    if _make_gfile(source).equal(_make_gfile(result_path)):
        exists = _make_gfile(result_path).query_exists(None)
        if exists:
            return (True, "", "")
        return (False, "file exists", "file missing")

    return _check_move(source, result_path)


def _check_trash(source: str, result_path: str) -> tuple:
    src_exists = _make_gfile(source).query_exists(None)

    if not src_exists:
        return (True, "", "")

    return (False, "source gone", "source still exists")


def _check_create_folder(source: str, result_path: str) -> tuple:
    gfile = _make_gfile(result_path)

    if not gfile.query_exists(None):
        return (False, "folder exists", "folder missing")

    try:
        info = gfile.query_info("standard::type", Gio.FileQueryInfoFlags.NONE, None)
        if info.get_file_type() == Gio.FileType.DIRECTORY:
            return (True, "", "")
        return (
            False,
            "is directory",
            f"is file type {info.get_file_type().value_nick}",
        )
    except Exception:
        return (False, "is directory", "type query failed")


def _check_restore(source: str, result_path: str) -> tuple:
    exists = _make_gfile(result_path).query_exists(None)

    if exists:
        return (True, "", "")

    return (False, "file exists at restore location", "file missing")


def _check_create_file(source: str, result_path: str) -> tuple:
    gfile = _make_gfile(result_path)

    if not gfile.query_exists(None):
        return (False, "file exists", "file missing")

    try:
        info = gfile.query_info("standard::type", Gio.FileQueryInfoFlags.NONE, None)
        if info.get_file_type() == Gio.FileType.REGULAR:
            return (True, "", "")
        return (False, "is regular file", f"is {info.get_file_type().value_nick}")
    except Exception:
        return (False, "is regular file", "type query failed")


def _check_create_symlink(source: str, result_path: str) -> tuple:
    gfile = _make_gfile(result_path)

    if not gfile.query_exists(None):
        return (False, "symlink exists", "symlink missing")

    try:
        info = gfile.query_info(
            "standard::type", Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS, None
        )
        if info.get_file_type() == Gio.FileType.SYMBOLIC_LINK:
            return (True, "", "")
        return (False, "is symlink", f"is {info.get_file_type().value_nick}")
    except Exception:
        return (False, "is symlink", "type query failed")


_VALIDATORS = {
    "copy": _check_copy,
    "move": _check_move,
    "rename": _check_rename,
    "trash": _check_trash,
    "createFolder": _check_create_folder,
    "createFile": _check_create_file,
    "createSymlink": _check_create_symlink,
    "restore": _check_restore,
}
