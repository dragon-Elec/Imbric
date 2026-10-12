import subprocess
import time
import sys
from pathlib import Path
from ..daemon import PROJECT_ROOT, gradle_base_cmd
from ..filter import OutputFilter

def register(subparsers):
    p = subparsers.add_parser("lint", help="Run code quality checks")
    p.add_argument("--fix", action="store_true", help="Auto-fix issues where possible")
    p.add_argument("--strict", action="store_true", help="Fail on warnings")

def run(args):
    print("Running code quality checks...")
    print()
    
    if args.fix:
        print("note: --fix not supported (no auto-fixer configured: lint runs compile + grep checks)", file=sys.stderr)
    
    checks_passed = True
    
    # 1. Check compilation
    print("1. Compilation check...")
    gradle_cmd = gradle_base_cmd("compileKotlin")
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
            if args.strict and filt.warnings:
                print(f"   ✗ Compilation warnings ({elapsed}s)")
                checks_passed = False
            else:
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
    gradle_cmd = gradle_base_cmd("compileTestKotlin")
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
            if args.strict and filt.warnings:
                print(f"   ✗ Test compilation warnings ({elapsed}s)")
                checks_passed = False
            else:
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
        # grep exits 0=match, 1=no match, 2=error (missing dir). Treating 2 as
        # "clean" reported success for a check that never ran.
        if result.returncode == 2:
            print("   ⚠ TODO/FIXME check could not run (src/main/kotlin missing?)")
            if args.strict:
                checks_passed = False
        elif result.stdout.strip():
            lines = result.stdout.strip().splitlines()
            print(f"   ⚠ Found {len(lines)} TODO/FIXME comments:")
            for line in lines[:5]:  # Show first 5
                print(f"     {line}")
            if len(lines) > 5:
                print(f"     ... and {len(lines) - 5} more")
            if args.strict:
                checks_passed = False
        else:
            print("   ✓ No TODO/FIXME comments found")
    except Exception:
        print("   ⚠ Could not check for TODO/FIXME comments")

    # Check for unused imports (basic check)
    try:
        # Kotlin marks an unused import by never referencing the symbol; the old
        # pattern `import.*unused` matched nothing in any real Kotlin file and so
        # always reported clean. Detect imports whose simple name never appears
        # again in the file body.
        result = subprocess.run(
            [sys.executable, str(Path(__file__).parent / "_unused_imports.py")],
            cwd=str(PROJECT_ROOT), capture_output=True, text=True
        )
        if result.returncode != 0:
            # 2 = missing source dir. Any other non-zero is an unexpected crash,
            # and reporting that as "✓ No obvious unused imports" would claim a
            # clean bill of health for a check that never completed.
            print("   ⚠ unused-import check could not run (non-zero exit)")
            if args.strict:
                checks_passed = False
        elif result.stdout.strip():
            # Advisory only: this is a name-occurrence heuristic, and deleting an
            # import it wrongly flags breaks compilation. It informs; it does not
            # gate --strict.
            print("   ⚠ Found potential unused imports (advisory — verify before removing):")
            for line in result.stdout.strip().splitlines()[:5]:
                print(f"     {line}")
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
