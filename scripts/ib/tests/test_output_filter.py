"""OutputFilter contract tests (scripts/ib/filter.py) + test.py dot rendering.

Pins:
- BUILD SUCCESSFUL / BUILD FAILED lines are swallowed (return None) and flush
  any pending dots; callers print their own single summary line.
- "w: ..." lines are collected (never passed through); flush_warnings writes a
  count summary by default and the grouped block with show_warnings=True.
- Error lines pass through unfiltered.
- GLib/GIO native warnings dedupe to one "(Nx)" summary; consecutive
  "at " stack frames compress (framework frames collapse to a skip
  count); [PIPELINE] lines reformat as a timeline.
- test.py's inline renderer buffers GLib criticals and prints the same
  deduped summary to stdout — flushed on the next non-GLib line so it
  lands where the flood occurred, and once at end-of-loop for a
  trailing flood.
- Error patterns are anchored: a PASSED test line naming
  testExceptionPath() or a mid-line "error:" must NOT flip in_error.
- test.py's inline renderer: dots for PASSED lines are separated from the
  BUILD SUCCESSFUL summary by a newline (dots not glued).

test.py's renderer is inline in run() (no seam), so it is exercised by
driving run() with a stub Popen whose stdout yields exact Gradle lines.
"""

import argparse
import contextlib
import io
import unittest
from unittest import mock

from scripts.ib.filter import OutputFilter
from scripts.ib.commands import test as test_cmd


class FakeProc:
    """Stub for subprocess.Popen: iterable stdout, wait(), terminate()."""

    def __init__(self, lines=None, returncode=0):
        self.stdout = iter(lines or [])
        self.returncode = returncode

    def wait(self):
        return self.returncode

    def terminate(self):
        pass


class TestBuildLinesAreSwallowed(unittest.TestCase):
    def test_build_successful_returns_none(self):
        self.assertIsNone(OutputFilter().filter_line("BUILD SUCCESSFUL in 5s"))

    def test_build_failed_returns_none(self):
        self.assertIsNone(OutputFilter().filter_line("BUILD FAILED in 3s"))

    def test_build_line_flushes_pending_dots(self):
        f = OutputFilter()
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            f.filter_line("> Task :someLib")  # non-key task -> one dot
            self.assertEqual(f.dot_count, 1)
            self.assertIsNone(f.filter_line("BUILD SUCCESSFUL in 5s"))
            self.assertEqual(f.dot_count, 0)  # dots flushed before swallowing


class TestWarningCollection(unittest.TestCase):
    def test_warning_collected_and_not_passed_through(self):
        f = OutputFilter()  # show_warnings=False by default
        line = "w: Unnecessary non-null assertion (!!)"
        self.assertIsNone(f.filter_line(line))
        self.assertEqual(f.warnings, [line])

    def test_flush_warnings_writes_count_summary_by_default(self):
        f = OutputFilter()
        f.filter_line("w: something")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            f.flush_warnings()
        self.assertIn("[1 warning (use -w / --warnings to view)]", err.getvalue())

    def test_flush_warnings_writes_grouped_block_when_enabled(self):
        f = OutputFilter(show_warnings=True)
        f.filter_line("w: file:///src/App.kt:10:5 No cast needed.")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            f.flush_warnings()
        self.assertIn("--- 1 Compiler Warning ---", err.getvalue())

    def test_no_warnings_no_summary(self):
        f = OutputFilter()
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            f.flush_warnings()
        self.assertEqual(err.getvalue(), "")


class TestErrorPassthrough(unittest.TestCase):
    def test_compiler_error_line_passes_through(self):
        f = OutputFilter()
        line = "e: file:///src/App.kt:42:10 Unresolved reference 'foo'"
        self.assertEqual(f.filter_line(line), line)
        self.assertTrue(f.in_error)

    def test_failed_token_line_passes_through(self):
        f = OutputFilter()
        line = "Execution FAILED for task ':test'."
        self.assertEqual(f.filter_line(line), line)

    def test_exception_line_passes_through(self):
        f = OutputFilter()
        line = "java.lang.Exception: boom"
        self.assertEqual(f.filter_line(line), line)


