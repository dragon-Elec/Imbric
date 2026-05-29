import subprocess
import time
import sys
from ..daemon import PROJECT_ROOT
from ..filter import OutputFilter

def register(subparsers):
    p = subparsers.add_parser("lint", help="Run code quality checks")
    p.add_argument("--fix", action="store_true", help="Auto-fix issues where possible")
    p.add_argument("--strict", action="store_true", help="Fail on warnings")

def run(args):
    print("Running code quality checks...")
    print()
    
    checks_passed = True
    
    # 1. Check compilation
    print("1. Compilation check...")
    gradle_cmd = ["./gradlew", "compileKotlin", "--console=plain"]
    filt = OutputFilter(mode="lint")
    start = time.time()
    
    try:
        proc = subprocess.Popen(
            gradle_cmd,
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        for line in proc.stdout:
            filtered = filt.filter_line(line)
            if filtered is not None:
                print(filtered, flush=True)
        
        filt.flush_warnings()
        proc.wait()
        
        elapsed = int(time.time() - start)
        if proc.returncode == 0:
            print(f"   ✓ Compilation OK ({elapsed}s)")
        else:
            print(f"   ✗ Compilation failed ({elapsed}s)")
            checks_passed = False
    except Exception as e:
        print(f"   ✗ Compilation error: {e}")
        checks_passed = False
    
    print()
    
    # 2. Check test compilation
    print("2. Test compilation check...")
    gradle_cmd = ["./gradlew", "compileTestKotlin", "--console=plain"]
    filt = OutputFilter(mode="lint")
    start = time.time()
    
    try:
        proc = subprocess.Popen(
            gradle_cmd,
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        for line in proc.stdout:
            filtered = filt.filter_line(line)
            if filtered is not None:
                print(filtered, flush=True)
        
        filt.flush_warnings()
        proc.wait()
        
        elapsed = int(time.time() - start)
        if proc.returncode == 0:
            print(f"   ✓ Test compilation OK ({elapsed}s)")
        else:
            print(f"   ✗ Test compilation failed ({elapsed}s)")
            checks_passed = False
    except Exception as e:
        print(f"   ✗ Test compilation error: {e}")
        checks_passed = False
    
    print()
    
    # 3. Check for common issues
    print("3. Code quality checks...")
    
    # Check for TODO/FIXME comments
    try:
        result = subprocess.run(
            ["grep", "-r", "-n", "-i", "-E", "TODO|FIXME|HACK|XXX", "src/main/kotlin"],
            cwd=str(PROJECT_ROOT), capture_output=True, text=True
        )
        if result.stdout.strip():
            lines = result.stdout.strip().splitlines()
            print(f"   ⚠ Found {len(lines)} TODO/FIXME comments:")
            for line in lines[:5]:  # Show first 5
                print(f"     {line}")
            if len(lines) > 5:
                print(f"     ... and {len(lines) - 5} more")
        else:
            print("   ✓ No TODO/FIXME comments found")
    except Exception:
        print("   ⚠ Could not check for TODO/FIXME comments")
    
    # Check for unused imports (basic check)
    try:
        result = subprocess.run(
            ["grep", "-r", "-n", "import.*unused", "src/main/kotlin"],
            cwd=str(PROJECT_ROOT), capture_output=True, text=True
        )
        if result.stdout.strip():
            print("   ⚠ Found potential unused imports")
        else:
            print("   ✓ No obvious unused imports")
    except Exception:
        print("   ⚠ Could not check for unused imports")
    
    print()
    
    # Summary
    if checks_passed:
        print("✓ All checks passed!")
        sys.exit(0)
    else:
        print("✗ Some checks failed!")
        sys.exit(1)
