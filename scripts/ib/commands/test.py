import subprocess
import time
import sys
import re
import xml.etree.ElementTree as ET
from pathlib import Path
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

_GRADLE_NOISE = OutputFilter.NOISE_PATTERNS

def _get_previously_failed_test_classes() -> list[str]:
    """Scans build/test-results/test/ for XML test reports with failures."""
    test_results_dir = PROJECT_ROOT / "build" / "test-results" / "test"
    if not test_results_dir.exists():
        return []

    failed_classes = set()
    for xml_file in test_results_dir.glob("TEST-*.xml"):
        try:
            tree = ET.parse(xml_file)
            root = tree.getroot()
            for testcase in root.findall("testcase"):
                if testcase.find("failure") is not None or testcase.find("error") is not None:
                    classname = testcase.get("classname", "")
                    if classname:
                        # Extract simple classname if package-prefixed
                        simple_name = classname.split(".")[-1]
                        failed_classes.add(simple_name)
        except Exception:
            continue
    return sorted(failed_classes)

def register(subparsers):
    p = subparsers.add_parser("test", help="Run tests with clean, concise filtering")
    p.add_argument("--tests", action="append", type=str, help="Run specific test class or method; repeatable (e.g. --tests FooTest --tests BarTest)")
    p.add_argument("--failed", action="store_true", help="Re-run only the test classes that failed in the previous run")
    p.add_argument("--rerun", action="store_true", help="Force test re-execution bypassing Gradle cache")
    p.add_argument("--continue", dest="continue_on_fail", action="store_true", help="Continue running tests even if some fail")

def run(args):
    gradle_cmd = ["./gradlew", "test", "--console=plain"]

    if args.failed:
        failed_classes = _get_previously_failed_test_classes()
        if not failed_classes:
            print("No failed tests recorded from previous run.")
            return
        print(f"Re-running {len(failed_classes)} previously failed test classes: {', '.join(failed_classes)}\n")
        for cls in failed_classes:
            gradle_cmd.extend(["--tests", cls])
    elif args.tests:
        # repeatable: forward EVERY filter, gradle's --tests is append-friendly (last-wins
        # silently dropped all but the final class)
        for t in args.tests:
            gradle_cmd.extend(["--tests", t])

    if args.rerun:
        gradle_cmd.append("--rerun-tasks")

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
            # Propagate: a test wrapper that always exits 0 cannot gate anything
            sys.exit(proc.returncode)

    except KeyboardInterrupt:
        if proc:
            proc.terminate()
        print("\nInterrupted.")
        sys.exit(130)
