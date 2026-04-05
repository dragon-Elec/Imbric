import pytest
import time
from pathlib import Path
import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

from core.models.file_job import FileJob, FileOperationSignals
from core.backends.gio.io_ops import BatchTransferRunnable


def test_batch_partial_failure_continue(temp_dir):
    """
    Test that BatchTransferRunnable continues after an error by default (halt_on_error=False).
    """
    # Create mock source files
    num_files = 5
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

    signals = FileOperationSignals()
    finished_emissions = []

    def on_batch_finished(tid, success_list, failed_list):
        finished_emissions.append((tid, success_list, failed_list))

    signals.batchFinished.connect(on_batch_finished)

    # We will simulate a failure on the 3rd file (index 2)
    class FailingBatchTransferRunnable(BatchTransferRunnable):
        def _perform_single_transfer(
            self, source, base_dest, op_type, overwrite, auto_rename
        ):
            if "src_2" in source:
                raise Exception("Simulated permission denied")
            return super()._perform_single_transfer(
                source, base_dest, op_type, overwrite, auto_rename
            )

    job = FileJob(
        id="batch_job_1",
        op_type="batch_transfer",
        source=sources[0],
        transaction_id="tx_1",
        items=batch_items,
        ui_refresh_rate_ms=100,
        halt_on_error=False,
    )

    runnable = FailingBatchTransferRunnable(job, signals)
    runnable.run()

    assert len(finished_emissions) == 1
    tid, success_list, failed_list = finished_emissions[0]

    assert tid == "tx_1"
    assert len(success_list) == 4
    assert len(failed_list) == 1
    assert failed_list[0]["job_id"] == "job_2"
    assert "Simulated permission denied" in failed_list[0]["error"]

    # Check that non-failing files were copied
    for i in range(num_files):
        if i == 2:
            assert not Path(dests[i]).exists()
        else:
            assert Path(dests[i]).exists()


def test_batch_partial_failure_halt(temp_dir):
    """
    Test that BatchTransferRunnable stops after an error when halt_on_error=True.
    """
    # Create mock source files
    num_files = 5
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

    signals = FileOperationSignals()
    finished_emissions = []

    def on_batch_finished(tid, success_list, failed_list):
        finished_emissions.append((tid, success_list, failed_list))

    signals.batchFinished.connect(on_batch_finished)

    # We will simulate a failure on the 3rd file (index 2)
    class FailingBatchTransferRunnable(BatchTransferRunnable):
        def _perform_single_transfer(
            self, source, base_dest, op_type, overwrite, auto_rename
        ):
            if "src_2" in source:
                raise Exception("Simulated permission denied")
            return super()._perform_single_transfer(
                source, base_dest, op_type, overwrite, auto_rename
            )

    job = FileJob(
        id="batch_job_1",
        op_type="batch_transfer",
        source=sources[0],
        transaction_id="tx_1",
        items=batch_items,
        ui_refresh_rate_ms=100,
        halt_on_error=True,
    )

    runnable = FailingBatchTransferRunnable(job, signals)
    runnable.run()

    assert len(finished_emissions) == 1
    tid, success_list, failed_list = finished_emissions[0]

    assert tid == "tx_1"
    assert len(success_list) == 2  # indices 0, 1
    assert len(failed_list) == 1  # index 2

    # Check that files after the error were not copied
    assert Path(dests[0]).exists()
    assert Path(dests[1]).exists()
    assert not Path(dests[2]).exists()
    assert not Path(dests[3]).exists()
    assert not Path(dests[4]).exists()
