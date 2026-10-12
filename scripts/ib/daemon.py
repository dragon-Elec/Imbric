import datetime
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from .process import ProcessManager
from .filter import OutputFilter

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
GRADLE_DIR = PROJECT_ROOT / ".gradle"
PID_FILE = GRADLE_DIR / "imbric-daemon.pid"
LOG_FILE = GRADLE_DIR / "imbric-daemon.log"

# Flags every Gradle invocation shares. `--console=plain` was copy-pasted into
# six command modules, so a new command would silently fall back to Gradle's
# rich progress output — unreadable through a pipe and noisy for an agent.
#
# `--stacktrace` was tried here and removed: on a failed build Gradle dumps 30+
# frames of its own internals *after* `* What went wrong:`, which buries the one
# line that names the failing task. That block already carries the cause.
GRADLE_FLAGS = ["--console=plain"]

# Seconds to wait between restart attempts. Continuous mode is
# supposed to run forever, so a gradle that exits right away is
# probably a hard failure — back off instead of hot-looping.
RESTART_BACKOFF = [5, 15, 45]

# How long the parent waits for the grandchild to write the
# PID file before declaring the daemon failed to start.
START_TIMEOUT = 5.0
START_POLL_INTERVAL = 0.1


def gradle_base_cmd(*tasks: str) -> list[str]:
    """Build a Gradle argv from task names plus the shared flags."""
    return ["./gradlew", *tasks, *GRADLE_FLAGS]

