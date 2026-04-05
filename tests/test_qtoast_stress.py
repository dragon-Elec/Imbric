#!/usr/bin/env python3
"""
Stress Test: GIO QTOAST Orchestrator Robustness
Validates: Concurrency, Cancellation, Memory Leaks, and Priority Queueing.
"""

import sys
import os
import time
import threading
import unittest
from typing import Any

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PySide6.QtCore import QCoreApplication, QTimer, Slot, QObject
from core.threading.worker_pool import AsyncWorkerPool

app = QCoreApplication.instance() or QCoreApplication(sys.argv)


class StressMonitor(QObject):
    """Tracks signals and stats during stress tests."""

    def __init__(self):
        super().__init__()
        self.results = []
        self.errors = []
        self.progress = []
        self.completed_batches = set()
        self.batch_counts = {}  # batch_id -> count

    def reset(self):
        self.results.clear()
        self.errors.clear()
        self.progress.clear()
        self.completed_batches.clear()
        self.batch_counts.clear()

    @Slot(str, object)
    def on_result(self, task_id, result):
        self.results.append((task_id, result))

    @Slot(str, str)
    def on_error(self, task_id, error):
        self.errors.append((task_id, error))

    @Slot(str, int, int)
    def on_progress(self, task_id, current, total):
        self.progress.append((task_id, current, total))

    @Slot(str)
    def on_batch_done(self, batch_id):
        self.completed_batches.add(batch_id)


monitor = StressMonitor()


