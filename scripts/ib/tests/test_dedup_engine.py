"""DedupEngine contract tests (scripts/ib/dedup.py) + test.py wiring.

The engine is the universal repeated-line compressor: it collapses
CONSECUTIVE runs of the same logical line (volatile tokens stripped)
to "[Nx] <cleaned>", keeps 1x/2x runs verbatim, never collapses
interleaved output, and never dedupes failures.

Wiring tests drive test.py's run() through the same seam as
TestTestCommandGLibBuffering in test_output_filter.py: FakeProc
stdout + mock.patch(Popen) + redirect_stdout.
"""

import argparse
import contextlib
import io
import unittest
from unittest import mock

from scripts.ib.commands import test as test_cmd
from scripts.ib.dedup import DedupEngine
from scripts.ib.compressor import compress_glib_warnings


class FakeProc:
    """Stub for subprocess.Popen: iterable stdout, wait(), terminate()."""

    def __init__(self, lines=None, returncode=0):
        self.stdout = iter(lines or [])
        self.returncode = returncode

    def wait(self):
        return self.returncode

    def terminate(self):
        pass


def run_engine(engine, lines):
    """Feed lines through an engine and return the full emission."""
    out = []
    for line in lines:
        out.extend(engine.feed(line))
    out.extend(engine.flush())
    return out


class TestVerbatimRepeat(unittest.TestCase):
    """1. Same line Nx -> [Nx] line."""

    def test_five_identical_lines_collapse_to_summary(self):
        engine = DedupEngine()
        self.assertEqual(
            run_engine(engine, ["line"] * 5),
            ["[5x] line"])

    def test_single_line_emitted_verbatim(self):
        engine = DedupEngine()
        self.assertEqual(run_engine(engine, ["once"]), ["once"])


class TestVolatileTokenRepeat(unittest.TestCase):
    """2. Identical events with different volatile tokens collapse."""

    def test_process_prefixes_collapse(self):
        engine = DedupEngine()
        out = run_engine(engine, [
            "(process:123): same message",
            "(process:456): same message",
            "(process:789): same message",
        ])
        self.assertEqual(out, ["[3x] same message"])

    def test_com_prefixes_2x_emits_both_distinct_lines(self):
        engine = DedupEngine()
        out = run_engine(engine, [
            "(com.imbric:12345): event",
            "(com.imbric:99999): event",
        ])
        # 2x runs are information: both ACTUAL lines emitted
        # verbatim (not the first line twice).
        self.assertEqual(out, [
            "(com.imbric:12345): event",
            "(com.imbric:99999): event"])


class TestThreshold(unittest.TestCase):
    """3. 2x shows BOTH verbatim; 3x collapses to [3x]."""

    def test_two_repeats_emit_both_verbatim(self):
        engine = DedupEngine()
        self.assertEqual(
            run_engine(engine, ["dup", "dup"]),
            ["dup", "dup"])

    def test_three_repeats_collapse(self):
        engine = DedupEngine()
        self.assertEqual(
            run_engine(engine, ["dup", "dup", "dup"]),
            ["[3x] dup"])

    def test_run_continuing_across_flush_boundary(self):
        # A pending 2x run is flushed by the next distinct
        # line's feed call (lazy emission); the boundary
        # line itself is emitted by the following call.
        engine = DedupEngine()
        self.assertEqual(engine.feed("dup"), [])
        self.assertEqual(engine.feed("dup"), [])
        self.assertEqual(engine.feed("other"), ["dup", "dup"])
        self.assertEqual(engine.flush(), ["other"])


class TestNoFalseCollapse(unittest.TestCase):
    """4. Two genuinely different messages are NEVER collapsed."""

    def test_different_messages_stay_separate(self):
        engine = DedupEngine()
        out = run_engine(engine, [
            "downloading module A",
            "downloading module B",
            "downloading module A",
        ])
        self.assertEqual(out, [
            "downloading module A",
            "downloading module B",
            "downloading module A"])

    def test_message_differing_after_prefix_stays_separate(self):
        engine = DedupEngine()
        out = run_engine(engine, [
            "(process:1): failed to sync row 1",
            "(process:2): failed to sync row 2",
        ])
        # Row numbers are content, not volatile tokens.
        self.assertEqual(out, [
            "(process:1): failed to sync row 1",
            "(process:2): failed to sync row 2"])


