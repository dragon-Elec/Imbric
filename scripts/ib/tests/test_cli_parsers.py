"""Parser-contract tests for the `ib` CLI command plugins (scripts/ib/commands/*).

Pins:
- The test subparser's --tests flag is repeatable (append). The old last-wins
  behavior silently dropped all but the final class (P1 fix, commit 24c1538).
- Conflicting-flag precedence notes printed to stderr:
    test     --failed  + --tests   -> "--tests ignored because --failed"
    compile  --full    + --tests   -> "--tests ignored because --full"
    bench    --tests   + --all     -> "--all ignored because --tests"
    clean    --bindings+ --deep    -> "--deep ignored because --bindings"
- doctor's Gradle wrapper version check, with subprocess.run stubbed
  (no real gradlew invocation).

Everything that touches the OS (gradle, daemon, filesystem) is stubbed at the
module boundary; clean's destructive shutil.rmtree is fully mocked and its
PROJECT_ROOT is pointed at a temp sandbox.
"""

import argparse
import contextlib
import io
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.ib.commands import bench, clean, compile, doctor
from scripts.ib.commands import test as test_cmd


def _parse(argv):
    """Fresh parser with the command plugins registered; parse argv."""
    parser = argparse.ArgumentParser(prog="ib")
    sub = parser.add_subparsers(dest="command")
    for mod in (clean, doctor, test_cmd, compile, bench):
        mod.register(sub)
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


class TestTestsFlagRepeatable(unittest.TestCase):
    def test_multiple_tests_flags_accumulate(self):
        args = _parse(["test", "--tests", "A", "--tests", "B"])
        self.assertEqual(args.tests, ["A", "B"])

    def test_single_tests_flag(self):
        args = _parse(["test", "--tests", "Only"])
        self.assertEqual(args.tests, ["Only"])

    def test_no_tests_flag_defaults_to_none(self):
        args = _parse(["test"])
        self.assertIsNone(args.tests)

    def test_run_forwards_every_tests_filter(self):
        # The P1 fix: the gradle command must carry BOTH --tests filters,
        # not just the last one.
        proc = FakeProc(lines=["BUILD SUCCESSFUL in 1s"], returncode=0)
        with mock.patch.object(test_cmd.subprocess, "Popen",
                               return_value=proc) as popen:
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                test_cmd.run(argparse.Namespace(
                    tests=["A", "B"], failed=False, rerun=False,
                    continue_on_fail=False))
        self.assertEqual(
            popen.call_args.args[0],
            # --console=plain comes from the shared GRADLE_FLAGS so no command can
            # forget it; --tests is still forwarded once per class.
            ["./gradlew", "test", "--console=plain", "--tests", "A", "--tests", "B"],
        )


