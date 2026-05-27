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
        res = subprocess.run(["./gradlew", "--version"], cwd=str(PROJECT_ROOT), capture_output=True, text=True)
        if "9.5.1" in res.stdout:
            print("✓ Gradle 9.5.1 wrapper OK")
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
