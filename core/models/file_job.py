"""
FileJob dataclass and FileOperationSignals.
No GIO/Qt dependencies in the dataclass definition - those are injected in the runnables.
"""

from dataclasses import dataclass, field
from typing import TypedDict, NotRequired, TYPE_CHECKING
from PySide6.QtCore import QObject, Signal

if TYPE_CHECKING:
    from core.logic.transfer_policy import SyncPolicy

from core.interfaces.cancellation import CancellationToken


class InversePayload(TypedDict, total=False):
    """Contract for undo reversal data. Built by backend, executed by UndoManager."""

    action: str  # "trash" | "restore" | "rename" | "move"
    target: str  # Path to operate on
    dest: NotRequired[str]  # Original source (for move reversal)
    new_name: NotRequired[str]  # Original name (for rename reversal)
    rename_to: NotRequired[str]  # For restore with new name
    tid: NotRequired[str]  # Transaction ID (injected at execution time)
    backend_id: NotRequired[str]  # Backend that should execute the reversal


@dataclass(slots=True)
class FileJob:
    """Tracks a single file operation (Standard or Trash)."""

    id: str
    op_type: str  # "copy", "move", "trash", "restore", "rename", "createFolder", "list", "empty", "transfer"
    source: str
    dest: str = ""  # Destination path (or new name for rename)
    transaction_id: str = ""  # Links this job to a larger transaction (batch)
    cancellable: CancellationToken | None = field(
        default=None, repr=False
    )  # Injected by executor
    inverse_payload: InversePayload | None = None  # Built by backend upon success
    auto_rename: bool = (
        False  # If True, automatically find a free name (For New Folder / Duplicate)
    )
    skipped_files: list[str] = field(default_factory=list)  # For partial success
    overwrite: bool = False  # If True, overwrite existing files without prompt
    rename_to: str = ""  # Specific for Restore: if set, restore with this filename
    status: str = "pending"  # Lifecycle: pending → running → done/error/cancelled
    backend_id: str = ""  # The backend executing this job
    policy: "SyncPolicy | None" = None  # Decisions on conflicts/sync

    # --- True Batch Specific Fields ---
    items: list[dict] = field(
        default_factory=list
    )  # List of dicts representing operations in a batch
    ui_refresh_rate_ms: int = 100  # How often to emit batchProgress (default 100ms)
    halt_on_error: bool = False  # Whether to stop batch on first error


class FileOperationSignals(QObject):
    """
    Signal hub for file operations.
    Runnables hold a reference and emit via QMetaObject.invokeMethod (wrapped here).
    """

    started = Signal(str, str, str)  # (job_id, op_type, source_path)
    progress = Signal(str, int, int)  # (job_id, current_bytes, total_bytes)
    finished = Signal(
        str, str, str, str, bool, str, object
    )  # (tid, job_id, op_type, result_path, success, message, inverse_payload)
    operationError = Signal(
        str, str, str, str, str, object
    )  # (tid, job_id, op_type, path, message, conflict_data)

    # Trash Specific Signals (Consolidated here)
    itemListed = Signal(object)  # TrashItem (for list operation)
    trashNotSupported = Signal(str, str)  # (path, error_message)

    # Pre-Flight
    batchAssessmentReady = Signal(str, list, list)  # (tid, valid_items, conflicts)

    # True Batching
    batchProgress = Signal(
        str, int, int, str
    )  # (tid, completed_count, total_count, current_filename)
    batchFinished = Signal(str, list, list)  # (tid, successful_items, failed_items)
    batchConflictEncountered = Signal(
        str, str, str, str, object
    )  # (tid, job_id, src, dest, conflict_data)
