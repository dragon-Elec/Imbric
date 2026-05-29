import os
import subprocess
from ..process import ProcessManager, ProcessInfo

def register(subparsers):
    p = subparsers.add_parser("processes", help="Show all running Gradle/Kotlin/Imbric processes")
    p.add_argument("--kill", "-k", action="store_true", help="Kill all processes after showing")
    p.add_argument("--force", "-f", action="store_true", help="Force kill (SIGKILL)")
    p.add_argument("--verbose", "-v", action="store_true", help="Show full command lines")

def _get_process_details(pid: int) -> dict:
    """Get detailed process info from /proc/pid."""
    details = {
        "name": "?",
        "state": "?",
        "threads": "?",
        "rss": "?",
        "vms": "?",
        "cpu_time": "?",
        "start_time": "?",
    }
    try:
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                if line.startswith("Name:"):
                    details["name"] = line.split()[1]
                elif line.startswith("State:"):
                    details["state"] = line.split()[1]
                elif line.startswith("Threads:"):
                    details["threads"] = line.split()[1]
                elif line.startswith("VmRSS:"):
                    kb = int(line.split()[1])
                    details["rss"] = f"{kb / 1024:.0f}MB" if kb > 1024 else f"{kb}KB"
                elif line.startswith("VmSize:"):
                    kb = int(line.split()[1])
                    details["vms"] = f"{kb / 1024:.0f}MB" if kb > 1024 else f"{kb}KB"
    except (FileNotFoundError, ValueError, IndexError):
        pass
    
    try:
        with open(f"/proc/{pid}/stat") as f:
            parts = f.read().split()
            # Fields 13-14 are utime and stime in clock ticks
            utime = int(parts[13])
            stime = int(parts[14])
            ticks_per_sec = os.sysconf(os.sysconf_names["SC_CLK_TCK"])
            total_secs = (utime + stime) / ticks_per_sec
            details["cpu_time"] = f"{total_secs:.1f}s"
    except (FileNotFoundError, ValueError, IndexError):
        pass
    
    return details

def _format_process(proc: ProcessInfo, verbose: bool = False) -> str:
    """Format a process for display."""
    details = _get_process_details(proc.pid)
    mem = proc.mem or "?"
    cpu = details["cpu_time"]
    threads = details["threads"]
    state = details["state"]
    cmd = proc.cmd if verbose else proc.cmd[:60] + "..." if len(proc.cmd) > 60 else proc.cmd
    
    return f"  {proc.pid:>6}  {mem:>6}  {cpu:>6}  {threads:>3}  {state:<2}  {cmd}"

def run(args):
    print("=== Running Processes ===")
    print()
    
    status = ProcessManager.get_status()
    total_procs = 0
    
    for category, procs in status.items():
        if not procs:
            continue
        print(f"{category.replace('_', ' ').title()}:")
        print(f"  {'PID':>6}  {'MEM':>6}  {'CPU':>6}  {'THR':>3}  {'ST':<2}  COMMAND")
        for p in procs:
            print(_format_process(p, args.verbose))
            total_procs += 1
        print()
    
    if total_procs == 0:
        print("No processes running.")
    else:
        print(f"Total: {total_procs} process(es)")
    
    if args.kill:
        print()
        if args.force:
            print("Force killing all processes...")
            killed = ProcessManager.kill_all(force=True)
        else:
            print("Killing all processes...")
            killed = ProcessManager.kill_all(force=False)
        
        if killed:
            print(f"Killed {len(killed)} process(es).")
        else:
            print("No processes to kill.")
