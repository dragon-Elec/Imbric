#!/usr/bin/env python3
"""
Stress Test: Undo Logic Resistance (DEBUG VERSION)
Enhanced with verbose debugging to trace ID flow.
"""

import sys
import os
import shutil
import time
import unittest
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PySide6.QtCore import QCoreApplication, Slot
from core.managers import FileOperations
from core.managers import TransactionManager
from core.managers import UndoManager
from core.registry import BackendRegistry
from core.backends.gio.backend import GIOBackend
from core.models.file_job import FileOperationSignals

app = QCoreApplication.instance() or QCoreApplication(sys.argv)


class DebugHooks:
    """Intercepts and logs all signal traffic for debugging."""

    def __init__(self):
        self.log = []
        self.job_map = {}  # job_id -> (tid, op_type, path)

    def clear(self):
        self.log = []
        self.job_map = {}

    def log_event(self, event_type, **kwargs):
        entry = {"type": event_type, "time": time.time(), **kwargs}
        self.log.append(entry)
        print(f"  [DEBUG] {event_type}: {kwargs}")

    @Slot(str, str, str)
    def on_op_started(self, job_id, op_type, path):
        self.log_event(
            "OP_STARTED",
            job_id=job_id[:8],
            op_type=op_type,
            path=os.path.basename(path),
        )

    @Slot(str, str, str, str, bool, str)
    def on_op_finished(self, tid, job_id, op_type, path, success, msg):
        self.log_event(
            "OP_FINISHED",
            tid=tid[:8],
            job_id=job_id[:8],
            op_type=op_type,
            success=success,
        )

    @Slot(str, str, str, str, str, object)
    def on_op_error(self, tid, job_id, op_type, path, msg, conflict):
        self.log_event(
            "OP_ERROR", tid=tid[:8], job_id=job_id[:8], op_type=op_type, msg=msg
        )

    @Slot(str, str)
    def on_tx_started(self, tid, desc):
        self.log_event("TX_STARTED", tid=tid[:8], desc=desc)

    @Slot(str, str)
    def on_tx_finished(self, tid, status):
        self.log_event("TX_FINISHED", tid=tid[:8], status=status)

    @Slot(object)
    def on_history_committed(self, tx):
        ops_summary = [
            f"{op.op_type}:{op.job_id[:8] if op.job_id else 'NO_ID'}" for op in tx.ops
        ]
        self.log_event("HISTORY_COMMITTED", tx_id=tx.id[:8], ops=ops_summary[:5])

    def print_summary(self):
        print("\n  === DEBUG SUMMARY ===")
        type_counts = {}
        for entry in self.log:
            t = entry["type"]
            type_counts[t] = type_counts.get(t, 0) + 1
        for t, c in type_counts.items():
            print(f"    {t}: {c}")
        print("  =====================\n")


debug = DebugHooks()