class TestDotRendering(unittest.TestCase):
    def test_dots_not_glued_to_build_summary(self):
        # Exact Gradle lines from a passing test run.
        proc = FakeProc(lines=[
            "FooTest > bar PASSED\n",
            "> Task :test\n",
            "BUILD SUCCESSFUL in 5s\n",
        ], returncode=0)
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(test_cmd.subprocess, "Popen", return_value=proc):
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                test_cmd.run(argparse.Namespace(
                    tests=None, failed=False, rerun=False, continue_on_fail=False, warnings=False))
        printed = out.getvalue()
        self.assertIn(".", printed)                       # dot for the passed test
        self.assertIn("BUILD SUCCESSFUL in 5s", printed)  # gradle summary passes through
        self.assertNotIn(".BUILD SUCCESSFUL", printed)    # ...never glued
        # Full suite (no --tests) suppresses the name — compact dots only.
        self.assertNotIn("FooTest > bar PASSED", printed)

    def test_passing_proc_reports_success(self):
        proc = FakeProc(lines=["BUILD SUCCESSFUL in 5s\n"], returncode=0)
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(test_cmd.subprocess, "Popen", return_value=proc):
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                test_cmd.run(argparse.Namespace(
                    tests=None, failed=False, rerun=False, continue_on_fail=False, warnings=False))
        self.assertIn("Tests completed successfully", out.getvalue())


class TestFailureDigest(unittest.TestCase):
    """Gradle's actual failure reason must survive the filter.

    Pre-fix: `* What went wrong:` matched nothing, `FAILURE:` (not `FAILED`) flipped no
    state, and the `> `/`* ` swallow rule ate the ENTIRE reason block — `ib` printed an
    exit code with zero explanation (the orchestrator hit this live: a failing test
    showed no assertion, only "Tests failed (exit code 1)").
    """

    def test_failure_block_passes_through(self):
        # Cold filter, FAILURE-first (config-phase failure shape): no preceding FAILED
        # line opens error context, so ONLY the two new patterns can save the block.
        # Verified vacuous before the fix — this exact sequence passed identically with
        # the old pattern set. If it ever goes green on a revert, the test is lying.
        f = OutputFilter()
        out = [
            f.filter_line("FAILURE: Build failed with an exception."),
            f.filter_line(""),
            f.filter_line("* What went wrong:"),
            f.filter_line("Execution failed for task ':compileKotlin'."),
            f.filter_line("> Run with --scan to get full insights."),
        ]
        kept = [l for l in out if l]
        self.assertIn("FAILURE: Build failed with an exception.", kept)
        self.assertIn("* What went wrong:", kept)
        self.assertIn("Execution failed for task ':compileKotlin'.", kept)
        self.assertIn("> Run with --scan to get full insights.", kept)

    def test_task_failure_block_passes_through(self):
        # Task-phase shape: FAILED line opens context, reason block follows.
        f = OutputFilter()
        out = [
            f.filter_line("> Task :compileKotlin FAILED"),
            f.filter_line("e: file:///x.kt:3:2: expect '}'"),
            f.filter_line("FAILURE: Build failed with an exception."),
            f.filter_line("* What went wrong:"),
            f.filter_line("Execution failed for task ':compileKotlin'."),
        ]
        kept = [l for l in out if l]
        self.assertIn("* What went wrong:", kept)
        self.assertIn("Execution failed for task ':compileKotlin'.", kept)

    def test_no_failure_no_stray_block(self):
        # Outside a failure the `> `/`* ` swallow rule still suppresses gradle noise
        f = OutputFilter()
        self.assertIsNone(f.filter_line("* Get more help at https://help.gradle.org"))
        self.assertIsNone(f.filter_line("> Run some other task"))


