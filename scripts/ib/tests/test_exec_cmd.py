"""exec passthrough and ProcessManager.kill_all tests.

Pins:
- exec: arbitrary-command output is a raw passthrough — lines
  starting with "> " or "* " (and everything else) reach stdout
  unchanged, since an arbitrary command's output must not be
  treated as Gradle noise.
- exec: non-zero child returncode propagates as SystemExit(code).
- exec: missing executable -> "executable not found" on stderr,
  exit 127.
- kill_all: the same PID found by several patterns (and again by
  the survivor pass) is returned once, first-seen order kept, so
  "Killed N process(es)" does not over-count.

All Popen/pgrep boundaries are stubbed (module-level subprocess
mock, and ProcessManager.find_processes / kill_pid); nothing real
executes.
"""

import argparse
import contextlib
import io
import os
import unittest
from unittest import mock

from scripts.ib.commands import exec_cmd
from scripts.ib.process import (
    GRADLEW_PATTERN, ProcessInfo, ProcessManager,
)


class FakeProc:
    """Stub for subprocess.Popen: iterable stdout, wait(), terminate()."""

    def __init__(self, lines=None, returncode=0):
        self.stdout = iter(lines or [])
        self.returncode = returncode

    def wait(self):
        return self.returncode

    def terminate(self):
        pass


class TestExecPassthrough(unittest.TestCase):
    @staticmethod
    def _run_exec(proc=None, popen_side_effect=None):
        """Run exec_cmd.run with Popen stubbed.

        Returns (out, err, exit_code); exit_code is None when no
        SystemExit.
        """
        out, err = io.StringIO(), io.StringIO()
        code = None
        if popen_side_effect is not None:
            p = mock.patch.object(exec_cmd.subprocess, "Popen",
                                  side_effect=popen_side_effect)
        else:
            p = mock.patch.object(exec_cmd.subprocess, "Popen",
                                  return_value=proc)
        with p, contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err):
            try:
                exec_cmd.run(argparse.Namespace(cmd=["diff", "a", "b"]))
            except SystemExit as e:
                code = e.code
        return out.getvalue(), err.getvalue(), code

    def test_gradle_style_lines_pass_through_unchanged(self):
        # "> " and "* " lines are exactly what OutputFilter used
        # to drop; an arbitrary command (e.g. diff) emits them.
        lines = ["> Task :app:compileKotlin", "* What went wrong:",
                 "BUILD FAILED in 1s", "plain stdout line"]
        out, _, code = self._run_exec(FakeProc(lines, returncode=0))
        self.assertIsNone(code)
        for line in lines:
            self.assertIn(line, out)
        self.assertIn("Running: diff a b", out)
        self.assertIn("Completed in", out)

    def test_nonzero_returncode_propagates(self):
        out, _, code = self._run_exec(FakeProc([], returncode=3))
        self.assertEqual(code, 3)
        self.assertIn("Failed (code 3)", out)

    def test_missing_executable_exits_127(self):
        out, err, code = self._run_exec(
            popen_side_effect=FileNotFoundError(2, "No such file or directory"))
        self.assertEqual(code, 127)
        self.assertIn("executable not found: diff", err)
        self.assertIn("Running: diff a b", out)


class TestKillAllDedupe(unittest.TestCase):
    # Never os.getpid(): kill_all skips its own PID, and kill_pid
    # is stubbed, so the value only has to survive that check.
    FAKE_PID = os.getpid() + 1

    def _run_kill_all(self, find, force):
        with mock.patch.object(ProcessManager, "find_processes",
                               side_effect=find), \
             mock.patch.object(ProcessManager, "kill_pid",
                               return_value=True), \
             mock.patch("time.sleep"):
            return ProcessManager.kill_all(force=force)

    @staticmethod
    def _procs(*pids):
        return [ProcessInfo(pid=pid, cmd=f"fake {pid}", mem="")
                for pid in pids]

    def test_dedupes_across_patterns_force_true(self):
        # Every pattern reports the same PID — it must be returned
        # (and counted) once.
        killed = self._run_kill_all(
            lambda pattern: self._procs(self.FAKE_PID), force=True)
        self.assertEqual(killed, [str(self.FAKE_PID)])

    def test_survivor_pass_does_not_reappend_pid(self):
        # force=False: the SIGTERM'd PID is "found again" by the
        # survivor pass and SIGKILLed — still exactly one entry.
        killed = self._run_kill_all(
            lambda pattern: self._procs(self.FAKE_PID), force=False)
        self.assertEqual(killed, [str(self.FAKE_PID)])
        self.assertEqual(killed.count(str(self.FAKE_PID)), 1)

    def test_dedupe_preserves_first_seen_order(self):
        first, second = self.FAKE_PID, self.FAKE_PID + 1

        def find(pattern):
            # The first pattern sees [first, second]; every other
            # pattern (and the survivor pass) sees them reversed.
            if pattern == GRADLEW_PATTERN:
                return self._procs(first, second)
            return self._procs(second, first)

        killed = self._run_kill_all(find, force=False)
        self.assertEqual(killed, [str(first), str(second)])


if __name__ == "__main__":
    unittest.main()
