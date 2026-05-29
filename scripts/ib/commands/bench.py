import subprocess
import time
import sys
import re
from ..daemon import PROJECT_ROOT
from ..filter import OutputFilter

def register(subparsers):
    p = subparsers.add_parser("bench", help="Run benchmarks with clean output")
    p.add_argument("--tests", type=str, help="Run specific benchmark class (e.g. 'GioListingBenchmark')")
    p.add_argument("--all", action="store_true", help="Run all benchmarks")

def run(args):
    gradle_cmd = ["./gradlew", "test", "--console=plain"]
    
    if args.tests:
        gradle_cmd.extend(["--tests", args.tests])
    elif args.all:
        # Run all benchmark tests
        gradle_cmd.extend(["--tests", "*Benchmark*"])
    else:
        # Default: run GioListingBenchmark
        gradle_cmd.extend(["--tests", "GioListingBenchmark"])
    
    print(f"Running benchmarks...")
    filt = OutputFilter(mode="bench")
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
        elapsed_str = f"{elapsed}s" if elapsed < 60 else f"{elapsed//60}m {elapsed%60}s"
        
        if proc.returncode == 0:
            print(f"\nBenchmarks completed in {elapsed_str}")
        else:
            print(f"\nBenchmarks failed (exit code {proc.returncode}) in {elapsed_str}")
            sys.exit(proc.returncode)
    
    except KeyboardInterrupt:
        proc.terminate()
        print("\nInterrupted.")
        sys.exit(1)