class TestTestCommandVisibility(unittest.TestCase):
    """Regression pins for the two real defects found in the 2026-10 deepwork audit.

    1. Kotlin compiler errors print as `e: file://...`. The old `_IMPORTANT`
       matched only `error:` (Gradle's own wording), so every Kotlin compile
       failure was filtered out of `ib test` — you had to go read the build
       directory to learn the build was broken.
    2. Passing tests print their name, not a bare `.`, so `--tests FooTest` is
       verifiable from one run instead of guessing whether it was discovered.
    """

    def _run_test_cmd(self, lines, returncode=0, tests=None):
        proc = FakeProc(lines=lines, returncode=returncode)
        out = io.StringIO()
        # run() propagates the child exit code via sys.exit — swallow it so the
        # assertion is about printed output, not the process status.
        with mock.patch.object(test_cmd.subprocess, "Popen", return_value=proc):
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                with contextlib.suppress(SystemExit):
                    test_cmd.run(argparse.Namespace(
                        tests=tests, failed=False, rerun=False, continue_on_fail=False, warnings=False))
        return out.getvalue()

    def test_kotlin_compile_error_is_visible(self):
        printed = self._run_test_cmd([
            "> Task :compileTestKotlin FAILED\n",
            "e: file:///p/Test.kt:2:5 Unresolved reference: foo\n",
            "FAILURE: Build failed\n",
        ], returncode=1)
        self.assertIn("e: file:///p/Test.kt:2:5 Unresolved reference: foo", printed)

    def test_passing_test_shows_name(self):
        # Targeted runs (--tests) print each name so you can
        # confirm exactly what ran.
        printed = self._run_test_cmd([
            "FooTest > doesTheThing() PASSED\n",
            "BUILD SUCCESSFUL in 5s\n",
        ], tests=["FooTest"])
        self.assertIn("FooTest > doesTheThing() PASSED", printed)

    def test_full_suite_compact_progress(self):
        # Full suite (no --tests) prints compact dots, not names —
        # hundreds of passing names overflow scrollback and bury failures.
        printed = self._run_test_cmd([
            "FooTest > a() PASSED\n",
            "BarTest > b() PASSED\n",
            "BUILD SUCCESSFUL in 5s\n",
        ])
        self.assertNotIn("FooTest > a() PASSED", printed)  # names suppressed
        self.assertNotIn("BarTest > b() PASSED", printed)
        self.assertIn(".", printed)                         # compact dots remain
        self.assertIn("(2 tests)", printed)                 # count in the summary

    def test_kotlin_warning_does_not_enter_error_block(self):
        # `w:` is a warning, not a failure: it is collected into the
        # warning summary and must NOT set in_error, or every line
        # after it floods until the next task line.
        printed = self._run_test_cmd([
            "w: file:///p/A.kt:3:1 unused variable\n",
            "FooTest > bar PASSED\n",
            "BUILD SUCCESSFUL in 5s\n",
        ])
        self.assertIn("[1 compiler warning", printed)  # collected, not flooded
        self.assertIn(".", printed)                     # test after it still prints


class TestGLibDedup(unittest.TestCase):
    """Native GLib/GIO criticals collapse to one deduped summary line."""

    def test_repeated_glib_criticals_collapse_with_count(self):
        f = OutputFilter()
        critical = ("(com.imbric:12345): GLib-GIO-CRITICAL **: "
                    "g_file_info_get_attribute_byte_string: "
                    "assertion 'G_IS_FILE_INFO (info)' failed")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            for _ in range(3):
                self.assertIsNone(f.filter_line(critical))
            f.filter_line("some normal line")   # non-GLib line flushes
            f.filter_line("another normal line")  # ...exactly once
        out = err.getvalue()
        self.assertIn("⚠️ [GLib-GIO-CRITICAL] (3x)", out)
        self.assertEqual(out.count("g_file_info_get_attribute_byte_string"), 1)

    def test_glib_warning_does_not_flip_error_state(self):
        f = OutputFilter()
        self.assertIsNone(f.filter_line(
            "(com.imbric:1): GLib-GIO-CRITICAL **: assertion failed"))
        self.assertFalse(f.in_error)

    def test_flush_warnings_empties_glib_buffer(self):
        f = OutputFilter()
        f.filter_line("GLib-WARNING **: g_set_error: custom error")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            f.flush_warnings()
            f.flush_warnings()  # second flush writes nothing
        self.assertEqual(err.getvalue().count("g_set_error"), 1)


