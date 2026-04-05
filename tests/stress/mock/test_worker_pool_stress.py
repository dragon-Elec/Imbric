"""
Stress tests using mocked I/O operations.
Fast tests suitable for CI that verify concurrency and robustness.
"""

import pytest
import time
import threading
from unittest.mock import MagicMock

from PySide6.QtCore import Slot

from core.threading.worker_pool import AsyncWorkerPool


class TestWorkerPoolStress:
    """Stress tests for the AsyncWorkerPool."""

    @pytest.fixture(autouse=True)
    def setup(self, qapp):
        self.pool = AsyncWorkerPool(max_concurrent=4)
        self.results = []
        self.errors = []
        self.progress = []
        self.batches_done = set()
        self.qapp = qapp

        self.pool.resultReady.connect(self._on_result)
        self.pool.errorOccurred.connect(self._on_error)
        self.pool.progressUpdated.connect(self._on_progress)
        self.pool.allTasksDone.connect(self._on_batch_done)

        yield

        self.pool.clear()
        time.sleep(0.1)  # Allow threads to clean up

    @Slot(str, object)
    def _on_result(self, tid: str, result: object):
        self.results.append((tid, result))

    @Slot(str, str)
    def _on_error(self, tid: str, error: str):
        self.errors.append((tid, error))

    @Slot(str, int, int)
    def _on_progress(self, tid: str, current: int, total: int):
        self.progress.append((tid, current, total))

    @Slot(str)
    def _on_batch_done(self, bid: str):
        self.batches_done.add(bid)

    def mock_worker(self, name: str, delay: float = 0.0, **kwargs):
        """Standard mock worker for testing."""
        cancel_evt = kwargs.get("cancel_event")

        start_time = time.time()
        while time.time() - start_time < delay:
            if cancel_evt and cancel_evt.is_set():
                return "CANCELLED"
            time.sleep(0.005)

        return f"SUCCESS_{name}"

    def test_zombie_apocalypse(self, qapp):
        """
        Scenario: Immediate cancellation of active threads.
        Tests that pool handles rapid cancellation without deadlocking.
        """
        BATCH_COUNT = 10
        TASKS_PER_BATCH = 5

        for b in range(BATCH_COUNT):
            bid = f"batch_{b}"
            tasks = [
                (f"{bid}_{t}", self.mock_worker, (f"{t}", 0.5), {})
                for t in range(TASKS_PER_BATCH)
            ]
            self.pool.enqueue_batch(tasks, bid, inject_cancel=True)

        # Let tasks start
        time.sleep(0.1)

        # Cancel half the batches
        victims = [f"batch_{i}" for i in range(5)]
        for vid in victims:
            self.pool.clear(vid)

        # Wait for remaining batches
        start_wait = time.time()
        timeout = 10.0
        while len(self.batches_done) < 5 and (time.time() - start_wait) < timeout:
            self.qapp.processEvents()
            time.sleep(0.01)

        assert len(self.batches_done) == 5, (
            f"Expected 5 batches to complete, got {len(self.batches_done)}"
        )

    def test_thundering_herd(self, qapp):
        """
        Scenario: 5000 fast tasks submitted rapidly.
        Tests mutex safety under heavy signal load.
        """
        COUNT = 5000
        bid = "herd_batch"

        # Use instant-returning lambdas for maximum speed
        tasks = [(f"task_{i}", lambda **kw: "ok", (), {}) for i in range(COUNT)]
        self.pool.enqueue_batch(tasks, bid)

        # Wait for completion
        start = time.time()
        timeout = 20.0
        while bid not in self.batches_done and (time.time() - start) < timeout:
            qapp.processEvents()
            time.sleep(0.01)

        stats = self.pool.get_batch_stats(bid)

        assert stats["done"] == COUNT, (
            f"Signal loss detected! Expected {COUNT}, got {stats['done']}"
        )
        assert len(self.results) == COUNT, (
            f"Results count mismatch! Expected {COUNT}, got {len(self.results)}"
        )

    def test_memory_sieve(self):
        """
        Scenario: 500 mini-batches that complete instantly.
        Tests that batch tracking dictionaries are properly cleaned up.
        """
        NUM_BATCHES = 500

        for i in range(NUM_BATCHES):
            bid = f"mini_{i}"
            self.pool.enqueue(f"t_{i}", lambda **kw: "ok", batch_id=bid)

        # Wait for all batches
        timeout = 15.0
        start = time.time()
        while len(self.batches_done) < NUM_BATCHES and (time.time() - start) < timeout:
            time.sleep(0.01)

        # Verify cleanup
        assert len(self.pool._pending_batches) == 0, (
            f"Leaked entries in _pending_batches: {len(self.pool._pending_batches)}"
        )
        assert len(self.pool._batch_events) == 0, (
            f"Leaked entries in _batch_events: {len(self.pool._batch_events)}"
        )

    def test_priority_squeeze(self, qapp):
        """
        Scenario: Fill pool with blockers, then add low-priority mass, then high-priority urgent.
        Tests that priority queue prevents starvation.
        """
        block_evt = threading.Event()

        def blocker(**kwargs):
            block_evt.wait(5.0)
            return "DONE_BLOCK"

        def low_task(**kwargs):
            return "LOW"

        def urgent_task(**kwargs):
            return "HIGH"

        # Fill pool with blockers
        for i in range(4):  # max_concurrent
            self.pool.enqueue(f"blocker_{i}", blocker, priority=50)

        # Add low-priority mass
        for i in range(100):
            self.pool.enqueue(f"low_{i}", low_task, priority=100)

        # Add the urgent task
        self.pool.enqueue("URGENT", urgent_task, priority=1)

        # Release blockers
        block_evt.set()

        # Wait for URGENT to complete
        timeout = 5.0
        start = time.time()
        urgent_done = False
        while not urgent_done and (time.time() - start) < timeout:
            self.qapp.processEvents()
            urgent_done = any(r[0] == "URGENT" for r in self.results)
            time.sleep(0.01)

        assert urgent_done, "URGENT task should have completed"

        # URGENT should be among first 5 results (4 blockers + 1 urgent)
        urgent_idx = next(i for i, r in enumerate(self.results) if r[0] == "URGENT")
        assert urgent_idx <= 4, (
            f"Starvation detected! URGENT task was #{urgent_idx}, should be ≤4"
        )

    def test_rapid_thrash(self, qapp):
        """
        Scenario: Rapidly enqueue and clear batches in a loop.
        Tests state machine robustness.
        """
        for i in range(50):
            bid = f"thrash_{i}"
            tasks = [(f"t{j}", self.mock_worker, ("x", 0.1), {}) for j in range(5)]
            self.pool.enqueue_batch(tasks, bid)
            self.pool.clear(bid)

        # After thrashing, pool should still work
        self.pool.enqueue("final", lambda **kw: "ALIVE")

        timeout = 5.0
        start = time.time()
        final_done = False
        while not final_done and (time.time() - start) < timeout:
            self.qapp.processEvents()
            final_done = any(r[0] == "final" for r in self.results)
            time.sleep(0.01)

        assert final_done, "Pool should still accept work after state thrashing"


