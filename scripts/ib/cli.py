import argparse
import importlib
import sys
from .daemon import DaemonManager
from .process import ProcessManager

# Plugin command modules, registered and dispatched per-module so a single broken
# import costs only its own command instead of the whole CLI.
COMMAND_MODULES = (
    "clean", "doctor", "generate", "exec_cmd", "history", "run", "test",
    "audit", "compile", "status", "processes", "memory", "bench",
    "project", "lint",
)

def cmd_dev(args):
    DaemonManager.start_daemon()

def cmd_hot(args):
    DaemonManager.start_daemon(hot=True)

def cmd_stop(args):
    DaemonManager.stop_daemon()

def cmd_status(args):
    from .commands.status import run as status_run
    status_run(args)

def cmd_log(args):
    from .daemon import LOG_FILE
    import subprocess
    if not LOG_FILE.exists():
        print(f"No log file at {LOG_FILE}")
        return
    if args.follow:
        try:
            subprocess.run(["tail", "-f", "-n", str(args.lines), str(LOG_FILE)])
        except KeyboardInterrupt:
            pass
    else:
        subprocess.run(["tail", "-n", str(args.lines), str(LOG_FILE)])

def cmd_kill(args):
    killed = ProcessManager.kill_all(force=True)
    if killed:
        print(f"Killed {len(killed)} process(es): {', '.join(killed)}")
    else:
        print("No processes to kill.")

def main():
    parser = argparse.ArgumentParser(prog="ib", description="Imbric Build Utility")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("dev", help="Start build daemon (continuous mode)")
    sub.add_parser("hot", help="Start hot-reload daemon (JBR DCEVM required)")
    sub.add_parser("stop", help="Stop daemon")
    sub.add_parser("kill", help="Kill all Gradle/Kotlin/Imbric processes")

    log_p = sub.add_parser("log", help="Show daemon log")
    log_p.add_argument("-f", "--follow", action="store_true")
    log_p.add_argument("-n", "--lines", type=int, default=50)

    # Register command plugins
    # Per-module: one module failing to import (or a typo in one file) used to abort the
    # whole block — ZERO commands registered, and the user saw 'invalid choice' with only
    # a stale warning line for context. Each module registers independently so one bad
    # import costs exactly its own command.
    for name in COMMAND_MODULES:
        try:
            mod = importlib.import_module(f".commands.{name}", __package__)
            mod.register(sub)
        except ImportError as e:
            print(f"Warning: '{name}' command not available: {e}")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    cmds = {
        "dev": cmd_dev, "hot": cmd_hot, "stop": cmd_stop,
        "log": cmd_log, "kill": cmd_kill
    }
    
    if args.command in cmds:
        cmds[args.command](args)
    elif args.command in COMMAND_MODULES:
        try:
            mod = importlib.import_module(f".commands.{args.command}", __package__)
            mod.run(args)
        except ImportError as e:
            print(f"Error: '{args.command}' command not available: {e}")
            sys.exit(1)
    else:
        print(f"Unknown command: {args.command}")
        parser.print_help()
        sys.exit(1)
