"""--failed filter, memory fallback, and --force note tests.

Pins:
- _get_previously_failed_test_classes ignores benchmark reports:
  TEST-*Benchmark.xml shares build/test-results/test/ with real
  test reports, and a failing benchmark must not be resurrected
  as a previously failed test class. Normal failing classes are
  still picked up. The scan runs against a temp sandbox via
  patched PROJECT_ROOT (no repo files are read).
- memory breakdown: an unreadable smaps_rollup leaves pss at 0
  (rendered "?"); PSS is never derived from VmSize, which is
  virtual address space, not proportional set size. run() reads
  each process's breakdown exactly once.
- processes --force without --kill prints the conflict note to
  stderr and kills nothing (ProcessManager.get_status is stubbed
  to empty; kill_all is never reached).
"""

import argparse
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.ib.commands import memory, processes
from scripts.ib.commands import test as test_cmd
from scripts.ib.process import ProcessInfo, ProcessManager


class TestFailedFilter(unittest.TestCase):
    BENCH_XML = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="com.imbric.core.desktop.backends.GioRecentBackendBenchmark" tests="2" failures="1">
    <testcase name="benchmarkRecent" classname="com.imbric.core.desktop.backends.GioRecentBackendBenchmark" time="1.0">
        <failure message="bench failed" type="AssertionError">trace</failure>
    </testcase>
    <testcase name="benchmarkEnumerate" classname="com.imbric.core.desktop.backends.GioRecentBackendBenchmark" time="2.0"/>
</testsuite>
"""
    BENCH_ERROR_XML = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="com.imbric.core.desktop.backends.GioRecentBackendBenchmark" tests="1" errors="1">
    <testcase name="benchmarkRecent" classname="com.imbric.core.desktop.backends.GioRecentBackendBenchmark" time="1.0">
        <error message="boom" type="RuntimeException">trace</error>
    </testcase>
</testsuite>
"""
    FAILING_XML = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="com.imbric.core.foo.BrokenTest" tests="1" failures="1">
    <testcase name="testThing" classname="com.imbric.core.foo.BrokenTest" time="0.1">
        <failure message="assertion failed" type="AssertionError">trace</failure>
    </testcase>
