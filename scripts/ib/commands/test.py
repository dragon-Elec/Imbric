import subprocess
import time
import sys
import re
from ..daemon import PROJECT_ROOT
from ..filter import OutputFilter

_PASSED = re.compile(r" > .* PASSED")
_TASK_START = re.compile(r"^> Task ")

_IMPORTANT = [
    re.compile(r"FAILED"),
    re.compile(r"error:"),
    re.compile(r"Exception"),
    re.compile(r"BUILD SUCCESSFUL"),
    re.compile(r"BUILD FAILED"),
    re.compile(r"^> Task :test(?!Classes)"),
]

# Use shared noise patterns from OutputFilter
_GRADLE_NOISE = OutputFilter.NOISE_PATTERNS

def register(subparsers):
    p = subparsers.add_parser("test", help="Run tests with clean, concise filtering")
    p.add_argument("--tests", type=str, help="Run specific test class or method (e.g. 'GioBackendTest')")
    p.add_argument("--continue", dest="continue_on_fail", action="store_true", help="Continue running tests even if some fail")

def run(args):
    gradle_cmd = ["./gradlew", "test", "--console=plain"]
    if args.tests:
        gradle_cmd.extend(["--tests", args.tests])
    if args.continue_on_fail:
        gradle_cmd.append("--continue")

    print(f"Running: {' '.join(gradle_cmd)}\n")
    start = time.time()
    proc = None

    try:
        proc = subprocess.Popen(
            gradle_cmd,
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        in_error = False
        dot_count = 0

        for line in proc.stdout:
            line = line.rstrip()
            if not line:
                continue

            # Failure or important line → show full output immediately
            if any(p.search(line) for p in _IMPORTANT):
                if not in_error and dot_count > 0:
                    print()
                print(line, flush=True)
                in_error = True
                continue

            # Passed test → single dot
            if _PASSED.search(line):
                print(".", end="", flush=True)
                dot_count += 1
                continue

            # Gradle noise → always suppress
            if any(p.search(line) for p in _GRADLE_NOISE):
                continue

            # Inside an error block → keep printing until next task boundary
            if in_error:
                if _TASK_START.match(line):
                    in_error = False
                    print(f"\n{line}", flush=True)
                else:
                    print(line, flush=True)
                continue

            # Test task boundary → show as progress marker
            if _TASK_START.match(line) and re.search(r":test\b", line):
                print(f"\n{line}", flush=True)
                continue

            # Non-test Gradle task line → suppress
            if _TASK_START.match(line):
                continue

            # Non-Gradle output → pass through
            print(line, flush=True)

        proc.wait()

        elapsed = int(time.time() - start)
        elapsed_str = f"{elapsed}s" if elapsed < 60 else f"{elapsed//60}m {elapsed%60}s"

        if proc.returncode == 0:
            print(f"\nTests completed successfully in {elapsed_str}")
        else:
            print(f"\nTests failed (exit code {proc.returncode}) in {elapsed_str}")

    except KeyboardInterrupt:
        if proc:
            proc.terminate()
        print("\nInterrupted.")