class TestQToastStress(unittest.TestCase):
    def setUp(self):
        monitor.reset()
        self.pool = AsyncWorkerPool(max_concurrent=4)
        self.pool.resultReady.connect(monitor.on_result)
        self.pool.errorOccurred.connect(monitor.on_error)
        self.pool.progressUpdated.connect(monitor.on_progress)
        self.pool.allTasksDone.connect(monitor.on_batch_done)

    def tearDown(self):
        self.pool.clear()
        # Small delay for thread pool cleanup
        time.sleep(0.1)

    def _wait_for(self, condition, timeout=10.0):
        start = time.time()
        while not condition():
            app.processEvents()
            time.sleep(0.001)
            if time.time() - start > timeout:
                return False
        return True

    def mock_worker(self, name: str, delay: float = 0.0, **kwargs):
        """Standard mock worker for testing logic."""
        # Check for injected cancel event
        cancel_evt = kwargs.get("cancel_event")

        # Simulate work with cooperative cancellation
        start_time = time.time()
        while time.time() - start_time < delay:
            if cancel_evt and cancel_evt.is_set():
                return "CANCELLED"
            time.sleep(0.005)  # Fine grained sleep

        return f"SUCCESS_{name}"

    def test_01_zombie_apocalypse(self):
        """SCENARIO 1: Immediate Cancellation of active threads."""
        print("\n[STRESS] Scenario 1: Zombie Apocalypse (Cancellation)")

        # 10 batches, 5 tasks each = 50 tasks
        BATCH_COUNT = 10
        TASKS_PER_BATCH = 5

        for b in range(BATCH_COUNT):
            bid = f"batch_{b}"
            tasks = [
                (f"{bid}_{t}", self.mock_worker, (f"{t}", 0.5), {})
                for t in range(TASKS_PER_BATCH)
            ]
            self.pool.enqueue_batch(tasks, bid, inject_cancel=True)

        # Let them start
        print("  -> Tasks enqueued, waiting for pool saturation...")
        time.sleep(0.1)

        # Kill half the batches
        victims = [f"batch_{i}" for i in range(5)]
        print(f"  -> Terminating batches: {victims}")
        for vid in victims:
            self.pool.clear(vid)

        start_wait = time.time()
        # Remaining: 5 batches * 5 tasks = 25 tasks. 4 threads. ~3-4s.
        self._wait_for(lambda: len(monitor.completed_batches) == 5, timeout=10)
        duration = time.time() - start_wait

        print(f"  -> Duration: {duration:.2f}s")
        print(f"  -> Batches completed: {monitor.completed_batches}")
        self.assertEqual(len(monitor.completed_batches), 5)

    def test_02_thundering_herd(self):
        """SCENARIO 2: Mutex safety under heavy signal load."""
        print("\n[STRESS] Scenario 2: Thundering Herd (5k Fast Tasks)")

        COUNT = 5000
        bid = "herd_batch"
        tasks = [(f"task_{i}", lambda **kwargs: "ok", (), {}) for i in range(COUNT)]

        self.pool.enqueue_batch(tasks, bid)

        self._wait_for(lambda: bid in monitor.completed_batches, timeout=20)

        # Verify stats integrity
        stats = self.pool.get_batch_stats(bid)
        print(f"  -> Stats: {stats}")
        self.assertEqual(stats["done"], COUNT, "Signal loss detected! Mutex issue?")
        self.assertEqual(len(monitor.results), COUNT)

    def test_03_memory_sieve(self):
        """SCENARIO 3: Leak detection for batch tracking dicts."""
        print("\n[STRESS] Scenario 3: Memory Sieve (Batch Tracking Cleanup)")

        NUM_BATCHES = 500
        for i in range(NUM_BATCHES):
            bid = f"mini_{i}"
            # Faster completion - use direct return
            self.pool.enqueue(f"t_{i}", lambda: "ok", batch_id=bid)

        self._wait_for(
            lambda: len(monitor.completed_batches) == NUM_BATCHES, timeout=15
        )

        # Cleanup is automatic in AsyncWorkerPool now (it cleans up in _on_task_end)
        # But let's verify if anything is left
        self.assertEqual(
            len(self.pool._pending_batches), 0, "Leaked entries in _pending_batches"
        )
        self.assertEqual(
            len(self.pool._batch_events), 0, "Leaked entries in _batch_events"
        )
        # _batch_stats might remain unless forget_batch is called,
        # but let's check current implementation behavior
        print(
            f"  -> Internal dict state: pending={len(self.pool._pending_batches)}, events={len(self.pool._batch_events)}"
        )

    def test_04_priority_squeeze(self):
        """SCENARIO 4: Priority queue integrity under load."""
        print("\n[STRESS] Scenario 4: Priority Squeeze (Starvation Test)")

        # 1. Fill pool with blockers
        block_evt = threading.Event()

        def blocker(**kwargs):
            block_evt.wait(5.0)
            return "DONE_BLOCK"

        for i in range(4):  # max_concurrent
            self.pool.enqueue(f"blocker_{i}", blocker, priority=50)

        # 2. Add Low Prio mass
        for i in range(100):
            self.pool.enqueue(f"low_{i}", lambda **kwargs: "LOW", priority=100)

        # 3. Add the Urgent task
        self.pool.enqueue("URGENT", lambda **kwargs: "HIGH", priority=1)

        # 4. Release blockers
        print("  -> Releasing blockers...")
        block_evt.set()

        # 5. Wait for URGENT
        self._wait_for(
            lambda: any(r[0] == "URGENT" for r in monitor.results), timeout=5
        )

        # Check: URGENT should complete (priority queue working)
        res_ids = [r[0] for r in monitor.results]
        if "URGENT" not in res_ids:
            print(f"  -> ERROR: URGENT not found. Monitor Errors: {monitor.errors[:5]}")
            self.fail("URGENT task failed or never ran")

        urgent_idx = res_ids.index("URGENT")
        print(f"  -> URGENT task index: {urgent_idx}")
        # With priority=1 (highest), URGENT should run before low-prio tasks
        # It may be among first results when blockers finish and queue is drained
        self.assertLessEqual(
            urgent_idx, 50, "Priority starvation detected! URGENT took too long."
        )

    def test_05_rapid_thrash(self):
        """SCENARIO 5: State Machine robustness."""
        print("\n[STRESS] Scenario 5: Rapid Thrash (Enqueue/Clear Loop)")

        for i in range(50):
            bid = f"thrash_{i}"
            tasks = [(f"t{j}", self.mock_worker, ("x", 0.1), {}) for j in range(5)]
            self.pool.enqueue_batch(tasks, bid)
            self.pool.clear(bid)

        # After thrashing, ensure we can still run a normal task
        self.pool.enqueue("final", lambda **kwargs: "ALIVE")
        success = self._wait_for(
            lambda: any(r[0] == "final" for r in monitor.results), timeout=5
        )
        if not success:
            print(
                f"  -> Monitor stats: active={self.pool._active_count}, queue={len(self.pool._queue)}"
            )

        self.assertTrue(success, "Pool deadlocked after state thrashing")
        print("  -> Pool is still ALIVE")


if __name__ == "__main__":
    print("🚀 STARTING GIO QTOAST STRESS SUITE")
    unittest.main(verbosity=1)