class TestConservativeTokens(unittest.TestCase):
    """5. Bare numbers are NOT volatile — proof of conservatism."""

    def test_bare_path_numbers_are_not_stripped(self):
        engine = DedupEngine()
        out = run_engine(engine, [
            "file/a/1.txt",
            "file/a/2.txt",
            "file/a/3.txt",
        ])
        self.assertEqual(out, [
            "file/a/1.txt", "file/a/2.txt", "file/a/3.txt"])

    def test_default_patterns_do_not_strip_hash_numbers(self):
        engine = DedupEngine()
        out = run_engine(engine, [
            "item #0 ready",
            "item #1 ready",
            "item #2 ready",
        ])
        self.assertEqual(out, [
            "item #0 ready", "item #1 ready", "item #2 ready"])


class TestAlternating(unittest.TestCase):
    """6. A B A B is interleaved, not consecutive — never collapsed."""

    def test_alternating_lines_do_not_collapse(self):
        engine = DedupEngine()
        self.assertEqual(
            run_engine(engine, ["A", "B", "A", "B"]),
            ["A", "B", "A", "B"])

    def test_interleaved_with_volatile_tokens(self):
        engine = DedupEngine()
        out = run_engine(engine, [
            "(process:1): tick",
            "(process:2): tock",
            "(process:3): tick",
            "(process:4): tock",
        ])
        self.assertEqual(len(out), 4)


class TestBoundaryFlush(unittest.TestCase):
    """7. A different line flushes the pending summary before itself."""

    def test_different_line_flushes_summary_before_itself(self):
        engine = DedupEngine()
        for _ in range(3):
            engine.feed("flood line")
        # The summary is emitted by the boundary line's feed
        # call — not held for stream end. The boundary line
        # itself is emitted by the next call.
        self.assertEqual(
            engine.feed("next line"), ["[3x] flood line"])
        self.assertEqual(engine.flush(), ["next line"])


class TestStreamEndFlush(unittest.TestCase):
    """8. A trailing flood is flushed at stream end."""

    def test_trailing_flood_flushed_by_flush(self):
        engine = DedupEngine()
        engine.feed("first")
        for _ in range(4):
            engine.feed("trailing flood")
        self.assertEqual(engine.flush(), ["[4x] trailing flood"])

    def test_flush_with_no_pending_run_is_empty(self):
        self.assertEqual(DedupEngine().flush(), [])


class TestOrderPreservation(unittest.TestCase):
    """9. Summaries appear where the flood occurred, not at exit."""

    def test_summary_precedes_later_distinct_line(self):
        engine = DedupEngine()
        out = run_engine(engine, [
            "early flood", "early flood", "early flood",
            "later distinct line",
        ])
        self.assertEqual(out, ["[3x] early flood", "later distinct line"])
        self.assertLess(
            out.index("[3x] early flood"),
            out.index("later distinct line"))

    def test_two_floods_stay_in_stream_order(self):
        engine = DedupEngine()
        out = run_engine(engine, [
            "flood one", "flood one", "flood one",
            "between",
            "flood two", "flood two", "flood two",
        ])
        self.assertEqual(out, [
            "[3x] flood one", "between", "[3x] flood two"])


class TestTaskBoundary(unittest.TestCase):
    """> Task lines are flush boundaries and never collapse."""

    def test_task_boundary_flushes_pending_run(self):
        engine = DedupEngine()
        for _ in range(3):
            engine.feed("flood")
        self.assertEqual(
            engine.feed("> Task :test"),
            ["[3x] flood", "> Task :test"])

    def test_task_boundary_lines_are_never_collapsed(self):
        engine = DedupEngine()
        out = run_engine(engine, ["> Task :compileKotlin"] * 3)
        self.assertEqual(out, ["> Task :compileKotlin"] * 3)