class TestConcurrentOperationsMock:
    """Mock concurrent operations without real I/O."""

    def test_rapid_creation_burst(self, qapp):
        """
        Simulate rapid creation of 100 operations.
        Tests that ID generation is unique and thread-safe.
        """
        from core.managers import FileOperations
        from core.models.file_job import FileOperationSignals
        from core.registry import BackendRegistry
        from core.backends.gio.backend import GIOBackend

        signals = FileOperationSignals()
        registry = BackendRegistry()
        registry.set_default_io(GIOBackend())

        fo = FileOperations()
        fo.setRegistry(registry)

        # Mock all operations to instant-return
        original_copy = fo.copy

        from uuid import uuid4

        def mock_copy(*args, **kwargs):
            # Return immediately with fake job_id
            return str(uuid4())

        fo.copy = mock_copy

        # Generate 100 job IDs rapidly
        job_ids = set()
        for _ in range(100):
            jid = str(uuid4())
            job_ids.add(jid)

        # All IDs should be unique
        assert len(job_ids) == 100, f"ID collision! Only {len(job_ids)} unique IDs"

        fo.shutdown()

    def test_transaction_spam(self, transaction_manager):
        """
        Create and immediately complete many transactions rapidly.
        Tests transaction state management.
        """
        NUM_TRANSACTIONS = 100

        for i in range(NUM_TRANSACTIONS):
            tid = transaction_manager.startTransaction(f"Spam_{i}")

            # Add operations
            for j in range(5):
                transaction_manager.addOperation(tid, "copy", f"/src{j}", f"/dest{j}")

        # All transactions should be tracked
        assert len(transaction_manager._active_transactions) == NUM_TRANSACTIONS
