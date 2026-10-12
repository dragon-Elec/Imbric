"""Exit-code propagation tests (the P1 bug class: wrappers that always exit 0).

Pins:
- generate: gradlew returncode N propagates as SystemExit(N);
  KeyboardInterrupt during generation -> SystemExit(130).
- audit: scan finds missing declarations -> SystemExit(1); fully documented
  -> no exit. The scan runs against a temp sandbox via patched PROJECT_ROOT
  (no repo files are read or written).
- test: failing gradle proc -> SystemExit(1); passing proc -> no exit;
  KeyboardInterrupt -> SystemExit(130).

All gradle invocations are stubbed at the module boundary
(commands.<module>.subprocess.run / .Popen); nothing real executes.
"""

import argparse
import contextlib
import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.ib.commands import audit, generate
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


class TestGenerateExitCodes(unittest.TestCase):
    def _run_generate(self, run_impl):
        """Run generate.run with subprocess.run stubbed.

        Returns (out, err, exit_code); exit_code is None when no SystemExit.
        """
        out, err = io.StringIO(), io.StringIO()
        code = None
        with mock.patch.object(generate.DaemonManager, "stop_daemon"), \
             mock.patch.object(generate.subprocess, "run", side_effect=run_impl), \
             contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                generate.run(argparse.Namespace())
            except SystemExit as e:
                code = e.code
        return out.getvalue(), err.getvalue(), code

    def test_generate_propagates_gradlew_returncode(self):
        def fake_run(*a, **kw):
            return subprocess.CompletedProcess([], 3)
        out, _, code = self._run_generate(fake_run)
        self.assertEqual(code, 3)
        self.assertIn("Generation failed (exit code 3)", out)

    def test_generate_keyboard_interrupt_exits_130(self):
        def raise_ki(*a, **kw):
            raise KeyboardInterrupt
        out, _, code = self._run_generate(raise_ki)
        self.assertEqual(code, 130)

    def test_generate_success_exits_clean(self):
        def fake_run(*a, **kw):
            return subprocess.CompletedProcess([], 0)
        out, _, code = self._run_generate(fake_run)
        self.assertIsNone(code)
        self.assertIn("Bindings generated", out)


class TestAuditExitCodes(unittest.TestCase):
    FOO_KT = "class Foo {\n    fun bar() {}\n}\n"

    @staticmethod
    def _make_project(tmp, document_bar):
        """Tiny sandbox: src/Foo.kt plus the src/srccontext.md audit block."""
        src = Path(tmp) / "src"
        src.mkdir()
        (src / "Foo.kt").write_text(TestAuditExitCodes.FOO_KT)
        block = "- fun Foo\n" + ("- fun bar\n" if document_bar else "")
        (src / "srccontext.md").write_text(f"### [FILE: Foo.kt]\n{block}")
        return Path(tmp)

    def _run_audit_scan(self, root):
        out, err = io.StringIO(), io.StringIO()
        code = None
        with mock.patch.object(audit, "PROJECT_ROOT", root), \
             contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                audit.run(argparse.Namespace(file=None))
            except SystemExit as e:
                code = e.code
        return out.getvalue(), err.getvalue(), code

    def test_scan_with_missing_declarations_exits_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._make_project(tmp, document_bar=False)
            out, _, code = self._run_audit_scan(root)
        self.assertEqual(code, 1)
        self.assertIn("Found 1 missing declarations across 1 files.", out)
        self.assertIn("bar", out)

    def test_scan_fully_documented_exits_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._make_project(tmp, document_bar=True)
            out, _, code = self._run_audit_scan(root)
        self.assertIsNone(code)
        # The banner must state how many files it actually audited, so an
        # unaudited tree cannot pass itself off as fully documented.
        self.assertIn(
            "All public declarations across 1 audited files are fully documented", out)

    def test_scan_with_no_context_files_does_not_claim_clean(self):
        # A tree with Kotlin sources but no *context.md checked nothing. That
        # used to print the all-documented banner and exit 0.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            (root / "src" / "Foo.kt").write_text(TestAuditExitCodes.FOO_KT)
            out, _, code = self._run_audit_scan(root)
        self.assertEqual(code, 1)
        self.assertNotIn("fully documented", out)
        self.assertIn("nothing was audited", out)

    def test_single_file_with_missing_declaration_exits_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._make_project(tmp, document_bar=False)
            out, err = io.StringIO(), io.StringIO()
            code = None
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                try:
                    audit.run(argparse.Namespace(file=str(root / "src" / "Foo.kt")))
                except SystemExit as e:
                    code = e.code
            self.assertEqual(code, 1)
            self.assertIn("Validation Results: Foo.kt", out.getvalue())


class TestCommandExitCodes(unittest.TestCase):
    @staticmethod
    def _run_test_cmd(proc):
        """Run test.run with Popen stubbed. Returns (out, err, exit_code)."""
        out, err = io.StringIO(), io.StringIO()
        code = None
        with mock.patch.object(
                test_cmd, "_get_previously_failed_test_classes", return_value=[]), \
             mock.patch.object(test_cmd.subprocess, "Popen", return_value=proc), \
             contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                test_cmd.run(argparse.Namespace(
                    tests=None, failed=False, rerun=False, continue_on_fail=False))
            except SystemExit as e:
                code = e.code
        return out.getvalue(), err.getvalue(), code

    def test_failing_proc_exits_with_its_code(self):
        out, _, code = self._run_test_cmd(FakeProc(lines=[], returncode=1))
        self.assertEqual(code, 1)
        self.assertIn("Tests failed (exit code 1)", out)

    def test_passing_proc_exits_clean(self):
        out, _, code = self._run_test_cmd(
            FakeProc(lines=["BUILD SUCCESSFUL in 1s"], returncode=0))
        self.assertIsNone(code)
        self.assertIn("Tests completed successfully", out)

    def test_keyboard_interrupt_exits_130(self):
        out, err = io.StringIO(), io.StringIO()
        code = None
        with mock.patch.object(
                test_cmd, "_get_previously_failed_test_classes", return_value=[]), \
             mock.patch.object(test_cmd.subprocess, "Popen",
                             side_effect=KeyboardInterrupt), \
             contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                test_cmd.run(argparse.Namespace(
                    tests=None, failed=False, rerun=False, continue_on_fail=False))
            except SystemExit as e:
                code = e.code
        self.assertEqual(code, 130)
        self.assertIn("Interrupted.", out.getvalue())


if __name__ == "__main__":
    unittest.main()
