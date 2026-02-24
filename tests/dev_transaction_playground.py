
import sys
import os
import time
from PySide6.QtCore import QCoreApplication

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.transaction_manager import TransactionManager
from core.file_operations import FileOperations
from core.undo_manager import UndoManager

def verify_transaction_logic():
    print("--- Verifying Transaction System ---")
    app = QCoreApplication(sys.argv)
    
    # 1. Setup Components
    tm = TransactionManager()
    file_ops = FileOperations()
    undo_mgr = UndoManager(file_ops)
    
    # Wire them up
    # AppBridge logic: Signal connections
    tm.transactionFinished.connect(lambda tid, status: print(f"Transaction {tid[:8]} Finished: {status}"))
    tm.historyCommitted.connect(undo_mgr.push) # The critical link
    
    # FileOps -> TM
    file_ops.operationFinished.connect(tm.onOperationFinished)
    
    # 2. Start a Fake Transaction
    print("\n[Step 1] Starting Transaction...")
    tid = tm.startTransaction("Test Batch Move")
    print(f"Transaction ID: {tid}")
    
    # 3. Add Operations (Mocking what AppBridge does)
    tm.addOperation(tid, "copy", "/tmp/a.txt", "/tmp/b.txt")
    tm.addOperation(tid, "copy", "/tmp/c.txt", "/tmp/d.txt")
    
    # 4. Execute (Mocking FileOps execution)
    # We manually fire the signal that FileOps WOULD fire
    # Because we don't want to actually touch disk in this logic test
    print("\n[Step 2] Executing Jobs (Simulated)...")
    
    # Job 1 starts -> finishes
    tm.onOperationStarted("job1", "copy", "/tmp/a.txt")
    tm.onOperationFinished(tid, "job1", "copy", "/tmp/b.txt", True, "Success")
    print("Job 1 reported success.")
    
    # Job 2 starts -> finishes
    tm.onOperationStarted("job2", "copy", "/tmp/c.txt")
    tm.onOperationFinished(tid, "job2", "copy", "/tmp/d.txt", True, "Success")
    print("Job 2 reported success.")
    
    # 5. Verify History
    print("\n[Step 3] Checking Undo History...")
    history = undo_mgr._undo_stack
    if len(history) == 1:
        print("SUCCESS: Undo Stack has exactly 1 entry (Batch).")
        entry = history[0]
        # It should be a Transaction object
        if hasattr(entry, 'ops') and len(entry.ops) == 2:
             print("SUCCESS: Entry contains 2 operations.")
        else:
             print(f"FAILURE: Entry content wrong: {entry}")
    else:
        print(f"FAILURE: Undo Stack has {len(history)} entries. Expected 1.")

    print("\n--- Test Complete ---")

if __name__ == "__main__":
    verify_transaction_logic()
