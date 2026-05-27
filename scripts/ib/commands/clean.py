import shutil
from pathlib import Path
from ..daemon import DaemonManager, PROJECT_ROOT

def register(subparsers):
    p = subparsers.add_parser("clean", help="Clean build artifacts")
    p.add_argument("--deep", action="store_true", help="Also delete .gradle caches")
    p.add_argument("--bindings", action="store_true", help="Only delete generated bindings")

def run(args):
    DaemonManager.stop_daemon()
    
    if args.bindings:
        target = PROJECT_ROOT / "build" / "native-gen"
        if target.exists():
            shutil.rmtree(target)
            print("Cleaned bindings.")
        return

    build_dir = PROJECT_ROOT / "build"
    if build_dir.exists():
        shutil.rmtree(build_dir)
        print("Cleaned build directory.")
        
    if args.deep:
        gradle_cache = PROJECT_ROOT / ".gradle" / "caches"
        if gradle_cache.exists():
            shutil.rmtree(gradle_cache)
            print("Cleaned Gradle caches.")
