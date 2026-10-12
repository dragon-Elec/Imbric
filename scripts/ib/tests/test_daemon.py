"""Daemon lifecycle tests (fully mocked — no real forking or Gradle runs).

Pins:
- stop_daemon(quiet=True) prints nothing, with or without a daemon;
  the default verbose mode still prints the stop messages.
- _wait_for_daemon_pid polls the PID file and gives up after the
  timeout instead of a single fixed sleep.
- _is_clean_stop: hot mode treats exit 0 as a clean stop; continuous
  mode counts any exit (even 0) as a failed attempt, so the daemon
  cannot restart every 5 seconds forever.
- _terminate_child: terminates a live child, escalates to SIGKILL
  when terminate is ignored, no-ops when no child is active.
- start_daemon: fork failure and start failure exit 1; success
  prints the started banner and returns normally.
- _run_daemon: continuous mode gives up after max_crashes attempts
  with backoff; hot mode stops cleanly on exit 0.

os.fork / subprocess.Popen / ProcessManager are stubbed at the module
boundary; nothing real executes.
"""

import contextlib
import io
import subprocess
import unittest
from unittest import mock

from scripts.ib import daemon
from scripts.ib.daemon import DaemonManager


class FakeProc:
    """Popen stub with a scripted lifecycle: iterable stdout, poll,
    terminate, kill, wait."""

    def __init__(self, returncode=0, die_on_terminate=True):
        self._final_returncode = returncode
        self._die_on_terminate = die_on_terminate
        self.returncode = None
        self.stdout = iter([])
        self.terminate_calls = 0
        self.kill_calls = 0
        self.wait_calls = 0

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminate_calls += 1
        if self._die_on_terminate:
            self.returncode = self._final_returncode

    def kill(self):
        self.kill_calls += 1
        self.returncode = self._final_returncode

    def wait(self, timeout=None):
        self.wait_calls += 1
        if self.returncode is None:
            if timeout is not None and not self._die_on_terminate:
                # Still running and ignoring signals: only SIGKILL ends it.
                raise subprocess.TimeoutExpired(cmd="fake", timeout=timeout)
            self.returncode = self._final_returncode
        return self.returncode


class TestStopDaemonQuiet(unittest.TestCase):
    def _capture(self, **kwargs):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            DaemonManager.stop_daemon(**kwargs)
        return out.getvalue()

    def test_quiet_no_daemon_prints_nothing(self):
        with mock.patch.object(DaemonManager, "read_pid", return_value=None):
            self.assertEqual(self._capture(quiet=True), "")

    def test_verbose_no_daemon_prints_message(self):
        with mock.patch.object(DaemonManager, "read_pid", return_value=None):
            self.assertIn("No daemon running.", self._capture())

    def test_quiet_stops_daemon_silently(self):
        with mock.patch.object(DaemonManager, "read_pid", return_value=4242), \
             mock.patch.object(DaemonManager, "remove_pid") as rm_pid, \
             mock.patch.object(daemon.ProcessManager, "kill_pid", return_value=True), \
             mock.patch.object(daemon.ProcessManager, "is_alive", return_value=False):
            self.assertEqual(self._capture(quiet=True), "")
        rm_pid.assert_called_once()

    def test_verbose_stops_daemon_with_messages(self):
        with mock.patch.object(DaemonManager, "read_pid", return_value=4242), \
             mock.patch.object(daemon.ProcessManager, "kill_pid", return_value=True), \
             mock.patch.object(daemon.ProcessManager, "is_alive", return_value=False):
            out = self._capture()
        self.assertIn("Stopping daemon (PID 4242)...", out)
        self.assertIn("Daemon stopped.", out)

    def test_quiet_force_kill_prints_nothing(self):
        with mock.patch.object(DaemonManager, "read_pid", return_value=4242), \
             mock.patch.object(daemon.ProcessManager, "kill_pid", return_value=True), \
             mock.patch.object(daemon.ProcessManager, "is_alive", return_value=True), \
             mock.patch.object(daemon.time, "sleep"):
            self.assertEqual(self._capture(quiet=True), "")

    def test_verbose_force_kill_prints_message(self):
        with mock.patch.object(DaemonManager, "read_pid", return_value=4242), \
             mock.patch.object(daemon.ProcessManager, "kill_pid", return_value=True), \
             mock.patch.object(daemon.ProcessManager, "is_alive", return_value=True), \
             mock.patch.object(daemon.time, "sleep"):
            out = self._capture()
        self.assertIn("force killing", out)
        self.assertIn("Daemon force-killed.", out)


