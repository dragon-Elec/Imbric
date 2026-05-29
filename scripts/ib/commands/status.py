import os
import time
import subprocess
from ..process import ProcessManager, ProcessInfo
from ..daemon import DaemonManager, PROJECT_ROOT, PID_FILE, LOG_FILE

def register(subparsers):
    p = subparsers.add_parser("status", help="Show detailed process status with memory and uptime")
    p.add_argument("--verbose", "-v", action="store_true", help="Show full command lines")

def _get_uptime(pid: int) -> str:
    """Get process uptime from /proc/pid/stat."""
    try:
        with open(f"/proc/{pid}/stat") as f:
            parts = f.read().split()
            # Field 21 is starttime in clock ticks
            starttime = int(parts[21])
            # Get system uptime
            with open("/proc/uptime") as f:
                uptime_secs = float(f.read().split()[0])
            # Get clock ticks per second
            ticks_per_sec = os.sysconf(os.sysconf_names["SC_CLK_TCK"])
            # Calculate process start time relative to system boot
            proc_start_secs = starttime / ticks_per_sec
            # Calculate uptime
            proc_uptime = uptime_secs - proc_start_secs
            if proc_uptime < 60:
                return f"{int(proc_uptime)}s"
            elif proc_uptime < 3600:
                return f"{int(proc_uptime // 60)}m {int(proc_uptime % 60)}s"
            else:
                return f"{int(proc_uptime // 3600)}h {int((proc_uptime % 3600) // 60)}m"
    except (FileNotFoundError, ValueError, IndexError, OSError):
        return "?"

def _get_memory_details(pid: int) -> dict:
    """Get detailed memory info from /proc/pid/status."""
    details = {"rss": "?", "vms": "?", "shared": "?"}
    try:
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    kb = int(line.split()[1])
                    details["rss"] = f"{kb / 1024:.0f}MB" if kb > 1024 else f"{kb}KB"
                elif line.startswith("VmSize:"):
                    kb = int(line.split()[1])
                    details["vms"] = f"{kb / 1024:.0f}MB" if kb > 1024 else f"{kb}KB"
                elif line.startswith("VmStk:"):
                    kb = int(line.split()[1])
                    details["shared"] = f"{kb / 1024:.0f}MB" if kb > 1024 else f"{kb}KB"
    except (FileNotFoundError, ValueError, IndexError):
        pass
    return details

def _format_process(proc: ProcessInfo, verbose: bool = False) -> str:
    """Format a process for display."""
    mem = proc.mem or "?"
    uptime = _get_uptime(proc.pid)
    cmd = proc.cmd if verbose else proc.cmd[:80] + "..." if len(proc.cmd) > 80 else proc.cmd
    return f"  PID {proc.pid:>6}  {mem:>6}  {uptime:>6}  {cmd}"

def run(args):
    print("=== Imbric Status ===")
    print()
    
    # Daemon status
    pid = DaemonManager.read_pid()
    if pid:
        uptime = _get_uptime(pid)
        mem = _get_memory_details(pid)
        print(f"Daemon:    PID {pid} (uptime: {uptime}, RSS: {mem['rss']})")
        if LOG_FILE.exists():
            size = LOG_FILE.stat().st_size
            print(f"Log:       {LOG_FILE} ({size / 1024:.0f}KB)")
    else:
        print("Daemon:    not running")
    print()
    
    # Process status
    status = ProcessManager.get_status()
    total_mem = 0
    total_procs = 0
    
    for category, procs in status.items():
        if not procs:
            continue
        print(f"{category.replace('_', ' ').title()}:")
        for p in procs:
            print(_format_process(p, args.verbose))
            total_procs += 1
        print()
    
    if total_procs == 0:
        print("No processes running. Safe to start dev.")
    else:
        print(f"Total: {total_procs} process(es)")
    
    # Show recent log entries if daemon is running
    if pid and LOG_FILE.exists():
        print()
        print("Recent log:")
        try:
            with open(LOG_FILE) as f:
                lines = f.readlines()
                for line in lines[-5:]:
                    print(f"  {line.rstrip()}")
        except Exception:
            pass
