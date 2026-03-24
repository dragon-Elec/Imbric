"""
Core data models - pure data structures with zero external dependencies.
"""

from core.models.file_info import FileInfo
from core.models.file_job import FileJob, FileOperationSignals
from core.models.trash_item import TrashItem
from core.transaction import Transaction, TransactionOperation, TransactionStatus

__all__ = [
    "FileInfo",
    "FileJob",
    "FileOperationSignals",
    "TrashItem",
    "Transaction",
    "TransactionOperation",
    "TransactionStatus",
]