class TestConflictingFlagPrecedence(unittest.TestCase):
    def _capture(self, module, args):
        """Run module.run(args) with OS side effects stubbed; return (out, err)."""
        out, err = io.StringIO(), io.StringIO()
        patchers = []
        if hasattr(module, "subprocess"):
            patchers.append(mock.patch.object(
                module.subprocess, "Popen",
                return_value=FakeProc(lines=[], returncode=0)))
        if module is test_cmd:
            # Never scan the real build/test-results directory.
            patchers.append(mock.patch.object(
                test_cmd, "_get_previously_failed_test_classes", return_value=[]))
        if module is clean:
            # Never signal a real daemon; never delete a real directory.
            patchers.append(mock.patch.object(clean, "DaemonManager"))
            patchers.append(mock.patch.object(clean.shutil, "rmtree"))
        with contextlib.ExitStack() as stack:
            for patcher in patchers:
                stack.enter_context(patcher)
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                module.run(args)
        return out.getvalue(), err.getvalue()

    def test_failed_ignores_tests(self):
        _, err = self._capture(test_cmd, _parse(["test", "--failed", "--tests", "X"]))
        self.assertIn("--tests ignored because --failed", err)

    def test_full_ignores_tests(self):
        _, err = self._capture(compile, _parse(["compile", "--full", "--tests"]))
        self.assertIn("--tests ignored because --full", err)

    def test_tests_ignores_all(self):
        _, err = self._capture(
            bench, _parse(["bench", "--tests", "GioListingBenchmark", "--all"]))
        self.assertIn("--all ignored because --tests", err)

    def test_bindings_ignores_deep(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(clean, "PROJECT_ROOT", Path(tmp)):
                _, err = self._capture(clean, _parse(["clean", "--bindings", "--deep"]))
        self.assertIn("--deep ignored because --bindings", err)

    def test_bindings_deep_deletes_only_the_bindings_target(self):
        # Destructive path fully mocked: rmtree must hit build/native-gen only.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bindings = root / "build" / "native-gen"
            bindings.mkdir(parents=True)
            with mock.patch.object(clean, "PROJECT_ROOT", root):
                with mock.patch.object(clean.shutil, "rmtree") as rmtree:
                    out, err = io.StringIO(), io.StringIO()
                    with mock.patch.object(clean, "DaemonManager"), \
                         contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                        clean.run(_parse(["clean", "--bindings", "--deep"]))
            rmtree.assert_called_once_with(bindings)
            self.assertIn("Cleaned bindings.", out.getvalue())


class TestDoctorGradleVersionCheck(unittest.TestCase):
    def _run_doctor(self, gradle_stdout, env_ok=True):
        """Run doctor with subprocess.run stubbed; return (stdout, exit_code).

        doctor exits non-zero when any check fails, so a test that leaves the real
        JAVA_HOME in place now (correctly) exits 1. Both the output and the code
        are returned so tests can assert either.
        """
        def fake_run(cmd, *a, **kw):
            if cmd and cmd[0] == "java":
                return subprocess.CompletedProcess(
                    cmd, 0, stdout='openjdk version "25.0.1"', stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout=gradle_stdout, stderr="")

        env = {"JAVA_HOME": "/usr/lib/jvm/java-25-openjdk-amd64"} if env_ok else {}
        out, err = io.StringIO(), io.StringIO()
        code = None
        with mock.patch.object(doctor.subprocess, "run", side_effect=fake_run):
            with mock.patch.dict(os.environ, env, clear=True):
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    try:
                        doctor.run(_parse(["doctor"]))
                    except SystemExit as e:
                        code = e.code
        return out.getvalue(), code

    def test_matching_version_reports_ok(self):
        out, code = self._run_doctor("Gradle 9.6.1\nBuild time: 2026-01-01\n")
        self.assertIn("✓ Gradle 9.6.1 wrapper OK", out)
        self.assertIsNone(code)  # every check passed -> exit 0

    def test_wrong_version_reports_issue(self):
        out, _ = self._run_doctor("Gradle 8.1.1\n")
        self.assertIn("✗ Gradle wrapper issue", out)

    def test_failing_check_exits_nonzero(self):
        """A health check that always exits 0 cannot gate `ib doctor && deploy`."""
        out, code = self._run_doctor("Gradle 9.6.1\n", env_ok=False)
        self.assertIn("✗ JAVA_HOME", out)
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()


class TestPluginIsolation(unittest.TestCase):
    """One broken command module must cost only its own command.

    Pre-fix: all 15 register() calls shared one try/except ImportError — a single bad
    import registered ZERO commands and the user got 'invalid choice'.
    """

    def test_command_modules_tuple(self):
        from scripts.ib.cli import COMMAND_MODULES
        cli_names = [cli for cli, _ in COMMAND_MODULES]
        self.assertIn("test", cli_names)
        self.assertIn("compile", cli_names)
        self.assertIn("exec", cli_names)
        self.assertEqual(len(COMMAND_MODULES), len(set(COMMAND_MODULES)))

    def test_every_module_importable_and_registers(self):
        import importlib
        from scripts.ib.cli import COMMAND_MODULES
        for cli_name, module_name in COMMAND_MODULES:
            mod = importlib.import_module(f"scripts.ib.commands.{module_name}")
            self.assertTrue(hasattr(mod, "register"), f"{cli_name} has no register()")
            self.assertTrue(hasattr(mod, "run"), f"{cli_name} has no run()")


class TestCommandDispatch(unittest.TestCase):
    """CLI name resolves to the right module — the `exec`/`exec_cmd` split broke this once.

    Pre-fix: the dispatch checked the module name (`exec_cmd`) against the CLI name
    (`exec`), so `ib exec` printed `Unknown command` and exited 1. Every CLI name must
    resolve, especially ones whose module name differs.
    """

    def test_every_cli_name_resolves(self):
        import importlib
        from scripts.ib.cli import COMMAND_MODULES
        for cli_name, module_name in COMMAND_MODULES:
            mod = importlib.import_module(f"scripts.ib.commands.{module_name}")
            self.assertTrue(callable(getattr(mod, "run", None)),
                            f"{cli_name} -> {module_name} has no run()")

    def test_exec_alias_resolves(self):
        from scripts.ib.cli import COMMAND_MODULES
        resolved = dict(COMMAND_MODULES).get("exec")
        self.assertEqual(resolved, "exec_cmd")
