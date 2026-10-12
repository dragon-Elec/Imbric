"""Parser-contract tests for the `ib` CLI command plugins (scripts/ib/commands/*).

Pins:
- The test subparser's --tests flag is repeatable (append). The old last-wins
  behavior silently dropped all but the final class (P1 fix, commit 24c1538).
- Conflicting-flag precedence notes printed to stderr:
    test     --failed  + --tests   -> "--tests ignored because --failed"
    compile  --full    + --tests   -> "--tests ignored because --full"
    bench    --tests   + --all     -> "--all ignored because --tests"
    clean    --bindings+ --deep    -> "--deep ignored because --bindings"
- doctor's checks, with subprocess.run stubbed (no real java or
  gradlew invocation): the Gradle wrapper version, the
  org.gradle.java.home pin parsed from a fake gradle.properties in
  a temp sandbox, the either/or GIR locations (Path.exists mocked),
  and the generate prerequisites (shutil.which stubbed).

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
                    continue_on_fail=False, warnings=False))
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


def _doctor_sandbox(props_template):
    """Temp PROJECT_ROOT populated with everything doctor reads.

    {root} inside the properties template is replaced with the sandbox
    path, so tests can point org.gradle.java.home at the fake JDK dir.
    """
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    (root / "gradle.properties").write_text(props_template.format(root=root))
    wrapper = root / "gradle" / "wrapper"
    wrapper.mkdir(parents=True)
    (wrapper / "gradle-wrapper.properties").write_text(
        "distributionUrl=https://services.gradle.org/distributions/gradle-9.6.1-bin.zip\n")
    # Fake pinned JDK: subprocess.run is stubbed, so only the
    # directory itself has to exist for the is_dir() check.
    (root / "jbr-25" / "bin").mkdir(parents=True)
    bindings = root / "build" / "native-gen" / "bindings"
    bindings.mkdir(parents=True)
    (bindings / "Gio.java").write_text("")
    gir = root / "ref" / "java-gi_patched" / "ext" / "gir-files" / "linux"
    gir.mkdir(parents=True)
    (gir / "GLib-2.0.gir").write_text("")
    gen_bin = (root / "ref" / "java-gi_patched" / "generator"
               / "build" / "install" / "java-gi" / "bin")
    gen_bin.mkdir(parents=True)
    (gen_bin / "java-gi").write_text("#!/bin/sh\n")
    return tmp, root


def _run_doctor(props_template, gradle_stdout="Gradle 9.6.1\nBuild time: 2026-01-01\n",
                default_java='openjdk version "25.0.1"',
                pinned_java='openjdk version "25.0.1"',
                env=None, gir_ref=True, gir_system=True,
                missing_tools=(), with_generator=True):
    """Run doctor against a sandbox with every OS touch stubbed.

    subprocess.run (default java, the pinned JDK, gradlew),
    shutil.which and the two GIR Path.exists calls are all faked —
    no real java or gradle ever runs. Returns (stdout, exit_code).
    """
    tmp, root = _doctor_sandbox(props_template)
    if not with_generator:
        (root / "ref" / "java-gi_patched" / "generator"
         / "build" / "install" / "java-gi" / "bin" / "java-gi").unlink()

    def fake_run(cmd, *a, **kw):
        if cmd and cmd[-1] == "-version":
            # The default `java` and the org.gradle.java.home binary
            # both end in "-version"; tell them apart by the program.
            out = default_java if cmd[0] == "java" else pinned_java
            return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout=gradle_stdout, stderr="")

    real_exists = Path.exists

    def fake_exists(self):
        s = str(self)
        if s.endswith("gir-files/linux/GLib-2.0.gir"):
            return gir_ref
        if s == "/usr/share/gir-1.0/GLib-2.0.gir":
            return gir_system
        return real_exists(self)

    def fake_which(tool, *a, **kw):
        return None if tool in missing_tools else f"/usr/bin/{tool}"

    out, err = io.StringIO(), io.StringIO()
    code = None
    with mock.patch.object(doctor, "PROJECT_ROOT", root), \
         mock.patch.object(doctor.subprocess, "run", side_effect=fake_run), \
         mock.patch.object(doctor.shutil, "which", side_effect=fake_which), \
         mock.patch.object(doctor.Path, "exists", new=fake_exists), \
         mock.patch.dict(os.environ, env or {}, clear=True), \
         contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            doctor.run(_parse(["doctor"]))
        except SystemExit as e:
            code = e.code
    tmp.cleanup()
    return out.getvalue(), code


class TestDoctorGradlePropertiesParsing(unittest.TestCase):
    def test_parses_simple_assignment(self):
        self.assertEqual(
            doctor.gradle_java_home("org.gradle.java.home=/opt/jbr-25\n"),
            "/opt/jbr-25")

    def test_ignores_comment_lines(self):
        props = ("# org.gradle.java.home=/wrong\n"
                 "! org.gradle.java.home=/also-wrong\n"
                 "org.gradle.java.home=/opt/jbr-25\n")
        self.assertEqual(doctor.gradle_java_home(props), "/opt/jbr-25")

    def test_ignores_other_keys(self):
        props = ("org.gradle.parallel=true\n"
                 "org.gradle.caching=true\n"
                 "org.gradle.java.home=/opt/jbr-25\n")
        self.assertEqual(doctor.gradle_java_home(props), "/opt/jbr-25")

    def test_missing_key_returns_none(self):
        self.assertIsNone(doctor.gradle_java_home("org.gradle.parallel=true\n"))

    def test_empty_value_returns_none(self):
        self.assertIsNone(doctor.gradle_java_home("org.gradle.java.home=\n"))


class TestDoctorJdkChecks(unittest.TestCase):
    def test_valid_pinned_jdk_passes(self):
        out, code = _run_doctor("org.gradle.java.home={root}/jbr-25\n")
        self.assertIn("✓ JDK 25 at org.gradle.java.home", out)
        self.assertIn("jbr-25", out)
        self.assertIsNone(code)  # every check passed -> exit 0

    def test_missing_pinned_jdk_fails(self):
        out, code = _run_doctor("org.gradle.parallel=true\n")
        self.assertIn("✗ org.gradle.java.home missing in gradle.properties", out)
        self.assertEqual(code, 1)

    def test_commented_out_pinned_jdk_fails(self):
        # A commented-out pin means Gradle has no pinned JDK at all.
        out, code = _run_doctor("# org.gradle.java.home={root}/jbr-25\n")
        self.assertIn("✗ org.gradle.java.home missing in gradle.properties", out)
        self.assertEqual(code, 1)

    def test_wrong_pinned_jdk_version_fails(self):
        out, code = _run_doctor(
            "org.gradle.java.home={root}/jbr-25\n",
            pinned_java='openjdk version "21.0.1"')
        self.assertIn("✗ org.gradle.java.home (", out)
        self.assertIn("is not a JDK 25 install", out)
        self.assertEqual(code, 1)

    def test_missing_pinned_jdk_dir_fails(self):
        out, code = _run_doctor("org.gradle.java.home={root}/no-such-jdk\n")
        self.assertIn("is not a JDK 25 install", out)
        self.assertEqual(code, 1)

    def test_unset_java_home_is_not_a_failure(self):
        # JAVA_HOME unset is the healthy case: gradle.properties pins the JDK.
        out, code = _run_doctor("org.gradle.java.home={root}/jbr-25\n", env={})
        self.assertIn("ℹ JAVA_HOME: <unset>", out)
        self.assertIsNone(code)

    def test_default_java_version_is_info_only(self):
        # Gradle ignores the default java — a wrong one must not fail doctor.
        out, code = _run_doctor(
            "org.gradle.java.home={root}/jbr-25\n",
            default_java='openjdk version "17.0.1"')
        self.assertIn("ℹ default java: JDK 25 not found", out)
        self.assertIsNone(code)


class TestDoctorGirEitherOr(unittest.TestCase):
    def test_ref_gir_preferred(self):
        out, code = _run_doctor("org.gradle.java.home={root}/jbr-25\n",
                                gir_ref=True, gir_system=True)
        self.assertIn("✓ GIR files found", out)
        self.assertIn("ref/java-gi_patched/ext/gir-files/linux", out)
        self.assertIsNone(code)

    def test_system_gir_fallback(self):
        out, code = _run_doctor("org.gradle.java.home={root}/jbr-25\n",
                                gir_ref=False, gir_system=True)
        self.assertIn("✓ GIR files found (/usr/share/gir-1.0)", out)
        self.assertIsNone(code)

    def test_both_gir_locations_missing_fails(self):
        out, code = _run_doctor("org.gradle.java.home={root}/jbr-25\n",
                                gir_ref=False, gir_system=False)
        self.assertIn("✗ GIR files missing", out)
        self.assertEqual(code, 1)


class TestDoctorGeneratePrereqs(unittest.TestCase):
    def test_wget_and_unzip_present(self):
        out, code = _run_doctor("org.gradle.java.home={root}/jbr-25\n")
        self.assertIn("✓ wget found", out)
        self.assertIn("✓ unzip found", out)
        self.assertIsNone(code)

    def test_missing_wget_fails(self):
        out, code = _run_doctor("org.gradle.java.home={root}/jbr-25\n",
                                missing_tools=("wget",))
        self.assertIn("✗ wget missing", out)
        self.assertIn("'ib generate'", out)
        self.assertEqual(code, 1)

    def test_missing_unzip_fails(self):
        out, code = _run_doctor("org.gradle.java.home={root}/jbr-25\n",
                                missing_tools=("unzip",))
        self.assertIn("✗ unzip missing", out)
        self.assertEqual(code, 1)

    def test_missing_generator_binary_fails(self):
        # generate_bindings.sh invokes the patched generator directly
        # (it does not build it), so a missing binary breaks 'ib generate'.
        out, code = _run_doctor("org.gradle.java.home={root}/jbr-25\n",
                                with_generator=False)
        self.assertIn("✗ Patched java-gi generator missing", out)
        self.assertEqual(code, 1)


class TestDoctorGradleVersionCheck(unittest.TestCase):
    def test_matching_version_reports_ok(self):
        out, code = _run_doctor("org.gradle.java.home={root}/jbr-25\n",
                                gradle_stdout="Gradle 9.6.1\nBuild time: 2026-01-01\n")
        self.assertIn("✓ Gradle 9.6.1 wrapper OK", out)
        self.assertIsNone(code)  # every check passed -> exit 0

    def test_wrong_version_reports_issue(self):
        out, _ = _run_doctor("org.gradle.java.home={root}/jbr-25\n",
                             gradle_stdout="Gradle 8.1.1\n")
        self.assertIn("✗ Gradle wrapper issue", out)

    def test_failing_check_exits_nonzero(self):
        """A health check that always exits 0 cannot gate `ib doctor && deploy`."""
        out, code = _run_doctor("org.gradle.parallel=true\n")
        self.assertIn("✗ org.gradle.java.home missing", out)
        self.assertEqual(code, 1)



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


if __name__ == "__main__":
    unittest.main()