class TestWaitForDaemonPid(unittest.TestCase):
    def test_returns_pid_once_file_appears(self):
        calls = {"n": 0}

        def read_pid():
            calls["n"] += 1
            return 99 if calls["n"] >= 3 else None

        with mock.patch.object(DaemonManager, "read_pid", side_effect=read_pid), \
             mock.patch.object(daemon.time, "sleep") as sleep:
            pid = DaemonManager._wait_for_daemon_pid()
        self.assertEqual(pid, 99)
        self.assertEqual(sleep.call_count, 2)

    def test_gives_up_after_timeout(self):
        with mock.patch.object(DaemonManager, "read_pid", return_value=None), \
             mock.patch.object(daemon.time, "sleep") as sleep:
            pid = DaemonManager._wait_for_daemon_pid()
        self.assertIsNone(pid)
        expected = int(daemon.START_TIMEOUT / daemon.START_POLL_INTERVAL)
        self.assertEqual(sleep.call_count, expected)


class TestCleanStop(unittest.TestCase):
    def test_hot_exit_zero_is_clean_stop(self):
        self.assertTrue(DaemonManager._is_clean_stop(0, hot=True))

    def test_hot_crash_is_not_clean_stop(self):
        self.assertFalse(DaemonManager._is_clean_stop(1, hot=True))

    def test_continuous_exit_zero_is_not_clean_stop(self):
        # run --continuous is meant to run forever: a clean exit is
        # still a failed attempt so the daemon does not restart
        # every few seconds indefinitely.
        self.assertFalse(DaemonManager._is_clean_stop(0, hot=False))

    def test_continuous_crash_is_not_clean_stop(self):
        self.assertFalse(DaemonManager._is_clean_stop(1, hot=False))


class TestTerminateChild(unittest.TestCase):
    def tearDown(self):
        DaemonManager._proc = None

    def test_no_active_child_is_noop(self):
        with mock.patch.object(DaemonManager, "_proc", None):
            DaemonManager._terminate_child()  # must not raise

    def test_already_dead_child_is_not_signalled(self):
        proc = FakeProc(returncode=0)
        proc.returncode = 0  # poll() reports it exited
        with mock.patch.object(DaemonManager, "_proc", proc):
            DaemonManager._terminate_child()
        self.assertEqual(proc.terminate_calls, 0)
        self.assertEqual(proc.kill_calls, 0)

    def test_terminates_live_child(self):
        proc = FakeProc(returncode=0)
        with mock.patch.object(DaemonManager, "_proc", proc):
            DaemonManager._terminate_child()
        self.assertEqual(proc.terminate_calls, 1)
        self.assertEqual(proc.kill_calls, 0)
        self.assertEqual(proc.wait_calls, 1)
        self.assertIsNone(DaemonManager._proc)

    def test_escapes_to_kill_when_terminate_ignored(self):
        proc = FakeProc(returncode=0, die_on_terminate=False)
        with mock.patch.object(DaemonManager, "_proc", proc):
            DaemonManager._terminate_child()
        self.assertEqual(proc.terminate_calls, 1)
        self.assertEqual(proc.kill_calls, 1)


