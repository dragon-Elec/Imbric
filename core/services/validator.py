"""
Post-operation filesystem verification.
Moved from core/operation_validator.py
"""

from PySide6.QtCore import QObject, Signal, QRunnable, QThreadPool

from core.registry import BackendRegistry


class OperationValidator(QObject):
    """Post-operation validator. Verifies filesystem state matches reported outcomes."""

    validationPassed = Signal(str, str)
    validationFailed = Signal(str, str, str, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pool = QThreadPool.globalInstance()
        self._enabled = True
        self._registry: BackendRegistry | None = None

    def setRegistry(self, registry: BackendRegistry):
        self._registry = registry

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
            if not self.validator._registry:
                return

            backend = self.validator._registry.get_io(self.source)

            checker = _VALIDATORS.get(self.op_type)
            if not checker:
                return

            passed, expected, actual = checker(self.source, self.result_path, backend)

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


def _check_copy(source: str, result_path: str, backend) -> tuple:
    src_exists = backend.query_exists(source)
    dest_exists = backend.query_exists(result_path)

    if dest_exists and src_exists:
        return (True, "", "")

    issues = []
    if not dest_exists:
        issues.append("dest missing")
    if not src_exists:
        issues.append("source deleted (should still exist after copy)")

    return (False, "dest exists + source exists", ", ".join(issues))


def _check_move(source: str, result_path: str, backend) -> tuple:
    src_exists = backend.query_exists(source)
    dest_exists = backend.query_exists(result_path)

    if dest_exists and not src_exists:
        return (True, "", "")

    issues = []
    if not dest_exists:
        issues.append("dest missing")
    if src_exists:
        issues.append("source still exists (should be gone after move)")

    return (False, "dest exists + source gone", ", ".join(issues))


def _check_rename(source: str, result_path: str, backend) -> tuple:
    if backend.is_same_file(source, result_path):
        exists = backend.query_exists(result_path)
        if exists:
            return (True, "", "")
        return (False, "file exists", "file missing")

    return _check_move(source, result_path, backend)


def _check_trash(source: str, result_path: str, backend) -> tuple:
    src_exists = backend.query_exists(source)

    if not src_exists:
        return (True, "", "")

    return (False, "source gone", "source still exists")


def _check_create_folder(source: str, result_path: str, backend) -> tuple:
    if not backend.query_exists(result_path):
        return (False, "folder exists", "folder missing")

    if backend.is_directory(result_path):
        return (True, "", "")
    return (False, "is directory", "is not directory")


def _check_restore(source: str, result_path: str, backend) -> tuple:
    exists = backend.query_exists(result_path)

    if exists:
        return (True, "", "")

    return (False, "file exists at restore location", "file missing")


def _check_create_file(source: str, result_path: str, backend) -> tuple:
    if not backend.query_exists(result_path):
        return (False, "file exists", "file missing")

    if backend.is_regular_file(result_path):
        return (True, "", "")
    return (False, "is regular file", "is not regular file")


def _check_create_symlink(source: str, result_path: str, backend) -> tuple:
    if not backend.query_exists(result_path):
        return (False, "symlink exists", "symlink missing")

    if backend.is_symlink(result_path):
        return (True, "", "")
    return (False, "is symlink", "is not symlink")


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
