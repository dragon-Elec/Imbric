import subprocess
import time
import sys
import signal
from ..daemon import PROJECT_ROOT, gradle_base_cmd
from ..process import ProcessManager
from ..filter import OutputFilter

def register(subparsers):
    p = subparsers.add_parser("run", help="Run the Imbric app in the foreground with log filtering")
    p.add_argument("--hot", action="store_true", help="Run in hot-reload mode (DCEVM required)")

def run(args):
    if args.hot:
        gradle_cmd = gradle_base_cmd("hotRun", "--auto", "--no-configuration-cache")
        print("Starting Imbric in Hot-Reload mode...")
    else:
        gradle_cmd = gradle_base_cmd("run")
        print("Starting Imbric...")

    filt = OutputFilter(mode="run")
    start = time.time()
    proc = None

    def handle_sigint(signum, frame):
        print("\nStopping Imbric...")
        if proc:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
        # Clean up any orphaned app processes
        ProcessManager.kill_all(force=True, include_daemons=False)
        # Deliberately 0, not 130: Ctrl-C is the NORMAL way to stop a foreground app.
        # Reporting it as failure would break wrappers that stop-then-check.
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_sigint)
    signal.signal(signal.SIGTERM, handle_sigint)

    try:
        # Clean up any existing app processes first
        ProcessManager.kill_all(force=True, include_daemons=False)

        proc = subprocess.Popen(
            gradle_cmd,
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        for line in proc.stdout:
            filtered = filt.filter_line(line)
            if filtered is not None:
                print(filtered, flush=True)

        filt.flush_warnings()
        proc.wait()

        elapsed = int(time.time() - start)
        elapsed_str = f"{elapsed}s" if elapsed < 60 else f"{elapsed//60}m {elapsed%60}s"

        if proc.returncode == 0:
            print(f"\nApp exited cleanly in {elapsed_str}")
        else:
            print(f"\nApp exited with code {proc.returncode} in {elapsed_str}")
            sys.exit(proc.returncode)

    except KeyboardInterrupt:
        handle_sigint(None, None)
    finally:
        ProcessManager.kill_all(force=True, include_daemons=False)
