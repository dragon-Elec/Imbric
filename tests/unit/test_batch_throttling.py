import pytest
import time
from pathlib import Path

from core.models.file_job import FileJob, FileOperationSignals
from core.backends.gio.io_ops import BatchTransferRunnable


def test_batch_throttling(temp_dir):
    """
    Test that BatchTransferRunnable throttles progress signals to the given refresh rate.
    """
    # Create mock source files
    num_files = 10
    sources = []
    dests = []

    for i in range(num_files):
        src = temp_dir / f"src_{i}.txt"
        src.write_text(f"Content {i}")
        dest = temp_dir / f"dest_{i}.txt"
        sources.append(str(src))
        dests.append(str(dest))

    # Prepare batch items
    batch_items = []
    for i in range(num_files):
        batch_items.append(
            {
                "job_id": f"job_{i}",
                "src": sources[i],
                "dest": dests[i],
                "op_type": "copy",
                "auto_rename": False,
                "overwrite": False,
            }
        )

    # Create signals and track emissions
    signals = FileOperationSignals()
    progress_emissions = []

    def on_batch_progress(tid, completed, total, name):
        progress_emissions.append((time.time(), completed, total, name))

    signals.batchProgress.connect(on_batch_progress)

    # We will simulate a slow copy by monkey patching _perform_single_transfer
    class SlowBatchTransferRunnable(BatchTransferRunnable):
        def _perform_single_transfer(
            self, source, base_dest, op_type, overwrite, auto_rename
        ):
            time.sleep(0.02)  # Simulate 20ms copy per file
            return super()._perform_single_transfer(
                source, base_dest, op_type, overwrite, auto_rename
            )

    job = FileJob(
        id="batch_job_1",
        op_type="batch_transfer",
        source=sources[0],
        transaction_id="tx_1",
        items=batch_items,
        ui_refresh_rate_ms=50,  # 50ms throttle
        halt_on_error=False,
    )

    runnable = SlowBatchTransferRunnable(job, signals)
    runnable.run()

    # 10 files * 20ms = 200ms total time.
    # With 50ms throttle, we expect roughly 200/50 = 4 emissions.
    # The first one fires immediately (since last_emit is 0), and then maybe 3 or 4 more.
    assert 2 <= len(progress_emissions) <= 6, (
        f"Expected throttled emissions, got {len(progress_emissions)}"
    )

    # Check that all files were actually copied
    for dest in dests:
        assert Path(dest).exists()
