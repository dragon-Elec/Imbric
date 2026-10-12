import os
import shutil
import subprocess
import sys
from pathlib import Path
from ..daemon import PROJECT_ROOT

# generate_bindings.sh hardcodes the system GIR dir as its fallback when
# the submodule copy is absent — mirror that here so doctor checks the
# same two locations the script actually uses.
SYSTEM_GIR_DIR = Path("/usr/share/gir-1.0")

# External tools generate_bindings.sh shells out to: wget fetches the
# foundation sources jar, unzip extracts it. Coreutils (cp, find, mkdir,
# rm, sed) are assumed present on any Linux box.
GENERATE_TOOLS = ("wget", "unzip")

def register(subparsers):
    p = subparsers.add_parser("doctor", help="Environment health check")

def gradle_java_home(props_text: str) -> str | None:
    """Parse org.gradle.java.home out of gradle.properties content.

    gradle.properties is `key=value` lines with `#`/`!` comments — the
    same file Gradle itself reads, so this is the JDK Gradle will
    actually use. Returns None when the key is absent or empty.
    """
    for raw in props_text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("!"):
            continue
        key, sep, value = line.partition("=")
        if key.strip() == "org.gradle.java.home":
            value = value.strip()
            return value or None
    return None

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

    def info(msg: str):
        # Informational only: printed, never counted as a failure.
        print("ℹ " + msg)

    # Check the JDK Gradle actually uses. gradle.properties pins
    # org.gradle.java.home; the default `java` on PATH and the JAVA_HOME
    # env var are NOT used by Gradle, so treating them as requirements
    # false-fails healthy machines where JAVA_HOME is simply unset.
    try:
        props_text = (PROJECT_ROOT / "gradle.properties").read_text()
    except Exception:
        props_text = ""
    pinned_home = gradle_java_home(props_text)
    if pinned_home:
        jdk_dir = Path(pinned_home)
        try:
            res = subprocess.run([str(jdk_dir / "bin" / "java"), "-version"], capture_output=True, text=True)
            out = res.stdout + res.stderr
            check(jdk_dir.is_dir() and "25" in out,
                  f"JDK 25 at org.gradle.java.home ({pinned_home})",
                  f"org.gradle.java.home ({pinned_home}) is not a JDK 25 install")
        except Exception:
            check(False, "", f"org.gradle.java.home ({pinned_home}) is not a JDK 25 install")
    else:
        check(False, "", "org.gradle.java.home missing in gradle.properties")

    # Default java on PATH: Gradle ignores it — info only.
    try:
        res = subprocess.run(["java", "-version"], capture_output=True, text=True)
        out = res.stdout + res.stderr
        info("default java: JDK 25 found" if "25" in out
             else "default java: JDK 25 not found (Gradle ignores the default java)")
    except Exception:
        info("default java: not found (Gradle ignores the default java)")

    # JAVA_HOME: Gradle ignores it when org.gradle.java.home is set — info only.
    env_jh = os.environ.get("JAVA_HOME")
    info(f"JAVA_HOME: {env_jh or '<unset>'} (Gradle ignores JAVA_HOME when org.gradle.java.home is set)")

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

    # Check GIR — generate_bindings.sh prefers the submodule GIR files
    # and falls back to the system dir, so either location is fine.
    # Only both missing is a failure.
    ref_gir_dir = PROJECT_ROOT / "ref" / "java-gi_patched" / "ext" / "gir-files" / "linux"
    if (ref_gir_dir / "GLib-2.0.gir").exists():
        gir_dir = ref_gir_dir
    elif (SYSTEM_GIR_DIR / "GLib-2.0.gir").exists():
        gir_dir = SYSTEM_GIR_DIR
    else:
        gir_dir = None
    check(gir_dir is not None,
          f"GIR files found ({gir_dir})",
          "GIR files missing (need GLib-2.0.gir in ref/java-gi_patched/ext/gir-files/linux or /usr/share/gir-1.0)")

    # Check generate prerequisites: the external tools generate_bindings.sh
    # shells out to. Missing them means `ib generate` cannot run.
    for tool in GENERATE_TOOLS:
        check(shutil.which(tool) is not None,
              f"{tool} found",
              f"{tool} missing — required by scripts/generate_bindings.sh (install it to run 'ib generate')")

    # Patched generator binary. generate_bindings.sh invokes it directly
    # (under set -e) and does NOT build it when missing, so a missing
    # binary means `ib generate` cannot run.
    patched_gen_bin = (PROJECT_ROOT / "ref" / "java-gi_patched" / "generator"
                       / "build" / "install" / "java-gi" / "bin" / "java-gi")
    check(patched_gen_bin.exists(),
          "Patched java-gi generator found",
          f"Patched java-gi generator missing ({patched_gen_bin}) — build ref/java-gi_patched before 'ib generate'")

    # Check bindings
    gen_dir = PROJECT_ROOT / "build" / "native-gen" / "bindings"
    check(gen_dir.exists() and any(gen_dir.iterdir()), "Bindings exist", "Bindings missing (run 'ib generate')")

    if failures:
        print(f"\n{failures} check(s) failed.")
        sys.exit(1)
    print("\nAll checks passed.")
