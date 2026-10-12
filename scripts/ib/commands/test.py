import subprocess
import time
import sys
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from ..daemon import PROJECT_ROOT, gradle_base_cmd
from ..filter import OutputFilter
from ..compressor import _GLIB_PATTERN, compress_glib_warnings, compress_stacktrace
from ..dedup import DedupEngine

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
    # Stack frames inside a failure block: buffered and collapsed
    # via compress_stacktrace. The engine treats `at ` frames as
    # failures and would emit them verbatim — collapsing them
    # here keeps only com.imbric frames plus a skip count.
    stack_buffer: list[str] = []
    # Universal repeated-line compressor: collapses consecutive
    # runs of ANY repeated line (not just GLib). GLib lines keep
    # their dedicated path below — compress_glib_warnings collapses
    # at 2x and renders ⚠️ [LEVEL] prefixes, while the engine's
    # contract is 2x-verbatim / [Nx] summaries (see dedup.py).
    dedup = DedupEngine()
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

        def flush_stack():
            # Same dot dance as flush_glib. Failure blocks are
            # short, so this flushes almost immediately — only
            # consecutive `at ` frames are ever pending.
            if not stack_buffer:
                return
            if dot_count > 0:
                print()
            print(compress_stacktrace(stack_buffer), flush=True)
            stack_buffer.clear()

        def flush_dedup():
            # Same dot dance as flush_glib: a pending dot row
            # gets a newline first so a collapsed summary never
            # glues onto the dots (dot_count is read, never
            # reset — it feeds the final test total).
            emitted = dedup.flush()
            if not emitted:
                return
            if dot_count > 0:
                print()
            for line in emitted:
                print(line, flush=True)

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
                # A GLib flood bounds any pending engine run:
                # flush it first so an earlier flood's summary
                # prints before this flood's (deferred) summary.
                flush_dedup()
                glib_buffer.append(line)
                continue
            if glib_buffer:
                # The GLib flood preceded the engine's pending
                # run, so its summary keeps stream position.
                flush_glib()

            # BUILD banners: show, but they END error context — matching
            # them via _IMPORTANT used to set in_error=True, which kept
            # swallowing lines after a successful build.
            if "BUILD SUCCESSFUL" in line or "BUILD FAILED" in line:
                flush_dedup()
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
                # Failures are sacred: they print immediately,
                # so any pending flood summary must come first.
                flush_dedup()
                if dot_count > 0:
                    print()
                print(line, flush=True)
                in_error = True
                continue

            # Passed test. Targeted: dot + name for grep-ability. Full suite:
            # a bare dot — the name would flood scrollback. The newline flush
            # before the summary still works because each dot line ends here.
            if _PASSED.search(line):
                flush_dedup()
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
                    flush_stack()
                    flush_dedup()
                    print(f"\n{line}", flush=True)
                elif line.strip().startswith("at "):
                    # Stack frames: buffer and collapse framework
                    # frames via compress_stacktrace (see flush_stack).
                    stack_buffer.append(line)
                else:
                    # Non-frame lines inside an error block can
                    # still flood (progress chatter); route them
                    # through the engine. Failure-shaped lines pass
                    # through verbatim — the engine never dedupes
                    # them (failures are sacred).
                    flush_stack()
                    for emitted in dedup.feed(line):
                        print(emitted, flush=True)
                continue

            # Test task boundary → show as progress marker
            if _TASK_START.match(line) and re.search(r":test\b", line):
                flush_dedup()
                print(f"\n{line}", flush=True)
                continue

            # Non-test Gradle task line → suppress. Task lines
            # are engine boundaries: flush any pending run so
            # floods don't merge across task boundaries.
            if _TASK_START.match(line):
                flush_dedup()
                continue

            # Non-Gradle output → pass through, collapsing
            # consecutive repeated lines via the universal
            # engine (dedup.py).
            emitted = dedup.feed(line)
            if emitted:
                # A collapsed summary starts a new line (same
                # dance as flush_glib). Verbatim lines keep
                # gluing to a pending dot row — exactly as
                # unfiltered output always has.
                if emitted[0] != line and dot_count > 0:
                    print()
                for em in emitted:
                    print(em, flush=True)
            continue

        proc.wait()

        # Trailing flood: the child may end mid-GLib-spam with no
        # non-GLib line after it to trigger the in-loop flush.
        # GLib first: a glib flood that preceded an engine flood
        # must keep its stream position.
        flush_stack()
        flush_glib()
        flush_dedup()

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