class TestTestCommandGLibBuffering(unittest.TestCase):
    """test.py buffers GLib criticals and prints one deduped summary.

    test.py owns its inline renderer (no OutputFilter seam), so it
    reuses the shared compress_glib_warnings() — a second dedup
    implementation would drift from filter.py's.
    """

    def _critical(self, ts, pid="149156"):
        return (f"(process:{pid}): GLib-GIO-CRITICAL **: {ts}: "
                "g_file_info_get_is_symlink: "
                "assertion 'G_IS_FILE_INFO (info)' failed")

    def _run_test_cmd(self, lines, returncode=0, tests=None):
        proc = FakeProc(lines=lines, returncode=returncode)
        out = io.StringIO()
        # run() propagates the child exit code via sys.exit — swallow it
        # so the assertion is about printed output, not process status.
        with mock.patch.object(test_cmd.subprocess, "Popen", return_value=proc):
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                with contextlib.suppress(SystemExit):
                    test_cmd.run(argparse.Namespace(
                        tests=tests, failed=False, rerun=False,
                        continue_on_fail=False, warnings=False))
        return out.getvalue()

    def test_glib_criticals_collapse_inline(self):
        printed = self._run_test_cmd([
            "FooTest > a PASSED\n",
            self._critical("12:25:14.025", "149156"),
            self._critical("12:25:14.101", "149157"),
            self._critical("12:25:15.202", "149158"),
            "FooTest > b PASSED\n",
            "BUILD SUCCESSFUL in 5s\n",
        ], tests=["FooTest"])
        self.assertIn("(3x)", printed)
        self.assertEqual(printed.count("g_file_info_get_is_symlink"), 1)
        self.assertIn(".", printed)                        # dots present
        self.assertIn("\nBUILD SUCCESSFUL", printed)        # banner on its own line
        self.assertNotIn("12:25:14.025", printed)         # timestamp stripped

    def test_glib_summary_lands_where_the_flood_occurred(self):
        # Flush happens on the next non-GLib line — between the two
        # test names, NOT all at exit.
        critical = self._critical("12:25:14.025")
        printed = self._run_test_cmd([
            "FooTest > a PASSED\n",
            critical,
            critical,
            "FooTest > b PASSED\n",
            "BUILD SUCCESSFUL in 5s\n",
        ], tests=["FooTest"])
        self.assertIn("(2x)", printed)
        a_pos = printed.find("FooTest > a PASSED")
        summary_pos = printed.find("(2x)")
        b_pos = printed.find("FooTest > b PASSED")
        self.assertLess(a_pos, summary_pos)   # after test a ...
        self.assertLess(summary_pos, b_pos)   # ... before test b

    def test_trailing_glib_flood_before_build_flushes(self):
        # Criticals are the last lines before BUILD: the BUILD line
        # (non-GLib) triggers the in-loop flush before it prints.
        critical = self._critical("12:25:14.025")
        printed = self._run_test_cmd([
            "FooTest > a PASSED\n",
            critical,
            critical,
            "BUILD SUCCESSFUL in 5s\n",
        ], tests=["FooTest"])
        self.assertIn("(2x)", printed)
        self.assertEqual(printed.count("g_file_info_get_is_symlink"), 1)
        self.assertIn("\nBUILD SUCCESSFUL", printed)

    def test_glib_flood_at_stream_end_flushes(self):
        # Child ends mid-flood with no non-GLib line after it: only
        # the end-of-loop flush can print the summary.
        critical = self._critical("12:25:14.025")
        printed = self._run_test_cmd([
            "FooTest > a PASSED\n",
            critical,
            critical,
        ], tests=["FooTest"])
        self.assertIn("(2x)", printed)
        self.assertEqual(printed.count("g_file_info_get_is_symlink"), 1)
        self.assertIn("Tests completed successfully", printed)


