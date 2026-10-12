"""Stacktrace compression in `ib test` failure output.

When a test fails, `test.py` used to print every `at ...` frame raw —
org.gradle / jdk.internal frames buried the com.imbric frame you need.
test.py now buffers stack frames inside an error block and flushes them
through compressor.compress_stacktrace, which keeps app frames and
summarizes internal framework frames.

These tests drive test.run() through the same FakeProc + mock.patch(Popen)
seam as test_exit_codes.py: no Gradle, no subprocess.
"""
import argparse
import contextlib
import io
import unittest
from unittest import mock

from ib.commands import test as test_cmd


class FakeProc:
    """Stub for subprocess.Popen: iterable stdout, wait()."""

    def __init__(self, lines=None, returncode=0):
        self.stdout = iter(lines or [])
        self.returncode = returncode

    def wait(self):
        return self.returncode

    def terminate(self):
        pass


class TestStacktraceCompression(unittest.TestCase):
    # A realistic Gradle test-failure block: task line, FAILED header,
    # the exception message, app frames, framework frames, JUnit's
    # "... N more", then the BUILD FAILED banner.
    FAILURE_BLOCK = [
        "> Task :test",
        "",
        "SomeTest > someTest FAILED",
        "    org.opentest4j.AssertionFailedError: expected: <1> but was: <3>",
        "        at com.imbric.core.SomeClass.someMethod(SomeClass.kt:42)",
        "        at com.imbric.core.OtherClass.otherMethod(OtherClass.kt:10)",
        "        at org.gradle.internal.SomeRunner.run(SomeRunner.kt:1)",
        "        at org.gradle.internal.OtherRunner.run(OtherRunner.kt:2)",
        "        at jdk.internal.reflect.NativeMethodAccessor.invoke(NativeMethodAccessor.java:1)",
        "        ... 15 more",
        "",
        "BUILD FAILED in 5s",
    ]

    @staticmethod
    def _run_test_cmd(proc):
        out, err = io.StringIO(), io.StringIO()
        # run() returns normally on success (exit 0) and only
        # raises SystemExit on failure — so default to 0 and
        # let a real sys.exit override it.
        code = 0
        with mock.patch.object(
                test_cmd, "_get_previously_failed_test_classes", return_value=[]), \
             mock.patch.object(test_cmd.subprocess, "Popen", return_value=proc), \
             contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                test_cmd.run(argparse.Namespace(
                    tests=None, failed=False, rerun=False,
                    continue_on_fail=False, warnings=False))
            except SystemExit as e:
                code = e.code
        return out.getvalue(), err.getvalue(), code

    def test_framework_frames_collapsed_app_frames_kept(self):
        out, _, code = self._run_test_cmd(FakeProc(self.FAILURE_BLOCK, returncode=1))
        # App frames survive — they are the frames you debug.
        self.assertIn("at com.imbric.core.SomeClass.someMethod", out)
        self.assertIn("at com.imbric.core.OtherClass.otherMethod", out)
        # Framework frames are summarized, not printed raw.
        self.assertIn("internal framework frames skipped", out)
        self.assertNotIn("at org.gradle.internal.SomeRunner.run", out)
        self.assertNotIn("at jdk.internal.reflect.NativeMethodAccessor.invoke", out)
        # The exception message — the actual assertion failure — is never
        # buffered away; it prints immediately.
        self.assertIn("expected: <1> but was: <3>", out)
        # Exit code still propagates from the child.
        self.assertEqual(code, 1)

    def test_stack_flushes_before_build_banner(self):
        # Frames buffered, then the BUILD banner (no task boundary between)
        # must still flush them — the after-loop flush covers it.
        out, _, _ = self._run_test_cmd(FakeProc(self.FAILURE_BLOCK, returncode=1))
        # The compressed summary appears before BUILD FAILED, not after.
        self.assertLess(
            out.index("internal framework frames skipped"),
            out.index("BUILD FAILED"))

    def test_no_stack_no_summary(self):
        # A clean run (no failure) must not emit any "frames skipped" line.
        out, _, code = self._run_test_cmd(
            FakeProc(["FooTest > bar PASSED", "BUILD SUCCESSFUL in 5s"], returncode=0))
        self.assertNotIn("internal framework frames skipped", out)
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
