import os
import subprocess
import sys
from pathlib import Path
from ..daemon import PROJECT_ROOT

def register(subparsers):
    p = subparsers.add_parser("doctor", help="Environment health check")

def run(args):
    print("=== Imbric Doctor ===")

    # A health check that always exits 0 cannot gate anything — `ib doctor && deploy`
    # would deploy on a broken env. Count failures and exit non-zero.
    failures = 0

    def check(ok: bool, good: str, bad: str):
        nonlocal failures
        print(("✓ " if ok else "✗ ") + (good if ok else bad))
        if not ok:
            failures += 1

    # Check Java
    try:
        res = subprocess.run(["java", "-version"], capture_output=True, text=True)
        out = res.stdout + res.stderr
        check("25" in out, "JDK 25 found", "JDK 25 missing or not default")
    except Exception:
        check(False, "", "Java not found")

    # Check JAVA_HOME
    jh = os.environ.get("JAVA_HOME")
    check(bool(jh) and "25" in jh, "JAVA_HOME looks correct", "JAVA_HOME missing or wrong version")

    # Check Gradle
    try:
        try:
            wrapper_props = (PROJECT_ROOT / "gradle" / "wrapper" / "gradle-wrapper.properties").read_text()
            gradle_version = wrapper_props.split("gradle-")[1].split("-")[0]
        except Exception:
            gradle_version = "9.6.1"
        res = subprocess.run(["./gradlew", "--version"], cwd=str(PROJECT_ROOT), capture_output=True, text=True)
        check(gradle_version in res.stdout, f"Gradle {gradle_version} wrapper OK", "Gradle wrapper issue")
    except Exception:
        check(False, "", "gradlew failed")

    # Check GIR
    gir_dir = PROJECT_ROOT / "ref" / "java-gi_patched" / "ext" / "gir-files" / "linux"
    check(gir_dir.exists() and (gir_dir / "GLib-2.0.gir").exists(), "GIR files found", "GIR files missing")

    # Check bindings
    gen_dir = PROJECT_ROOT / "build" / "native-gen" / "bindings"
    check(gen_dir.exists() and any(gen_dir.iterdir()), "Bindings exist", "Bindings missing (run 'ib generate')")

    if failures:
        print(f"\n{failures} check(s) failed.")
        sys.exit(1)
    print("\nAll checks passed.")
