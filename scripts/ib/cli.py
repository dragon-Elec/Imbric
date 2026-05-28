import argparse
import sys
from .daemon import DaemonManager
from .process import ProcessManager

def cmd_dev(args):
    DaemonManager.start_daemon()

def cmd_hot(args):
    DaemonManager.start_daemon(hot=True)

def cmd_stop(args):
    DaemonManager.stop_daemon()

def cmd_status(args):
    from .daemon import PID_FILE
    pid = DaemonManager.read_pid()
    if pid:
        print(f"Daemon:  imbric-daemon (PID {pid}) — running")
    else:
        print("Daemon:  not running")

    status = ProcessManager.get_status()
    for p in status["gradle_daemons"]:
        print(f"Gradle:  GradleDaemon (PID {p.pid}) — {p.mem}")
    for p in status["kotlin_daemons"]:
        print(f"Kotlin:  KotlinCompileDaemon (PID {p.pid}) — {p.mem}")
    for p in status["app_processes"]:
        print(f"App:     com.imbric.app (PID {p.pid}) — {p.mem}")
    for p in status["gradlew_processes"]:
        print(f"Gradlew: gradlew (PID {p.pid}) — {p.mem}")
        
    if not any(status.values()):
        print("No processes running. Safe to start dev.")

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
    sub.add_parser("status", help="Show process status")
    sub.add_parser("kill", help="Kill all Gradle/Kotlin/Imbric processes")

    log_p = sub.add_parser("log", help="Show daemon log")
    log_p.add_argument("-f", "--follow", action="store_true")
    log_p.add_argument("-n", "--lines", type=int, default=50)

    # We will register command plugins here later
    try:
        from .commands import clean, doctor, generate, exec_cmd, history, run
        clean.register(sub)
        doctor.register(sub)
        generate.register(sub)
        exec_cmd.register(sub)
        history.register(sub)
        run.register(sub)
    except ImportError as e:
        pass # Optional commands

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    cmds = {
        "dev": cmd_dev, "hot": cmd_hot, "stop": cmd_stop,
        "status": cmd_status, "log": cmd_log, "kill": cmd_kill
    }
    
    if args.command in cmds:
        cmds[args.command](args)
    else:
        # Delegate to command plugins
        from .commands import clean, doctor, generate, exec_cmd, history, run
        cmd_modules = {
            "clean": clean.run,
            "doctor": doctor.run,
            "generate": generate.run,
            "exec": exec_cmd.run,
            "history": history.run,
            "run": run.run,
        }
        if args.command in cmd_modules:
            cmd_modules[args.command](args)