class TestUndoStress(unittest.TestCase):
    def setUp(self):
        debug.clear()
        # Use ~/Desktop to ensure Trash is supported (not /tmp which may be tmpfs)
        base_dir = os.path.expanduser("~/Desktop")
        self.test_dir = os.path.join(base_dir, f"stress_undo_{int(time.time())}")
        os.makedirs(self.test_dir, exist_ok=True)

        signals = FileOperationSignals()
        self.registry = BackendRegistry()
        self.registry.set_default_io(GIOBackend())

        self.tm = TransactionManager()
        self.file_ops = FileOperations()
        self.file_ops.setRegistry(self.registry)
        self.undo_mgr = UndoManager(self.tm)
        self.undo_mgr.setFileOperations(self.file_ops)
        self.tm.setFileOperations(self.file_ops)
        self.file_ops.setTransactionManager(self.tm)

        # Connect standard signals
        self.file_ops.operationFinished.connect(self.tm.onOperationFinished)
        self.file_ops.operationError.connect(self.tm.onOperationError)
        self.file_ops.operationFinished.connect(self.undo_mgr._on_op_finished)

        # Connect DEBUG hooks
        self.file_ops.operationStarted.connect(debug.on_op_started)
        self.file_ops.operationFinished.connect(debug.on_op_finished)
        self.file_ops.operationError.connect(debug.on_op_error)
        self.tm.transactionStarted.connect(debug.on_tx_started)
        self.tm.transactionFinished.connect(debug.on_tx_finished)
        self.tm.historyCommitted.connect(debug.on_history_committed)

        self.undo_finished = False
        self.undo_success = False
        self.last_msg = ""
        self.undo_mgr.operationFinished.connect(self._on_undo_finished)

    def tearDown(self):
        debug.print_summary()
        self.file_ops.shutdown()
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def _on_undo_finished(self, success, msg):
        self.undo_finished = True
        self.undo_success = success
        self.last_msg = msg
        debug.log_event("UNDO_FINISHED", success=success, msg=msg)

    def _wait(self, timeout=10):
        self.undo_finished = False
        start = time.time()
        while not self.undo_finished:
            app.processEvents()
            time.sleep(0.01)
            if time.time() - start > timeout:
                return False
        return True

    def _wait_for_tx(self, tid, timeout=10):
        start = time.time()
        while tid in self.tm._active_transactions:
            app.processEvents()
            time.sleep(0.01)
            if time.time() - start > timeout:
                print(f"  [WARN] Transaction {tid[:8]} timed out")
                return False
        time.sleep(0.05)  # Debounce
        return True

    def test_01_single_op_trace(self):
        """Test 0: Trace a SINGLE operation to verify ID flow."""
        print("\n[TEST] Single Operation ID Trace")

        p = os.path.join(self.test_dir, "SingleTest")

        # Start Transaction
        tid = self.tm.startTransaction("Single Op")
        print(f"  Started TID: {tid[:8]}")

        # Check what addOperation does
        # We'll peek at the internal state
        print(
            f"  Active TXs before createFolder: {list(self.tm._active_transactions.keys())}"
        )

        # Create folder (this should call addOperation internally)
        job_id = self.file_ops.createFolder(p, tid)
        print(f"  createFolder returned JID: {job_id[:8]}")
        self.tm.commitTransaction(tid)

        # Check TM state immediately
        if tid in self.tm._active_transactions:
            tx = self.tm._active_transactions[tid]
            print(f"  TX has {len(tx.ops)} operations:")
            for op in tx.ops:
                print(
                    f"    - op_type={op.op_type}, job_id={op.job_id[:8] if op.job_id else 'NONE'}"
                )

        # Wait for completion
        self._wait_for_tx(tid)

        # Check history
        print(f"  Undo stack size: {len(self.undo_mgr._undo_stack)}")
        if self.undo_mgr._undo_stack:
            last = self.undo_mgr._undo_stack[-1]
            print(f"  Last TX in Undo: {last.id[:8]}, ops={len(last.ops)}")
            for op in last.ops:
                print(
                    f"    - op_type={op.op_type}, job_id={op.job_id[:8] if op.job_id else 'NONE'}, status={op.status}"
                )

        self.assertTrue(os.path.exists(p))

    def test_02_rapid_fire_undo(self):
        """Test 1: Create 10 folders, then UNDO them rapidly."""
        print("\n[TEST] Rapid Fire Undo (10 ops)")

        NUM = 10

        # 1. Generate History
        for i in range(NUM):
            p = os.path.join(self.test_dir, f"Rapid_{i}")
            tid = self.tm.startTransaction(f"Create_{i}")
            job_id = self.file_ops.createFolder(p, tid)
            self.tm.commitTransaction(tid)
            print(f"  Created TX {tid[:8]} -> JID {job_id[:8]}")
            self._wait_for_tx(tid)

        print(f"  Undo stack size: {len(self.undo_mgr._undo_stack)}")

        # 2. Rapid Undo (with waiting to ensure serial completion)
        print("  Triggering Undos...")
        for i in range(NUM):
            if not self.undo_mgr.can_undo():
                print(f"  [FAIL] Stack empty at index {i}")
                break

            self.undo_mgr.undo()
            res = self._wait(timeout=5)
            print(f"    Undo {i}: success={self.undo_success}")

        # Check results
        remaining = [x for x in os.listdir(self.test_dir) if "Rapid_" in x]
        print(f"  Remaining folders: {len(remaining)} (Expected 0)")

    def test_03_batch_undo(self):
        """Test 2: Undo a single transaction with 20 items."""
        print("\n[TEST] Batch Undo (20 items)")

        NUM = 20
        tid = self.tm.startTransaction("Batch Create")
        print(f"  Batch TID: {tid[:8]}")

        for i in range(NUM):
            p = os.path.join(self.test_dir, f"Batch_{i}")
            job_id = self.file_ops.createFolder(p, tid)
        self.tm.commitTransaction(tid)

        self._wait_for_tx(tid, timeout=15)

        # Check TX recorded correctly
        print(f"  Undo stack size: {len(self.undo_mgr._undo_stack)}")
        if self.undo_mgr._undo_stack:
            last = self.undo_mgr._undo_stack[-1]
            print(f"  Last TX: {len(last.ops)} ops")

        print("  Undoing Batch...")
        self.undo_mgr.undo()
        res = self._wait(timeout=30)

        print(f"  Result: Success={self.undo_success}")
        remaining = [x for x in os.listdir(self.test_dir) if "Batch_" in x]
        print(f"  Remaining files: {len(remaining)} (Expected 0)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
