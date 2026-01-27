from dataclasses import dataclass, field
from typing import List, Optional, Dict
from enum import Enum
import time

class TransactionStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    # PARTIAL? If we want to support partial successes

@dataclass
class TransactionOperation:
    """Represents a single atomic operation within a transaction."""
    op_type: str        # "copy", "move", "rename", "trash", "createFolder"
    src: str
    dest: str = ""      # Final destination path (if applicable)
    result_path: str = "" # Specifically for rename/copy (e.g., "file (2).txt")
    job_id: str = ""    # The low-level job ID from FileOperations
    status: TransactionStatus = TransactionStatus.PENDING
    error: str = ""

@dataclass
class Transaction:
    """Represents a high-level job (batch of operations)."""
    id: str
    description: str
    created_at: float = field(default_factory=time.time)
    
    # Operations
    ops: List[TransactionOperation] = field(default_factory=list)
    
    # Progress State
    total_ops: int = 0
    completed_ops: int = 0
    
    # Status
    status: TransactionStatus = TransactionStatus.PENDING
    error_message: str = ""
    
    def add_operation(self, op: TransactionOperation):
        self.ops.append(op)
        self.total_ops += 1
        
    def get_progress(self) -> float:
        """Returns progress 0.0 to 1.0"""
        if self.total_ops == 0:
            return 0.0
        return self.completed_ops / self.total_ops

    def find_operation(self, job_id: str) -> Optional[TransactionOperation]:
        """Finds an operation by its job ID."""
        for op in self.ops:
            if op.job_id == job_id:
                return op
        return None

    def update_status(self, job_id: str, status: TransactionStatus, error: str = ""):
        """Updates status of a specific operation."""
        op = self.find_operation(job_id)
        if op:
            op.status = status
            op.error = error