class TestStartDaemonExitCodes(unittest.TestCase):
    def _run_start(self, wait_result, fork_return=None, fork_side_effect=None):
        """Run start_daemon with fork/PID-polling stubbed.

        Returns (out, err, exit_code); exit_code is None when no SystemExit.
        """
        fork_kwargs = {}
        if fork_side_effect is not None:
            fork_kwargs["side_effect"] = fork_side_effect
        elif fork_return is not None:
            fork_kwargs["return_value"] = fork_return
        out, err = io.StringIO(), io.StringIO()
        code = None
        with mock.patch.object(DaemonManager, "read_pid", return_value=None), \
             mock.patch.object(daemon.ProcessManager, "kill_all", return_value=[]), \
             mock.patch.object(daemon.os, "fork", **fork_kwargs), \
             mock.patch.object(DaemonManager, "_wait_for_daemon_pid",
                               return_value=wait_result), \
             contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                DaemonManager.start_daemon()
            except SystemExit as e:
                code = e.code
        return out.getvalue(), err.getvalue(), code

    def test_start_success_returns_normally(self):
        out, err, code = self._run_start(wait_result=777, fork_return=12345)
        self.assertIsNone(code)
        self.assertIn("Daemon started (PID 777)", out)
        self.assertIn("[continuous]", out)

    def test_start_failure_exits_1(self):
        out, err, code = self._run_start(wait_result=None, fork_return=12345)
        self.assertEqual(code, 1)
        self.assertIn("Daemon failed to start", out)

    def test_fork_failure_exits_1(self):
        out, err, code = self._run_start(
            wait_result=None, fork_side_effect=OSError("fork failed"))
        self.assertEqual(code, 1)
        self.assertIn("fork failed", err)


class TestRunDaemonRestartLoop(unittest.TestCase):
    def tearDown(self):
        DaemonManager._proc = None

    def _run(self, procs, hot=False):
        """Run _run_daemon with the process plumbing stubbed.

        Returns (remove_pid_mock, sleep_mock).
        """
        with mock.patch.object(DaemonManager, "write_pid"), \
             mock.patch.object(DaemonManager, "remove_pid") as rm_pid, \
             mock.patch.object(DaemonManager, "_log"), \
             mock.patch.object(daemon.os, "open", return_value=99), \
             mock.patch.object(daemon.os, "dup2"), \
             mock.patch.object(daemon.os, "close"), \
             mock.patch.object(daemon.signal, "signal"), \
             mock.patch.object(daemon.ProcessManager, "kill_all", return_value=[]), \
             mock.patch.object(daemon.subprocess, "Popen", side_effect=procs), \
             mock.patch.object(daemon.time, "sleep") as sleep:
            DaemonManager._run_daemon(hot=hot)
        return rm_pid, sleep

    def test_continuous_clean_exit_still_counts_as_failure(self):
        # run --continuous exiting 0 must NOT reset the crash count:
        # three attempts, then give up — not a 5-second restart loop.
        procs = [FakeProc(returncode=0) for _ in range(3)]
        rm_pid, sleep = self._run(procs, hot=False)
        rm_pid.assert_called_once()  # gave up and cleaned the PID file
        self.assertEqual(sleep.call_count, 2)
        sleep.assert_any_call(5)
        sleep.assert_any_call(15)

    def test_hot_clean_exit_stops_daemon(self):
        procs = [FakeProc(returncode=0)]
        rm_pid, sleep = self._run(procs, hot=True)
        rm_pid.assert_called_once()
        sleep.assert_not_called()  # clean stop, no restart

    def test_crashing_gradle_gives_up_after_three_attempts(self):
        procs = [FakeProc(returncode=1) for _ in range(3)]
        rm_pid, sleep = self._run(procs, hot=False)
        rm_pid.assert_called_once()
        self.assertEqual(sleep.call_count, 2)
        sleep.assert_any_call(5)
        sleep.assert_any_call(15)


if __name__ == "__main__":
    unittest.main()
