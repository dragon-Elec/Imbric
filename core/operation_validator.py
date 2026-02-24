"""
OperationValidator — Post-Operation Verification

Verifies that file operation outcomes match their intended results
using Gio post-condition checks. Catches implementation bugs
(wrong API, silent failures) regardless of what caused them.

Design:
- Runs AFTER TransactionManager commits (fire-and-forget safety net)
- Async via QThreadPool (does not block signal chain)
- Uses Gio.File.query_exists() for VFS-safe checks
"""

import gi
gi.require_version('Gio', '2.0')
from gi.repository import Gio

from PySide6.QtCore import QObject, Signal, QRunnable, QThreadPool

from core.file_workers import _make_gfile


class OperationValidator(QObject):
    """
    Post-operation validator. Verifies filesystem state matches reported outcomes.
    
    Wired to TransactionManager via setValidator(). TM calls validate() after
    each successful job completion. Validation runs async and emits signals.
    """
    
    # Emitted when post-condition checks pass
    validationPassed = Signal(str, str)  # (job_id, op_type)
    
    # Emitted when post-condition checks FAIL (something unexpected happened)
    validationFailed = Signal(str, str, str, str, str)  # (job_id, op_type, source, expected, actual)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._pool = QThreadPool.globalInstance()
        self._enabled = True
    
    def setEnabled(self, enabled: bool):
        """Toggle validation on/off (e.g., for performance profiling)."""
        self._enabled = enabled
    
    def validate(self, job_id: str, op_type: str, source: str, result_path: str, success: bool):
        """
        Queue an async validation check for a completed operation.
        
        Called by TransactionManager after processing onOperationFinished.
        Only validates successful operations (failed ops have nothing to verify).
        
        Args:
            job_id: Unique job identifier
            op_type: Operation type (copy, move, rename, trash, createFolder, restore)
            source: Original source path/URI
            result_path: Reported result path/URI from the worker
            success: Whether the worker reported success
        """
        if not self._enabled or not success:
            return
        
        if not source or not result_path:
            return  # Can't validate without paths
        
        runnable = ValidationRunnable(
            job_id, op_type, source, result_path, self
        )
        self._pool.start(runnable)


class ValidationRunnable(QRunnable):
    """Async post-condition checker. Runs in QThreadPool."""
    
    def __init__(self, job_id: str, op_type: str, source: str, 
                 result_path: str, validator: OperationValidator):
        super().__init__()
        self.job_id = job_id
        self.op_type = op_type
        self.source = source
        self.result_path = result_path
        self.validator = validator
        self.setAutoDelete(True)
    
    def run(self):
        """Execute post-condition checks based on operation type."""
        try:
            checker = _VALIDATORS.get(self.op_type)
            if not checker:
                return  # Unknown op type, skip silently
            
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


# =============================================================================
# VALIDATION RULES
# Each returns: (passed: bool, expected: str, actual: str)
# =============================================================================

def _check_copy(source: str, result_path: str) -> tuple:
    """Copy: dest must exist, source must still exist."""
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
    """Move: dest must exist, source must be gone."""
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
    """Rename: new path must exist, old path must be gone."""
    # Handle no-op rename (renamed to same name)
    if _make_gfile(source).equal(_make_gfile(result_path)):
        exists = _make_gfile(result_path).query_exists(None)
        if exists:
            return (True, "", "")
        return (False, "file exists", "file missing")
    
    # Otherwise same logic as move (rename = same-dir move)
    return _check_move(source, result_path)


def _check_trash(source: str, result_path: str) -> tuple:
    """Trash: source must be gone from its original location."""
    src_exists = _make_gfile(source).query_exists(None)
    
    if not src_exists:
        return (True, "", "")
    
    return (False, "source gone", "source still exists")


def _check_create_folder(source: str, result_path: str) -> tuple:
    """CreateFolder: result path must exist and be a directory."""
    gfile = _make_gfile(result_path)
    
    if not gfile.query_exists(None):
        return (False, "folder exists", "folder missing")
    
    try:
        info = gfile.query_info(
            "standard::type",
            Gio.FileQueryInfoFlags.NONE,
            None
        )
        if info.get_file_type() == Gio.FileType.DIRECTORY:
            return (True, "", "")
        return (False, "is directory", f"is file type {info.get_file_type().value_nick}")
    except Exception:
        return (False, "is directory", "type query failed")


def _check_restore(source: str, result_path: str) -> tuple:
    """Restore: result path must exist at the restored location."""
    exists = _make_gfile(result_path).query_exists(None)
    
    if exists:
        return (True, "", "")
    
    return (False, "file exists at restore location", "file missing")


def _check_create_file(source: str, result_path: str) -> tuple:
    """CreateFile: result path must exist and be a regular file."""
    gfile = _make_gfile(result_path)
    
    if not gfile.query_exists(None):
        return (False, "file exists", "file missing")
    
    try:
        info = gfile.query_info(
            "standard::type",
            Gio.FileQueryInfoFlags.NONE,
            None
        )
        if info.get_file_type() == Gio.FileType.REGULAR:
            return (True, "", "")
        return (False, "is regular file", f"is {info.get_file_type().value_nick}")
    except Exception:
        return (False, "is regular file", "type query failed")


def _check_create_symlink(source: str, result_path: str) -> tuple:
    """CreateSymlink: result path must exist and be a symbolic link."""
    gfile = _make_gfile(result_path)
    
    if not gfile.query_exists(None):
        return (False, "symlink exists", "symlink missing")
    
    try:
        info = gfile.query_info(
            "standard::type",
            Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS,
            None
        )
        if info.get_file_type() == Gio.FileType.SYMBOLIC_LINK:
            return (True, "", "")
        return (False, "is symlink", f"is {info.get_file_type().value_nick}")
    except Exception:
        return (False, "is symlink", "type query failed")


# Map op_type strings to checker functions
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