class TestFailuresSacred(unittest.TestCase):
    """Failure lines pass through verbatim — never deduped."""

    def test_exception_lines_pass_through_verbatim(self):
        engine = DedupEngine()
        out = run_engine(engine, ["java.lang.Exception: boom"] * 5)
        self.assertEqual(out, ["java.lang.Exception: boom"] * 5)

    def test_failed_token_lines_pass_through_verbatim(self):
        engine = DedupEngine()
        out = run_engine(engine, ["> Task :test FAILED"] * 4)
        self.assertEqual(out, ["> Task :test FAILED"] * 4)

    def test_compiler_error_lines_pass_through_verbatim(self):
        engine = DedupEngine()
        out = run_engine(engine, ["e: file:///p/Test.kt:2:5 boom"] * 3)
        self.assertEqual(out, ["e: file:///p/Test.kt:2:5 boom"] * 3)

    def test_error_colon_lines_pass_through_verbatim(self):
        engine = DedupEngine()
        out = run_engine(engine, ["error: something broke"] * 3)
        self.assertEqual(out, ["error: something broke"] * 3)

    def test_stacktrace_frames_pass_through_verbatim(self):
        engine = DedupEngine()
        frame = "    at org.gradle.internal.Dispatch.dispatch(D.java:36)"
        out = run_engine(engine, [frame] * 3)
        self.assertEqual(out, [frame] * 3)

    def test_failure_line_flushes_pending_run(self):
        engine = DedupEngine()
        for _ in range(3):
            engine.feed("noise flood")
        out = engine.feed("e: file:///p/Test.kt:2:5 Unresolved reference")
        self.assertEqual(
            out,
            ["[3x] noise flood",
             "e: file:///p/Test.kt:2:5 Unresolved reference"])

    def test_passing_test_named_exception_path_is_not_a_failure(self):
        # Anchored patterns: a PASSED line merely CONTAINING
        # "Exception" is ordinary output, collapsible.
        engine = DedupEngine()
        out = run_engine(engine, ["FooTest > testExceptionPath() PASSED"] * 3)
        self.assertEqual(out, ["[3x] FooTest > testExceptionPath() PASSED"])


class TestVolatileTokens(unittest.TestCase):
    """Each default volatile-token shape is stripped for keys and
    cleaned summaries."""

    def test_timestamps_are_volatile(self):
        engine = DedupEngine()
        out = run_engine(engine, [
            "event at 12:25:14.025 done",
            "event at 12:26:01.500 done",
            "event at 12:27:59.999 done",
        ])
        self.assertEqual(out, ["[3x] event at done"])

    def test_hex_addresses_are_volatile(self):
        engine = DedupEngine()
        out = run_engine(engine, [
            "allocated block at 0x7ffd1234",
            "allocated block at 0x7ffd5678",
            "allocated block at 0x7ffd9abc",
        ])
        self.assertEqual(out, ["[3x] allocated block at"])

    def test_pid_and_tid_tokens_are_volatile(self):
        engine = DedupEngine()
        out = run_engine(engine, [
            "pid=1234 worker started",
            "pid=5678 worker started",
            "tid=9012 worker started",
        ])
        self.assertEqual(out, ["[3x] worker started"])

    def test_thread_names_are_volatile(self):
        engine = DedupEngine()
        out = run_engine(engine, [
            "Thread-12 acquired lock",
            "Thread-99 acquired lock",
        ])
        # 2x: both verbatim (volatile stripping applies to keys and
        # collapsed summaries; verbatim runs keep the original lines).
        self.assertEqual(out, [
            "Thread-12 acquired lock", "Thread-99 acquired lock"])


class TestConfigurability(unittest.TestCase):
    """11. Custom volatile-token list and custom threshold take effect."""

    def test_custom_volatile_patterns_take_effect(self):
        engine = DedupEngine(volatile_patterns=[r"#\d+"])
        out = run_engine(engine, [
            "item #0 ready",
            "item #1 ready",
            "item #2 ready",
        ])
        self.assertEqual(out, ["[3x] item ready"])

    def test_custom_threshold_takes_effect(self):
        engine = DedupEngine(threshold=5)
        out = run_engine(engine, ["repeat me"] * 4)
        self.assertEqual(out, ["repeat me"] * 4)  # 4 < 5: all verbatim

        engine = DedupEngine(threshold=5)
        self.assertEqual(
            run_engine(engine, ["repeat me"] * 5),
            ["[5x] repeat me"])

    def test_custom_failure_patterns_take_effect(self):
        engine = DedupEngine(failure_patterns=[r"^CRITICAL"])
        out = run_engine(engine, ["CRITICAL disk full"] * 3)
        self.assertEqual(out, ["CRITICAL disk full"] * 3)

    def test_invalid_threshold_rejected(self):
        with self.assertRaises(ValueError):
            DedupEngine(threshold=0)


