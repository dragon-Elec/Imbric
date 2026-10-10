import os
import subprocess
from pathlib import Path
from ..daemon import PROJECT_ROOT

def register(subparsers):
    p = subparsers.add_parser("doctor", help="Environment health check")

def run(args):
    print("=== Imbric Doctor ===")
    
    # Check Java
    try:
        res = subprocess.run(["java", "-version"], capture_output=True, text=True)
        out = res.stdout + res.stderr
        if "25" in out:
            print("✓ JDK 25 found")
        else:
            print("✗ JDK 25 missing or not default")
    except Exception:
        print("✗ Java not found")
        
    # Check JAVA_HOME
    jh = os.environ.get("JAVA_HOME")
    if jh and "25" in jh:
        print("✓ JAVA_HOME looks correct")
    else:
        print("✗ JAVA_HOME missing or wrong version")
        
    # Check Gradle
    try:
        try:
            wrapper_props = (PROJECT_ROOT / "gradle" / "wrapper" / "gradle-wrapper.properties").read_text()
            gradle_version = wrapper_props.split("gradle-")[1].split("-")[0]
        except Exception:
            gradle_version = "9.6.1"
        res = subprocess.run(["./gradlew", "--version"], cwd=str(PROJECT_ROOT), capture_output=True, text=True)
        if gradle_version in res.stdout:
            print(f"✓ Gradle {gradle_version} wrapper OK")
        else:
            print("✗ Gradle wrapper issue")
    except Exception:
        print("✗ gradlew failed")
        
    # Check GIR
    gir_dir = PROJECT_ROOT / "ref" / "java-gi_patched" / "ext" / "gir-files" / "linux"
    if gir_dir.exists() and (gir_dir / "GLib-2.0.gir").exists():
        print("✓ GIR files found")
    else:
        print("✗ GIR files missing")
        
    # Check bindings
    gen_dir = PROJECT_ROOT / "build" / "native-gen" / "bindings"
    if gen_dir.exists() and any(gen_dir.iterdir()):
        print("✓ Bindings exist")
    else:
        print("✗ Bindings missing (run 'ib generate')")