class TestStacktraceCompression(unittest.TestCase):
    """Consecutive "at " frames buffer up and compress on flush."""

    def test_stacktrace_frames_compress_on_flush(self):
        f = OutputFilter()
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(
                f.filter_line("java.lang.NullPointerException: state was null"),
                "java.lang.NullPointerException: state was null")
            self.assertIsNone(f.filter_line(
                "    at com.imbric.core.ifs.DirState.refresh(DirState.kt:120)"))
            f.filter_line(
                "    at org.gradle.internal.dispatch.ReflectionDispatch"
                ".dispatch(ReflectionDispatch.java:36)")
            f.filter_line(
                "    at jdk.internal.reflect.DirectMethodHandleAccessor"
                ".invoke(DirectMethodHandleAccessor.java:104)")
            f.filter_line(
                "    at com.imbric.app.viewmodel.FileBrowserViewModel"
                ".navigateTo(FileBrowserViewModel.kt:45)")
            f.filter_line(
                "    at org.gradle.process.internal.worker.child"
                ".ActionExecutionWorker.execute(ActionExecutionWorker.java:56)")
            f.filter_line("some normal line")  # non-"at" line flushes
        out = err.getvalue()
        self.assertIn("com.imbric.core.ifs.DirState.refresh", out)
        self.assertIn("com.imbric.app.viewmodel.FileBrowserViewModel.navigateTo", out)
        self.assertIn("[... 2 internal framework frames skipped ...]", out)
        self.assertIn("[... 1 internal framework frames skipped ...]", out)
        # Framework frames are collapsed, not printed raw
        self.assertNotIn("ReflectionDispatch", out)
        self.assertNotIn("DirectMethodHandleAccessor", out)


class TestPipelineFormatting(unittest.TestCase):
    def test_pipeline_line_is_formatted(self):
        f = OutputFilter()
        line = ("[PIPELINE] 135ms (ui_click=+0ms → "
                "gio_list_done=+134ms [990] → ui_rendered=+245ms [990])")
        result = f.filter_line(line)
        assert result is not None
        self.assertIn("⏱️  [PIPELINE TIMELINE] Total: 135ms", result)
        self.assertIn("1. ui_click=+0ms", result)
        self.assertIn("2. gio_list_done=+134ms [990]", result)
        self.assertIn("3. ui_rendered=+245ms [990]", result)


class TestErrorPatternAnchors(unittest.TestCase):
    """Error detection must not trigger on lookalike passing output."""

    def test_passed_test_with_exception_in_name_does_not_flip_error(self):
        f = OutputFilter()
        line = "FooTest > testExceptionPath() PASSED"
        self.assertEqual(f.filter_line(line), line)
        self.assertFalse(f.in_error)

    def test_exception_at_line_start_flips_error(self):
        f = OutputFilter()
        line = "java.lang.RuntimeException: boom"
        self.assertEqual(f.filter_line(line), line)
        self.assertTrue(f.in_error)

    def test_caused_by_line_flips_error(self):
        f = OutputFilter()
        line = "Caused by: java.lang.IllegalStateException: null"
        self.assertEqual(f.filter_line(line), line)
        self.assertTrue(f.in_error)

    def test_exception_in_thread_flips_error(self):
        f = OutputFilter()
        line = 'Exception in thread "main" java.lang.ArithmeticException'
        self.assertEqual(f.filter_line(line), line)
        self.assertTrue(f.in_error)

    def test_midline_error_colon_does_not_flip_error(self):
        f = OutputFilter()
        line = "Build failed with error: something went wrong"
        self.assertEqual(f.filter_line(line), line)
        self.assertFalse(f.in_error)

    def test_leading_error_colon_flips_error(self):
        f = OutputFilter()
        line = "error: something went wrong"
        self.assertEqual(f.filter_line(line), line)
        self.assertTrue(f.in_error)


if __name__ == "__main__":
    unittest.main()