class DaemonManager:
    # Active Gradle child of the daemon loop, so the SIGTERM
    # handler can kill it instead of orphaning it.
    _proc: subprocess.Popen | None = None

    @staticmethod
    def read_pid() -> int | None:
        try:
            pid = int(PID_FILE.read_text().strip())
            if ProcessManager.is_alive(pid):
                return pid
            PID_FILE.unlink(missing_ok=True)
            return None
        except (FileNotFoundError, ValueError):
            return None

    @staticmethod
    def write_pid(pid: int):
        GRADLE_DIR.mkdir(parents=True, exist_ok=True)
        PID_FILE.write_text(str(pid))

    @staticmethod
    def remove_pid():
        PID_FILE.unlink(missing_ok=True)

    @classmethod
    def start_daemon(cls, hot=False):
        existing_pid = cls.read_pid()
        if existing_pid:
            print(f"Daemon already running (PID {existing_pid}).")
            print("Use 'ib log -f' to watch, 'ib stop' to kill.")
            return

        print("Cleaning up orphaned processes to free memory...")
        killed = ProcessManager.kill_all(include_daemons=False)
        if killed:
            print(f"  Killed {len(killed)} orphaned process(es).")
            time.sleep(1)

        GRADLE_DIR.mkdir(parents=True, exist_ok=True)
        LOG_FILE.write_text("")

        try:
            pid = os.fork()
        except OSError as e:
            print(f"Failed to fork daemon process: {e}", file=sys.stderr)
            sys.exit(1)

        if pid > 0:
            daemon_pid = cls._wait_for_daemon_pid()
            if daemon_pid:
                mode = "hot-reload" if hot else "continuous"
                print(f"Daemon started (PID {daemon_pid}) [{mode}]")
                print(f"Log: {LOG_FILE}")
                print("Use 'ib log -f' to watch output, 'ib stop' to kill.")
            else:
                print("Daemon failed to start. Check log:")
                print(f"  cat {LOG_FILE}")
                sys.exit(1)
            return

        os.setsid()
        if os.fork() > 0:
            os._exit(0)

        cls._run_daemon(hot=hot)

    @classmethod
    def _wait_for_daemon_pid(cls) -> int | None:
        """Poll the PID file until the grandchild writes it.

        A fixed sleep races a loaded machine: the grandchild may
        not have written the file yet, and a healthy start would
        be reported as a failure.
        """
        attempts = max(1, int(START_TIMEOUT / START_POLL_INTERVAL))
        for _ in range(attempts):
            pid = cls.read_pid()
            if pid:
                return pid
            time.sleep(START_POLL_INTERVAL)
        return None

    @classmethod
    def _run_daemon(cls, hot=False):
        cls.write_pid(os.getpid())

        log_fd = os.open(str(LOG_FILE), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
        os.dup2(log_fd, 1)
        os.dup2(log_fd, 2)
        os.close(log_fd)

        dev_null = os.open(os.devnull, os.O_RDONLY)
        os.dup2(dev_null, 0)
        os.close(dev_null)

        def handle_sigterm(signum, frame):
            # Minimal and safe: kill the Gradle child, clear the
            # PID file, exit. Anything more risks deadlock in
            # handler context.
            cls._log("Daemon received SIGTERM, shutting down...")
            cls._terminate_child()
            cls.remove_pid()
            sys.exit(0)

        signal.signal(signal.SIGTERM, handle_sigterm)
        signal.signal(signal.SIGINT, handle_sigterm)

        if hot:
            gradle_cmd = gradle_base_cmd("hotRun", "--auto", "--no-configuration-cache")
        else:
            gradle_cmd = gradle_base_cmd("run", "--continuous")

        cls._log("Daemon started.")
        cls._log(f"Project: {PROJECT_ROOT}")
        cls._log(f"Command: {' '.join(gradle_cmd)}")

        crash_count = 0
        max_crashes = 3

        while crash_count < max_crashes:
            cls._log(f"Starting Gradle (attempt {crash_count + 1})...")
            try:
                ProcessManager.kill_all(force=True, include_daemons=False)
                proc = subprocess.Popen(
                    gradle_cmd,
                    cwd=str(PROJECT_ROOT),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                cls._proc = proc
                try:
                    filt = OutputFilter(mode="run")
                    for line in proc.stdout:
                        filtered = filt.filter_line(line)
                        if filtered is not None:
                            print(filtered, flush=True)

                    filt.flush_warnings()
                    proc.wait()
                finally:
                    # Any exit path (signal, exception, normal
                    # end) must not leave the Gradle child running.
                    cls._terminate_child()

                if cls._is_clean_stop(proc.returncode, hot):
                    cls._log("Gradle exited normally.")
                    cls._log("Hot-reload task exited cleanly. Daemon stopping.")
                    cls.remove_pid()
                    return

                crash_count += 1
                if proc.returncode == 0:
                    cls._log(
                        "Gradle exited normally, but continuous "
                        "mode should run indefinitely.")
                else:
                    cls._log(f"Gradle exited with code {proc.returncode}.")
            except Exception as e:
                crash_count += 1
                cls._log(f"Gradle error: {e}.")

            if crash_count < max_crashes:
                delay = RESTART_BACKOFF[min(crash_count - 1, len(RESTART_BACKOFF) - 1)]
                cls._log(f"Restarting in {delay} seconds...")
                time.sleep(delay)

        cls._log("Too many crashes. Daemon giving up.")
        cls.remove_pid()

    @classmethod
    def _terminate_child(cls, timeout: float = 3.0) -> None:
        """Terminate the active Gradle child, escalating to SIGKILL.

        Safe to call from the signal handler and from the read
        loop's finally: clears _proc first, so a second call
        (handler + finally) is a no-op.
        """
        proc = cls._proc
        if proc is None:
            return
        cls._proc = None
        if proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(timeout=timeout)
            return
        except subprocess.TimeoutExpired:
            pass
        proc.kill()
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            cls._log(f"Gradle child {proc.pid} did not die after SIGKILL.")

    @staticmethod
    def _is_clean_stop(returncode: int, hot: bool) -> bool:
        """Hot mode treats exit 0 as an intentional stop. Continuous mode
        is supposed to run indefinitely, so any exit (even 0) is a failed
        attempt that counts toward the crash limit."""
        return hot and returncode == 0

    @staticmethod
    def _log(msg: str):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] {msg}", flush=True)

    @classmethod
    def stop_daemon(cls, quiet: bool = False):
        """Stop the running daemon.

        quiet=True suppresses every print: clean/generate call this
        on every invocation and should not chat about it.
        """
        pid = cls.read_pid()
        if not pid:
            if not quiet:
                print("No daemon running.")
            return

        if not quiet:
            print(f"Stopping daemon (PID {pid})...")
        ProcessManager.kill_pid(pid, signal.SIGTERM)

        for _ in range(10):
            if not ProcessManager.is_alive(pid):
                if not quiet:
                    print("Daemon stopped.")
                cls.remove_pid()
                return
            time.sleep(0.5)

        if not quiet:
            print("Daemon didn't stop gracefully, force killing...")
        ProcessManager.kill_pid(pid, signal.SIGKILL)
        time.sleep(1)
        cls.remove_pid()
        if not quiet:
            print("Daemon force-killed.")