class TestEmptyAndWhitespace(unittest.TestCase):
    """12. Empty/whitespace lines don't create spurious runs."""

    def test_blank_lines_pass_through_without_runs(self):
        engine = DedupEngine()
        self.assertEqual(engine.feed(""), [""])
        self.assertEqual(engine.feed("   "), [""])
        self.assertEqual(engine.feed("\t"), [""])
        # No pending run was created by the blank lines.
        self.assertEqual(engine.flush(), [])

    def test_blank_line_flushes_pending_run(self):
        engine = DedupEngine()
        engine.feed("x")
        engine.feed("x")
        engine.feed("x")
        self.assertEqual(engine.feed(""), ["[3x] x", ""])

    def test_blank_lines_separate_floods(self):
        engine = DedupEngine()
        out = run_engine(engine, [
            "x", "x", "x", "", "x", "x", "x",
        ])
        self.assertEqual(out, ["[3x] x", "", "[3x] x"])


class TestGlibEquivalence(unittest.TestCase):
    """10. The engine collapses real GLib criticals exactly like the
    dedicated compress_glib_warnings — same collapse, same count,
    PIDs and timestamps stripped.

    The dedicated compressor stays wired into test.py anyway: it
    collapses at 2x and renders ⚠️ [LEVEL] prefixes, while the
    engine's contract is 2x-verbatim / [Nx] summaries. That
    policy difference is provable — see
    test_policy_difference_is_why_both_exist.
    """

    def _criticals(self):
        return [
            "(process:149156): GLib-GIO-CRITICAL **: 12:25:14.025: "
            "g_file_info_get_is_symlink: "
            "assertion 'G_IS_FILE_INFO (info)' failed",
            "(process:149157): GLib-GIO-CRITICAL **: 12:25:14.101: "
            "g_file_info_get_is_symlink: "
            "assertion 'G_IS_FILE_INFO (info)' failed",
            "(process:149158): GLib-GIO-CRITICAL **: 12:25:15.202: "
            "g_file_info_get_is_symlink: "
            "assertion 'G_IS_FILE_INFO (info)' failed",
        ]

    def test_engine_collapses_glib_criticals(self):
        engine = DedupEngine()
        out = run_engine(engine, self._criticals())
        self.assertEqual(len(out), 1)
        self.assertTrue(out[0].startswith("[3x] "))
        self.assertIn("GLib-GIO-CRITICAL", out[0])
        self.assertIn("g_file_info_get_is_symlink", out[0])
        self.assertIn("assertion 'G_IS_FILE_INFO (info)' failed", out[0])
        # Volatile tokens stripped from the cleaned sample.
        self.assertNotIn("12:25", out[0])
        self.assertNotIn("14915", out[0])
        self.assertNotIn("process:", out[0])

    def test_dedicated_compressor_collapses_same_input(self):
        glib = compress_glib_warnings(self._criticals())
        self.assertIn("(3x)", glib)
        self.assertIn("GLib-GIO-CRITICAL", glib)
        self.assertNotIn("12:25", glib)
        self.assertNotIn("14915", glib)

    def test_policy_difference_is_why_both_exist(self):
        # 2x input: the engine emits BOTH verbatim (a small repeat
        # is information); the dedicated GLib compressor collapses
        # to (2x). Different contracts → both are kept.
        pair = self._criticals()[:2]
        engine = DedupEngine()
        self.assertEqual(run_engine(engine, pair), pair)
        self.assertIn("(2x)", compress_glib_warnings(pair))


