import subprocess
import time
from ..daemon import PROJECT_ROOT
from ..filter import OutputFilter

def register(subparsers):
    p = subparsers.add_parser("exec", help="Execute arbitrary command with filtering")
    p.add_argument("cmd", nargs="+", help="Command to run")

def run(args):
    print(f"Running: {' '.join(args.cmd)}\n")
    
    filt = OutputFilter(mode="run")
    start = time.time()
    
    try:
        proc = subprocess.Popen(
            args.cmd,
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
            print(f"\nCompleted in {elapsed_str}")
        else:
            print(f"\nFailed (code {proc.returncode}) in {elapsed_str}")
            
    except KeyboardInterrupt:
        proc.terminate()
        print("\nInterrupted.")
