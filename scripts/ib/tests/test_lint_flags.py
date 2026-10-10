"""Lint flag semantics (scripts/ib/commands/lint.py).

Pins:
- --strict turns compiler warnings into a failed check (SystemExit 1 with the
  failures summary); without --strict the same warning does NOT fail.
- --fix prints the unsupported note to stderr.

Gradle invocations (Popen) and the grep-based checks (subprocess.run) are
stubbed at the module boundary; no real gradle or grep runs.
"""

import argparse
import contextlib
import io
import subprocess
import unittest
from unittest import mock

from scripts.ib.commands import lint


def _parse(argv):
    parser = argparse.ArgumentParser(prog="ib")
    sub = parser.add_subparsers(dest="command")
    lint.register(sub)
    return parser.parse_args(argv)


class FakeProc:
    """Stub for subprocess.Popen: iterable stdout, wait(), terminate()."""

    def __init__(self, lines=None, returncode=0):
        self.stdout = iter(lines or [])
        self.returncode = returncode

    def wait(self):
        return self.returncode

    def terminate(self):
        pass


class TestLintFlags(unittest.TestCase):
    WARNING_LINE = "w: Unnecessary non-null assertion (!!)\n"

    def _run_lint(self, argv):
        """Run lint with stubbed gradle + grep.

        Returns (out, err, exit_code); exit_code is None when no SystemExit.
        """
        def fake_popen(*a, **kw):
            return FakeProc(lines=[self.WARNING_LINE], returncode=0)

        grep_result = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        out, err = io.StringIO(), io.StringIO()
        code = None
        with mock.patch.object(lint.subprocess, "Popen", side_effect=fake_popen), \
             mock.patch.object(lint.subprocess, "run", return_value=grep_result), \
             contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                lint.run(_parse(argv))
            except SystemExit as e:
                code = e.code
        return out.getvalue(), err.getvalue(), code

    def test_strict_fails_on_compilation_warnings(self):
        out, _, code = self._run_lint(["lint", "--strict"])
        self.assertEqual(code, 1)
        self.assertIn("✗ Compilation warnings", out)
        self.assertIn("✗ Some checks failed!", out)

    def test_without_strict_warnings_do_not_fail(self):
        out, _, code = self._run_lint(["lint"])
        self.assertEqual(code, 0)
        self.assertIn("✓ Compilation OK", out)
        self.assertIn("✓ All checks passed!", out)

    def test_fix_prints_unsupported_note(self):
        out, err, code = self._run_lint(["lint", "--fix"])
        self.assertEqual(code, 0)
        self.assertIn("--fix not supported", err)

    def test_strict_summary_counts_both_compile_steps(self):
        # Both compileKotlin and compileTestKotlin emit the stubbed warning,
        # so --strict must flag both steps.
        out, _, code = self._run_lint(["lint", "--strict"])
        self.assertEqual(code, 1)
        self.assertIn("✗ Compilation warnings", out)
        self.assertIn("✗ Test compilation warnings", out)


if __name__ == "__main__":
    unittest.main()
