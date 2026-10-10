"""OutputFilter contract tests (scripts/ib/filter.py) + test.py dot rendering.

Pins:
- BUILD SUCCESSFUL / BUILD FAILED lines are swallowed (return None) and flush
  any pending dots; callers print their own single summary line.
- "w: ..." lines are collected (never passed through); flush_warnings writes a
  count summary by default and the grouped block with show_warnings=True.
- Error lines pass through unfiltered.
- test.py's inline renderer: dots for PASSED lines are separated from the
  BUILD SUCCESSFUL summary by a newline (dots not glued).

test.py's renderer is inline in run() (no seam), so it is exercised by
driving run() with a stub Popen whose stdout yields exact Gradle lines.
"""

import argparse
import contextlib
import io
import unittest
from unittest import mock

from scripts.ib.filter import OutputFilter
from scripts.ib.commands import test as test_cmd


class FakeProc:
    """Stub for subprocess.Popen: iterable stdout, wait(), terminate()."""

    def __init__(self, lines=None, returncode=0):
        self.stdout = iter(lines or [])
        self.returncode = returncode

    def wait(self):
        return self.returncode

    def terminate(self):
        pass


class TestBuildLinesAreSwallowed(unittest.TestCase):
    def test_build_successful_returns_none(self):
        self.assertIsNone(OutputFilter().filter_line("BUILD SUCCESSFUL in 5s"))

    def test_build_failed_returns_none(self):
        self.assertIsNone(OutputFilter().filter_line("BUILD FAILED in 3s"))

    def test_build_line_flushes_pending_dots(self):
        f = OutputFilter()
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            f.filter_line("> Task :someLib")  # non-key task -> one dot
            self.assertEqual(f.dot_count, 1)
            self.assertIsNone(f.filter_line("BUILD SUCCESSFUL in 5s"))
            self.assertEqual(f.dot_count, 0)  # dots flushed before swallowing


class TestWarningCollection(unittest.TestCase):
    def test_warning_collected_and_not_passed_through(self):
        f = OutputFilter()  # show_warnings=False by default
        line = "w: Unnecessary non-null assertion (!!)"
        self.assertIsNone(f.filter_line(line))
        self.assertEqual(f.warnings, [line])

    def test_flush_warnings_writes_count_summary_by_default(self):
        f = OutputFilter()
        f.filter_line("w: something")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            f.flush_warnings()
        self.assertIn("[1 warning (use -w / --warnings to view)]", err.getvalue())

    def test_flush_warnings_writes_grouped_block_when_enabled(self):
        f = OutputFilter(show_warnings=True)
        f.filter_line("w: file:///src/App.kt:10:5 No cast needed.")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            f.flush_warnings()
        self.assertIn("--- 1 Compiler Warning ---", err.getvalue())

    def test_no_warnings_no_summary(self):
        f = OutputFilter()
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            f.flush_warnings()
        self.assertEqual(err.getvalue(), "")


class TestErrorPassthrough(unittest.TestCase):
    def test_compiler_error_line_passes_through(self):
        f = OutputFilter()
        line = "e: file:///src/App.kt:42:10 Unresolved reference 'foo'"
        self.assertEqual(f.filter_line(line), line)
        self.assertTrue(f.in_error)

    def test_failed_token_line_passes_through(self):
        f = OutputFilter()
        line = "Execution FAILED for task ':test'."
        self.assertEqual(f.filter_line(line), line)

    def test_exception_line_passes_through(self):
        f = OutputFilter()
        line = "java.lang.Exception: boom"
        self.assertEqual(f.filter_line(line), line)


class TestDotRendering(unittest.TestCase):
    def test_dots_not_glued_to_build_summary(self):
        # Exact Gradle lines from a passing test run.
        proc = FakeProc(lines=[
            "FooTest > bar PASSED\n",
            "> Task :test\n",
            "BUILD SUCCESSFUL in 5s\n",
        ], returncode=0)
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(test_cmd.subprocess, "Popen", return_value=proc):
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                test_cmd.run(argparse.Namespace(
                    tests=None, failed=False, rerun=False, continue_on_fail=False))
        printed = out.getvalue()
        self.assertIn(".", printed)                       # dot for the passed test
        self.assertIn("BUILD SUCCESSFUL in 5s", printed)  # gradle summary passes through
        self.assertIn(".\n", printed)                     # newline between dots and summary
        self.assertNotIn(".BUILD SUCCESSFUL", printed)    # ...never glued

    def test_passing_proc_reports_success(self):
        proc = FakeProc(lines=["BUILD SUCCESSFUL in 5s\n"], returncode=0)
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(test_cmd.subprocess, "Popen", return_value=proc):
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                test_cmd.run(argparse.Namespace(
                    tests=None, failed=False, rerun=False, continue_on_fail=False))
        self.assertIn("Tests completed successfully", out.getvalue())


if __name__ == "__main__":
    unittest.main()
