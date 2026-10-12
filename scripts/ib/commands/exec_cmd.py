import subprocess
import sys
import time
from ..daemon import PROJECT_ROOT

def register(subparsers):
    p = subparsers.add_parser("exec", help="Execute arbitrary command (raw passthrough)")
    p.add_argument("cmd", nargs="+", help="Command to run")

def run(args):
    print(f"Running: {' '.join(args.cmd)}\n")

    start = time.time()

    # Raw passthrough: an arbitrary command's output must not be
    # treated as Gradle noise — OutputFilter would drop every
    # line starting with "> " or "* " (e.g. all of diff's output).
    try:
        proc = subprocess.Popen(
            args.cmd,
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
    except FileNotFoundError:
        print(f"executable not found: {args.cmd[0]}", file=sys.stderr)
        sys.exit(127)

    try:
        for line in proc.stdout:
            print(line, end="", flush=True)

        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        print("\nInterrupted.")
        sys.exit(130)

    elapsed = int(time.time() - start)
    elapsed_str = f"{elapsed}s" if elapsed < 60 else f"{elapsed//60}m {elapsed%60}s"

    if proc.returncode == 0:
        print(f"\nCompleted in {elapsed_str}")
    else:
        print(f"\nFailed (code {proc.returncode}) in {elapsed_str}")
        sys.exit(proc.returncode)