class TestTestCommandDedupWiring(unittest.TestCase):
    """test.py routes pass-through output through DedupEngine.

    Same seam as TestTestCommandGLibBuffering: FakeProc stdout +
    mock.patch(Popen) + redirect_stdout. Proves: a repeated-line
    flood in real Gradle output collapses to a summary, and a
    failure still passes through uncompressed.
    """

    def _run_test_cmd(self, lines, returncode=0, tests=None):
        proc = FakeProc(lines=lines, returncode=returncode)
        out = io.StringIO()
        # run() propagates the child exit code via sys.exit —
        # swallow it so the assertion is about printed output,
        # not the process status.
        with mock.patch.object(test_cmd.subprocess, "Popen",
                               return_value=proc):
            with contextlib.redirect_stdout(out), \
                    contextlib.redirect_stderr(io.StringIO()):
                with contextlib.suppress(SystemExit):
                    test_cmd.run(argparse.Namespace(
                        tests=tests, failed=False, rerun=False,
                        continue_on_fail=False, warnings=False))
        return out.getvalue()

    def test_repeated_line_flood_collapses_to_summary(self):
        printed = self._run_test_cmd([
            "FooTest > a PASSED\n",
            "same status line\n",
            "same status line\n",
            "same status line\n",
            "FooTest > b PASSED\n",
            "BUILD SUCCESSFUL in 5s\n",
        ], tests=["FooTest"])
        self.assertIn("[3x] same status line", printed)
        self.assertEqual(printed.count("same status line"), 1)

    def test_flood_summary_lands_where_the_flood_occurred(self):
        printed = self._run_test_cmd([
            "FooTest > a PASSED\n",
            "flood line\n",
            "flood line\n",
            "flood line\n",
            "FooTest > b PASSED\n",
            "BUILD SUCCESSFUL in 5s\n",
        ], tests=["FooTest"])
        a_pos = printed.find("FooTest > a PASSED")
        summary_pos = printed.find("[3x]")
        b_pos = printed.find("FooTest > b PASSED")
        self.assertLess(a_pos, summary_pos)
        self.assertLess(summary_pos, b_pos)

    def test_volatile_flood_collapses_with_tokens_stripped(self):
        printed = self._run_test_cmd([
            "FooTest > a PASSED\n",
            "(process:1001): worker still alive\n",
            "(process:1002): worker still alive\n",
            "(process:1003): worker still alive\n",
            "FooTest > b PASSED\n",
            "BUILD SUCCESSFUL in 5s\n",
        ], tests=["FooTest"])
        self.assertIn("[3x] worker still alive", printed)
        self.assertNotIn("process:1001", printed)
        self.assertNotIn("process:1002", printed)
        self.assertNotIn("process:1003", printed)

    def test_failure_flood_passes_through_uncompressed(self):
        printed = self._run_test_cmd([
            "FooTest > a FAILED\n",
            "java.lang.AssertionError: expected 1 but was 2\n",
            "java.lang.AssertionError: expected 1 but was 2\n",
            "java.lang.AssertionError: expected 1 but was 2\n",
            "BUILD FAILED in 3s\n",
        ], returncode=1)
        # Failure lines are sacred: every occurrence printed verbatim.
        self.assertEqual(
            printed.count("java.lang.AssertionError: expected 1 but was 2"),
            3)
        self.assertNotIn("[3x]", printed)

    def test_glib_criticals_still_use_dedicated_compressor(self):
        # Coexistence proof in the wired path: GLib floods keep the
        # ⚠️ [LEVEL] (Nx) summary, not the engine's [Nx] format.
        printed = self._run_test_cmd([
            "FooTest > a PASSED\n",
            "(process:149156): GLib-GIO-CRITICAL **: 12:25:14.025: "
            "g_file_info_get_is_symlink: assertion failed\n",
            "(process:149157): GLib-GIO-CRITICAL **: 12:25:14.101: "
            "g_file_info_get_is_symlink: assertion failed\n",
            "(process:149158): GLib-GIO-CRITICAL **: 12:25:15.202: "
            "g_file_info_get_is_symlink: assertion failed\n",
            "FooTest > b PASSED\n",
            "BUILD SUCCESSFUL in 5s\n",
        ], tests=["FooTest"])
        self.assertIn("⚠️ [GLib-GIO-CRITICAL] (3x)", printed)
        self.assertNotIn("12:25:14.025", printed)

    def test_trailing_flood_at_stream_end_flushes(self):
        printed = self._run_test_cmd([
            "FooTest > a PASSED\n",
            "end flood\n",
            "end flood\n",
            "end flood\n",
        ], tests=["FooTest"])
        self.assertIn("[3x] end flood", printed)
        self.assertIn("Tests completed successfully", printed)


if __name__ == "__main__":
    unittest.main()
