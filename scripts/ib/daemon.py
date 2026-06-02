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

class DaemonManager:
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

        pid = os.fork()
        if pid > 0:
            time.sleep(0.5)
            daemon_pid = cls.read_pid()
            if daemon_pid:
                mode = "hot-reload" if hot else "continuous"
                print(f"Daemon started (PID {daemon_pid}) [{mode}]")
                print(f"Log: {LOG_FILE}")
                print("Use 'ib log -f' to watch output, 'ib stop' to kill.")
            else:
                print("Daemon failed to start. Check log:")
                print(f"  cat {LOG_FILE}")
            return

        os.setsid()
        if os.fork() > 0:
            os._exit(0)

        cls._run_daemon(hot=hot)

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

        try:
            import ctypes
            libc = ctypes.CDLL("libc.so.6")
            libc.prctl(15, b"imbric-daemon", 0, 0, 0)
        except Exception:
            pass

        def handle_sigterm(signum, frame):
            cls._log("Daemon received SIGTERM, shutting down...")
            cls.remove_pid()
            sys.exit(0)

        signal.signal(signal.SIGTERM, handle_sigterm)
        signal.signal(signal.SIGINT, handle_sigterm)

        if hot:
            gradle_cmd = ["./gradlew", "hotRun", "--auto", "--no-configuration-cache", "--console=plain"]
        else:
            gradle_cmd = ["./gradlew", "run", "--continuous", "--console=plain"]

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

                filt = OutputFilter(mode="run")
                for line in proc.stdout:
                    filtered = filt.filter_line(line)
                    if filtered is not None:
                        print(filtered, flush=True)

                filt.flush_warnings()
                proc.wait()

                if proc.returncode == 0:
                    cls._log("Gradle exited normally.")
                    if hot:
                        cls._log("Hot-reload task exited cleanly. Daemon stopping.")
                        cls.remove_pid()
                        return
                    crash_count = 0
                else:
                    crash_count += 1
                    cls._log(f"Gradle exited with code {proc.returncode}.")
            except Exception as e:
                crash_count += 1
                cls._log(f"Gradle error: {e}.")

            if crash_count < max_crashes:
                cls._log("Restarting in 5 seconds...")
                time.sleep(5)

        cls._log("Too many crashes. Daemon giving up.")
        cls.remove_pid()

    @staticmethod
    def _log(msg: str):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] {msg}", flush=True)

    @classmethod
    def stop_daemon(cls):
        pid = cls.read_pid()
        if not pid:
            print("No daemon running.")
            return

        print(f"Stopping daemon (PID {pid})...")
        ProcessManager.kill_pid(pid, signal.SIGTERM)

        for _ in range(10):
            if not ProcessManager.is_alive(pid):
                print("Daemon stopped.")
                cls.remove_pid()
                return
            time.sleep(0.5)

        print("Daemon didn't stop gracefully, force killing...")
        ProcessManager.kill_pid(pid, signal.SIGKILL)
        time.sleep(1)
        cls.remove_pid()
        print("Daemon force-killed.")