</testsuite>
"""

    def _scan(self, root):
        with mock.patch.object(test_cmd, "PROJECT_ROOT", root):
            return test_cmd._get_previously_failed_test_classes()

    @staticmethod
    def _write_results(root, files):
        results = Path(root) / "build" / "test-results" / "test"
        results.mkdir(parents=True)
        for name, content in files.items():
            (results / name).write_text(content)

    def test_benchmark_failure_excluded_normal_failure_included(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write_results(tmp, {
                "TEST-com.imbric.core.desktop.backends.GioRecentBackendBenchmark.xml":
                    self.BENCH_XML,
                "TEST-com.imbric.core.foo.BrokenTest.xml": self.FAILING_XML,
            })
            failed = self._scan(Path(tmp))
        self.assertEqual(failed, ["BrokenTest"])

    def test_benchmark_error_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write_results(tmp, {
                "TEST-com.imbric.core.desktop.backends.GioRecentBackendBenchmark.xml":
                    self.BENCH_ERROR_XML,
            })
            failed = self._scan(Path(tmp))
        self.assertEqual(failed, [])

    def test_no_results_dir_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            failed = self._scan(Path(tmp))
        self.assertEqual(failed, [])


class TestMemoryBreakdown(unittest.TestCase):
    PID = 4242
    SMAPS_ROLLUP = (
        "Rss:            2048 kB\n"
        "Pss:            1500 kB\n"
        "Shared_Clean:    500 kB\n"
        "Shared_Dirty:    100 kB\n"
        "Private_Clean:   300 kB\n"
        "Private_Dirty:   600 kB\n"
        "Swap:              0 kB\n"
    )
    STATUS = "Name:\tjava\nVmRSS:\t  1024 kB\nVmSize:\t40000000 kB\n"

    def _fake_open(self, smaps=None, status=None):
        """open() replacement: smaps_rollup/status served from strings.

        None means "unreadable" (raises FileNotFoundError).
        """
        def fake_open(path, *a, **kw):
            path = str(path)
            if path.endswith("smaps_rollup"):
                if smaps is None:
                    raise FileNotFoundError(path)
                return io.StringIO(smaps)
            if path == f"/proc/{self.PID}/status":
                if status is None:
                    raise FileNotFoundError(path)
                return io.StringIO(status)
            raise FileNotFoundError(path)
        return fake_open

    def test_smaps_rollup_parsed(self):
        with mock.patch.object(memory, "open",
                             self._fake_open(smaps=self.SMAPS_ROLLUP),
                             create=True):
            breakdown = memory._get_memory_breakdown(self.PID)
        self.assertEqual(breakdown["rss"], 2048)
        self.assertEqual(breakdown["pss"], 1500)
        self.assertEqual(breakdown["shared"], 600)
        self.assertEqual(breakdown["private"], 900)
        self.assertEqual(breakdown["swap"], 0)

    def test_unreadable_smaps_never_derives_pss_from_vmsize(self):
        # smaps_rollup unreadable, status carries a ~40GB VmSize.
        with mock.patch.object(memory, "open",
                             self._fake_open(status=self.STATUS),
                             create=True):
            breakdown = memory._get_memory_breakdown(self.PID)
        # RSS falls back to VmRSS (a real measurement) ...
        self.assertEqual(breakdown["rss"], 1024)
        # ... but PSS stays 0 instead of being faked from VmSize.
        self.assertEqual(breakdown["pss"], 0)
        self.assertEqual(breakdown["shared"], 0)
        self.assertEqual(breakdown["private"], 0)
        self.assertEqual(breakdown["swap"], 0)

    def test_all_unavailable_renders_question_marks(self):
        with mock.patch.object(memory, "open", self._fake_open(),
                             create=True):
            breakdown = memory._get_memory_breakdown(self.PID)
        self.assertEqual(
            breakdown,
            {"rss": 0, "pss": 0, "shared": 0, "private": 0, "swap": 0})
        proc = ProcessInfo(pid=self.PID, cmd="java -jar", mem="")
        row = memory._format_process(proc, verbose=True, breakdown=breakdown)
        self.assertEqual(row.count("?"), 5)

    def test_formatter_shows_question_for_unavailable_pss(self):
        breakdown = {"rss": 1024, "pss": 0, "shared": 0, "private": 0, "swap": 0}
        proc = ProcessInfo(pid=self.PID, cmd="java -jar", mem="")
        row = memory._format_process(proc, verbose=True, breakdown=breakdown)
        self.assertIn("?", row)
        # Neither the raw VmSize nor its ~38GB rendering may appear.
        self.assertNotIn("40000000", row)
        self.assertNotIn("GB", row)
        self.assertIn("1024KB", row)

    def test_run_reads_each_process_once(self):
        # run() used to read the breakdown twice per process (once for
        # the row, once for the totals); the same dict must feed both.
        status = {"app_processes": [
            ProcessInfo(pid=self.PID, cmd="java -jar", mem="")]}
        reads = []

        def counting_breakdown(pid):
            reads.append(pid)
            return {"rss": 2048, "pss": 1500, "shared": 600,
                    "private": 900, "swap": 0}

        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(ProcessManager, "get_status",
                             return_value=status), \
             mock.patch.object(memory, "_get_memory_breakdown",
                             counting_breakdown), \
             contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            memory.run(argparse.Namespace(verbose=True))
        self.assertEqual(reads, [self.PID])
        self.assertIn("Total PSS", out.getvalue())


class TestProcessesForceNote(unittest.TestCase):
    EMPTY_STATUS = {name: [] for name in (
        "gradle_daemons", "kotlin_daemons", "app_processes",
        "gradlew_processes", "hotreload_devtools")}

    def _run(self, force):
        out, err = io.StringIO(), io.StringIO()
        args = argparse.Namespace(force=force, kill=False, verbose=False)
        with mock.patch.object(ProcessManager, "get_status",
                             return_value=self.EMPTY_STATUS), \
             contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            processes.run(args)
        return out.getvalue(), err.getvalue()

    def test_force_without_kill_prints_note(self):
        out, err = self._run(force=True)
        self.assertIn("note: --force ignored without --kill", err)
        self.assertIn("No processes running.", out)

    def test_no_note_without_force(self):
        out, err = self._run(force=False)
        self.assertNotIn("--force", err)
        self.assertIn("No processes running.", out)


if __name__ == "__main__":
    unittest.main()
