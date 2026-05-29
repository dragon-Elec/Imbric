import subprocess
import time
import sys
from ..daemon import PROJECT_ROOT
from ..filter import OutputFilter

def register(subparsers):
    p = subparsers.add_parser("compile", help="Compile Kotlin sources with filtered output")
    p.add_argument("--tests", action="store_true", help="Also compile test sources")
    p.add_argument("--full", action="store_true", help="Full build (all tasks, not just compileKotlin)")

def run(args):
    if args.full:
        gradle_cmd = ["./gradlew", "build", "--console=plain", "-x", "test"]
    elif args.tests:
        gradle_cmd = ["./gradlew", "compileKotlin", "compileTestKotlin", "--console=plain"]
    else:
        gradle_cmd = ["./gradlew", "compileKotlin", "--console=plain"]

    print(f"Compiling...")
    filt = OutputFilter(mode="compile")
    start = time.time()

    try:
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
            print(f"\nBUILD OK in {elapsed_str}")
        else:
            print(f"\nBUILD FAILED in {elapsed_str}")
            sys.exit(proc.returncode)

    except KeyboardInterrupt:
        proc.terminate()
        print("\nInterrupted.")
        sys.exit(1)
