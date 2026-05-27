import subprocess
import time
from ..daemon import DaemonManager, PROJECT_ROOT

def register(subparsers):
    p = subparsers.add_parser("generate", help="Generate GNOME bindings")

def run(args):
    DaemonManager.stop_daemon()
    
    print("Generating bindings...")
    script = PROJECT_ROOT / "scripts" / "generate_bindings.sh"
    
    start = time.time()
    res = subprocess.run([str(script)], cwd=str(PROJECT_ROOT))
    elapsed = int(time.time() - start)
    
    if res.returncode == 0:
        print(f"\nBindings generated in {elapsed}s")
    else:
        print(f"\nGeneration failed (exit code {res.returncode})")
