import subprocess
import time
import sys
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from ..daemon import PROJECT_ROOT, gradle_base_cmd
from ..filter import OutputFilter
from ..compressor import _GLIB_PATTERN, compress_glib_warnings

_PASSED = re.compile(r" > .* PASSED")
_TASK_START = re.compile(r"^> Task ")
# Compiler warnings are collected into a count, not printed
# inline — they are compiler noise, not test results.
_WARNING = re.compile(r"^w: ")
# Gradle/JVM compile notes and incubating-feature notices carry
# no diagnostic value.
_NOTE = re.compile(r"^Note: ")
_INCUBATING = re.compile(r"^\[Incubating\]")
# JUnit captures a test's System.out as a STANDARD_OUT block
# (benchmark reports, debug prints). Noise in a normal run.
_STANDARD_OUT = re.compile(r" STANDARD_OUT$")

_IMPORTANT = [
    re.compile(r"FAILED"),
    # Kotlin compiler errors are `e: file://...` — matching only `error:` (Gradle's
    # own wording) hid every Kotlin compile failure from the filtered output.
    re.compile(r"^\s*e: "),
    # Anchored (same fix as filter.py): bare `Exception` matched any line
    # containing the word — a passing test named testExceptionPath() took
    # this branch instead of the _PASSED dot branch and set in_error.
    re.compile(r"^\s*(?:Caused by:\s*)?[\w.$]*(?:Exception|Error)\b"),
    # BUILD SUCCESSFUL/FAILED handled by the dedicated branch in run()
    # (they END error context instead of starting it).
    re.compile(r"^> Task :test(?!Classes)"),
]

_GRADLE_NOISE = OutputFilter.NOISE_PATTERNS

def _get_previously_failed_test_classes() -> list[str]:
    """Scans build/test-results/test/ for XML test reports with failures.

    Reflects the last executed test-task results: Gradle does not
    guarantee a single coherent previous run (filtered or crashed
    runs leave partial results behind), so --failed is a
    best-effort hint, not a promise. Benchmark reports
    (TEST-*Benchmark.xml) share this directory and are excluded —
    they are not unit tests to re-run.
    """
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
                        # Benchmarks write into the same results dir;
                        # endswith, not substring — a BenchmarkHelperTest
                        # is a real test and must still re-run.
                        if simple_name.endswith("Benchmark"):
                            continue
                        failed_classes.add(simple_name)
        except Exception:
            continue
    return sorted(failed_classes)

def register(subparsers):
    p = subparsers.add_parser("test", help="Run tests with clean, concise filtering")
    p.add_argument("--tests", action="append", type=str, help="Run specific test class or method; repeatable (e.g. --tests FooTest --tests BarTest)")
    p.add_argument("-w", "--warnings", action="store_true", help="Display full compiler warnings")
    p.add_argument("--failed", action="store_true", help="Re-run only the test classes that failed in the previous run")
    p.add_argument("--rerun", action="store_true", help="Force test re-execution bypassing Gradle cache")
    p.add_argument("--continue", dest="continue_on_fail", action="store_true", help="Continue running tests even if some fail")

def run(args):
    gradle_cmd = gradle_base_cmd("test")

    if args.failed and args.tests:
        print("note: --tests ignored because --failed", file=sys.stderr)

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

    # Targeted runs (--tests/--failed) print each test name so you can
    # confirm exactly what ran. A full suite prints compact progress
    # instead: hundreds of passing names overflow the terminal scrollback
    # and can bury the failures this filter exists to surface. The mode
    # is inferred from the args, not a flag.
    verbose = bool(args.tests or args.failed)
    show_warnings = args.warnings
    warnings: list[str] = []
    glib_buffer: list[str] = []
    in_stdout = False

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

        def flush_glib():
            # Reads dot_count (never assigns — it also feeds the
            # final "(N tests)" total) so the summary newline
            # mirrors the dot-flush without clobbering the count.
            if not glib_buffer:
                return
            if dot_count > 0:
                print()
            print(compress_glib_warnings(glib_buffer), flush=True)
            glib_buffer.clear()

        for line in proc.stdout:
            line = line.rstrip()
            if not line:
                continue

            # JUnit-captured test stdout: benchmark reports and
            # debug prints. The captured lines are indented; a
            # non-indented line ends the block.
            if in_stdout:
                if line.startswith((" ", "\t")):
                    continue
                in_stdout = False
            if _STANDARD_OUT.search(line):
                in_stdout = True
                continue

            # GLib/GIO native criticals: buffer and collapse to one
            # deduped summary. Flushed on the NEXT non-GLib line so
            # the summary lands where the flood occurred (not all at
            # exit, which would reorder a minute-1 critical after a
            # minute-2 failure). search (not match) matches filter.py
            # and tolerates indentation. Lines inside a failure block
            # buffer instead of printing raw.
            if _GLIB_PATTERN.search(line):
                glib_buffer.append(line)
                continue
            if glib_buffer:
                flush_glib()

            # BUILD banners: show, but they END error context — matching
            # them via _IMPORTANT used to set in_error=True, which kept
            # swallowing lines after a successful build.
            if "BUILD SUCCESSFUL" in line or "BUILD FAILED" in line:
                if dot_count > 0:
                    print()
                print(line, flush=True)
                in_error = False
                continue

            # Compiler warnings: collect into a summary instead of
            # printing every one inline.
            if _WARNING.match(line):
                warnings.append(line)
                continue

            # Gradle/JVM compile notes and incubating notices: noise.
            if _NOTE.match(line) or _INCUBATING.match(line):
                continue

            # Failure or important line → show full output immediately
            if any(p.search(line) for p in _IMPORTANT):
                if dot_count > 0:
                    print()
                print(line, flush=True)
                in_error = True
                continue

            # Passed test. Targeted: dot + name for grep-ability. Full suite:
            # a bare dot — the name would flood scrollback. The newline flush
            # before the summary still works because each dot line ends here.
            if _PASSED.search(line):
                if verbose:
                    print(f". {line.strip()}", flush=True)
                else:
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

        # Trailing flood: the child may end mid-GLib-spam with no
        # non-GLib line after it to trigger the in-loop flush.
        flush_glib()

        elapsed = int(time.time() - start)
        elapsed_str = f"{elapsed}s" if elapsed < 60 else f"{elapsed//60}m {elapsed%60}s"

        if proc.returncode == 0:
            suffix = f" ({dot_count} tests)" if dot_count else ""
            print(f"\nTests completed successfully in {elapsed_str}{suffix}")
        else:
            print(f"\nTests failed (exit code {proc.returncode}) in {elapsed_str}")

        if warnings:
            if show_warnings:
                print(f"\n--- {len(warnings)} Compiler Warning{'s' if len(warnings) != 1 else ''} ---")
                for w in warnings:
                    print(w)
            else:
                plural = "s" if len(warnings) != 1 else ""
                print(f"\n[{len(warnings)} compiler warning{plural} (use -w / --warnings to view)]")

        # Propagate: a test wrapper that always exits 0 cannot gate anything
        if proc.returncode != 0:
            sys.exit(proc.returncode)

    except KeyboardInterrupt:
        if proc:
            proc.terminate()
        print("\nInterrupted.")
        sys.exit(130)
