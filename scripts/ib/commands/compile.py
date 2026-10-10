import subprocess
import time
import sys
from ..daemon import PROJECT_ROOT
from ..filter import OutputFilter

def register(subparsers):
    p = subparsers.add_parser("compile", help="Compile Kotlin sources with filtered output")
    p.add_argument("--tests", action="store_true", help="Also compile test sources")
    p.add_argument("-w", "--warnings", action="store_true", help="Display full compiler warnings")
    p.add_argument("--rerun", action="store_true", help="Force task re-execution bypassing Gradle cache")
    p.add_argument("--full", action="store_true", help="Full build (all tasks, not just compileKotlin)")

def run(args):
    if args.full and args.tests:
        print("note: --tests ignored because --full", file=sys.stderr)

    # The GIO bindings live in build output, not the repo — a fresh clone without them
    # fails with cryptic `unresolved reference: gnome`. Point at the fix, not the symptom.
    bindings = PROJECT_ROOT / "build" / "native-gen" / "bindings"
    if not bindings.is_dir() or not any(bindings.iterdir()):
        print("Bindings missing: run `ib generate` first (builds them from the patched fork).")
        sys.exit(1)

    if args.full:
        gradle_cmd = ["./gradlew", "build", "--console=plain", "-x", "test"]
    elif args.tests:
        gradle_cmd = ["./gradlew", "compileKotlin", "compileTestKotlin", "--console=plain"]
    else:
        gradle_cmd = ["./gradlew", "compileKotlin", "--console=plain"]

    if args.rerun:
        gradle_cmd.append("--rerun-tasks")

    print(f"Compiling...")
    filt = OutputFilter(mode="compile", show_warnings=args.warnings)
    start = time.time()

    try:
        proc = None
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
        if proc is not None:
            proc.terminate()
        print("\nInterrupted.")
        sys.exit(130)
